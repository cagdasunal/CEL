"""Robot click-tests for the optional Weglot column of the document page (desk v2, CEL-060).

The column was built with the page (CEL-026; its on/off/reload test is in test_document_browser.py, section 8).
CEL-060 added what the client asked for on top of it, and this file holds the page to that:
  * a text Weglot has no wording for shows "No Weglot translation yet" in the column;
  * ONE small "Same as Weglot" mark appears under a text that is word for word Weglot's, only while the column
    is on, and nothing else is highlighted;
  * the column is read-only and never sent: the same edit writes the same bytes with the column on and off;
  * three columns fit at 1280 / 1440 / 2560 without a sideways scroll.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/,
the storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text.t`, never
typed here. The harness helpers are COPIED from test_document_browser.py (the convention of this folder: no
imports between test files). Desktop only (Ruling 23:48).
"""
from __future__ import annotations

import json
import re
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
LANG = "de"
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')


# ── the harness, copied from test_document_browser.py ──────────────────────────────────────
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk(save_on: bool = False):
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
def doc(browser, *, seed=None, size: tuple[int, int] = (1440, 900)):
    """The document page open and ready, autosave in ~0.2 s; asserts no page error and no console error."""
    with desk(save_on=True) as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store)
        if seed:
            seed(env)
        pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
        pg.set_default_timeout(10000)
        # The dashboard's BugHerd tag is a third party: answered here with an empty script, so a console error of
        # BugHerd's own pages can never fail a test (CEL-067).
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            url = (msg.location or {}).get("url", "") or ""
            if msg.type == "error" and not url.endswith("/favicon.ico"):
                env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.add_init_script("window.DOC_TIMING=" + json.dumps(TIMING))
        pg.goto(f"{base}/admin/localization/document/?page={PAGE_KEY}&lang={LANG}")
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def blk(page, uid):
    return page.locator(f'li.doc-block[data-uid="{uid}"]')


def clean(b: dict, need_w: bool) -> bool:
    """A plain paragraph/list text on no other page; with a Weglot wording (need_w) or without."""
    if b["lock"] or b["b"] not in ("p", "li") or b.get("also") or b.get("out") or MARK.search(b["en"]):
        return False
    w = b.get("w", {}).get(LANG, "")
    if need_w:
        return bool(w) and not MARK.search(w) and 12 <= len(b["en"]) <= 400
    return not w and 3 <= len(b["en"]) <= 400


def pick(n: int, need_w: bool) -> list[str]:
    out = [b["id"] for b in _stage_data()["blocks"] if clean(b, need_w)][:n]
    assert len(out) == n, "the page data has too few plain texts for this test"
    return out


def wording(uid: str) -> str:
    return next(b for b in _stage_data()["blocks"] if b["id"] == uid)["w"][LANG]


def draft(store, uid, text):
    store.drafts[(LANG, uid)] = {"text": text, "arrivedAt": "2026-10-01T10:00:00.000Z"}


def edit(page, uid, text):
    blk(page, uid).locator(".doc-tgt").click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type(text)


def show_weglot(page, on: bool = True):
    box = page.locator("#doc-weglot")
    box.check() if on else box.uncheck()


# ── the tests ──────────────────────────────────────────────────────────────────────────────
def test_a_text_weglot_has_no_wording_for_says_so_in_the_column(browser):
    (empty,) = pick(1, need_w=False)
    (full,) = pick(1, need_w=True)
    with doc(browser) as e:
        show_weglot(e.page)
        cell = blk(e.page, empty).locator(".doc-weglot")
        cell.scroll_into_view_if_needed()
        expect(cell).to_be_visible()
        assert cell.get_attribute("data-placeholder") == C.t("doc.weglot.none")
        shown = cell.evaluate("el => getComputedStyle(el, '::before').content")
        assert shown.strip('"') == C.t("doc.weglot.none")
        # a text Weglot has a wording for shows the wording and no placeholder
        other = blk(e.page, full).locator(".doc-weglot")
        assert other.get_attribute("data-placeholder") is None
        assert other.evaluate("el => getComputedStyle(el, '::before').content") in ("none", "normal")


def test_the_same_as_weglot_mark_shows_only_for_the_identical_wording_and_only_with_the_column_on(browser):
    same, differs = pick(2, need_w=True)
    with doc(browser, seed=lambda e: (draft(e.store, same, wording(same)),
                                      draft(e.store, differs, wording(differs) + " (new)"))) as e:
        mark = lambda uid: blk(e.page, uid).locator(".doc-note-same")  # noqa: E731
        # off by default: the mark is there in the DOM but not shown
        expect(e.page.locator("#doc-blocks")).to_have_attribute("data-weglot", "off")
        assert not mark(same).is_visible()

        show_weglot(e.page)
        blk(e.page, same).scroll_into_view_if_needed()
        expect(mark(same)).to_be_visible()
        expect(mark(same)).to_have_text(C.t("doc.weglot.same"))
        blk(e.page, differs).scroll_into_view_if_needed()
        assert mark(differs).inner_text().strip() == ""          # a different wording: no mark
        # nothing else is highlighted: no block carries a state or colour for being the same
        assert blk(e.page, same).get_attribute("data-same") is None

        # editing the text away from Weglot's wording takes the mark away at once
        edit(e.page, same, wording(same) + " changed")
        e.page.wait_for_function("uid => !document.querySelector('li.doc-block[data-uid=\"' + uid + '\"] "
                                 ".doc-note-same').textContent", arg=same)
        show_weglot(e.page, False)
        assert not mark(same).is_visible()


def test_the_weglot_cell_is_read_only_and_a_click_in_it_sends_nothing(browser):
    (uid,) = pick(1, need_w=True)
    with doc(browser) as e:
        show_weglot(e.page)
        cell = blk(e.page, uid).locator(".doc-weglot")
        cell.scroll_into_view_if_needed()
        assert cell.get_attribute("contenteditable") in (None, "false")
        before = e.page.evaluate("el => el.innerHTML", cell.element_handle())
        writes = []
        raw = e.store.handle
        e.store.handle = lambda a, b, who: (writes.append(a), raw(a, b, who))[1]
        cell.click()
        e.page.keyboard.type("typed into the Weglot column")
        e.page.wait_for_timeout(600)
        assert e.page.evaluate("el => el.innerHTML", cell.element_handle()) == before
        assert "desk-write" not in writes


def _write_bodies_for_one_edit(browser, uid, with_column: bool):
    sent = []

    def seed(e):
        raw = e.store.handle

        def spy(action, body, who):
            if action == "desk-write":
                sent.append(json.dumps(body["changes"], sort_keys=True))
            return raw(action, body, who)

        e.store.handle = spy

    with doc(browser, seed=seed) as e:
        if with_column:
            show_weglot(e.page)
        edit(e.page, uid, "The same edit with the column on or off")
        e.page.wait_for_function(
            "uid => { const li = document.querySelector('li.doc-block[data-uid=\"' + uid + '\"]');"
            " return li && li.dataset.state === 'saved'; }", arg=uid)
    return sent


def test_the_column_is_never_sent_the_same_edit_writes_the_same_bytes_with_it_on_and_off(browser):
    (uid,) = pick(1, need_w=True)
    on = _write_bodies_for_one_edit(browser, uid, True)
    off = _write_bodies_for_one_edit(browser, uid, False)
    assert on and on == off
    # An approved text carries ONE Weglot wording: the stamp it is approved against (`approvedAgainst`, CEL-026:
    # the export refuses a text whose Weglot wording moved meanwhile). The column adds nothing else to a write.
    (change,) = json.loads(on[0])
    assert change["record"].pop("approvedAgainst") == wording(uid)
    assert wording(uid) not in json.dumps(change), change


def _export_requests(browser, uids, with_column: bool) -> list:
    """What the page sends when the client presses Export for the open page and language: every storage write
    and the job start, in order, as the stand-in received them."""
    log = []

    def seed(e):
        for n, uid in enumerate(uids):
            draft(e.store, uid, f"Entwurf Nummer {n + 1}")
        raw = e.store.handle

        def spy(action, body, who):
            if action in ("desk-write", "desk-job-start"):
                log.append([action, body])
            return raw(action, body, who)

        e.store.handle = spy

    with doc(browser, seed=seed) as e:
        if with_column:
            show_weglot(e.page)
        e.page.locator("#doc-export").click()
        expect(e.page.locator("#ex-modal")).to_be_visible()
        e.page.locator("#ex-go").click()
        expect(e.page.locator(f'li.ex-file[data-page="{PAGE_KEY}"][data-lang="{LANG}"]')) \
            .to_have_attribute("data-state", "queued", timeout=10000)
    return log


def test_export_excludes_the_column_the_same_requests_with_it_on_and_off(browser):
    uids = pick(2, need_w=True)
    on = _export_requests(browser, uids, True)
    off = _export_requests(browser, uids, False)
    assert [a for a, _b in on].count("desk-job-start") == 1 and any(a == "desk-write" for a, _b in on)
    assert json.dumps(on, sort_keys=True) == json.dumps(off, sort_keys=True)
    # Weglot's wording appears in an export request only as the stamp each approval is given against
    # (`approvedAgainst`, CEL-026: the export refuses a text whose Weglot wording moved meanwhile); nowhere else
    stamps = [c["record"].pop("approvedAgainst") for a, b in on if a == "desk-write" for c in b["changes"]]
    assert sorted(stamps) == sorted(wording(u) for u in uids), stamps
    assert not any(wording(u) in json.dumps(on) for u in uids), "Weglot's wording travels beyond the stamp"


@pytest.mark.parametrize("width", [1280, 1440, 2560])
def test_three_columns_fit_without_a_sideways_scroll(browser, width):
    (uid,) = pick(1, need_w=True)
    with doc(browser, size=(width, 900)) as e:
        show_weglot(e.page)
        li = blk(e.page, uid)
        li.scroll_into_view_if_needed()
        cols = [li.locator(s).bounding_box() for s in (".doc-en", ".doc-tgt", ".doc-weglot")]
        assert all(cols), cols
        xs = [c["x"] for c in cols]
        assert xs == sorted(xs) and len(set(xs)) == 3, xs               # English | draft | Weglot, left to right
        assert all(c["width"] >= 220 for c in cols), [c["width"] for c in cols]
        assert cols[2]["x"] + cols[2]["width"] <= width, cols[2]
        assert e.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
