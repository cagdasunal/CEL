"""Robot click-tests for the document desk's running / saving states (CEL-077): items 5, 12, 13, 17 and 19 of the
UX sweep (.team/CEL/runtime/out/loc2/ux-sweep/findings.md in the monorepo). The client always sees what is
running, what is not saved and where it is. One test per item (item 12 and 19 have two).

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text`, never typed
here. The harness helpers are COPIED from test_document_weglot_browser.py (the convention of this folder: no
imports between test files). Desktop only (Ruling 23:48).
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
OTHER_PAGE = "vancouver"
LANG = "de"
OTHER = "other@example.test"
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


def blk(page, uid):
    return page.locator(f'li.doc-block[data-uid="{uid}"]')


def bar(page):
    return page.locator("#doc-save")


def more(page):
    return page.locator("#doc-save-more")


def toasts(page):
    return page.locator("#doc-toasts")


def plain_ids(n: int, *, key: str = PAGE_KEY, after: int = 0) -> list[str]:
    out = [b["id"] for b in _stage_data(key)["blocks"][after:]
           if not b["lock"] and b["b"] in ("p", "li") and not b.get("also") and not b.get("out")
           and not MARK.search(b["en"]) and 12 <= len(b["en"]) <= 400][:n]
    assert len(out) == n, "the page data has too few plain texts for this test"
    return out


def draft(store, uid, text, lang=LANG):
    store.drafts[(lang, uid)] = {"text": text, "arrivedAt": "2026-10-01T10:00:00.000Z"}


def edit(page, uid, text):
    blk(page, uid).locator(".doc-tgt").click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type(text)


def in_view(page, uid) -> bool:
    return page.evaluate("""uid => { const r = document.querySelector('li.doc-block[data-uid="' + uid + '"]')
        .getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; }""", uid)


# ── 5. a Re-translate on its way shows on its text, and a job that never ends is given up ─────────
def _open_retranslate(page, uid):
    blk(page, uid).locator(".doc-tgt").click()
    page.locator(f'li.doc-block[data-uid="{uid}"] .doc-tool-retranslate').click()
    expect(page.locator("#rt-modal")).to_be_visible()
    page.locator("#rt-go").click()


def test_item_5_a_retranslate_on_its_way_is_said_on_the_text_and_its_button_is_off(browser):
    (u,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, u, "Alter Entwurf")) as e:
        p = e.page
        _open_retranslate(p, u)
        li = blk(p, u)
        expect(li.locator(".doc-note")).to_contain_text(C.t("doc.text.retranslating"))
        expect(li).to_have_attribute("data-retranslating", "")
        expect(li.locator(".doc-tool-retranslate")).to_be_disabled()
        # the engine finishes: the sign goes, the button is on again
        e.store.finish_job(LANG, "retranslate", "done", {"drafts": 1})
        expect(li).not_to_have_attribute("data-retranslating", "")
        expect(li.locator(".doc-tool-retranslate")).to_be_enabled()
        assert C.t("doc.text.retranslating") not in li.locator(".doc-note").inner_text()


def test_item_5_a_job_that_never_ends_is_given_up_with_a_reason(browser):
    (u,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, u, "Alter Entwurf"), timing={"jobMax": 1200}) as e:
        p = e.page
        _open_retranslate(p, u)
        expect(blk(p, u).locator(".doc-note")).to_contain_text(C.t("doc.text.retranslating"))
        expect(toasts(p)).to_contain_text(C.t("retr.failed", reason=C.t("retr.timeout")), timeout=8000)
        expect(blk(p, u)).not_to_have_attribute("data-retranslating", "")
        expect(blk(p, u).locator(".doc-tool-retranslate")).to_be_enabled()


def test_item_5_while_one_text_is_re_translated_the_other_texts_say_why_they_wait(browser):
    a, b = plain_ids(2)

    def seed(e):
        draft(e.store, a, "Alter Entwurf A")
        draft(e.store, b, "Alter Entwurf B")

    with doc(browser, seed=seed) as e:
        p = e.page
        _open_retranslate(p, a)
        own = blk(p, a).locator(".doc-tool-retranslate")
        other = blk(p, b).locator(".doc-tool-retranslate")
        # the Worker keeps one open re-translate job per language: a second Re-translate would only be refused as busy
        expect(own).to_be_disabled()
        expect(other).to_be_disabled()
        expect(other).to_have_attribute("data-tip", C.t("retr.wait"))     # the desk's tooltip, not the browser's `title`
        expect(own).not_to_have_attribute("data-tip", C.t("retr.wait"))
        e.store.finish_job(LANG, "retranslate", "done", {"drafts": 1})
        expect(other).to_be_enabled()
        expect(own).to_be_enabled()
        expect(other).not_to_have_attribute("data-tip", C.t("retr.wait"))


def test_item_5_the_desk_watches_longer_than_the_worker_keeps_a_job_open(browser):
    with doc(browser) as e:
        wait = e.page.evaluate("window.DocDesk.TIMING.jobMax")
        # The Worker fails an open job only after 35 min (JOB_STALE_MS, cloudflare-worker.js): giving up before that
        # leaves the job open there, and the next Try again answers busy while the toast said it had ended.
        assert wait > 35 * 60 * 1000, wait


# ── 12. a text that is not saved says why, and the bar can go to it ──────────────────────────────
def test_item_12_a_refused_text_says_so_and_the_bar_goes_to_it(browser):
    far = plain_ids(1, after=150)[0]

    def seed(e):
        raw = e.store.handle

        def handle(action, body, who):
            if action == "desk-write":                       # taken, but neither applied nor in conflict: refused
                return 200, {"ok": True, "applied": [], "conflicts": [], "refused": []}
            return raw(action, body, who)

        e.store.handle = handle

    with doc(browser, seed=seed) as e:
        p = e.page
        edit(p, far, "Dieser Text wird nicht angenommen")
        li = blk(p, far)
        expect(bar(p)).to_have_attribute("data-state", "refused")
        expect(li.locator(".doc-note")).to_contain_text(C.t("doc.text.refused"))
        assert C.t("doc.text.error") not in li.locator(".doc-note").inner_text()
        p.mouse.wheel(0, -100000)                            # back to the top of the page
        p.wait_for_timeout(300)
        assert not in_view(p, far)
        go = more(p).locator("#doc-save-go")
        expect(go).to_have_text(C.t("doc.save.go"))
        go.click()
        p.wait_for_function("""uid => { const r = document.querySelector('li.doc-block[data-uid="' + uid + '"]')
            .getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; }""", arg=far, timeout=8000)


def test_item_12_a_stopped_save_says_so_on_the_text(browser):
    (u,) = plain_ids(1)
    with doc(browser, http_errors=True) as e:
        p = e.page
        e.worker.desk_fault = {"status": 429, "error": "daily"}
        edit(p, u, "Text vor dem Halt")
        expect(bar(p)).to_have_attribute("data-state", "stopped")
        expect(blk(p, u).locator(".doc-note")).to_contain_text(C.t("doc.text.stopped"))
        expect(more(p).locator("#doc-save-go")).to_have_text(C.t("doc.save.go"))


# ── 13. 'changed elsewhere' names the language and page and goes there ───────────────────────────
def test_item_13_a_conflict_names_where_it_is_and_opens_it(browser):
    (u,) = plain_ids(1)
    with doc(browser) as e:
        p = e.page
        code, out = e.store.handle("desk-write", {"locale": LANG, "client": 1, "changes": [
            {"unit": u, "page": PAGE_KEY, "base": 0, "record": {"text": "Their text"}}]}, OTHER)
        assert code == 200 and out["applied"], out
        edit(p, u, "My text")
        expect(blk(p, u).locator(".doc-conflict")).to_be_visible()
        p.locator(f'.doc-cell[data-page="{OTHER_PAGE}"][data-lang="{LANG}"]').click()      # leave the page
        p.wait_for_function("new URL(location.href).searchParams.get('page') === '%s'" % OTHER_PAGE)
        expect(p.locator(READY)).to_be_visible()
        where = C.t("autosave.conflict.where", language=C.t(f"lang.{LANG}"), page=C.t(f"page.{PAGE_KEY}"))
        expect(more(p)).to_contain_text(where)
        expect(bar(p)).to_have_text(C.tn("autosave.conflict", 1))      # the bar's own count line is unchanged
        more(p).locator("#doc-conflict-go").click()
        p.wait_for_function("new URL(location.href).searchParams.get('page') === '%s'" % PAGE_KEY)
        expect(blk(p, u).locator(".doc-conflict")).to_be_visible()
        assert in_view(p, u)


# ── 17. texts Next has marked come back on request ───────────────────────────────────────────────
def test_item_17_looked_at_texts_can_be_shown_again(browser):
    ids = plain_ids(3)

    def seed(e):
        for n, uid in enumerate(ids):
            draft(e.store, uid, f"Entwurf {n + 1}")

    with doc(browser, seed=seed) as e:
        p = e.page
        count = p.locator("#doc-next-count")
        again = p.locator("#doc-seen-reset")
        expect(count).to_have_text(C.tn("doc.next.left", 3))
        assert not again.is_visible(), "nothing is looked at yet"
        for _ in range(3):
            p.locator("#doc-next").click()
        expect(count).to_have_text(C.tn("doc.next.left", 1))
        expect(again).to_have_text(C.tn("doc.next.again", 2))
        again.click()
        expect(count).to_have_text(C.tn("doc.next.left", 3))
        assert not again.is_visible()


# ── 19. Export: one zip, Stop, and a headline ────────────────────────────────────────────────────
def _tick(page, key, lang):
    page.locator(f'#ex-grid input[data-page="{key}"][data-lang="{lang}"]').check()


def test_item_19_the_count_says_one_zip_and_a_stopped_export_ends_with_a_headline(browser):
    (a,) = plain_ids(1)
    (b,) = plain_ids(1, key=OTHER_PAGE)

    def seed(e):
        draft(e.store, a, "Entwurf eins", LANG)
        draft(e.store, b, "Entwurf zwei", LANG)

    with doc(browser, seed=seed) as e:
        p = e.page
        p.locator("#doc-export").click()
        expect(p.locator("#ex-modal")).to_be_visible()
        _tick(p, OTHER_PAGE, LANG)
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 2))
        assert "zip" in p.locator("#ex-count").inner_text().lower()
        assert not p.locator("#ex-stop").is_visible()
        p.locator("#ex-go").click()
        first = p.locator(f'li.ex-file[data-page="{OTHER_PAGE}"][data-lang="{LANG}"]')     # pages go in page order
        expect(first).to_have_attribute("data-state", "queued", timeout=10000)
        stop = p.locator("#ex-stop")
        expect(stop).to_have_text(C.t("export.stop"))
        stop.click()
        expect(stop).to_have_text(C.t("export.stopping"))
        expect(stop).to_be_disabled()
        # the engine finishes the file already being made; the next one is not started
        csv = "Original,Translation\r\n\"Hello\",\"Hallo\"\r\n"
        e.store.seed_export("b-stop", LANG, csv, 1, [], None)
        e.store.finish_job(LANG, "export", "done", {"batchId": "b-stop", "rows": 1, "refused": [], "warned": [],
                                                    "notes": [], "skipped": {}})
        second = p.locator(f'li.ex-file[data-page="{PAGE_KEY}"][data-lang="{LANG}"]')
        expect(second).to_have_attribute("data-state", "stopped")
        expect(second).to_contain_text(C.t("export.step.stopped"))
        expect(p.locator("#ex-result .ex-headline")).to_have_text(C.t("export.result.stopped", done=1, total=2))
        assert len([j for j in e.store.jobs.values() if j["kind"] == "export"]) == 1, "a second job was started"
        assert not stop.is_visible()


def test_item_19_a_finished_export_says_how_many_files_were_made(browser):
    (a,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, a, "Entwurf eins", LANG)) as e:
        p = e.page
        p.locator("#doc-export").click()
        expect(p.locator("#ex-modal")).to_be_visible()
        p.locator("#ex-go").click()
        expect(p.locator(f'li.ex-file[data-page="{PAGE_KEY}"][data-lang="{LANG}"]')).to_have_attribute(
            "data-state", "queued", timeout=10000)
        csv = "Original,Translation\r\n\"Hello\",\"Hallo\"\r\n"
        e.store.seed_export("b-done", LANG, csv, 1, [], None)
        with p.expect_download():
            e.store.finish_job(LANG, "export", "done", {"batchId": "b-done", "rows": 1, "refused": [], "warned": [],
                                                        "notes": [], "skipped": {}})
        head = p.locator("#ex-result .ex-headline")
        expect(head).to_have_text(C.t("export.result.done", done=1, total=1))
        # a rule of its own on the Export window's scale (its neighbours `.ex-count` and `.ex-group-title` set theirs):
        # no browser margin on a bare <p>, the medium size, weight 500 like a group title
        look = head.evaluate("""el => { const cs = getComputedStyle(el), probe = document.createElement('span');
            probe.style.fontSize = 'var(--fs-md)'; el.appendChild(probe);
            const md = getComputedStyle(probe).fontSize; probe.remove();
            return { top: cs.marginTop, bottom: cs.marginBottom, weight: cs.fontWeight, size: cs.fontSize, md: md }; }""")
        assert look["top"] == "0px" and look["bottom"] == "0px", look
        assert look["weight"] == "500" and look["size"] == look["md"], look
