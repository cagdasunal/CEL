"""Tests for translator.weglot — the reusable Weglot-CSV emitter (tracker-094).

Key invariant: a translator run MERGES new translation rows into a CSV that
already holds Fidelo translations — Fidelo rows are preserved, dedup works.
"""
import csv
from pathlib import Path

from tools.translator import Translation, TranslationUnit  # noqa: F401 (Translation used)
from tools.translator.weglot import (
    WeglotPair,
    emit_consolidated_csv,
    pairs_from_translations,
    read_existing_csv,
)

# A pre-existing Weglot CSV as written by the Fidelo exporter (tools/weglot/csv_export.py).
_FIDELO_CSV = (
    "id;language_from;language_to;word_from;word_to;type\n"
    ';en;de;"1 teacher per student";"1 Lehrer pro Schüler";Text\n'
    ';en;de;"10 min. walk to CEL";"10 Minuten zu Fuss zu CEL";Text\n'
)


def test_pairs_from_translations_maps_and_skips_empty():
    trs = [
        Translation(id="a", source="Welcome", target="Willkommen", target_locale="de"),
        Translation(id="b", source="Empty", target="   ", target_locale="de"),  # skipped
    ]
    pairs = pairs_from_translations(trs)
    assert len(pairs) == 1
    assert pairs[0].word_from == "Welcome" and pairs[0].word_to == "Willkommen"
    assert pairs[0].type_ == "Text"


def test_pairs_from_translations_custom_type():
    trs = [Translation(id="t", source="Home", target="Startseite", target_locale="de")]
    pairs = pairs_from_translations(trs, type_="meta_title")
    assert pairs[0].type_ == "meta_title"


def test_emit_consolidates_with_fidelo_rows(tmp_path: Path):
    """Translator rows are appended to a Fidelo CSV without clobbering Fidelo content."""
    csv_path = tmp_path / "de.csv"
    csv_path.write_text(_FIDELO_CSV, encoding="utf-8")

    new_pairs = [
        WeglotPair(word_from="Learn English in the USA", word_to="Englisch lernen in den USA"),
        WeglotPair(word_from="Our courses", word_to="Unsere Kurse", type_="meta_title"),
    ]
    report = emit_consolidated_csv(
        target_locale="de", existing_csv_path=csv_path,
        summary_pairs=new_pairs, out_path=csv_path,
    )
    assert report.existing_row_count == 2  # both Fidelo rows preserved
    assert report.new_row_count == 2

    rows = read_existing_csv(csv_path)
    body = rows[1:]  # drop header
    froms = {r[3] for r in body}
    # Fidelo rows survive AND new translator rows are present.
    assert "1 teacher per student" in froms
    assert "10 min. walk to CEL" in froms
    assert "Learn English in the USA" in froms
    assert "Our courses" in froms
    # The meta_title type is carried through.
    assert any(r[3] == "Our courses" and r[5] == "meta_title" for r in body)


def test_emit_dedups_on_word_from_and_locale(tmp_path: Path):
    """A new pair whose source already exists (e.g. a Fidelo row) is skipped, not duplicated."""
    csv_path = tmp_path / "de.csv"
    csv_path.write_text(_FIDELO_CSV, encoding="utf-8")
    # "1 teacher per student" already exists from Fidelo → must dedup.
    dup = [WeglotPair(word_from="1 teacher per student", word_to="(retranslated)")]
    report = emit_consolidated_csv(
        target_locale="de", existing_csv_path=csv_path,
        summary_pairs=dup, out_path=csv_path,
    )
    assert report.new_row_count == 0
    assert report.duplicates_skipped >= 1
    # Original Fidelo translation is preserved (not overwritten).
    rows = read_existing_csv(csv_path)
    assert any(r[3] == "1 teacher per student" and r[4] == "1 Lehrer pro Schüler" for r in rows[1:])


def test_emit_brand_new_file_writes_header(tmp_path: Path):
    csv_path = tmp_path / "fr.csv"  # does not exist
    report = emit_consolidated_csv(
        target_locale="fr", existing_csv_path=csv_path,
        summary_pairs=[WeglotPair(word_from="Hello", word_to="Bonjour")],
        out_path=csv_path,
    )
    assert csv_path.exists()
    assert report.new_row_count == 1
    text = csv_path.read_text(encoding="utf-8")
    assert text.startswith("id;language_from;language_to;word_from;word_to;type")
    assert "Bonjour" in text


def test_emit_byte_identical_to_fidelo_exporter(tmp_path: Path):
    """tracker-095 I1: output must match the Fidelo exporter
    (tools/weglot/csv_export.py) byte-for-byte so rows interleave in one file —
    header + id/lang/type bare, word_from/word_to ALWAYS double-quoted."""
    csv_path = tmp_path / "de.csv"
    emit_consolidated_csv(
        target_locale="de", existing_csv_path=csv_path,
        summary_pairs=[WeglotPair(word_from="Learn English", word_to="Englisch lernen")],
        out_path=csv_path,
    )
    assert csv_path.read_text(encoding="utf-8") == (
        "id;language_from;language_to;word_from;word_to;type\n"
        ';en;de;"Learn English";"Englisch lernen";Text\n'
    )


def test_emit_escapes_internal_quotes_like_fidelo(tmp_path: Path):
    """Internal double-quotes are escaped as "" (Fidelo _weglot_quote parity)."""
    csv_path = tmp_path / "de.csv"
    emit_consolidated_csv(
        target_locale="de", existing_csv_path=csv_path,
        summary_pairs=[WeglotPair(word_from='Say "hi"', word_to='Sag "hallo"')],
        out_path=csv_path,
    )
    line = csv_path.read_text(encoding="utf-8").splitlines()[1]
    assert line == ';en;de;"Say ""hi""";"Sag ""hallo""";Text'
    # And it round-trips back through the reader to the original text.
    rows = read_existing_csv(csv_path)
    assert rows[1][3] == 'Say "hi"' and rows[1][4] == 'Sag "hallo"'


def test_csv_emitter_reexports_still_work():
    """The summary-side csv_emitter must still expose the moved names (back-compat)."""
    from tools.summary.csv_emitter import (
        SummaryPair, emit_consolidated_csv as e, read_existing_csv as r,
        pair_from_paragraphs, split_summary_into_paragraphs,
    )
    # SummaryPair is the WeglotPair alias.
    p = SummaryPair(word_from="x", word_to="y")
    assert p.as_row("de") == ["", "en", "de", "x", "y", "Text"]
    assert split_summary_into_paragraphs("a\n\nb") == ["a", "b"]
