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


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _save_fields() -> set[str]:
    """What the desk sends (WO-17): its STORED_FIELDS."""
    m = re.search(r"var STORED_FIELDS = \[([^\]]*)\]", DESK.read_text(encoding="utf-8"))
    assert m, "the desk's STORED_FIELDS list was not found"
    return set(re.findall(r"'([A-Za-z]+)'", m.group(1)))


def _allowed_keys() -> set[str]:
    """What the storage keeps: the Worker's deskRecord(), through the harness stand-in the
    monorepo holds to it answer for answer (scripts/tests/test_desk_standin_parity.py)."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from localize_desk.desk_store import record_of
    probe = {f: ["x"] if f == "rejected" else ("csv" if f == "tray" else "x")
             for f in ("tray", "text", "approvedAgainst", "rejected", "by", "at", "liveAt",
                       "exportedAt", "importedAt", "sentAt", "arrivedAt", "failed", "why")}
    return set(record_of(probe))


def _read_fields(c: dict) -> set[str]:
    return set().union(*map(set, c["reads"].values()))


def test_every_field_the_engine_reads_is_saved_or_a_listed_gap():
    """The desk's fields must arrive from the desk; `by` is the server's stamp; the engine's
    own stamps arrive from the engine (its table, WO-21) -- they are the monorepo's half."""
    c = _contract()
    arrives = (_save_fields() & _allowed_keys()) | {"by"}
    desk_read = {f for f in _read_fields(c) if c["written_by"].get(f) == "desk"}
    gaps = desk_read - arrives
    listed = {f for f in c["known_gaps"] if c["written_by"].get(f) == "desk"}
    assert not gaps - listed, f"the engine reads fields the desk cannot save: {sorted(gaps - listed)}"
    assert not listed - gaps, f"{sorted(listed - gaps)} are saved now: remove them from known_gaps"


def test_whatever_the_desk_sends_the_server_keeps():
    dropped = _save_fields() - _allowed_keys()
    assert not dropped, f"the desk sends fields the storage throws away: {sorted(dropped)}"


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
