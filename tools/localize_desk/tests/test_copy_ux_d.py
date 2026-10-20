"""CEL-093 (desk UX fixes D), the words: v2 has no Approve, so no line a reviewer reads about a text the export
refused tells them to approve anything; each says what they can do (edit, undo, export again). The Re-translate
window names the same two kinds of text in its body and in its count.

The wording comes from COPY.md; what is pinned here is the vocabulary, per row, so a later edit of a row cannot bring
"approve" back unseen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import copy_text as C  # noqa: E402

ROWS = C.load()
REFUSAL = {k: v for k, v in ROWS.items() if k.startswith("refusal.")}

# The rows that tell the reviewer what to do, and the words they now say it with.
ACT = {
    "refusal.CLIENT-RULE": "Edit it, then export it again;",
    "refusal.NUMBER-PARITY": "then export it again.",
    "refusal.META-BUDGET": "Shorten it, then export it again.",
    "refusal.POISON": "Check it, then export it again.",
    "refusal.EMPTY-TARGET": "Write one, or undo your edit.",
    "refusal.CSV-INJECTION": "Change how it starts, then export it again.",
    "refusal.PLACEHOLDER-SET": "then export it again.",
    "refusal.PLACEHOLDER-ORDER": "Edit it, then export it again.",
    "refusal.PLACEHOLDER-BALANCE": "Edit it, then export it again.",
    "refusal.OG-TWIN-MISSING": "Export both, with the same words.",
    "refusal.OG-TWIN-DIVERGED": "then export both again.",
    "refusal.UNSIGNED": "Export it again.",
    "refusal.BAD-SIGNATURE": "Export it again.",
    "refusal.UNREGISTERED": "Export it again.",
    "refusal.OVERRIDE-UNNAMED": "Export it again.",
    "refusal.EXPORT-SKIP-APPROVED-AGAINST-AN-UNKNOWN-WORDING": "Export it again.",
    "refusal.EXPORT-SKIP-NOTHING-TO-SAY": "Write one, or undo your edit.",
}
# The rows that say what happened to a text the reviewer exported.
HAPPENED = {
    "refusal.UNIT-MISMATCH": "The English changed after it was exported.",
    "refusal.ENGLISH-DRIFT": "The English changed after it was exported.",
    "refusal.EXPORT-SKIP-TRANSLATION-MOVED-SINCE-APPROVAL": "changed after it was exported.",
    "refusal.DUPLICATE": "The same text was exported twice",
    "refusal.LANG-MISMATCH": "It was exported in another language's list.",
    "refusal.NO-VERIFIER": "The exported texts couldn't be checked",
    "refusal.EXPORT-SKIP-NOT-APPROVED": "Not exported, so it isn't in the file.",
}


def test_no_line_about_a_refused_text_mentions_approving():
    """The 24 rows that did (CEL-075 Found 3): every key is still here, none of their texts says approve."""
    assert len(REFUSAL) >= 50, "the refusal rows are gone?"
    said = sorted(k for k, v in REFUSAL.items() if re.search(r"approv", v, re.I))
    assert not said, said


@pytest.mark.parametrize("key,words", sorted(ACT.items()))
def test_a_line_that_tells_the_reviewer_to_act_says_what_they_can_do(key, words):
    assert words in REFUSAL[key], (key, REFUSAL[key])


@pytest.mark.parametrize("key,words", sorted(HAPPENED.items()))
def test_a_line_about_what_happened_says_exported(key, words):
    assert words in REFUSAL[key], (key, REFUSAL[key])


def test_the_retranslate_count_names_the_same_texts_as_its_body():
    """`retr.page.body` says Gemini keeps the texts you have edited or exported; the count under the box, once it is
    ticked, says how many of those Gemini's wording replaces."""
    kinds = "edited or exported"
    assert kinds in C.t("retr.page.body")
    for key in ("retr.page.count.one", "retr.page.count.other"):
        assert kinds in ROWS[key] and "approv" not in ROWS[key].lower(), (key, ROWS[key])
    assert C.tn("retr.page.count", 2) == "Gemini's new wording replaces 2 texts you edited or exported."
