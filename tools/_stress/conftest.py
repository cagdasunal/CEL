"""Stress harness — repo root on sys.path + a no-spend backstop.

These tests are deterministic and must make NO real Gemini or Webflow calls; deleting
the keys means any accidental real call raises. All tests here carry the `stress` marker
(registered in pyproject.toml), so `pytest -m "not stress"` runs the legacy suite alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _no_spend(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("WEBFLOW_API_TOKEN", raising=False)
