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


def test_a_page_job_carries_its_page_in_ref_as_json_and_gives_it_back_as_the_object():
    """Desk v2 (CEL-022): translate-page / retranslate / an export for a page. The stored text is canonical."""
    s = _store()
    ref = {"keepEdited": False, "note": "förmlicher", "unit": "a" * 16, "page": "vancouver"}
    code, r = s.handle("desk-job-start", {"locale": "de", "kind": "retranslate", "ref": ref}, "pat@example.test")
    assert code == 200 and r["job"]["ref"] == {"page": "vancouver", "unit": "a" * 16, "note": "förmlicher", "keepEdited": False}
    assert s.jobs[r["job"]["id"]]["ref"] == '{"page":"vancouver","unit":"aaaaaaaaaaaaaaaa","note":"förmlicher","keepEdited":false}'
    assert s.dispatched == [r["job"]["id"]]
    code, got = s.handle("desk-job-get", {"locale": "de"}, "pat@example.test")
    assert code == 200 and got["jobs"]["retranslate"]["ref"]["unit"] == "a" * 16
    code, r2 = s.handle("desk-job-start", {"locale": "es", "kind": "export", "ref": {"page": "vs-toronto"}}, "pat@example.test")
    assert code == 200 and r2["job"]["ref"] == {"page": "vs-toronto"}
    assert s.handle("desk-job-start", {"locale": "pt", "kind": "export"}, "pat@example.test")[0] == 200


def test_a_page_job_is_one_open_job_per_language_whatever_the_page():
    s = _store()
    start = lambda loc, page: s.handle("desk-job-start", {"locale": loc, "kind": "translate-page",
                                                          "ref": {"page": page, "keepEdited": True}}, "pat@example.test")
    assert start("de", "vancouver")[0] == 200
    code, r = start("de", "vs-toronto")
    assert code == 409 and r["job"]["ref"] == {"page": "vancouver", "keepEdited": True}
    assert start("fr", "vancouver")[0] == 200


def test_a_page_job_refuses_what_the_worker_refuses():
    s = _store()
    ok = {"page": "vancouver", "keepEdited": True}
    bad = [
        ("translate-page", None), ("translate-page", "vancouver"), ("translate-page", []),
        ("translate-page", {"page": "home", "keepEdited": True}), ("translate-page", {"page": "vancouver"}),
        ("translate-page", {**ok, "keepEdited": "true"}), ("translate-page", {**ok, "unit": "a" * 16}),
        ("translate-page", {**ok, "langs": ["de"]}), ("retranslate", {**ok, "unit": "A" * 16}),
        ("retranslate", {**ok, "unit": "a" * 16 + "\n"}), ("retranslate", {**ok, "unit": None}),
        ("retranslate", {**ok, "note": ""}), ("retranslate", {**ok, "note": "x" * 501}),
        ("retranslate", {**ok, "note": "a\nb"}), ("retranslate", {**ok, "note": "\ud800"}),
        ("export", {"page": "home"}), ("export", {}), ("export", "vancouver"), ("export", {**ok}),
        ("plan", {"page": "vancouver"}), ("verify", {"page": "vancouver"}),
    ]
    for kind, ref in bad:
        assert s.handle("desk-job-start", {"locale": "de", "kind": kind, "ref": ref}, "pat@example.test")[0] == 400, (kind, ref)
    assert s.handle("desk-job-start", {"locale": "de", "kind": "translate-page"}, "pat@example.test")[0] == 400
    assert s.handle("desk-job-start", {"locale": "all", "kind": "translate-page", "ref": ok}, "pat@example.test")[0] == 400
    assert s.handle("desk-job-start", {"locale": "de", "kind": "translate-page", "amount_usd": 1, "ref": ok},
                    "pat@example.test")[0] == 400
    assert s.dispatched == []
    # A note of 500 UTF-16 units is taken, an emoji counting as two, as the Worker counts it.
    assert s.handle("desk-job-start", {"locale": "de", "kind": "retranslate", "ref": {**ok, "note": "\U0001F600" * 250}},
                    "pat@example.test")[0] == 200
    assert s.handle("desk-job-start", {"locale": "fr", "kind": "retranslate", "ref": {**ok, "note": "\U0001F600" * 251}},
                    "pat@example.test")[0] == 400


def test_plan_submit_and_collect_run_for_all_languages_and_a_file_does_not():
    """The Manager's ruling (U3): one Gemini run per Send; a Weglot file stays one language at a time."""
    s = _store()
    assert s.handle("desk-job-start", {"locale": "all", "kind": "plan"}, "pat@example.test")[0] == 200
    assert s.handle("desk-job-start", {"locale": "all", "kind": "plan"}, "pat@example.test")[0] == 409
    assert s.handle("desk-job-start", {"locale": "all", "kind": "export"}, "pat@example.test")[0] == 400
    code, r = s.handle("desk-job-get", {"locale": "all"}, "pat@example.test")
    assert code == 200 and r["jobs"]["plan"]["locale"] == "all"
    assert s.handle("desk-read", {"locale": "all"}, "pat@example.test")[0] == 400


# ── the client's translation rules (monorepo CEL-038 Worker, CEL-043 stand-in) ─────────────────
# The contract, answer for answer against the real Worker, is the monorepo's differential test; these are the
# CEL-side guards the rules page's click tests lean on.
PAT, KIM = "pat@example.test", "kim@example.test"


def _rules(store, action, **body):
    return store.handle(f"desk-rules-{action}", body, PAT)


def _publish(store, scope, text, base, who=PAT):
    return store.handle("desk-rules-write", {"scope": scope, "body": text, "baseVersion": base}, who)


def test_a_scope_nobody_published_reads_as_version_zero_with_no_body():
    s = _store()
    code, r = _rules(s, "read", scope="de")
    assert (code, r["version"], r["body"]) == (200, 0, None) and "updatedBy" not in r
    assert _rules(s, "history", scope="de")[1]["history"] == []


def test_a_publish_moves_the_version_and_a_restore_is_a_write_of_an_old_body():
    s = _store()
    assert _publish(s, "de", "One", 0, PAT)[1]["version"] == 1
    code, r = _publish(s, "de", "Two", 1, KIM)
    assert (code, r["version"], r["updatedBy"]) == (200, 2, KIM)
    code, r = _publish(s, "de", "One", 2)                       # restore v1: v3, not a rewind
    assert (code, r["version"]) == (200, 3)
    hist = _rules(s, "history", scope="de")[1]["history"]
    assert [(h["version"], h["body"]) for h in hist] == [(3, "One"), (2, "Two"), (1, "One")]
    assert _rules(s, "read", scope="de")[1]["body"] == "One"


def test_a_stale_base_is_a_409_with_the_winner_and_the_text_in_use_is_never_a_conflict():
    s = _store()
    _publish(s, "fr", "One", 0)
    _publish(s, "fr", "Two", 1, KIM)
    code, r = _publish(s, "fr", "Three", 1)
    assert code == 409 and r["current"]["version"] == 2 and r["current"]["updatedBy"] == KIM
    assert _publish(s, "fr", "Three", 0)[0] == 409              # base 0 on a scope that is there
    for base in (0, 1, 2, 9):                                  # Kim's own text, whatever the base: nothing to publish
        code, r = _publish(s, "fr", "Two", base)
        assert (code, r.get("unchanged"), r["version"]) == (200, True, 2)
    assert len(_rules(s, "history", scope="fr")[1]["history"]) == 2
    code, r = _publish(s, "es", "x", 3)                         # nothing there at all
    assert code == 409 and r["current"] == {"scope": "es", "version": 0, "body": None}


def test_the_scope_rule_is_the_workers_and_there_is_no_draft_route():
    s = _store()
    for ok in ("global", "de", "glossary:ja", "brief:vancouver:ar", "brief:vs-toronto:de"):
        assert _rules(s, "read", scope=ok)[0] == 200, ok
    for bad in ("", "zz", "DE", "glossary:zz", "glossary:de:de", "brief:de", "brief:home:de", "foo:de",
                "x:vancouver:de", "glossary:vancouver:de", None, 7, ["de"]):
        for action, extra in (("read", {}), ("write", {"body": "x", "baseVersion": 0}), ("history", {})):
            code, r = _rules(s, action, scope=bad, **extra)
            assert (code, r["error"]) == (400, "invalid: unknown rules scope"), (action, bad)
    assert _rules(s, "read")[0] == 400
    assert s.handle("desk-rules-draft", {"scope": "de", "body": "x"}, PAT) == (400, {"error": "invalid action"})
    assert s.rules == {}


def test_a_body_follows_the_workers_rules_in_bytes_and_in_javascripts_idea_of_blank():
    s = _store()
    for bad in (None, 7, ["x"], "", " \n\t", " ", "﻿", " "):
        assert _publish(s, "ko", bad, 0)[1]["error"] in ("invalid: body must be text", "invalid: a rules block cannot be empty")
    assert _publish(s, "ko", "a\ud800", 0)[1]["error"] == "invalid: body is not valid text"
    for base in (-1, 1.5, "0", True, None, 2 ** 53, 10 ** 400):    # the last: JavaScript reads Infinity; no OverflowError here
        assert _publish(s, "ko", "x", base)[1]["error"] == "invalid: bad baseVersion"
    assert s.rules == {}
    for i, odd in enumerate(("\u0085", "\u001c", "᠎", "​")):   # not blank in JavaScript, blank to Python's strip()
        assert _publish(s, "ko", odd, i)[0] == 200, repr(odd)
    assert _publish(s, "ar", "a" * 262144, 0)[0] == 200 and _publish(s, "ar", "a" * 262145, 1)[0] == 400
    assert _publish(s, "ja", "語" * 87381 + "a", 0)[0] == 200 and _publish(s, "ja", "語" * 87382, 1)[0] == 400
    assert _publish(s, "fr", "\U0001F600" * 65536, 0)[0] == 200 and _publish(s, "fr", "\U0001F600" * 65537, 1)[0] == 400


def test_the_history_keeps_the_last_fifty_versions_newest_first():
    s = _store()
    for i in range(52):
        assert _publish(s, "it", f"Version {i + 1}", i)[0] == 200
    hist = _rules(s, "history", scope="it")[1]["history"]
    assert [h["version"] for h in hist] == list(range(52, 2, -1)) and hist[0]["body"] == "Version 52"


def test_a_name_comes_from_the_user_store_for_the_rules_answers_only():
    users = [{"email": PAT, "firstName": " Pat ", "lastName": "Hoffmann"}, {"email": KIM, "firstName": "", "lastName": None}]
    s = DeskStore({U1: {"vancouver"}}, users=users)
    _publish(s, "de", "One", 0, PAT)
    _publish(s, "de", "Two", 1, KIM)
    assert _rules(s, "history", scope="de")[1]["history"][1]["byName"] == "Pat Hoffmann"
    assert "byName" not in _rules(s, "read", scope="de")[1]                  # Kim has no name
    code, r = _publish(s, "de", "Three", 1, KIM)
    assert code == 409 and "byName" not in r["current"]
    _publish(s, "de", "Four", 2, PAT)
    assert _rules(s, "read", scope="de")[1]["byName"] == "Pat Hoffmann"
    nameless = _store()
    assert nameless.users == [] and "byName" not in _publish(nameless, "de", "One", 0)[1]
    _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv"}}])
    assert "byName" not in s.handle("desk-history", {"locale": "de", "unit": U1}, PAT)[1]["history"][0]


def test_the_rules_are_apart_from_the_desks_decisions():
    s = _store()
    _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv", "text": "Hallo"}}])
    before = s.handle("desk-read", {"locale": "de"}, PAT)[1]["decisions"]
    _publish(s, "de", "Rules", 0)
    after = s.handle("desk-read", {"locale": "de"}, PAT)[1]
    assert after["decisions"] == before and "rules" not in after and "version" not in after


def test_the_harness_answers_the_rules_actions_and_a_fault_can_be_set_on_them():
    root = H.stage_copy()
    try:
        worker = H.MockWorker(root)
        code, r = worker.handle({"action": "desk-rules-write", "scope": "de", "body": "Rules", "baseVersion": 0})
        assert (code, r["version"], r["updatedBy"]) == (200, 1, "reviewer@example.test")
        read = worker.handle({"action": "desk-rules-read", "scope": "de"})[1]
        assert read["body"] == "Rules" and read["byName"] == "Test Reviewer"      # the harness signs in as Test Reviewer
        code, r = worker.store.handle("desk-rules-write", {"scope": "de", "body": "Other", "baseVersion": 0}, "kim@example.test")
        assert code == 409 and r["current"]["byName"] == "Test Reviewer"
        assert len(worker.handle({"action": "desk-rules-history", "scope": "de"})[1]["history"]) == 1
        worker.action_faults["desk-rules-write"] = {"status": 429, "error": "over the cap"}
        assert worker.handle({"action": "desk-rules-write", "scope": "de", "body": "More", "baseVersion": 1}) == \
            (429, {"ok": False, "error": "over the cap"})
        assert worker.handle({"action": "desk-rules-read", "scope": "de"})[0] == 200          # only the named action
        assert worker.handle({"action": "desk-rules-draft", "scope": "de"})[0] == 400
        assert worker.calls.count("desk-rules-write") == 2
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
