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
    assert all(s.endswith("?v=abc123") for s in seen)       # every fetch is cache-busted


def test_a_stale_file_is_named(pages, tmp_path):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    (served / "admin/localization/de/units.json").write_text("yesterday", encoding="utf-8")
    assert L.check("abc123", base=base, docs=docs, tries=2, pause=0) == ["admin/localization/de/units.json"]


def test_a_file_missing_from_the_site_is_named(pages, tmp_path):
    served, base, _seen = pages
    docs = _tree(tmp_path / "docs")
    (served / "admin/localization/index.html").unlink()
    assert L.check("abc123", base=base, docs=docs, tries=1, pause=0) == ["admin/localization/index.html"]


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
    assert "scripts/cel-arabic.css" in files and "assets/css/dashboard.css" in files
