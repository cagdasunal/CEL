"""Tests for translation QA checks."""
from tools.translator.qa import check_translation


def test_clean_translation_passes():
    ok, flags = check_translation("Welcome to CEL", "Willkommen bei CEL", "de")
    assert ok
    assert flags == []


def test_empty_translation_blocks():
    ok, flags = check_translation("Welcome", "   ", "de")
    assert not ok
    assert "empty_translation" in flags


def test_number_drift_blocks():
    ok, flags = check_translation("B2 in 12 weeks", "B2 in zwölf Wochen", "de")
    # "12" missing from target (spelled out) → blocking number_drift.
    assert not ok
    assert any(f.startswith("number_drift") for f in flags)


def test_number_preserved_passes():
    ok, flags = check_translation("12 weeks", "12 Wochen", "de")
    assert ok
    assert not any(f.startswith("number_drift") for f in flags)


def test_url_drift_blocks():
    ok, flags = check_translation(
        "See https://www.englishcollege.com/courses",
        "Siehe unsere Kursseite",
        "de",
    )
    assert not ok
    assert any(f.startswith("url_drift") for f in flags)


def test_placeholder_mismatch_blocks():
    ok, flags = check_translation("Hello {name}", "Hallo", "de")
    assert not ok
    assert any(f.startswith("placeholder_mismatch") for f in flags)


def test_untranslated_passthrough_warns_not_blocks():
    ok, flags = check_translation("Vancouver", "Vancouver", "de")
    # Passthrough is a warning (some strings legitimately don't translate), not a block.
    assert ok
    assert "untranslated_passthrough" in flags


def test_length_ratio_warns():
    ok, flags = check_translation("Hi", "X" * 50, "de")
    assert any(f.startswith("length_ratio") for f in flags)


def test_url_check_skipped_when_disabled():
    # tracker-095 H2: the summary path swaps/removes links per locale, so the
    # source URL is intentionally absent — url preservation must be skippable.
    ok, flags = check_translation(
        "See https://www.englishcollege.com/courses",
        "Siehe unsere Kursseite",
        "de",
        check_urls=False,
    )
    assert ok
    assert not any(f.startswith("url_drift") for f in flags)


def test_arabic_indic_numerals_not_number_drift():
    # tracker-095 M3: a model that localizes digits for `ar` (١٢ = 12) must not
    # trip number_drift — digits are Unicode→ASCII folded before comparison.
    ok, flags = check_translation("12 weeks", "١٢ أسبوعًا", "ar")
    assert not any(f.startswith("number_drift") for f in flags)
    assert ok
