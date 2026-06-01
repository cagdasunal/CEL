"""Regression guards for the genai client per-request HTTP timeout (tracker 138).

A hung Gemini request must fail in minutes, not ride the 60-min GitHub job cap
(the blog-summary-autopilot deferred item). These tests exercise `_gemini_client`
directly so they cover both the live-SDK path and the unit-test mock path.
"""
from types import SimpleNamespace

from tools.core.gemini import client as gc


def test_timeout_constant_is_sane():
    # 1–10 minutes, in milliseconds (google-genai HttpOptions.timeout is ms).
    assert 60_000 <= gc._GEMINI_HTTP_TIMEOUT_MS <= 600_000


def test_client_applies_http_timeout_when_types_available():
    """Real-SDK shape (genai.types present) → client gets http_options w/ the timeout."""
    captured = {}
    fake = SimpleNamespace(
        Client=lambda **kw: (captured.update(kw), SimpleNamespace(**kw))[1],
        types=SimpleNamespace(HttpOptions=lambda **kw: SimpleNamespace(**kw)),
    )
    gc._gemini_client(fake, "key")
    assert "http_options" in captured
    assert captured["http_options"].timeout == gc._GEMINI_HTTP_TIMEOUT_MS


def test_client_degrades_when_types_absent():
    """Unit-test mocks inject a SimpleNamespace `genai` with `.Client` but no `.types`.
    The helper must NOT raise (it degrades to http_options=None). This reproduces the
    AttributeError that reddened cel stress-test on 2026-06-01."""
    captured = {}
    fake = SimpleNamespace(Client=lambda **kw: (captured.update(kw), SimpleNamespace(**kw))[1])
    gc._gemini_client(fake, "key")  # must not raise AttributeError
    assert captured.get("http_options") is None
