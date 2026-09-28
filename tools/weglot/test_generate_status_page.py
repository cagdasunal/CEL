"""Tests for generate_status_page.render_summaries_html translation folding (tracker-107).

generate_status_page.py is a byte-identical mirror of the monorepo SSOT, so this test
covers both copies' folding logic. It monkeypatches the two on-disk data sources
(`_latest_summary_run_dir`, `_load_translation_status`) so no real artifacts are read.
"""
import json
from pathlib import Path

from tools.weglot import generate_status_page as g


def _stub_run_dir(tmp_path: Path) -> Path:
    (tmp_path / "en-summaries.json").write_text(
        json.dumps({
            "gen-0": {
                "url": "https://www.englishcollege.com/a",
                "markdown": "## Tag\n\n### Title\n\nWord one two three four.",
                "content_type": "landing",
                "locale": "en",
            },
        }),
        encoding="utf-8",
    )
    return tmp_path


def test_overview_folds_translations_into_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "_latest_summary_run_dir", lambda: _stub_run_dir(tmp_path))
    monkeypatch.setattr(g, "_load_translation_status", lambda: {
        "generated_at": "2026-05-24T00:00:00+00:00",
        "target_locales": ["de", "fr"],
        "per_locale": {
            "de": {"translated": 1, "failed": 0, "csv": "de.csv", "words": 100, "internal_links": 7},
            "fr": {"translated": 1, "failed": 0, "csv": "fr.csv", "words": 120, "internal_links": 7},
        },
        "per_item": {"gen-0": ["de", "fr"]},
    })
    html = g.render_summaries_html()
    # Total summaries = 1 source + 2 translated = 3, with the source/translated split shown.
    assert "<strong>3</strong>" in html
    assert "1 source + 2 translated" in html
    # Translated words (100 + 120 = 220) folded into Total words (source words + 220).
    src_words = g._count_words_in_markdown("## Tag\n\n### Title\n\nWord one two three four.")
    assert f"{src_words + 220:,}" in html
    # By-language now includes the translated locales.
    assert "German" in html and "French" in html


def test_overview_unchanged_when_no_translation_status(tmp_path, monkeypatch):
    """Pre-translation state: no status file → totals are source-only, no split note."""
    monkeypatch.setattr(g, "_latest_summary_run_dir", lambda: _stub_run_dir(tmp_path))
    monkeypatch.setattr(g, "_load_translation_status", lambda: {})
    html = g.render_summaries_html()
    assert "<strong>1</strong>" in html          # 1 source summary, nothing folded
    assert "source +" not in html                # no translated split note


def test_a_frozen_pages_summary_is_not_offered_for_pasting(tmp_path, monkeypatch):
    """Review round 2 (localization runbook WO-32, L3 P1-1): pasting a frozen page's
    summary changes its English under every approval made in the open round."""
    import json as _json
    from tools.weglot import generate_status_page as gsp
    summaries = tmp_path / "static-summaries"
    summaries.mkdir()
    for slug in ("vancouver", "vancouver-vs-toronto", "home"):
        (summaries / f"{slug}.summary.md").write_text("## x\n")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(_json.dumps({"schema_version": 1, "frozen_pages": ["/vancouver"],
                                   "frozen_until": None}))
    monkeypatch.setattr(gsp, "STATIC_SUMMARIES_DIR", summaries)
    monkeypatch.setattr(gsp, "FREEZE_FILE", freeze)
    page = gsp.render_files_html()
    assert "static-summaries/vancouver.summary.md" not in page
    assert "static-summaries/vancouver-vs-toronto.summary.md" in page     # per page, not prefix
    assert "static-summaries/home.summary.md" in page
    assert page.count("Do not paste") == 1
    freeze.write_text("{broken")                                           # unreadable: hold all
    assert gsp.render_files_html().count("Do not paste") == 3


import pytest as _pytest


@_pytest.mark.parametrize("doc", [
    {"schema_version": 1, "frozen_pages": ["/vancouver"], "frozen_until": ""},
    {"schema_version": 1, "frozen_pages": ["/vancouver"], "frozen_until": "10/01/2026"},
    {"schema_version": 1, "frozen_pages": ["https://www.englishcollege.com/vancouver"], "frozen_until": None},
    {"schema_version": 2, "frozen_pages": ["/vancouver"], "frozen_until": None},
    {"schema_version": 1, "frozen_pages": "/vancouver", "frozen_until": None},
])
def test_a_freeze_the_pipeline_would_refuse_holds_every_paste(tmp_path, monkeypatch, doc):
    """Round 3 review of WO-32: the dashboard read these as "nothing frozen" while the
    summary pipeline refused them and held every page."""
    import json as _json
    from tools.weglot import generate_status_page as gsp
    summaries = tmp_path / "static-summaries"
    summaries.mkdir()
    for slug in ("vancouver", "home"):
        (summaries / f"{slug}.summary.md").write_text("## x\n")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(_json.dumps(doc))
    monkeypatch.setattr(gsp, "STATIC_SUMMARIES_DIR", summaries)
    monkeypatch.setattr(gsp, "FREEZE_FILE", freeze)
    assert gsp.frozen_paste_slugs() is None
    assert gsp.render_files_html().count("Do not paste") == 2

