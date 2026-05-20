"""Gemini 3.1 Pro Batch API submission + retrieval (tracker-091 migration).

Dry-run mode writes the would-be batch payload to disk as JSONL and returns a
mock handle — no HTTP request fires.

Live mode uses the `google-genai` SDK. The SDK is imported lazily so the module
loads (and dry-run works) without the dependency installed in the local venv.

Per-request custom_id round-trips via the SDK's `InlinedRequest.metadata` dict
(verified against google-genai 2.4.0). At submit time the request's custom_id
is stored in `metadata={"custom_id": ...}`; at response parse time the same
metadata is read back from `InlinedResponse.metadata`. Falls back to index
ordering if metadata is missing.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from tools.summary import config


# ---- Data types (interface stable — cli.py + tests depend on these) ----


@dataclass(frozen=True)
class BatchRequest:
    """One request in a Gemini batch.

    NOTE on max_tokens (tracker-091 M-11 + M-12.5, 2026-05-19): Gemini's
    `max_output_tokens` is a CEILING on thinking_tokens + visible_tokens —
    NOT just visible output (this is a critical semantic difference from
    Anthropic's `max_tokens`).

    M-11 bumped this 2000 → 4000 after a 60-word pilot truncation. M-12.5
    bumped it again 4000 → 8000 after a second pilot smoke-test showed
    the home page still truncating at output_tokens=156 — Gemini's
    `thinking_config.thinking_budget=1500` setting is ADVISORY, not a
    hard cap; the model spent ~3844 thinking tokens on the home summary
    and hit the 4000 ceiling. Bump to 8000 gives headroom for up to
    ~7000 dynamic thinking + ~1000 visible output, which covers every
    summary length we currently produce. The trade-off is cost: billed
    output is `thinking + visible` tokens × $6/M; a typical summary now
    costs ~$0.025 instead of ~$0.013, but that's $0.001-0.002 per page
    in absolute terms.

    If thinking-budget enforcement improves in a future Gemini model
    we can pull this back down. Until then, the M-11 truncation detector
    in `_parse_inline_response` ensures any future shortfall fails loud
    (MANUAL_REVIEW) instead of silently writing clipped copy.
    """

    custom_id: str
    system_blocks: list[dict]
    user_message: str
    max_tokens: int = 8000
    enable_thinking: bool = True


@dataclass
class BatchHandle:
    """Identifier returned by submit_batch. Dry-run handles have id starting with 'dryrun-'."""

    batch_id: str
    request_count: int
    submitted_at: str
    dry_run: bool
    artifact_path: Optional[Path] = None


@dataclass
class BatchResult:
    """One result row from the batch."""

    custom_id: str
    succeeded: bool
    content: str = ""
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0  # Gemini doesn't fill this; kept for interface stability
    cache_read_tokens: int = 0


# ---- Cost estimation ----


# Gemini 3.1 Pro Preview — Batch tier pricing (prompts ≤ 200k tokens).
# Per https://ai.google.dev/gemini-api/docs/pricing as of 2026-05-19.
# These ARE the batched prices already — no additional discount multiplier.
# (tracker-091 M-12.2: BATCH_DISCOUNT constant removed — was a no-op carryover
#  from the Anthropic implementation where Batch tier carried a 0.5 multiplier.)
PRICE_INPUT_PER_M = 1.00
PRICE_OUTPUT_PER_M = 6.00
PRICE_CACHE_READ_PER_M = 0.20
PRICE_CACHE_WRITE_PER_M = 0.0  # Implicit caching on Batch tier — no explicit write cost


def estimate_batch_cost_usd(
    requests: Iterable[BatchRequest],
    avg_input_tokens_per_request: int = 4500,
    avg_output_tokens_per_request: int = 800,
    cached_prefix_tokens: int = 2500,
) -> float:
    """Rough cost estimate for a batch. Assumes implicit prompt caching is active.

    Returns USD. Prices in PRICE_* constants are already the Batch-tier rates
    published by Gemini; no extra discount multiplier is applied.
    """
    n = sum(1 for _ in requests)
    if n == 0:
        return 0.0
    # First request "writes" cache implicitly (cost 0 on Gemini Batch);
    # remaining (n-1) read cache at the cache-read rate.
    cache_write_total = cached_prefix_tokens
    cache_read_total = max(0, n - 1) * cached_prefix_tokens
    variable_input_total = n * max(0, avg_input_tokens_per_request - cached_prefix_tokens)
    output_total = n * avg_output_tokens_per_request

    return (
        (variable_input_total / 1_000_000) * PRICE_INPUT_PER_M
        + (cache_write_total / 1_000_000) * PRICE_CACHE_WRITE_PER_M
        + (cache_read_total / 1_000_000) * PRICE_CACHE_READ_PER_M
        + (output_total / 1_000_000) * PRICE_OUTPUT_PER_M
    )


# ---- Submit→wait fallback (for custom_id mapping when metadata is missing) ----


# Primary path: custom_id round-trips via InlinedRequest.metadata.
# Fallback path: index ordering against the stashed request list.
_PENDING_BATCHES: dict[str, list[BatchRequest]] = {}


# ---- Dry-run submit ----


def dry_run_submit(
    requests: list[BatchRequest],
    artifact_dir: Optional[Path] = None,
) -> BatchHandle:
    """Write the batch payload to disk; no API call fires."""
    artifact_dir = artifact_dir or config.DRYRUN_DIR
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_dir / f"{timestamp}-batch.jsonl"

    with artifact_path.open("w", encoding="utf-8") as f:
        for r in requests:
            system_text = _flatten_system_blocks(r.system_blocks)
            line = {
                "custom_id": r.custom_id,
                "model": config.MODEL_ID,
                "request": _build_inlined_request_dict(r, system_text),
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    return BatchHandle(
        batch_id=f"dryrun-{uuid.uuid4().hex[:12]}",
        request_count=len(requests),
        submitted_at=datetime.now(timezone.utc).isoformat(),
        dry_run=True,
        artifact_path=artifact_path,
    )


def _flatten_system_blocks(blocks: list[dict]) -> str:
    """Concatenate text from system_blocks into one string for Gemini system_instruction.

    Accepts either {"type": "text", "text": "..."} dicts or plain strings.
    Empty blocks/strings are skipped.
    """
    if not blocks:
        return ""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict):
            t = b.get("text", "")
        else:
            t = str(b)
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def _build_generation_config(r: BatchRequest, system_text: str) -> dict:
    """Build Gemini's GenerateContentConfig dict from our BatchRequest.

    NOTE: Gemini 3.1 Pro Preview REQUIRES thinking mode — `thinking_budget=0`
    is rejected with "This model only works in thinking mode". When the
    caller passes `enable_thinking=True` we use the configured budget;
    when `enable_thinking=False` (the translate phase) we OMIT thinking_config
    entirely so the model uses its dynamic default (typically small for
    short tasks). Verified live 2026-05-19 against gemini-3.1-pro-preview.
    """
    cfg: dict[str, Any] = {
        "max_output_tokens": r.max_tokens,
    }
    if system_text:
        cfg["system_instruction"] = system_text
    if r.enable_thinking:
        cfg["thinking_config"] = {"thinking_budget": config.THINKING_BUDGET_TOKENS}
    # else: omit thinking_config — model picks default budget dynamically.
    return cfg


def _build_inlined_request_dict(r: BatchRequest, system_text: str) -> dict:
    """Build the InlinedRequest payload (dict shape) for the SDK.

    Verified against google-genai 2.4.0:
      InlinedRequest fields = {model, contents, metadata, config}
      config is GenerateContentConfig (not "generation_config")
      metadata is dict[str,str] — used to round-trip our custom_id.
    """
    return {
        "contents": [{"parts": [{"text": r.user_message}], "role": "user"}],
        "config": _build_generation_config(r, system_text),
        "metadata": {"custom_id": r.custom_id},
    }


# ---- Transient-error retry (tracker-092 Phase 2.3) ----

# Substrings that indicate a RETRYABLE (transient) failure — network blips,
# 5xx, rate limits. Permanent errors (e.g. 400 API_KEY_INVALID) do NOT match
# and raise immediately, so we never burn retries on an unfixable error.
_TRANSIENT_MARKERS = (
    "timeout", "timed out", "deadline", "temporarily", "unavailable",
    "connection", "reset by peer", "503", "502", "500", "429", "rate limit",
)


def _is_transient(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(m in s for m in _TRANSIENT_MARKERS)


def _retry_transient(fn, *, attempts: int = 3, base_delay: float = 2.0):
    """Call `fn()`; on a transient-looking exception retry with exponential
    backoff (base_delay * 2**i). Non-transient errors and the final attempt
    re-raise immediately. Keeps a mid-run 503/429 from crashing the pipeline.
    """
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — classify, then re-raise
            if not _is_transient(e) or i == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** i))
    raise RuntimeError("unreachable")  # pragma: no cover


# ---- Live submit ----


def submit_batch(requests: list[BatchRequest], api_key_env: str = "GEMINI_API_KEY") -> BatchHandle:
    """Submit a real batch to Gemini. Imports google-genai SDK lazily."""
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"Environment variable {api_key_env} is not set. Required for live API calls."
        )
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "google-genai SDK is not installed. Run `pip install google-genai` "
            "or use tools/summary/requirements.txt."
        ) from e

    client = genai.Client(api_key=api_key)
    src: list[dict] = []
    for r in requests:
        system_text = _flatten_system_blocks(r.system_blocks)
        src.append(_build_inlined_request_dict(r, system_text))

    display_name = f"cel-summary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    batch = _retry_transient(lambda: client.batches.create(
        model=config.MODEL_ID,
        src=src,
        config={"display_name": display_name},
    ))
    batch_name = getattr(batch, "name", None) or str(batch)

    # Stash request list for wait_for_batch's custom_id reconstruction.
    _PENDING_BATCHES[batch_name] = list(requests)

    return BatchHandle(
        batch_id=batch_name,
        request_count=len(requests),
        submitted_at=datetime.now(timezone.utc).isoformat(),
        dry_run=False,
    )


def generate_sync(
    requests: list[BatchRequest], api_key_env: str = "GEMINI_API_KEY"
) -> list[BatchResult]:
    """Synchronous generation — one `models.generate_content` call per request,
    results returned immediately (no Batch API queue / ≤24h SLA).

    Same model (`config.MODEL_ID`) + generation config as the Batch path; only the
    transport differs. Cost is the standard (non-batch) rate, so this is for FAST
    TESTING + small runs — not the full catalog (use the Batch API for that). Each
    request is independent: a per-request failure becomes a failed BatchResult and
    never aborts the rest (mirrors the Batch path's per-row isolation). Imports the
    google-genai SDK lazily so dry-run + module import work without it installed.
    """
    if not requests:
        return []
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"Environment variable {api_key_env} is not set. Required for live API calls."
        )
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "google-genai SDK is not installed. Run `pip install google-genai` "
            "or use tools/summary/requirements.txt."
        ) from e

    client = genai.Client(api_key=api_key)
    results: list[BatchResult] = []
    for r in requests:
        system_text = _flatten_system_blocks(r.system_blocks)
        cfg = _build_generation_config(r, system_text)
        try:
            resp = _retry_transient(
                lambda r=r, cfg=cfg: client.models.generate_content(
                    model=config.MODEL_ID, contents=r.user_message, config=cfg
                )
            )
            results.append(_result_from_response(resp, r.custom_id))
        except Exception as e:  # noqa: BLE001 — isolate per-request failure
            results.append(BatchResult(custom_id=r.custom_id, succeeded=False, error=str(e)))
    return results


def wait_for_batch(
    handle: BatchHandle,
    poll_interval_sec: int = 60,
    timeout_sec: int = 24 * 3600,
    api_key_env: str = "GEMINI_API_KEY",
) -> list[BatchResult]:
    """Poll a live Gemini batch until completion; return parsed results.

    Raises TimeoutError if the batch is still running after timeout_sec.
    Raises RuntimeError if the batch enters FAILED / CANCELLED / EXPIRED.
    Dry-run handles return an empty list immediately.
    """
    if handle.dry_run:
        return []

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Environment variable {api_key_env} is not set.")
    from google import genai  # type: ignore

    client = genai.Client(api_key=api_key)
    deadline = time.time() + timeout_sec
    batch_job = None
    # tracker-091 M-12.1: pop the stashed request list in a `finally` block so
    # it's released on EVERY exit path — including TimeoutError and the
    # FAILED/CANCELLED/EXPIRED RuntimeError raises. Previously the .pop()
    # only ran on the success path, which leaked one entry per failed batch
    # for the lifetime of the process.
    try:
        while time.time() < deadline:
            batch_job = _retry_transient(lambda: client.batches.get(name=handle.batch_id))
            state = _job_state_name(batch_job)
            if state == "JOB_STATE_SUCCEEDED":
                break
            if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
                raise RuntimeError(f"Batch {handle.batch_id} ended in state {state}")
            time.sleep(poll_interval_sec)
        else:
            raise TimeoutError(f"Batch {handle.batch_id} did not complete within {timeout_sec}s")
    finally:
        original_requests = _PENDING_BATCHES.pop(handle.batch_id, [])

    # Extract inline responses. Gemini returns them in submission order.
    inline_responses = []
    dest = getattr(batch_job, "dest", None)
    if dest is not None:
        inline_responses = getattr(dest, "inlined_responses", None) or []

    results: list[BatchResult] = []
    for i, inline in enumerate(inline_responses):
        custom_id = (
            original_requests[i].custom_id
            if i < len(original_requests)
            else f"unknown-{i}"
        )
        results.append(_parse_inline_response(inline, custom_id))

    return results


def _job_state_name(batch_job: Any) -> str:
    """Extract state name from a BatchJob, handling enum + string variants."""
    state = getattr(batch_job, "state", None)
    if state is None:
        return ""
    return getattr(state, "name", None) or str(state)


def _parse_inline_response(inline: Any, fallback_custom_id: str) -> BatchResult:
    """Parse one Gemini inlined_response → BatchResult.

    Prefers custom_id from `inline.metadata` (round-tripped from submit). Falls
    back to the supplied fallback_custom_id (index-mapped from the request list)
    if metadata is absent.
    """
    metadata = getattr(inline, "metadata", None) or {}
    custom_id = metadata.get("custom_id") if isinstance(metadata, dict) else None
    if not custom_id:
        custom_id = fallback_custom_id

    err = getattr(inline, "error", None)
    if err is not None:
        msg = getattr(err, "message", None) or str(err)
        return BatchResult(custom_id=custom_id, succeeded=False, error=msg)

    response = getattr(inline, "response", None)
    if response is None:
        return BatchResult(custom_id=custom_id, succeeded=False, error="no response")

    return _result_from_response(response, custom_id)


def _result_from_response(response: Any, custom_id: str) -> BatchResult:
    """Parse a Gemini `GenerateContentResponse` → BatchResult.

    Shared by the Batch path (`_parse_inline_response`, via `inline.response`) and
    the synchronous path (`generate_sync`, which gets the response directly). Carries
    the tracker-091 M-11 MAX_TOKENS truncation guard so neither path persists clipped
    copy.
    """
    # Try response.text (convenience property on GenerateContentResponse).
    text = getattr(response, "text", None)
    candidates = getattr(response, "candidates", None) or []
    if not text:
        # Fall back to candidates[0].content.parts[*].text.
        if candidates:
            content = getattr(candidates[0], "content", None)
            if content is not None:
                parts = getattr(content, "parts", None) or []
                text = "".join(getattr(p, "text", "") for p in parts)
    text = text or ""

    # tracker-091 M-11: detect MAX_TOKENS truncation. Gemini's
    # `max_output_tokens` ceiling can clip the visible response mid-sentence
    # when thinking tokens consume most of the budget. The candidate's
    # `finish_reason` reveals this — STOP means clean completion;
    # MAX_TOKENS means the cap was hit. We surface that as a failure so the
    # caller can either retry with a larger budget or mark the row as
    # MANUAL_REVIEW, rather than persisting truncated copy.
    finish_reason = ""
    if candidates:
        fr = getattr(candidates[0], "finish_reason", None)
        if fr is not None:
            finish_reason = getattr(fr, "name", None) or str(fr)
    truncated = finish_reason.upper().endswith("MAX_TOKENS")

    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
    cache_read = getattr(usage, "cached_content_token_count", 0) if usage else 0

    # Note (tracker-091 M-12.3): cache_creation_tokens omitted from both
    # BatchResult constructions below — Gemini's Batch tier uses implicit
    # caching with no explicit "write" cost or signal, so the field has no
    # source to populate from. The dataclass default (0) carries forward
    # for interface stability with the original Anthropic-era callers.
    if truncated:
        return BatchResult(
            custom_id=custom_id,
            succeeded=False,
            content=text,  # preserved for forensics, NOT for write-back
            error=f"truncated: finish_reason={finish_reason} "
                  f"(output_tokens={output_tokens}, max_tokens cap hit — "
                  f"raise BatchRequest.max_tokens)",
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cache_read_tokens=int(cache_read or 0),
        )

    return BatchResult(
        custom_id=custom_id,
        succeeded=bool(text),
        content=text,
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cache_read_tokens=int(cache_read or 0),
    )
