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
