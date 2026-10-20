"""Robot click-tests for the reason a failed Translate page job shows on the document page (CEL-103).

The engine records why a collect brought nothing in the job's `result.reason` (CEL-095): an English sentence for the
team's log ("the model's reply was not valid JSON (...)"). The desk words it from COPY.md and adds it to the banner's
"The translation did not finish" line. A reason it does not know adds nothing, and nothing of the engine's own
sentence is shown as it is. A failed job without a reason reads exactly as before.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker; the engine is played by `store.finish_job`). Expected wording comes from
COPY.md through `copy_text`, never typed here. The harness helpers are COPIED from test_document_states_browser.py
(the convention of this folder: no imports between test files). Desktop only (Ruling 23:48).
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright lives in the monorepo's .venv314; the CEL hook and the "
                           "browser CI job run this file with it")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import harness as H  # noqa: E402

PAGE_KEY = "cost-of-studying-english"
LANG = "fr"
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')


# ── the harness, copied from test_document_weglot_browser.py ───────────────────────────────────
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk(save_on: bool = True):
    root = H.stage_copy(save_on=save_on, save_off=False)
    worker = H.MockWorker(root)
    server = H.make_server(root, worker, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", root, worker
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class Env:
    base: str
    root: Path
    worker: object
    store: object
    page: object = None
    errors: list = field(default_factory=list)


@lru_cache(maxsize=None)
def _stage_data(name: str = PAGE_KEY) -> dict:
    path = H.REPO_DOCS / "admin" / "localization" / "document" / "data" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def doc(browser, *, key: str = PAGE_KEY, lang: str = LANG, seed=None, timing: dict | None = None,
        http_errors: bool = False):
    """The document page open and ready; asserts no page error and no console error on a normal exit."""
    with desk() as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store)
        if seed:
            seed(env)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(10000)
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            url = (msg.location or {}).get("url", "") or ""
            if msg.type != "error" or url.endswith("/favicon.ico"):
                return
            if http_errors and "Failed to load resource" in msg.text:
                return
            env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.add_init_script("window.DOC_TIMING=" + json.dumps({**TIMING, **(timing or {})}))
        pg.goto(f"{base}/admin/localization/document/?page={key}&lang={lang}")
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def until(fn, timeout: float = 6.0, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def jobs(e):
    return [j for j in e.store.jobs.values() if j["locale"] == LANG and j["kind"] == "translate-page"]


def fail_the_job(e, result, error="nothing-arrived"):
    """Translate page pressed from the banner, then the engine ends the job as failed with this result."""
    e.page.locator("#doc-banner-translate").click()
    expect(e.page.locator("#doc-confirm")).to_be_visible()
    e.page.locator("#doc-confirm-ok").click()
    until(lambda: len(jobs(e)) == 1, what="the job")
    e.store.finish_job(LANG, "translate-page", "failed", result, error=error)


def banner(e):
    return e.page.locator("#doc-banner-text")


WITHOUT_WHY = C.t("doc.job.failed", reason=C.t("job.failed.nothing-arrived"))

# what the engine's collect writes today (tools/localize/batch.py parse_results), with the detail it adds
CASES = [
    ("not valid JSON", "the model's reply was not valid JSON (Expecting ',' delimiter: line 1 column 3; it ends '...\"}')", "doc.job.why.json"),
    ("not an object", "the model's reply was not an object (a list)", "doc.job.why.shape"),
    ("nothing for a row", "the model returned nothing for this row", "doc.job.why.empty"),
]


@pytest.mark.parametrize("name, reason, key", CASES, ids=[c[0] for c in CASES])
def test_a_failed_translation_says_why_in_the_desks_own_words(browser, name, reason, key):
    with doc(browser, lang=LANG) as e:
        fail_the_job(e, {"runId": "r1", "drafts": 0, "failed": 186, "collected": True, "reason": reason})
        expect(banner(e)).to_have_text(WITHOUT_WHY + " " + C.t("doc.job.why", why=C.t(key)))
        shown = banner(e).inner_text()
        assert "model" not in shown and "JSON" not in shown.replace(C.t("doc.job.why.json"), "")   # the engine's sentence is never shown


def test_a_reason_the_desk_does_not_know_adds_nothing(browser):
    with doc(browser, lang=LANG) as e:
        fail_the_job(e, {"runId": "r1", "drafts": 0, "failed": 3, "collected": True, "reason": "something new nobody worded"})
        expect(banner(e)).to_have_text(WITHOUT_WHY)


@pytest.mark.parametrize("result", [None, {"runId": "r1", "drafts": 0}, {"reason": 7}, {"reason": None}])
def test_a_failed_job_with_no_usable_reason_reads_as_it_did(browser, result):
    with doc(browser, lang=LANG) as e:
        fail_the_job(e, result)
        expect(banner(e)).to_have_text(WITHOUT_WHY)


def test_the_reason_goes_with_a_known_error_code_too(browser):
    with doc(browser, lang=LANG) as e:
        fail_the_job(e, {"reason": "the model's reply was not valid JSON (x)"}, error="engine-stopped")
        expect(banner(e)).to_have_text(C.t("doc.job.failed", reason=C.t("job.failed.engine-stopped")) + " "
                                       + C.t("doc.job.why", why=C.t("doc.job.why.json")))
