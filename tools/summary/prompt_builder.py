"""Compose Claude API messages from content type + locale + source item.

System prompt is built as a stack of cacheable blocks:
    [common.md, <content_type>.md, locales/<source_locale>.md]

Each block carries `cache_control={"type": "ephemeral"}` so the static prefix
is cached across batch requests. The user message contains the per-item
variable input: source body, keywords, link inventory subset.
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
    """Return a list of system-prompt blocks ready for the Anthropic API.

    Each block carries `cache_control={"type": "ephemeral"}` so the static
    prefix is cached. Order: common → content_type → locale.
    """
    common = _load_prompt("common.md")
    type_layer = _load_prompt(_content_type_filename(content_type))
    locale_path = f"locales/{source_locale}.md"
    locale_layer = _load_prompt(locale_path)

    return [
        {
            "type": "text",
            "text": common,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# {content_type.replace('_', ' ').title()} Layer\n\n{type_layer}",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# Source Locale: {source_locale}\n\n{locale_layer}",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
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
        lines.append("## Existing summary (if any — improve, don't duplicate)")
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
    lines.append("Pick 1-3 contextually-relevant links from this list. Do NOT invent URLs.")
    lines.append("")
    for url in candidates[:30]:  # cap to 30 to stay within reasonable prompt size
        lines.append(f"- {url}")
    lines.append("")

    lines.append("## Task")
    lines.append(
        "Write the Summary section for this page per the rules above. Return only the "
        "rendered Markdown (one `## H2`, optional `### H3` lines, paragraphs). No code "
        "fences, no preamble, no trailing commentary."
    )
    return "\n".join(lines)


# ---- Translation request ----


def build_translation_system_prompt(target_locale: str) -> list[dict]:
    """System prompt for translation pass — common.md + target locale layer only."""
    common = _load_prompt("common.md")
    locale_path = f"locales/{target_locale}.md"
    locale_layer = _load_prompt(locale_path)
    return [
        {
            "type": "text",
            "text": common,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        {
            "type": "text",
            "text": f"\n\n---\n\n# Target Locale: {target_locale}\n\n{locale_layer}",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
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
        f"Translate the following English Summary into {target_locale}, keeping the "
        f"Markdown structure (one H2, optional H3s, paragraphs). Apply the locale-"
        f"specific tone, idiom, and conventions from the system prompt."
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
