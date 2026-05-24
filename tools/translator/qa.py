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
import unicodedata

# {var}, {{var}}, %s, %(name)s, <tag> — runtime placeholders that MUST survive.
_PLACEHOLDER_RE = re.compile(r"\{\{?[^}]*\}?\}|%\([^)]+\)[sd]|%[sd]|<[^>]+>")
_NUMBER_RE = re.compile(r"\d[\d,.]*")
_URL_RE = re.compile(r"https?://[^\s)]+")


def _to_ascii_digits(s: str) -> str:
    """Fold any Unicode decimal digit (Arabic-Indic ٠-٩, fullwidth ０-９, …) to
    its ASCII value so number-preservation comparison works for non-Latin
    locales. Non-digit characters pass through unchanged. (tracker-095 M3 — a
    model that localizes numerals for `ar` must not trip number_drift.)
    """
    out = []
    for ch in s:
        d = unicodedata.digit(ch, None)
        out.append(str(d) if d is not None else ch)
    return "".join(out)

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


def check_translation(
    source: str, target: str, locale: str, *, check_urls: bool = True
) -> tuple[bool, list[str]]:
    """Run translation QA. Returns (ok, flags). ok=False on any BLOCKING failure.

    `check_urls`: when False, skip the URL-preservation check. The summary caller
    emits per-block PLAIN TEXT (links collapsed to their anchor text by
    `structure.summary_page_blocks`; the localized hrefs are applied by Weglot's
    URL-translation rules on the live page, NOT carried in the CSV — audit-108 M-4,
    2026-05-24). So source URLs are EXPECTED to be absent from the target and
    url_drift would false-flag every linked block. Meta-tag translation has no
    links, so it keeps the default True.
    """
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

    # BLOCKING — every number in source must appear in target (digit-normalized,
    # Unicode→ASCII folded so localized numerals for ar/etc. still match).
    src_ascii = _to_ascii_digits(source)
    tgt_digits = re.sub(r"[^0-9]", "", _to_ascii_digits(target))
    src_nums = {re.sub(r"[^0-9]", "", n) for n in _NUMBER_RE.findall(src_ascii) if re.sub(r"[^0-9]", "", n)}
    missing_nums = sorted(n for n in src_nums if n not in tgt_digits)
    if missing_nums:
        ok = False
        flags.append(f"number_drift:{missing_nums}")

    # BLOCKING — every URL in source must appear verbatim in target (unless the
    # caller swaps links, in which case check_urls=False).
    if check_urls:
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
