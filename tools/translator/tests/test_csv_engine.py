"""Direct tests for the canonical Weglot CSV engine (tools.weglot.csv_engine).

The engine is also exercised through the re-exports in test_weglot.py / test_purge.py /
test_csv_emitter.py; this file pins its public API + byte-format independently.
"""
from pathlib import Path

from tools.weglot import csv_engine


def test_weglotpair_as_row():
    assert csv_engine.WeglotPair("Hello", "Hallo").as_row("de") == ["", "en", "de", "Hello", "Hallo", "Text"]


def test_weglot_quote_escapes_doublequotes_and_public_alias():
    assert csv_engine.weglot_quote('a "b" c') == '"a ""b"" c"'
    assert csv_engine._weglot_quote is csv_engine.weglot_quote  # _weglot_quote kept for importers


def test_format_csv_text_header_bare_values_quoted_lf_no_bom():
    rows = [list(csv_engine._CSV_COLUMNS), ["", "en", "de", "Word & more", "Wort", "Text"]]
    text = csv_engine.format_csv_text(rows)
    assert not text.encode("utf-8").startswith(b"\xef\xbb\xbf")  # no BOM
    assert text.split("\n")[0] == "id;language_from;language_to;word_from;word_to;type"
    assert text.split("\n")[1] == ';en;de;"Word & more";"Wort";Text'


def test_emit_roundtrip(tmp_path: Path):
    out = tmp_path / "de.csv"
    rep = csv_engine.emit_consolidated_csv("de", out, [csv_engine.WeglotPair("Hi", "Hallo")], out)
    assert rep.new_row_count == 1
    rows = csv_engine.read_existing_csv(out)
    assert rows[0] == list(csv_engine._CSV_COLUMNS)
    assert ["", "en", "de", "Hi", "Hallo", "Text"] in rows


def test_stale_discriminator():
    assert csv_engine.is_stale_summary_word_from("## Heading")
    assert not csv_engine.is_stale_summary_word_from("Plain (ESTA) text")


# tracker-114: source<->target mis-pairing guard.

def test_poison_pair_flags_short_source_long_target():
    assert csv_engine.is_poison_pair("and", "Welcher Standort bietet die richtige Sichtbarkeit?")
    assert csv_engine.is_poison_pair(".", "Überlegungen zur Unterkunft für ein langfristiges Studium")
    assert csv_engine.is_poison_pair("CEL", "unsere TOEFL-Prüfungsvorbereitung empfiehlt sich", "Text")


def test_poison_pair_exemptions():
    assert not csv_engine.is_poison_pair("Learn English", "Englisch lernen — eine lange Beschreibung hier", "meta_title")
    assert not csv_engine.is_poison_pair("USA", "Vereinigte Staaten von Amerika (Nordamerika)", "Text", {"USA"})
    assert not csv_engine.is_poison_pair("✓ Parking", "✓ Parkplatz buchbar gegen Aufpreis verfügbar")
    assert not csv_engine.is_poison_pair("Studio (max. 2)", "Studio (max. 2) mit eigener Küche und Bad")
    assert not csv_engine.is_poison_pair("and", "und")
    assert not csv_engine.is_poison_pair(
        "Welcome to CEL, your top choice for learning English here.",
        "Willkommen bei CEL, Ihrer ersten Wahl zum Englischlernen.",
    )


def test_detect_poison_rows_skips_header_and_meta():
    rows = [
        list(csv_engine._CSV_COLUMNS),
        ["", "en", "de", "and", "Welcher Standort bietet die richtige Sichtbarkeit?", "Text"],
        ["", "en", "de", "Amenities", "Ausstattung", "Text"],
        ["", "en", "de", "Title", "Ein langer Titel mit deutlich mehr als dreißig Zeichen", "meta_title"],
    ]
    hits = csv_engine.detect_poison_rows(rows)
    assert len(hits) == 1 and hits[0][3] == "and"


def test_emit_warns_on_poison(tmp_path: Path):
    out = tmp_path / "de.csv"
    rep = csv_engine.emit_consolidated_csv(
        "de", out,
        [csv_engine.WeglotPair("and", "Welcher Standort bietet die richtige Sichtbarkeit?")],
        out,
    )
    assert any("mis-pairing" in w for w in rep.warnings)


def test_emit_no_poison_warning_when_clean(tmp_path: Path):
    out = tmp_path / "de.csv"
    rep = csv_engine.emit_consolidated_csv(
        "de", out, [csv_engine.WeglotPair("Welcome to CEL and our schools here.", "Willkommen bei CEL.")], out,
    )
    assert not any("mis-pairing" in w for w in rep.warnings)
