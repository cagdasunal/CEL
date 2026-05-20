"""Tests for tools.summary.structure — 4-part parse + Markdown→HTML (tracker-096)."""

from tools.summary.structure import (
    FourPartSummary,
    four_part_content_html,
    parse_four_part,
    parts_to_markdown,
)

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
