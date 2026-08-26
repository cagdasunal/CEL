"""Retry behaviour of the Offers Webflow HTTP wrapper.

Content Pipeline run 32902744831 (2026-08-25) hit
`[offers_viewer] ERROR fetching offers: HTTP 406 ... 406 Not Acceptable`
on a plain paginated GET. api_request had no retry at all, so a single
edge/WAF blip was fatal. 98 of the surrounding 100 runs succeeded and the
same GET returned 200 from a laptop, so the 406 was transient.

Retry is deliberately scoped to GET: replaying a PATCH/POST could
double-apply a write the server had already accepted.
"""
import io
import sys
import time as _time
import urllib.error
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pytest  # noqa: E402

from tools.offers import _token_helper as th  # noqa: E402


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b'{"m":"blocked"}'))


def _urlopen_stub(codes, monkeypatch):
    calls = {"n": 0}

    class _Resp:
        def read(self): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, *a, **kw):
        i = calls["n"]; calls["n"] += 1
        if i < len(codes):
            raise _http_error(codes[i])
        return _Resp()

    monkeypatch.setattr(th.urllib.request, "urlopen", fake)
    # Patch the stdlib module object, not `th.time` — `th` may not import time
    # at all (it did not before this fix), and an AttributeError here would make
    # these tests fail for a fixture reason instead of the behaviour under test.
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    return calls


def test_transient_406_on_get_is_retried(monkeypatch):
    """The exact production failure: one 406 must not kill the step."""
    calls = _urlopen_stub([406], monkeypatch)
    assert th.api_request("GET", "http://x", "tok") == {"ok": True}
    assert calls["n"] == 2, f"406 was not retried (calls={calls['n']})"


def test_429_and_5xx_on_get_are_retried(monkeypatch):
    calls = _urlopen_stub([429, 503], monkeypatch)
    assert th.api_request("GET", "http://x", "tok") == {"ok": True}
    assert calls["n"] == 3


def test_real_client_errors_on_get_are_not_retried(monkeypatch):
    for code in (400, 401, 403, 404, 422):
        calls = _urlopen_stub([code] * 9, monkeypatch)
        with pytest.raises(th.APIError):
            th.api_request("GET", "http://x", "tok")
        assert calls["n"] == 1, f"{code} must not be retried (calls={calls['n']})"


def test_writes_are_never_retried(monkeypatch):
    """A PATCH/POST replay could double-apply an already-accepted write."""
    for method in ("PATCH", "POST", "PUT", "DELETE"):
        calls = _urlopen_stub([406] * 9, monkeypatch)
        with pytest.raises(th.APIError):
            th.api_request(method, "http://x", "tok", data={"a": 1})
        assert calls["n"] == 1, f"{method} must not retry (calls={calls['n']})"


def test_persistent_transient_status_still_raises(monkeypatch):
    """Retry must not silently mask a sustained outage."""
    _urlopen_stub([406] * 99, monkeypatch)
    with pytest.raises(th.APIError) as ei:
        th.api_request("GET", "http://x", "tok")
    assert ei.value.status == 406 if hasattr(ei.value, "status") else True
