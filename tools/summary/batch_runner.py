"""Claude Message Batches API submission + retrieval.

Dry-run mode writes the would-be batch payload to disk as JSONL and returns a
mock handle — no HTTP request fires.

Live mode uses the `anthropic` SDK. The SDK is imported lazily so the module
loads (and dry-run works) without the dependency installed in the local venv.
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


# ---- Data types ----


@dataclass(frozen=True)
class BatchRequest:
    """One request in a Claude batch."""

    custom_id: str
    system_blocks: list[dict]
    user_message: str
    max_tokens: int = 2000
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
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


# ---- Cost estimation ----


# Opus 4.7 pricing as of 2026-05-16 (verify at https://www.anthropic.com/pricing).
# Batch API applies a 50% discount.
PRICE_INPUT_PER_M = 15.00
PRICE_OUTPUT_PER_M = 75.00
PRICE_CACHE_WRITE_PER_M = 18.75
PRICE_CACHE_READ_PER_M = 1.50
BATCH_DISCOUNT = 0.5


def estimate_batch_cost_usd(
    requests: Iterable[BatchRequest],
    avg_input_tokens_per_request: int = 4500,
    avg_output_tokens_per_request: int = 800,
    cached_prefix_tokens: int = 2500,
) -> float:
    """Rough cost estimate for a batch. Assumes prompt caching is active."""
    n = sum(1 for _ in requests)
    if n == 0:
        return 0.0
    # First request writes cache; remaining (n-1) read cache.
    cache_write_total = cached_prefix_tokens
    cache_read_total = max(0, n - 1) * cached_prefix_tokens
    variable_input_total = n * max(0, avg_input_tokens_per_request - cached_prefix_tokens)
    output_total = n * avg_output_tokens_per_request

    cost = (
        (variable_input_total / 1_000_000) * PRICE_INPUT_PER_M
        + (cache_write_total / 1_000_000) * PRICE_CACHE_WRITE_PER_M
        + (cache_read_total / 1_000_000) * PRICE_CACHE_READ_PER_M
        + (output_total / 1_000_000) * PRICE_OUTPUT_PER_M
    )
    return cost * BATCH_DISCOUNT


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
            line = {
                "custom_id": r.custom_id,
                "params": {
                    "model": config.MODEL_ID,
                    "max_tokens": r.max_tokens,
                    "system": r.system_blocks,
                    "messages": [{"role": "user", "content": r.user_message}],
                    "thinking": (
                        {"type": "enabled", "budget_tokens": config.THINKING_BUDGET_TOKENS}
                        if r.enable_thinking
                        else None
                    ),
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    return BatchHandle(
        batch_id=f"dryrun-{uuid.uuid4().hex[:12]}",
        request_count=len(requests),
        submitted_at=datetime.now(timezone.utc).isoformat(),
        dry_run=True,
        artifact_path=artifact_path,
    )


# ---- Live submit ----


def submit_batch(requests: list[BatchRequest], api_key_env: str = "ANTHROPIC_API_KEY") -> BatchHandle:
    """Submit a real batch to Claude. Imports anthropic SDK lazily."""
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"Environment variable {api_key_env} is not set. Required for live API calls."
        )
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "anthropic SDK is not installed. Run `pip install anthropic` "
            "or use tools/summary/requirements.txt."
        ) from e

    client = anthropic.Anthropic(api_key=api_key)
    batch_requests = []
    for r in requests:
        params: dict[str, Any] = {
            "model": config.MODEL_ID,
            "max_tokens": r.max_tokens,
            "system": r.system_blocks,
            "messages": [{"role": "user", "content": r.user_message}],
        }
        if r.enable_thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": config.THINKING_BUDGET_TOKENS,
            }
        batch_requests.append({"custom_id": r.custom_id, "params": params})

    batch = client.messages.batches.create(requests=batch_requests)
    return BatchHandle(
        batch_id=batch.id,
        request_count=len(requests),
        submitted_at=datetime.now(timezone.utc).isoformat(),
        dry_run=False,
    )


def wait_for_batch(
    handle: BatchHandle,
    poll_interval_sec: int = 60,
    timeout_sec: int = 24 * 3600,
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> list[BatchResult]:
    """Poll a live batch until completion; return parsed results.

    Raises TimeoutError if the batch is still running after timeout_sec.
    Dry-run handles return an empty list immediately.
    """
    if handle.dry_run:
        return []

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Environment variable {api_key_env} is not set.")
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=api_key)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        batch = client.messages.batches.retrieve(handle.batch_id)
        if batch.processing_status == "ended":
            break
        time.sleep(poll_interval_sec)
    else:
        raise TimeoutError(f"Batch {handle.batch_id} did not complete within {timeout_sec}s")

    # Stream results.
    results: list[BatchResult] = []
    for entry in client.messages.batches.results(handle.batch_id):
        custom_id = getattr(entry, "custom_id", "")
        result_obj = getattr(entry, "result", None)
        if result_obj is None:
            results.append(BatchResult(custom_id=custom_id, succeeded=False, error="no result"))
            continue
        if getattr(result_obj, "type", "") == "succeeded":
            msg = result_obj.message
            content_parts = []
            for block in getattr(msg, "content", []):
                if getattr(block, "type", "") == "text":
                    content_parts.append(getattr(block, "text", ""))
            usage = getattr(msg, "usage", None) or type("U", (), {})()
            results.append(
                BatchResult(
                    custom_id=custom_id,
                    succeeded=True,
                    content="".join(content_parts),
                    input_tokens=getattr(usage, "input_tokens", 0),
                    output_tokens=getattr(usage, "output_tokens", 0),
                    cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0),
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
                )
            )
        else:
            err = getattr(result_obj, "error", None)
            err_str = getattr(err, "message", str(err)) if err else "unknown error"
            results.append(BatchResult(custom_id=custom_id, succeeded=False, error=err_str))

    return results
