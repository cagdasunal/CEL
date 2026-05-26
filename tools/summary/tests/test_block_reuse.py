"""Tests for tools.summary.block_reuse — the block-level translation reuse layer.

Uses the real TranslationMemory (tmp-file backed) so the tm_key scheme +
glossary-version invalidation are exercised, not a mock.
"""
from __future__ import annotations

from pathlib import Path

from tools.summary import block_reuse
from tools.translator.tm import TranslationMemory

GVER = "test-gv-1"
LOC = "de"


def _tm(tmp_path: Path) -> TranslationMemory:
    return TranslationMemory(tmp_path / "block-tm.json")


def test_lookup_returns_none_when_any_block_missing(tmp_path: Path):
    tm = _tm(tmp_path)
    tm.put("Block A", LOC, GVER, "Block A (de)")
    # only A is cached; the page also has B → must miss as a whole
    assert block_reuse.lookup_page_blocks(["Block A", "Block B"], LOC, tm, GVER) is None


def test_lookup_returns_all_targets_when_fully_cached(tmp_path: Path):
    tm = _tm(tmp_path)
    tm.put("Block A", LOC, GVER, "A-de")
    tm.put("Block B", LOC, GVER, "B-de")
    got = block_reuse.lookup_page_blocks(["Block A", "Block B"], LOC, tm, GVER)
    assert got == ["A-de", "B-de"]


def test_lookup_empty_blocks_or_no_tm_returns_none(tmp_path: Path):
    tm = _tm(tmp_path)
    assert block_reuse.lookup_page_blocks([], LOC, tm, GVER) is None
    assert block_reuse.lookup_page_blocks(["Block A"], LOC, None, GVER) is None


def test_lookup_respects_glossary_version(tmp_path: Path):
    """A glossary bump must invalidate block hits exactly like the page-level TM."""
    tm = _tm(tmp_path)
    tm.put("Block A", LOC, GVER, "A-de")
    assert block_reuse.lookup_page_blocks(["Block A"], LOC, tm, GVER) == ["A-de"]
    assert block_reuse.lookup_page_blocks(["Block A"], LOC, tm, "other-gv") is None


def test_lookup_respects_locale(tmp_path: Path):
    tm = _tm(tmp_path)
    tm.put("Block A", LOC, GVER, "A-de")
    assert block_reuse.lookup_page_blocks(["Block A"], "fr", tm, GVER) is None


def test_store_then_lookup_roundtrip(tmp_path: Path):
    tm = _tm(tmp_path)
    n = block_reuse.store_page_blocks(
        tm, ["Block A", "Block B"], ["A-de", "B-de"], LOC, GVER
    )
    assert n == 2
    assert block_reuse.lookup_page_blocks(["Block A", "Block B"], LOC, tm, GVER) == ["A-de", "B-de"]


def test_store_noop_on_length_mismatch(tmp_path: Path):
    tm = _tm(tmp_path)
    assert block_reuse.store_page_blocks(tm, ["A", "B"], ["only-one"], LOC, GVER) == 0
    assert len(tm) == 0


def test_store_skips_blank_pairs(tmp_path: Path):
    tm = _tm(tmp_path)
    n = block_reuse.store_page_blocks(tm, ["A", "  "], ["A-de", "B-de"], LOC, GVER)
    assert n == 1  # the blank source is skipped


def test_store_noop_when_no_tm(tmp_path: Path):
    assert block_reuse.store_page_blocks(None, ["A"], ["A-de"], LOC, GVER) == 0


def test_store_persists_across_instances(tmp_path: Path):
    """Stored blocks survive save()/reload — the cross-run reuse guarantee."""
    path = tmp_path / "block-tm.json"
    tm1 = TranslationMemory(path)
    block_reuse.store_page_blocks(tm1, ["Block A"], ["A-de"], LOC, GVER)
    tm1.save()
    tm2 = TranslationMemory(path)
    assert block_reuse.lookup_page_blocks(["Block A"], LOC, tm2, GVER) == ["A-de"]
