"""Robot click-tests for the document desk's language tabs (CEL-106): each tab shows the language's flag, the status
dot became a small badge on the flag's corner.

The operator asked for flags instead of the blue dots (Ruling 19:3x): a tab used to start with a status dot (queued,
translating, drafted, edited, exported, failed, unknown); the same dot, in the same colours, now sits on the corner of
the tab's flag, so no information is lost. The flag is the one `desk_shared.LOCALES` holds and the Export grid prints.
The status word stays in the tab's accessible name and its hover text (the desk's tooltip, `data-tip`: no native
`title`, test_desk_style).

The harness helpers are COPIED from test_document_shared_note_browser.py (the convention of this folder: no imports
between test files). Desktop only (ruling 2026-10-19 23:48). Every test asserts the page raised no error.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright lives in the monorepo's .venv314; the CEL hook and the "
                           "browser CI job run this file with it")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from localize_desk import desk_shared as S  # noqa: E402
from localize_desk import harness as H  # noqa: E402

PAGE_KEY = "cost-of-studying-english"
LANG = "de"
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
STATES = ("queued", "translating", "drafted", "edited", "exported", "failed", "unknown")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk():
    root = H.stage_copy(save_on=True)
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
    page: object = None
    errors: list = field(default_factory=list)


@contextmanager
def doc(browser, *, size: tuple[int, int] = (1440, 900)):
    """The document page open and ready. On a normal exit it asserts no page error and no console error happened."""
    with desk() as (base, _root, _worker):
        env = Env()
        pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
        pg.set_default_timeout(10000)
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


def box(loc) -> dict:
    b = loc.bounding_box()
    assert b, "the element has no box on screen"
    return b


# ── 1. a flag first, then the name ───────────────────────────────────────────────────────────────────────
def test_each_tab_starts_with_its_flag_and_then_its_name(browser):
    with doc(browser) as e:
        p = e.page
        expect(p.locator(".doc-tab")).to_have_count(len(S.LOCALES))
        for code, _endonym, _dir, flag in S.LOCALES:
            tab = p.locator(f"#doc-tab-{code}")
            flagbox = tab.locator(".doc-tab-flag")
            expect(flagbox).to_have_count(1)
            assert flagbox.evaluate("el => el.firstChild.textContent") == flag, code
            expect(flagbox).to_have_attribute("aria-hidden", "true")
            assert tab.evaluate("el => el.firstElementChild.className") == "doc-tab-flag", code      # flag before the name
            expect(tab.locator(".doc-tab-name")).to_have_text(S.lang_name(code))
            assert box(flagbox)["x"] < box(tab.locator(".doc-tab-name"))["x"], code


def test_a_tabs_accessible_name_still_holds_its_language_and_its_status(browser):
    with doc(browser) as e:
        p = e.page
        for code, *_ in S.LOCALES:
            tab = p.locator(f"#doc-tab-{code}")
            word = tab.locator(".doc-st-word").inner_text()
            assert word, code                                              # the status is still said in words
            expect(p.get_by_role("tab", name=re.compile(rf"^{S.lang_name(code)}\b"))).to_have_count(1)
            expect(tab.locator(".doc-tab-flag")).to_have_attribute("aria-hidden", "true")


# ── 2. the status is a badge on the flag's corner ────────────────────────────────────────────────────────
def test_the_status_dot_is_one_small_badge_on_the_flags_corner_inside_the_tab(browser):
    with doc(browser) as e:
        p = e.page
        expect(p.locator(".doc-tab .doc-st")).to_have_count(len(S.LOCALES))
        for code, *_ in S.LOCALES:
            tab = p.locator(f"#doc-tab-{code}")
            badge = tab.locator(".doc-tab-flag > .doc-st")
            expect(badge).to_have_count(1)
            expect(badge).to_have_attribute("aria-hidden", "true")
            f, b, t = box(tab.locator(".doc-tab-flag")), box(badge), box(tab)
            cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            assert abs(cx - (f["x"] + f["width"])) <= 6 and abs(cy - (f["y"] + f["height"])) <= 6, (code, f, b)   # the corner
            assert (cx - (f["x"] + f["width"] / 2)) > 3 and (cy - (f["y"] + f["height"] / 2)) > 3, (code, f, b)   # not mid-flag
            assert b["width"] <= 10 and b["height"] <= 10, (code, b)                                              # small
            assert t["x"] <= b["x"] and b["x"] + b["width"] <= t["x"] + t["width"], (code, t, b)                   # inside the tab
            assert t["y"] <= b["y"] and b["y"] + b["height"] <= t["y"] + t["height"], (code, t, b)


def test_the_badge_keeps_the_status_colours_of_the_dot(browser):
    """The tab's badge and the page tree's dot are the same `.doc-st` rules: for every state they draw the same border
    and, where the state fills the dot, the same fill (an unfilled state shows the tab's page colour inside). Set and
    read in one synchronous call: the runtime repaints a status in between otherwise."""
    read = """states => {
        const badge = document.querySelector('#doc-tab-fr .doc-st'), dot = document.querySelector('.doc-tree-page .doc-st');
        const look = el => { const s = getComputedStyle(el);
            return [s.borderTopColor, s.borderTopStyle, s.backgroundColor, s.backgroundImage]; };
        return Object.fromEntries(states.map(st => {
            badge.setAttribute('data-s', st); dot.setAttribute('data-s', st);
            return [st, {tab: look(badge), dot: look(dot)}]; })); }"""
    with doc(browser) as e:
        got = e.page.evaluate(read, list(STATES))
        for state in STATES:
            tab_style, dot_style = got[state]["tab"], got[state]["dot"]
            assert tab_style[:2] == dot_style[:2], (state, tab_style, dot_style)
            if state in ("translating", "drafted", "exported"):
                assert tab_style[2] == dot_style[2] != "rgba(0, 0, 0, 0)", (state, tab_style, dot_style)
            if state == "edited":
                assert tab_style[3] == dot_style[3] and "gradient" in tab_style[3], (state, tab_style)
            if state in ("queued", "failed", "unknown"):
                assert tab_style[2] != "rgba(0, 0, 0, 0)", (state, tab_style)         # opaque: the flag does not show through
        assert len({tuple(got[st]["tab"][:3]) for st in STATES}) == len(STATES), "two states look the same"


def test_a_state_change_reaches_the_badge_the_way_it_reached_the_dot(browser):
    with doc(browser) as e:
        p = e.page
        for code, *_ in S.LOCALES:
            tab = p.locator(f"#doc-tab-{code}")
            status = tab.get_attribute("data-status")
            assert status and status != "unknown", (code, status)                  # painted by the runtime, as before
            assert tab.locator(".doc-st").get_attribute("data-s") == status, code


# ── 3. what the dot's hover said is still said ───────────────────────────────────────────────────────────
def test_hovering_the_flag_shows_the_desks_tooltip_with_the_status_word(browser):
    with doc(browser) as e:
        p = e.page
        tab = p.locator("#doc-tab-fr")
        tip_text = tab.get_attribute("data-tip")
        assert tip_text and tab.locator(".doc-st-word").inner_text() in tip_text
        tab.locator(".doc-tab-flag").hover()
        tip = p.locator(".desk-tip")
        expect(tip).to_be_visible()
        expect(tip).to_have_text(tip_text)


def test_no_tab_carries_a_native_title(browser):
    with doc(browser) as e:
        assert e.page.locator("#doc-tabs [title]").count() == 0


def test_the_tabs_still_switch_the_language_by_click_and_by_key(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-tab-fr").click()
        expect(p.locator("#doc-tab-fr")).to_have_attribute("aria-selected", "true")
        p.keyboard.press("Alt+3")
        expect(p.locator("#doc-tab-es")).to_have_attribute("aria-selected", "true", timeout=5000)
        assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
