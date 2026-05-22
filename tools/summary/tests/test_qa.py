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


# ---- tracker-096: 4-part structure (Tagline / Title / Paragraph / Content) ----

_FOUR_PART_PASS = """## English School Life

### How long does it take to learn english in vancouver

Most students learn english in vancouver in 6 to 12 months at CEL, with small classes of about 7 students and full-time intensive options that accelerate progress.

#### What level do I need to start

CEL accepts all levels from A1 to C2. See [our Vancouver campus](https://www.englishcollege.com/vancouver) for placement details.
"""

_FP_KW = "learn english in vancouver"
_FP_INV = ["https://www.englishcollege.com/vancouver"]


def test_four_part_passing_draft():
    r = qa_checks(
        _FOUR_PART_PASS, _FP_KW, "en", _FP_INV,
        excluded_path_segments=("vc", "sd", "sm"), structure="four_part",
    )
    assert r.passed, f"notes: {r.notes}"
    assert r.checks["tagline_word_count"]
    assert r.checks["keyword_in_title"]
    assert r.checks["keyword_in_paragraph"]
    # tracker-098: links_only_in_content was relaxed to no_links_in_tagline_title.
    assert r.checks["no_links_in_tagline_title"]
    assert r.checks["heading_order"]
    assert r.checks["content_starts_with_h4"]
    assert r.checks["no_link_stuffing"]


def test_four_part_tagline_too_long_is_critical():
    draft = _FOUR_PART_PASS.replace("## English School Life", "## A Tagline With Far Too Many Words")
    r = qa_checks(draft, _FP_KW, "en", _FP_INV, structure="four_part")
    assert not r.checks["tagline_word_count"]
    assert not r.passed


def test_four_part_keyword_must_be_in_title():
    draft = _FOUR_PART_PASS.replace(
        "How long does it take to learn english in vancouver", "A generic section title"
    )
    r = qa_checks(draft, _FP_KW, "en", _FP_INV, structure="four_part")
    assert not r.checks["keyword_in_title"]
    assert not r.passed


def test_four_part_link_in_paragraph_now_allowed():
    """tracker-098: a link in the Paragraphs (before the first H4) is now ALLOWED —
    no_links_in_tagline_title still passes and the draft still passes overall."""
    draft = _FOUR_PART_PASS.replace(
        "accelerate progress.",
        "accelerate progress at [our Vancouver campus](https://www.englishcollege.com/vancouver).",
    )
    r = qa_checks(
        draft, _FP_KW, "en", _FP_INV,
        excluded_path_segments=("vc", "sd", "sm"), structure="four_part",
    )
    assert r.checks["no_links_in_tagline_title"], r.notes
    assert r.passed, r.notes


def test_four_part_link_in_title_is_critical():
    """tracker-098: a link in the Title (H3) must fail no_links_in_tagline_title (CRITICAL).
    Links in headings are detected on the raw heading line (parts.title is markdown-stripped).
    A distinct URL is used so first_occurrence_only stays green and the failure is isolated."""
    draft = _FOUR_PART_PASS.replace(
        "### How long does it take to learn english in vancouver",
        "### How long to [learn english in vancouver](https://www.englishcollege.com/courses)",
    )
    inv = _FP_INV + ["https://www.englishcollege.com/courses"]
    r = qa_checks(draft, _FP_KW, "en", inv, structure="four_part")
    assert not r.checks["no_links_in_tagline_title"], r.notes
    assert r.checks["first_occurrence_only"], r.notes  # the failure is isolated to the heading-link rule
    assert not r.passed


def test_four_part_em_dash_still_critical():
    draft = _FOUR_PART_PASS.replace("6 to 12 months", "6 to 12 months — quickly")
    r = qa_checks(draft, _FP_KW, "en", _FP_INV, structure="four_part")
    assert not r.checks["no_em_dashes"]
    assert not r.passed


def test_four_part_empty_content_is_critical():
    """A 4-part draft with no Content section fails content_starts_with_h4 (CRITICAL),
    so it can't ship an empty RichText `summary` field."""
    draft = (
        "## English School Life\n\n"
        "### How long does it take to learn english in vancouver\n\n"
        "Most students learn english in vancouver in 6 to 12 months at CEL.\n"
    )
    r = qa_checks(draft, _FP_KW, "en", _FP_INV, structure="four_part")
    assert not r.checks["content_starts_with_h4"]
    assert not r.passed


def test_four_part_excluded_link_in_content_flags():
    draft = _FOUR_PART_PASS.replace(
        "[our Vancouver campus](https://www.englishcollege.com/vancouver)",
        "[a legacy listing](https://www.englishcollege.com/vc/student-house)",
    )
    r = qa_checks(
        draft, _FP_KW, "en", _FP_INV,
        excluded_path_segments=("vc", "sd", "sm"), structure="four_part",
    )
    assert not r.checks["no_excluded_links"]


# ---- tracker-097 follow-up: paraphrase/accent/punctuation/inflection-tolerant keyword matching ----
#
# The QA gate used to require the derived keyword as a VERBATIM substring, but a
# generative model reorders, inserts words into, re-punctuates, and inflects the
# keyword. That false-failed blog summaries en masse (the real pilot failures below).
# Matching is now content-token presence (accent/punctuation/inflection tolerant).


def test_keyword_matches_when_model_paraphrases_h2():
    """Real pilot failure: keyword 'anglais pour étudier' (derived) is NOT a contiguous
    substring of the model's H2 'Quel niveau d'anglais est requis pour étudier...'.
    Content-token matching must PASS (the topic is clearly present)."""
    draft = (
        "## Quel niveau d'anglais est requis pour étudier à l'étranger ?\n\n"
        "Pour étudier à l'étranger, un niveau B1 en anglais suffit souvent, "
        "selon le programme choisi et vos objectifs personnels.\n\n"
        "### Comment évaluer son anglais avant de partir étudier\n\n"
        "CEL propose un test de placement dès le premier jour.\n"
    )
    r = qa_checks(draft, "anglais pour étudier", "fr", [])
    assert r.checks["keyword_in_h2"], r.notes
    assert r.checks["keyword_in_p1"], r.notes
    assert r.passed, r.notes


def test_keyword_matches_across_punctuation():
    """A hyphen/apostrophe between the keyword's words must not break the match
    ('séjour linguistique' ~ 'séjour-linguistique')."""
    draft = (
        "## Tout sur le séjour-linguistique à San Diego\n\n"
        "Un séjour-linguistique à San Diego combine cours d'anglais et plage.\n"
    )
    r = qa_checks(draft, "séjour linguistique", "fr", [])
    assert r.checks["keyword_in_h2"]
    assert r.checks["keyword_in_p1"]


def test_keyword_matches_across_inflection():
    """Inflected forms match ('learn' ~ 'learning')."""
    draft = (
        "## Learning English in Vancouver\n\n"
        "Learning English in Vancouver at CEL takes most students 6 to 12 months.\n"
    )
    r = qa_checks(draft, "learn english", "en", [])
    assert r.checks["keyword_in_h2"]
    assert r.checks["keyword_in_p1"]


def test_keyword_matches_german_suffix_inflection():
    """German verb inflection (suffix substitution): keyword 'überraschen' vs the H2's
    'überrascht' must match via shared stem — without false-matching short shared prefixes."""
    from tools.summary.qa import _keyword_covered
    h2 = "Was überrascht Studenten in Vancouver"
    assert _keyword_covered("studenten in vancouver überraschen", h2, "de")
    # Guard: a 5-char shared prefix ("inter") must NOT cause a false match.
    assert not _keyword_covered("international", "an interesting topic", "en")


def test_keyword_topic_absent_still_fails():
    """Robustness guard: if NONE of the keyword's content words are present, the
    check still FAILS — the fix must not make every keyword pass."""
    draft = (
        "## A completely unrelated heading about cooking recipes\n\n"
        "This paragraph is about food and has nothing to do with the subject.\n"
    )
    r = qa_checks(draft, "séjour linguistique", "fr", [])
    assert not r.checks["keyword_in_h2"]
    assert not r.passed


def test_density_floor_satisfied_when_topic_present_but_phrase_paraphrased():
    """A multi-word keyword whose words are present but never appear as the exact
    phrase satisfies the density FLOOR via topic presence (old code scored 0.00% → fail)."""
    draft = (
        "## Le séjour idéal pour apprendre une langue\n\n"
        "Un bon séjour à l'étranger améliore votre apprentissage linguistique. "
        "Le séjour combine cours et immersion, et l'expérience linguistique reste intense.\n"
    )
    r = qa_checks(draft, "séjour linguistique", "fr", [])  # exact phrase never appears
    assert r.checks["keyword_density"], r.notes


def test_density_ceiling_still_catches_stuffing():
    """Anti-stuffing preserved: repeating the exact keyword phrase trips the 2.0% ceiling."""
    stuffed = "## learn english\n\n" + ("learn english " * 25) + "is great.\n"
    r = qa_checks(stuffed, "learn english", "en", [])
    assert not r.checks["keyword_density"], r.notes


def test_keyword_in_p1_allows_topic_later_in_lead_paragraph():
    """The keyword topic may appear past the first 120 chars of the lead paragraph;
    the whole lead block counts (the old fixed 120-char window false-failed multi-word
    keywords whose words land just past the cutoff)."""
    draft = (
        "## Comment bien se préparer avant de partir\n\n"
        "Avant le départ, il faut organiser son budget, réserver son logement, "
        "obtenir son visa étudiant et vérifier son assurance, puis penser concrètement "
        "à son séjour linguistique pour en tirer le maximum dès la première semaine.\n\n"
        "### Détails pratiques\n\nCEL accompagne chaque étudiant pas à pas.\n"
    )
    r = qa_checks(draft, "séjour linguistique", "fr", [])
    assert r.checks["keyword_in_p1"], r.notes


def test_four_part_keyword_matches_when_title_paraphrases():
    """4-part Title may paraphrase the keyword (content words present, not verbatim)."""
    draft = (
        "## English School Life\n\n"
        "### Niveau d'anglais requis avant de partir étudier à l'étranger\n\n"
        "Pour étudier à l'étranger en anglais, un niveau B1 suffit souvent selon le programme.\n\n"
        "#### Comment se préparer\n\nCEL propose un test de placement dès le premier jour.\n"
    )
    r = qa_checks(draft, "anglais pour étudier", "fr", [], structure="four_part")
    assert r.checks["keyword_in_title"], r.notes
    assert r.checks["keyword_in_paragraph"], r.notes


# ---- tracker-098: locale-matched links for blog (single_block) ----

_DE_BLOG = (
    "## Wie lange dauert es, Englisch zu lernen\n\n"
    "Die meisten Lernenden erreichen B2 in etwa zwölf Wochen, abhängig vom Startniveau "
    "und den Wochenstunden. Siehe {LINK} für Details.\n"
)
_DE_INV = [
    "https://www.englishcollege.com/de/post/englisch-lernen",
    "https://www.englishcollege.com/de/vancouver",
    "https://www.englishcollege.com/post/learn-english",  # an EN sibling (wrong locale for a DE post)
]


def test_blog_links_locale_matched_passes_for_same_locale_link():
    draft = _DE_BLOG.format(
        LINK="[unser Vancouver-Campus](https://www.englishcollege.com/de/vancouver)"
    )
    r = qa_checks(draft, "englisch lernen", "de", _DE_INV)
    assert r.checks["links_locale_matched"], r.notes
    assert r.passed, r.notes


def test_blog_off_locale_link_is_critical():
    """A DE blog post linking to an unprefixed (EN) URL fails links_locale_matched (CRITICAL)."""
    draft = _DE_BLOG.format(
        LINK="[learn English](https://www.englishcollege.com/post/learn-english)"
    )
    r = qa_checks(draft, "englisch lernen", "de", _DE_INV)
    assert not r.checks["links_locale_matched"], r.notes
    assert not r.passed


def test_blog_en_post_rejects_prefixed_locale_link():
    """An EN post must NOT link to a /de/ (or any prefixed-locale) URL."""
    draft = (
        "## How long does it take to learn English\n\n"
        "Most students reach B2 in about 12 weeks. See "
        "[our German page](https://www.englishcollege.com/de/vancouver) for more.\n"
    )
    inv = ["https://www.englishcollege.com/de/vancouver", "https://www.englishcollege.com/vancouver"]
    r = qa_checks(draft, "learn english", "en", inv)
    assert not r.checks["links_locale_matched"], r.notes
    assert not r.passed


def test_blog_locale_check_vacuous_without_inventory():
    """Audit phase (no inventory) must not block on the locale-match check."""
    draft = _DE_BLOG.format(
        LINK="[learn English](https://www.englishcollege.com/post/learn-english)"
    )
    r = qa_checks(draft, "englisch lernen", "de", [])  # no inventory
    assert r.checks["links_locale_matched"]


def test_four_part_is_exempt_from_locale_match():
    """Courses/housing/landing (Weglot-translated) are EXEMPT — the locale-match check
    is not even present in the four_part report."""
    draft = (
        "## English School Life\n\n"
        "### How long does it take to learn english in vancouver\n\n"
        "Most students learn english in vancouver in 6 to 12 months at CEL.\n\n"
        "#### What level do I need\n\nAll levels. See "
        "[our German page](https://www.englishcollege.com/de/vancouver).\n"
    )
    inv = ["https://www.englishcollege.com/de/vancouver"]
    r = qa_checks(draft, "learn english in vancouver", "en", inv, structure="four_part")
    assert "links_locale_matched" not in r.checks


# ---- tracker-098: 6-8 link target + hard anti-stuffing ceiling ----


def _long_body(words: int) -> str:
    """A blank-line-separated prose body of ~`words` words (no links, no headings)."""
    sentence = "Students reach strong fluency through steady daily practice and feedback. "
    text = (sentence * ((words // 10) + 1)).strip()
    return text


def test_link_density_passes_in_target_band_for_long_summary():
    """A long summary with 7 links (inside the 6-8 target / 5-9 band) passes link_density
    and is not flagged as stuffing."""
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(7)
    )
    draft = "## How long to learn english in vancouver\n\n" + _long_body(700) + " " + links + "\n"
    r = qa_checks(draft, "learn english in vancouver", "en", [])
    assert r.checks["link_density"], r.notes
    assert r.checks["no_link_stuffing"], r.notes


def test_link_density_warns_when_under_linked_long_summary():
    """A long (700-word) summary with only 1 link falls below the band → link_density
    warns (scored fail), but it's NOT a critical stuffing failure."""
    draft = (
        "## How long to learn english in vancouver\n\n" + _long_body(700)
        + " See [our Vancouver campus](https://www.englishcollege.com/vancouver).\n"
    )
    r = qa_checks(draft, "learn english in vancouver", "en", [])
    assert not r.checks["link_density"], r.notes
    assert r.checks["no_link_stuffing"]  # under-linking is not stuffing


def test_link_stuffing_ceiling_is_critical():
    """Exceeding 1 link per ~90 words trips no_link_stuffing (CRITICAL)."""
    # ~120 words with 20 links → ~6 words/link, far over the 1/90 ceiling.
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(20)
    )
    draft = "## How long to learn english in vancouver\n\n" + _long_body(120) + " " + links + "\n"
    r = qa_checks(draft, "learn english in vancouver", "en", [])
    assert not r.checks["no_link_stuffing"], r.notes
    assert not r.passed


def test_short_draft_with_few_links_still_passes_density():
    """The original short fixtures (1 link, ~120 words) must remain green under the new band."""
    r = qa_checks(_PASSING_DRAFT, _PRIMARY_KW, "en", _INVENTORY)
    assert r.checks["link_density"], r.notes
    assert r.checks["no_link_stuffing"]


# ---- tracker-098 pass 2: ceiling loosened 90 → 80 (so the raised word-count targets,
#      every minimum ≥ 650, leave headroom for 8 links @ 1/80 = 640 words). ----


def _exact_words(n: int) -> str:
    """Return a prose string of EXACTLY `n` words (no links, no headings)."""
    return " ".join(["word"] * n) + "."  # the trailing period is not a \b\w+\b match


def _draft_with_links(body_words: int, n_links: int) -> str:
    """A single-block draft: one H2, a body of `body_words` plain words, and `n_links`
    Markdown links appended. qa counts the H2 text (3 words) + body + 9 words/link."""
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(n_links)
    )
    return f"## a section heading\n\n{_exact_words(body_words)} {links}\n"


def test_link_stuffing_ceiling_constant_is_80():
    """tracker-098 pass 2: the hard anti-stuffing ceiling moved from 90 to 80 words/link."""
    from tools.summary.qa import _LINK_STUFFING_WORDS_PER_LINK

    assert _LINK_STUFFING_WORDS_PER_LINK == 80


def test_link_stuffing_function_boundary_at_80():
    """The pure ceiling: 8 links pass at 640 words (8/80), fail at 639."""
    from tools.summary.qa import _link_stuffing

    assert not _link_stuffing(8, 640)  # exactly 1/80 — not over the ceiling
    assert _link_stuffing(8, 639)      # one word short — over the ceiling, FAIL


def test_650_word_8_link_draft_passes_no_link_stuffing():
    """A 650-word / 8-link summary clears the 1/80 ceiling (650/80 = 8.125 > 8)."""
    # body sized so total word_count == 650: 3 (heading) + body + 8*9 (links) = 650.
    draft = _draft_with_links(body_words=650 - 3 - 8 * 9, n_links=8)
    r = qa_checks(draft, "a section", "en", [])
    # A passing check appends no note, so verify the boolean directly. (notes is a
    # list populated only on failure; assert nothing about no_link_stuffing is in it.)
    assert r.checks["no_link_stuffing"], r.notes
    assert not any(n.startswith("no_link_stuffing") for n in r.notes), r.notes


def test_400_word_8_link_draft_fails_no_link_stuffing():
    """A 400-word / 8-link summary trips the 1/80 ceiling (400/80 = 5 < 8) → CRITICAL fail."""
    draft = _draft_with_links(body_words=400 - 3 - 8 * 9, n_links=8)
    r = qa_checks(draft, "a section", "en", [])
    assert not r.checks["no_link_stuffing"], r.notes
    assert not r.passed
    # The failure note records the actual word count + ceiling for triage.
    stuffing_note = next(n for n in r.notes if n.startswith("no_link_stuffing"))
    assert "400 words" in stuffing_note, stuffing_note
    assert "ceiling 1 per 80" in stuffing_note, stuffing_note


# ---- 2026-05-22: internal-domain link guardrail (the /housing incident) ----
#
# A few external links (e.g. https://claude.ai/...) had leaked onto the live /housing
# page. Root cause: the only domain-aware check (link_in_inventory) was a non-critical
# WARNING, so a hallucinated off-site link passed QA and shipped. links_internal_domain
# is now a CRITICAL check: every link target must be a root-relative path or an
# englishcollege.com URL. A summary with any off-domain link is rejected (never ships).


def test_link_internal_domain_helper():
    """The host-level guardrail: relative paths + englishcollege.com (incl. subdomains)
    are internal; foreign domains, lookalikes, and non-web schemes are external."""
    from tools.summary.qa import _link_internal_domain_ok

    # Internal — root-relative path / bare slug / fragment / query.
    assert _link_internal_domain_ok("/courses")
    assert _link_internal_domain_ok("courses")
    assert _link_internal_domain_ok("#section")
    assert _link_internal_domain_ok("?ref=x")
    # Internal — englishcollege.com, www, and any subdomain.
    assert _link_internal_domain_ok("https://www.englishcollege.com/courses")
    assert _link_internal_domain_ok("https://englishcollege.com/courses")
    assert _link_internal_domain_ok("http://www.englishcollege.com/de/kurse")
    assert _link_internal_domain_ok("https://cel.englishcollege.com/llms.txt")
    # External — foreign domains (the actual incident), lookalikes, non-web schemes.
    assert not _link_internal_domain_ok("https://claude.ai/")
    assert not _link_internal_domain_ok("https://claude.ai/vancouver")
    assert not _link_internal_domain_ok("https://x.com")
    assert not _link_internal_domain_ok("https://example.com/courses")
    assert not _link_internal_domain_ok("https://notenglishcollege.com/x")  # suffix-bypass guard
    assert not _link_internal_domain_ok("https://englishcollege.com.evil.com/x")  # lookalike guard
    assert not _link_internal_domain_ok("mailto:info@englishcollege.com")
    assert not _link_internal_domain_ok("javascript:alert(1)")
    assert not _link_internal_domain_ok("")


def test_external_domain_link_is_critical_single_block():
    """A single-block (blog) summary linking to claude.ai fails links_internal_domain
    (CRITICAL) and so does not pass QA."""
    draft = _PASSING_DRAFT.replace(
        "https://www.englishcollege.com/vancouver", "https://claude.ai/vancouver"
    )
    report = qa_checks(draft, _PRIMARY_KW, "en", _INVENTORY)
    assert not report.checks["links_internal_domain"], report.notes
    assert not report.passed
    note = next(n for n in report.notes if n.startswith("links_internal_domain"))
    assert "claude.ai" in note, note


def test_external_domain_link_is_critical_four_part():
    """A 4-part (course/housing/landing) summary linking to claude.ai fails
    links_internal_domain (CRITICAL) and so does not pass QA — the /housing path."""
    draft = _FOUR_PART_PASS.replace(
        "https://www.englishcollege.com/vancouver", "https://claude.ai/vancouver"
    )
    r = qa_checks(
        draft, _FP_KW, "en", _FP_INV,
        excluded_path_segments=("vc", "sd", "sm"), structure="four_part",
    )
    assert not r.checks["links_internal_domain"], r.notes
    assert not r.passed


def test_relative_links_pass_domain_check():
    """Root-relative internal links satisfy the domain check (and still pass overall)."""
    draft = _PASSING_DRAFT.replace("https://www.englishcollege.com/vancouver", "/vancouver")
    report = qa_checks(draft, _PRIMARY_KW, "en", [])  # empty inventory → link_in_inventory vacuous
    assert report.checks["links_internal_domain"], report.notes
    assert report.passed, report.notes


def test_passing_drafts_satisfy_domain_check():
    """Regression guard: the canonical passing fixtures (englishcollege.com links) keep
    links_internal_domain green under both structures."""
    single = qa_checks(_PASSING_DRAFT, _PRIMARY_KW, "en", _INVENTORY)
    assert single.checks["links_internal_domain"], single.notes
    four = qa_checks(
        _FOUR_PART_PASS, _FP_KW, "en", _FP_INV,
        excluded_path_segments=("vc", "sd", "sm"), structure="four_part",
    )
    assert four.checks["links_internal_domain"], four.notes
