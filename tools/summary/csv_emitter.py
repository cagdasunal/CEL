"""Summary-side re-export shim for Weglot CSV emission.

tracker-094: the generic Weglot CSV emission (the dialect, the row dataclass, the
read/consolidate/atomic-write) lives in `tools.translator.weglot` so the
`translator` package owns it and other tools can reuse it. This module re-exports
those names (keeping `SummaryPair` as a back-compat alias for `WeglotPair`) for
`cli._execute_translate` / `_execute_translate_meta`.

The consolidation reads the existing per-language CSV (which carries Fidelo
translations written by `tools/weglot/csv_export.py`), dedups on
(word_from, language_to), and appends — Fidelo rows are preserved.

audit-108 L-1 (2026-05-24): the paragraph-split helpers
(`split_summary_into_paragraphs`, `pair_from_paragraphs`, `_strip_md_heading`,
`_strip_html`) were REMOVED — they encoded the pre-block-level matching theory
(split on blank lines, strip a leading `##`) and had NO production caller. The
translate path now pairs the page's rendered text nodes via
`tools.summary.structure.summary_page_blocks` (tracker-107), so `word_from`
equals what Weglot extracts from the live page.
"""
from __future__ import annotations

# Generic Weglot-CSV emission now lives in the translator package (single source).
from tools.translator.weglot import (  # noqa: F401  (re-exported for back-compat)
    EmissionReport,
    WeglotPair as SummaryPair,
    emit_consolidated_csv,
    pairs_from_translations,
    read_existing_csv,
)
