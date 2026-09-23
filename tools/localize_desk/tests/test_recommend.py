"""Tests for the desk's recommendation checks.

Almost every case here is a FALSE POSITIVE that the first version produced on the real
corpus. The first run flagged 1,391 of 7,920 rows (17.6%) and was wrong on roughly
1,284 of them; the version these tests pin flags 379 (4.8%). That gap is the whole
value of the feature — a recommender that cries wolf spends the reviewer's attention,
which is the one thing this project exists to save.

So the bar for a check is precision, and these tests are mostly proof that it stays
quiet when it should.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk.recommend import (  # noqa: E402
    LEVEL_CHECK,
    LEVEL_FINE,
    _digits,
    recommend,
)


class TestDigits:
    """Digit-group separators differ per locale; changed numbers do not."""

    @pytest.mark.parametrize("text,expected", [
        ("C$3,368", ["3368"]),          # English thousands
        ("3.368 C$", ["3368"]),         # German thousands
        ("C$2'850", ["2850"]),          # Swiss apostrophe — seen live in the de corpus
        ("C$2’850", ["2850"]),     # …and its typographic apostrophe
        ("5 090", ["5090"]),            # French space
        ("13–19 Weeks", ["13", "19"]),
        ("", []),
    ])
    def test_separators_are_normalised(self, text, expected):
        assert _digits(text) == expected

    def test_a_comma_before_a_space_is_not_a_group_separator(self):
        """The bug that made every date look like a changed number.

        A greedy [.,space] run joined "21, 2026" into one token, so the German
        "21. August 2026" (which splits it) never matched.
        """
        assert _digits("June 22 –August 21, 2026") == ["22", "21", "2026"]
        assert _digits("22. Juni – 21. August 2026") == ["22", "21", "2026"]


class TestQuietWhenItShouldBe:
    def test_localised_price_is_not_a_changed_number(self):
        assert recommend("Only C$3,368 instead of C$5,090",
                         "Nur 3.368 C$ statt 5.090 C$", "de")[0] == LEVEL_FINE

    def test_date_reordering_is_not_a_changed_number(self):
        assert recommend("June 22 – August 21, 2026",
                         "22. Juni – 21. August 2026", "de")[0] == LEVEL_FINE

    def test_an_address_identical_in_both_is_fine(self):
        """Seen live: '401 Wilshire Boulevard #200, Santa Monica, CA 90401 USA'.

        Identical text is not evidence of a missing translation when there is no
        English in it to translate.
        """
        addr = "401 Wilshire Boulevard #200, Santa Monica, CA 90401 USA"
        assert recommend(addr, addr, "de")[0] == LEVEL_FINE

    def test_a_non_english_source_identical_to_its_target_is_fine(self):
        """Seen live: German blog titles whose 'source' is already German.

        Their correct German 'translation' is the same string, and flagging that as
        untranslated was the single biggest false-positive source.
        """
        de = "5 Dinge, die Studenten in Vancouver überraschen"
        assert recommend(de, de, "de")[0] == LEVEL_FINE

    def test_a_short_identical_string_is_fine(self):
        assert recommend("CEL Vancouver", "CEL Vancouver", "de")[0] == LEVEL_FINE

    def test_german_lowercase_sie_is_not_the_formal_address(self):
        # "sie" = she/they. Only the capitalised form mid-sentence is the formal one.
        assert recommend("They learn quickly", "Schnell lernen sie Englisch", "de")[0] == LEVEL_FINE

    def test_a_locale_with_no_register_rule_is_not_checked(self):
        assert recommend("Learn English", "Sie Sie Sie", "ja")[0] == LEVEL_FINE


class TestFlagsRealDefects:
    def test_untranslated_english_is_flagged(self):
        en = "5 Things That Surprise Students About Living in Vancouver"
        level, why = recommend(en, en, "de")
        assert level == LEVEL_CHECK
        assert "English" in why

    def test_empty_target_is_flagged(self):
        level, why = recommend("Anything at all here", "   ", "de")
        assert level == LEVEL_CHECK
        assert "nothing" in why

    def test_a_dropped_number_is_flagged(self):
        level, why = recommend("An additional C$35 per week applies",
                               "Es kommt ein Zuschlag pro Woche hinzu", "de")
        assert level == LEVEL_CHECK
        assert "35" in why

    def test_a_duplicated_link_placeholder_is_flagged(self):
        """Seen live in ja: two distinct anchors collapsed into wg-1 twice.

        The imported row would lose a link silently, which is exactly the class of
        defect a human will not spot by reading.
        """
        src = '<a wg-1="">+1 604 685 0291</a><a wg-2="">Get Directions</a>'
        tgt = '<a wg-1="">+1 604 685 0291</a><a wg-1="">アクセス</a>'
        level, why = recommend(src, tgt, "ja")
        assert level == LEVEL_CHECK
        assert "placeholder" in why

    def test_german_formal_address_is_flagged(self):
        level, why = recommend("Learn English in Vancouver at our campus.",
                               "Lernen Sie Englisch in Vancouver an unserem Campus.", "de")
        assert level == LEVEL_CHECK
        assert "informal" in why

    def test_spanish_usted_is_flagged(self):
        level, why = recommend("You can study here", "Usted puede estudiar aquí", "es")
        assert level == LEVEL_CHECK
        assert "usted" in why.lower()


class TestContract:
    def test_fine_carries_no_reason(self):
        assert recommend("Hello there friend", "Hallo mein Freund", "de") == (LEVEL_FINE, "")

    def test_check_always_carries_a_reason(self):
        level, why = recommend("Anything at all here", "", "de")
        assert level == LEVEL_CHECK and why

    def test_it_never_proposes_a_replacement(self):
        """The operator's constraint: recommendations guide, they do not act.

        The return type is (level, reason) and there is nowhere for a suggested
        translation to live — which is the point.
        """
        result = recommend("Learn English", "Lernen Sie Englisch", "de")
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(x, str) for x in result)
