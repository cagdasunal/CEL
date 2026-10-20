"""Robot click-tests for the shell's follow-ups (CEL-101; CEL-069 round-1 review): the page tree folds without hiding where you
are, a failed page is told apart by shape as well as colour, and the shell's colour rows follow shell-spec.md section 1.

  * a folded folder keeps showing the OPEN page's row (and its sections); the others are hidden; this holds across a reload;
  * the fold button keeps the keyboard focus after its click; a stored fold value that is not a list is ignored;
  * a failed page's mark is a square (every other status is round), in --err, which keeps 3:1 on the five grounds of the spec;
  * the `/` hint sits on --stage (#E8E1CF) and the keyboard-highlighted row's slug is --accent-strong, as the open row's is.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the storage's
stand-in behind a mock Worker). The harness helpers are COPIED from test_document_shell_browser.py (the convention of this
folder: no imports between test files). Desktop only (Ruling 23:48).
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
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
LANG = "de"
LANGS = ["de", "fr", "es", "pt", "it", "ja", "ko", "ar"]
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
# Records whether the page's own keydown handlers prevented the default: a bubble listener on window runs after
# the desk's listeners on document.
SPY_KEYS = "window.__dp = []; window.addEventListener('keydown', function (e) { window.__dp.push([e.code, e.defaultPrevented]); });"


# ── the harness, copied from test_document_states_browser.py ───────────────────────────────────
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


@contextmanager
def doc(browser, *, key: str = PAGE_KEY, lang: str = LANG, width: int = 1440, path: str = "document"):
    """The page open and ready; asserts no page error and no console error on a normal exit."""
    with desk() as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store)
        pg = browser.new_page(viewport={"width": width, "height": 900})
        pg.set_default_timeout(10000)
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            url = (msg.location or {}).get("url", "") or ""
            if msg.type != "error" or url.endswith("/favicon.ico"):
                return
            env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.add_init_script("window.DOC_TIMING=" + json.dumps(TIMING))
        if path == "document":
            pg.goto(f"{base}/admin/localization/document/?page={key}&lang={lang}")
            pg.wait_for_selector(READY, timeout=20000)
            pg.wait_for_selector(".doc-tree-page", timeout=20000)
        else:
            pg.goto(f"{base}/admin/localization/rules/?lang={lang}")
            pg.wait_for_selector('#rules-app[data-state="ready"]', timeout=20000)
        pg.evaluate(SPY_KEYS)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def now(page):
    return page.evaluate("""() => [(document.querySelector('.doc-tree-page[aria-current="page"]') || {dataset: {}}).dataset.page || null,
        (document.querySelector('.doc-tab[aria-selected="true"]') || {dataset: {}}).dataset.lang || null,
        new URL(location.href).searchParams.get('page'), new URL(location.href).searchParams.get('lang')]""")


def wait_open(page, key, lang):
    page.wait_for_function("""([k, l]) => document.querySelector('#doc').dataset.state === 'ready'
        && document.querySelector('.doc-tree-page[aria-current="page"]').dataset.page === k
        && document.querySelector('.doc-tab[aria-selected="true"]').dataset.lang === l""", arg=[key, lang], timeout=20000)


def rows(page):
    return page.eval_on_selector_all(".doc-tree-page", "els => els.map(r => r.dataset.page)")


def until(fn, timeout: float = 6.0, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb):
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def rgb(css: str):
    nums = re.findall(r"[0-9.]+", css)
    return tuple(int(float(n)) for n in nums[:3])


# shell-spec section 1: the five grounds a status mark sits on (bar / tree / hover / open / selected tab)
GROUNDS = {"bar": (0xF1, 0xEA, 0xD8), "tree": (0xE7, 0xDE, 0xC7), "hover": (0xEC, 0xE4, 0xCF),
           "open": (0xF1, 0xEA, 0xD8), "tab": (0xE0, 0xDA, 0xC9)}


# ── folding ────────────────────────────────────────────────────────────────────────────────────
def test_a_folded_folder_keeps_the_open_page_and_its_sections(browser):
    with doc(browser) as e:
        p = e.page
        fold = p.locator(".doc-tree-fold").first
        fold.click()
        expect(fold).to_have_attribute("aria-expanded", "false")
        assert rows(p) == [PAGE_KEY]                                         # the others are hidden, where you are is not
        expect(p.locator('.doc-tree-page[aria-current="page"] + #doc-outline')).to_be_visible()
        p.reload()
        p.wait_for_selector(READY, timeout=20000)
        p.wait_for_selector(".doc-tree-page", timeout=20000)
        expect(p.locator(".doc-tree-fold").first).to_have_attribute("aria-expanded", "false")
        assert rows(p) == [PAGE_KEY]
        expect(p.locator('.doc-tree-page[aria-current="page"] + #doc-outline')).to_be_visible()
        p.locator(".doc-tree-fold").first.click()
        assert len(rows(p)) == 4


def test_the_fold_button_keeps_the_keyboard_after_its_click(browser):
    with doc(browser) as e:
        p = e.page
        p.locator(".doc-tree-fold").first.focus()
        p.keyboard.press("Enter")
        assert p.evaluate("document.activeElement.classList.contains('doc-tree-fold')")
        assert p.evaluate("document.activeElement.dataset.dir") == p.evaluate("document.querySelector('.doc-tree-fold').dataset.dir")
        p.keyboard.press("Enter")                                            # and Enter again unfolds it from the same place
        assert len(rows(p)) == 4
        assert p.evaluate("document.activeElement.classList.contains('doc-tree-fold')")


@pytest.mark.parametrize("stored", ["7", '"a-string"', '{"a": 1}', "null", "true"])
def test_a_stored_fold_value_that_is_not_a_list_is_ignored(browser, stored):
    with desk() as (base, root, worker):
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(10000)
        errors = []
        pg.on("pageerror", lambda err: errors.append(str(err)))
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        pg.add_init_script("window.DOC_TIMING=" + json.dumps(TIMING))
        pg.add_init_script(f"localStorage.setItem('cel-doc-fold', {json.dumps(stored)});")
        try:
            pg.goto(f"{base}/admin/localization/document/?page={PAGE_KEY}&lang={LANG}")
            pg.wait_for_selector(READY, timeout=20000)
            pg.wait_for_selector(".doc-tree-page", timeout=20000)
            assert len(rows(pg)) == 4 and errors == []
        finally:
            pg.close()


# ── the failed mark ────────────────────────────────────────────────────────────────────────────
def fail_one_page(e):
    """The open page in French, never translated: Translate page from the banner, then the engine fails the job."""
    e.page.locator("#doc-banner-translate").click()
    expect(e.page.locator("#doc-confirm")).to_be_visible()
    e.page.locator("#doc-confirm-ok").click()
    until(lambda: [j for j in e.store.jobs.values() if j["locale"] == "fr" and j["kind"] == "translate-page"], what="the job")
    e.store.finish_job("fr", "translate-page", "failed", None, error="engine-stopped")
    expect(e.page.locator(f'.doc-tree-page[data-page="{PAGE_KEY}"]')).to_have_attribute("data-status", "failed")


MARK_JS = """sel => { const el = document.querySelector(sel); const s = getComputedStyle(el);
    return {radius: s.borderTopLeftRadius, w: el.getBoundingClientRect().width, h: el.getBoundingClientRect().height,
            bg: s.backgroundColor, border: s.borderTopColor, style: s.borderTopStyle}; }"""


def test_a_failed_page_is_a_square_in_the_error_colour_and_every_other_mark_is_round(browser):
    with doc(browser, lang="fr") as e:
        p = e.page
        fail_one_page(e)
        failed = p.evaluate(MARK_JS, f'.doc-tree-page[data-page="{PAGE_KEY}"] .doc-st')
        assert failed["w"] == failed["h"] == 8 and failed["radius"] == "2px", failed        # a square, 2 px corners
        assert failed["bg"] == failed["border"] and failed["style"] == "solid"                  # filled in --err
        round_ones = p.evaluate("""() => [...document.querySelectorAll('.doc-tab .doc-st, .doc-tree-page .doc-st')]
            .filter(el => el.dataset.s !== 'failed').map(el => getComputedStyle(el).borderTopLeftRadius)""")
        assert round_ones and set(round_ones) == {"50%"}                                     # none / queued / ... stay round
        err = rgb(failed["bg"])
        for name, ground in GROUNDS.items():
            assert ratio(err, ground) >= 3.0, (name, ratio(err, ground))


# ── the colour rows ────────────────────────────────────────────────────────────────────────────
def test_the_slash_hint_sits_on_stage_and_the_highlighted_row_slug_is_accent_strong(browser):
    with doc(browser) as e:
        p = e.page
        hint = p.evaluate("""() => { const s = getComputedStyle(document.querySelector('.doc-kbd-hint'));
            return {bg: s.backgroundColor, color: s.color}; }""")
        assert rgb(hint["bg"]) == (0xE8, 0xE1, 0xCF), hint
        assert ratio(rgb(hint["color"]), rgb(hint["bg"])) >= 4.5
        p.locator(".doc-tree-fold").first.focus()
        p.keyboard.press("/")
        p.keyboard.press("ArrowDown")                                        # highlight a row that is not the open one
        slug = p.evaluate("""() => { const r = document.querySelector('.doc-tree-page.is-kb');
            return r && {page: r.dataset.page, color: getComputedStyle(r.querySelector('.doc-tree-slug')).color}; }""")
        assert slug is not None and rgb(slug["color"]) == (0x4E, 0x51, 0xBE), slug
        open_slug = p.evaluate("getComputedStyle(document.querySelector('.doc-tree-page[aria-current=\"page\"] .doc-tree-slug')).color")
        assert rgb(open_slug) == (0x4E, 0x51, 0xBE)
