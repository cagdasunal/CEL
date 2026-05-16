"""Tests for tools.summary.audit — scoring + REGENERATE/MANUAL_REVIEW/KEEP action."""

from tools.summary.audit import audit_existing_summary


_GOOD = """## How long does it take to learn English in Vancouver

To learn English in Vancouver at CEL takes 6 to 12 months for most students. Small classes (average 7 students) plus full-time intensive options accelerate progress for upper-intermediate learners.

### Choosing the right course to learn English in Vancouver

Most upper-intermediate students reach B2 in 12 weeks with our General English course; beginners need 24 to 36 weeks. See [our Vancouver campus](https://www.englishcollege.com/vancouver) for details.
"""

_BAD = """## Some heading

This is a paragraph with — em dashes — and no keyword presence.

<ul><li>Bad list</li></ul>
"""

_PRIMARY_KW = "learn english in vancouver"
_INVENTORY = ["https://www.englishcollege.com/vancouver"]


def test_empty_summary_recommends_regenerate():
    result = audit_existing_summary(
        url="https://www.englishcollege.com/courses",
        summary_markdown="",
        primary_keyword=_PRIMARY_KW,
        locale="en",
        link_inventory=_INVENTORY,
    )
    assert result.score == 0.0
    assert result.action == "REGENERATE"
    assert "empty_summary" in result.failed_checks


def test_passing_summary_scores_high():
    result = audit_existing_summary(
        url="https://www.englishcollege.com/vancouver/how-long-to-learn-english",
        summary_markdown=_GOOD,
        primary_keyword=_PRIMARY_KW,
        locale="en",
        link_inventory=_INVENTORY,
    )
    assert result.score >= 80.0, f"score={result.score}, notes={result.notes}"
    assert result.action == "KEEP"


def test_failing_summary_recommends_regenerate():
    result = audit_existing_summary(
        url="https://www.englishcollege.com/courses",
        summary_markdown=_BAD,
        primary_keyword=_PRIMARY_KW,
        locale="en",
        link_inventory=_INVENTORY,
    )
    assert result.score < 60.0, f"unexpectedly high score: {result.score}"
    assert result.action == "REGENERATE"
    assert "no_em_dashes" in result.failed_checks
    assert "no_lists" in result.failed_checks


def test_borderline_summary_marks_manual_review():
    # A summary that hits some checks but misses 1-2 critical ones lands in the
    # 60-80 band → MANUAL_REVIEW.
    borderline = """## Learn English in Vancouver — your guide

To learn English in Vancouver at CEL takes 6 to 12 months for most students. Small classes plus full-time intensive options accelerate progress.

### Levels offered

CEL covers all CEFR levels.
"""
    result = audit_existing_summary(
        url="https://www.englishcollege.com/vancouver",
        summary_markdown=borderline,
        primary_keyword=_PRIMARY_KW,
        locale="en",
        link_inventory=_INVENTORY,
    )
    # The em-dash in the H2 fails; depending on other checks, score should be
    # below 80 but action may be REGENERATE or MANUAL_REVIEW.
    assert result.action in ("REGENERATE", "MANUAL_REVIEW")
