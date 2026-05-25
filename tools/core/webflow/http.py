"""Webflow Data API v2 HTTP plumbing (shared, leaf).

Token resolution, the retry/backoff request loop (429/5xx + timeout/URLError), and the
error type — used by tools.core.webflow.cms and any tool talking to the Webflow Data
API. Stdlib urllib only. Moved here from tools/summary/webflow_client.py in Plan B.
See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional

WEBFLOW_API_BASE = "https://api.webflow.com/v2"


class WebflowApiError(RuntimeError):
    """Raised on HTTP / network error from the Webflow API."""


def resolve_token(env: str = "WEBFLOW_API_TOKEN") -> str:
    """Return the Webflow API token from the environment, or raise."""
    token = os.environ.get(env, "").strip()
    if not token:
        raise RuntimeError(
            f"Environment variable {env} is not set or empty. "
            f"Required for live Webflow API calls."
        )
    return token


def request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 30.0,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Issue one Webflow API request with retry/backoff. Returns parsed JSON ({} on
    empty body). Retries 429/5xx + transient timeout/URLError with 2**attempt backoff;
    raises WebflowApiError after exhausting attempts (or on a non-retryable 4xx).
    """
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    last_exc: Optional[WebflowApiError] = None
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                last_exc = WebflowApiError(f"HTTP {e.code} {method} {url}: {body[:200]}")
                time.sleep(2 ** attempt)
                continue
            raise WebflowApiError(f"HTTP {e.code} {method} {url}: {body[:500]}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            # A socket read-timeout raises a BARE TimeoutError (not URLError); catch both
            # and retry transient ones with backoff so one slow PATCH doesn't abort a batch.
            reason = getattr(e, "reason", e)
            last_exc = WebflowApiError(f"Network error {method} {url}: {reason}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise last_exc from e
    raise last_exc if last_exc else WebflowApiError(f"Request failed: {method} {url}")
