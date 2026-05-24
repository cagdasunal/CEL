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
