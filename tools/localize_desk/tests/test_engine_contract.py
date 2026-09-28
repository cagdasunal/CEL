"""The desk still saves, and still writes, every field the engine reads.

The engine (the private monorepo) reads saved decisions to build the import file, send
requests to Gemini and reconcile after an import. Its half of this contract lives there
(`tools/localize/test_desk_contract.py`); this is CEL's half, so a desk change that breaks
the seam fails HERE, before the push — CEL's own tests cannot see the monorepo (runbook
WO-03, finding R42).

The list of fields is data, not code: `data/localize/engine-reads.json`, identical in both
repos (the monorepo's parity check holds them together). It also says who is meant to write
each field, because "can be saved" is not "is ever set": `rejected` was saveable for weeks
while nothing wrote it, so a re-request would have paid Gemini twice for the same prompt
(R56). Every check fails in both directions: a new gap fails, and so does a gap that has
closed but is still listed.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "data" / "localize" / "engine-reads.json"
DESK = REPO / "tools" / "localize_desk" / "generate_desk_page.py"
SAVE = REPO / "tools" / "localize_desk" / "save_decisions.py"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _save_fields() -> set[str]:
    m = re.search(r"var SAVE_FIELDS = \[([^\]]*)\]", DESK.read_text(encoding="utf-8"))
    assert m, "the desk's SAVE_FIELDS list was not found"
    return set(re.findall(r"'([A-Za-z]+)'", m.group(1)))


def _allowed_keys() -> set[str]:
    tree = ast.parse(SAVE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ALLOWED_KEYS" for t in node.targets):
            return {elt.value for elt in node.value.elts}
    raise AssertionError("save_decisions.ALLOWED_KEYS not found")


def _read_fields(c: dict) -> set[str]:
    return set().union(*map(set, c["reads"].values()))


def test_every_field_the_engine_reads_is_saved_or_a_listed_gap():
    c = _contract()
    arrives = _save_fields() & _allowed_keys()
    gaps = _read_fields(c) - arrives
    listed = set(c["known_gaps"])
    assert not gaps - listed, f"the engine reads fields the desk cannot save: {sorted(gaps - listed)}"
    assert not listed - gaps, f"{sorted(listed - gaps)} are saved now: remove them from known_gaps"


def test_whatever_the_desk_sends_the_server_keeps():
    dropped = _save_fields() - _allowed_keys()
    assert not dropped, f"the desk sends fields save_decisions throws away: {sorted(dropped)}"


def test_every_field_the_desk_owns_has_a_writer_in_the_desk():
    """A desk-owned field must be assigned somewhere in the desk's script (`s.<field> =`)."""
    c = _contract()
    src = DESK.read_text(encoding="utf-8")
    owned = {f for f, who in c["written_by"].items() if who == "desk"}
    missing = {f for f in owned if not re.search(rf"\bs\.{f}\s*=[^=]", src)}
    listed = {f for f in c["no_writer_yet"] if c["written_by"].get(f) == "desk"}
    assert not missing - listed, f"desk-owned fields nothing in the desk writes: {sorted(missing - listed)}"
    assert not listed - missing, f"{sorted(listed - missing)} have a writer now: remove them from no_writer_yet"


def test_every_read_field_says_who_writes_it():
    c = _contract()
    unowned = _read_fields(c) - set(c["written_by"])
    assert not unowned, f"read fields with no stated writer: {sorted(unowned)}"
