"""Translator-side Weglot CSV adapter — re-exports the canonical engine + the Translation adapter.

The Weglot import-CSV format + IO now live in `tools.weglot.csv_engine` (the canonical,
tool-neutral engine, vendored byte-identical across cagdasunal/CEL + cagdasunal/webflow and
kept in lockstep by `system_inspector.check_dashboard_parity`). This module re-exports it so
every existing `from tools.translator.weglot import …` caller keeps working, and adds the one
translator-specific piece — `pairs_from_translations` — which maps engine `Translation` objects
to `WeglotPair` rows (it needs `Translation`, which the pure-stdlib engine must not import).

The summary tool's `tools/summary/csv_emitter.py` re-exports from HERE (back-compat chain).
"""
from __future__ import annotations

from typing import Iterable

from tools.translator.units import Translation
from tools.weglot.csv_engine import (  # noqa: F401  (re-exported for back-compat)
    EmissionReport,
    WeglotPair,
    atomic_write_text,
    emit_consolidated_csv,
    filter_out_stale_summary_rows,
    format_csv_text,
    is_stale_summary_word_from,
    read_existing_csv,
    weglot_quote,
    _weglot_quote,
)


def pairs_from_translations(
    translations: Iterable[Translation], type_: str = "Text"
) -> list[WeglotPair]:
    """Map engine `Translation` objects → Weglot rows (one row per translation).

    Skips empty/failed targets. This is the simple 1:1 path for callers whose units
    map directly to rows (meta tags, future tools). The summary caller uses block-level
    pairing instead (`structure.summary_page_blocks`).
    """
    return [
        WeglotPair(word_from=t.source, word_to=t.target, type_=type_)
        for t in translations
        if t.target.strip()
    ]
