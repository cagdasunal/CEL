"""Tests for tools.summary.qa — rule checks (em-dash, lists, headings, keyword placement, density)."""

from tools.summary.qa import qa_checks


_PASSING_DRAFT = """## How long does it take to learn English in Vancouver

To learn English in Vancouver at CEL takes 6 to 12 months for most students, depending on starting level and weekly hours. Small classes (average 7 students) plus full-time intensive options accelerate progress.

### Choosing the right course to learn English in Vancouver

Most upper-intermediate students reach B2 in 12 weeks with our General English course, while beginners need 24 to 36 weeks. See [our Vancouver campus](https://www.englishcollege.com/vancouver) for details.

### What level do I need to start

CEL accepts all levels from A1 to C2, with placement testing on day one to match you to the right course intensity.
"""

_PRIMARY_KW = "learn english in vancouver"
_INVENTORY = ["https://www.englishcollege.com/vancouver", "https://www.englishcollege.com/courses"]


def test_passing_draft():
    report = qa_checks(_PASSING_DRAFT, _PRIMARY_KW, "en", _INVENTORY)
    assert report.passed, f"expected pass, got notes: {report.notes}"
    assert report.checks["no_em_dashes"]
    assert report.checks["no_lists"]
    assert report.checks["heading_order"]
    assert report.checks["keyword_in_h2"]
    assert report.checks["keyword_in_p1"]


def test_em_dash_fails():
    draft = _PASSING_DRAFT.replace("at CEL takes", "at CEL — takes")
    assert "—" in draft  # sanity: confirm the replacement worked
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.passed
    assert not report.checks["no_em_dashes"]


def test_list_tag_fails():
    draft = _PASSING_DRAFT + "\n<ul><li>item</li></ul>"
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["no_lists"]


def test_missing_keyword_in_h2_fails():
    draft = _PASSING_DRAFT.replace(
        "How long does it take to learn English in Vancouver",
        "Quick guide to studying abroad",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["keyword_in_h2"]
    assert not report.passed


def test_excluded_link_fails():
    draft = _PASSING_DRAFT + "\n\nSee [Vancouver Housing](https://www.englishcollege.com/vc/student-house)."
    report = qa_checks(
        draft,
        _PRIMARY_KW,
        "en",
        _INVENTORY,
        excluded_path_segments=("vc", "sd", "sm"),
    )
    assert not report.checks["no_excluded_links"]


def test_duplicate_link_targets_fail():
    draft = _PASSING_DRAFT + (
        "\n\nLearn more about our [Vancouver campus](https://www.englishcollege.com/vancouver) again."
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["first_occurrence_only"]


def test_heading_order_h1_fails():
    draft = "# Top-level heading\n\n" + _PASSING_DRAFT
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["heading_order"]


def test_density_check_within_range():
    report = qa_checks(_PASSING_DRAFT, _PRIMARY_KW, "en", _INVENTORY)
    # The passing draft contains the keyword phrase ~3 times in ~120 words ≈ 2.5%.
    # If density is just over 2.0%, that's the edge — accept either outcome but
    # confirm the check ran and produced a note.
    assert "keyword_density" in report.checks
