"""Robot click-tests for the desk UX fixes D (CEL-093): the Export window and the messages.

One test per fix the step carries: item 1 (a page whose translation is out is not offered when it has no text, and is
when it has), item 8 (the lowest message stays clear of the BugHerd tab). The words of item 2 are pinned in
tests/test_copy_ux_d.py. Expected wording comes from COPY.md through `copy_text.t`, never typed here. Every test also
asserts the page raised no error and logged none to the console, through `doc()`.

The harness helpers are COPIED from test_document_ux_a_browser.py (the convention of this folder: no imports between
test files). Desktop only (Ruling 23:48).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
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
PAGES = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]
LANGS = ["de", "fr", "es", "pt", "it", "ja", "ko", "ar"]
LANG = "de"
READY = '#doc[data-state="ready"]'
# Autosave in ~0.2 s instead of 2 s / 10 s; the poll for a running job every 0.2 s.
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')


# ── the harness, copied from test_document_ux_a_browser.py ─────────────────────────────────────────
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk(mode: str = "", save_on: bool = False, save_off: bool = False):
    """The harness on a free port: a temporary copy of docs/ and the mock Worker."""
    root = H.stage_copy(save_on=save_on, save_off=save_off)
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


@dataclass
class Env:
    base: str
    root: Path
    worker: object
    store: object
    data: dict                    # the open page's JSON (blocks ...)
    pages: dict                   # data/pages.json
    lang: str = LANG
    key: str = PAGE_KEY
    page: object = None
    errors: list = field(default_factory=list)


def _json(root: Path, name: str) -> dict:
    return json.loads((root / "admin" / "localization" / "document" / "data" / f"{name}.json")
                      .read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _stage_json(name: str) -> dict:
    """The generated page data as committed in docs/ (what the harness copies): read once, to choose the
    texts a test seeds before any browser opens."""
    path = H.REPO_DOCS / "admin" / "localization" / "document" / "data" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_data(name: str = PAGE_KEY) -> dict:
    return _stage_json(name)


def _url(base: str, key: str, lang: str) -> str:
    return f"{base}/admin/localization/document/?page={key}&lang={lang}"


@contextmanager
def doc(browser, *, lang: str = LANG, key: str = PAGE_KEY, seed=None, timing: dict | None = None,
        size: tuple[int, int] = (1440, 900), http_errors: bool = False, init: tuple = ()):
    """The document page open and ready, with a `DOC_TIMING` that makes autosave quick.

    `seed(env)` runs before the page loads (put drafts, decisions, pipeline stamps in `env.store`).
    On a normal exit it asserts no page error and no console error happened (scenario 14); an HTTP
    failure the test asked for (`http_errors`) and a missing favicon are not errors."""
    with desk(save_on=True) as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store, data=_json(root, key),
                  pages=_json(root, "pages"), lang=lang, key=key)
        if seed:
            seed(env)
        pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
        pg.set_default_timeout(10000)
        # The dashboard's BugHerd tag is a third party: it is answered here with an empty script, so a console
        # error from BugHerd's own pages (CI run 39383869039: 'X-Frame-Options') can never fail a test, and the
        # no-console-error check below stays about our own code (CEL-067).
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            if msg.type != "error":
                return
            url = (msg.location or {}).get("url", "") or ""
            if url.endswith("/favicon.ico"):
                return
            if http_errors and "Failed to load resource" in msg.text and "__worker" in url:
                return
            env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.add_init_script("window.DOC_TIMING=" + json.dumps(timing or TIMING))
        for script in init:
            pg.add_init_script(script)
        pg.goto(_url(base, key, lang))
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def draft(store, uid, text, lang=LANG, at="2026-10-01T10:00:00.000Z"):
    store.drafts[(lang, uid)] = {"text": text, "arrivedAt": at}


def clean(b: dict, lang: str = LANG, need_w: bool = False) -> bool:
    """A plain paragraph/list text that is on no other page: editing it touches nothing else."""
    if b["lock"] or b["b"] not in ("p", "li") or b.get("also") or b.get("out"):
        return False
    w = b.get("w", {}).get(lang, "")
    if MARK.search(b["en"]) or MARK.search(w) or not 12 <= len(b["en"]) <= 400:
        return False
    return bool(w) if need_w else True


def pick(data: dict, n: int = 1, *, lang: str = LANG, need_w: bool = False) -> list[str]:
    out = [b["id"] for b in data["blocks"] if clean(b, lang, need_w)][:n]
    assert len(out) == n, "the page data has too few plain texts for this test"
    return out


def cell(page, key, lang):
    return page.locator(f'.doc-cell[data-page="{key}"][data-lang="{lang}"]')


def wait_cells_known(page):
    page.wait_for_function("document.querySelectorAll('.doc-cell[data-status=\"unknown\"]').length === 0",
                           timeout=15000)


def open_export(page):
    page.locator("#doc-export").click()
    expect(page.locator("#ex-modal")).to_be_visible()


def ex_box(page, key, lang):
    return page.locator(f'#ex-grid input[data-page="{key}"][data-lang="{lang}"]')


def open_cell(page, key, lang):
    cell(page, key, lang).click()
    page.wait_for_function(
        """([k, l]) => document.querySelector('#doc').dataset.state === 'ready'
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.page === k
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.lang === l""",
        arg=[key, lang], timeout=20000)


# ── the tests ─────────────────────────────────────────────────────────────────────────────────────

def tip_of(page, loc):
    """Hover (pointer) `loc` and return the desk tooltip's text."""
    loc.hover()
    tip = page.locator(".desk-tip")
    expect(tip).to_be_visible()
    return tip.inner_text()


def _translate_page(p, with_texts=False):
    """Translate the open page. With texts it is the toolbar button and the whole-page window; with none it is the
    banner's button and the confirm box."""
    if with_texts:
        p.locator("#doc-translate").click()
        p.locator("#rp-go").click()
    else:
        p.locator("#doc-banner-translate").click()
        expect(p.locator("#doc-confirm")).to_be_visible()
        p.locator("#doc-confirm-ok").click()


# 1. a page whose translation is out is not offered for export while there is no text in it
def test_item_1_a_translating_or_queued_page_with_no_text_is_greyed_in_the_export_window(browser):
    first, second = PAGE_KEY, "vancouver"
    with doc(browser, lang="fr", http_errors=True) as e:          # the Worker's 409 is how the queue starts
        p = e.page
        _translate_page(p)                                         # this page: translating
        open_cell(p, second, "fr")
        _translate_page(p)                                         # the next page: queued, behind it
        expect(cell(p, first, "fr")).to_have_attribute("data-status", "translating")
        expect(cell(p, second, "fr")).to_have_attribute("data-status", "queued")
        wait_cells_known(p)
        open_export(p)
        for key in (first, second):
            expect(ex_box(p, key, "fr")).to_be_disabled()
            assert tip_of(p, ex_box(p, key, "fr")) == C.t("export.step.nothing")
        expect(ex_box(p, "vs-toronto", "fr")).to_be_disabled()      # nothing in it at all: greyed before this step too


def test_item_1_a_translating_or_queued_page_with_texts_stays_pickable(browser):
    first, second = PAGE_KEY, "vancouver"
    (u1,), (u2,) = pick(_stage_data(first), 1, lang="fr"), pick(_stage_data(second), 1, lang="fr")

    def seed(env):
        draft(env.store, u1, "Brouillon un", lang="fr")
        draft(env.store, u2, "Brouillon deux", lang="fr")

    with doc(browser, lang="fr", seed=seed, http_errors=True) as e:
        p = e.page
        _translate_page(p, with_texts=True)
        open_cell(p, second, "fr")
        _translate_page(p, with_texts=True)
        expect(cell(p, first, "fr")).to_have_attribute("data-status", "translating")
        expect(cell(p, second, "fr")).to_have_attribute("data-status", "queued")
        wait_cells_known(p)
        open_export(p)
        for key in (first, second):
            expect(ex_box(p, key, "fr")).to_be_enabled()           # a re-translated page keeps the texts it has


# 8. the lowest message stays clear of the BugHerd tab
# The tab is `<bugherd-sidebar>`'s #TOGGLE, measured on the live desk page 2026-10-20: fixed, right 0, bottom 10 px,
# 103 x 70 px. The harness answers bugherd.com with an empty script, so a box of that size stands in for it.
TAB_JS = """() => {
    const tab = document.createElement('div');
    tab.id = 'bugherd-tab-stand-in';
    tab.style.cssText = 'position:fixed;right:0;bottom:10px;width:103px;height:70px;z-index:2147483647';
    document.body.appendChild(tab);
    const box = el => { const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
    return { tab: box(tab), toasts: Array.from(document.querySelectorAll('#doc-toasts .toast')).map(box) };
}"""


@pytest.mark.parametrize("width,height", [(1024, 768), (1280, 800), (1440, 900)])
def test_item_8_the_messages_stay_clear_of_the_bugherd_tab(browser, width, height):
    with doc(browser, size=(width, height)) as e:
        p = e.page
        p.evaluate("""() => { DocDesk.toast('One', 'err'); DocDesk.toast('Two', 'warn'); DocDesk.toast('Three', 'err'); }""")
        expect(p.locator("#doc-toasts .toast")).to_have_count(3)    # errors and warnings stay until closed
        boxes = p.evaluate(TAB_JS)
        tab = boxes["tab"]
        assert tab["right"] == width and tab["bottom"] == height - 10, boxes
        assert len(boxes["toasts"]) == 3, boxes
        for b in boxes["toasts"]:
            hit = b["left"] < tab["right"] and b["right"] > tab["left"] and b["top"] < tab["bottom"] and b["bottom"] > tab["top"]
            assert not hit, f"a message sits under the BugHerd tab at {width}x{height}: {boxes}"
