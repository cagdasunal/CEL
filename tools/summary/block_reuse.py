"""Block-level translation reuse for the summary translate pipeline.

Why
---
The whole-page translation memory (``tools.translator.tm``) keys on the ENTIRE
page-summary markdown, so it misses whenever *any* block on a page changes — one
edited sentence forces a paid re-translation of the page's other (unchanged)
blocks, and a glossary-version bump invalidates every entry at once. In practice
that meant ~0% reuse and a full Gemini re-charge even though the block
translations already existed (see memory/weglot-tm-reuse-credit-waste.md).

This module adds a BLOCK-level reuse layer the summary CLI consults before
calling Gemini:

* ``lookup_page_blocks`` — if EVERY rendered block of a page already has a stored
  translation, return them (the page is rebuilt for FREE). If even one block is
  missing, return ``None`` so the whole page goes to the model — keeping each
  page translated as one coherent unit (no isolated-block quality loss).
* ``store_page_blocks`` — after a page IS translated by the model, store each of
  its blocks so future runs reuse them. The block-TM self-fills.

Correct-by-construction pairing
-------------------------------
Each EN block is only ever stored against its OWN translation (same index, same
page, same call) and only ever looked up by its own exact text. Blocks are never
zipped across pages or sources, so the tracker-114 source↔target mis-pairing
class cannot arise here. The block-TM reuses ``tools.translator.tm`` verbatim
(``tm_key`` includes locale + glossary_version), so a glossary change still
invalidates stale block hits exactly like the page-level TM.
"""
from __future__ import annotations

from typing import Optional


def lookup_page_blocks(
    en_blocks: list[str],
    locale: str,
    block_tm,
    glossary_version: str,
    tone: str = "",
) -> Optional[list[str]]:
    """Return stored target blocks for ``en_blocks`` IFF every block is present.

    Returns ``None`` when ``block_tm`` is falsy, ``en_blocks`` is empty, or ANY
    block has no stored translation — signalling "send this whole page to the
    model". All-or-nothing per page keeps each summary translated coherently.
    """
    # NB: `block_tm is None`, not `not block_tm` — an EMPTY TranslationMemory is
    # falsy (it defines __len__), and an empty TM is a valid first-run state.
    if block_tm is None or not en_blocks:
        return None
    out: list[str] = []
    for block in en_blocks:
        target = block_tm.get(block, locale, glossary_version, tone)
        if not target:
            return None
        out.append(target)
    return out


def store_page_blocks(
    block_tm,
    en_blocks: list[str],
    tr_blocks: list[str],
    locale: str,
    glossary_version: str,
    tone: str = "",
) -> int:
    """Store each ``en_block -> tr_block`` pair for future reuse; return the count
    stored. No-op (returns 0) when ``block_tm`` is falsy, lists are empty, or
    their lengths differ (the caller already guards block-count parity)."""
    # `block_tm is None`, not `not block_tm` (empty TM is falsy via __len__).
    if block_tm is None or not en_blocks or len(en_blocks) != len(tr_blocks):
        return 0
    stored = 0
    for en, tr in zip(en_blocks, tr_blocks):
        if en.strip() and tr.strip():
            block_tm.put(en, locale, glossary_version, tr, tone)
            stored += 1
    return stored
