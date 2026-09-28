"""Tests for tools.summary.prompt_builder — system-prompt assembly + user-message format."""

import json
import re

import pytest

from tools.summary.prompt_builder import (
    KeywordPlan,
    SourceItem,
    build_link_insertion_system_prompt,
    build_link_insertion_user_message,
    build_system_prompt,
    build_translation_system_prompt,
    build_translation_user_message,
    build_user_message,
)


def test_link_insertion_system_prompt_is_focused_and_preserve_first():
    blocks = build_link_insertion_system_prompt()
    assert len(blocks) == 1  # the single focused link_insertion.md layer (cheap for Flash)
    text = blocks[0]["text"].lower()
    assert "preserve" in text and "do not" in text  # text-preservation is the hard rule
    assert "englishcollege.com" in text  # the www domain rule
    assert "same locale" in text


def test_link_insertion_user_message_carries_summary_candidates_and_locale():
    msg = build_link_insertion_user_message(
        "## Title\n\nSome existing summary text about studying in Vancouver.",
        [
            "https://www.englishcollege.com/vancouver",
            "https://www.englishcollege.com/courses",
        ],
        "de",
        post_title="Mein Beitrag",
    )
    assert "Some existing summary text about studying in Vancouver." in msg
    assert "https://www.englishcollege.com/vancouver" in msg
    assert "de" in msg
    assert "Mein Beitrag" in msg
    # The task tells the model to change no words.
    assert "change no words" in msg.lower()


def test_system_prompt_three_blocks_present():
    """Tracker-091: blocks are plain {type:text, text:...}; no cache_control (Gemini implicit cache)."""
    blocks = build_system_prompt(content_type="landing", source_locale="en")
    assert len(blocks) == 3
    for b in blocks:
        assert b["type"] == "text"
        assert "cache_control" not in b
        assert b["text"].strip()


def test_system_prompt_starts_with_common_rules():
    blocks = build_system_prompt(content_type="landing", source_locale="en")
    # First block is common.md content; must contain locked-rule markers.
    assert "Locked critical rules" in blocks[0]["text"]
    assert "No em dashes" in blocks[0]["text"]


def test_system_prompt_unknown_content_type_raises():
    with pytest.raises(ValueError):
        build_system_prompt(content_type="bogus", source_locale="en")


def test_system_prompt_unknown_locale_raises():
    with pytest.raises(FileNotFoundError):
        build_system_prompt(content_type="landing", source_locale="zz")


def test_user_message_includes_keywords_and_links():
    item = SourceItem(
        url="https://www.englishcollege.com/courses",
        title="Courses",
        body_excerpt="CEL offers English courses across San Diego, Los Angeles, and Vancouver.",
        locale="en",
        content_type="landing",
    )
    kw = KeywordPlan(primary="English courses", secondaries=("language school",), entities=("CEFR",))
    msg = build_user_message(
        item,
        link_candidates=["https://www.englishcollege.com/vancouver"],
        keywords=kw,
    )
    assert "English courses" in msg
    assert "vancouver" in msg.lower()
    assert "## Task" in msg
    assert item.title in msg


def test_user_message_caps_link_candidates():
    item = SourceItem(
        url="https://www.englishcollege.com/",
        title="Home",
        body_excerpt="Home page body.",
        locale="en",
        content_type="landing",
    )
    kw = KeywordPlan(primary="english school")
    msg = build_user_message(
        item,
        link_candidates=[f"https://www.englishcollege.com/page-{i}" for i in range(100)],
        keywords=kw,
    )
    # tracker-098: cap raised to 60; ensure the 61st URL is not present but the 31st is.
    assert "/page-60" not in msg
    assert "/page-30" in msg
    assert "/page-0" in msg


def test_translation_user_message_translates_without_swap_table():
    """audit-108 M-4: no link-swap table is injected — the model just translates the
    Markdown (links are localized by Weglot + stripped to anchor text at emit)."""
    msg = build_translation_user_message(
        en_summary_markdown="## H2\n\nSummary body with [a link](https://www.englishcollege.com/courses).",
        target_locale="de",
    )
    assert "Translate the following English Summary into de" in msg
    assert "Summary body with" in msg
    # The old swap-table apparatus must be gone.
    assert "swap table" not in msg.lower()
    assert "```json" not in msg
    assert "REMOVE" not in msg


def test_translation_system_prompt_two_blocks():
    """Tracker-091: blocks are plain {type:text, text:...}; no cache_control."""
    blocks = build_translation_system_prompt("de")
    assert len(blocks) == 2
    assert all("cache_control" not in b for b in blocks)
    assert all(b["type"] == "text" for b in blocks)
    assert "Target Locale: de" in blocks[1]["text"]


# ---- B3: prompts+keywords flow end-to-end (tracker-087) ----


def test_user_message_contains_keyword_plan_in_order():
    """The user message renders Primary / Secondary / Entities sections in that order."""
    item = SourceItem(
        url="https://www.englishcollege.com/learn-english-canada",
        title="Learn English in Canada",
        body_excerpt="Vancouver is the largest CEL campus in Canada.",
        locale="en",
        content_type="landing",
    )
    kw = KeywordPlan(
        primary="learn english in canada",
        secondaries=("vancouver", "campus"),
        entities=("CEFR", "DLI"),
    )
    msg = build_user_message(item, link_candidates=[], keywords=kw)
    # All three keyword fields must appear, in the documented order.
    p_idx = msg.find("Primary:")
    s_idx = msg.find("Secondary:")
    e_idx = msg.find("Entities to spell out")
    assert p_idx > 0, "Primary: section missing"
    assert s_idx > p_idx, "Secondary: section missing or before Primary:"
    assert e_idx > s_idx, "Entities section missing or before Secondary:"
    # The actual keyword content is inlined.
    assert "learn english in canada" in msg.lower()
    assert "vancouver" in msg.lower()
    assert "CEFR" in msg
    assert "DLI" in msg


def test_system_prompt_blocks_no_cache_control_after_gemini_migration():
    """Tracker-091: cache_control removed; Gemini caches the system prefix implicitly."""
    blocks = build_system_prompt(content_type="course", source_locale="en")
    assert len(blocks) == 3
    for b in blocks:
        assert "cache_control" not in b
        assert b["type"] == "text"
        assert b["text"].strip()


def test_common_md_contains_2026_corrections():
    """common.md (loaded as first system block) has the 2026 research corrections."""
    blocks = build_system_prompt(content_type="landing", source_locale="en")
    common = blocks[0]["text"]
    # Density narrowed to 1–2%.
    assert "1–2%" in common or "1-2%" in common
    # FAQPage schema lift.
    assert "FAQPage" in common
    # Trust > Experience EEAT re-weight.
    assert "Trust > Experience" in common
    # 134–167 answer-block target.
    assert "134–167" in common or "134-167" in common
    # Anti-AI burstiness section.
    assert "burstiness" in common.lower()


# ---- tracker-096: content-type-aware Task block ----


def test_user_message_task_is_four_part_for_landing():
    item = SourceItem(
        url="https://www.englishcollege.com/vancouver", title="Vancouver",
        body_excerpt="CEL Vancouver.", locale="en", content_type="landing",
    )
    msg = build_user_message(item, link_candidates=[], keywords=KeywordPlan(primary="x"))
    assert "## Task" in msg
    assert "4-part" in msg
    assert "Tagline" in msg and "Title" in msg and "Paragraph" in msg
    # tracker-098 pass 2: the lead is now TWO or THREE paragraphs (raised from two).
    assert "TWO or THREE lead Paragraphs" in msg
    # tracker-098: links are distributed across the lead Paragraphs AND the Content,
    # never in the Tagline or Title.
    low = msg.lower()
    assert "6" in msg and "internal links" in low
    assert "across the lead paragraphs and the content" in low
    assert "never in the tagline or title" in low


def test_user_message_task_is_single_block_for_blog():
    item = SourceItem(
        url="https://www.englishcollege.com/post/x", title="Post",
        body_excerpt="A post.", locale="de", content_type="blog_post",
    )
    msg = build_user_message(item, link_candidates=[], keywords=KeywordPlan(primary="x"))
    assert "## Task" in msg
    assert "4-part" not in msg  # blog keeps the single-block instruction
    assert "## H2" in msg


# ---- the client's Translation Guidelines §6: never a bare $ ----

# A dollar sign straight before an amount with no letters in front of it: "$1,950",
# "$ 330". "C$1,950" and "US$1,890" are not bare.
_BARE_DOLLAR_AMOUNT = re.compile(r"(?<![A-Za-z])\$\s?[0-9]")


@pytest.mark.parametrize("content_type", ["landing", "blog_post", "course", "housing"])
def test_the_english_writer_is_never_taught_a_bare_dollar(content_type):
    """Every English summary is written from common.md + the content type + locales/en.md.
    The client's Translation Guidelines §6: "Never use a bare `$`. Always disambiguate with
    `US$` or `C$`." Both files taught the opposite ("$1,950", "$1,890 CAD"), and the live
    cost page's summary carried 13 bare $, 12 of them as "$X CAD"."""
    text = "\n".join(b["text"] for b in build_system_prompt(content_type=content_type,
                                                            source_locale="en"))
    assert _BARE_DOLLAR_AMOUNT.findall(text) == []
    assert "C$1,950" in text and "US$" in text
    assert "never a bare $" in text.lower()


# ---- the translation layers against §6's table (client Translation Guidelines) ----
#
# §6: "Never use a bare `$`. Always disambiguate with `US$` or `C$`" and "Currency stays in
# the source currency. Do not convert C$ to EUR, CHF, or local currency." Its table for the
# five ratified languages is the test vector: US$100 -> DE `US$ 100`, FR `100 US$`,
# ES `US$100`, PT-BR `US$100`, IT `US$ 100` (C$ the same). Thousands 1.500 (DE/ES/PT-BR/IT),
# FR a narrow no-break space; decimals 1,5; 24-hour times.

_SPACE = "[ \u00a0\u202f]"
_SECTION_6 = {
    # locale: (symbol first?, space between symbol and amount?, thousands separator)
    "de": (True, True, "."),
    "fr": (False, True, "\u202f"),
    "es": (True, False, "."),
    "pt": (True, False, "."),
    "it": (True, True, "."),
}


def _locale_layer(locale):
    blocks = build_translation_system_prompt(target_locale=locale)
    return blocks[-1]["text"]


@pytest.mark.parametrize("locale", sorted(_SECTION_6))
def test_a_ratified_locale_layer_writes_currency_as_section_6_does(locale):
    symbol_first, spaced, thousands = _SECTION_6[locale]
    text = _locale_layer(locale)
    gap = _SPACE if spaced else ""
    for sym in ("US\\$", "C\\$"):
        amount = "[0-9]{1,3}(?:" + re.escape(thousands) + "[0-9]{3})*"
        shape = (sym + gap + amount) if symbol_first else (amount + gap + sym)
        assert re.search(shape, text), (locale, "no example in the §6 form", shape)
    # The wrong placement for this language never appears as an example.
    if symbol_first:
        wrong = r"(?:US|C)\$" + (r"[0-9]" if spaced else _SPACE + r"[0-9]")
    else:
        wrong = r"(?:US|C)\$" + _SPACE + r"?[0-9]"
    assert not re.search(wrong, text), (locale, "an example in the wrong placement")
    # No bare $, no conversion, no ISO code beside an amount.
    assert not re.search(r"(?<![A-Za-z])\$" + _SPACE + r"?[0-9]", text), locale
    assert not re.search(r"[0-9]" + _SPACE + r"?\$", text), locale
    assert "€" not in text, (locale, "an amount converted to euros")
    assert not re.search(r"[0-9]" + _SPACE + r"?(?:USD|CAD|EUR)\b|\b(?:USD|CAD|EUR)" + _SPACE + r"?[0-9]", text), locale


@pytest.mark.parametrize("locale", sorted(_SECTION_6))
def test_a_ratified_locale_layer_separates_numbers_as_section_6_does(locale):
    _, _, thousands = _SECTION_6[locale]
    text = _locale_layer(locale)
    assert "1" + thousands + "000" in text, (locale, "thousands example")
    assert re.search(r"[0-9],5\b", text), (locale, "decimal comma example")
    assert "a. m." not in text and "12h" not in text, (locale, "12-hour times")


@pytest.mark.parametrize("locale,bare_word", [("ar", "دولار"), ("ja", "ドル"), ("ko", "달러")])
def test_an_unratified_locale_layer_never_teaches_a_bare_dollar(locale, bare_word):
    """ar/ja/ko are not in §6's table, so their placement is left alone; §6's general
    rule still holds: every example amount carries US$ or C$, never a bare $ and never
    the bare word for "dollar" without the country."""
    text = _locale_layer(locale)
    assert "C$" in text and "US$" in text, locale
    assert not re.search(r"(?<![A-Za-z])\$" + _SPACE + r"?[0-9]", text), locale
    assert not re.search(r"[0-9][0-9,.]*" + _SPACE + r"?" + bare_word, text), (locale, "an amount in bare " + bare_word)
    assert not re.search(bare_word + _SPACE + r"?[0-9]", text), locale
