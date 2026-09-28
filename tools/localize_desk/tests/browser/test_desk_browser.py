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


def test_a_full_desk_stays_inside_its_budgets(browser):
    """L1 P3: with all eight languages decided, one click took 88 ms and a switch 0.26 s at
    4x CPU -- the budget test only ever measured an empty desk."""
    scale = float(os.environ.get("DESK_BUDGET_SCALE", "1"))
    with desk("new") as (base, root, _worker):
        page = browser.new_page()
        page.goto(base + "/admin/localization/de/")
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        for code in ("de", "fr", "es", "pt", "it", "ja", "ko", "ar"):
            recs = {u: {"tray": "csv", "by": "reviewer@example.test", "at": "2026-09-28T10:00:00Z",
                        "approvedAgainst": x["tgt"]} for u, x in _units(root, code).items()}
            page.evaluate("([c, r]) => { localStorage.setItem('cel-desk-' + c, r); localStorage.setItem('cel-desk-saved-' + c, r); }",
                          [code, json.dumps(recs)])
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 4})
        page.reload()
        page.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=60000)
        page.select_option("#f-state", "")
        clicks = sorted(page.evaluate("""() => { const b = document.querySelectorAll('tr[data-uid] [data-act="approve"]')[i];
            const t0 = performance.now(); b.click(); return performance.now() - t0; }""".replace("[i]", f"[{i}]")) for i in (0, 1, 2))
        page.wait_for_timeout(1500)
        switches = sorted(_timed_switch(page, code) for code in ("fr", "it", "es"))
        assert clicks[1] <= 40 * scale, f"a click took {clicks} ms (median over {40 * scale:.0f})"
        assert switches[1] <= 0.2 * scale, f"switch {switches} s, median over {0.2 * scale:.2f}"
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
    path, setup, scope = _STATES[state]
    with desk("new") as (base, _root, _worker):
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

def _save(page):
    page.locator("#btn-save").click()
    page.wait_for_function("() => !document.getElementById('btn-save').disabled", timeout=15000)
    page.wait_for_timeout(200)


def _server(worker, uid, locale="de"):
    row = worker.store.decisions.get((locale, uid))
    return None if row is None else {**row["record"], "version": row["version"], "by": row["by"]}


def test_a_save_lands_in_the_storage_and_another_computer_sees_it(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, errors = _open(browser, base + "/admin/localization/de/")
        u0, u1 = _visible_uids(page, 2)
        _act(page, u0, "approve")
        _act(page, u1, "queue")
        assert page.locator("#btn-save").is_visible()
        _save(page)
        s0 = _server(worker, u0)
        assert s0["tray"] == "csv" and s0["version"] == 1 and s0["by"] == "reviewer@example.test"
        assert s0["approvedAgainst"] == _units(_root, "de")[u0]["tgt"]
        assert _server(worker, u1)["tray"] == "draft"
        assert page.locator("#btn-save").is_hidden(), "nothing is unsaved after a save"
        _toast(page, C.t("save.done.title"))
        assert "desk-write" in worker.calls
        other = browser.new_context().new_page()          # another computer: no local copy
        other.goto(base + "/admin/localization/de/")
        other.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        assert _rec(other, u0).get("tray") == "csv" and _rec(other, u1).get("tray") == "draft"
        assert other.locator("#btn-save").is_hidden()
        assert not errors, errors
        page.close()


def test_someone_else_saving_first_is_a_conflict_on_the_row_and_theirs_can_be_taken(browser):
    with desk(save_on=True) as (base, _root, worker):
        a = browser.new_context().new_page()
        b = browser.new_context().new_page()
        for p in (a, b):
            p.goto(base + "/admin/localization/de/")
            p.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        u = _visible_uids(a, 1)[0]
        _visible_uids(b, 1)
        _act(a, u, "approve")
        _save(a)                                           # A saves first
        _act(b, u, "queue")
        _save(b)                                           # B's change was based on nothing
        assert _server(worker, u)["tray"] == "csv", "a conflict must never overwrite"
        assert C.t("status.conflict") in _label(b, u)
        _toast(b, C.t("save.conflicts.title"))
        _row(b, u).locator("[data-conflict]").click()     # use theirs
        assert _rec(b, u).get("tray") == "csv"
        assert b.locator("#btn-save").is_hidden(), "taking theirs leaves nothing to save"
        assert C.t("status.conflict") not in _label(b, u)


def test_keeping_yours_over_a_conflict_is_a_deliberate_save_on_their_version(browser):
    with desk(save_on=True) as (base, _root, worker):
        a = browser.new_context().new_page()
        b = browser.new_context().new_page()
        for p in (a, b):
            p.goto(base + "/admin/localization/de/")
            p.wait_for_function(f"document.querySelectorAll('{ROWS}').length > 800", timeout=20000)
        u = _visible_uids(a, 1)[0]
        _visible_uids(b, 1)
        _act(a, u, "approve")
        _save(a)
        _act(b, u, "queue")
        _save(b)
        _save(b)                                           # saving again does NOT overwrite
        assert _server(worker, u)["tray"] == "csv", "an undecided conflict was sent again"
        _put_in(b, u, "edited")                            # deciding again: yours, deliberately
        _save(b)
        s = _server(worker, u)
        assert (s["text"], s["version"]) == ("WO-06 wording of my own", 2), s


@pytest.mark.parametrize("status,error,reason", [
    (409, "desk out of date -- reload the page", "reload"),
    (429, "over the cap", "cap"),
    (429, "over the daily budget", "daily"),
    (503, "storage not configured", "unavailable"),
    (401, "session expired", "signed_out"),
    (500, "server error", "trouble"),
])
def test_a_failed_save_says_why_and_keeps_every_change(browser, status, error, reason):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        worker.desk_fault = {"status": status, "error": error}
        _save(page)
        toast = page.locator("#toast-stack").inner_text()
        assert C.t(f"save.reason.{reason}") in toast, toast
        assert page.locator("#btn-save").is_visible(), "the change must stay unsaved"
        assert _server(worker, u) is None
        worker.desk_fault = None
        _save(page)
        assert _server(worker, u)["tray"] == "csv"
        page.close()


def test_a_whole_language_saves_in_slices_the_storage_takes(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        page.select_option("#f-state", "")
        page.check("#pick-all")
        page.click("#bulk-approve")
        _save(page)
        assert worker.calls.count("desk-write") >= 5            # 823 in slices of 200
        assert sum(1 for (loc, _u) in worker.store.decisions if loc == "de") == 823
        assert page.locator("#btn-save").is_hidden()
        page.close()


def test_an_undo_after_a_save_is_saved_too(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        _act(page, u, "approve")
        _save(page)
        _act(page, u, "approve")                                 # undo
        _save(page)
        s = _server(worker, u)
        assert s["version"] == 2 and "tray" not in s
        page.close()


def test_a_text_the_storage_does_not_know_is_refused_and_kept(browser):
    with desk(save_on=True) as (base, _root, worker):
        page, _errors = _open(browser, base + "/admin/localization/de/")
        u = _visible_uids(page, 1)[0]
        worker.store.units = {(unit, pg) for unit, pg in worker.store.units if unit != u}
        _act(page, u, "approve")
        _save(page)
        _toast(page, C.t("save.refused.title"))
        assert _server(worker, u) is None and page.locator("#btn-save").is_visible()
        page.close()
