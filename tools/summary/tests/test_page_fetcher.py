"""Tests for tools.summary.page_fetcher — HTML parsing (no live network calls)."""

import pytest

from tools.summary.page_fetcher import _parse_html, fetch_page


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
    assert pc.existing_summary_parts == {}


# ---- tracker-096: 4-part Summary element extraction ----

_FOUR_PART_HTML = """<html><body>
<h1>Vancouver</h1>
<h2 id="summary-tagline">English School Life</h2>
<h3 id="summary-title">What to expect</h3>
<p id="summary-paragraph">Twelve weeks to a strong B2.</p>
<div id="summary-content"><h4>How long</h4><p>Twelve weeks at CEL.</p></div>
</body></html>"""


def test_parser_extracts_four_part_elements():
    pc = _parse_html("https://x.com/vancouver", "https://x.com/vancouver", 200, _FOUR_PART_HTML)
    parts = pc.existing_summary_parts
    assert set(parts.keys()) == {
        "summary-tagline", "summary-title", "summary-paragraph", "summary-content",
    }
    assert "English School Life" in parts["summary-tagline"]
    assert "What to expect" in parts["summary-title"]
    assert "Twelve weeks to a strong B2." in parts["summary-paragraph"]
    assert "How long" in parts["summary-content"]
    # No legacy single #summary element on a 4-part page.
    assert pc.existing_summary_html == ""


def test_parser_four_part_does_not_break_legacy_single_summary():
    """The legacy single id="summary" still populates existing_summary_html."""
    html = '<html><body><div id="summary"><h2>Q</h2><p>A</p></div></body></html>'
    pc = _parse_html("https://x.com", "https://x.com", 200, html)
    assert "Q" in pc.existing_summary_html and "A" in pc.existing_summary_html
    assert pc.existing_summary_parts == {}


# ---- URL-scheme validation (closes tracker-087 F-3 SSRF) ----


def test_fetch_page_rejects_file_scheme():
    """file:// URLs are rejected before urllib touches them."""
    with pytest.raises(ValueError, match="must be http or https"):
        fetch_page("file:///etc/passwd")


def test_fetch_page_rejects_ftp_scheme():
    with pytest.raises(ValueError, match="must be http or https"):
        fetch_page("ftp://example.com/test")


def test_fetch_page_rejects_gopher_scheme():
    with pytest.raises(ValueError, match="must be http or https"):
        fetch_page("gopher://example.com/")


def test_fetch_page_rejects_empty_scheme():
    """Bare paths or schemeless URLs are rejected."""
    with pytest.raises(ValueError, match="must be http or https"):
        fetch_page("/etc/passwd")


def test_fetch_page_accepts_http_and_https_schemes_at_validation_layer():
    """The scheme check itself passes for http(s); we don't make a network call here.

    The test simply asserts ValueError is NOT raised on validation. The actual
    urlopen() that follows would do real I/O, so we expect a network-style error
    (URLError / connection refused / DNS) — NOT a ValueError.
    """
    import urllib.error
    for scheme in ("http", "https"):
        try:
            fetch_page(f"{scheme}://nonexistent-host-for-test.invalid/")
        except ValueError:
            pytest.fail(f"unexpected ValueError for valid scheme {scheme}")
        except (urllib.error.URLError, OSError):
            pass  # expected — network failure for a fake host
