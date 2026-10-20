"""Robot click-tests for the link markers of the document view (CEL-096): a reviewer sees "Learn More" and "Contact Us" as
two links, not as the numbers 1 and 2.

  * READ columns (English, the website's text): the words between a pair carry a dotted underline and the hover "Link 1";
    no marker and no number is drawn.
  * The column being EDITED: a pair is two compact chips (‹ and ›) with no number, a hover that says which end it is, and
    the two light up together; a chip with no partner is drawn broken.
  * A draft that lacks a link the English has, has an extra one, has them in another order or leaves one open says so
    under the text, in COPY.md's words; a draft with all its links says nothing and takes no room.
  * What is saved is exactly what it was: the markers are still the text's own, byte for byte.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text`, never typed here. The
harness helpers are COPIED from test_document_states_browser.py (the convention of this folder: no imports between test
files). Desktop only (Ruling 23:48).
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
LANG = "de"
U = "2fd35c71420736a4"                       # <a wg-1="">Learn More</a><a wg-2="">Contact Us</a>  (de: Mehr erfahren / Kontaktiere uns)
EN = '<a wg-1="">Learn More</a><a wg-2="">Contact Us</a>'
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')
GOOD = '<a wg-1="">Mehr erfahren</a><a wg-2="">Kontaktiere uns</a>'


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


def draft(store, uid, text, lang=LANG):
    store.drafts[(lang, uid)] = {"text": text, "arrivedAt": "2026-10-01T10:00:00.000Z"}


def until(fn, timeout: float = 6.0, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def seeded(text):
    return lambda e: draft(e.store, U, text)


def settle(page):
    """Two animation frames: a scroll the page was moved by is heard (the desk's tooltip hides on any scroll) before the pointer arrives."""
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def hover(page, loc):
    loc.scroll_into_view_if_needed()
    settle(page)
    loc.hover()


def line(page, uid=U):
    return blk(page, uid).locator(".doc-note-links")


# ── the read columns ───────────────────────────────────────────────────────────────────────────
def test_the_english_column_shows_two_links_underlined_and_no_numbers(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        en = blk(e.page, U).locator(".doc-en")
        assert en.inner_text() == "Learn MoreContact Us"                   # the words, no marker, no number
        links = en.locator(".rf-link")
        expect(links).to_have_count(2)
        assert links.all_inner_texts() == ["Learn More", "Contact Us"]
        assert en.locator(".rf-token").count() == 0
        for i in range(2):
            css = links.nth(i).evaluate("el => { const s = getComputedStyle(el); return [s.textDecorationLine, s.textDecorationStyle]; }")
            assert css == ["underline", "dotted"], css
        assert [links.nth(i).get_attribute("data-link") for i in range(2)] == ["1", "2"]


def test_the_hover_on_a_link_says_which_link_it_is(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        links = blk(e.page, U).locator(".doc-en .rf-link")
        for i in range(2):
            hover(e.page, links.nth(i))
            expect(e.page.locator(".desk-tip")).to_have_text(C.t("doc.link", n=i + 1))
            e.page.mouse.move(5, 5)


def test_the_website_text_column_shows_its_links_the_same_way(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        e.page.locator("#doc-weglot").check(force=True)
        wg = blk(e.page, U).locator(".doc-weglot")
        expect(wg).to_be_visible()
        assert wg.inner_text() == "Mehr erfahrenKontaktiere uns"
        expect(wg.locator(".rf-link")).to_have_count(2)
        assert wg.locator(".rf-token").count() == 0


# ── the column being edited ────────────────────────────────────────────────────────────────────
def test_the_edited_column_has_two_chips_for_each_link_and_no_number(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        tgt = blk(e.page, U).locator(".doc-tgt")
        chips = tgt.locator(".rf-token")
        expect(chips).to_have_count(4)
        assert chips.all_inner_texts() == ["‹", "›", "‹", "›"]
        assert not re.search(r"[0-9]", tgt.inner_text()), tgt.inner_text()
        assert [chips.nth(i).get_attribute("data-tip") for i in range(4)] == [
            C.t("doc.link.start", n=1), C.t("doc.link.end", n=1), C.t("doc.link.start", n=2), C.t("doc.link.end", n=2)]
        assert [chips.nth(i).get_attribute("data-broken") for i in range(4)] == [None] * 4
        hover(e.page, chips.nth(2))
        expect(e.page.locator(".desk-tip")).to_have_text(C.t("doc.link.start", n=2))


def test_the_two_chips_of_a_pair_light_up_together(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        chips = blk(e.page, U).locator(".doc-tgt .rf-token")
        chips.nth(2).hover()
        lit = [chips.nth(i).evaluate("el => el.classList.contains('rf-lit')") for i in range(4)]
        assert lit == [False, False, True, True]
        e.page.mouse.move(5, 5)
        assert [chips.nth(i).evaluate("el => el.classList.contains('rf-lit')") for i in range(4)] == [False] * 4


def test_a_draft_with_all_its_links_says_nothing_and_takes_no_room(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        expect(line(e.page)).to_have_text("")
        assert line(e.page).evaluate("el => el.getBoundingClientRect().height") == 0


@pytest.mark.parametrize("text, key, params, broken", [
    ('<a wg-1="">Mehr erfahren</a> Kontakt', "doc.link.warn.missing", {"n": 2}, 0),
    ('<a wg-1="">Mehr erfahren</a><a wg-2="">Kontakt</a><a wg-3="">Mehr</a>', "doc.link.warn.extra", {"n": 3}, 0),
    ('<a wg-2="">Kontaktiere uns</a><a wg-1="">Mehr erfahren</a>', "doc.link.warn.order", {}, 0),
    ('<a wg-1="">Mehr erfahren</a><a wg-2="">Kontaktiere uns', "doc.link.warn.broken", {}, 1),
    ('<a wg-1="">Mehr erfahren</a>Kontaktiere uns</a>', "doc.link.warn.missing", {"n": 2}, 1),
])
def test_a_draft_missing_a_link_or_out_of_order_says_so_under_the_text(browser, text, key, params, broken):
    with doc(browser, seed=seeded(text)) as e:
        expect(line(e.page)).to_have_text(C.t(key, **params))
        assert line(e.page).evaluate("el => el.getBoundingClientRect().height") > 0
        # a chip with no partner is drawn broken, the others are not
        assert blk(e.page, U).locator(".doc-tgt .rf-token[data-broken]").count() == broken
        # and nothing is repainted into the English column
        assert blk(e.page, U).locator(".doc-en").inner_text() == "Learn MoreContact Us"


def test_typing_in_a_text_with_links_saves_the_markers_exactly_as_they_were(browser):
    with doc(browser, seed=seeded(GOOD)) as e:
        tgt = blk(e.page, U).locator(".doc-tgt")
        tgt.click()
        e.page.evaluate("""() => { const f = document.querySelector('li.doc-block[data-uid="%s"] .doc-tgt');
            const r = document.createRange(); r.selectNodeContents(f); r.collapse(false);
            const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""" % U)
        e.page.keyboard.type(" !")
        until(lambda: e.store.decisions.get((LANG, U)), what="the saved text")
        saved = e.store.decisions[(LANG, U)]["record"]["text"]
        assert MARK.findall(saved) == MARK.findall(GOOD)
        assert MARK.sub("", saved) == "Mehr erfahrenKontaktiere uns !"
        expect(line(e.page)).to_have_text("")
