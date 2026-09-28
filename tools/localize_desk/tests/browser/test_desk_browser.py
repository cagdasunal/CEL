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
