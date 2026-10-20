"""Cleanup C2 (monorepo CEL-051): what the desk pages share is defined once, in desk_shared.py.

The document page and the rules page used to read these names from the first desk's generator, so deleting
that generator (cleanup C4) would have broken both. These tests hold the end state: one definition, the first
desk's generator hands the same objects back until it is deleted, and the two newer pages do not import it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import desk_shared as S  # noqa: E402
from localize_desk import generate_desk_page as G  # noqa: E402
from localize_desk import generate_document_page as GD  # noqa: E402
from localize_desk import generate_rules_page as GR  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
SHARED = ["REPO_ROOT", "UNITS_DIR", "OUT_ROOT", "LOCALES", "PAGE_KEYS", "lang_name", "SAVE_OFF", "_head",
          "_STAGE_JS", "_PROXY_JS", "_TIP_JS"]
GENERATORS = ["generate_desk_page.py", "generate_document_page.py", "generate_rules_page.py"]


def _tree(name: str) -> ast.Module:
    return ast.parse((TOOLS / name).read_text(encoding="utf-8"))


def _alias(node: ast.Assign) -> bool:
    """`UNITS_DIR = S.UNITS_DIR`: a module-level name a test can point elsewhere, not a second definition."""
    v = node.value
    return (isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name) and v.value.id == "S"
            and all(isinstance(t, ast.Name) and t.id == v.attr for t in node.targets))


def _defined(name: str) -> set[str]:
    out: set[str] = set()
    for node in _tree(name).body:
        if isinstance(node, ast.Assign):
            if not _alias(node):
                out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def test_every_shared_name_is_defined_in_desk_shared():
    assert set(SHARED) <= _defined("desk_shared.py")


@pytest.mark.parametrize("generator", GENERATORS)
def test_no_generator_defines_a_shared_name_of_its_own(generator):
    assert not set(SHARED) & _defined(generator), "a second definition of a shared name"


def test_the_first_desks_generator_hands_back_the_same_objects():
    """Until cleanup C4 deletes it, `G.PAGE_KEYS`, `G._STAGE_JS` and the rest are what the tests and the
    monorepo checks read: they must be the shared objects, not copies."""
    for name in SHARED:
        assert getattr(G, name) is getattr(S, name), name


@pytest.mark.parametrize("module,name", [(GD, "UNITS_DIR"), (GD, "OUT_DIR"), (GR, "OUT_DIR")])
def test_the_pages_paths_come_from_the_shared_roots(module, name):
    assert str(getattr(module, name)).startswith(str(S.UNITS_DIR if name == "UNITS_DIR" else S.OUT_ROOT))


@pytest.mark.parametrize("generator", ["generate_document_page.py", "generate_rules_page.py"])
def test_the_document_and_rules_pages_do_not_import_the_first_desks_generator(generator):
    imported = []
    for node in ast.walk(_tree(generator)):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
    assert not [m for m in imported if "generate_desk_page" in m], imported
