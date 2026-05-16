"""Tests for tools.summary.csv_emitter — Fidelo CSV merge, idempotency, atomic write."""

import csv
from pathlib import Path

import pytest

from tools.summary.csv_emitter import (
    SummaryPair,
    emit_consolidated_csv,
    pair_from_paragraphs,
    read_existing_csv,
    split_summary_into_paragraphs,
)


_EXISTING_CSV = """id;language_from;language_to;word_from;word_to;type
;en;de;"1 teacher per student";"1 Lehrer pro Schüler";Text
;en;de;"10 - 20 min. by bus to CEL";"10 - 20 Minuten Busfahrt zu CEL";Text
"""


def test_split_paragraphs_markdown():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird."
    paras = split_summary_into_paragraphs(text)
    assert paras == ["First paragraph here.", "Second paragraph here.", "Third."]


def test_split_paragraphs_html():
    text = "<p>First.</p><p>Second.</p>"
    paras = split_summary_into_paragraphs(text)
    assert paras == ["First.", "Second."]


def test_emit_merges_existing_and_new(tmp_path: Path):
    existing = tmp_path / "de.csv"
    existing.write_text(_EXISTING_CSV, encoding="utf-8")
    out = tmp_path / "de.merged.csv"

    pairs = [
        SummaryPair(
            word_from="Welcome to CEL, English school in San Diego.",
            word_to="Willkommen bei CEL, Englischschule in San Diego.",
        ),
        SummaryPair(
            word_from="Our courses run from 1 to 52 weeks.",
            word_to="Unsere Kurse dauern von 1 bis 52 Wochen.",
        ),
    ]
    report = emit_consolidated_csv("de", existing, pairs, out)

    assert report.written_to == out
    assert report.new_row_count == 2
    assert out.exists()

    rows = read_existing_csv(out)
    # Header + 2 existing + 2 new = 5
    assert len(rows) == 5
    # New rows have correct language pair.
    assert rows[3][1] == "en"
    assert rows[3][2] == "de"


def test_emit_idempotent_dedup_on_rerun(tmp_path: Path):
    existing = tmp_path / "de.csv"
    existing.write_text(_EXISTING_CSV, encoding="utf-8")
    out = tmp_path / "de.merged.csv"

    pairs = [
        SummaryPair(word_from="Welcome.", word_to="Willkommen."),
    ]
    emit_consolidated_csv("de", existing, pairs, out)

    # Run again with same pairs — read out (which now has the new row) and merge same pairs.
    report2 = emit_consolidated_csv("de", out, pairs, out)
    assert report2.duplicates_skipped >= 1
    rows = read_existing_csv(out)
    # No duplicates added on rerun.
    word_from_values = [r[3] for r in rows[1:]]
    assert word_from_values.count("Welcome.") == 1


def test_emit_preserves_semicolon_separator(tmp_path: Path):
    existing = tmp_path / "de.csv"
    existing.write_text(_EXISTING_CSV, encoding="utf-8")
    out = tmp_path / "de.merged.csv"
    pairs = [SummaryPair(word_from="hello", word_to="hallo")]
    emit_consolidated_csv("de", existing, pairs, out)
    content = out.read_text(encoding="utf-8")
    # Header line uses semicolon.
    assert content.split("\n")[0] == "id;language_from;language_to;word_from;word_to;type"
    # New row uses semicolon too.
    assert ";en;de;hello;hallo;Text" in content


def test_emit_handles_missing_existing_csv(tmp_path: Path):
    nonexistent = tmp_path / "missing.csv"
    out = tmp_path / "fr.csv"
    pairs = [SummaryPair(word_from="hello", word_to="bonjour")]
    report = emit_consolidated_csv("fr", nonexistent, pairs, out)
    assert report.existing_row_count == 0
    assert report.new_row_count == 1
    rows = read_existing_csv(out)
    assert len(rows) == 2  # header + 1 new row


def test_emit_utf8_for_non_latin(tmp_path: Path):
    existing = tmp_path / "ko.csv"
    existing.write_text(
        "id;language_from;language_to;word_from;word_to;type\n", encoding="utf-8"
    )
    out = tmp_path / "ko.merged.csv"
    pairs = [SummaryPair(word_from="Hello", word_to="안녕하세요")]
    emit_consolidated_csv("ko", existing, pairs, out)
    content = out.read_text(encoding="utf-8")
    assert "안녕하세요" in content


def test_pair_from_paragraphs_zips_aligned():
    en = ["Hello.", "World."]
    tr = ["Hallo.", "Welt."]
    pairs = pair_from_paragraphs(en, tr)
    assert len(pairs) == 2
    assert pairs[0].word_from == "Hello."
    assert pairs[0].word_to == "Hallo."


def test_pair_from_paragraphs_length_mismatch_raises():
    with pytest.raises(ValueError):
        pair_from_paragraphs(["a", "b"], ["x"])
