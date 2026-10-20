"""Robot click-tests for the shared-text marker of the document page (desk v2, CEL-072).

A text that is also on other pages used to print one or two sentences under the translation ("Also on ... A change here
changes it there too." / "Also used on N other pages (/path). Your wording becomes the wording there too."). They took a
row of their own, so the English and the translation drifted apart on a shared text. Now the sentence is a small marker
in the translation's right gutter, and nothing else in the row:

  * ONE marker per shared text (a button holding the number of other pages), none on a text that is not shared, and no
    sentence printed in the row;
  * hover AND keyboard focus show the full sentence as the desk's tooltip; the marker is reached by Tab and its
    accessible name is the sentence;
  * a click opens a popover that says the sentence again and lists the other pages BY PATH (the pages of the four in
    page order, then every page outside them); Esc, a second click on the marker, a click elsewhere and Tab out close
    it; focus goes back to the marker on Esc; only one popover is open at a time; a long list scrolls inside it;
  * when editing starts the full sentence shows ONCE, as the first line of the note row under the text (nothing is
    laid over the floating toolbar or the text above), and is gone at blur; an unshared text has none;
  * at rest nothing takes room: the note row stays 0 high, English and the translation start on the same line, the
    block, both columns and the next block do not move when the marker is hidden, the popover opens or closes, the
    marker sits in the gutter and never over the text, and the page does not scroll sideways, at 1280 / 1440 / 2560,
    Weglot column off and on; while editing only the note row under the editor grows, the editor and English never move.

Expected wording comes from COPY.md through `copy_text.t` / `tn`, never typed here. Every test also asserts the page
raised no error and logged none to the console, through `doc()`.

The harness helpers are COPIED from test_document_browser.py (the convention of this folder: no imports between test
files).
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
LANG = "de"
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
VARIANTS = ["outside-one", "outside-home", "outside-many", "also-only", "both"]
SD_PATH = "/san-diego-ca/san-diego"


# ── the harness, copied from test_document_browser.py ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk(save_on: bool = False, save_off: bool = False):
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
    data: dict
    pages: dict
    page: object = None
    errors: list = field(default_factory=list)


def _json(root: Path, name: str) -> dict:
    return json.loads((root / "admin" / "localization" / "document" / "data" / f"{name}.json")
                      .read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _stage_json(name: str) -> dict:
    path = H.REPO_DOCS / "admin" / "localization" / "document" / "data" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_data(name: str = PAGE_KEY) -> dict:
    return _stage_json(name)


@contextmanager
def doc(browser, *, size: tuple[int, int] = (1440, 900)):
    """The document page open and ready. On a normal exit it asserts no page error and no console error happened."""
    with desk(save_on=True) as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store, data=_json(root, PAGE_KEY),
                  pages=_json(root, "pages"))
        pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
        pg.set_default_timeout(10000)
        # The dashboard's BugHerd tag is a third party: answered with an empty script (CEL-067).
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            if msg.type != "error":
                return
            url = (msg.location or {}).get("url", "") or ""
            if url.endswith("/favicon.ico"):
                return
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


def tgt(page, uid):
    return blk(page, uid).locator(".doc-tgt")


def box(loc) -> dict:
    b = loc.bounding_box()
    assert b, "the element has no box on screen"
    return b


def on_top(loc) -> bool:
    """A click at the element's centre (and near its left edge) would hit it: nothing is painted over it."""
    loc.scroll_into_view_if_needed()
    return loc.evaluate("""el => [[0.5, 0.5], [0.05, 0.5]].every(([fx, fy]) => {
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy);
        return !!hit && (hit === el || el.contains(hit)); })""")


# ── what the marker says, built from COPY.md ─────────────────────────────────────────────────────────────
def shared_sentence(b: dict) -> str:
    """The sentence about the other pages of the four, then the one about the pages outside them, joined by a space."""
    parts = []
    if b.get("also"):
        parts.append(C.t("doc.also", pages=", ".join(C.t(f"page.{p}") for p in b["also"])))
    if b.get("out"):
        eg = C.t("row.shared.home") if b.get("outEg") == "/" else b.get("outEg", "")
        parts.append(C.tn("doc.shared", b["out"], example=eg))
    return " ".join(parts)


def mark_name(b: dict) -> str:
    """The marker's accessible name: the count its chip shows, in words (WCAG 2.5.3), then the sentence."""
    return C.tn("doc.mark", len(b.get("also", [])) + b.get("out", 0)) + " " + shared_sentence(b)


def listed_pages(env: Env, b: dict) -> list[str]:
    """The list the popover shows: the pages of the four (their paths from pages.json), then every page outside them."""
    path_of = {p["key"]: p["path"] for p in env.pages["pages"]}
    paths = [path_of[k] for k in b.get("also", [])] + list(b.get("outAll", []))
    return [C.t("row.shared.home") if p == "/" else p for p in paths]


def pick_block(variant: str) -> dict:
    ok = {
        "outside-one": lambda b: b.get("out") == 1 and not b.get("also") and b.get("outEg") != "/",
        "outside-home": lambda b: b.get("outEg") == "/" and not b.get("also"),
        "outside-many": lambda b: b.get("out", 0) > 1 and not b.get("also"),
        "also-only": lambda b: bool(b.get("also")) and not b.get("out"),
        "both": lambda b: bool(b.get("also")) and bool(b.get("out")),
    }[variant]
    found = [b for b in _stage_data()["blocks"] if b["lock"] == "" and b["b"] == "p" and ok(b)]
    if not found:
        pytest.skip(f"no editable paragraph on this page is of kind {variant!r}")
    return found[0]


def pick_plain_block() -> dict:
    found = [b for b in _stage_data()["blocks"]
             if b["lock"] == "" and b["b"] == "p" and not b.get("also") and not b.get("out")]
    assert found, "no unshared paragraph on this page"
    return found[0]


def other_block_uid(env: Env, not_uid: str) -> str:
    """Another shared, editable paragraph (the second marker of a test)."""
    for b in env.data["blocks"]:
        if b["id"] != not_uid and b["lock"] == "" and b["b"] == "p" and (b.get("also") or b.get("out")):
            return b["id"]
    raise AssertionError("no second shared paragraph")


GEO_JS = """el => {
    const r = n => { const b = n.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height, right: b.right, bottom: b.bottom}; };
    const q = s => el.querySelector(s);
    const mark = q('.doc-shared-mark');
    return {li: r(el), en: r(q('.doc-en')), tgt: r(q('.doc-tgt')), note: r(q('.doc-note')),
            mark: mark && getComputedStyle(mark.closest('.doc-shared')).display !== 'none' ? r(mark) : null,
            pad: parseFloat(getComputedStyle(q('.doc-tgt')).marginRight),
            next: el.nextElementSibling ? el.nextElementSibling.getBoundingClientRect().y : null};
}"""


def geo(li) -> dict:
    return li.evaluate(GEO_JS)


def same_rows(a: dict, b: dict, keys=("li", "en", "tgt", "note")):
    for k in keys:
        for f in ("x", "y", "w", "h"):
            assert abs(a[k][f] - b[k][f]) < 0.01, (k, f, a[k], b[k])
    assert abs((a["next"] or 0) - (b["next"] or 0)) < 0.01, ("next block", a["next"], b["next"])


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. the marker
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("variant", VARIANTS)
def test_a_shared_text_has_one_marker_that_counts_the_other_pages(browser, variant):
    b = pick_block(variant)
    n = len(b.get("also", [])) + b.get("out", 0)
    with doc(browser) as e:
        mark = blk(e.page, b["id"]).locator(".doc-shared-mark")
        expect(mark).to_have_count(1)
        expect(mark).to_have_text(str(n))
        expect(mark).to_have_attribute("aria-label", mark_name(b))
        expect(mark).to_have_attribute("data-tip", shared_sentence(b))
        assert str(n) in mark.get_attribute("aria-label"), "the visible count is not in the accessible name"
        assert mark.evaluate("el => el.tagName") == "BUTTON"
        assert mark.get_attribute("type") == "button"


def test_only_a_shared_text_has_a_marker_and_no_sentence_is_printed_in_a_row(browser):
    data = _stage_data()
    shared = {b["id"] for b in data["blocks"] if b.get("also") or b.get("out")}
    assert len(shared) > 50, "the page should carry many shared texts for this test to mean anything"
    with doc(browser) as e:
        have = e.page.eval_on_selector_all(".doc-shared-mark", "els => els.map(x => x.closest('li.doc-block').dataset.uid)")
        assert sorted(have) == sorted(shared), "a marker per shared text, none anywhere else, none twice"
        assert e.page.locator(".doc-note-also, .doc-note-shared").count() == 0, "the old note spans are still built"
        assert e.page.locator(".doc-shared-warn:visible").count() == 0, "a warning shows before any editing"
        assert e.page.locator(".doc-shared-pop").count() == 0, "a popover is open before any click"


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_sentence_about_other_pages_is_a_line_of_the_page(browser, variant):
    b = pick_block(variant)
    head_also = C.t("doc.also", pages="\0").split("\0")[0].strip()
    head_shared = C.tn("doc.shared", 1, example="\0").split("\0")[0].strip()
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        li.scroll_into_view_if_needed()
        shown = li.inner_text()
        assert head_also not in shown and head_shared not in shown, shown
        assert li.locator(".doc-note").evaluate("el => el.getBoundingClientRect().height") == 0, "the note row takes room"


def test_every_sentence_the_marker_says_is_still_a_line_of_copy_md():
    copy = C.load()
    for key in ("doc.also", "doc.shared.one", "doc.shared.other", "row.shared.home", "doc.mark.one", "doc.mark.other"):
        assert key in copy, key


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. tooltip on hover and on keyboard focus
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_hover_shows_the_full_sentence_as_the_desks_tooltip(browser):
    b = pick_block("both")
    with doc(browser) as e:
        mark = blk(e.page, b["id"]).locator(".doc-shared-mark")
        mark.scroll_into_view_if_needed()
        mark.hover()
        tip = e.page.locator(".desk-tip")
        expect(tip).to_be_visible()
        expect(tip).to_have_text(shared_sentence(b))
        e.page.mouse.move(2, 2)
        expect(tip).to_be_hidden()


def test_tab_reaches_the_marker_and_keyboard_focus_shows_the_same_tooltip(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        tgt(e.page, b["id"]).focus()
        for _ in range(12):
            e.page.keyboard.press("Tab")
            if e.page.evaluate("() => document.activeElement.classList.contains('doc-shared-mark')"):
                break
        else:
            raise AssertionError("Tab never reached the marker")
        assert e.page.evaluate("() => document.activeElement.closest('li.doc-block').dataset.uid") == b["id"]
        expect(li.get_by_role("button", name=mark_name(b), exact=True)).to_be_focused()
        tip = e.page.locator(".desk-tip")
        expect(tip).to_be_visible()
        expect(tip).to_have_text(shared_sentence(b))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. the popover
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("variant", VARIANTS)
def test_a_click_opens_a_popover_that_lists_the_other_pages_by_path(browser, variant):
    b = pick_block(variant)
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        mark = li.locator(".doc-shared-mark")
        mark.scroll_into_view_if_needed()
        mark.click()
        pop = li.locator(".doc-shared-pop")
        expect(pop).to_be_visible()
        expect(pop).to_have_attribute("role", "dialog")
        expect(pop).to_have_attribute("aria-label", shared_sentence(b))
        expect(mark).to_have_attribute("aria-expanded", "true")
        expect(pop.locator(".doc-shared-pop-text")).to_have_text(shared_sentence(b))
        assert pop.locator(".doc-shared-pop-list li").all_inner_texts() == listed_pages(e, b)
        assert len(listed_pages(e, b)) == len(b.get("also", [])) + b.get("out", 0)
        expect(pop).to_be_focused()
        assert on_top(pop), "the popover is painted under something"
        pb = box(pop)
        assert pb["x"] >= 0 and pb["x"] + pb["width"] <= e.page.evaluate("() => innerWidth") + 1, pb


def test_the_popover_names_a_page_outside_the_four_by_its_path(browser):
    data = _stage_data()
    b = next((x for x in data["blocks"] if x["lock"] == "" and x["b"] == "p" and SD_PATH in x.get("outAll", [])), None)
    if b is None:
        pytest.skip(f"no editable paragraph on this page is also on {SD_PATH}")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        li.locator(".doc-shared-mark").click()
        assert SD_PATH in li.locator(".doc-shared-pop-list li").all_inner_texts()


def test_a_long_list_scrolls_inside_the_popover_and_lists_every_page(browser):
    data = _stage_data()
    b = max((x for x in data["blocks"] if x["lock"] == "" and x["b"] == "p" and x.get("outAll")),
            key=lambda x: len(x["outAll"]))
    assert len(b["outAll"]) >= 20, "this page has no text on 20 or more outside pages"
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        li.locator(".doc-shared-mark").click()
        pop = li.locator(".doc-shared-pop")
        expect(pop).to_be_visible()
        assert pop.locator(".doc-shared-pop-list li").all_inner_texts() == listed_pages(e, b)
        assert pop.evaluate("el => el.scrollHeight > el.clientHeight"), "a long list should scroll"
        assert box(pop)["height"] <= 262, box(pop)


def test_the_popover_is_on_top_with_the_weglot_column_on(browser):
    b = pick_block("both")
    with doc(browser) as e:
        e.page.locator("#doc-weglot").check()
        li = blk(e.page, b["id"])
        li.locator(".doc-shared-mark").click()
        pop = li.locator(".doc-shared-pop")
        expect(pop).to_be_visible()
        assert on_top(pop)


def test_escape_closes_the_popover_and_the_focus_goes_back_to_the_marker(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        mark = li.locator(".doc-shared-mark")
        mark.click()
        expect(li.locator(".doc-shared-pop")).to_be_visible()
        e.page.keyboard.press("Escape")
        expect(li.locator(".doc-shared-pop")).to_have_count(0)
        expect(mark).to_have_attribute("aria-expanded", "false")
        expect(mark).to_be_focused()


def test_a_second_click_on_the_marker_closes_the_popover(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        mark = li.locator(".doc-shared-mark")
        mark.click()
        expect(li.locator(".doc-shared-pop")).to_be_visible()
        mark.click()
        expect(li.locator(".doc-shared-pop")).to_have_count(0)
        expect(mark).to_have_attribute("aria-expanded", "false")


def test_a_click_elsewhere_closes_it_and_only_one_popover_is_open_at_a_time(browser):
    b = pick_block("both")
    with doc(browser) as e:
        first = blk(e.page, b["id"])
        first.locator(".doc-shared-mark").click()
        expect(first.locator(".doc-shared-pop")).to_be_visible()
        other = other_block_uid(e, b["id"])
        second = blk(e.page, other)
        second.locator(".doc-shared-mark").click()
        expect(e.page.locator(".doc-shared-pop")).to_have_count(1)
        expect(second.locator(".doc-shared-pop")).to_be_visible()
        expect(first.locator(".doc-shared-mark")).to_have_attribute("aria-expanded", "false")
        # a click on a text elsewhere closes the one that is open
        blk(e.page, b["id"]).locator(".doc-en").click()
        expect(e.page.locator(".doc-shared-pop")).to_have_count(0)
        expect(second.locator(".doc-shared-mark")).to_have_attribute("aria-expanded", "false")


def test_clicking_inside_the_popover_does_not_close_it_and_tabbing_out_does(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        li.locator(".doc-shared-mark").click()
        pop = li.locator(".doc-shared-pop")
        expect(pop).to_be_visible()
        pop.locator(".doc-shared-pop-text").click()
        expect(pop).to_be_visible()
        e.page.keyboard.press("Tab")
        expect(e.page.locator(".doc-shared-pop")).to_have_count(0)


def test_opening_the_popover_does_not_start_editing_or_save_anything(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        li.locator(".doc-shared-mark").click()
        e.page.keyboard.press("Escape")
        assert not e.store.decisions, "a marker click wrote a decision"
        assert li.get_attribute("data-open") is None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. the full sentence once, in the note row, while the text has focus
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("variant", ["outside-one", "also-only", "both"])
def test_the_full_sentence_shows_once_under_the_text_while_it_has_focus(browser, variant):
    b = pick_block(variant)
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        warn = li.locator(".doc-shared-warn")
        expect(warn).to_be_hidden()
        assert li.locator(".doc-note").evaluate("el => el.getBoundingClientRect().height") == 0
        tgt(e.page, b["id"]).click()
        expect(warn).to_be_visible()
        expect(warn).to_have_text(shared_sentence(b))
        assert e.page.locator(".doc-shared-warn:visible").count() == 1, "the sentence should show once"
        wb, tb = box(warn), box(tgt(e.page, b["id"]))
        assert wb["y"] >= tb["y"] + tb["height"] - 0.5, ("the sentence is not under the text", wb, tb)
        assert wb["x"] >= tb["x"] - 0.5 and wb["x"] + wb["width"] <= tb["x"] + tb["width"] + 0.5, (wb, tb)
        # it is a line of the page, so it lies over neither the floating toolbar nor the block above
        tools = box(li.locator(".doc-tools"))
        assert wb["y"] >= tools["y"] + tools["height"] or wb["x"] + wb["width"] <= tools["x"] or wb["x"] >= tools["x"] + tools["width"], (wb, tools)
        above = li.evaluate("el => el.previousElementSibling.getBoundingClientRect().bottom")
        assert wb["y"] >= above - 0.5, (wb, above)
        # leaving the text takes it away again, and the note row is empty again
        e.page.evaluate("() => document.activeElement.blur()")
        expect(warn).to_be_hidden()
        assert li.locator(".doc-note").evaluate("el => el.getBoundingClientRect().height") == 0


def test_a_text_that_is_not_shared_has_no_warning_and_no_marker(browser):
    b = pick_plain_block()
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        tgt(e.page, b["id"]).click()
        expect(li.locator(".doc-shared-warn")).to_have_count(0)
        expect(li.locator(".doc-shared-mark")).to_have_count(0)
        assert e.page.locator(".doc-shared-warn:visible").count() == 0


def test_moving_from_the_text_to_the_marker_takes_the_warning_away(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        tgt(e.page, b["id"]).click()
        expect(li.locator(".doc-shared-warn")).to_be_visible()
        li.locator(".doc-shared-mark").click()
        expect(li.locator(".doc-shared-warn")).to_be_hidden()
        expect(li.locator(".doc-shared-pop")).to_be_visible()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. at rest none of it takes room (desktop 1280 / 1440 / 2560, Weglot column off and on)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("weglot", [False, True], ids=["weglot-off", "weglot-on"])
@pytest.mark.parametrize("width", [1280, 1440, 2560])
@pytest.mark.parametrize("variant", ["outside-many", "both"])
def test_the_marker_takes_no_room_and_the_columns_line_up(browser, width, weglot, variant):
    b = pick_block(variant)
    with doc(browser, size=(width, 1000)) as e:
        if weglot:
            e.page.locator("#doc-weglot").check()
        li = blk(e.page, b["id"])
        li.scroll_into_view_if_needed()
        g = geo(li)
        m = g["mark"]
        assert m, "the marker has no box"
        # no sentence row: the note under the translation is 0 high, and English and the translation start on one line
        assert g["note"]["h"] == 0, g["note"]
        assert abs(g["en"]["y"] - g["tgt"]["y"]) < 0.5, (g["en"], g["tgt"])
        # the marker is in the translation's right gutter: past the text box, inside the column, inside the block
        assert m["x"] >= g["tgt"]["right"] - 0.5, ("the marker is over the text", m, g["tgt"])
        assert m["right"] <= g["tgt"]["right"] + g["pad"] + 0.5, ("the marker leaves its column", m, g["tgt"], g["pad"])
        assert m["y"] >= g["li"]["y"] - 0.5 and m["bottom"] <= g["li"]["bottom"] + 0.5, (m, g["li"])
        assert m["x"] > g["en"]["right"], "the marker is in the English column"
        # taking the marker away moves nothing: the block, both columns, the note row and the next block stay put
        li.locator(".doc-shared").evaluate("el => { el.style.display = 'none'; }")
        bare = geo(li)
        assert bare["mark"] is None
        same_rows(g, bare)
        li.locator(".doc-shared").evaluate("el => { el.style.display = ''; }")
        assert e.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), "the page scrolls sideways"


@pytest.mark.parametrize("weglot", [False, True], ids=["weglot-off", "weglot-on"])
@pytest.mark.parametrize("width", [1280, 1440, 2560])
def test_opening_and_closing_the_popover_moves_nothing(browser, width, weglot):
    b = pick_block("both")
    with doc(browser, size=(width, 1000)) as e:
        if weglot:
            e.page.locator("#doc-weglot").check()
        li = blk(e.page, b["id"])
        li.scroll_into_view_if_needed()
        before = geo(li)
        li.locator(".doc-shared-mark").click()
        expect(li.locator(".doc-shared-pop")).to_be_visible()
        same_rows(before, geo(li))
        e.page.keyboard.press("Escape")
        expect(li.locator(".doc-shared-pop")).to_have_count(0)
        same_rows(before, geo(li))
        assert e.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("weglot", [False, True], ids=["weglot-off", "weglot-on"])
@pytest.mark.parametrize("width", [1280, 1440, 2560])
def test_while_editing_only_the_note_row_under_the_editor_grows(browser, width, weglot):
    b = pick_block("both")
    with doc(browser, size=(width, 1000)) as e:
        if weglot:
            e.page.locator("#doc-weglot").check()
        li = blk(e.page, b["id"])
        li.scroll_into_view_if_needed()
        before = geo(li)
        tgt(e.page, b["id"]).click()
        expect(li.locator(".doc-shared-warn")).to_be_visible()
        during = geo(li)
        # the editor and English do not move, the block's top does not move, the note row is now the sentence's height
        for k in ("en", "tgt"):
            for f in ("x", "y", "w", "h"):
                assert abs(before[k][f] - during[k][f]) < 0.01, (k, f, before[k], during[k])
        assert abs(before["li"]["y"] - during["li"]["y"]) < 0.01
        assert during["note"]["h"] > 0
        assert abs((during["li"]["h"] - before["li"]["h"]) - during["note"]["h"]) < 1.5, (before["li"], during["li"], during["note"])
        assert during["tgt"]["y"] == pytest.approx(during["en"]["y"], abs=0.5)
        # at blur the block is exactly as it was
        e.page.evaluate("() => document.activeElement.blur()")
        expect(li.locator(".doc-shared-warn")).to_be_hidden()
        same_rows(before, geo(li))


def test_the_two_columns_of_a_shared_text_and_an_unshared_one_are_built_the_same_way(browser):
    """What the operator asked for: a shared row is no taller than its text needs, like any other row."""
    s, p = pick_block("both"), pick_plain_block()
    with doc(browser) as e:
        for uid in (s["id"], p["id"]):
            li = blk(e.page, uid)
            li.scroll_into_view_if_needed()
            g = geo(li)
            assert abs(g["en"]["y"] - g["tgt"]["y"]) < 0.5
            assert g["note"]["h"] == 0
            # the row is exactly the taller of its two texts plus their margins: nothing else sits in it
            tallest = max(g["en"]["h"], g["tgt"]["h"])
            assert g["li"]["h"] - tallest < 60, (uid, g["li"], tallest)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. the popover with other things open, and near the bottom edge
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_one_escape_closes_only_the_popover_when_the_history_panel_is_open(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        tgt(e.page, b["id"]).click()
        li.locator(".doc-history-btn").click()
        expect(e.page.locator("#doc-history")).to_be_visible()
        li.locator(".doc-shared-mark").click()
        expect(li.locator(".doc-shared-pop")).to_be_visible()
        e.page.keyboard.press("Escape")
        expect(li.locator(".doc-shared-pop")).to_have_count(0)
        expect(e.page.locator("#doc-history")).to_be_visible()          # the panel waits for its own Escape
        expect(li.locator(".doc-shared-mark")).to_be_focused()
        e.page.keyboard.press("Escape")
        expect(e.page.locator("#doc-history")).to_be_hidden()


def test_the_tooltip_is_not_left_over_the_popover(browser):
    b = pick_block("both")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        mark = li.locator(".doc-shared-mark")
        mark.scroll_into_view_if_needed()
        mark.hover()
        tip = e.page.locator(".desk-tip")
        expect(tip).to_be_visible()
        mark.click()
        expect(li.locator(".doc-shared-pop")).to_be_visible()
        expect(tip).to_be_hidden()
        e.page.wait_for_timeout(400)                                      # and it does not come back by itself
        expect(tip).to_be_hidden()


@pytest.mark.parametrize("width", [1280, 1440])
def test_the_longest_list_stays_inside_the_window_even_next_to_the_bottom_edge(browser, width):
    data = _stage_data()
    b = max((x for x in data["blocks"] if x["lock"] == "" and x["b"] == "p" and x.get("outAll")),
            key=lambda x: len(x["outAll"]))
    assert len(b["outAll"]) >= 20
    with doc(browser, size=(width, 720)) as e:
        li = blk(e.page, b["id"])
        mark = li.locator(".doc-shared-mark")
        mark.scroll_into_view_if_needed()
        # put the marker a hand above the status bar, where there is no room below it for 260 px
        floor = box(e.page.locator("#doc-status"))["y"]
        e.page.evaluate("dy => window.scrollBy(0, dy)", box(mark)["y"] - (floor - 60))
        mark.click()
        pop = li.locator(".doc-shared-pop")
        expect(pop).to_be_visible()
        pb = box(pop)
        assert pb["y"] >= 0 and pb["y"] + pb["height"] <= floor + 0.5, ("the popover runs under the status bar", pb, floor)
        assert pb["x"] >= 0 and pb["x"] + pb["width"] <= width + 1, pb
        assert on_top(pop)
        assert e.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), "the page scrolls sideways"
        assert "doc-shared-pop-up" in pop.get_attribute("class"), "it should have opened upward"
