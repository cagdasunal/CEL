"""The post-push live check tells a served desk that matches the push from one that does not.

Driven over real HTTP against a local server standing in for GitHub Pages.
"""
from __future__ import annotations

import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from localize_desk import live_check as L


def _tree(root: Path, body: str = "desk") -> Path:
    for p in ("admin/localization/index.html", "admin/localization/de/index.html",
              "admin/localization/de/units.json", "assets/css/dashboard.css"):
        f = root / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{body}:{p}", encoding="utf-8")
    return root


@pytest.fixture()
def pages(tmp_path):
    served = _tree(tmp_path / "served")
    seen = []

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(served), **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append(self.path)
            super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield served, f"http://127.0.0.1:{srv.server_address[1]}", seen
    srv.shutdown()
    srv.server_close()


def test_a_served_desk_that_matches_the_push_passes(pages, tmp_path):
    _served, base, seen = pages
    docs = _tree(tmp_path / "docs")
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == []
    # Every file is read past the edge (cache-busted by the commit) ...
    assert {s for s in seen if "?v=" in s} == {f"/{p}?v=abc123" for p in L.served_files(docs)}
    # ... and at the URL a reviewer's browser asks for.
    assert "/admin/localization/de/" in seen and "/admin/localization/de/units.json" in seen


def test_a_stale_file_is_named(pages, tmp_path):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    (served / "admin/localization/de/units.json").write_text("yesterday", encoding="utf-8")
    assert L.check("abc123", base=base, docs=docs, tries=2, pause=0) == ["admin/localization/de/units.json"]


def test_a_file_missing_from_the_site_is_named(pages, tmp_path):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    (served / "admin/localization/de/units.json").unlink()
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == ["admin/localization/de/units.json"]


def test_a_deploy_that_catches_up_passes_on_a_retry(pages, tmp_path, monkeypatch):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    target = served / "admin/localization/de/index.html"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(L.time, "sleep",
                        lambda s: target.write_text("desk:admin/localization/de/index.html", encoding="utf-8"))
    assert L.check("abc123", base=base, docs=docs, tries=3, pause=1) == []


def test_the_real_checkout_lists_every_language():
    files = L.served_files()
    for code in L.LOCALES:
        assert f"admin/localization/{code}/index.html" in files
        assert f"admin/localization/{code}/units.json" in files
    # Every same-origin script and stylesheet the pages load -- the save path needs auth.js
    # (the signed-in user) and dashboard-config.js (the Worker's URL) -- and nothing they don't.
    for asset in ("assets/css/dashboard.css", "assets/js/auth.js", "assets/js/dashboard-config.js"):
        assert asset in files
    assert "scripts/cel-arabic.css" not in files


def test_the_languages_are_the_desks():
    """The check's list is the generator's, so a new language cannot go unchecked."""
    from localize_desk import generate_desk_page as G
    assert L.LOCALES == tuple(code for code, *_ in G.LOCALES)


def test_the_edge_copy_reviewers_get_is_checked(pages, tmp_path, monkeypatch):
    """A CDN still serving yesterday's page at the plain URL, while the cache-busted read is
    fresh, is a stale desk for every reviewer (the review's probe: check() said [])."""
    _served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    real = L._fetch
    monkeypatch.setattr(L, "_fetch", lambda url, **k: b"yesterday" if url.endswith("/de/") else real(url, **k))
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == ["admin/localization/de/index.html"]


def test_a_link_with_a_query_is_read_at_that_url(pages, tmp_path, monkeypatch):
    """The index sends reviewers to /de/?show=check -- its own cache key at the edge."""
    served, base, seen = pages
    docs = _tree(tmp_path / "docs")
    for root in (docs, served):
        (root / "admin/localization/index.html").write_text(
            '<a href="/admin/localization/de/?show=check">de</a>', encoding="utf-8")
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == []
    assert "/admin/localization/de/?show=check" in seen
    real = L._fetch
    monkeypatch.setattr(L, "_fetch", lambda url, **k: b"yesterday" if url.endswith("?show=check") else real(url, **k))
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == ["admin/localization/de/index.html"]


def test_a_script_the_page_loads_is_checked(pages, tmp_path):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    for root in (docs, served):
        (root / "assets/js").mkdir(parents=True, exist_ok=True)
        (root / "assets/js/auth.js").write_text("new", encoding="utf-8")
        (root / "admin/localization/de/index.html").write_text(
            '<script src="/assets/js/auth.js"></script>', encoding="utf-8")
    (served / "assets/js/auth.js").write_text("old", encoding="utf-8")      # the same length
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == ["assets/js/auth.js"]


def test_a_gzip_answer_is_compared_decompressed(tmp_path):
    """Browsers get the gzip variant (Vary: Accept-Encoding); the check asks for it too."""
    import gzip
    body = "desk:admin/localization/index.html".encode()

    class H(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            z = gzip.compress(body)
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(z)))
            self.end_headers()
            self.wfile.write(z)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert L._fetch(f"http://127.0.0.1:{srv.server_address[1]}/x") == body
    finally:
        srv.shutdown()
        srv.server_close()


def test_main_exits_1_on_a_stale_desk_and_0_on_a_match(pages, tmp_path, monkeypatch, capsys):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    monkeypatch.setattr(L, "DOCS", docs)
    assert L.main(["--sha", "abc123", "--base", base, "--tries", "1", "--pause", "0"]) == 0
    (served / "admin/localization/de/units.json").write_text("yesterday", encoding="utf-8")
    assert L.main(["--sha", "abc123", "--base", base, "--tries", "1", "--pause", "0"]) == 1
    assert "admin/localization/de/units.json" in capsys.readouterr().err


def test_main_fails_on_an_empty_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DOCS", tmp_path / "docs")
    assert L.main(["--sha", "abc123", "--tries", "1", "--pause", "0"]) == 1


def test_a_check_overtaken_by_a_newer_push_hands_over(pages, tmp_path, monkeypatch, capsys):
    """A check still running when a newer push deploys compares the old commit with the new
    files. When main has moved on, the newer deploy's own check covers the desk: pass, and
    say so. When main has not moved, a mismatch stays red."""
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    monkeypatch.setattr(L, "DOCS", docs)
    (served / "admin/localization/de/units.json").write_text("newer", encoding="utf-8")
    argv = ["--sha", "abc123", "--base", base, "--tries", "1", "--pause", "0",
            "--repo", "https://example.invalid/r"]
    monkeypatch.setattr(L, "_main_head", lambda repo: "def456")
    assert L.main(argv) == 0
    assert "def456" in capsys.readouterr().out
    monkeypatch.setattr(L, "_main_head", lambda repo: "abc123")
    assert L.main(argv) == 1
    monkeypatch.setattr(L, "_main_head", lambda repo: None)     # unknown: never a pass
    assert L.main(argv) == 1
