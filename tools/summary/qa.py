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
    """
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
    kw_in_h2 = any(primary_kw_lower in h2.lower() for h2 in h2_lines) if h2_lines else False
    report.add(
        "keyword_in_h2",
        kw_in_h2,
        f"primary keyword {primary_keyword!r} not found in any H2 ({h2_lines})",
    )

    # 8. Primary keyword in first 120 chars of P1 (under the H2).
    p1_text = _first_paragraph_under_h2(draft)
    kw_in_p1 = primary_kw_lower in p1_text[:_KEYWORD_P1_WINDOW_CHARS].lower()
    report.add(
        "keyword_in_p1",
        kw_in_p1,
        f"primary keyword not in first {_KEYWORD_P1_WINDOW_CHARS} chars of P1",
    )

    # 9. Primary keyword in ≥1 H3.
    h3_lines = [m.group(2) for m in _H_RE.finditer(draft) if len(m.group(1)) == 3]
    kw_in_h3 = any(primary_kw_lower in h3.lower() for h3 in h3_lines)
    report.add(
        "keyword_in_h3",
        kw_in_h3 or not h3_lines,  # If no H3s, this check passes vacuously.
        f"no H3 contains primary keyword (H3 lines: {len(h3_lines)})",
    )

    # 10. Body density 0.3–2.0%.
    if word_count > 0:
        hits = body_text.lower().count(primary_kw_lower)
        density = hits / word_count
        in_density_range = _DENSITY_LOW <= density <= _DENSITY_HIGH
    else:
        density = 0.0
        in_density_range = False
    report.add(
        "keyword_density",
        in_density_range,
        f"density {density * 100:.2f}% (target 0.3–2.0%)",
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


# Internal helpers


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
