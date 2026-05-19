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


# ---- B1: multi-locale stopwords + brand-suffix variants (tracker-087 F-6) ----


def test_derives_secondaries_from_german_body_filters_german_stopwords():
    """German bodies use German stopwords; common articles like 'der/die/das' are filtered."""
    body = (
        "Sprachkurs Sprachkurs Sprachkurs Sprachkurs "
        "Vancouver Vancouver Vancouver Vancouver "
        "Studenten Studenten Studenten "
        "der der der der der die die die die das das das das "  # German stopwords
    )
    plan = derive_keywords(
        title="Englischkurs",
        h1="Englischkurs",
        url="https://www.englishcollege.com/de/kurse",
        body_text=body,
        locale="de",
    )
    # German function words must NOT appear in secondaries.
    assert "der" not in plan.secondaries
    assert "die" not in plan.secondaries
    assert "das" not in plan.secondaries
    # German content words SHOULD appear.
    assert any(t in plan.secondaries for t in ("sprachkurs", "vancouver", "studenten"))


def test_derives_secondaries_from_korean_body_filters_korean_stopwords():
    """Korean bodies use Korean stopwords; particles like 은/는/이/가 are filtered."""
    body = (
        "어학연수 어학연수 어학연수 어학연수 "
        "밴쿠버 밴쿠버 밴쿠버 밴쿠버 "
        "캠퍼스 캠퍼스 캠퍼스 "
        "은 은 은 은 는 는 는 는 이 이 이 가 가 가 "  # Korean particles (stopwords)
    )
    plan = derive_keywords(
        title="어학연수 프로그램",
        h1="어학연수 프로그램",
        url="https://www.englishcollege.com/ko/courses",
        body_text=body,
        locale="ko",
    )
    # Korean particles must NOT appear.
    assert "은" not in plan.secondaries
    assert "는" not in plan.secondaries
    # Korean content words SHOULD appear (at least one).
    assert any(t in plan.secondaries for t in ("어학연수", "밴쿠버", "캠퍼스"))


def test_brand_suffix_strip_handles_locale_variants():
    """The brand-suffix regex catches non-EN brand translations too."""
    # German variant
    plan_de = derive_keywords(
        title="Englischkurs in Vancouver | Englische Schule",
        h1="Englischkurs in Vancouver",
        url="https://www.englishcollege.com/de/kurse",
        body_text="",
    )
    assert "englische schule" not in plan_de.primary

    # Japanese variant
    plan_ja = derive_keywords(
        title="バンクーバーの英語コース | 英語学校",
        h1="バンクーバーの英語コース",
        url="https://www.englishcollege.com/ja/courses",
        body_text="",
    )
    assert "英語学校" not in plan_ja.primary


# ---- M-12.4: home page override prevents brand-slogan primary keyword ----


def test_homepage_primary_uses_override_not_brand_slogan():
    """The home page's title + H1 both contain CEL's brand slogan ("fluent in
    creating memories") — the candidate-A/B/C heuristic would pick the slogan
    as the longest shared phrase. The _PRIMARY_KEYWORD_OVERRIDES map forces
    an intent-driven keyword instead.

    Tracker-091 M-12.4: pilot's home.summary.md primary was the brand slogan
    (zero search volume). Override map fixes this without disturbing other
    pages' content-derived behavior.
    """
    plan = derive_keywords(
        title="Fluent in Creating Memories | College of English Language",
        h1="How does CEL ensure we are fluent in creating memories?",
        url="https://www.englishcollege.com/",
        body_text="At CEL we offer English courses across San Diego, Los Angeles, "
                  "and Vancouver. Students study English at our accredited campuses.",
    )
    assert plan.primary == "english language school", (
        f"home page primary should be the override 'english language school', "
        f"got {plan.primary!r}"
    )
    assert "fluent" not in plan.primary
    assert "memories" not in plan.primary


def test_homepage_override_applies_across_locales():
    """The override map is keyed by locale-stripped path, so a single entry
    covers all 9 locales without per-locale duplication."""
    for prefix in ("", "/de", "/fr", "/es", "/it", "/pt", "/ar", "/ko", "/ja"):
        url = f"https://www.englishcollege.com{prefix}/"
        plan = derive_keywords(
            title="Fluent in Creating Memories | CEL",
            h1="Fluent in creating memories",
            url=url,
            body_text="",
        )
        assert plan.primary == "english language school", (
            f"home page override didn't apply for locale prefix {prefix!r}: "
            f"got {plan.primary!r}"
        )


def test_non_homepage_unaffected_by_override():
    """Pages NOT in the override map fall through to the heuristic — make sure
    a typical landing page still derives its primary from content."""
    plan = derive_keywords(
        title="Learn English in USA | CEL",
        h1="Learn English in USA",
        url="https://www.englishcollege.com/learn-english-usa",
        body_text="",
    )
    # The intersection of A/B/C should produce something USA-related, NOT
    # the homepage override.
    assert plan.primary != "english language school"
    assert "english" in plan.primary or "usa" in plan.primary
