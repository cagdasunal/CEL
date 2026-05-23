"""Tests for tools.summary.llms_parser — section parsing, locale detection, equivalence lookup."""
from pathlib import Path

from tools.summary.llms_parser import LlmsIndex, parse_llms_txt

_FIXTURE = Path(__file__).parent / "fixtures" / "sample_llms.txt"


def _load_index() -> LlmsIndex:
    return parse_llms_txt(_FIXTURE.read_text(encoding="utf-8"))


def test_parser_loads_all_locales():
    idx = _load_index()
    by_locale = idx.urls_by_locale()
    assert "en" in by_locale
    assert "de" in by_locale
    assert "fr" in by_locale
    assert "es" in by_locale
    assert "it" in by_locale
    assert "pt" in by_locale
    assert "ko" in by_locale
    assert "ja" in by_locale
    assert "ar" in by_locale


def test_parser_extracts_section_and_description():
    idx = _load_index()
    entry = idx.get_entry("https://www.englishcollege.com/courses")
    assert entry is not None
    assert entry.section == "Courses"
    assert "Study English with CEL" in entry.description
    assert entry.locale == "en"


def test_find_equivalent_en_to_de():
    idx = _load_index()
    # /courses → /de/kurse — DIFFERENT slug, so find_equivalent must return None
    # (not /de/courses because that doesn't exist).
    eq = idx.find_equivalent("https://www.englishcollege.com/courses", "de")
    # Strict slug-substitution lookup: /courses → /de/courses → not in index → None
    assert eq is None


def test_find_equivalent_returns_none_when_missing():
    idx = _load_index()
    # FR-only post has no EN equivalent (original-per-locale).
    eq = idx.find_equivalent(
        "https://www.englishcollege.com/fr/post/cours-anglais-vancouver", "en"
    )
    assert eq is None


def test_find_equivalent_self_locale_returns_self():
    idx = _load_index()
    src = "https://www.englishcollege.com/de/kurse"
    eq = idx.find_equivalent(src, "de")
    assert eq == src


def test_urls_in_locale_excluding_filters_housing_slugs():
    idx = _load_index()
    en_urls = idx.urls_in_locale_excluding("en", ("vc", "sd", "sm"))
    # /vc/, /sd/, /sm/ must NOT be in the result.
    for url in en_urls:
        assert "/vc/" not in url
        assert "/sd/" not in url
        assert "/sm/" not in url
    # /courses must still be present (it's not in an excluded segment).
    assert "https://www.englishcollege.com/courses" in en_urls


def test_locale_detection_uses_first_path_segment_only():
    idx = _load_index()
    # /de/kurse → de
    entry = idx.get_entry("https://www.englishcollege.com/de/kurse")
    assert entry is not None
    assert entry.locale == "de"


def test_urls_by_section_groups_correctly():
    idx = _load_index()
    sections = idx.urls_by_section()
    assert "Courses" in sections
    assert "Housing" in sections
    assert len(sections["Courses"]) >= 1


def test_blog_section_extraction():
    idx = _load_index()
    blog = [e for e in idx.entries if e.section == "Blog"]
    assert any(e.locale == "en" for e in blog)
    assert any(e.locale == "de" for e in blog)
    assert any(e.locale == "fr" for e in blog)


def test_find_equivalent_or_fallback():
    """T2 (2026-05-23): exact same-locale equivalent → nearest in-index same-locale
    ancestor → locale root → None. Every result is target-locale-prefixed + in-index, so
    a fallback can never leak cross-locale."""
    from tools.summary.llms_parser import LlmsEntry

    idx = LlmsIndex(entries=[
        LlmsEntry(url="https://www.englishcollege.com/de/kurse", title="", description="", section="", locale="de"),
        LlmsEntry(url="https://www.englishcollege.com/de/", title="", description="", section="", locale="de"),
    ])
    # Exact swap: /kurse → /de/kurse.
    assert idx.find_equivalent_or_fallback(
        "https://www.englishcollege.com/kurse", "de"
    ) == "https://www.englishcollege.com/de/kurse"
    # Missing slug → falls back to the de hub (the only in-index ancestor).
    assert idx.find_equivalent_or_fallback(
        "https://www.englishcollege.com/post/missing-slug", "de"
    ) == "https://www.englishcollege.com/de/"
    # A locale with nothing in the index → None (never a cross-locale leak).
    assert idx.find_equivalent_or_fallback(
        "https://www.englishcollege.com/post/x", "fr"
    ) is None
