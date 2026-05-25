"""Pytest conftest — make the repo root importable.

The project's pyproject.toml pins `pythonpath = ["scripts"]`. These tests need
`tools.summary.*`, which requires the repo root on sys.path. Mirrors
`tools/fidelo/tests/conftest.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_summary_state(tmp_path, monkeypatch):
    """tracker-092 Phase 2: redirect the idempotency state file to a per-test
    tmp path so no live-mode test ever reads/writes the real
    data/seo-intel/summary-state.json (which would leak state across tests and
    pollute the repo). State still persists WITHIN a test (same tmp_path), so
    the idempotency-skip test can run generate-english twice and observe the skip.
    """
    from tools.summary import config
    monkeypatch.setattr(config, "SUMMARY_STATE_FILE", tmp_path / "summary-state.json")
    monkeypatch.setattr(config, "TRANSLATION_MEMORY_FILE", tmp_path / "translation-memory.json")
    # tracker-097: the persisted last-batch id (written by submit_batch) — isolate so
    # no test writes the real data/seo-intel/summary-last-batch.json.
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "summary-last-batch.json")
    # Plan A: the shared Gemini client (tools.core.gemini.client) reads LAST_BATCH_FILE
    # from tools.core.gemini.config — patch that too so submit/wait never touch the real file.
    monkeypatch.setattr("tools.core.gemini.config.LAST_BATCH_FILE", tmp_path / "summary-last-batch.json")
