"""Tests for tools.summary.keyword_extractor — derivation per /page-summary Phase 2.5."""

from tools.summary.keyword_extractor import derive_keywords


def test_derives_primary_from_common_phrase_title_h1():
    plan = derive_keywords(
        title="Learn English in Vancouver | CEL",
        h1="Learn English in Vancouver",
        url="https://www.englishcollege.com/vancouver/learn-english",
        body_text="Studying to learn English in Vancouver takes 6 to 12 months.",
    )
    assert "learn english" in plan.primary.lower()
    assert "vancouver" in plan.primary.lower()


def test_strips_brand_suffix():
    plan = derive_keywords(
        title="English Courses in USA & Canada | CEL",
        h1="English Courses",
        url="https://www.englishcollege.com/courses",
        body_text="",
    )
    assert "CEL" not in plan.primary
    assert "english courses" in plan.primary.lower()


def test_detects_entity_terms():
    plan = derive_keywords(
        title="IELTS Preparation Course",
        h1="IELTS Preparation",
        url="https://www.englishcollege.com/courses/ielts",
        body_text="Prepare for IELTS with our CEFR B2 program in San Diego.",
    )
    assert any("IELTS" == e for e in plan.entities)
    assert any("CEFR" == e for e in plan.entities)
    assert any("B2" == e for e in plan.entities)
    assert any("San Diego" == e for e in plan.entities)


def test_secondary_keywords_from_body_frequency():
    body = (
        "vancouver vancouver vancouver "
        "campus campus campus campus "
        "students students students "
        "the the the the the "  # stopword — should be excluded
    )
    plan = derive_keywords(
        title="Course",
        h1="Course",
        url="https://www.englishcollege.com/x",
        body_text=body,
    )
    # Body terms repeated ≥3 times, non-stopword:
    assert "vancouver" in plan.secondaries or "campus" in plan.secondaries or "students" in plan.secondaries
    # 'the' is a stopword — must NOT appear:
    assert "the" not in plan.secondaries


def test_fallback_to_h1_when_no_common_phrase():
    plan = derive_keywords(
        title="One thing",
        h1="Completely different",
        url="https://www.englishcollege.com/x",
        body_text="",
    )
    # No 2+ token overlap → fallback to H1 (or A, or C).
    assert plan.primary in {"completely different", "one thing"}


def test_slug_with_locale_prefix_stripped():
    plan = derive_keywords(
        title="Englischkurse",
        h1="Englischkurse",
        url="https://www.englishcollege.com/de/kurse",
        body_text="",
    )
    # URL slug rendered should strip /de/ prefix.
    assert "de" not in plan.primary.split()
