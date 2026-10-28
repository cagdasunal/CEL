"""The harness's stand-in for the Worker's desk storage (runbook WO-17 / WO-33).

The full contract -- every rule, answer for answer against the real Worker -- is the
monorepo's differential test (scripts/tests/test_desk_standin_parity.py). These are the
CEL-side guards that run in CEL's own CI: the rules the desk's save path leans on, and the
harness wiring.
"""
from __future__ import annotations

import json
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


def test_desk_summary_is_not_an_action_any_more():
    """CEL-054: the first desk's index counts are gone from the Worker; the stand-in refuses the action as it does."""
    s = _store()
    _write(s, [{"unit": U1, "page": "vancouver", "base": 0, "record": {"tray": "csv", "text": "Hallo"}}])
    for body in ({"locale": "de"}, {"locale": "de", "flagged": {"de": [U1]}}):
        code, r = s.handle("desk-summary", body, "pat@example.test")
        assert code == 400 and r.get("ok") is not True and "languages" not in r


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
    page = {"page": "vancouver", "keepEdited": True}
    _c, r = s.handle("desk-job-start", {"locale": "de", "kind": "translate-page", "ref": page}, "pat@example.test")
    s.jobs[r["job"]["id"]]["created_at"] = _stamp(34)
    _c, got = s.handle("desk-job-get", {"locale": "de"}, "pat@example.test")
    assert got["jobs"]["translate-page"]["status"] == "queued"           # 34 minutes: left alone
    s.jobs[r["job"]["id"]].update(status="running", started_at=_stamp(36))
    _c, got = s.handle("desk-job-get", {"locale": "de"}, "pat@example.test")
    assert got["jobs"]["translate-page"]["status"] == "failed" and got["jobs"]["translate-page"]["error"] == "engine-never-answered"
    assert s.handle("desk-job-start", {"locale": "de", "kind": "translate-page", "ref": page}, "pat@example.test")[0] == 200


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


def test_the_first_desks_kinds_are_refused_with_what_they_used_to_take():
    """CEL-054: verify, plan, submit and collect are gone, with their batch / run refs and their amount."""
    s = _store()
    for kind, extra in (("verify", {"ref": "de-1"}), ("verify", {}), ("plan", {}), ("submit", {"amount_usd": 3.42}),
                        ("collect", {"ref": "20260929T101500Z"}), ("collect", {"ref": "run:1"})):
        code, r = s.handle("desk-job-start", {"locale": "de", "kind": kind, **extra}, "pat@example.test")
        assert (code, r["error"]) == (400, "invalid: kind"), (kind, extra)
    assert s.jobs == {} and s.dispatched == []
    code, r = s.handle("desk-job-start", {"locale": "de", "kind": "export", "amount_usd": 1}, "pat@example.test")
    assert (code, r["error"]) == (400, "invalid: a job carries no amount")


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


def test_the_locale_all_is_not_a_language_to_any_job():
    """CEL-054: one Gemini run for every language went with plan, submit and collect."""
    s = _store()
    ref = {"page": "vancouver", "keepEdited": True}
    for kind, extra in (("export", {}), ("translate-page", {"ref": ref}), ("retranslate", {"ref": ref}),
                        ("plan", {}), ("submit", {"amount_usd": 1.5})):
        assert s.handle("desk-job-start", {"locale": "all", "kind": kind, **extra}, "pat@example.test")[0] == 400, kind
    assert s.handle("desk-job-get", {"locale": "all"}, "pat@example.test")[0] == 400
    assert s.handle("desk-read", {"locale": "all"}, "pat@example.test")[0] == 400
    assert s.dispatched == []


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
    for ok in ("global", "de", "glossary:ja", "words:ko", "words:ar", "brief:vancouver:ar", "brief:vs-toronto:de"):
        assert _rules(s, "read", scope=ok)[0] == 200, ok
    for bad in ("", "zz", "DE", "glossary:zz", "glossary:de:de", "brief:de", "brief:home:de", "foo:de",
                "x:vancouver:de", "glossary:vancouver:de", "words:zz", "words:xx", "words:", "words", "words:de:x",
                "WORDS:de", "words:vancouver:de", None, 7, ["de"]):
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


# ── CEL-112: the changes-file reader (desk-rules-import-read / desk-rules-import-apply) ──────────────────────────────
DE_RULES = '# German\n- Use formal "Sie", never "du". [DE-3]\n- Write prices with a space before the euro sign. [DE-7]\n- Avoid exclamation marks in headings. [DE-9]\n'
DE_WORDS = "| Term | Translation | Type |\n|---|---|---|\n| exam prep | Prüfungsvorbereitung | Always translate as |\n| Pacific Beach |  | Keep as is |\n"
ALL8 = ["de", "fr", "es", "pt", "it", "ja", "ko", "ar"]


def _chg(kind, language="de", target_id=None, term=None, before=None, after=None, type_=None, src="line"):
    return {"language": language, "kind": kind, "target_id": target_id, "term": term, "before": before, "after": after,
            "type": type_, "matched_by": "id" if target_id else None, "source_text": src}


def _read_file(s, answer, text="## German\n- ADD: x\n", langs=("de",)):
    s.import_answer = answer
    return s.handle("desk-rules-import-read", {"text": text, "languages": list(langs)}, PAT)


def _apply(s, changes, bases, who=PAT):
    return s.handle("desk-rules-import-apply", {"changes": changes, "bases": bases}, who)


def _seeded():
    s = _store()
    _publish(s, "de", DE_RULES, 0)
    _publish(s, "words:de", DE_WORDS, 0)
    _publish(s, "fr", "- Use vous. [FR-5]\n", 0)
    return s


def _snapshot(s):
    return json.dumps([s.rules, s.rules_history], sort_keys=True)


def test_words_scope_has_the_same_eight_languages_as_the_worker_and_stores_like_any_scope():
    s = _store()
    for i, lang in enumerate(ALL8):
        assert _publish(s, f"words:{lang}", DE_WORDS, 0)[1]["version"] == 1, lang
        assert _rules(s, "read", scope=f"words:{lang}")[1]["body"] == DE_WORDS
    assert _publish(s, "words:zz", DE_WORDS, 0)[0] == 400
    assert _rules(s, "history", scope="words:de")[1]["history"][0]["version"] == 1


def test_import_read_proposes_checks_in_code_and_writes_nothing():
    s = _seeded()
    before = _snapshot(s)
    good = [_chg("edit_rule", target_id="DE-7", before="x", after="Write prices as 1.234,50 EUR."),
            _chg("add_rule", after="Write dates as 31.12.2026."),
            _chg("remove_rule", target_id="DE-9"),
            _chg("add_word", term="homestay", after="Gastfamilie", type_="Always translate as")]
    bad = [_chg("edit_rule", target_id="DE-99", after="x", src="no such id"),
           _chg("edit_rule", target_id="FR-5", after="x", src="other language's id"),
           _chg("add_rule", after="   ", src="empty"),
           _chg("add_word", term="exam prep", after="y", type_="Always translate as", src="exists"),
           _chg("edit_word", term="nope", after="y", type_="Always translate as", src="missing term"),
           _chg("add_word", term="spa", after="y", type_="Whatever", src="bad type"),
           _chg("add_word", term="spa", after="y", src="no type"),
           _chg("add_word", term="spa", after="", type_="Always translate as", src="no translation"),
           _chg("add_rule", language="xx", after="x", src="unknown language"),
           _chg("add_rule", language="fr", after="x", src="language not ticked"),
           _chg("bogus", src="no such kind")]
    code, r = _read_file(s, {"changes": good + bad, "unplaced": [{"source_text": "?", "language": "tlh", "reason": "made up"}]})
    assert code == 200 and r["api"] == 1 and r["model"] == "gemini-3.1-pro-preview" and r["usage"] == {"promptTokens": 0, "outputTokens": 0}
    assert [(c["kind"], c["target_id"], c["before"], c["after"]) for c in r["changes"]] == [
        ("edit_rule", "DE-7", "Write prices with a space before the euro sign.", "Write prices as 1.234,50 EUR."),
        ("add_rule", None, None, "Write dates as 31.12.2026."), ("remove_rule", "DE-9", "Avoid exclamation marks in headings.", None),
        ("add_word", None, None, "Gastfamilie")]
    assert r["changes"][1]["assigned_id"] == "DE-10"
    assert r["unplaced"] == [{"source_text": "?", "language": None, "reason": "unreadable"}]     # an invented reason/language is clamped
    assert [(c["source_text"], c["reason"]) for c in r["problems"]] == [
        ("no such id", "rule_not_found"), ("other language's id", "rule_not_found"), ("empty", "empty_rule"),
        ("exists", "already_exists"), ("missing term", "term_not_found"), ("bad type", "type_unclear"), ("no type", "type_unclear"),
        ("no translation", "empty_rule"), ("unknown language", "unknown_language"), ("language not ticked", "language_not_requested"),
        ("no such kind", "bad_shape")]
    assert r["bases"] == {"de": 1, "words:de": 1}
    assert _snapshot(s) == before                                  # reading writes nothing


def test_import_read_flags_a_duplicate_and_a_conflicting_term_and_a_rule_changed_twice():
    s = _seeded()
    a = _chg("add_word", term="spa", after="Spa", type_="Always translate as", src="first")
    answer = {"changes": [a, _chg("add_word", term="SPA", after="Spa", type_="Always translate as", src="dup"),
                          _chg("add_word", term="spa", after="Spa2", type_="Always translate as", src="conflict"),
                          _chg("edit_rule", target_id="DE-3", after="One.", src="r1"),
                          _chg("remove_rule", target_id="DE-3", src="r2")], "unplaced": []}
    code, r = _read_file(s, answer)
    assert [c["source_text"] for c in r["changes"]] == ["r1", "first"] or [c["source_text"] for c in r["changes"]] == []
    assert sorted((c["source_text"], c["reason"]) for c in r["problems"]) == sorted(
        [("first", "conflict"), ("dup", "conflict"), ("conflict", "conflict"), ("r1", "conflict"), ("r2", "conflict")])


def test_a_word_is_stored_as_the_ruling_says_keep_as_is_term_only_always_translate_as_both_search_keyword_the_phrase():
    s = _seeded()
    code, r = _read_file(s, {"changes": [
        _chg("add_word", term="beach club", after="Beach Club", type_="Keep as is", src="keep"),
        _chg("add_word", term="homestay", after="Gastfamilie", type_="Always translate as", src="always"),
        _chg("add_word", term="Sprachreise", type_="Search keyword", src="keyword"),
        _chg("add_word", term="English", after="Englisch lernen", type_="Search keyword", src="keyword, English term first"),
        _chg("edit_word", term="exam prep", after="Examen", src="type kept"),
    ], "unplaced": []})
    assert [(c["source_text"], c["term"], c["after"], c["type"]) for c in r["changes"]] == [
        ("keep", "beach club", None, "Keep as is"), ("always", "homestay", "Gastfamilie", "Always translate as"),
        ("keyword", "Sprachreise", None, "Search keyword"), ("keyword, English term first", "Englisch lernen", None, "Search keyword"),
        ("type kept", "exam prep", "Examen", "Always translate as")]
    assert r["changes"][4]["before"] == "Prüfungsvorbereitung" and r["changes"][0]["before"] is None
    code, r = _apply(s, [c for c in r["changes"]], {"words:de": 1})
    assert code == 200 and s.rules["words:de"]["body"] == (
        "| Term | Translation | Type |\n|---|---|---|\n| exam prep | Examen | Always translate as |\n| Pacific Beach |  | Keep as is |\n"
        "| beach club |  | Keep as is |\n| homestay | Gastfamilie | Always translate as |\n| Sprachreise |  | Search keyword |\n"
        "| Englisch lernen |  | Search keyword |\n")
    code, r = _apply(s, [_chg("edit_word", term="Sprachreise", after="Sprachreise", type_="Always translate as")], {"words:de": 2})
    assert code == 200 and "| Sprachreise | Sprachreise | Always translate as |\n" in s.rules["words:de"]["body"]      # a phrase becomes a glossary row by Type
    assert _apply(s, [_chg("edit_word", term="Englisch lernen", after="x", type_="Search keyword")], {"words:de": 3})[1]["problems"][0]["reason"] == "term_not_found"   # the phrase IS the key


def test_import_read_refuses_over_64_kb_of_utf8_and_a_bad_request_and_a_bad_reader_answer():
    s = _seeded()
    s.import_answer = {"changes": [], "unplaced": []}
    ok = lambda text, langs=("de",): s.handle("desk-rules-import-read", {"text": text, "languages": list(langs)}, PAT)
    assert ok("a" * 65536)[0] == 200 and ok("a" * 65537)[0] == 413
    assert ok("語" * 21845)[0] == 200 and ok("語" * 21846)[0] == 413           # 3 bytes each: bytes, not characters
    assert ok("a" * 65537) == (413, {"ok": False, "error": "invalid: the upload is over 65536 bytes"})
    for bad in (None, 7, "", " \n", "a\ud800"):
        assert ok(bad)[0] == 400, repr(bad)
    assert ok("") == (400, {"ok": False, "error": "invalid: the upload is empty"})
    assert ok("a\ud800") == (400, {"ok": False, "error": "invalid: the upload is not valid text"})
    for langs in ((), ("xx",), ("zz",)):
        assert ok("x", langs) == (400, {"ok": False, "error": "invalid: name 1 to 8 desk languages"}), langs
    assert ok("x", ("de", "de"))[0] == 200                                         # the same language twice is read once
    assert s.handle("desk-rules-import-read", {"text": "x", "languages": "de"}, PAT)[0] == 400
    s.reader_configured = False
    assert ok("x") == (503, {"ok": False, "error": "reader not configured"})
    s.reader_configured = True
    for answer, status, error in (({"changes": "nope", "unplaced": []}, 502, "the reader answer had the wrong shape"),
                                  ("Sure! here you go", 502, "the reader answer was not readable"),
                                  ("```json\n{\"changes\":[],\"unplaced\":[]}\n```", 200, None)):
        s.import_answer = answer
        assert ok("x")[0] == status and (error is None or ok("x")[1]["error"] == error), answer
    s.import_answer = lambda text, langs: {"changes": [], "unplaced": [{"source_text": text, "language": None, "reason": "unreadable"}]}
    assert ok("hello")[1]["unplaced"][0]["source_text"] == "hello"
    s.import_answer = None
    s.import_status = 500
    assert ok("x") == (502, {"ok": False, "error": "the reader answered 500"})
    s.import_status, s.import_fault = 200, "timeout"
    assert ok("x") == (504, {"ok": False, "error": "the reader timed out"})
    s.import_fault = "unreachable"
    assert ok("x") == (502, {"ok": False, "error": "the reader could not be reached"})
    s.import_fault, s.import_usage = None, {"promptTokenCount": 1000, "candidatesTokenCount": 200, "thoughtsTokenCount": 300}
    assert ok("x")[1]["usage"] == {"promptTokens": 1000, "outputTokens": 500}
    assert s.import_calls[-1] == ("x", ("de",)) and ("a" * 65537, ("de",)) not in s.import_calls   # refused uploads never reached the reader


def test_import_apply_writes_every_language_at_once_one_version_each():
    s = _seeded()
    changes = [_chg("edit_rule", target_id="DE-7", after="Write prices as 1.234,50 EUR."),
               _chg("add_rule", after="Write dates as 31.12.2026."), _chg("remove_rule", target_id="DE-9"),
               _chg("add_word", term="homestay", after="Gastfamilie", type_="Always translate as"),
               _chg("remove_word", term="exam prep"),
               _chg("edit_rule", language="fr", target_id="FR-5", after="Use vous, never tu."),
               _chg("add_word", language="it", term="Pacific Beach", type_="Keep as is")]
    code, r = _apply(s, changes, {"de": 1, "words:de": 1, "fr": 1, "words:it": 0}, KIM)
    assert code == 200 and r["updatedBy"] == KIM and r["applied"] == 7
    assert r["versions"] == {"de": 2, "words:de": 2, "fr": 2, "words:it": 1}
    assert r["assigned"] == [{"language": "de", "id": "DE-10"}]
    assert s.rules["de"]["body"] == ('# German\n- Use formal "Sie", never "du". [DE-3]\n'
                                     '- Write prices as 1.234,50 EUR. [DE-7]\n- Write dates as 31.12.2026. [DE-10]\n')
    assert s.rules["words:de"]["body"] == ("| Term | Translation | Type |\n|---|---|---|\n| Pacific Beach |  | Keep as is |\n"
                                           "| homestay | Gastfamilie | Always translate as |\n")
    assert s.rules["fr"]["body"] == "- Use vous, never tu. [FR-5]\n"
    assert s.rules["words:it"]["body"] == "| Term | Translation | Type |\n|---|---|---|\n| Pacific Beach |  | Keep as is |\n"
    assert s.rules["de"]["updated_by"] == KIM
    assert [h["version"] for h in _rules(s, "history", scope="de")[1]["history"]] == [2, 1]    # one history row each
    assert _apply(s, [_chg("edit_rule", target_id="DE-3", after='Use formal "Sie", never "du". ')], {"de": 2}) == (
        400, {"ok": False, "error": "invalid: some changes do not fit the current rules", "problems": [
            {"reason": "unchanged", "source_text": "line", "change": _chg("edit_rule", target_id="DE-3", after='Use formal "Sie", never "du". ')}]})


def test_import_apply_never_reuses_a_removed_rules_number():
    s = _seeded()
    assert _apply(s, [_chg("remove_rule", target_id="DE-9")], {"de": 1})[0] == 200
    assert _apply(s, [_chg("add_rule", after="New.")], {"de": 2})[0] == 200
    assert s.rules["de"]["body"].splitlines()[-1] == "- New. [DE-10]"                  # DE-9 is gone for good, 10 is next
    assert _apply(s, [_chg("remove_rule", target_id="DE-10")], {"de": 3})[0] == 200
    assert _apply(s, [_chg("add_rule", after="Newer.")], {"de": 4})[0] == 200
    assert s.rules["de"]["body"].splitlines()[-1] == "- Newer. [DE-11]"                # nor the number of a rule just removed


def test_import_apply_is_all_or_nothing_a_stale_base_on_one_scope_is_a_409_and_nothing_moves():
    s = _seeded()
    _publish(s, "fr", "- Use vous, never tu. [FR-5]\n", 1, KIM)                       # Kim moves fr to v2 first
    before = _snapshot(s)
    changes = [_chg("add_rule", after="A new German rule."), _chg("add_rule", language="fr", after="New fr rule.")]
    code, r = _apply(s, changes, {"de": 1, "fr": 1})
    assert (code, r) == (409, {"ok": False, "error": "someone published these rules first", "api": 1, "stale": ["fr"],
                               "current": {"de": 1, "fr": 2}})
    assert _snapshot(s) == before                                                     # de, the fresh one, was not written either
    assert _apply(s, changes, {"de": 1, "fr": 2})[0] == 200
    assert _apply(s, [_chg("add_word", language="es", term="a", after="b", type_="Always translate as")], {"words:es": 1})[0] == 409   # base 1 on a scope that is not there
    assert "words:es" not in s.rules


def test_import_apply_rechecks_in_code_refuses_bad_requests_and_writes_nothing_on_any_refusal():
    s = _seeded()
    before = _snapshot(s)
    ok_chg = _chg("add_rule", after="Fine.")
    for changes, bases, why in (
            ([ok_chg, _chg("edit_rule", target_id="DE-99", after="x")], {"de": 1}, ["rule_not_found"]),
            ([ok_chg, _chg("add_rule", after=" ")], {"de": 1}, ["empty_rule"]),
            ([ok_chg, _chg("add_word", term="exam prep", after="y", type_="Always translate as")], {"de": 1, "words:de": 1}, ["already_exists"]),
            ([ok_chg, _chg("edit_word", term="exam prep", after="y"), _chg("remove_word", term="exam prep")],
             {"de": 1, "words:de": 1}, ["conflict", "conflict"]),
            ([_chg("remove_rule", target_id="DE-3"), _chg("remove_rule", target_id="DE-7"), _chg("remove_rule", target_id="DE-9"),
              _chg("remove_rule", target_id="DE-9")], {"de": 1}, ["duplicate"])):
        code, r = _apply(s, changes, bases)
        assert code == 400 and r["error"] == "invalid: some changes do not fit the current rules", (why, r)
        assert [p["reason"] for p in r["problems"]] == why, (why, r)
        assert _snapshot(s) == before, why
    code, r = _apply(s, [_chg("remove_rule", language="fr", target_id="FR-5")], {"fr": 1})      # the last rule: nothing left
    assert code == 400 and [p["reason"] for p in r["problems"]] == ["empty_result"]
    assert _snapshot(s) == before
    assert _apply(s, [ok_chg], {})[1]["error"] == "invalid: no base version for de"
    assert _apply(s, [], {"de": 1})[1]["error"] == "invalid: send 1 to 500 changes"
    assert _apply(s, [ok_chg], None)[1]["error"] == "invalid: bases must name each language's version"
    assert _apply(s, [_chg("add_rule", language="zz", after="x")], {"zz": 0})[1]["error"] == "invalid: no change names a desk language"
    for changes, bases in (("x", {}), ([ok_chg], {"de": -1}), ([ok_chg], {"de": "1"}), ([ok_chg], {"de": 10 ** 400}),
                           ([_chg("bogus")], {"de": 1}), ([ok_chg, 7], {"de": 1})):
        assert _apply(s, changes, bases)[0] == 400, (changes, bases)
    assert _snapshot(s) == before
    assert _apply(s, [ok_chg, dict(ok_chg, body="EVIL")], {"de": 1, "body": "EVIL"})[0] == 400      # the same rule twice: refused
    code, r = _apply(s, [ok_chg], {"de": 1.0})
    assert code == 200 and "EVIL" not in s.rules["de"]["body"]                                       # JSON 1.0 is 1


def test_the_import_answers_and_the_rules_actions_are_apart_from_each_other():
    s = _seeded()
    assert s.handle("desk-rules-import-draft", {}, PAT) == (400, {"error": "invalid action"})
    assert _apply(s, [_chg("add_rule", after="Fine.")], {"de": 1})[0] == 200
    assert _rules(s, "read", scope="de")[1]["version"] == 2 and _rules(s, "read", scope="glossary:de")[1]["version"] == 0
