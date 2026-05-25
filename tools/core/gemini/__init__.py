"""Shared Gemini client (leaf): Batch + sync generation, cost estimation, caching.

The canonical Gemini integration for all CEL tools (summary, translator, copywriter,
future). Import `from tools.core.gemini.client import submit_batch, BatchRequest, ...`.
Config knobs live in `tools.core.gemini.config`. See docs/ARCHITECTURE.md.
"""
