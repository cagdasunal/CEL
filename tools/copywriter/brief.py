"""The copywriter's request/result contract + brief loading.

A CopyRequest is the structured form of a human brief ("improve the Vancouver hero,
warmer tone, keep the DLI number"). The agent fills it from a chat brief or a JSON file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class CopyRequest:
    """One copy-improvement request. `target` (optional) names what to fetch/write:
    {"kind": "cms_item", "collection": "blog", "cms_item_id": "...", "field_slug": "..."}
    or {"kind": "static_page", "url": "https://www.englishcollege.com/..."}.
    """

    brief: str
    locale: str = "ko"
    content_type: str = "marketing"
    existing_copy: str = ""
    keywords: tuple[str, ...] = ()
    tone: str = ""
    max_words: int = 0
    target: Optional[dict[str, Any]] = None
    must_keep_facts: tuple[str, ...] = ()
    do_not_touch: tuple[str, ...] = ()
    translate_to: tuple[str, ...] = ()


@dataclass
class CopyResult:
    """The improved copy + QA verdict. `before` is the source copy (for the diff)."""

    text: str
    locale: str
    ok: bool
    qa_flags: list[str] = field(default_factory=list)
    before: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def load_brief(path: str | Path) -> CopyRequest:
    """Load a CopyRequest from a JSON brief file. Only `brief` is required."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("brief"):
        raise ValueError(f"brief file {path} must be a JSON object with a non-empty 'brief'")
    return CopyRequest(
        brief=data["brief"],
        locale=data.get("locale", "ko"),
        content_type=data.get("content_type", "marketing"),
        existing_copy=data.get("existing_copy", ""),
        keywords=tuple(data.get("keywords", ())),
        tone=data.get("tone", ""),
        max_words=int(data.get("max_words", 0)),
        target=data.get("target"),
        must_keep_facts=tuple(data.get("must_keep_facts", ())),
        do_not_touch=tuple(data.get("do_not_touch", ())),
        translate_to=tuple(data.get("translate_to", ())),
    )
