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
) -> QaReport:
    """Run all rule checks on a draft. Returns a QaReport with per-check pass/fail.

    A draft is Markdown-formatted text (rich-text Summary section). The check
    set mirrors the locked rules in `.claude/skills/page-summary/SKILL.md` Phase 7.
    """
    report = QaReport(passed=True, score=100.0)
    primary_kw_lower = primary_keyword.lower().strip()
    body_text = re.sub(r"<[^>]+>", "", draft)
    word_count = len(re.findall(r"\b\w+\b", body_text))
    inventory = set(link_inventory)
    excluded = tuple(excluded_path_segments)

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

    # Aggregate score (10 checks, 10 points each).
    passes = sum(1 for ok in report.checks.values() if ok)
    report.score = (passes / len(report.checks)) * 100 if report.checks else 0
    # The "passed" flag flips false on ANY CRITICAL miss (em-dashes, lists, H2 kw, P1 kw).
    critical = {"no_em_dashes", "no_lists", "keyword_in_h2", "keyword_in_p1"}
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
