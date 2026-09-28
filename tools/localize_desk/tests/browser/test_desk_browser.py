"""Robot click-tests: a real browser drives the desk in the click-test harness.

Why (runbook WO-04, guard G9): three audits of this desk never loaded the page, and every
defect the first real click found had survived them. Hand click-throughs get skipped, so
the clicking is done here, on every commit that touches the desk (the CEL pre-commit hook
runs this file with the monorepo's Python, the only one with Playwright) and in CI.

Each test starts the harness on a free port with the mock Worker in one mode, so the
desk's save logic meets the three situations it must survive: the current Worker (`new`),
one that cannot name its runs (`old`), and a colleague's run winning a race (`race`).
Expected wording comes from COPY.md through `copy_text.t`, never typed here.

Later work orders add their assertions to this file (the state table, colours, tooltips,
one page for all languages, autosave, the Weglot-style rows).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright lives in the monorepo's .venv314; the CEL hook and the "
                           "browser CI job run this file with it")
from playwright.sync_api import sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import harness as H  # noqa: E402

ROWS = 'tbody tr[data-uid]'


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk(mode: str, history: bool = True):
    """The harness on a free port: a temporary copy of docs/, the mock Worker in `mode`."""
    root = H.stage_copy()
    worker = H.MockWorker(root, mode, run_seconds=0.3, history=history)
    server = H.make_server(root, worker, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", root, worker
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(root, ignore_errors=True)


def _open(browser, url: str):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
    return page, errors


def _approve_first_visible(page):
    page.locator(f'{ROWS}:visible [data-act="approve"]').first.click()
    page.locator("#btn-save").wait_for(state="visible")


def _toast(page, text: str, timeout: float = 25000):
    page.locator("#toast-stack").get_by_text(text, exact=False).first.wait_for(timeout=timeout)


def _decisions(root: Path, locale: str = "de") -> dict:
    f = root / "admin" / "localization" / locale / "decisions.json"
    return json.loads(f.read_text())["decisions"] if f.is_file() else {}


def test_the_desk_loads_signed_in_with_every_text(browser):
    with desk("new") as (base, _root, _worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        assert page.locator(ROWS).count() == 823
        assert not errors, errors
        page.close()


def test_approve_and_save_lands_with_the_current_worker(browser):
    with desk("new") as (base, root, _worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        _approve_first_visible(page)
        page.click("#btn-save")
        _toast(page, C.t("save.done.title"))
        saved = _decisions(root)
        assert len(saved) == 1 and next(iter(saved.values()))["tray"] == "csv"
        assert not errors, errors
        page.close()


def test_a_worker_that_cannot_name_runs_is_refused_before_anything_is_sent(browser):
    with desk("old") as (base, root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        _approve_first_visible(page)
        page.click("#btn-save")
        _toast(page, C.t("save.failed.title"))
        assert _decisions(root) == {}
        assert worker.dispatched == [], "the desk dispatched against a Worker that cannot name runs"
        page.close()


@pytest.mark.xfail(strict=True, reason="R67, known gap: with no earlier run to read, the desk "
                   "cannot tell an old Worker from a new one, dispatches, and the save lands "
                   "while it reports Not saved. Reachable only with the pre-2026-09-23 Worker "
                   "on a workflow that has never run; WO-17 retires this save path and deletes "
                   "this test. strict=True: if it starts passing, the gap closed -- remove it.")
def test_known_gap_an_old_worker_with_no_run_history_is_not_refused(browser):
    with desk("old", history=False) as (base, root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        _approve_first_visible(page)
        page.click("#btn-save")
        _toast(page, C.t("save.failed.title"))
        time.sleep(1.0)          # let a dispatched run finish, if one was made
        assert worker.dispatched == [] and _decisions(root) == {}
        page.close()


def test_a_colleagues_run_winning_the_race_is_reported_as_not_saved(browser):
    with desk("race") as (base, root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        _approve_first_visible(page)
        page.click("#btn-save")
        _toast(page, C.t("save.reason.cancelled"))
        assert _decisions(root) == {}
        page.close()


def test_an_open_editor_survives_a_language_switch(browser):
    """Ruling #12: type into an editor, do not leave it, click another language."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        row = page.locator(f"{ROWS}:visible").first
        uid = row.get_attribute("data-uid")
        row.locator('[data-act="edit"]').click()
        box = row.locator("textarea.desk-edit")
        box.fill("WO-04 robot wording")
        page.locator('.desk-locales-strip [data-loc="fr"]').click()
        page.wait_for_url("**/localization/fr/**")
        stored = page.evaluate("() => localStorage.getItem('cel-desk-de')")
        assert "WO-04 robot wording" in json.loads(stored)[uid]["text"]
        page.close()


@pytest.mark.skipif(not os.environ.get("DESK_MEASURE"), reason="a measurement, not a guard: set DESK_MEASURE=1")
def test_record_the_timings(browser):
    """Today's numbers with the CPU slowed 4x, printed for the runbook (WO-08, WO-09 turn
    them into budgets). Run: DESK_MEASURE=1 <python> -m pytest ... -k timings -s"""
    with desk("new") as (base, _root, _worker):
        page = browser.new_page()
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 4})
        t0 = time.monotonic()
        page.goto(base + "/admin/localization/de/")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=60000)
        first = time.monotonic() - t0
        t0 = time.monotonic()
        page.locator('.desk-locales-strip [data-loc="fr"]').click()
        page.wait_for_url("**/localization/fr/**")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=60000)
        switch = time.monotonic() - t0
        nodes = page.evaluate("() => document.getElementsByTagName('*').length")
        print(json.dumps({"first_view_s": round(first, 2), "switch_s": round(switch, 2),
                          "elements": nodes, "cpu_slowdown": 4}))
        page.close()


# ── WO-06: the row-state table (contract §1, "Every state × every action") ──────────
# Walks each state through ✓ and ✦, each clicked twice: the second click is the undo, and
# it must land exactly where the table says (guard G11). States the desk cannot reach by
# clicking (sending, arrived, failed, exported, live) are set the way the engine will set
# them, through `deskIngest`.

ISO = "2026-09-28T10:00:00Z"
# from-state: (after ✓, after ✓ again, after ✦, after ✦ again)
TABLE = {
    "todo":     ("approved", "todo",     "queued", "todo"),
    "approved": ("todo",     "approved", "queued", "approved"),
    "edited":   ("todo",     "edited",   "queued", "edited"),
    "queued":   ("approved", "queued",   "todo",   "queued"),
    "arrived":  ("edited",   "arrived",  "queued", "arrived"),
    "failed":   ("approved", "todo",     "queued", "todo"),     # a decision ends a failure
    "exported": ("todo",     "exported", "queued", "exported"),
    "live":     ("live",     "live",     "queued", "live"),
}


def _row(page, uid):
    return page.locator(f'tr[data-uid="{uid}"]')


def _label(page, uid) -> str:
    return _row(page, uid).locator(".desk-state").inner_text()


def _rec(page, uid) -> dict:
    return page.evaluate("u => (window.deskState()[u] || {})", uid)


def _ingest(page, uid, rec):
    page.evaluate("([u, r]) => window.deskIngest({schema: 'cel-localization-desk/1', locale: 'de', "
                  "decisions: {[u]: r}})", [uid, rec])


def _act(page, uid, act):
    _row(page, uid).locator(f'[data-act="{act}"]').click()


def _put_in(page, uid, state):
    if state in ("approved", "exported", "live"):
        _act(page, uid, "approve")
    if state == "edited":
        _act(page, uid, "edit")
        _row(page, uid).locator("textarea.desk-edit").fill("WO-06 wording of my own")
        _row(page, uid).locator('[data-edit="save"]').click()
    if state in ("queued", "sending"):
        _act(page, uid, "queue")
    if state == "sending":
        _ingest(page, uid, {"sentAt": ISO})
    if state == "arrived":
        _ingest(page, uid, {"arrivedAt": ISO, "text": "WO-06 draft from Gemini"})
    if state == "failed":
        _ingest(page, uid, {"failed": "quota"})
    if state == "exported":
        _ingest(page, uid, {"exportedAt": ISO})
    if state == "live":
        _ingest(page, uid, {"liveAt": ISO})


def _all_rows(page):
    page.select_option("#f-state", "")
    return [page.locator(ROWS).nth(i).get_attribute("data-uid") for i in range(12)]


def test_every_state_through_approve_and_request_and_back(browser):
    with desk("new") as (base, _root, _worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        _all_rows(page)
        wrong = []
        # one fresh row per (state, action) so no case inherits another's history
        pool = [page.locator(ROWS).nth(i).get_attribute("data-uid") for i in range(40)]
        k = 0
        for start, (a1, a2, q1, q2) in TABLE.items():
            for act, first, second in (("approve", a1, a2), ("queue", q1, q2)):
                uid = pool[k]; k += 1
                _put_in(page, uid, start)
                assert C.t(f"status.{start}") in _label(page, uid), (start, _label(page, uid))
                _act(page, uid, act)
                if C.t(f"status.{first}") not in _label(page, uid):
                    wrong.append(f"{start} --{act}--> {_label(page, uid)!r}, table says {first}")
                _act(page, uid, act)
                if C.t(f"status.{second}") not in _label(page, uid):
                    wrong.append(f"{start} --{act} twice--> {_label(page, uid)!r}, table says {second}")
        assert not wrong, "\n".join(wrong)
        assert not errors, errors
        page.close()


def test_requesting_again_records_the_draft_that_was_turned_down(browser):
    """R56: ✦ on an arrived draft must tell Gemini what was rejected, or a re-request repeats
    the same prompt and pays twice. Undo puts the draft back."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        uid = _all_rows(page)[0]
        _put_in(page, uid, "arrived")
        _act(page, uid, "queue")
        rec = _rec(page, uid)
        assert rec.get("rejected") == "WO-06 draft from Gemini" and "text" not in rec
        _act(page, uid, "queue")
        rec = _rec(page, uid)
        assert rec.get("text") == "WO-06 draft from Gemini" and "rejected" not in rec
        page.close()


def test_a_row_in_flight_ignores_the_keyboard(browser):
    """Desk audit P1-4: the buttons are disabled while a row is being sent, but `a` and `r`
    reached it anyway."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        uid = _all_rows(page)[0]
        _put_in(page, uid, "sending")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("j")
        # the proof needs the cursor ON this row, or the test passes for the wrong reason
        assert "is-cursor" in (_row(page, uid).get_attribute("class") or "")
        # "sending" outranks the tray in the label, so read the record after EACH key: the
        # request in flight must stay a request (a then r would cancel out and hide a bug).
        page.keyboard.press("a")
        assert _rec(page, uid).get("tray") == "draft", "a changed a row that is being sent"
        page.keyboard.press("r")
        assert _rec(page, uid).get("tray") == "draft", "r changed a row that is being sent"
        assert C.t("status.sending") in _label(page, uid)
        page.close()


def test_rows_hold_their_place_after_a_bulk_action(browser):
    """Ruling #17, desk audit P1-5: approving the whole flagged view emptied it."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        visible = page.locator(f"{ROWS}:visible")
        n = visible.count()
        assert n > 2
        for i in range(3):
            visible.nth(i).locator("[data-pick]").check()
        page.click("#bulk-approve")
        assert page.locator(f"{ROWS}:visible").count() == n
        page.close()


def test_the_show_counts_respect_the_page_filter(browser):
    """Desk audit P1-9b: an option could promise 38 rows and show none."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-page", "vs-toronto")
        values = page.eval_on_selector_all("#f-state option", "os => os.map(o => o.value)")
        for v in values:
            page.select_option("#f-state", v)
            shown = page.locator(f"{ROWS}:visible").count()
            label = page.eval_on_selector(f'#f-state option[value="{v}"]', "o => o.textContent")
            assert f"({shown})" in label, (v, label, shown)
        page.close()


def test_an_empty_view_offers_a_way_back(browser):
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.fill("#f-q", "zzqq-nothing-matches-this")
        page.locator("#no-rows").wait_for(state="visible")
        page.click("#no-rows-reset")
        assert page.locator(f"{ROWS}:visible").count() == 823
        page.close()
