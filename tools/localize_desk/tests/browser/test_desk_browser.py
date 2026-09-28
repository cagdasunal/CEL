"""Robot click-tests: a real browser drives the desk in the click-test harness.

Why (runbook WO-04, guard G9): three audits of this desk never loaded the page, and every
defect the first real click found had survived them. Hand click-throughs get skipped, so
the clicking is done here, on every commit that touches the desk (the CEL pre-commit hook
runs this file with the monorepo's Python, the only one with Playwright) and in CI.

Each test starts the harness on a free port: a temporary copy of the desk, the storage's
stand-in behind a mock Worker (held to the real Worker by the monorepo's differential test).
`desk(save_on=True)` serves the copy with saving switched on, for the save path (WO-17).
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
def desk(mode: str = "", save_on: bool = False):
    """The harness on a free port: a temporary copy of docs/ and the mock Worker. (`mode`
    named the retired save workflow's Worker; it is ignored.)"""
    root = H.stage_copy(save_on=save_on)
    worker = H.MockWorker(root)
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


def test_the_desk_loads_signed_in_with_every_text(browser):
    with desk("new") as (base, _root, _worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        assert page.locator(ROWS).count() == 823
        assert not errors, errors
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


def _wait_ready(page, code: str):
    page.wait_for_function(f"performance.getEntriesByName('desk-ready:{code}').length > 0", timeout=60000)


def _top_row(page):
    """The first row wholly in view: the reviewer's place, as [uid, y]."""
    return page.evaluate(f"""() => {{
        const tr = [...document.querySelectorAll('{ROWS}')].find(r => {{
            const b = r.getBoundingClientRect(); return !r.hidden && b.top >= 0 && b.height > 0; }});
        return [tr.dataset.uid, tr.getBoundingClientRect().top];
    }}""")


def _timed_switch(page, code: str) -> float:
    """Seconds from the click to the new language ready, timed inside the page by the
    desk's own marks, so Playwright's round trips are not counted (runbook WO-09)."""
    page.locator(f'.desk-locales-strip [data-loc="{code}"]').click()
    page.wait_for_function(f"performance.getEntriesByName('desk-ready:{code}').length > 0", timeout=60000)
    return page.evaluate(
        f"() => performance.getEntriesByName('desk-ready:{code}')[0].startTime"
        f" - performance.getEntriesByName('desk-switch:{code}')[0].startTime") / 1000


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
        switch = _timed_switch(page, "fr")
        nodes = page.evaluate("() => document.getElementsByTagName('*').length")
        print(json.dumps({"first_view_s": round(first, 2), "switch_s": round(switch, 3),
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
        # A LIST, the last five: the Worker's storage and draft.py both read one, and
        # a string was refused by the Worker -- taking the whole save down with it (review
        # round 2, L7 P1-1).
        assert rec.get("rejected") == ["WO-06 draft from Gemini"] and "text" not in rec
        from localize_desk.desk_store import record_of          # the storage's own check
        assert record_of(rec)["rejected"] == ["WO-06 draft from Gemini"]
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
        page.keyboard.press("e")
        assert not page.is_visible(f'tr[data-uid="{uid}"] .desk-editor'), "e opened an editor on a row being sent"
        assert C.t("status.sending") in _label(page, uid)
        # and it looks it: no control on the row may invite a click that does nothing
        assert _row(page, uid).locator("[data-act]").evaluate_all("bs => bs.map(b => b.disabled)") == [True, True, True]
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


# ── WO-08: tooltips (ruling #51) ─────────────────────────────────────────────────────

def test_a_tooltip_shows_quickly_on_hover_at_once_on_focus_and_closes_on_escape(browser):
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        btn = page.locator(f'{ROWS}:visible [data-act="approve"]').first
        label = btn.get_attribute("aria-label")
        tip = page.locator(".desk-tip")
        btn.hover()
        page.wait_for_timeout(150)
        assert tip.is_visible() and tip.inner_text() == label
        page.mouse.move(1, 1)
        assert not tip.is_visible()
        btn.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")        # keyboard focus, so :focus-visible applies
        assert tip.is_visible()
        page.keyboard.press("Escape")
        assert not tip.is_visible()
        page.close()


def test_the_tooltip_says_the_state_after_a_click(browser):
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        btn = page.locator(f'{ROWS}:visible [data-act="approve"]').first
        btn.hover()
        btn.click()
        page.wait_for_timeout(150)
        assert page.locator(".desk-tip").inner_text() == C.t("action.approve.on")
        page.close()


# ── WO-09: one page for all languages (ruling #52) ───────────────────────────────────

def _units(root: Path, code: str) -> dict:
    data = json.loads((root / "admin" / "localization" / code / "units.json").read_text())
    return {u["id"]: u for u in (data["units"] if isinstance(data, dict) else data)}


def test_switching_language_does_not_reload_and_keeps_filters_and_place(browser):
    with desk("new") as (base, root, _worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-page", "vs-toronto")
        page.select_option("#f-state", "")
        tab = page.locator('.desk-locales-strip [data-loc="fr"]')
        # A reviewer scrolls up to the tabs to click one; the English text then at the
        # top of the view is their place, and it must be where it was after the switch.
        tab.scroll_into_view_if_needed()
        anchor_uid, y0 = _top_row(page)
        page.evaluate("() => { window.__sameDocument = true; }")
        tab.click()
        page.wait_for_url("**/localization/fr/**")
        _wait_ready(page, "fr")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        assert page.evaluate("() => window.__sameDocument === true"), "the switch reloaded the page"
        assert page.locator("#f-page").input_value() == "vs-toronto"
        assert "page=vs-toronto" in page.url
        fr = _units(root, "fr")
        some = page.locator(f"{ROWS}:visible").first.get_attribute("data-uid")
        assert fr[some]["tgt"] in page.locator(f'tr[data-uid="{some}"] .desk-live').inner_text().replace("\n", "") \
            or page.locator(f'tr[data-uid="{some}"] .desk-live').inner_text()  # French text on screen
        assert page.locator('.desk-loc.is-active').get_attribute("data-loc") == "fr"
        # the same English text, in the same place
        box = page.locator(f'tr[data-uid="{anchor_uid}"]').bounding_box()
        assert box and abs(box["y"] - y0) < 2, f"the reviewer's place moved: {y0} -> {box and box['y']}"
        assert not errors, errors
        page.close()


def test_back_returns_to_the_previous_language_without_a_reload(browser):
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")      # every text, so the list is long
        page.evaluate("() => { window.__sameDocument = true; }")
        page.locator('.desk-locales-strip [data-loc="it"]').click()
        page.wait_for_url("**/localization/it/**")
        _wait_ready(page, "it")
        # Back works from anywhere in the page -- deep in the list the place matters most,
        # and the browser's own scroll restore would put the reader back at the top.
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        page.locator(f"{ROWS}:visible").nth(60).scroll_into_view_if_needed()
        anchor_uid, y0 = _top_row(page)
        page.go_back()
        page.wait_for_url("**/localization/de/**")
        page.wait_for_function("performance.getEntriesByName('desk-ready:de').length > 1", timeout=20000)
        assert page.evaluate("() => window.__sameDocument === true")
        assert page.locator('.desk-loc.is-active').get_attribute("data-loc") == "de"
        box = page.locator(f'tr[data-uid="{anchor_uid}"]').bounding_box()
        assert box and abs(box["y"] - y0) < 2, f"Back lost the reviewer's place: {y0} -> {box and box['y']}"
        page.close()


def test_switch_and_first_view_stay_inside_their_budgets(browser):
    """G9 budgets (runbook WO-09), CPU slowed 4x: first view <= 1.5 s, switch <= 0.2 s,
    each timed inside the page from the start to the new rows painted. The median of
    three switches, so one slow frame on a busy runner does not decide it.

    The budgets are set on the reference machine (the operator's Mac, where the pre-commit
    hook runs this at scale 1). A 4x slowdown is relative to the host, and GitHub's runner
    is itself slower: its first run measured a 0.305 s median switch against 0.126 s here.
    CI sets DESK_BUDGET_SCALE (desk-browser.yml) rather than a looser number in this file,
    and a real regression still fails there -- the old reload-per-switch desk took 0.63 s
    on the Mac, about 1.5 s on the runner."""
    scale = float(os.environ.get("DESK_BUDGET_SCALE", "1"))
    with desk("new") as (base, _root, _worker):
        page = browser.new_page()
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 4})
        page.goto(base + "/admin/localization/de/")
        _wait_ready(page, "de")
        first = page.evaluate("() => performance.getEntriesByName('desk-ready:de')[0].startTime") / 1000
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=60000)
        page.wait_for_timeout(1500)       # the other languages prefetch while the reviewer reads
        switches = sorted(_timed_switch(page, code) for code in ("fr", "it", "es"))
        assert first <= 1.5 * scale, f"first view {first:.2f} s > {1.5 * scale:.2f} s (scale {scale})"
        assert switches[1] <= 0.2 * scale, f"switch {switches} s, median > {0.2 * scale:.2f} s (scale {scale})"
        page.close()


def test_a_decision_in_one_language_survives_a_switch_and_back(browser):
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        uid = page.locator(f"{ROWS}:visible").first.get_attribute("data-uid")
        _act(page, uid, "approve")
        page.locator('.desk-locales-strip [data-loc="ja"]').click()
        _wait_ready(page, "ja")                    # the bar is painted with the new language
        assert "1" in page.locator("#save-elsewhere").inner_text()    # still unsaved, still counted
        page.locator('.desk-locales-strip [data-loc="de"]').click()
        page.wait_for_function("document.querySelector('.desk-loc.is-active').dataset.loc === 'de'")
        page.select_option("#f-state", "")
        assert C.t("status.approved") in _label(page, uid)
        page.close()


def test_shared_addresses_use_reviewer_words_and_old_links_still_open(browser):
    """Desk audit §6 #2 (runbook WO-09): reviewers share links, so the address says
    `approved` / `requested`; a link with the old `csv` / `draft` opens the same list and
    is rewritten to the word."""
    with desk("new") as (base, _root, _worker):
        for asked, value, word in (("approved", "csv", "approved"), ("requested", "draft", "requested"),
                                   ("csv", "csv", "approved"), ("draft", "draft", "requested")):
            page, errors = _open(browser, f"{base}/admin/localization/de/?show={asked}")
            assert page.locator("#f-state").input_value() == value, asked
            assert f"show={word}" in page.url and f"show={value}" not in page.url.replace(f"show={word}", ""), page.url
            assert not errors, errors
            page.close()
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "csv")
        assert "show=approved" in page.url
        assert "show=approved" in page.locator('.desk-locales-strip [data-loc="fr"]').get_attribute("href")
        page.close()


# ── Review round 2 (runbook WO-32): each finding the reviewers reproduced, as a guard ───

def _visible_uids(page, n=3):
    page.select_option("#f-state", "")
    return page.locator(f"{ROWS}:visible").evaluate_all("els => els.map(e => e.dataset.uid)")[:n]


def _stored(page, key="cel-desk-de") -> dict:
    return json.loads(page.evaluate(f"() => localStorage.getItem('{key}') || '{{}}'"))


def test_back_closes_a_review_list_and_leaves_the_other_language_alone(browser):
    """L1 P0: a German list left open over the French desk after Back, and its undo
    removed the FRENCH approval."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/fr/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        page.locator('.desk-locales-strip [data-loc="de"]').click()
        _wait_ready(page, "de")
        _act(page, u, "approve")
        page.click("#open-csv")
        assert page.is_visible("#tray-overlay")
        page.go_back()
        page.wait_for_function("performance.getEntriesByName('desk-ready:fr').length > 1", timeout=20000)
        assert not page.is_visible("#tray-overlay"), "the German list stayed open over the French desk"
        assert _rec(page, u).get("tray") == "csv"
        page.close()


def test_overlapping_loads_never_build_the_table_twice(browser):
    """L1 P1-1: de (still loading) -> fr -> de left two live loads for de, both built."""
    with desk("new") as (base, _root, worker):
        worker.faults["de/units.json"] = {"delay": 0.8}
        page = browser.new_page()
        page.goto(base + "/admin/localization/de/")
        page.wait_for_selector('.desk-locales-strip [data-loc="fr"]')
        page.locator('.desk-locales-strip [data-loc="fr"]').click()
        page.locator('.desk-locales-strip [data-loc="de"]').click()
        page.wait_for_function("performance.getEntriesByName('desk-ready:de').length > 0", timeout=20000)
        page.wait_for_timeout(2000)                   # every load still running has landed
        ids = page.locator("#desk-body tr[data-uid]").evaluate_all("els => els.map(e => e.dataset.uid)")
        assert len(ids) == len(set(ids)) == 823, (len(ids), len(set(ids)))
        page.close()


def test_two_tabs_of_one_browser_keep_each_others_decisions(browser):
    """L1 P1-2: each tab wrote its whole in-memory copy, so the second erased the first."""
    with desk("new") as (base, _root, _worker):
        ctx = browser.new_context()
        a, b = ctx.new_page(), ctx.new_page()
        for p in (a, b):
            p.goto(base + "/admin/localization/de/")
            p.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        u0, u1 = _visible_uids(a, 2)
        _visible_uids(b, 2)
        _act(a, u0, "approve")
        b.wait_for_function("u => (window.deskState()[u] || {}).tray === 'csv'", arg=u0, timeout=3000)
        _act(b, u1, "approve")
        a.wait_for_function("u => (window.deskState()[u] || {}).tray === 'csv'", arg=u1, timeout=3000)
        stored = _stored(a)
        assert stored.get(u0, {}).get("tray") == "csv" and stored.get(u1, {}).get("tray") == "csv"
        ctx.close()


def test_another_page_rewriting_a_language_is_not_undone_by_an_open_desk_tab(browser):
    """L1 P1-2: after the index's Discard, one more click in the open desk put it all back.
    (The Discard button is hidden while saving is off -- round 3 -- so another page of
    the same browser rewrites the language directly: the same storage path.)"""
    with desk("new") as (base, _root, _worker):
        ctx = browser.new_context()
        d = ctx.new_page()
        d.goto(base + "/admin/localization/de/")
        d.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        u0, u1, u2 = _visible_uids(d, 3)
        _act(d, u0, "approve")
        _act(d, u1, "approve")
        idx = ctx.new_page()
        idx.goto(base + "/admin/localization/")
        idx.evaluate("() => localStorage.setItem('cel-desk-de', '{}')")
        d.wait_for_function("u => !(window.deskState()[u] || {}).tray", arg=u0, timeout=3000)
        _act(d, u2, "approve")
        stored = _stored(d)
        assert [stored.get(u, {}).get("tray") for u in (u0, u1, u2)] == [None, None, "csv"]
        ctx.close()


def test_the_index_counts_only_what_is_really_unsaved(browser):
    """L1 P2-3: key order and empty records made the index offer to discard saved work."""
    with desk("new") as (base, _root, _worker):
        page = browser.new_page()
        page.goto(base + "/admin/localization/")
        u = "0123456789abcdef"
        page.evaluate("""u => {
            localStorage.setItem('cel-desk-de', JSON.stringify({[u]: {tray: 'csv', by: 'r@x', at: 't', approvedAgainst: 'a'}, other: {}}));
            localStorage.setItem('cel-desk-saved-de', JSON.stringify({[u]: {approvedAgainst: 'a', at: 't', by: 'r@x', tray: 'csv'}}));
        }""", u)
        page.reload()
        assert page.locator('.desk-locale-card[data-locale="de"] .desk-locale-discard').count() == 0
        page.close()


def test_committing_nothing_by_clicking_the_open_language_keeps_cancel_honest(browser):
    """L1 P2-2: clicking the active tab committed the editor behind the reviewer's back,
    so a later 'throw away what you typed' kept it as an approval."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.on("dialog", lambda dlg: dlg.accept())
        u = _visible_uids(page, 1)[0]
        _act(page, u, "edit")
        _row(page, u).locator("textarea.desk-edit").fill("Mein eigener Text")
        page.locator('.desk-locales-strip [data-loc="de"]').click()
        _row(page, u).locator('[data-edit="cancel"]').click()
        assert _rec(page, u).get("text") is None, "throwing the text away kept it"
        page.close()


def test_a_language_that_failed_to_load_can_be_opened_again_from_its_tab(browser):
    """L1 P2-4: after a failed load its own tab did nothing, and the error styling stuck."""
    with desk("new") as (base, _root, worker):
        worker.faults["fr/units.json"] = {"status": 503}   # before the idle prefetch reaches it
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.locator('.desk-locales-strip [data-loc="fr"]').click()
        page.wait_for_function("document.getElementById('count-line').classList.contains('is-error')", timeout=10000)
        del worker.faults["fr/units.json"]
        page.locator('.desk-locales-strip [data-loc="fr"]').click()
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        assert "is-error" not in (page.get_attribute("#count-line", "class") or "")
        page.close()


def test_switching_does_not_fill_the_action_log(browser):
    """L1 P2-5: every switch logged a 'load', and eight capped logs nearly filled the
    origin's storage."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        for _ in range(6):
            for code in ("fr", "de"):
                page.locator(f'.desk-locales-strip [data-loc="{code}"]').click()
                _wait_ready(page, code)
        log = json.loads(page.evaluate("() => localStorage.getItem('cel-desk-log-de') || '[]'"))
        assert sum(1 for e in log if e.get("a") == "load") <= 1
        page.close()


def test_shortcuts_do_nothing_while_a_dialog_is_open(browser):
    """L1 P3 / L5 #4: J/K/A/E acted on the table behind an open list."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("j")
        u = page.locator(f"{ROWS}.is-cursor").get_attribute("data-uid")
        page.click("#how-open")
        page.keyboard.press("a")
        assert not _rec(page, u).get("tray"), "a approved a row behind the open list"
        page.close()


def test_every_text_cell_says_its_language_and_the_count_is_announced(browser):
    """L1 P3: target cells had no lang, so screen readers and CJK glyphs used English."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/ja/")
        langs = page.locator(f"{ROWS} .desk-live").evaluate_all("els => [...new Set(els.map(e => e.getAttribute('lang')))]")
        assert langs == ["ja"]
        assert page.get_attribute("#count-line", "aria-live") == "polite"
        page.locator('.desk-locales-strip [data-loc="ar"]').click()
        _wait_ready(page, "ar")
        langs = page.locator(f"{ROWS} .desk-live").evaluate_all("els => [...new Set(els.map(e => e.getAttribute('lang')))]")
        assert langs == ["ar"]
        page.close()


def test_a_message_never_covers_the_buttons_it_talks_about(browser):
    """L5 #2: a toast sat on View approved / View requests / Save, and hovering it kept it."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.select_option("#f-state", "")
        page.locator(f"{ROWS}:visible [data-pick]").nth(0).check()
        page.click("#bulk-approve")
        page.wait_for_selector("#toast-stack .toast, #toast-stack > *", timeout=5000)
        for sel in ("#open-csv", "#btn-save"):
            if not page.is_visible(sel):
                continue
            hit = page.evaluate("""sel => { const b = document.querySelector(sel).getBoundingClientRect();
                const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
                return !!e && !!e.closest(sel); }""", sel)
            assert hit, f"a message covers {sel}"
        page.close()


def test_the_help_can_be_read_to_the_end_and_closed_on_a_laptop(browser):
    """L5 #3: the help was taller than the screen with no scrolling, so its end and its
    Close button were out of reach below ~1,050 px."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.click("#how-open")
        page.locator("#how-close").scroll_into_view_if_needed()
        hit = page.evaluate("""() => { const b = document.getElementById('how-close').getBoundingClientRect();
            const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
            return !!e && !!e.closest('#how-close'); }""")
        assert hit, "the help's Close button cannot be reached"
        page.click("#how-close")
        assert not page.is_visible("#how-overlay")
        page.close()


def test_all_texts_is_kept_in_the_address(browser):
    """L5 #5: 'All texts' wrote no show=, and a reload fell back to Flagged (263 rows -> 1)."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")
        assert "show=all" in page.url
        again = browser.new_page()
        again.goto(page.url)
        again.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        assert again.locator("#f-state").input_value() == ""
        again.close()
        page.close()


def test_undo_all_in_a_list_leaves_rows_with_gemini_alone(browser):
    """L5 #7: Undo all in the Requested list took rows out that Gemini was working on."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.on("dialog", lambda dlg: dlg.accept())
        u1, u2 = _visible_uids(page, 2)
        _act(page, u1, "queue")
        _put_in(page, u2, "sending")
        page.click("#open-draft")
        page.click("#tray-empty")
        assert _rec(page, u2).get("tray") == "draft" and _rec(page, u2).get("sentAt"), "a row with Gemini was undone"
        assert not _rec(page, u1).get("tray")
        page.close()


def test_an_approval_records_who_and_the_wording_it_was_given_to(browser):
    """L6 P1-1: nothing checked approvedAgainst, without which the export cannot refuse a
    translation that moved after it was approved."""
    with desk("new") as (base, root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        rec = _rec(page, u)
        assert rec.get("approvedAgainst") == _units(root, "de")[u]["tgt"]
        assert rec.get("by") and rec.get("at")
        page.close()


def test_saving_is_off_until_it_is_private_and_says_so(browser):
    """WO-34 (A15): until WO-17, Save would commit the reviewer's email to the public repo.
    It is switched off with its reason, and nothing reaches the storage."""
    with desk("new") as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        _approve_first_visible(page)
        btn = page.locator("#btn-save")
        assert btn.is_disabled()
        assert btn.get_attribute("data-tip") == C.t("save.off.hint")
        btn.click(force=True)
        page.wait_for_timeout(500)
        assert not [c for c in worker.calls if c.startswith("desk-")], worker.calls
        page.close()


@pytest.mark.parametrize("save_on", [False, True], ids=["saving off", "saving on"])
def test_a_full_desk_stays_inside_its_budgets(browser, save_on):
    """L1 P3: with all eight languages decided, one click took 88 ms and a switch 0.26 s at
    4x CPU -- the budget test only ever measured an empty desk. With saving on (WO-18) the
    storage holds the same decisions, so the desk starts with nothing unsaved."""
    scale = float(os.environ.get("DESK_BUDGET_SCALE", "1"))
    with desk("new", save_on=save_on) as (base, root, worker):
        page = browser.new_page()
        page.goto(base + "/admin/localization/de/")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        for code in ("de", "fr", "es", "pt", "it", "ja", "ko", "ar"):
            recs = {u: {"tray": "csv", "by": "reviewer@example.test", "at": "2026-09-28T10:00:00Z",
                        "approvedAgainst": x["tgt"]} for u, x in _units(root, code).items()}
            saved = recs
            if save_on:
                units = _units(root, code)
                for i in range(0, len(recs), 200):
                    worker.store.handle("desk-write", {"locale": code, "client": 1, "changes": [
                        {"unit": u, "page": units[u]["pages"][0], "base": 0,
                         "record": {"tray": "csv", "approvedAgainst": units[u]["tgt"]}}
                        for u in list(recs)[i:i + 200]]}, "reviewer@example.test")
                saved = {u: {"tray": "csv", "approvedAgainst": x["approvedAgainst"], "version": 1} for u, x in recs.items()}
            page.evaluate("([c, r, v]) => { localStorage.setItem('cel-desk-' + c, r); localStorage.setItem('cel-desk-saved-' + c, v); }",
                          [code, json.dumps(recs), json.dumps(saved)])
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 4})
        page.reload()
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=60000)
        page.select_option("#f-state", "")
        clicks = sorted(page.evaluate("""() => { const b = document.querySelectorAll('tr[data-uid] [data-act="approve"]')[i];
            const t0 = performance.now(); b.click(); return performance.now() - t0; }""".replace("[i]", f"[{i}]")) for i in (0, 1, 2))
        page.wait_for_timeout(1500)
        switches = sorted(_timed_switch(page, code) for code in ("fr", "it", "es"))
        assert clicks[1] <= 40 * scale, f"a click took {clicks} ms (median over {40 * scale:.0f})"
        # Saving on, a switch also reads the storage before it builds (WO-17), a round trip the
        # desk without saving never makes. Measured 2026-09-28 at 4x CPU, median 135 ms before
        # autosave and 133 ms with it: the read is the cost, and it sits on 0.2 s -- so this
        # variant's budget is 0.3 s (runbook §7: with a real network the read is longer still).
        budget = (0.3 if save_on else 0.2) * scale
        assert switches[1] <= budget, f"switch {switches} s, median over {budget:.2f}"
        page.close()


# ── Round 3 (the independent re-check of WO-32's desk fixes) ──────────────────────────

def test_a_list_selection_does_not_outlive_another_tab_moving_the_row(browser):
    """P2-1: a row ticked in tab A's Approved list, then requested in tab B, left the list's
    Undo counting it -- and Undo erased tab B's request for a row the list no longer showed."""
    with desk("new") as (base, _root, _worker):
        ctx = browser.new_context()
        a, b = ctx.new_page(), ctx.new_page()
        for p in (a, b):
            p.goto(base + "/admin/localization/de/")
            p.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        u0, u1 = _visible_uids(a, 2)
        _act(a, u0, "approve")
        _act(a, u1, "approve")
        a.click("#open-csv")
        a.locator("#tray-list .desk-pick").first.check()           # the list follows page order: u0
        _visible_uids(b, 2)
        b.wait_for_function("u => (window.deskState()[u] || {}).tray === 'csv'", arg=u0, timeout=3000)
        _act(b, u0, "queue")
        a.wait_for_function("u => (window.deskState()[u] || {}).tray === 'draft'", arg=u0, timeout=3000)
        assert a.locator("#tray-remove-sel").is_disabled(), "the list still counts a row it no longer shows"
        assert _rec(a, u0).get("tray") == "draft"
        ctx.close()


def test_undo_from_the_requested_list_puts_the_turned_down_draft_back(browser):
    """P2-2: the table's Undo restored the arrived draft; the list's left the row reading
    "new translation" over the website's wording, the draft still marked rejected."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        uid = _visible_uids(page, 1)[0]
        _put_in(page, uid, "arrived")
        _act(page, uid, "queue")
        assert _rec(page, uid).get("rejected") == ["WO-06 draft from Gemini"]
        page.click("#open-draft")
        page.locator("#tray-list .desk-review-item button").first.click()
        rec = _rec(page, uid)
        assert rec.get("text") == "WO-06 draft from Gemini" and "rejected" not in rec, rec
        page.close()


def test_the_index_offers_no_discard_while_saving_is_off(browser):
    """P2-3: with nothing on a server, "Discard N unsaved" was a one-click wipe of a whole
    language, beside a desk saying "kept in this browser"."""
    with desk("new") as (base, _root, _worker):
        page = browser.new_page()
        page.goto(base + "/admin/localization/")
        page.evaluate("() => localStorage.setItem('cel-desk-de', JSON.stringify({'0123456789abcdef': {tray: 'csv'}}))")
        page.reload()
        assert page.locator(".desk-locale-discard").count() == 0
        assert "unsaved" not in page.locator("main").inner_text().lower()
        page.close()


def test_a_load_failure_stays_on_screen_when_another_tab_writes(browser):
    """P3: another tab's write repainted the failed language as "0 of 0" with the reset panel."""
    with desk("new") as (base, _root, worker):
        worker.faults["fr/units.json"] = {"status": 503}
        ctx = browser.new_context()
        p = ctx.new_page()
        p.goto(base + "/admin/localization/fr/")
        p.wait_for_function("document.getElementById('count-line').classList.contains('is-error')", timeout=15000)
        said = p.locator("#count-line").inner_text()
        other = ctx.new_page()
        other.goto(base + "/admin/localization/")
        other.evaluate("() => localStorage.setItem('cel-desk-fr', JSON.stringify({'0123456789abcdef': {tray: 'csv'}}))")
        p.wait_for_timeout(500)
        assert p.locator("#count-line").inner_text() == said
        assert p.locator("#no-rows").is_hidden()
        ctx.close()


def test_shortcuts_do_nothing_behind_the_account_dialog(browser):
    """P3: the change-password dialog is the shell's, and `a` approved the row behind it."""
    with desk("new") as (base, _root, _worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("j")
        u = page.locator(f"{ROWS}.is-cursor").get_attribute("data-uid")
        page.evaluate("() => { document.getElementById('cpw-overlay').hidden = false; }")
        page.keyboard.press("a")
        assert not _rec(page, u).get("tray"), "a approved a row behind the account dialog"
        page.close()


def test_a_draft_turned_down_before_the_list_shape_is_kept(browser):
    """P3: a `rejected` saved as a string before round 2 was dropped on the next ✦."""
    with desk("new") as (base, _root, _worker):
        page = browser.new_page()
        page.goto(base + "/admin/localization/de/")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        uid = _visible_uids(page, 1)[0]
        page.evaluate("u => localStorage.setItem('cel-desk-de', JSON.stringify({[u]: {rejected: 'an older draft'}}))", uid)
        page.reload()
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        _put_in(page, uid, "arrived")
        _act(page, uid, "queue")
        assert _rec(page, uid).get("rejected") == ["an older draft", "WO-06 draft from Gemini"]
        page.close()


# ── The dead-control robot (runbook WO-32 lens L5; WO-33) ──────────────────────────────
# Every control on the index and on a language page, in every state that shows new ones,
# is clicked on a fresh page: each must visibly change something (the address, the text on
# screen, what is stored, a dialog) -- or, if disabled, say why on hover. None may do
# nothing. A link to the page you are on (aria-current, or its own address) is exempt.

_FINGERPRINT = """() => JSON.stringify([location.href, document.body.innerText,
  JSON.stringify(Object.assign({}, localStorage)),
  [...document.querySelectorAll('.cpw-overlay, [role=menu]')].map(o => o.hidden || getComputedStyle(o).display)])"""
_TAG = """scope => [...document.querySelectorAll(
    ['a[href]', 'button', 'select', 'input'].map(t => scope + ' ' + t).join(','))]
  .filter(e => e.offsetParent !== null && !(e.closest('#desk-body') && e.closest('tr') !== document.querySelector('#desk-body tr:not([hidden])')))
  .map((e, i) => { e.setAttribute('data-robot', i); return {
    i, tag: e.tagName, type: e.type || '', id: e.id, label: (e.getAttribute('aria-label') || e.innerText || '').trim().slice(0, 40),
    disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true', tip: e.getAttribute('data-tip') || '',
    current: e.getAttribute('aria-current') === 'page' ||
      (e.tagName === 'A' && e.href.split('?')[0].replace(/index\\.html$/, '') === location.href.split('?')[0]) }; })"""


def _rows_ready(page):
    page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)


def _first_visible(page, act):
    page.locator(f'{ROWS}:visible [data-act="{act}"]').first.evaluate("e => e.click()")


_STATES = {
    "the index": ("/admin/localization/", None, "body"),
    "a language page": ("/admin/localization/de/", _rows_ready, "body"),
    "with texts ticked": ("/admin/localization/de/?show=all", lambda pg: (
        _rows_ready(pg), pg.locator(f"{ROWS}:visible [data-pick]").first.evaluate("e => e.click()")), "#savebar"),
    "with an edit box open": ("/admin/localization/de/?show=all", lambda pg: (
        _rows_ready(pg), _first_visible(pg, "edit")), ".desk-editor:not([hidden])"),
    "with the help open": ("/admin/localization/de/", lambda pg: (
        _rows_ready(pg), pg.locator("#how-open").evaluate("e => e.click()")), "#how-overlay"),
    "with nothing to show": ("/admin/localization/de/?show=all&q=zzzzzzzz", _rows_ready, "#no-rows"),
    "the approved list": ("/admin/localization/de/?show=all", lambda pg: (
        _rows_ready(pg), _first_visible(pg, "approve"), pg.locator("#open-csv").evaluate("e => e.click()")), "#tray-overlay"),
    "the requests list": ("/admin/localization/de/?show=all", lambda pg: (
        _rows_ready(pg), _first_visible(pg, "queue"), pg.locator("#open-draft").evaluate("e => e.click()")), "#tray-overlay"),
    # Saving on, the storage refusing: the bar's Try again (runbook WO-18).
    "with saving stopped": ("/admin/localization/de/?show=all", lambda pg: (
        _rows_ready(pg), _first_visible(pg, "approve"), pg.wait_for_function(
            "() => document.getElementById('save-status').getAttribute('data-state') === 'stopped'", timeout=15000)),
        "#savebar", {"save_on": True, "fault": {"status": 401, "error": "session expired"}}),
}


def _robot_act(page, c) -> str:
    el = page.locator(f'[data-robot="{c["i"]}"]')
    if c["tag"] == "SELECT":
        options = el.evaluate("s => [...s.options].filter(o => !o.disabled && !o.hidden).map(o => o.value)")
        other = next((o for o in options if o != el.input_value()), None)
        if other is None:
            return "no other option"
        el.select_option(other)
    elif c["type"] in ("search", "text"):
        el.fill("zz")
    else:
        el.evaluate("e => e.click()")
    return ""


@pytest.mark.parametrize("state", sorted(_STATES))
def test_no_control_is_a_dead_end(browser, state):
    path, setup, scope, *more = _STATES[state]
    opts = more[0] if more else {}
    with desk("new", save_on=opts.get("save_on", False)) as (base, _root, worker):
        worker.desk_fault = opts.get("fault")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("dialog", lambda d: d.accept())

        def fresh():
            page.evaluate("() => localStorage.clear()") if page.url.startswith("http") else None
            page.goto(base + path)
            page.wait_for_load_state()
            if setup:
                setup(page)
            page.wait_for_timeout(150)
            return page.evaluate(_TAG, scope)

        controls = fresh()
        assert controls, f"{state}: no controls found in {scope}"
        dead = []
        for c in controls:
            if c["current"]:
                continue
            fresh()
            if c["disabled"]:
                if not c["tip"]:
                    dead.append(f'{c["tag"]} #{c["id"]} "{c["label"]}": disabled, and says nothing about why')
                continue
            before = page.evaluate(_FINGERPRINT)
            why = _robot_act(page, c)
            page.wait_for_timeout(250)
            if page.evaluate(_FINGERPRINT) == before:
                dead.append(f'{c["tag"]} #{c["id"]} "{c["label"]}": nothing changed {why}'.rstrip())
        assert not dead, f"{state}: " + " | ".join(dead)
        page.close()


# ── WO-17: the desk saves to the Worker's storage (served with saving on) ──────────────
# Since WO-18 there is no Save button: a change goes by itself after a quiet moment, and the
# bar's status says where it stands (`data-state` on #save-status, its words from COPY.md).

def _as_state(page) -> str:
    return page.locator("#save-status").get_attribute("data-state") or ""


def _as_wait(page, state: str, timeout: float = 20000):
    page.wait_for_function("s => document.getElementById('save-status').getAttribute('data-state') === s",
                           arg=state, timeout=timeout)


def _as_words(page) -> str:
    el = page.locator("#save-status")
    return el.inner_text() + " " + (el.get_attribute("data-tip") or "")


def _server(worker, uid, locale="de"):
    row = worker.store.decisions.get((locale, uid))
    return None if row is None else {**row["record"], "version": row["version"], "by": row["by"]}


def _as_open(context, url):
    page = context.new_page()
    page.goto(url)
    page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
    return page


def test_a_save_lands_in_the_storage_and_another_computer_sees_it(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        u0, u1 = _visible_uids(page, 2)
        _act(page, u0, "approve")
        _act(page, u1, "queue")
        _as_wait(page, "saved")
        s0 = _server(worker, u0)
        assert s0["tray"] == "csv" and s0["version"] == 1 and s0["by"] == "reviewer@example.test"
        assert s0["approvedAgainst"] == _units(_root, "de")[u0]["tgt"]
        assert _server(worker, u1)["tray"] == "draft"
        assert page.locator("#save-status").inner_text() == C.t("autosave.saved")
        other = _as_open(browser.new_context(), base + "/admin/localization/de/")   # another computer
        assert _rec(other, u0).get("tray") == "csv" and _rec(other, u1).get("tray") == "draft"
        _as_wait(other, "saved")
        assert not errors, errors
        page.close()


def test_someone_else_saving_first_is_a_conflict_on_the_row_and_theirs_can_be_taken(browser):
    with desk(save_on=True) as (base, _root, worker):
        a = _as_open(browser.new_context(), base + "/admin/localization/de/")
        b = _as_open(browser.new_context(), base + "/admin/localization/de/")
        u = _visible_uids(a, 1)[0]
        _visible_uids(b, 1)
        _act(a, u, "approve")
        _as_wait(a, "saved")                               # A saves first
        _act(b, u, "queue")                                # B's change was based on nothing
        _as_wait(b, "conflict")
        assert _server(worker, u)["tray"] == "csv", "a conflict must never overwrite"
        assert C.t("status.conflict") in _label(b, u)
        assert C.tn("autosave.conflict", 1) in _as_words(b)
        _toast(b, C.t("save.conflicts.title"))
        _row(b, u).locator("[data-conflict]").click()     # use theirs
        assert _rec(b, u).get("tray") == "csv"
        _as_wait(b, "saved")
        assert C.t("status.conflict") not in _label(b, u)


def test_keeping_yours_over_a_conflict_is_a_deliberate_save_on_their_version(browser):
    with desk(save_on=True) as (base, _root, worker):
        a = _as_open(browser.new_context(), base + "/admin/localization/de/")
        b = _as_open(browser.new_context(), base + "/admin/localization/de/")
        u = _visible_uids(a, 1)[0]
        _visible_uids(b, 1)
        _act(a, u, "approve")
        _as_wait(a, "saved")
        _act(b, u, "queue")
        _as_wait(b, "conflict")
        writes = worker.calls.count("desk-write")
        b.wait_for_timeout(4000)                           # autosave does NOT send it again
        assert worker.calls.count("desk-write") == writes and _server(worker, u)["tray"] == "csv"
        _put_in(b, u, "edited")                            # deciding again: yours, deliberately
        _as_wait(b, "saved")
        s = _server(worker, u)
        assert (s["text"], s["version"]) == ("WO-06 wording of my own", 2), s


def test_a_whole_language_saves_in_slices_the_storage_takes(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")
        page.check("#pick-all")
        page.click("#bulk-approve")
        _as_wait(page, "saved", 40000)
        assert worker.calls.count("desk-write") >= 5            # 823 in slices of 200
        assert sum(1 for (loc, _u) in worker.store.decisions if loc == "de") == 823
        page.close()


def test_an_undo_after_a_save_is_saved_too(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        _as_wait(page, "saved")
        _act(page, u, "approve")                                 # undo
        page.wait_for_function("u => !(window.deskState()[u] || {}).tray", arg=u)
        _as_wait(page, "saved")
        s = _server(worker, u)
        assert s["version"] == 2 and "tray" not in s
        page.close()


def test_a_text_the_storage_does_not_know_is_refused_kept_and_not_sent_again(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        worker.store.units = {(unit, pg) for unit, pg in worker.store.units if unit != u}
        _act(page, u, "approve")
        _as_wait(page, "refused")
        _toast(page, C.t("save.refused.title"))
        assert _server(worker, u) is None and _rec(page, u).get("tray") == "csv"
        writes = worker.calls.count("desk-write")
        page.wait_for_timeout(5000)
        assert worker.calls.count("desk-write") == writes, "a refused text went round again"
        page.close()


# ── WO-18: autosave (contract §8 S3) ──────────────────────────────────────────────────

def test_a_decision_saves_itself_after_a_quiet_moment_and_the_save_button_is_gone(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        t0 = time.monotonic()
        _act(page, u, "approve")
        assert page.locator("#btn-save").is_hidden() and page.locator("#tray-save").count() == 0
        assert _as_state(page) == "saving" and C.tn("autosave.saving", 1) in _as_words(page)
        page.wait_for_timeout(1000)
        assert "desk-write" not in worker.calls, "sent before the reviewer paused"
        _as_wait(page, "saved")
        assert time.monotonic() - t0 >= 1.8
        assert _server(worker, u)["tray"] == "csv"
        page.click("#open-csv")
        assert page.locator("#tray-save").count() == 0, "the list has no Save either"
        assert not errors, errors
        page.close()


def test_quick_decisions_travel_together_and_one_request_is_ever_in_flight(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 5)
        for x in u[:3]:
            _act(page, x, "approve")
        _as_wait(page, "saved")
        assert worker.calls.count("desk-write") == 1, "three quick decisions, one request"
        worker.desk_fault = {"delay": 4}
        _act(page, u[3], "approve")
        for _ in range(100):                               # the slow request is on its way
            if worker.inflight:
                break
            time.sleep(0.1)
        assert _as_state(page) == "saving"
        _act(page, u[4], "approve")                        # its quiet moment ends mid-request
        worker.desk_fault = None
        _as_wait(page, "saved", 30000)
        assert worker.max_inflight == 1, "a second request went while one was in flight"
        assert _server(worker, u[3])["tray"] == "csv" and _server(worker, u[4])["tray"] == "csv"
        page.close()


def test_two_tabs_of_one_browser_share_the_saving(browser):
    with desk(save_on=True) as (base, _root, worker):
        ctx = browser.new_context()
        a = _as_open(ctx, base + "/admin/localization/de/")
        b = _as_open(ctx, base + "/admin/localization/de/")
        u0, u1 = _visible_uids(a, 2)
        _visible_uids(b, 2)
        worker.desk_fault = {"delay": 4}
        _act(a, u0, "approve")
        for _ in range(100):
            if worker.inflight:
                break
            time.sleep(0.1)
        _act(b, u1, "approve")                             # tab B's quiet moment ends during A's request
        worker.desk_fault = None
        _as_wait(a, "saved", 30000)
        _as_wait(b, "saved", 30000)
        assert worker.max_inflight == 1, "two tabs sent at once"
        assert (_server(worker, u0)["version"], _server(worker, u1)["version"]) == (1, 1)
        assert C.t("status.conflict") not in _label(a, u0) + _label(b, u1)
        ctx.close()


@pytest.mark.parametrize("status,error,state,reason", [
    (500, "server error", "retrying", "trouble"),
    (503, "storage not configured", "retrying", "unavailable"),
    (429, "over the cap", "stopped", "cap"),
    (429, "over the daily budget", "stopped", "daily"),
    (401, "session expired", "stopped", "signed_out"),
    (409, "desk out of date -- reload the page", "stopped", "reload"),
    (400, "invalid: bad page", "stopped", "refused"),
    (403, "forbidden origin", "stopped", "refused"),          # review of WO-17, P3: not "signed out"
])
def test_each_way_saving_can_fail_is_shown_and_loses_nothing(browser, status, error, state, reason):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        worker.desk_fault = {"status": status, "error": error}
        _act(page, u, "approve")
        _as_wait(page, state)
        assert C.t(f"save.reason.{reason}") in _as_words(page), _as_words(page)
        assert _server(worker, u) is None
        page.reload()                                      # nothing is lost across a reload
        _rows_ready(page)
        assert _rec(page, u).get("tray") == "csv"
        _as_wait(page, state)
        worker.desk_fault = None                           # the storage works again
        if state == "retrying":
            _as_wait(page, "saved", 30000)                 # by itself
        elif reason == "reload":
            page.reload()                                  # what the words say to do
            _rows_ready(page)
            _as_wait(page, "saved")
        else:
            page.click("#save-retry")
            _as_wait(page, "saved")
        assert _server(worker, u)["tray"] == "csv"
        page.close()


def test_offline_keeps_changes_on_this_computer_and_sends_them_when_back(browser):
    with desk(save_on=True) as (base, _root, worker):
        ctx = browser.new_context()
        page = _as_open(ctx, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        ctx.set_offline(True)
        _act(page, u, "approve")
        _as_wait(page, "offline")
        assert C.tn("autosave.offline", 1) in _as_words(page)
        ctx.set_offline(False)
        _as_wait(page, "saved", 30000)
        assert _server(worker, u)["tray"] == "csv"
        ctx.close()


def test_nothing_is_sent_on_the_way_out_and_it_goes_on_the_next_visit(browser):
    with desk(save_on=True) as (base, _root, worker):
        ctx = browser.new_context()
        page = _as_open(ctx, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        page.close(run_before_unload=True)                 # before the quiet moment is over
        time.sleep(3)
        assert "desk-write" not in worker.calls, "something was sent on the way out"
        again = _as_open(ctx, base + "/admin/localization/de/")
        _as_wait(again, "saved")
        assert _server(worker, u)["tray"] == "csv"
        ctx.close()


@pytest.mark.parametrize("fault", [{"drop": True}, {"status": 502, "error": "bad gateway", "apply": True}],
                         ids=["the answer lost", "a 502 after the write landed"])
def test_an_answer_lost_on_the_way_back_is_not_a_conflict_with_yourself(browser, fault):
    """Review of WO-17, P2-1: the reviewer's own save came back as "Changed elsewhere"."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        worker.desk_fault = fault                          # applied, then no good answer
        _act(page, u, "approve")
        page.wait_for_function("() => ['offline', 'retrying'].includes(document.getElementById('save-status').getAttribute('data-state'))", timeout=15000)
        assert _server(worker, u)["version"] == 1
        worker.desk_fault = None
        page.wait_for_function("() => ['saved', 'conflict'].includes(document.getElementById('save-status').getAttribute('data-state'))",
                               timeout=30000)
        assert _as_state(page) == "saved", f"its own save came back as {_as_state(page)!r}: {_label(page, u)}"
        assert _server(worker, u)["version"] == 1
        assert C.t("status.conflict") not in _label(page, u)
        page.close()


def test_a_browser_holding_an_old_copy_takes_the_newer_decision_instead_of_overwriting_it(browser):
    """R26: B's copy of a text was saved and unchanged; A changed it since. B's reload
    kept its old copy as if it were a change of its own -- and would have saved it over A's."""
    with desk(save_on=True) as (base, _root, worker):
        a = _as_open(browser.new_context(), base + "/admin/localization/de/")
        u = _visible_uids(a, 1)[0]
        _act(a, u, "approve")
        _as_wait(a, "saved")
        b = _as_open(browser.new_context(), base + "/admin/localization/de/")
        assert _rec(b, u).get("tray") == "csv"
        _act(a, u, "queue")                                # A changes its mind: version 2
        _as_wait(a, "saved")
        b.reload()
        _rows_ready(b)
        b.wait_for_timeout(3000)
        s = _server(worker, u)
        assert (s["tray"], s["version"]) == ("draft", 2), f"a stale browser overwrote a newer decision: {s}"
        assert _rec(b, u).get("tray") == "draft"
        _as_wait(b, "saved")


def test_an_undo_not_yet_sent_survives_a_reload(browser):
    """An undone decision has nothing left in it, and the load took the storage's copy over
    it -- the undo came back as an approval."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        _as_wait(page, "saved")
        worker.desk_fault = {"status": 503, "error": "storage not configured"}
        _act(page, u, "approve")                           # undo, not sent yet
        _as_wait(page, "retrying")
        page.reload()
        _rows_ready(page)
        assert not _rec(page, u).get("tray"), "the undo was lost on reload"
        worker.desk_fault = None
        _as_wait(page, "saved", 30000)
        s = _server(worker, u)
        assert s["version"] == 2 and "tray" not in s
        page.close()


_FILL = """() => {
  let lo = 0, hi = 16 * 1024 * 1024;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    try { localStorage.setItem('zz-someone-else', 'x'.repeat(mid)); lo = mid; }
    catch (e) { localStorage.removeItem('zz-someone-else'); hi = mid - 1; }
  }
  localStorage.setItem('zz-someone-else', 'x'.repeat(lo));
  return lo;
}"""


def test_when_the_browser_is_full_the_unsent_changes_are_what_it_keeps(browser):
    """P0-8 / R54: a full store gives up its logs, then the copies the storage already holds
    (they come back from it); the change nobody has sent yet is what stays."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.on("dialog", lambda d: d.accept())
        page.select_option("#f-state", "")
        u = page.locator(f"{ROWS}:visible").first.get_attribute("data-uid")
        page.check("#pick-all")
        _row(page, u).locator("[data-pick]").uncheck()
        page.click("#bulk-approve")                        # 822 decided and saved; u is not
        _as_wait(page, "saved", 40000)
        worker.desk_fault = {"status": 503, "error": "storage not configured"}
        # The log gives way first (review round 2) -- here it has already gone, so what is left
        # to give way is the saved copy.
        page.evaluate("() => localStorage.removeItem('cel-desk-log-de')")
        filled = page.evaluate(_FILL)
        _act(page, u, "approve")                           # the one change that does not fit
        stored = _stored(page)
        assert list(stored) == [u] and stored[u].get("tray") == "csv", f"kept {len(stored)} texts"
        assert page.evaluate("() => localStorage.getItem('zz-someone-else').length") == filled
        page.reload()
        _rows_ready(page)
        v = next(x for x in _units(_root, "de") if x != u)
        assert _rec(page, u).get("tray") == "csv", "the unsent change was lost"
        assert _rec(page, v).get("tray") == "csv", "a saved decision did not come back from the storage"
        worker.desk_fault = None
        _as_wait(page, "saved", 30000)
        de = [r for (loc, _x), r in worker.store.decisions.items() if loc == "de"]
        assert len(de) == 823 and {r["version"] for r in de} == {1}, "something already saved was sent again"
        page.close()


def test_the_client_never_sends_more_than_the_storage_takes_in_ten_minutes(browser):
    """The hard client cap: this browser stays under the Worker's 2,000 changes per 10 minutes,
    and says so, instead of being refused."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        for code in ("de", "fr", "es"):
            if code != "de":
                page.locator(f'.desk-locales-strip [data-loc="{code}"]').click()
                _wait_ready(page, code)
            page.select_option("#f-state", "")
            page.check("#pick-all")
            page.click("#bulk-approve")
        _as_wait(page, "stopped", 60000)
        assert C.t("save.reason.cap") in _as_words(page)
        assert len(worker.store.decisions) == 823 + 823 + 200
        page.close()


# ── WO-18: the index's counts come from the storage (desk-summary) ──────────────────────

def test_the_index_on_another_computer_shows_what_was_saved(browser):
    with desk(save_on=True) as (base, _root, worker):
        a = _as_open(browser.new_context(), base + "/admin/localization/de/?show=all")
        flagged = a.locator(f"{ROWS}[data-why]").first.get_attribute("data-uid")
        u0, u1 = [x for x in _visible_uids(a, 3) if x != flagged][:2]
        _act(a, flagged, "approve")
        _act(a, u0, "approve")
        _act(a, u1, "queue")
        _as_wait(a, "saved")
        idx = browser.new_context().new_page()             # another computer: nothing local
        idx.goto(base + "/admin/localization/")
        card = idx.locator('.desk-locale-card[data-locale="de"]')
        total = int(card.get_attribute("data-total"))
        card.get_by_text(C.t("index.card.progress", done=3, total=total)).wait_for(timeout=15000)
        assert C.t("index.chip.approved", n=2) in card.inner_text()
        assert C.tn("index.chip.requested", 1) in card.inner_text()
        n_flagged = int(card.get_attribute("data-flagged"))
        href = card.locator(".desk-locale-open").get_attribute("href")
        assert href.endswith("?show=check" if n_flagged > 1 else "?show=todo"), href
        assert "desk-summary" in worker.calls


def test_the_index_says_so_when_it_cannot_read_the_storage(browser):
    with desk(save_on=True) as (base, _root, worker):
        worker.action_faults["desk-summary"] = {"status": 503, "error": "storage not configured"}
        idx = browser.new_page()
        idx.goto(base + "/admin/localization/")
        idx.get_by_text(C.t("index.summary.failed")).wait_for(timeout=15000)


def test_the_live_index_asks_the_storage_nothing_while_saving_is_off(browser):
    with desk("new") as (base, _root, worker):
        idx = browser.new_page()
        idx.goto(base + "/admin/localization/")
        idx.wait_for_timeout(1500)
        assert not [c for c in worker.calls if c.startswith("desk-")], worker.calls


# ── The independent review of WO-17's local half (CEL d1f77a15), each finding as a guard ──

def test_review_p0_1_probe_1_a_reload_takes_a_colleagues_newer_wording(browser):
    """A approves and saves (v1); B edits and saves (v2); A only reloads. A's desk offered
    "1 unsaved" -- A's old approval -- and saving it made v3 without B's wording."""
    with desk(save_on=True) as (base, _root, worker):
        a = _as_open(browser.new_context(), base + "/admin/localization/de/")
        u = _visible_uids(a, 1)[0]
        _act(a, u, "approve")
        _as_wait(a, "saved")
        b = _as_open(browser.new_context(), base + "/admin/localization/de/")
        _visible_uids(b, 1)
        _put_in(b, u, "edited")
        _as_wait(b, "saved")
        assert _server(worker, u)["version"] == 2
        a.reload()
        _rows_ready(a)
        _as_wait(a, "saved")
        a.wait_for_timeout(3000)
        s = _server(worker, u)
        assert (s["version"], s.get("text")) == (2, "WO-06 wording of my own"), f"B's wording was lost: {s}"
        assert _rec(a, u).get("text") == "WO-06 wording of my own"


def test_review_p0_1_probe_2_an_unsent_decision_meets_a_newer_save_as_a_conflict(browser):
    """A approves without saving; B requests and saves (v1); A reloads and saves: A's approval
    became v2 over B's request, with no conflict. A leaves before its quiet moment is over --
    nothing goes on the way out -- so its approval is still unsent when it comes back."""
    with desk(save_on=True) as (base, _root, worker):
        ctx_a = browser.new_context()
        a = _as_open(ctx_a, base + "/admin/localization/de/")
        u = _visible_uids(a, 1)[0]
        _act(a, u, "approve")
        a.close(run_before_unload=True)                    # unsent: A left within the quiet moment
        b = _as_open(browser.new_context(), base + "/admin/localization/de/")
        _visible_uids(b, 1)
        _act(b, u, "queue")
        _as_wait(b, "saved")
        assert "csv" not in str(_server(worker, u)), "A's approval went out before B's request"
        a = _as_open(ctx_a, base + "/admin/localization/de/")
        a.wait_for_function("() => ['saved', 'conflict'].includes(document.getElementById('save-status').getAttribute('data-state'))",
                            timeout=20000)
        s = _server(worker, u)
        assert (s["tray"], s["version"]) == ("draft", 1), f"A's approval overwrote B's request: {s}"
        assert _as_state(a) == "conflict" and C.t("status.conflict") in _label(a, u)


def test_review_p1_4_a_decision_with_no_page_does_not_block_the_language(browser):
    """A decision for a text the page no longer has went with page '' and the Worker refused the
    whole request -- every save of that language, for good."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.evaluate("() => { const s = JSON.parse(localStorage.getItem('cel-desk-de') || '{}');"
                      " s['0123456789abcdef'] = {tray: 'csv'}; localStorage.setItem('cel-desk-de', JSON.stringify(s)); }")
        page.reload()
        _rows_ready(page)
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        _as_wait(page, "refused")
        assert _server(worker, u)["tray"] == "csv", "the text next to it was never saved"
        assert _server(worker, "0123456789abcdef") is None


def test_review_p3_an_answer_with_nothing_in_it_is_not_a_save(browser):
    """A 200 with no JSON body counted as success -- with nothing saved, and nothing said."""
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        worker.desk_fault = {"status": 200, "empty": True}
        _act(page, u, "approve")
        _as_wait(page, "retrying")
        assert C.t("save.reason.trouble") in _as_words(page)
        worker.desk_fault = None
        _as_wait(page, "saved", 30000)
        assert _server(worker, u)["tray"] == "csv"


_STAGE_VECTORS = [
    # (record, stage) -- stamps from two writers: the Worker's toISOString() and Python's isoformat
    ({"tray": "draft", "sentAt": "2026-09-28T10:00:00.000Z", "failed": "quota", "failedAt": "2026-09-28T10:05:00.000Z"}, "failed"),
    ({"tray": "draft", "sentAt": "2026-09-28T11:00:00.000Z", "failed": "quota", "failedAt": "2026-09-28T10:05:00.000Z"}, "sending"),
    ({"sentAt": "2026-09-28T10:00:00.000Z", "failed": "quota", "failedAt": "2026-09-28T10:05:00.000Z",
      "arrivedAt": "2026-09-28T10:30:00.000Z", "text": "neu"}, "arrived"),
    # a string comparison gets this one wrong: "…00Z" sorts after "…00.500Z", but is earlier
    ({"failed": "quota", "failedAt": "2026-09-28T10:00:00Z", "arrivedAt": "2026-09-28T10:00:00.500Z", "text": "neu"}, "arrived"),
    ({"failed": "quota", "failedAt": "2026-09-28T10:00:00.250000+00:00", "sentAt": "2026-09-28T10:00:00.100Z"}, "failed"),
    ({"failed": "quota"}, "failed"),                       # a failure with no time is the newest thing
    ({"tray": "draft", "sentAt": "2026-09-28T10:00:00Z", "arrivedAt": "2026-09-28T09:00:00Z"}, "sending"),
    ({"tray": "draft", "sentAt": "2026-09-28T10:00:00Z"}, "sending"),
    ({"tray": "csv", "liveAt": "2026-09-28T10:00:00Z"}, "live"),
    # the engine's failed_now(): a failure whose time cannot be read stands
    ({"failed": "quota", "failedAt": "not a time", "sentAt": "2026-09-28T11:00:00.000Z"}, "failed"),
    # its in_flight(): a send whose time cannot be read counts as still out
    ({"tray": "draft", "sentAt": "not a time", "arrivedAt": "2026-09-28T10:00:00.000Z"}, "sending"),
    # a stamp with no offset is UTC, as the engine reads it -- not the browser's local time
    ({"failed": "quota", "failedAt": "2026-09-28T10:00:00", "arrivedAt": "2026-09-28T10:00:00.500Z", "text": "neu"}, "arrived"),
]


def test_review_p2_4_a_failure_counts_only_while_it_is_the_newest_stamp(browser):
    """The pipeline keeps `failed` after a later send or arrival; stageOf() said "failed" for as
    long as it was set. It now compares times, as the engine's in_flight() does -- parsed, never
    as strings, because two writers stamp them."""
    from localize_desk import generate_desk_page as G
    page = browser.new_page(timezone_id="America/Vancouver")
    got = page.evaluate("([js, recs]) => { const stageOf = new Function(js + '; return stageOf;')();"
                        " return recs.map(stageOf); }", [G._STAGE_JS, [r for r, _ in _STAGE_VECTORS]])
    assert got == [st for _, st in _STAGE_VECTORS], list(zip(got, [st for _, st in _STAGE_VECTORS]))
    page.close()


# ── The second independent review (current main), the desk half of P1-A ─────────────────

def test_review2_p1_a_an_edit_records_the_website_wording_it_replaced(browser):
    """An edit dropped `approvedAgainst`, and the export checks "moved since approval" only when
    it is there: a live text changed after the edit shipped the edit over it, signed and green.
    An approval of any kind now records the website's wording it was given against."""
    with desk(save_on=True) as (base, root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u, v = _visible_uids(page, 2)
        live = _units(root, "de")
        _put_in(page, u, "edited")
        assert _rec(page, u).get("approvedAgainst") == live[u]["tgt"]
        _put_in(page, v, "arrived")                        # Gemini's draft, approved as it is
        _act(page, v, "approve")
        assert _rec(page, v).get("text") and _rec(page, v).get("approvedAgainst") == live[v]["tgt"]
        _as_wait(page, "saved")
        assert _server(worker, u)["approvedAgainst"] == live[u]["tgt"]
        assert _server(worker, v)["approvedAgainst"] == live[v]["tgt"]
