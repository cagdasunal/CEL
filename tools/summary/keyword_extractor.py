"""Derive a KeywordPlan from page content per /page-summary skill Phase 2.5.

Public API: `derive_keywords(title, h1, url, body_text) -> KeywordPlan`.

Algorithm (from `.claude/skills/page-summary/SKILL.md`):
  1. Candidate A = page title minus brand suffix
  2. Candidate B = H1
  3. Candidate C = URL slug rendered as natural language
  4. Primary = longest phrase common to ≥ 2 of {A, B, C}; fallback to B
  5. Secondary = body-frequency top words (≥ 3 hits, non-stopword) + heading tokens
  6. Entities = matches against a static allowlist
"""
from __future__ import annotations

import collections
import re
import urllib.parse
from dataclasses import dataclass

from tools.summary.prompt_builder import KeywordPlan


# Static entity allowlist (CEL-specific). First mention spells full name + abbreviation.
_ENTITY_TERMS = (
    "CEFR", "A1", "A2", "B1", "B2", "C1", "C2",
    "IELTS", "TOEFL iBT", "TOEFL",
    "Cambridge English", "FCE", "CAE", "B2 First",
    "PGWPP", "DLI", "GIC",
    "ACCET", "CEA", "Languages Canada",
    "San Diego", "Los Angeles", "Vancouver",
    "California", "British Columbia",
)

# Stop-words for body frequency (lower-case).
_STOPWORDS = frozenset(
    """
    the a an and or but if when where why how what who which that this these those
    is are was were be been being have has had do does did can will would should
    could may might must shall to from in on at by for with of as into onto upon
    over under above below than then so just only also even still already yet
    not no nor never very more most much many such other some any all every each
    you your yours their them they our we us i me my him her his she he it its
    """.split()
)

# Brand suffix patterns to strip from titles.
_BRAND_SUFFIX_RE = re.compile(
    r"\s*[\|\-–—]\s*(CEL|College of English Language).*$", re.IGNORECASE
)


def derive_keywords(
    title: str, h1: str, url: str, body_text: str = ""
) -> KeywordPlan:
    """Derive a KeywordPlan per /page-summary Phase 2.5."""
    candidate_a = _strip_brand(title)
    candidate_b = _strip_brand(h1)
    candidate_c = _slug_to_phrase(url)

    primary = _longest_common_phrase([candidate_a, candidate_b, candidate_c])
    if not primary:
        primary = candidate_b or candidate_a or candidate_c or "english school"
    primary = primary.strip().lower()

    # Secondary keywords: body frequency + heading tokens.
    secondaries = _body_frequency_terms(body_text, exclude=primary, limit=5)

    # Entity terms found in the page.
    entities = tuple(
        e for e in _ENTITY_TERMS if e.lower() in (title + " " + h1 + " " + body_text).lower()
    )

    return KeywordPlan(
        primary=primary,
        secondaries=tuple(secondaries),
        entities=entities,
    )


# ---- Internal helpers ----


def _strip_brand(text: str) -> str:
    """Remove `| CEL` or `| College of English Language` suffix patterns."""
    if not text:
        return ""
    cleaned = _BRAND_SUFFIX_RE.sub("", text).strip()
    return cleaned


def _slug_to_phrase(url: str) -> str:
    """Render a URL slug as natural language. /vancouver/how-long-to-learn-english → 'how long to learn english in vancouver'."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return ""
    # Strip locale prefix if present.
    if parts[0] in {"de", "fr", "es", "it", "pt", "ko", "ja", "ar"}:
        parts = parts[1:]
    if not parts:
        return ""
    # Last segment is the "topic"; earlier segments are context.
    topic = parts[-1].replace("-", " ").replace("_", " ").strip()
    context_segments = [p.replace("-", " ").replace("_", " ") for p in parts[:-1]]
    if context_segments:
        return f"{topic} in {' '.join(context_segments)}"
    return topic


def _longest_common_phrase(candidates: list[str]) -> str:
    """Find the longest phrase common to ≥ 2 of the candidate strings.

    A 'phrase' is a contiguous run of 2+ lowercase tokens. Returns "" if no common
    phrase. Single-token overlaps are ignored.
    """
    cleaned = [c.lower().strip() for c in candidates if c and c.strip()]
    if len(cleaned) < 2:
        return ""
    # Build all 2-to-N gram sets per candidate.
    grams_per_candidate: list[set[str]] = []
    for c in cleaned:
        tokens = re.findall(r"[a-z0-9]+", c)
        grams: set[str] = set()
        for n in range(2, min(len(tokens), 8) + 1):
            for i in range(len(tokens) - n + 1):
                grams.add(" ".join(tokens[i : i + n]))
        grams_per_candidate.append(grams)
    # Find grams present in ≥ 2 candidates.
    common: set[str] = set()
    for i, g_i in enumerate(grams_per_candidate):
        for j, g_j in enumerate(grams_per_candidate):
            if i >= j:
                continue
            common |= g_i & g_j
    if not common:
        return ""
    # Longest by word count.
    return max(common, key=lambda g: (len(g.split()), len(g)))


def _body_frequency_terms(body_text: str, exclude: str, limit: int = 5) -> list[str]:
    """Top non-stopword tokens by frequency in body, excluding the primary keyword's tokens."""
    if not body_text:
        return []
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", body_text.lower())
    exclude_tokens = set(re.findall(r"[a-z]+", exclude.lower()))
    counts = collections.Counter(
        t for t in tokens if t not in _STOPWORDS and t not in exclude_tokens
    )
    # Filter to terms appearing ≥ 3 times.
    common = [w for w, c in counts.most_common() if c >= 3]
    return common[:limit]
