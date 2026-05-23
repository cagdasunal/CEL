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

    tracker-098 (2026-05-21): bumped 8000 -> 16000. The reconfiguration raised
    summary length (650-1100 words ~= 1500-2500 visible tokens); combined with
    ~7000 dynamic thinking tokens that exceed 8000, the 3 longest landing
    summaries truncated (visible output clipped at ~850-1365 tokens). 16000
    covers ~13000 thinking + ~3000 visible. Only ACTUAL tokens are billed, so
    raising the ceiling adds no cost on its own — it just stops the clip.
    """

    custom_id: str
    system_blocks: list[dict]
    user_message: str
    max_tokens: int = 16000
    enable_thinking: bool = True
    # tracker-097: per-request model (tiering). Empty → config.MODEL_ID (Pro).
    # cli sets this from config.model_for_content_type(content_type), so blog
    # requests run on Flash and the rest on Pro. The Batch API takes ONE model
    # per job, so cli groups requests by this field before submitting.
    model: str = ""


@dataclass
class BatchHandle:
    """Identifier returned by submit_batch. Dry-run handles have id starting with 'dryrun-'."""

    batch_id: str
    request_count: int
    submitted_at: str
    dry_run: bool
    artifact_path: Optional[Path] = None
    # tracker-097: explicit-context-cache resource names created for this batch.
    # wait_for_batch deletes them once the batch reaches a terminal state (the
    # cache must outlive async batch processing, so we can't delete at submit).
    cache_names: list = field(default_factory=list)
    # M5 (2026-05-23): count of eligible caches that FAILED to create (swallowed in
    # _create_caches). A silent cache miss means full-price billing with no signal — a
    # burst contributor — so surface it on the handle for the report.
    cache_create_failures: int = 0


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


# ---- Cost estimation (tracker-097: per-model, batch-vs-interactive, cache-aware) ----


# Verified 2026-05-21 against https://ai.google.dev/gemini-api/docs/pricing.
# Rates are (input_$/M, output_$/M). "interactive" = the synchronous
# generate_content path (used by --sync); "batch" = the Batch API (50% of
# interactive). cache_read = price of a cached-prefix token; cache_min = the
# minimum prefix size that is cacheable for that model family.
#
# tracker-097 RC2: the old PRICE_* constants were the Pro Batch rates ($1/$6)
# applied to BOTH paths — but --sync bills at interactive ($2/$12), so every sync
# run undershot by 2×. The estimator now prices by the path actually used.
_PRICING = {
    "pro": {
        "interactive": (2.00, 12.00),
        "batch": (1.00, 6.00),
        "cache_read": 0.20,
        "cache_min": 4096,
    },
    "flash": {
        "interactive": (0.30, 2.50),
        "batch": (0.15, 1.25),
        "cache_read": 0.03,
        "cache_min": 1024,
    },
}

# Back-compat module constants (Pro Batch tier — the historical defaults). The
# estimator drives off _PRICING; these remain for any external reference.
PRICE_INPUT_PER_M = _PRICING["pro"]["batch"][0]        # 1.00
PRICE_OUTPUT_PER_M = _PRICING["pro"]["batch"][1]       # 6.00
PRICE_CACHE_READ_PER_M = _PRICING["pro"]["cache_read"]  # 0.20


def _model_family(model: str) -> str:
    """Classify a Gemini model id into a pricing family ('flash' | 'pro')."""
    return "flash" if "flash" in (model or "").lower() else "pro"


def _cache_min_tokens(model: str) -> int:
    return _PRICING[_model_family(model)]["cache_min"]


def _est_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token). Floor of 1 for any non-empty text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _request_model(r: Any, default_model: str) -> str:
    return (getattr(r, "model", "") or "") or default_model


def estimate_batch_cost_usd(
    requests: Iterable[Any],
    *,
    mode: str = "batch",
    cached: bool = False,
    avg_output_tokens_per_request: int = 800,
    avg_input_tokens_per_request: int = 6500,
    default_model: Optional[str] = None,
) -> float:
    """Estimate a run's USD cost from the actual request content.

    tracker-097 rewrite. Honest accounting that fixes the two undershoots that
    masked the real spend:
      - RC2: `mode` selects the rate tier actually billed — "interactive" for the
        --sync path ($2/$12 Pro), "batch" for the Batch API ($1/$6 Pro).
      - RC1: caching is credited ONLY when `cached=True` (explicit caching actually
        engaged this run). The old estimator always assumed a fictional 2,500-token
        cached prefix, so it under-priced reality.

    Per-request input/output tokens come from the request's own system + user text
    when available (BatchRequest), falling back to the avg defaults for objects
    without that shape (e.g. TranslationUnit count-proxy callers). Each request is
    priced at its own model's rate (BatchRequest.model), defaulting to
    default_model or config.MODEL_ID. When cached, requests are grouped by
    (model, system text); a group with >= config.CACHE_MIN_GROUP_SIZE items and a
    prefix >= the model's cache_min pays one full-rate prefix "write" + the
    cache-read rate on every request's prefix. Per-request user tokens always pay
    full rate.
    """
    reqs = list(requests)
    n = len(reqs)
    if n == 0:
        return 0.0
    default_model = default_model or config.MODEL_ID
    mode = "interactive" if mode == "interactive" else "batch"

    total = 0.0
    cache_groups: dict[tuple[str, str], dict[str, int]] = {}

    for r in reqs:
        model = _request_model(r, default_model)
        in_rate, out_rate = _PRICING[_model_family(model)][mode]

        sys_blocks = getattr(r, "system_blocks", None)
        user_msg = getattr(r, "user_message", None)
        if sys_blocks is None and user_msg is None:
            # Non-BatchRequest (e.g. TranslationUnit) — fall back to the avg defaults.
            sys_text, sys_tok, usr_tok = "", 0, avg_input_tokens_per_request
            out_tok = avg_output_tokens_per_request
        else:
            sys_text = _flatten_system_blocks(sys_blocks or [])
            sys_tok = _est_tokens(sys_text)
            usr_tok = _est_tokens(user_msg or "")
            # C1 (2026-05-23): output allowance per (model family, thinking). Gemini bills
            # thinking AS output, so a flat 800 under-projected Pro ~6x (the burst RC).
            fam = _model_family(model)
            thinking = bool(getattr(r, "enable_thinking", True))
            out_tok = config.OUTPUT_TOKEN_ESTIMATE.get(
                (fam, thinking), config.DEFAULT_OUTPUT_TOKEN_ESTIMATE
            )

        total += (out_tok / 1_000_000) * out_rate

        if cached and sys_tok >= _cache_min_tokens(model):
            g = cache_groups.setdefault((model, sys_text), {"prefix": sys_tok, "count": 0})
            g["count"] += 1
            total += (usr_tok / 1_000_000) * in_rate  # user tokens always full rate
        else:
            total += ((sys_tok + usr_tok) / 1_000_000) * in_rate

    # Cached groups: only groups large enough to cache get the discount; smaller
    # groups fall back to a full-rate prefix on every request (mirrors submit_batch).
    for (model, _sys), g in cache_groups.items():
        in_rate, _ = _PRICING[_model_family(model)][mode]
        cache_read_rate = _PRICING[_model_family(model)]["cache_read"]
        prefix, count = g["prefix"], g["count"]
        if count >= config.CACHE_MIN_GROUP_SIZE:
            total += (prefix / 1_000_000) * in_rate                  # 1 cache write
            total += (count * prefix / 1_000_000) * cache_read_rate  # N cache reads
        else:
            total += (count * prefix / 1_000_000) * in_rate          # too small to cache
    return total


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
            model = r.model or config.MODEL_ID
            line = {
                "custom_id": r.custom_id,
                "model": model,
                "request": _build_inlined_request_dict(r, system_text, model=model),
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


def _build_generation_config(
    r: BatchRequest,
    system_text: str,
    model: str = "",
    cached_content_name: Optional[str] = None,
) -> dict:
    """Build Gemini's GenerateContentConfig dict from our BatchRequest.

    NOTE: Gemini 3.x Pro REQUIRES thinking mode — `thinking_budget=0` is rejected
    with "This model only works in thinking mode". For Pro we pass the configured
    budget when `enable_thinking=True`; when False (the translate phase) we OMIT
    thinking_config so the model uses its dynamic default. Verified live 2026-05-19.

    tracker-097: Gemini 2.5 Flash (the blog tier) DOES support disabling thinking,
    so we set `thinking_budget=0` to minimize output/thinking cost on the bulk blog
    path (the QA gate is the quality backstop). When `cached_content_name` is set
    (explicit context cache), we OMIT system_instruction — it lives in the cache —
    and reference the cache instead.
    """
    model = model or r.model or config.MODEL_ID
    cfg: dict[str, Any] = {"max_output_tokens": r.max_tokens}
    if cached_content_name:
        cfg["cached_content"] = cached_content_name
    elif system_text:
        cfg["system_instruction"] = system_text
    if _model_family(model) == "flash":
        cfg["thinking_config"] = {"thinking_budget": 0}
    elif r.enable_thinking:
        cfg["thinking_config"] = {"thinking_budget": config.THINKING_BUDGET_TOKENS}
    # else (Pro, no thinking requested): omit — model picks its dynamic default.
    return cfg


def _build_inlined_request_dict(
    r: BatchRequest,
    system_text: str,
    model: str = "",
    cached_content_name: Optional[str] = None,
) -> dict:
    """Build the InlinedRequest payload (dict shape) for the SDK.

    Verified against google-genai 2.4.0:
      InlinedRequest fields = {model, contents, metadata, config}
      config is GenerateContentConfig (not "generation_config")
      metadata is dict[str,str] — used to round-trip our custom_id.
    """
    return {
        "contents": [{"parts": [{"text": r.user_message}], "role": "user"}],
        "config": _build_generation_config(r, system_text, model, cached_content_name),
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


# ---- Explicit context caching (tracker-097 Phase 1) ----


@dataclass
class CachePlanEntry:
    """One (model, system-prefix) group + whether it's worth caching."""

    system_text: str
    model: str
    request_count: int
    prefix_tokens: int
    eligible: bool
    reason: str = ""


def plan_caches(requests: list[BatchRequest], model: str = "") -> list[CachePlanEntry]:
    """Group requests by their flattened system prefix; decide which to cache.

    A group is cache-eligible when it has >= config.CACHE_MIN_GROUP_SIZE requests
    AND its prefix is >= the model's minimum cacheable size. Pure function (no API
    calls) so the dry-run report can show the plan and tests can assert it offline.
    """
    default = model or config.MODEL_ID
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for r in requests:
        m = r.model or default
        sys_text = _flatten_system_blocks(r.system_blocks)
        if not sys_text:
            continue
        key = (m, sys_text)
        if key not in counts:
            counts[key] = 0
            order.append(key)
        counts[key] += 1
    out: list[CachePlanEntry] = []
    for (m, sys_text) in order:
        count = counts[(m, sys_text)]
        prefix_tokens = _est_tokens(sys_text)
        min_tok = _cache_min_tokens(m)
        if count < config.CACHE_MIN_GROUP_SIZE:
            eligible, reason = False, f"group too small ({count} < {config.CACHE_MIN_GROUP_SIZE})"
        elif prefix_tokens < min_tok:
            eligible, reason = False, f"prefix {prefix_tokens} tok < model min {min_tok}"
        else:
            eligible, reason = True, "cacheable"
        out.append(CachePlanEntry(
            system_text=sys_text, model=m, request_count=count,
            prefix_tokens=prefix_tokens, eligible=eligible, reason=reason,
        ))
    return out


def _create_caches(client: Any, plan: list[CachePlanEntry]) -> dict[str, str]:
    """Create explicit context caches for eligible plan entries. Fallback-safe:
    any per-cache failure is swallowed so the run proceeds at full price.
    Returns {system_text: cache_resource_name}."""
    created: dict[str, str] = {}
    for entry in plan:
        if not entry.eligible:
            continue
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            cache = _retry_transient(lambda e=entry, ts=ts: client.caches.create(
                model=e.model,
                config={
                    "system_instruction": e.system_text,
                    "ttl": f"{config.CACHE_TTL_SECONDS}s",
                    "display_name": f"cel-summary-cache-{ts}",
                },
            ))
            name = getattr(cache, "name", None)
            if name:
                created[entry.system_text] = name
        except Exception:  # noqa: BLE001 — caching is an optimization; never fatal
            continue
    return created


def _delete_caches(client: Any, cache_names: Iterable[str]) -> None:
    """Best-effort delete of created caches (the TTL is the backstop)."""
    for name in cache_names:
        try:
            client.caches.delete(name=name)
        except Exception:  # noqa: BLE001 — TTL auto-expires the cache anyway
            continue


def _persist_last_batch(handle: BatchHandle, requests: list[BatchRequest], model: str) -> None:
    """Persist the submitted batch's id + custom_ids so a cancelled/failed run can
    `cancel-batch` / `retrieve-batch` it later (tracker-097 RC5). Best-effort —
    never fatal to a submit. Overwrites: a multi-model run records its LAST group's
    batch_id (the per-run report.json carries every batch_id)."""
    try:
        path = config.LAST_BATCH_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "batch_id": handle.batch_id,
            "model": model,
            "submitted_at": handle.submitted_at,
            "request_count": handle.request_count,
            "custom_ids": [r.custom_id for r in requests],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def cancel_batch(batch_id: str, api_key_env: str = "GEMINI_API_KEY") -> str:
    """Cancel a running Gemini batch so it stops processing + billing (RC5).

    A submitted Gemini batch keeps running (and billing) even after the GitHub
    Actions run that launched it is cancelled — this is the recovery handle.
    Returns the post-cancel state name. Imports the SDK lazily.
    """
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Environment variable {api_key_env} is not set.")
    from google import genai  # type: ignore

    client = genai.Client(api_key=api_key)
    _retry_transient(lambda: client.batches.cancel(name=batch_id))
    job = _retry_transient(lambda: client.batches.get(name=batch_id))
    return _job_state_name(job)


# ---- Live submit ----


def submit_batch(
    requests: list[BatchRequest],
    api_key_env: str = "GEMINI_API_KEY",
    model: Optional[str] = None,
) -> BatchHandle:
    """Submit a real batch to Gemini. Imports google-genai SDK lazily.

    tracker-097: all requests in one batch share ONE model (cli groups by model
    before calling, since the Batch API takes a single model per job). When
    config.ENABLE_EXPLICIT_CACHE is on, eligible system-prefix groups are cached
    and referenced via `cached_content`; the cache names ride on the returned
    handle and are deleted by wait_for_batch after the batch completes (the cache
    must outlive async batch processing). Caching is fallback-safe: if the cached
    submit is rejected, we rebuild the batch without caching and submit once. The
    submitted batch_id is persisted to config.LAST_BATCH_FILE for cancel/retrieve.
    """
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

    model = model or (requests[0].model if requests else "") or config.MODEL_ID
    client = genai.Client(api_key=api_key)
    display_name = f"cel-summary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    cache_by_system: dict[str, str] = {}
    cache_failures = 0
    if config.ENABLE_EXPLICIT_CACHE:
        _plan = plan_caches(requests, model)
        cache_by_system = _create_caches(client, _plan)
        # M5 (2026-05-23): surface eligible caches that silently failed to create — a
        # cache that doesn't engage means full-price input billing with no signal.
        cache_failures = max(0, sum(1 for e in _plan if e.eligible) - len(cache_by_system))

    def _src(with_cache: bool) -> list[dict]:
        out: list[dict] = []
        for r in requests:
            system_text = _flatten_system_blocks(r.system_blocks)
            cname = cache_by_system.get(system_text) if with_cache else None
            out.append(_build_inlined_request_dict(r, system_text, model=model, cached_content_name=cname))
        return out

    try:
        batch = _retry_transient(lambda: client.batches.create(
            model=model, src=_src(bool(cache_by_system)),
            config={"display_name": display_name},
        ))
    except Exception:  # noqa: BLE001 — if caching made the submit invalid, retry uncached
        if not cache_by_system:
            raise
        _delete_caches(client, list(cache_by_system.values()))
        cache_by_system = {}
        batch = _retry_transient(lambda: client.batches.create(
            model=model, src=_src(False),
            config={"display_name": display_name},
        ))

    batch_name = getattr(batch, "name", None) or str(batch)
    _PENDING_BATCHES[batch_name] = list(requests)
    handle = BatchHandle(
        batch_id=batch_name,
        request_count=len(requests),
        submitted_at=datetime.now(timezone.utc).isoformat(),
        dry_run=False,
        cache_names=list(cache_by_system.values()),
        cache_create_failures=cache_failures,
    )
    _persist_last_batch(handle, requests, model)
    return handle


def generate_sync(
    requests: list[BatchRequest], api_key_env: str = "GEMINI_API_KEY"
) -> list[BatchResult]:
    """Synchronous generation — one `models.generate_content` call per request,
    results returned immediately (no Batch API queue / ≤24h SLA).

    Per-request model (tracker-097 tiering: `BatchRequest.model` or config.MODEL_ID)
    + generation config as the Batch path; only the transport differs. Cost is the
    standard (non-batch / interactive) rate, so this is for FAST TESTING + small runs
    — not the full catalog (use the Batch API for that). The sync path does NOT use
    explicit context caching (negligible ROI on the handful of items it's meant for;
    Gemini 3.x still applies implicit prefix caching automatically). Each request is
    independent: a per-request failure becomes a failed BatchResult and never aborts
    the rest. Imports the google-genai SDK lazily so dry-run + import work without it.
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
        model = r.model or config.MODEL_ID
        cfg = _build_generation_config(r, system_text, model)
        try:
            resp = _retry_transient(
                lambda r=r, cfg=cfg, model=model: client.models.generate_content(
                    model=model, contents=r.user_message, config=cfg
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
    except KeyboardInterrupt:
        # H1 (2026-05-23): a Ctrl-C / SIGTERM (e.g. a cancelled GitHub-Actions run) must
        # STOP the batch's billing, not just exit and leave it running. Best-effort cancel,
        # then re-raise. A submitted Gemini batch keeps processing + billing otherwise.
        try:
            client.batches.cancel(name=handle.batch_id)
        except Exception:  # noqa: BLE001 — best-effort; never mask the interrupt
            pass
        raise
    finally:
        original_requests = _PENDING_BATCHES.pop(handle.batch_id, [])
        # tracker-097: release the explicit context caches now that the batch has
        # reached a terminal state (or we've abandoned it on timeout). Best-effort;
        # the cache TTL is the backstop. Safe when cache_names is empty.
        _delete_caches(client, handle.cache_names)

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

    # L1 (2026-05-23): a successfully-completed batch no longer needs the recovery
    # pointer — clear it so last-batch.json never lingers pointing at a done batch
    # (only `cancel_batch` cleared it before, so a clean success left a stale pointer).
    try:
        config.LAST_BATCH_FILE.unlink(missing_ok=True)
    except OSError:
        pass
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
