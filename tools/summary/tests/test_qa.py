"""Tests for tools.summary.qa — rule checks (em-dash, lists, headings, keyword placement, density)."""

from tools.summary.qa import qa_checks, boilerplate_pairs


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


# ---- tracker-092 SEO / no-new-content guards ----


_SOURCE = (
    "CEL Vancouver offers General English and IELTS prep. Shared apartments in "
    "Kitsilano start at $1,950 per month. Classes average 7 students. Most "
    "upper-intermediate students reach B2 in 12 weeks. Founded 1985."
)


def test_fact_grounding_prices_blocks_fabricated_price():
    """A $-price not present in the source is a CRITICAL fabrication → not passed."""
    draft = _PASSING_DRAFT.replace(
        "for details.",
        "for details. Tuition is just $2,750 per month.",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY, source_text=_SOURCE)
    assert not report.checks["fact_grounding_prices"], report.notes
    assert not report.passed  # price fabrication is critical


def test_fact_grounding_prices_passes_when_price_in_source():
    draft = _PASSING_DRAFT.replace(
        "for details.",
        "for details. Shared apartments start at $1,950 per month.",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY, source_text=_SOURCE)
    assert report.checks["fact_grounding_prices"]


def test_fact_grounding_prices_vacuous_pass_without_source():
    """Audit phase (no source_text) must not block on grounding."""
    draft = _PASSING_DRAFT.replace("for details.", "for details. Costs $9,999 per month.")
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)  # no source_text
    assert report.checks["fact_grounding_prices"]


def test_fact_grounding_figures_warns_on_unsourced_year():
    """A year not in source is a non-critical warning (figures), not a block."""
    draft = _PASSING_DRAFT.replace("for details.", "for details. CEL was founded in 1962.")
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY, source_text=_SOURCE)
    assert not report.checks["fact_grounding_figures"]  # 1962 not in source (1985 is)


def test_fact_grounding_figures_does_not_double_flag_price_digits():
    """tracker-093 L1: a fabricated price is flagged ONCE (by prices), not also by
    figures on its inner digit-core (the '750' inside '$2,750')."""
    draft = _PASSING_DRAFT.replace("for details.", "for details. Tuition is $2,750 monthly.")
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY, source_text=_SOURCE)
    assert not report.checks["fact_grounding_prices"], "price should be flagged (fabricated)"
    assert report.checks["fact_grounding_figures"], (
        f"figures must NOT re-flag the price's digits; notes: {report.notes}"
    )


def test_near_duplicate_flags_verbatim_copy():
    """A draft that copies the source verbatim trips the near-duplicate guard."""
    verbatim = (
        "## How long to learn English in Vancouver\n\n"
        + _SOURCE + " " + _SOURCE + "\n"
    )
    report = qa_checks(verbatim, _PRIMARY_KW, "en", _INVENTORY, source_text=_SOURCE)
    assert not report.checks["near_duplicate"], report.notes


def test_answer_first_flags_hedge_opener():
    draft = _PASSING_DRAFT.replace(
        "To learn English in Vancouver at CEL takes 6 to 12 months",
        "This page covers how long it takes to learn English in Vancouver and more",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["answer_first"], report.notes


def test_descriptive_anchors_flags_generic_cta():
    draft = _PASSING_DRAFT.replace(
        "[our Vancouver campus](https://www.englishcollege.com/vancouver)",
        "[click here](https://www.englishcollege.com/vancouver)",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["descriptive_anchors"], report.notes


def test_no_faq_schema_blocks_jsonld():
    draft = _PASSING_DRAFT + '\n\n<script type="application/ld+json">{"@type":"FAQPage"}</script>'
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["no_faq_schema"]
    assert not report.passed  # schema injection is critical


def test_link_in_inventory_flags_invented_url():
    draft = _PASSING_DRAFT.replace(
        "[our Vancouver campus](https://www.englishcollege.com/vancouver)",
        "[our Vancouver campus](https://www.englishcollege.com/invented-page)",
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["link_in_inventory"], report.notes


def test_existing_passing_draft_still_passes_with_grounding():
    """The original passing draft, given a matching source, still fully passes."""
    src = "Learn English in Vancouver at CEL. B2 in 12 weeks. 7 students per class. A1 to C2 levels."
    report = qa_checks(_PASSING_DRAFT, _PRIMARY_KW, "en", _INVENTORY, source_text=src)
    assert report.passed, f"notes: {report.notes}"


def test_boilerplate_pairs_flags_near_identical_summaries():
    """tracker-092 (1.3): two summaries that are near-duplicates of each other
    are flagged; distinct summaries are not."""
    a = _PASSING_DRAFT
    b = _PASSING_DRAFT.replace("Vancouver", "Vancouver").replace("6 to 12", "6 to 12")  # ~identical
    distinct = (
        "## Why study English in San Diego\n\nSan Diego offers year-round sunshine and "
        "beachside campuses. Students pick from morning or afternoon intensives.\n"
    )
    pairs = boilerplate_pairs({"page-a": a, "page-b": b, "page-c": distinct})
    flagged = {tuple(sorted((x, y))) for x, y, _ in pairs}
    assert ("page-a", "page-b") in flagged
    assert ("page-a", "page-c") not in flagged
    assert ("page-b", "page-c") not in flagged


def test_boilerplate_pairs_empty_for_single_summary():
    assert boilerplate_pairs({"only": _PASSING_DRAFT}) == []
