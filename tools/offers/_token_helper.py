"""Stdlib HTTP helpers for Webflow API.

Self-contained copy of api_request / get_api_token / APIError / NetworkError
extracted from scripts/asset_upload.py. No .env fallback — this module ships
in the CEL repo where there is no .env file.

No module-level I/O.
"""
from __future__ import annotations

import json
import time
import os
import urllib.error
import urllib.request


class APIError(Exception):
    """Webflow API error with status code and body."""

    def __init__(self, status_code: int, body: str, url: str) -> None:
        self.status_code = status_code
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status_code} from {url}: {body}")


class NetworkError(Exception):
    """Network connectivity error."""

    def __init__(self, reason: str, url: str) -> None:
        self.reason = reason
        self.url = url
        super().__init__(f"Network error for {url}: {reason}")


def get_api_token(env_var: str = "WEBFLOW_API_TOKEN") -> str | None:
    """Return the API token from the environment variable, or None if unset."""
    return os.environ.get(env_var) or None


# Transient statuses worth retrying on an idempotent read. 406 is what
# Webflow's edge returns when it blocks a request outright — observed
# 2026-08-25 in Content Pipeline run 32902744831, where the identical GET
# succeeded from a laptop and on the next scheduled run.
RETRYABLE_STATUS = frozenset({406, 408, 425, 429})
_RETRY_ATTEMPTS = 4


def api_request(
    method: str,
    url: str,
    token: str,
    data=None,
    content_type: str = "application/json",
) -> dict:
    """Make an authenticated Webflow API request.

    Returns parsed JSON response or raises APIError / NetworkError.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        if content_type == "application/json":
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            body = data
            headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    # Retry only idempotent reads. A GET can be replayed safely; a PATCH/POST
    # cannot, because a transient error may mask a write the server already
    # applied, and a blind replay would double-apply it.
    attempts = _RETRY_ATTEMPTS if method.upper() == "GET" else 1

    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                if resp_body:
                    return json.loads(resp_body)
                return {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            retryable = e.code in RETRYABLE_STATUS or e.code >= 500
            if not retryable or attempt == attempts - 1:
                raise APIError(e.code, error_body, url)
        except urllib.error.URLError as e:
            if attempt == attempts - 1:
                raise NetworkError(str(e.reason), url)
        time.sleep(2 ** attempt)

    # Unreachable: the final attempt either returns or raises above.
    raise NetworkError("retry loop exhausted without a result", url)
