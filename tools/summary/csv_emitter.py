"""Summary-side helpers for Weglot CSV emission.

tracker-094: the generic Weglot CSV emission (the dialect, the row dataclass, the
read/consolidate/atomic-write) now lives in `tools.translator.weglot` so the
`translator` package owns it and other tools can reuse it. This module re-exports
those names (keeping `SummaryPair` as a back-compat alias for `WeglotPair`) and
adds the summary-specific paragraph helpers used by `cli._execute_translate`.

The consolidation still reads the existing per-language CSV (which carries Fidelo
translations written by `tools/weglot/csv_export.py`), dedups on
(word_from, language_to), and appends — Fidelo rows are preserved.
"""
from __future__ import annotations

from typing import Sequence

# Generic Weglot-CSV emission now lives in the translator package (single source).
from tools.translator.weglot import (  # noqa: F401  (re-exported for back-compat)
    EmissionReport,
    WeglotPair as SummaryPair,
    emit_consolidated_csv,
    pairs_from_translations,
    read_existing_csv,
)


def split_summary_into_paragraphs(rich_text_html_or_markdown: str) -> list[str]:
    """Split a rich-text Summary into paragraphs for row-level translation.

    Per LOCKED DECISION: ONE row per paragraph (not per sentence). Handles both
    plain Markdown (blank-line-separated) and Webflow rich-text HTML (`<p>` tags).
    """
    text = rich_text_html_or_markdown.strip()
    if not text:
        return []

    # Strip simple `<p>...</p>` wrappers if present.
    if "<p" in text:
        import re

        parts = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL | re.IGNORECASE)
        cleaned = [_strip_html(p).strip() for p in parts]
        return [p for p in cleaned if p]

    # Markdown: split on double-newline.
    parts = [p.strip() for p in text.split("\n\n")]
    return [p for p in parts if p]


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s)


def pair_from_paragraphs(
    en_paragraphs: Sequence[str], translated_paragraphs: Sequence[str]
) -> list[SummaryPair]:
    """Zip EN paragraphs with translated paragraphs into pair objects.

    Caller is responsible for ensuring both sequences are the same length and
    aligned (the model produces paragraph-for-paragraph translations).
    """
    if len(en_paragraphs) != len(translated_paragraphs):
        raise ValueError(
            f"paragraph count mismatch: en={len(en_paragraphs)} "
            f"target={len(translated_paragraphs)}"
        )
    return [
        SummaryPair(word_from=src, word_to=tgt)
        for src, tgt in zip(en_paragraphs, translated_paragraphs)
        if src.strip()
    ]
