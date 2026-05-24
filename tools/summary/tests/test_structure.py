"""Tests for tools.summary.structure — 4-part parse + Markdown→HTML (tracker-096/098)."""

import re

from tools.summary.structure import (
    FourPartSummary,
    four_part_content_html,
    four_part_paragraph_html,
    parse_four_part,
    parts_to_markdown,
    summary_html_to_markdown,
    summary_markdown_to_html,
    summary_page_blocks,
)


def test_summary_html_to_markdown_roundtrip():
    """md → html → md preserves headings, prose, and inline links (2026-05-23) so the
    link-insertion pass can recover a CMS-only summary as a faithful Markdown base."""
    md = (
        "## How long to learn English in Vancouver\n\n"
        "Most students reach B2 in 12 weeks at our "
        "[Vancouver campus](https://www.englishcollege.com/vancouver) with small classes.\n\n"
        "### What level do I need\n\n"
        "All levels from A1 to C2, with placement on day one."
    )
    back = summary_html_to_markdown(summary_markdown_to_html(md))
    assert "## How long to learn English in Vancouver" in back
    assert "### What level do I need" in back
    assert "[Vancouver campus](https://www.englishcollege.com/vancouver)" in back
    assert "Most students reach B2 in 12 weeks" in re.sub(r"\s+", " ", back)
    assert "All levels from A1 to C2" in re.sub(r"\s+", " ", back)


def test_summary_html_to_markdown_empty():
    assert summary_html_to_markdown("") == ""

_FOUR_PART = """## English School Life

### What to expect from an english language school

Twelve weeks is the typical timeline at an english language school like CEL, where most students reach B2.

#### How long does it take to reach B2

Most students reach B2 within twelve weeks. See [our Vancouver campus](https://www.englishcollege.com/vancouver) for details.

##### Beginners

Absolute beginners need 24 to 36 weeks depending on weekly hours.
"""


def test_parse_extracts_four_parts():
    p = parse_four_part(_FOUR_PART)
    assert p.tagline == "English School Life"
    assert p.title == "What to expect from an english language school"
    assert p.paragraph.startswith("Twelve weeks is the typical timeline")
    assert "B2" in p.paragraph
    # Content begins at the first H4 and includes the H5 + its prose.
    assert p.content_md.startswith("#### How long does it take to reach B2")
    assert "##### Beginners" in p.content_md


def test_parse_keeps_links_only_in_content():
    p = parse_four_part(_FOUR_PART)
    assert "](https://www.englishcollege.com/vancouver)" not in p.tagline
    assert "](https://www.englishcollege.com/vancouver)" not in p.title
    assert "](https://www.englishcollege.com/vancouver)" not in p.paragraph
    assert "/vancouver" in p.content_md  # the link lives in Content


def test_summary_page_blocks_matches_rendered_text_nodes():
    """tracker-107: word_from must equal the page's rendered text nodes — one plain-text
    block per <h2>/<h3>/<h4>/<h5>/<p>, links collapsed to anchor text, no markdown."""
    blocks = summary_page_blocks(_FOUR_PART)
    assert blocks == [
        "English School Life",
        "What to expect from an english language school",
        "Twelve weeks is the typical timeline at an english language school like CEL, where most students reach B2.",
        "How long does it take to reach B2",
        "Most students reach B2 within twelve weeks. See our Vancouver campus for details.",
        "Beginners",
        "Absolute beginners need 24 to 36 weeks depending on weekly hours.",
    ]
    # No markdown markers / URLs leak into a Weglot source string.
    assert not any("#" in b or "[" in b or "http" in b for b in blocks)


def test_summary_page_blocks_tagline_title_first_and_empty_safe():
    assert summary_page_blocks("")[:] == []
    # Tagline+title lead; a content-only doc still yields its blocks.
    blocks = summary_page_blocks("## Tag\n\n### Title\n\nLead paragraph here.")
    assert blocks[0] == "Tag" and blocks[1] == "Title"
    assert blocks[2] == "Lead paragraph here."


def test_parse_tolerates_missing_parts():
    p = parse_four_part("## Just a tagline\n\nStray text with no title or content.")
    assert p.tagline == "Just a tagline"
    assert p.title == ""
    assert p.content_md == ""
    # Paragraph is only collected after a Title, so a draft without H3 has none.
    assert p.paragraph == ""


def test_parse_strips_inline_markdown_in_plain_parts():
    md = "## **Bold** Tagline\n\n### Title with [a link](https://x.com)\n\ntext\n\n#### H4\n\nbody"
    p = parse_four_part(md)
    assert p.tagline == "Bold Tagline"
    assert p.title == "Title with a link"  # link collapses to anchor text


def test_content_html_renders_subset():
    html = four_part_content_html(
        "#### How long\n\nMost reach B2 in [twelve weeks](https://www.englishcollege.com/courses). "
        "It is **fast**.\n\n##### Beginners\n\nThey need *longer*."
    )
    assert "<h4>How long</h4>" in html
    assert "<h5>Beginners</h5>" in html
    assert '<a href="https://www.englishcollege.com/courses">twelve weeks</a>' in html
    assert "<strong>fast</strong>" in html
    assert "<em>longer</em>" in html
    assert html.count("<p>") == 2


def test_content_html_escapes_stray_markup():
    html = four_part_content_html("#### A & B < C\n\nText with <unsafe> & ampersand.")
    assert "<h4>A &amp; B &lt; C</h4>" in html
    assert "&lt;unsafe&gt; &amp; ampersand" in html


def test_content_html_handles_heading_without_blank_line():
    html = four_part_content_html("#### Heading\nProse on the next line.")
    assert "<h4>Heading</h4>" in html
    assert "<p>Prose on the next line.</p>" in html


def test_content_html_empty():
    assert four_part_content_html("") == ""
    assert four_part_content_html("   \n  ") == ""


def test_four_part_summary_defaults():
    p = FourPartSummary()
    assert p.tagline == "" and p.title == "" and p.paragraph == "" and p.content_md == ""


# ---- tracker-096 review: parts_to_markdown (audit reconstruction from live HTML) ----


def test_parts_to_markdown_reconstructs_and_round_trips():
    parts = {
        "summary-tagline": "<h2>English School Life</h2>",
        "summary-title": "<h3>What to expect</h3>",
        "summary-paragraph": "<p>Twelve weeks to B2.</p>",
        "summary-content": "<h4>How long</h4><p>Twelve weeks.</p><h5>Beginners</h5><p>Longer.</p>",
    }
    md = parts_to_markdown(parts)
    assert md.startswith("## English School Life")
    assert "### What to expect" in md
    assert "Twelve weeks to B2." in md
    assert "#### How long" in md
    assert "##### Beginners" in md
    # Round-trips back through the parser.
    p = parse_four_part(md)
    assert p.tagline == "English School Life"
    assert p.title == "What to expect"
    assert p.content_md.startswith("#### How long")


def test_parts_to_markdown_empty():
    assert parts_to_markdown({}) == ""
    assert parts_to_markdown({"summary-tagline": ""}) == ""


# ---- tracker-098: RichText Paragraphs (markdown source) + render helpers ----

_TWO_PARA = """## Coastal Study Life

### How long does it take to learn English in San Diego

Most students reach B2 in 12 weeks at [CEL San Diego](https://www.englishcollege.com/san-diego-ca/language-school), where classes average 7 students.

Beginners typically need 24 to 36 weeks depending on weekly hours and study intensity.

#### Who is this course for

University-bound students. See [our courses](https://www.englishcollege.com/courses).
"""


def test_parse_captures_two_paragraphs_as_markdown_with_links():
    """tracker-098: the Paragraphs part keeps Markdown (blank-line-separated paragraphs
    + inline links), no longer stripped to plain text."""
    p = parse_four_part(_TWO_PARA)
    # Blank-line separation between the two paragraphs is preserved.
    assert "\n\n" in p.paragraph
    paras = [blk for blk in p.paragraph.split("\n\n") if blk.strip()]
    assert len(paras) == 2
    # The inline link Markdown survives in the paragraph source.
    assert "[CEL San Diego](https://www.englishcollege.com/san-diego-ca/language-school)" in p.paragraph
    assert paras[1].startswith("Beginners typically need")


def test_four_part_paragraph_html_renders_two_paragraphs_and_links():
    p = parse_four_part(_TWO_PARA)
    html = four_part_paragraph_html(p.paragraph)
    assert html.count("<p>") == 2
    assert '<a href="https://www.englishcollege.com/san-diego-ca/language-school">CEL San Diego</a>' in html
    # No heading tags leak from the Paragraphs render.
    assert "<h" not in html


def test_four_part_paragraph_html_emphasis_and_escape():
    html = four_part_paragraph_html("It is **fast** & cheap.\n\nLevels A1 < C2 apply.")
    assert "<strong>fast</strong>" in html
    assert "&amp;" in html and "&lt;" in html
    assert html.count("<p>") == 2


def test_four_part_paragraph_html_empty():
    assert four_part_paragraph_html("") == ""
    assert four_part_paragraph_html("   \n  ") == ""


def test_summary_markdown_to_html_renders_blog_single_block():
    md = (
        "## How long does it take to learn English?\n\n"
        "Most reach B2 in [12 weeks](https://www.englishcollege.com/courses). It is **fast**.\n\n"
        "### What level do I need\n\n"
        "All levels from A1 to C2, with *placement* on day one.\n\n"
        "#### A deeper note\n\nExtra detail."
    )
    html = summary_markdown_to_html(md)
    assert "<h2>How long does it take to learn English?</h2>" in html
    assert "<h3>What level do I need</h3>" in html
    assert "<h4>A deeper note</h4>" in html
    assert '<a href="https://www.englishcollege.com/courses">12 weeks</a>' in html
    assert "<strong>fast</strong>" in html
    assert "<em>placement</em>" in html
    # No literal Markdown markers leak through.
    assert "## " not in html and "](http" not in html


def test_summary_markdown_to_html_empty():
    assert summary_markdown_to_html("") == ""
    assert summary_markdown_to_html("  \n  ") == ""
