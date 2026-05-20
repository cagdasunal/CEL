"""Tests for tools.summary.prompt_builder — system-prompt assembly + user-message format."""

import json

import pytest

from tools.summary.prompt_builder import (
    KeywordPlan,
    LinkSwap,
    SourceItem,
    build_system_prompt,
    build_translation_system_prompt,
    build_translation_user_message,
    build_user_message,
)


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
    # Cap is 30; ensure the 31st URL is not present.
    assert "/page-30" not in msg
    assert "/page-0" in msg


def test_translation_user_message_contains_swap_table():
    swaps = [
        LinkSwap(
            source_url="https://www.englishcollege.com/post/x",
            target_url="https://www.englishcollege.com/de/post/x",
        ),
        LinkSwap(
            source_url="https://www.englishcollege.com/post/y",
            target_url=None,  # REMOVE
        ),
    ]
    msg = build_translation_user_message(
        en_summary_markdown="## H2\n\nSummary body.",
        target_locale="de",
        link_swaps=swaps,
    )
    assert "swap table" in msg.lower()
    assert "REMOVE" in msg
    # JSON swap-table block must be present and valid.
    assert "/de/post/x" in msg
    assert "null" in msg


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
    # Links-only-in-Content instruction is present.
    assert "links in the Content" in msg.lower() or "links in the content" in msg.lower()


def test_user_message_task_is_single_block_for_blog():
    item = SourceItem(
        url="https://www.englishcollege.com/post/x", title="Post",
        body_excerpt="A post.", locale="de", content_type="blog_post",
    )
    msg = build_user_message(item, link_candidates=[], keywords=KeywordPlan(primary="x"))
    assert "## Task" in msg
    assert "4-part" not in msg  # blog keeps the single-block instruction
    assert "## H2" in msg
