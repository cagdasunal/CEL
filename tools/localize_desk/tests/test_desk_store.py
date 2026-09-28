"""The harness's stand-in for the Worker's desk storage (runbook WO-17 / WO-33).

The full contract -- every rule, answer for answer against the real Worker -- is the
monorepo's differential test (scripts/tests/test_desk_standin_parity.py). These are the
CEL-side guards that run in CEL's own CI: the rules the desk's save path leans on, and the
harness wiring.
"""
from __future__ import annotations

from pathlib import Path

from localize_desk import harness as H
from localize_desk.desk_store import DeskStore

U1, U2 = "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"


def _store():
    return DeskStore({U1: {"vancouver"}, U2: {"vs-toronto"}})


def _write(store, changes, locale="de", who="pat@example.test"):
    return store.handle("desk-write", {"locale": locale, "client": 1, "changes": changes}, who)


def test_a_change_on_the_current_version_applies_and_a_stale_one_conflicts():
    s = _store()
    code, r = _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv"}}])
    assert code == 200 and r["applied"] == [{"unit": U1, "version": 1}]
    code, r = _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "draft"}}], who="kim@example.test")
    assert r["applied"] == [] and r["conflicts"][0]["current"]["version"] == 1
    assert r["conflicts"][0]["current"]["by"] == "pat@example.test"


def test_a_text_not_on_the_named_page_is_refused():
    s = _store()
    _code, r = _write(s, [{"unit": U2, "page": "vancouver", "base": 0, "record": {"tray": "csv"}}])
    assert r["refused"] == [{"unit": U2, "reason": "not on this page"}] and r["applied"] == []


def test_the_read_carries_what_the_desk_needs():
    s = _store()
    _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv", "text": "Hallo"}}])
    code, r = s.handle("desk-read", {"locale": "de"}, "pat@example.test")
    d = r["decisions"][U1]
    assert code == 200 and r["api"] == 1
    assert (d["tray"], d["text"], d["page"], d["version"], d["by"]) == ("csv", "Hallo", "vancouver", 1, "pat@example.test")


def test_an_old_desk_is_told_to_reload():
    s = _store()
    code, r = s.handle("desk-write", {"locale": "de", "client": 0, "changes": []}, "p@example.test")
    assert code == 409 and "reload" in r["error"]


def test_the_harness_answers_the_desk_actions_from_the_real_page_map():
    root = H.stage_copy()
    try:
        worker = H.MockWorker(root)
        uid = sorted(u for u, _p in worker.store.units if _p == "vancouver")[0]
        code, r = worker.handle({"action": "desk-write", "locale": "de", "client": 1,
                                 "changes": [{"unit": uid, "page": "vancouver", "base": 0, "record": {"tray": "csv"}}]})
        assert code == 200 and r["applied"][0]["version"] == 1
        code, r = worker.handle({"action": "desk-read", "locale": "de"})
        assert r["decisions"][uid]["by"] == "reviewer@example.test"
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
