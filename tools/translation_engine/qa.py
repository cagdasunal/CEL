"""Translation QA — cheap, high-value checks on LLM translation output.

Reimplements pofilter-style logic (translate-toolkit is GPL + heavy; we borrow
the check list, not the dependency). Split by severity:

  BLOCKING (ok=False): placeholder/variable set mismatch, number/URL drift.
    These break runtime or factual correctness — never ship.
  WARNING (ok stays True, flag recorded): untranslated passthrough, length-ratio
    out of band. Surfaced for review, not auto-blocked.

`check_translation(source, target, locale)` returns (ok, flags).
"""
from __future__ import annotations

import re

# {var}, {{var}}, %s, %(name)s, <tag> — runtime placeholders that MUST survive.
_PLACEHOLDER_RE = re.compile(r"\{\{?[^}]*\}?\}|%\([^)]+\)[sd]|%[sd]|<[^>]+>")
_NUMBER_RE = re.compile(r"\d[\d,.]*")
_URL_RE = re.compile(r"https?://[^\s)]+")

# Per-locale acceptable target/source character-length ratio band. CJK + Arabic
# render shorter; German/long-form locales render longer.
_LENGTH_BAND = {
    "de": (0.7, 2.6), "fr": (0.7, 2.4), "es": (0.7, 2.4), "it": (0.7, 2.4),
    "pt": (0.7, 2.4), "ar": (0.4, 1.8), "ko": (0.3, 1.6), "ja": (0.3, 1.6),
}
_DEFAULT_BAND = (0.5, 2.5)


def _multiset(matches: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in matches:
        out[m] = out.get(m, 0) + 1
    return out


def check_translation(source: str, target: str, locale: str) -> tuple[bool, list[str]]:
    """Run translation QA. Returns (ok, flags). ok=False on any BLOCKING failure."""
    flags: list[str] = []
    ok = True

    if not target.strip():
        return False, ["empty_translation"]

    # BLOCKING — placeholder/variable set must match exactly.
    src_ph = _multiset(_PLACEHOLDER_RE.findall(source))
    tgt_ph = _multiset(_PLACEHOLDER_RE.findall(target))
    if src_ph != tgt_ph:
        ok = False
        flags.append(f"placeholder_mismatch:src={sorted(src_ph)}|tgt={sorted(tgt_ph)}")

    # BLOCKING — every number in source must appear in target (digit-normalized).
    src_nums = {re.sub(r"[^\d]", "", n) for n in _NUMBER_RE.findall(source) if re.sub(r"[^\d]", "", n)}
    tgt_digits = re.sub(r"[^\d]", "", target)
    missing_nums = sorted(n for n in src_nums if n not in tgt_digits)
    if missing_nums:
        ok = False
        flags.append(f"number_drift:{missing_nums}")

    # BLOCKING — every URL in source must appear verbatim in target.
    src_urls = set(_URL_RE.findall(source))
    missing_urls = sorted(u for u in src_urls if u not in target)
    if missing_urls:
        ok = False
        flags.append(f"url_drift:{missing_urls}")

    # WARNING — untranslated passthrough (target byte-identical to source).
    if source.strip() and target.strip() == source.strip():
        flags.append("untranslated_passthrough")

    # WARNING — length ratio out of the locale band.
    lo, hi = _LENGTH_BAND.get(locale, _DEFAULT_BAND)
    if source.strip():
        ratio = len(target) / max(len(source), 1)
        if not (lo <= ratio <= hi):
            flags.append(f"length_ratio:{ratio:.2f}")

    return ok, flags
