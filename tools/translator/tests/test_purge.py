"""Tests for the audit-108 M-1/M-2 stale-row purge + CSV write helpers (tools.translator.weglot).

REVIEW HOTSPOT: the discriminator must drop ONLY unambiguous stale summary chunks
(ATX-heading-leading or containing a `[text](url)` link) and NEVER a Fidelo/meta row.
"""
from pathlib import Path

from tools.translator import weglot


# ---- is_stale_summary_word_from: the discriminator ----

def test_stale_detects_atx_heading_and_markdown_link():
    assert weglot.is_stale_summary_word_from("## North American Immersion")
    assert weglot.is_stale_summary_word_from("#### How do campus locations differ?")
    assert weglot.is_stale_summary_word_from("Study at our [Vancouver campus](https://x/de/vancouver) today")


def test_stale_does_NOT_match_fidelo_or_clean_rows():
    # Clean rendered block (what summary_page_blocks emits) — must survive.
    assert not weglot.is_stale_summary_word_from("Study English by the Pacific for 12 weeks.")
    # Fidelo-style strings with brackets/parens/URLs that are NOT markdown links — must survive.
    assert not weglot.is_stale_summary_word_from("Apply for your visa (ESTA) before you travel")
    assert not weglot.is_stale_summary_word_from("rate is $300 (per week)")
    assert not weglot.is_stale_summary_word_from("See https://www.englishcollege.com/courses for details")
    assert not weglot.is_stale_summary_word_from("Choose [a] option")          # brackets, no (url)
    assert not weglot.is_stale_summary_word_from("Small classes & a café — 1:1")
    assert not weglot.is_stale_summary_word_from("C# and other courses")        # '#' not heading (no leading ## + space)


def test_filter_keeps_header_fidelo_meta_clean_drops_only_stale():
    rows = [
        ["id", "language_from", "language_to", "word_from", "word_to", "type"],   # header
        ["", "en", "de", "1 teacher per student", "1 Lehrer pro Schüler", "Text"],  # Fidelo
        ["", "en", "de", "Learn English at CEL", "Englisch lernen bei CEL", "meta_title"],  # meta
        ["", "en", "de", "Study by the Pacific for 12 weeks.", "...", "Text"],     # clean block
        ["", "en", "de", "## North American Immersion", "...", "Text"],            # STALE heading
        ["", "en", "de", "See our [courses](https://x/courses) page", "...", "Text"],  # STALE link
    ]
    kept, dropped = weglot.filter_out_stale_summary_rows(rows)
    assert len(dropped) == 2
    assert {r[3] for r in dropped} == {"## North American Immersion", "See our [courses](https://x/courses) page"}
    assert any(r[0] == "id" for r in kept)  # header row kept
    kept_wf = {r[3] for r in kept}
    assert "1 teacher per student" in kept_wf  # Fidelo kept
    assert "Learn English at CEL" in kept_wf   # meta kept
    assert "Study by the Pacific for 12 weeks." in kept_wf  # clean kept


def test_filter_idempotent():
    rows = [
        ["id", "language_from", "language_to", "word_from", "word_to", "type"],
        ["", "en", "de", "## Stale", "x", "Text"],
        ["", "en", "de", "Clean block.", "x", "Text"],
    ]
    kept1, _ = weglot.filter_out_stale_summary_rows(rows)
    kept2, dropped2 = weglot.filter_out_stale_summary_rows(kept1)
    assert dropped2 == []  # nothing left to drop
    assert kept1 == kept2


def test_format_csv_text_roundtrip_and_no_bom(tmp_path: Path):
    rows = [
        ["id", "language_from", "language_to", "word_from", "word_to", "type"],
        ["", "en", "de", "Quote \"inside\" text", "Anführung", "Text"],
        ["", "en", "ja", "日本語のテキスト", "x", "Text"],          # non-ASCII
        ["", "en", "ar", "مرحبا & welcome", "x", "Text"],
    ]
    text = weglot.format_csv_text(rows)
    # No UTF-8 BOM (Weglot wants plain UTF-8).
    assert not text.encode("utf-8").startswith(b"\xef\xbb\xbf")
    # word_from/word_to quoted; header bare.
    assert text.split("\n")[0] == "id;language_from;language_to;word_from;word_to;type"
    p = tmp_path / "de.csv"
    weglot.atomic_write_text(p, text)
    back = weglot.read_existing_csv(p)
    assert back == [list(r) for r in rows]  # exact round-trip incl. non-ASCII + embedded quote
