"""Tests for tools.summary.url_map — hreflang-derived EN↔locale URL map (tracker-106)."""
import json

from tools.summary import url_map


def test_is_en_page_includes_blog_excludes_locale_and_sitemap():
    assert url_map.is_en_page("https://www.englishcollege.com/courses")
    # Blog posts ARE included — they're link targets in translated summaries.
    assert url_map.is_en_page("https://www.englishcollege.com/post/some-post")
    assert not url_map.is_en_page("https://www.englishcollege.com/de/kurse")   # locale = a target
    assert not url_map.is_en_page("https://www.englishcollege.com/sitemap.xml")
    assert not url_map.is_en_page("https://other.com/x")


def test_extract_hreflang_robust_to_attr_order_and_normalizes():
    html = (
        '<link rel="alternate" hreflang="en" href="https://www.englishcollege.com/pathway-program-usa">'
        '<link href="https://www.englishcollege.com/de/auslandsstudium-usa/" hreflang="de" rel="alternate">'
        '<link hreflang="fr" rel="alternate" href="https://www.englishcollege.com/fr/programme-x">'
        '<link rel="stylesheet" href="/x.css">'
    )
    alts = url_map.extract_hreflang(html)
    assert alts["de"] == "https://www.englishcollege.com/de/auslandsstudium-usa"  # trailing slash stripped
    assert alts["fr"] == "https://www.englishcollege.com/fr/programme-x"
    assert alts["en"] == "https://www.englishcollege.com/pathway-program-usa"


def test_extract_hreflang_ignores_non_alternate_links():
    # Blog posts carry hreflang only in JS/switcher markup, NOT <link rel=alternate>.
    assert url_map.extract_hreflang('<a href="/de/post/x" hreflang="de">switch</a>') == {}
    assert url_map.extract_hreflang('<link rel="canonical" href="/x" hreflang="de">') == {}


def test_build_url_map_with_injected_fetch():
    pages = {
        "https://www.englishcollege.com/pathway-program-usa":
            '<link rel="alternate" hreflang="de" href="https://www.englishcollege.com/de/auslandsstudium-usa">'
            '<link rel="alternate" hreflang="fr" href="https://www.englishcollege.com/fr/programme-x">',
        "https://www.englishcollege.com/no-alts": "<html>nothing</html>",
        "https://www.englishcollege.com/fetch-fails": None,
    }
    m, skipped = url_map.build_url_map(pages.keys(), fetch=lambda u: pages[u], locales=("de", "fr"))
    assert m["https://www.englishcollege.com/pathway-program-usa"] == {
        "de": "https://www.englishcollege.com/de/auslandsstudium-usa",
        "fr": "https://www.englishcollege.com/fr/programme-x",
    }
    assert "https://www.englishcollege.com/no-alts" in skipped       # no usable alternate
    assert "https://www.englishcollege.com/fetch-fails" in skipped   # fetch returned None


def test_en_pages_from_sources_unions_and_filters():
    llms = ("- [x](https://www.englishcollege.com/courses)\n"
            "- [y](https://www.englishcollege.com/de/kurse)\n"
            "- [z](https://www.englishcollege.com/post/p1)")
    sm = "<loc>https://www.englishcollege.com/housing</loc><loc>https://www.englishcollege.com/fr/x</loc>"
    en = url_map.en_pages_from_sources(llms, sm)
    assert "https://www.englishcollege.com/courses" in en
    assert "https://www.englishcollege.com/housing" in en       # from sitemap
    assert "https://www.englishcollege.com/post/p1" in en       # blog included as a target
    assert "https://www.englishcollege.com/de/kurse" not in en  # locale page excluded
    assert "https://www.englishcollege.com/fr/x" not in en


def test_load_url_map_handles_wrapped_bare_and_missing(tmp_path):
    wrapped = tmp_path / "w.json"
    wrapped.write_text(json.dumps({"generated_at": "t", "map": {"a": {"de": "b"}}}), encoding="utf-8")
    assert url_map.load_url_map(wrapped) == {"a": {"de": "b"}}
    bare = tmp_path / "b.json"
    bare.write_text(json.dumps({"a": {"de": "b"}}), encoding="utf-8")
    assert url_map.load_url_map(bare) == {"a": {"de": "b"}}
    assert url_map.load_url_map(tmp_path / "missing.json") == {}
