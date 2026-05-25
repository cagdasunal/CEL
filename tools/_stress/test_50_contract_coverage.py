"""(f) The leaf-contract must list EVERY consumer tool — self-guard against the H1 hole.

audit-002 H1: `.importlinter` `forbidden_modules` had omitted `tools.copywriter` (and the
namespace-package `tools.weglot`), so a `tools.core -> consumer` import would not have been
caught. This test computes the live consumer set and asserts each is forbidden, so the next
tool added without updating the contract fails HERE instead of silently widening the hole.

Consumer = a `tools/<x>/` package that is importable: it has an `__init__.py` OR a
top-level `*.py` module (PEP-420 namespace packages like `tools/weglot` have no
`__init__.py`). Excludes the leaf itself (`core`) and the test harness (`_stress`).
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.stress

REPO_ROOT = Path(__file__).resolve().parents[2]
_NOT_CONSUMERS = {"core", "_stress", "__pycache__"}


def _consumer_packages() -> set[str]:
    out: set[str] = set()
    for d in (REPO_ROOT / "tools").iterdir():
        if not d.is_dir() or d.name in _NOT_CONSUMERS:
            continue
        if (d / "__init__.py").exists() or any(d.glob("*.py")):
            out.add(f"tools.{d.name}")
    return out


def _forbidden_modules() -> set[str]:
    text = (REPO_ROOT / ".importlinter").read_text(encoding="utf-8")
    m = re.search(r"forbidden_modules\s*=\s*\n((?:[ \t]+\S+\n?)+)", text)
    assert m, "could not parse forbidden_modules from .importlinter"
    return {ln.strip() for ln in m.group(1).splitlines() if ln.strip()}


def test_every_consumer_tool_is_forbidden_from_core():
    missing = _consumer_packages() - _forbidden_modules()
    assert not missing, (
        "consumer tools missing from .importlinter forbidden_modules — the leaf-contract "
        f"has a hole (a tools.core import of these would NOT be caught): {sorted(missing)}"
    )
