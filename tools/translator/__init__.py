"""`translator` — a dedicated, reusable LLM translation component (tracker-092/094).

A small translator built on the existing `tools.summary.batch_runner` Gemini Batch
client + Python stdlib (no heavy frameworks). It adds the layers a raw Gemini call
lacks: a translation-memory (don't re-translate unchanged source), a glossary
(do-not-translate brand/entity terms + forbidden/preferred), and translation QA
(placeholder/number/URL preservation, passthrough, length).

Public API:
    from tools.translator import translate_batch, TranslationUnit, Translation
    from tools.translator.glossary import load_glossary
    from tools.translator.tm import TranslationMemory
    # Weglot CSV output (consolidates with existing Fidelo rows):
    from tools.translator.weglot import pairs_from_translations, emit_consolidated_csv, WeglotPair

Designed for reuse across tools: callers pass neutral `TranslationUnit`s and get
`Translation`s back; `tools.translator.weglot` turns those into Weglot import CSVs
that merge cleanly with the Fidelo translations already in the per-locale files.

Callers today (CEL summary tool):
    - tools/summary/cli.py:_execute_translate       (summary paragraphs → Weglot CSV)
    - tools/summary/cli.py:_execute_translate_meta   (page meta titles/descriptions → CSV)
"""
from __future__ import annotations

from tools.translator.engine import translate_batch
from tools.translator.units import Translation, TranslationUnit

__all__ = ["translate_batch", "Translation", "TranslationUnit"]
