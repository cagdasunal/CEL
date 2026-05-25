"""copywriter CLI — the fetch allowlist (defensive guard on _resolve_before).

The static-page target URL is operator-supplied via the brief; _resolve_before must
only fetch over https from englishcollege.com, and must NOT call out for anything else.
"""
import types

from tools.copywriter.brief import CopyRequest
from tools.copywriter.cli import _is_allowlisted_url, _resolve_before


def test_is_allowlisted_url_accepts_https_englishcollege():
    assert _is_allowlisted_url("https://www.englishcollege.com/courses")
    assert _is_allowlisted_url("https://cel.englishcollege.com/llms.txt")
    assert _is_allowlisted_url("https://englishcollege.com/")


def test_is_allowlisted_url_rejects_other():
    assert not _is_allowlisted_url("http://www.englishcollege.com/x")        # not https
    assert not _is_allowlisted_url("https://evil.example.com/x")             # wrong host
    assert not _is_allowlisted_url("https://englishcollege.com.evil.com/x")  # suffix trick
    assert not _is_allowlisted_url("https://evil-englishcollege.com/x")      # prefix trick
    assert _is_allowlisted_url(None) is False                                # non-str (G4)
    assert _is_allowlisted_url(123) is False                                 # non-str (G4)


def test_resolve_before_refuses_non_allowlisted_url(monkeypatch):
    import tools.core.web.page_fetcher as pf
    calls = {"n": 0}

    def _spy(*a, **k):
        calls["n"] += 1
        return types.SimpleNamespace(body_text_excerpt="SHOULD NOT BE USED")

    monkeypatch.setattr(pf, "fetch_page", _spy)
    req = CopyRequest(brief="x", target={"kind": "static_page", "url": "http://evil.example.com/x"})
    out = _resolve_before(req)
    assert calls["n"] == 0            # fetch_page never called for a non-allowlisted URL
    assert out.existing_copy == ""    # proceeds with empty copy (non-fatal)


def test_resolve_before_fetches_allowlisted_url(monkeypatch):
    import tools.core.web.page_fetcher as pf
    calls = {"n": 0}

    def _spy(url, *a, **k):
        calls["n"] += 1
        return types.SimpleNamespace(body_text_excerpt="Fetched body.")

    monkeypatch.setattr(pf, "fetch_page", _spy)
    req = CopyRequest(brief="x", target={"kind": "static_page", "url": "https://www.englishcollege.com/courses"})
    out = _resolve_before(req)
    assert calls["n"] == 1
    assert out.existing_copy == "Fetched body."
