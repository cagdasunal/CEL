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


def test_the_summary_counts_shapes_and_answers_flagged_texts():
    """desk-summary (runbook WO-18): the index's counts, as the shapes stageOf() reads."""
    s = _store()
    _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv", "text": "Hallo"}},
               {"unit": U2, "page": "vs-toronto", "base": 0, "record": {"tray": "draft"}}])
    code, r = s.handle("desk-summary", {"flagged": {"de": [U1], "fr": [U1]}}, "pat@example.test")
    assert code == 200 and list(r["languages"]) == ["de", "fr", "es", "pt", "it", "ja", "ko", "ar"]
    assert r["languages"]["de"]["shapes"] == [[{"tray": "csv", "text": True}, 1], [{"tray": "draft"}, 1]]
    assert r["languages"]["de"]["flagged"] == {U1: {"tray": "csv", "text": True}}
    assert r["languages"]["fr"] == {"shapes": [], "flagged": {}}
    assert "Hallo" not in str(r), "no reviewer's wording travels to the index"
    code, r = s.handle("desk-summary", {"flagged": {"zz": [U1]}}, "pat@example.test")
    assert code == 400


def test_an_id_with_a_trailing_newline_is_refused_as_the_worker_refuses_it():
    s = _store()
    code, r = _write(s, [{"unit": U1 + "\n", "page": "vancouver", "base": 0, "record": {"tray": "csv"}}])
    assert code == 400 and r["error"] == "invalid: bad text id"


def _stamp(minutes_ago: float) -> str:
    from datetime import datetime, timedelta, timezone
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def test_a_job_the_engine_never_answered_is_failed_and_frees_its_language():
    """The Worker's sweep (U1), which the parity test cannot reach: it has no clock to move."""
    s = _store()
    _c, r = s.handle("desk-job-start", {"locale": "de", "kind": "plan"}, "pat@example.test")
    s.jobs[r["job"]["id"]]["created_at"] = _stamp(34)
    _c, got = s.handle("desk-job-get", {"locale": "de"}, "pat@example.test")
    assert got["jobs"]["plan"]["status"] == "queued"                     # 34 minutes: left alone
    s.jobs[r["job"]["id"]].update(status="running", started_at=_stamp(36))
    _c, got = s.handle("desk-job-get", {"locale": "de"}, "pat@example.test")
    assert got["jobs"]["plan"]["status"] == "failed" and got["jobs"]["plan"]["error"] == "engine-never-answered"
    assert s.handle("desk-job-start", {"locale": "de", "kind": "plan"}, "pat@example.test")[0] == 200


def test_the_harness_plays_the_engine_for_the_desks_jobs():
    s = _store()
    assert s.finish_job("de", "export") is None                            # nothing open
    _c, r = s.handle("desk-job-start", {"locale": "de", "kind": "export"}, "pat@example.test")
    assert s.dispatched == [r["job"]["id"]]
    assert s.finish_job("de", "export", "running") == r["job"]["id"]
    assert s.jobs[r["job"]["id"]]["started_at"]
    s.finish_job("de", "export", "done", {"batchId": "de-1", "rows": 1, "refused": []})
    s.seed_export("de-1", "de", "word_from,word_to\nHello,Hallo\n", 1, [])
    _c, got = s.handle("desk-job-get", {"locale": "de", "id": r["job"]["id"]}, "pat@example.test")
    assert got["job"]["status"] == "done" and got["job"]["result"]["batchId"] == "de-1"
    code, x = s.handle("desk-export-get", {"batch_id": "de-1"}, "pat@example.test")
    assert code == 200 and x["export"]["csv"].startswith("word_from") and x["export"]["rows"] == 1
    s.dispatch_status = 422
    code, r = s.handle("desk-job-start", {"locale": "fr", "kind": "export"}, "pat@example.test")
    assert code == 502 and r["job"]["error"] == "engine-did-not-start" and len(s.dispatched) == 1


def test_a_users_job_starts_are_capped_per_day_as_the_worker_caps_them():
    s = _store()
    codes = [s.handle("desk-job-start", {"locale": "de", "kind": "export"}, "pat@example.test")[0] for _ in range(61)]
    assert codes[0] == 200 and set(codes[1:60]) == {409} and codes[60] == 429
    assert s.handle("desk-job-start", {"locale": "fr", "kind": "export"}, "kim@example.test")[0] == 200


def test_a_ref_follows_the_runners_rule():
    s = _store()
    start = lambda ref: s.handle("desk-job-start", {"locale": "de", "kind": "verify", "ref": ref}, "pat@example.test")[0]
    assert start("de-1.2") == 400 and start("run:1") == 400 and start("a" * 121) == 400
    assert start("a" * 120) == 200


def test_plan_submit_and_collect_run_for_all_languages_and_a_file_does_not():
    """The Manager's ruling (U3): one Gemini run per Send; a Weglot file stays one language at a time."""
    s = _store()
    assert s.handle("desk-job-start", {"locale": "all", "kind": "plan"}, "pat@example.test")[0] == 200
    assert s.handle("desk-job-start", {"locale": "all", "kind": "plan"}, "pat@example.test")[0] == 409
    assert s.handle("desk-job-start", {"locale": "all", "kind": "export"}, "pat@example.test")[0] == 400
    code, r = s.handle("desk-job-get", {"locale": "all"}, "pat@example.test")
    assert code == 200 and r["jobs"]["plan"]["locale"] == "all"
    assert s.handle("desk-read", {"locale": "all"}, "pat@example.test")[0] == 400
