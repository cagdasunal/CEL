"""Compose the copywriter's Gemini messages.

System = the copywriter's universal common.md + the reused per-locale layer
(tools/summary/prompts/locales/<locale>.md — register/typography/banlist).
User = the brief + the current copy + keywords/facts/do-not-touch + link candidates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tools.copywriter import config
from tools.copywriter.brief import CopyRequest


def build_system_prompt(locale: str) -> list[dict]:
    """Return system-prompt blocks: [copywriter common.md, locale layer].

    (Content type is conveyed to the model via build_user_message, not the system
    prompt — there is no per-content-type system layer, so it isn't a parameter here.)
    """
    common = (config.PROMPTS_DIR / "common.md").read_text(encoding="utf-8")
    blocks = [{"type": "text", "text": common}]
    locale_path = Path(config.LOCALE_LAYERS_DIR) / f"{locale}.md"
    if locale_path.exists():
        layer = locale_path.read_text(encoding="utf-8")
        blocks.append({"type": "text", "text": f"\n\n---\n\n# Locale layer ({locale})\n\n{layer}"})
    return blocks


def build_user_message(
    req: CopyRequest, current_copy: str, link_candidates: Iterable[str] = ()
) -> str:
    """Build the per-request user message (brief + current copy + constraints)."""
    lines: list[str] = ["## Brief", req.brief.strip(), ""]
    lines.append(f"## Target locale: {req.locale}  |  Content type: {req.content_type}")
    if req.tone:
        lines.append(f"## Tone notes: {req.tone}")
    if req.max_words:
        lines.append(f"## Length: aim for about {req.max_words} words")
    lines += ["", "## Current copy — improve THIS (rewrite in the same language; keep its facts)", ""]
    lines.append(current_copy.strip() or "(none provided — write fresh per the brief)")
    lines.append("")
    if req.keywords:
        lines.append(f"## Keywords (use naturally; do not stuff): {', '.join(req.keywords)}")
    if req.must_keep_facts:
        lines.append("## MUST keep these facts verbatim:")
        lines += [f"- {f}" for f in req.must_keep_facts]
    if req.do_not_touch:
        lines.append("## Do NOT change these (leave exactly as-is):")
        lines += [f"- {d}" for d in req.do_not_touch]
    cands = list(link_candidates)
    if cands:
        lines += ["", "## Internal link candidates (use ONLY these URLs, descriptive anchors, where they genuinely help):"]
        lines += [f"- {u}" for u in cands[:40]]
    lines += [
        "",
        "## Task",
        "Rewrite/improve the current copy per the brief and every rule above. Return ONLY "
        "the improved copy as Markdown in the target language — no preamble, no commentary, "
        "no code fences.",
    ]
    return "\n".join(lines)
