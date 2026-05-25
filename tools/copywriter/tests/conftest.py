"""Make the repo root importable for the copywriter tests + a no-spend backstop.

Mirrors tools/summary/tests/conftest.py. The copywriter tests are dry-run / QA only —
they must NEVER call Gemini or Webflow; deleting the keys makes a real call raise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("WEBFLOW_API_TOKEN", raising=False)
