"""Dedicated, reusable LLM translation engine (tracker-092 Phase 3).

A small translation engine built on the existing `tools.summary.batch_runner`
Gemini Batch client + Python stdlib (no heavy frameworks). It adds the layers a
raw Gemini call lacks: a translation-memory (don't re-translate unchanged
source), a glossary (do-not-translate brand/entity terms + forbidden/preferred),
and translation QA (placeholder/number/URL preservation, passthrough, length).

Public API:
    from tools.translation_engine import translate_batch, TranslationUnit, Translation
    from tools.translation_engine.glossary import load_glossary
    from tools.translation_engine.tm import TranslationMemory

Callers (tracker-092):
    - tools/summary/cli.py:_execute_translate  (summary paragraphs → Weglot CSV)
    - tools/summary/cli.py:_execute_translate_meta  (page meta titles/descriptions → CSV)

CSV emission is NOT the engine's job — callers reuse tools.summary.csv_emitter so
the Weglot CSV format stays single-sourced.
"""
from __future__ import annotations

from tools.translation_engine.engine import translate_batch
from tools.translation_engine.units import Translation, TranslationUnit

__all__ = ["translate_batch", "Translation", "TranslationUnit"]
