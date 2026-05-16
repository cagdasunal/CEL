"""Pytest conftest — make the repo root importable.

The project's pyproject.toml pins `pythonpath = ["scripts"]`. These tests need
`tools.summary.*`, which requires the repo root on sys.path. Mirrors
`tools/fidelo/tests/conftest.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
