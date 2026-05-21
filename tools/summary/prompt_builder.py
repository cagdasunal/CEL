"""Compose Gemini API messages from content type + locale + source item.

System prompt is built as a list of text blocks:
    [common.md, <content_type>.md, locales/<source_locale>.md]

Gemini caches the system prompt prefix implicitly on the Batch tier — no
explicit `cache_control` markers are needed (unlike the prior Anthropic
implementation; see tracker-091). `batch_runner._flatten_system_blocks`
concatenates the block list into a single `system_instruction` string at
submit time.

The user message contains the per-item variable input: source body, keywords,
link inventory subset.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from tools.summary import config


# ---- Data types ----


@dataclass(frozen=True)
class SourceItem:
    """The page or CMS item being summarized."""

    url: str
    title: str
    body_excerpt: str  # Plain-text body, trimmed to a reasonable window (≤8000 chars).
    locale: str  # Source language; "en" for landing pages and most CMS items
    content_type: str  # one of: "landing", "course", "housing", "blog_post"
    cms_item_id: Optional[str] = None
    # tracker-098 pass 2: the item's CURRENT summary (plain text, ≤~1500 chars), passed
    # to build_user_message as the reuse seed so generation expands what exists instead
    # of starting blank. Empty when the item has no prior summary.
    existing_summary_excerpt: str = ""


@dataclass(frozen=True)
class KeywordPlan:
    primary: str
    secondaries: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkSwap:
    """For translation: source link → equivalent in target locale, or None to REMOVE."""

    source_url: str
    target_url: Optional[str]  # None = remove the link entirely


# ---- Loading ----


def _load_prompt(name: str) -> str:
    path = config.PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def _content_type_filename(content_type: str) -> str:
    mapping = {
        "blog_post": "blog_post.md",
        "course": "course.md",
        "housing": "housing.md",
        "landing": "landing.md",
    }
    if content_type not in mapping:
        raise ValueError(
            f"unknown content_type {content_type!r}; expected one of "
            f"{sorted(mapping.keys())}"
        )
    return mapping[content_type]


# ---- System prompt assembly ----


def build_system_prompt(content_type: str, source_locale: str) -> list[dict]:
    """Return a list of system-prompt blocks (tracker-091 — Gemini-compatible shape).

    Order: common → content_type → locale.
    Each block is `{"type": "text", "text": "..."}` — NO cache_control field.
    Gemini caches the prefix implicitly on the Batch tier.
    `batch_runner._flatten_system_blocks` concatenates these into a single
    `system_instruction` string at submit time.
    """
    common = _load_prompt("common.md")
    type_layer = _load_prompt(_content_type_filename(content_type))
    locale_path = f"locales/{source_locale}.md"
    locale_layer = _load_prompt(locale_path)

    return [
        {
            "type": "text",
            "text": common,
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# {content_type.replace('_', ' ').title()} Layer\n\n{type_layer}",
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# Source Locale: {source_locale}\n\n{locale_layer}",
        },
    ]


# ---- User message assembly ----


def build_user_message(
    item: SourceItem,
    link_candidates: Iterable[str],
    keywords: KeywordPlan,
    existing_summary_excerpt: str = "",
) -> str:
    """Build the user-message Markdown for a generation request."""
    candidates = list(link_candidates)
    lines: list[str] = []

    lines.append(f"## Source page")
    lines.append(f"- URL: {item.url}")
    lines.append(f"- Title: {item.title}")
    lines.append(f"- Locale: {item.locale}")
    lines.append(f"- Content type: {item.content_type}")
    if item.cms_item_id:
        lines.append(f"- CMS item ID: {item.cms_item_id}")
    lines.append("")
    lines.append(f"## Existing body excerpt")
    lines.append("")
    lines.append(item.body_excerpt.strip())
    lines.append("")

    if existing_summary_excerpt.strip():
        lines.append(
            "## Existing summary — REUSE this: keep its verified facts, EXPAND it to "
            "the new length, and add the new internal links. Do NOT discard it or "
            "rewrite from scratch."
        )
        lines.append("")
        lines.append(existing_summary_excerpt.strip())
        lines.append("")

    lines.append("## Keywords (use ONLY these — do not invent new keyword targets)")
    lines.append(f"- Primary: {keywords.primary}")
    if keywords.secondaries:
        lines.append(f"- Secondary: {', '.join(keywords.secondaries)}")
    if keywords.entities:
        lines.append(f"- Entities to spell out on first mention: {', '.join(keywords.entities)}")
    lines.append("")

    lines.append("## Available internal link candidates")
    lines.append("Pick 6–8 contextually-relevant links, distributed across the summary. Do NOT invent URLs.")
    lines.append("")
    for url in candidates[:60]:  # cap to 60 to stay within reasonable prompt size
        lines.append(f"- {url}")
    lines.append("")

    lines.append("## Task")
    if item.content_type == "blog_post":
        lines.append(
            "Write the Summary section for this page per the rules above. Return only "
            "the rendered Markdown (one `## H2`, optional `### H3` lines, paragraphs). "
            "No code fences, no preamble, no trailing commentary."
        )
    else:
        # tracker-096: courses, housing, and landing pages use the 4-part structure.
        # tracker-098 pass 2: the Paragraph part is now TWO or THREE paragraphs that
        # may carry links (raised from two; structure renders N paragraphs).
        lines.append(
            "Write the 4-part Summary section per the rules above, as ONE Markdown "
            "document in this exact order: a `## ` Tagline (2-3 related words, no "
            "punctuation), a `### ` Title (place the primary keyword here), TWO or "
            "THREE lead Paragraphs (blank-line separated; the first leads with the "
            "answer + the primary keyword in its first sentence), then the Content "
            "starting at `#### ` (use `##### ` only where needed). Distribute 6–8 "
            "internal links across the lead Paragraphs and the Content (never in the "
            "Tagline or Title). No code fences, no preamble, no trailing commentary."
        )
    return "\n".join(lines)


# ---- Translation request ----


def build_translation_system_prompt(target_locale: str) -> list[dict]:
    """System prompt for translation pass — common.md + target locale layer only.

    Tracker-091: cache_control removed; Gemini caches implicitly on Batch tier.
    """
    common = _load_prompt("common.md")
    locale_path = f"locales/{target_locale}.md"
    locale_layer = _load_prompt(locale_path)
    return [
        {
            "type": "text",
            "text": common,
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# Target Locale: {target_locale}\n\n{locale_layer}",
        },
    ]


def build_translation_user_message(
    en_summary_markdown: str,
    target_locale: str,
    link_swaps: Iterable[LinkSwap],
) -> str:
    """User message for translation: source EN summary + per-link swap table.

    For each link_swap with target_url=None, the model is instructed to REMOVE
    the link (drop the anchor text inline) — never link cross-language.
    """
    swap_table = {}
    for swap in link_swaps:
        swap_table[swap.source_url] = swap.target_url  # None = remove

    lines: list[str] = []
    lines.append("## Task")
    lines.append(
        f"Translate the following English Summary into {target_locale}, preserving the "
        f"exact Markdown structure (every heading level and its position, paragraph "
        f"breaks, and link placement). Apply the locale-specific tone, idiom, and "
        f"conventions from the system prompt."
    )
    lines.append("")
    lines.append("## Link swap rules")
    lines.append(
        "For each Markdown link `[text](URL)` in the source, look up the URL in the "
        "swap table below. If the table has a target URL, use it. If the table maps "
        "the URL to `null` (no equivalent in the target locale), REMOVE the link "
        "entirely — drop the `[...](...)` syntax and keep the anchor text inline as "
        "plain prose. Do NOT translate the URL itself or link cross-language."
    )
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(swap_table, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Source (English)")
    lines.append("")
    lines.append(en_summary_markdown.strip())
    lines.append("")
    lines.append(
        "Return only the translated Markdown. No code fences, no preamble, no "
        "commentary."
    )
    return "\n".join(lines)
