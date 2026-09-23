"""Recommendations for the Localization Desk — guidance, never an action.

Basecamp #451. Operator, 2026-09-23:

    "the recommendations work something like that: Better to re-translate or it might
     be approved. i mean just for guide user. It should not execute anything. No need
     to spend Gemini tokens that much by translating them."

So this module answers one question per row — *should the reviewer look harder at this
one?* — and nothing else. It does not translate, it does not decide, it does not call
an API. It runs at page-build time, so it costs nothing at all and the reviewer's
browser does no work.

PRECISION OVER RECALL
---------------------
The product is the reviewer's attention. A false "needs attention" spends it on a row
that was fine, which is the exact cost this whole project exists to remove — so a check
only ships if it is nearly always right. Anything merely suspicious is left to the
reviewer's eye, or later to a cheap Flash pass on the rows these checks clear.

That is why, for example, the number check strips digit-group separators before
comparing: German writes C$3,368 as 3.368 C$, and a naive comparison would flag every
price on the site. A check that cries wolf on a correct translation is worse than no
check.
"""
from __future__ import annotations

import re
import unicodedata

# A recommendation is (level, reason). Levels, worst first — the desk sorts on this.
LEVEL_CHECK = "check"   # a concrete, near-certain defect
LEVEL_FINE = "fine"     # nothing detected; not a promise that it is good

# A digit-group separator is only a separator when exactly three more digits
# follow ("3,368", "3.368", "5 090"). Letting any run of [.,space] join digits
# merged "21, 2026" into one token, so "21. August 2026" read as a changed number
# -- a false alarm on every date in the corpus.
_DIGIT_RUN = re.compile("\\d+(?:[.,'\u2019\u00a0\u202f ]\\d{3}(?!\\d))*(?:[.,]\\d+)?")
_ANCHOR = re.compile(r"<a wg-(\d+)=\"\">")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# Forms of address the client's per-language rules forbid (their guidelines §7.1-7.5).
# Matched as whole words, case-sensitively where case is what distinguishes them:
# German lowercase "sie" is "she/they" and is perfectly fine; capital "Sie" mid-
# sentence is the formal address. Italian "Lei" likewise.
#
# The client's rule is NOT "informal everywhere", and this table used to assume it
# was: French is always *vous* ("never tu, even though Weglot defaults to tu") and had
# no check at all, while Spanish flagged *ustedes*, which the client names as the
# correct plural. Each message now says what the client actually asks for.
# Measured 2026-09-23 on the live French render: all 6 tu/toi hits are real.
_FORMAL = {
    "de": (re.compile(r"(?<![.!?]\s)(?<!^)\b(Sie|Ihnen|Ihre[mnrs]?|Ihr)\b"),
           "formal Sie-Anrede — the client's rules ask for du"),
    "es": (re.compile(r"\busted\b", re.IGNORECASE),
           "formal usted — the client's rules ask for tú (plural ustedes is right)"),
    "it": (re.compile(r"(?<![.!?]\s)(?<!^)\bLei\b"),
           "formal Lei — the client's rules ask for tu"),
    "fr": (re.compile(r"\b(tu|toi)\b|\bt['’](?=[a-zàâéèêëîïôûùüç])", re.IGNORECASE),
           "informal tu — the client's rules ask for vous"),
    "pt": (re.compile(r"\b(o senhor|a senhora|os senhores|as senhoras)\b", re.IGNORECASE),
           "formal o senhor / a senhora — the client's rules ask for você"),
}


def _digits(text: str) -> list[str]:
    """Digit groups with separators removed, in order.

    "C$3,368" -> ["3368"];  "3.368 C$" -> ["3368"];  "13-19" -> ["13", "19"].
    Comparing these rather than the raw text is what stops every correctly-localised
    price from being reported as a changed number.
    """
    out = []
    for run in _DIGIT_RUN.findall(text or ""):
        cleaned = re.sub("[.,'\u2019\u00a0\u202f ]", "", run)
        if cleaned:
            out.append(cleaned)
    return out


# Function words that are overwhelmingly English. A German or Spanish sentence does
# not contain "the/and/of/for/your"; an address or a product name does not either.
_EN_STOPWORDS = frozenset("""
the and for you your our with from that this what how much does are can will
into their they them when where which who why about after before between
""".split())


def _looks_untranslated(source: str, target: str) -> bool:
    """The target is the untouched English source.

    Identical text is NOT enough on its own, and assuming it was cost this check its
    credibility on the first run: of 1,284 hits, almost all were addresses
    ("401 Wilshire Boulevard #200, Santa Monica, CA 90401 USA"), proper nouns, or
    units whose source is not English at all (German blog titles, which are correctly
    identical to their German "translation").

    So identity must be corroborated by the source actually reading as English --
    at least two unmistakable English function words.
    """
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s or "").casefold()
        return " ".join(s.split())
    words = [w.casefold() for w in _WORD.findall(source or "")]
    if len(words) < 3:
        return False
    if norm(source) != norm(target):
        return False
    return sum(1 for w in words if w in _EN_STOPWORDS) >= 2


def recommend(source: str, target: str, locale: str) -> tuple[str, str]:
    """Return (level, reason). reason is "" when level is LEVEL_FINE.

    Checks are ordered by how actionable they are, and the first hit wins: a reviewer
    needs one clear reason to look, not four.
    """
    target = target or ""
    source = source or ""

    if not target.strip():
        return LEVEL_CHECK, "nothing translated"

    if _looks_untranslated(source, target):
        return LEVEL_CHECK, "still in English"

    # Anchor placeholders are how Weglot re-attaches links. A dropped one means the
    # imported row would render without its link, silently.
    src_anchors = sorted(_ANCHOR.findall(source))
    tgt_anchors = sorted(_ANCHOR.findall(target))
    if src_anchors != tgt_anchors:
        return LEVEL_CHECK, "link placeholder missing or changed"

    src_digits, tgt_digits = _digits(source), _digits(target)
    if sorted(src_digits) != sorted(tgt_digits):
        missing = [d for d in src_digits if d not in tgt_digits]
        if missing:
            return LEVEL_CHECK, f"number changed or dropped ({', '.join(missing[:3])})"
        return LEVEL_CHECK, "numbers do not match the source"

    formal = _FORMAL.get(locale)
    if formal and formal[0].search(target):
        return LEVEL_CHECK, formal[1]

    return LEVEL_FINE, ""
