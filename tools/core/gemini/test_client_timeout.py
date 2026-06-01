"""Regression guard: every genai.Client in client.py carries the reliability HTTP
timeout (tracker 138). A hung Gemini request must fail in minutes, not ride the
60-min GitHub job cap (the blog-summary-autopilot deferred item)."""
from pathlib import Path

from tools.core.gemini import client as gemini_client


def test_timeout_constant_is_sane():
    # 1–10 minutes, expressed in milliseconds (google-genai HttpOptions.timeout is ms).
    assert 60_000 <= gemini_client._GEMINI_HTTP_TIMEOUT_MS <= 600_000


def test_no_bare_genai_client_construction():
    """Every `genai.Client(...)` must pass http_options with the timeout — a bare
    construction would silently reintroduce the unbounded-hang gap."""
    lines = Path(gemini_client.__file__).read_text(encoding="utf-8").splitlines()
    calls = [ln.strip() for ln in lines if "genai.Client(" in ln]
    assert calls, "expected at least one genai.Client(...) construction"
    bare = [ln for ln in calls if "http_options" not in ln]
    assert not bare, f"bare genai.Client without http_options timeout: {bare}"
