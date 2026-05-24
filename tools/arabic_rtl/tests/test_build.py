"""Unit tests for the engine's pure helpers (no network)."""
from tools.arabic_rtl import build


def test_dedupe_collapses_exact_duplicates():
    css = ".a{margin-left:5px}.a{margin-left:5px}.b{left:0}"
    assert build.dedupe_rules(css) == ".a{margin-left:5px}.b{left:0}"


def test_dedupe_keeps_distinct_same_selector():
    css = ".a{margin-left:5px}.a{margin-left:8px}"
    assert build.dedupe_rules(css) == ".a{margin-left:5px}.a{margin-left:8px}"


def test_dedupe_preserves_import_statement():
    css = "@import url(x.css);.a{left:0}.a{left:0}"
    assert build.dedupe_rules(css) == "@import url(x.css);.a{left:0}"


def test_extract_css_urls_keeps_webflow_drops_vendor_and_nonstylesheet():
    html = (
        '<link href="https://cdn.prod.website-files.com/abc/css/site.min.css" rel="stylesheet">'
        '<link rel="stylesheet" href="https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.css">'
        '<link rel="icon" href="https://cdn.prod.website-files.com/abc/favicon.ico">'
    )
    assert build.extract_css_urls(html) == [
        "https://cdn.prod.website-files.com/abc/css/site.min.css"
    ]


def test_get_ar_urls_filters_locale_only():
    xml = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://www.englishcollege.com/vancouver</loc></url>'
        '<url><loc>https://www.englishcollege.com/ar/vancouver</loc></url>'
        '<url><loc>https://www.englishcollege.com/ar</loc></url>'
        '<url><loc>https://www.englishcollege.com/calendar</loc></url>'
        '</urlset>'
    )
    assert build.get_ar_urls(xml) == [
        "https://www.englishcollege.com/ar",
        "https://www.englishcollege.com/ar/vancouver",
    ]


def test_fingerprint_is_order_independent_and_content_sensitive():
    assert build.fingerprint(["b", "a"]) == build.fingerprint(["a", "b"])
    assert build.fingerprint(["a"]) != build.fingerprint(["a", "b"])
