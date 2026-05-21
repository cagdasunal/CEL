"""QA — port of /page-summary Phase 7 rule checks.

Pure functions. Called by both batch_runner (post-generation) and audit (scoring
existing summaries). No I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Locales where Latin char limits don't apply (script uses fewer characters per unit).
_NON_LATIN_LOCALES = ("ko", "ja", "ar")

# Rule constants (mirror /page-summary SKILL.md "Critical rules" + Phase 7 checklist).
_EM_DASH_CHARS = ("—", "–")
_LIST_TAG_RE = re.compile(r"<\s*(ul|ol|li)\b", re.IGNORECASE)
_H_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LINKS_PER_1000_LOW = 2
_LINKS_PER_1000_HIGH = 5
_DENSITY_LOW = 0.003  # 0.3%
_DENSITY_HIGH = 0.020  # 2.0%
_KEYWORD_P1_WINDOW_CHARS = 120

# tracker-092: hedge/meta openers that violate the answer-first rule.
_HEDGE_OPENER_RE = re.compile(
    r"^\s*(this page|in this|here we|here you|welcome to|learn about|"
    r"in today'?s|in the world of|when it comes to|it'?s important to)",
    re.IGNORECASE,
)
# Generic CTA anchors that are never acceptable as link text.
_GENERIC_ANCHORS = frozenset(
    {"click here", "read more", "learn more", "here", "this page", "more", "link"}
)
# The stable set of checks that contribute to QaReport.score. The audit phase's
# REGENERATE/MANUAL_REVIEW/KEEP thresholds are calibrated against these 10; the
# tracker-092 SEO/grounding guards gate `passed` but are intentionally excluded
# from the score so audit calibration is preserved.
_SCORED_CHECKS = (
    "no_em_dashes", "no_lists", "heading_order", "link_density",
    "first_occurrence_only", "no_excluded_links", "keyword_in_h2",
    "keyword_in_p1", "keyword_in_h3", "keyword_density",
)
# tracker-096: the parallel stable scored set for the 4-part structure
# (Tagline/Title/Paragraph/Content). Same count + role as _SCORED_CHECKS, with the
# structure/keyword checks swapped for their 4-part equivalents.
_SCORED_CHECKS_FOUR_PART = (
    "no_em_dashes", "no_lists", "heading_order", "link_density",
    "first_occurrence_only", "no_excluded_links", "keyword_in_title",
    "keyword_in_paragraph", "tagline_word_count", "keyword_density",
)


@dataclass
class QaReport:
    passed: bool
    score: float  # 0–100
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, note: str = "") -> None:
        self.checks[name] = ok
        if not ok and note:
            self.notes.append(f"{name}: {note}")


def qa_checks(
    draft: str,
    primary_keyword: str,
    locale: str,
    link_inventory: Iterable[str],
    excluded_path_segments: Iterable[str] = (),
    source_text: str = "",
    structure: str = "single_block",
) -> QaReport:
    """Run all rule checks on a draft. Returns a QaReport with per-check pass/fail.

    A draft is Markdown-formatted text (rich-text Summary section). The check
    set mirrors the locked rules in `.claude/skills/page-summary/SKILL.md` Phase 7,
    plus the tracker-092 SEO/no-new-content guards (fact-grounding, near-duplicate,
    answer-first, descriptive anchors, no-schema, link-in-inventory).

    `source_text` is the source page body the summary was generated from. When
    provided (the generate-english phase has it; the audit phase may not), the
    fact-grounding and near-duplicate checks run against it. When empty those
    checks pass vacuously, so audit-phase callers keep their prior behavior.

    tracker-096: `structure="four_part"` switches to the Tagline/Title/Paragraph/
    Content rule set (see `_qa_checks_four_part`). The default "single_block" path
    below is unchanged — blog summaries + audit callers keep their exact behavior.
    """
    if structure == "four_part":
        return _qa_checks_four_part(
            draft, primary_keyword, locale, link_inventory,
            excluded_path_segments=excluded_path_segments, source_text=source_text,
        )
    report = QaReport(passed=True, score=100.0)
    primary_kw_lower = primary_keyword.lower().strip()
    body_text = re.sub(r"<[^>]+>", "", draft)
    word_count = len(re.findall(r"\b\w+\b", body_text))
    inventory = set(link_inventory)
    excluded = tuple(excluded_path_segments)
    source_digits = re.sub(r"[^\d]", "", source_text)

    # 1. No em dashes.
    em_dash_count = sum(draft.count(ch) for ch in _EM_DASH_CHARS)
    report.add(
        "no_em_dashes",
        em_dash_count == 0,
        f"found {em_dash_count} em-dash character(s)",
    )

    # 2. No HTML list tags (paragraphs only).
    list_match = _LIST_TAG_RE.search(draft)
    report.add("no_lists", list_match is None, "draft contains <ul>/<ol>/<li>")

    # 3. Heading order: exactly 1 H2 then H3s only (no H1 or H4+).
    h_levels = [len(m.group(1)) for m in _H_RE.finditer(draft)]
    has_one_h2 = h_levels.count(2) == 1
    no_h1 = 1 not in h_levels
    no_deeper = all(h <= 3 for h in h_levels)
    report.add(
        "heading_order",
        has_one_h2 and no_h1 and no_deeper,
        f"heading-level distribution {h_levels}",
    )

    # 4. Link count within 2–5 per 1000 words.
    links = _LINK_RE.findall(draft)
    target_links = [url for _, url in links]
    link_density = (len(target_links) / max(word_count, 1)) * 1000
    in_range = _LINKS_PER_1000_LOW <= link_density <= _LINKS_PER_1000_HIGH or (
        word_count < 250 and len(target_links) <= _LINKS_PER_1000_HIGH
    )
    report.add(
        "link_density",
        in_range,
        f"{len(target_links)} links in {word_count} words ({link_density:.1f}/1000)",
    )

    # 5. First-occurrence-only — no duplicate link targets.
    duplicate_targets = [u for u in target_links if target_links.count(u) > 1]
    report.add(
        "first_occurrence_only",
        not duplicate_targets,
        f"duplicate link targets: {sorted(set(duplicate_targets))}",
    )

    # 6. No excluded path segments in any link target (vc/sd/sm housing).
    bad_segment_links = [
        u
        for u in target_links
        if any(_path_has_segment(u, seg) for seg in excluded)
    ]
    report.add(
        "no_excluded_links",
        not bad_segment_links,
        f"links to excluded segments: {bad_segment_links}",
    )

    # 7. Primary keyword in H2.
    h2_lines = [m.group(2) for m in _H_RE.finditer(draft) if len(m.group(1)) == 2]
    kw_in_h2 = any(_keyword_covered(primary_keyword, h2, locale) for h2 in h2_lines) if h2_lines else False
    report.add(
        "keyword_in_h2",
        kw_in_h2,
        f"primary keyword {primary_keyword!r} (topic) not found in any H2 ({h2_lines})",
    )

    # 8. Primary keyword (topic) in the lead paragraph under the H2. (The separate
    #    answer_first warning guards against burying the answer; requiring the topic in
    #    the WHOLE lead block — not an arbitrary 120-char window — avoids false-failing
    #    a multi-word keyword whose words span the first sentence.)
    p1_text = _first_paragraph_under_h2(draft)
    kw_in_p1 = _keyword_covered(primary_keyword, p1_text, locale)
    report.add(
        "keyword_in_p1",
        kw_in_p1,
        "primary keyword (topic) not found in the lead paragraph",
    )

    # 9. Primary keyword in ≥1 H3.
    h3_lines = [m.group(2) for m in _H_RE.finditer(draft) if len(m.group(1)) == 3]
    kw_in_h3 = any(_keyword_covered(primary_keyword, h3, locale) for h3 in h3_lines)
    report.add(
        "keyword_in_h3",
        kw_in_h3 or not h3_lines,  # If no H3s, this check passes vacuously.
        f"no H3 contains primary keyword (H3 lines: {len(h3_lines)})",
    )

    # 10. Body density — keyword topic present (content tokens), not over-stuffed (<=2.0%).
    in_density_range, density = _keyword_density_ok(primary_keyword, body_text, word_count, locale)
    report.add(
        "keyword_density",
        in_density_range,
        f"density {density * 100:.2f}% (keyword topic present + <=2.0% ceiling)",
    )

    # ---- tracker-092 SEO / no-new-content guards ----

    # 11. Fact-grounding (prices + percentages) — CRITICAL. Every $-price and
    #     %-figure in the draft must be traceable to the source page. A
    #     fabricated price is the most harmful "new content" failure. Matching
    #     is digit-normalized + loose (errs toward PASS) so a legitimately
    #     source-present figure is never falsely blocked. Vacuous-pass when no
    #     source_text is supplied (audit phase).
    price_pct_tokens = re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%", draft)
    if source_text:
        unmatched_money = [
            t for t in price_pct_tokens
            if re.sub(r"[^\d]", "", t) and re.sub(r"[^\d]", "", t) not in source_digits
        ]
    else:
        unmatched_money = []
    report.add(
        "fact_grounding_prices",
        not unmatched_money,
        f"prices/percentages not found in source: {unmatched_money}",
    )

    # 12. Fact-grounding (years / decimals / large integers) — WARNING. Softer
    #     signals that often have word-forms in source; flag for review, don't block.
    #     tracker-093 L1: strip price/percentage spans first so a figure already
    #     reported by check 11 (e.g. the "750" inside "$2,750") isn't double-flagged.
    if source_text:
        draft_for_figures = re.sub(
            r"\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%", " ", draft
        )
        figure_tokens = re.findall(r"\b(?:19|20)\d{2}\b|\b\d+\.\d+\b|\b\d{3,}\b", draft_for_figures)
        unmatched_figures = [
            t for t in figure_tokens
            if re.sub(r"[^\d]", "", t) not in source_digits
        ]
    else:
        unmatched_figures = []
    report.add(
        "fact_grounding_figures",
        not unmatched_figures,
        f"figures not found in source (review): {unmatched_figures}",
    )

    # 13. Near-duplicate vs source — WARNING. If most of the draft's word-5-gram
    #     shingles also appear in the source, the model copied the page verbatim
    #     instead of recapping it. Containment > 0.70 flags. Vacuous-pass w/o source.
    if source_text and word_count >= 40:
        draft_shingles = _word_shingles(body_text, 5)
        source_shingles = _word_shingles(source_text, 5)
        if draft_shingles:
            contained = len(draft_shingles & source_shingles) / len(draft_shingles)
        else:
            contained = 0.0
        not_duplicate = contained <= 0.70
    else:
        contained = 0.0
        not_duplicate = True
    report.add(
        "near_duplicate",
        not_duplicate,
        f"draft shingle-containment vs source {contained:.0%} (>70% = verbatim copy)",
    )

    # 14. Answer-first — WARNING. P1 must open with a direct answer, not a hedge/
    #     meta opener ("This page...", "In this...", "Welcome to...").
    p1_text = _first_paragraph_under_h2(draft)
    first_sentence = re.split(r"(?<=[.!?])\s", p1_text.strip(), maxsplit=1)[0] if p1_text.strip() else ""
    answer_first = bool(first_sentence) and not _HEDGE_OPENER_RE.match(first_sentence)
    report.add(
        "answer_first",
        answer_first,
        f"P1 opens with a hedge/meta phrase: {first_sentence[:60]!r}",
    )

    # 15. Descriptive anchors — WARNING. Anchor text must be ≥2 words and not a
    #     generic CTA ("click here", "read more", "here").
    link_anchors = [a for a, _ in links]
    bad_anchors = [
        a for a in link_anchors
        if len(a.split()) < 2 or a.strip().lower() in _GENERIC_ANCHORS
    ]
    report.add(
        "descriptive_anchors",
        not bad_anchors,
        f"non-descriptive anchors: {bad_anchors}",
    )

    # 16. No schema / script — CRITICAL. The summary is plain rich-text Markdown;
    #     it must never carry JSON-LD (incl. FAQPage), <script>, or <iframe>.
    has_schema = bool(re.search(r"faqpage|application/ld\+json|<\s*script|<\s*iframe", draft, re.IGNORECASE))
    report.add(
        "no_faq_schema",
        not has_schema,
        "draft contains schema/script/iframe markup (must be plain Markdown)",
    )

    # 17. Links in inventory — WARNING. Every link target must come from the
    #     provided inventory (the model must not invent URLs). Only enforced
    #     when an inventory was supplied.
    if inventory:
        invented = [u for u in target_links if u not in inventory]
    else:
        invented = []
    report.add(
        "link_in_inventory",
        not invented,
        f"link targets not in inventory (invented?): {invented}",
    )

    # Aggregate score over the STABLE original-10 set only. The tracker-092
    # guards (checks 11-17) gate `passed` and surface in notes, but they do NOT
    # enter the score — that keeps the audit-phase REGENERATE/MANUAL_REVIEW/KEEP
    # calibration (config thresholds) exactly where it was. Several of the new
    # guards pass vacuously when source_text/inventory are absent (audit phase),
    # so counting them would silently inflate audit scores.
    scored = [report.checks[c] for c in _SCORED_CHECKS if c in report.checks]
    report.score = (sum(scored) / len(scored)) * 100 if scored else 0
    # The "passed" flag flips false on ANY CRITICAL miss. CRITICAL = the failures
    # that make a summary unsafe to publish: AI-tell formatting (em-dashes/lists),
    # missing primary-keyword placement, fabricated prices, or embedded schema.
    critical = {
        "no_em_dashes", "no_lists", "keyword_in_h2", "keyword_in_p1",
        "fact_grounding_prices", "no_faq_schema",
    }
    report.passed = all(report.checks.get(c, False) for c in critical)

    return report


def _qa_checks_four_part(
    draft: str,
    primary_keyword: str,
    locale: str,
    link_inventory: Iterable[str],
    excluded_path_segments: Iterable[str] = (),
    source_text: str = "",
) -> QaReport:
    """QA for the 4-part structure (tracker-096): Tagline (H2, 2-3 words) → Title
    (H3, carries the primary keyword) → Paragraph (lead block) → Content (H4/H5;
    the ONLY part with internal links). Structure-agnostic guards (em-dash, lists,
    grounding, schema, anchors, inventory, excluded-links) mirror the single-block
    set; the structure/keyword/link checks are 4-part specific.
    """
    from tools.summary.structure import parse_four_part

    report = QaReport(passed=True, score=100.0)
    primary_kw_lower = primary_keyword.lower().strip()
    body_text = re.sub(r"<[^>]+>", "", draft)
    word_count = len(re.findall(r"\b\w+\b", body_text))
    inventory = set(link_inventory)
    excluded = tuple(excluded_path_segments)
    source_digits = re.sub(r"[^\d]", "", source_text)
    parts = parse_four_part(draft)
    links = _LINK_RE.findall(draft)
    target_links = [url for _, url in links]

    # 1. No em dashes (agnostic).
    em_dash_count = sum(draft.count(ch) for ch in _EM_DASH_CHARS)
    report.add("no_em_dashes", em_dash_count == 0, f"found {em_dash_count} em-dash character(s)")

    # 2. No HTML list tags (agnostic).
    report.add("no_lists", _LIST_TAG_RE.search(draft) is None, "draft contains <ul>/<ol>/<li>")

    # 3. Heading order: exactly one H2 (tagline) + one H3 (title), no H1, H4/H5 only
    #    beyond, at least one H4 to open the Content section.
    h_levels = [len(m.group(1)) for m in _H_RE.finditer(draft)]
    heading_ok = (
        h_levels.count(2) == 1
        and h_levels.count(3) == 1
        and 1 not in h_levels
        and all(2 <= h <= 5 for h in h_levels)
        and any(h == 4 for h in h_levels)
    )
    report.add(
        "heading_order", heading_ok,
        f"heading levels {h_levels} (need one H2, one H3, >=1 H4, H4/H5 only)",
    )

    # tagline_word_count (CRITICAL): the Tagline is 2-3 words.
    tagline_words = len(parts.tagline.split())
    report.add(
        "tagline_word_count", 2 <= tagline_words <= 3,
        f"tagline has {tagline_words} word(s), need 2-3: {parts.tagline!r}",
    )

    # keyword_in_title (CRITICAL): primary keyword (topic) in the H3 Title.
    report.add(
        "keyword_in_title",
        _keyword_covered(primary_keyword, parts.title, locale),
        f"primary keyword {primary_keyword!r} (topic) not in title {parts.title!r}",
    )

    # keyword_in_paragraph (CRITICAL): keyword (topic) anywhere in the lead Paragraph.
    report.add(
        "keyword_in_paragraph",
        _keyword_covered(primary_keyword, parts.paragraph, locale),
        "primary keyword (topic) not found in the lead paragraph",
    )

    # content_starts_with_h4: the Content section opens with an H4.
    first_content_line = ""
    if parts.content_md.strip():
        first_content_line = parts.content_md.lstrip().splitlines()[0]
    report.add(
        "content_starts_with_h4",
        bool(re.match(r"^####\s+\S", first_content_line)),
        f"content does not start with an H4: {first_content_line[:60]!r}",
    )

    # links_only_in_content (CRITICAL): no links before the first H4.
    content_idx = draft.find("####")
    pre_content = draft[:content_idx] if content_idx >= 0 else draft
    links_before = _LINK_RE.findall(pre_content)
    report.add(
        "links_only_in_content", not links_before,
        f"links found outside the Content section: {[u for _, u in links_before]}",
    )

    # link_density: 2-5 per 1000 words, computed over the Content text only.
    content_body = re.sub(r"<[^>]+>", "", parts.content_md)
    content_words = len(re.findall(r"\b\w+\b", content_body))
    content_links = [u for _, u in _LINK_RE.findall(parts.content_md)]
    density = (len(content_links) / max(content_words, 1)) * 1000
    density_ok = _LINKS_PER_1000_LOW <= density <= _LINKS_PER_1000_HIGH or (
        content_words < 250 and len(content_links) <= _LINKS_PER_1000_HIGH
    )
    report.add(
        "link_density", density_ok,
        f"{len(content_links)} links in {content_words} content words ({density:.1f}/1000)",
    )

    # first_occurrence_only (agnostic).
    duplicate_targets = [u for u in target_links if target_links.count(u) > 1]
    report.add(
        "first_occurrence_only", not duplicate_targets,
        f"duplicate link targets: {sorted(set(duplicate_targets))}",
    )

    # no_excluded_links (agnostic).
    bad_segment_links = [u for u in target_links if any(_path_has_segment(u, seg) for seg in excluded)]
    report.add("no_excluded_links", not bad_segment_links, f"links to excluded segments: {bad_segment_links}")

    # keyword_density — topic present (content tokens) + not over-stuffed (<=2.0%).
    density_kw_ok, density_kw = _keyword_density_ok(primary_keyword, body_text, word_count, locale)
    report.add("keyword_density", density_kw_ok, f"density {density_kw * 100:.2f}% (keyword topic present + <=2.0% ceiling)")

    # 11. fact_grounding_prices — CRITICAL (agnostic).
    price_pct_tokens = re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%", draft)
    if source_text:
        unmatched_money = [
            t for t in price_pct_tokens
            if re.sub(r"[^\d]", "", t) and re.sub(r"[^\d]", "", t) not in source_digits
        ]
    else:
        unmatched_money = []
    report.add("fact_grounding_prices", not unmatched_money, f"prices/percentages not found in source: {unmatched_money}")

    # 12. fact_grounding_figures — WARNING (agnostic).
    if source_text:
        draft_for_figures = re.sub(r"\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%", " ", draft)
        figure_tokens = re.findall(r"\b(?:19|20)\d{2}\b|\b\d+\.\d+\b|\b\d{3,}\b", draft_for_figures)
        unmatched_figures = [t for t in figure_tokens if re.sub(r"[^\d]", "", t) not in source_digits]
    else:
        unmatched_figures = []
    report.add("fact_grounding_figures", not unmatched_figures, f"figures not found in source (review): {unmatched_figures}")

    # 13. near_duplicate — WARNING (agnostic).
    if source_text and word_count >= 40:
        draft_shingles = _word_shingles(body_text, 5)
        source_shingles = _word_shingles(source_text, 5)
        contained = (len(draft_shingles & source_shingles) / len(draft_shingles)) if draft_shingles else 0.0
        not_duplicate = contained <= 0.70
    else:
        contained = 0.0
        not_duplicate = True
    report.add("near_duplicate", not_duplicate, f"draft shingle-containment vs source {contained:.0%} (>70% = verbatim copy)")

    # 14. answer_first — WARNING. The Paragraph must open with a direct answer.
    first_sentence = re.split(r"(?<=[.!?])\s", parts.paragraph.strip(), maxsplit=1)[0] if parts.paragraph.strip() else ""
    answer_first = bool(first_sentence) and not _HEDGE_OPENER_RE.match(first_sentence)
    report.add("answer_first", answer_first, f"paragraph opens with a hedge/meta phrase: {first_sentence[:60]!r}")

    # 15. descriptive_anchors — WARNING (agnostic).
    link_anchors = [a for a, _ in links]
    bad_anchors = [a for a in link_anchors if len(a.split()) < 2 or a.strip().lower() in _GENERIC_ANCHORS]
    report.add("descriptive_anchors", not bad_anchors, f"non-descriptive anchors: {bad_anchors}")

    # 16. no_faq_schema — CRITICAL (agnostic).
    has_schema = bool(re.search(r"faqpage|application/ld\+json|<\s*script|<\s*iframe", draft, re.IGNORECASE))
    report.add("no_faq_schema", not has_schema, "draft contains schema/script/iframe markup (must be plain Markdown)")

    # 17. link_in_inventory — WARNING (agnostic).
    invented = [u for u in target_links if u not in inventory] if inventory else []
    report.add("link_in_inventory", not invented, f"link targets not in inventory (invented?): {invented}")

    scored = [report.checks[c] for c in _SCORED_CHECKS_FOUR_PART if c in report.checks]
    report.score = (sum(scored) / len(scored)) * 100 if scored else 0
    # CRITICAL set for 4-part: AI-tell formatting + the structure invariants the user
    # was explicit about (2-3 word tagline, Content starts with H4, links only in
    # Content) + keyword placement + fabricated prices + embedded schema.
    # content_starts_with_h4 is critical because it guarantees a non-empty Content
    # part — without it a summary could ship with an empty RichText `summary` field.
    critical = {
        "no_em_dashes", "no_lists", "keyword_in_title", "keyword_in_paragraph",
        "fact_grounding_prices", "no_faq_schema", "tagline_word_count",
        "links_only_in_content", "content_starts_with_h4",
    }
    report.passed = all(report.checks.get(c, False) for c in critical)

    return report


# Internal helpers


def _norm_match(s: str) -> str:
    """Lowercase + collapse every run of non-word characters (punctuation, hyphens,
    apostrophes, whitespace) to a single space. Unicode-aware, so accented letters
    survive. Used to compare a derived keyword against generated text tolerant of
    punctuation/spacing differences ("est-elle" ~ "est elle", "d'anglais" ~ "d anglais")."""
    return re.sub(r"[^\w]+", " ", s.lower(), flags=re.UNICODE).strip()


def _content_tokens(keyword: str, locale: str) -> list[str]:
    """Content tokens of `keyword`: normalized tokens that are >= 3 chars and not a
    locale stopword. Falls back to all tokens if the keyword is entirely function
    words. Lazy import of the locale stopword sets mirrors the existing lazy-import
    pattern (no import-time coupling)."""
    from tools.summary.keyword_extractor import _LOCALE_STOPWORDS, _STOPWORDS

    stop = _LOCALE_STOPWORDS.get(locale, _STOPWORDS)
    toks = _norm_match(keyword).split()
    content = [t for t in toks if len(t) >= 3 and t not in stop]
    return content or toks


def _keyword_covered(keyword: str, text: str, locale: str) -> bool:
    """True if every content token of `keyword` appears as a token of `text`.

    tracker-097 follow-up: the QA gate used to require the keyword as a VERBATIM
    substring, but a generative model reorders, inserts words into, and re-punctuates
    the derived keyword (derives "anglais étudier", writes "anglais ... pour étudier";
    derives "séjour linguistique", writes "séjour-linguistique"). The verbatim check
    false-failed every such case → blog summaries demoted en masse. Matching on
    content-token presence confirms the keyword's TOPIC is in the text, which is what
    the placement checks actually care about, while staying accent/punctuation tolerant.
    """
    if not keyword.strip():
        return False
    text_tokens = set(_norm_match(text).split())
    for t in _content_tokens(keyword, locale):
        if t in text_tokens:
            continue
        # Tolerate suffix-ADDITION inflection: one token is a prefix of the other
        # (both >= 4 chars), so "learn"~"learning", "étudier"~"étudie", "kurs"~"kurse".
        if len(t) >= 4 and any(
            len(w) >= 4 and (w.startswith(t) or t.startswith(w)) for w in text_tokens
        ):
            continue
        # Tolerate suffix-SUBSTITUTION inflection via a long shared stem, e.g. German
        # "überraschen"~"überrascht" (stem "überrasch"). Conservative: shared prefix
        # >= 6 chars AND >= 60% of the shorter token, so "inter"(5) won't collide.
        if len(t) >= 6 and any(
            len(w) >= 6
            and _shared_prefix_len(t, w) >= 6
            and _shared_prefix_len(t, w) >= 0.6 * min(len(t), len(w))
            for w in text_tokens
        ):
            continue
        return False
    return True


def _shared_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _keyword_density_ok(
    keyword: str, body_text: str, word_count: int, locale: str
) -> tuple[bool, float]:
    """Paraphrase-tolerant density check. Floor = the keyword's topic is present
    (its content tokens appear in the body); ceiling = the exact phrase is not
    over-repeated (anti-stuffing, the 2.0% cap). Returns (ok, phrase_density).

    The old `phrase_count / word_count` floor structurally false-failed multi-word
    keywords (a long exact phrase appears ~once → density < 0.3%) and paraphrased
    keywords (phrase absent → 0%). Topic-presence is the right floor: a keyword
    derived FROM the page, whose content words are in the summary, is on-topic.
    """
    if word_count <= 0 or not keyword.strip():
        return False, 0.0
    hits = _norm_match(body_text).count(_norm_match(keyword))
    density = hits / word_count
    present = _keyword_covered(keyword, body_text, locale)
    return (present and density <= _DENSITY_HIGH), density


def _first_paragraph_under_h2(draft: str) -> str:
    """Return the first non-empty line block after the H2 (or empty string)."""
    lines = draft.splitlines()
    in_p1 = False
    p1: list[str] = []
    for line in lines:
        m = _H_RE.match(line)
        if m and len(m.group(1)) == 2:
            in_p1 = True
            continue
        if not in_p1:
            continue
        if m and len(m.group(1)) >= 3:
            # Hit the next heading; stop.
            break
        if line.strip():
            p1.append(line.strip())
        elif p1:
            # Blank line after we've collected something — end of P1.
            break
    return " ".join(p1)


def _path_has_segment(url: str, segment: str) -> bool:
    import urllib.parse

    parts = urllib.parse.urlparse(url).path.strip("/").split("/")
    return segment in parts


def _word_shingles(text: str, n: int) -> set[tuple[str, ...]]:
    """Return the set of lowercase word n-grams in `text` (for near-duplicate detection)."""
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def boilerplate_pairs(
    texts: dict[str, str], threshold: float = 0.80
) -> list[tuple[str, str, float]]:
    """Find pairs of summaries that are near-duplicates of EACH OTHER.

    Templated boilerplate repeated across pages is the scaled-content-abuse
    footprint Google's March-2024 policy targets (tracker-092 1.3). Returns
    `(id_a, id_b, overlap)` for pairs whose mutual 5-gram shingle overlap
    (intersection / smaller-set size) exceeds `threshold`. Non-blocking — the
    caller surfaces these as warnings.
    """
    shingles = {
        cid: _word_shingles(re.sub(r"<[^>]+>", "", t), 5) for cid, t in texts.items()
    }
    ids = list(shingles)
    out: list[tuple[str, str, float]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = shingles[ids[i]], shingles[ids[j]]
            if not a or not b:
                continue
            overlap = len(a & b) / min(len(a), len(b))
            if overlap > threshold:
                out.append((ids[i], ids[j], round(overlap, 2)))
    return out
