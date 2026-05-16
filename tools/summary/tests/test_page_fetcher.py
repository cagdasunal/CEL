"""Tests for tools.summary.page_fetcher — HTML parsing (no live network calls)."""

from tools.summary.page_fetcher import _parse_html


_SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>English Courses in San Diego &amp; Vancouver | CEL</title>
  <link rel="canonical" href="https://www.englishcollege.com/courses">
  <link rel="alternate" hreflang="de" href="https://www.englishcollege.com/de/kurse">
  <link rel="alternate" hreflang="fr" href="https://www.englishcollege.com/fr/cours">
</head>
<body>
  <h1>English Language Courses</h1>
  <h2>Course types</h2>
  <p>CEL offers English courses in San Diego, Los Angeles, and Vancouver.</p>
  <div id="summary"><h2>How do you pick a course?</h2><p>Pick by level + location.</p></div>
  <script>console.log("ignored")</script>
  <style>body { color: red; }</style>
</body>
</html>
"""


def test_parser_extracts_title():
    pc = _parse_html("https://example.com/courses", "https://example.com/courses", 200, _SAMPLE_HTML)
    assert "English Courses in San Diego" in pc.title
    assert "CEL" in pc.title  # full title before brand strip


def test_parser_extracts_h1_and_headings():
    pc = _parse_html("https://example.com", "https://example.com", 200, _SAMPLE_HTML)
    assert pc.h1 == "English Language Courses"
    assert "Course types" in pc.headings


def test_parser_extracts_canonical():
    pc = _parse_html("https://example.com", "https://example.com", 200, _SAMPLE_HTML)
    assert pc.canonical == "https://www.englishcollege.com/courses"


def test_parser_extracts_hreflang_urls():
    pc = _parse_html("https://example.com", "https://example.com", 200, _SAMPLE_HTML)
    assert "https://www.englishcollege.com/de/kurse" in pc.hreflang_urls
    assert "https://www.englishcollege.com/fr/cours" in pc.hreflang_urls


def test_parser_extracts_summary_element():
    pc = _parse_html("https://example.com", "https://example.com", 200, _SAMPLE_HTML)
    assert "How do you pick a course?" in pc.existing_summary_html
    assert "Pick by level + location." in pc.existing_summary_html


def test_parser_strips_scripts_and_styles_from_body_excerpt():
    pc = _parse_html("https://example.com", "https://example.com", 200, _SAMPLE_HTML)
    assert "console.log" not in pc.body_text_excerpt
    assert "color: red" not in pc.body_text_excerpt
    assert "English courses in San Diego" in pc.body_text_excerpt


def test_body_excerpt_capped_at_8000_chars():
    big_body = "<html><body>" + ("word " * 5000) + "</body></html>"
    pc = _parse_html("https://example.com", "https://example.com", 200, big_body)
    assert len(pc.body_text_excerpt) <= 8000


def test_parser_handles_missing_summary_element():
    html_no_summary = "<html><head><title>X</title></head><body><h1>Y</h1></body></html>"
    pc = _parse_html("https://example.com", "https://example.com", 200, html_no_summary)
    assert pc.existing_summary_html == ""
