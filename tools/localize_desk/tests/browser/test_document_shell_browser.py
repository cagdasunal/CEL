"""Robot click-tests for the Option B shell of the document desk (CEL-069; CEL-068 shell-spec.md §3-§8): the page
tree (filter by path or name, arrows / Enter / Esc, `/` and Cmd/Ctrl+K), the language tabs (Alt+1..8 that never
take a typed character), the path row, and the rules page's tabs and desk link.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text`, never typed
here. The harness helpers are COPIED from test_document_states_browser.py (the convention of this folder: no
imports between test files). Desktop only (Ruling 23:48): 1024-2560.
"""
from __future__ import annotations

import json
import re
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


def last_prevented(page, code):
    rows = [p for c, p in page.evaluate("window.__dp") if c == code]
    assert rows, f"no keydown {code} reached the page"
    return rows[-1]


def rows(page):
    return page.eval_on_selector_all(".doc-tree-page", "els => els.map(r => r.dataset.page)")


def into_draft(page):
    """The caret in the first draft field (contenteditable `.doc-tgt.rf-field`)."""
    field_ = page.locator("li.doc-block .doc-tgt.rf-field").first
    field_.click()
    page.wait_for_function("() => !!document.activeElement.closest('[contenteditable]')")


# ── the tree ───────────────────────────────────────────────────────────────────────────────────────
def test_the_filter_matches_the_path_and_the_name_and_says_when_nothing_matches(browser):
    with doc(browser) as e:
        p = e.page
        f = p.locator("#doc-tree-filter")
        expect(f).to_have_attribute("placeholder", C.t("nav.tree.filter"))
        f.fill("vs-toronto")                                          # by path
        assert rows(p) == ["vs-toronto"]
        f.fill("how long")                                            # by name, every word must match
        assert rows(p) == ["how-long-to-learn-english"]
        f.fill("vancouver cost")                                      # a word of the path and a word of the name
        assert rows(p) == ["cost-of-studying-english"]
        f.fill("zzz nothing")
        assert rows(p) == []
        expect(p.locator("#doc-tree-none")).to_have_text(C.t("nav.tree.none", q="zzz nothing"))
        f.fill("")
        assert rows(p) == ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]
        expect(p.locator("#doc-tree-none")).to_be_hidden()


def test_arrows_and_enter_open_the_highlighted_page_and_keep_the_language(browser):
    with doc(browser, lang="fr") as e:
        p = e.page
        p.locator("#doc-tree-filter").click()
        p.keyboard.type("vancouver")
        p.keyboard.press("ArrowDown")                                 # the second visible row
        expect(p.locator(".doc-tree-page.is-kb")).to_have_count(1)
        target = p.locator(".doc-tree-page.is-kb").get_attribute("data-page")
        p.keyboard.press("Enter")
        wait_open(p, target, "fr")
        assert now(p) == [target, "fr", target, "fr"]
        expect(p.locator("#doc-tree-filter")).to_have_value("")


def test_esc_clears_the_filter_and_leaves_it(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-tree-filter").fill("toronto")
        p.locator("#doc-tree-filter").press("Escape")
        expect(p.locator("#doc-tree-filter")).to_have_value("")
        assert p.evaluate("document.activeElement.id") != "doc-tree-filter"
        assert len(rows(p)) == 4


def test_a_row_click_keeps_the_language_and_a_tab_click_keeps_the_page(browser):
    with doc(browser) as e:
        p = e.page
        p.locator('.doc-tree-page[data-page="vancouver"]').click()
        wait_open(p, "vancouver", "de")
        p.locator("#doc-tab-it").click()
        wait_open(p, "vancouver", "it")
        assert now(p) == ["vancouver", "it", "vancouver", "it"]
        expect(p.locator("#doc-rules")).to_have_attribute("href", "/admin/localization/rules/?lang=it")
        # the open page's sections sit under its row in the tree
        expect(p.locator('.doc-tree-page[aria-current="page"] + #doc-outline')).to_be_visible()
        assert p.locator("#doc-outline-list .doc-outline-item").count() > 0


def test_a_folder_folds_and_stays_folded(browser):
    with doc(browser) as e:
        p = e.page
        fold = p.locator(".doc-tree-fold").first
        fold.click()
        expect(fold).to_have_attribute("aria-expanded", "false")
        assert rows(p) == []
        p.reload()
        p.wait_for_selector(READY, timeout=20000)
        expect(p.locator(".doc-tree-fold").first).to_have_attribute("aria-expanded", "false")
        p.locator(".doc-tree-fold").first.click()
        assert len(rows(p)) == 4


# ── the keys ───────────────────────────────────────────────────────────────────────────────────────
def test_alt_digit_outside_a_text_switches_the_language_keeps_the_page_and_takes_the_key(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-tab-de").focus()
        p.keyboard.press("Alt+Digit2")
        wait_open(p, PAGE_KEY, "fr")
        assert last_prevented(p, "Digit2") is True
        assert now(p) == [PAGE_KEY, "fr", PAGE_KEY, "fr"]
        p.locator("body").click(position={"x": 5, "y": 5})
        p.keyboard.press("Alt+Digit8")
        wait_open(p, PAGE_KEY, "ar")


def test_alt_digit_in_a_draft_types_its_character_and_leaves_the_tab(browser):
    """Option+1 is "¡" on a Mac; AltGr arrives as Ctrl+Alt (AltGr+2 = "@"): neither is taken from the text."""
    with doc(browser) as e:
        p = e.page
        into_draft(p)
        p.keyboard.press("Alt+Digit1")
        assert last_prevented(p, "Digit1") is False
        p.keyboard.press("Control+Alt+Digit2")
        assert last_prevented(p, "Digit2") is False
        assert now(p)[1] == "de"


def test_alt_digit_with_cmd_or_ctrl_held_does_nothing(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-tab-de").focus()
        p.keyboard.press("Control+Alt+Digit3")                       # AltGr outside a text: still not a switch
        assert last_prevented(p, "Digit3") is False
        p.keyboard.press("Meta+Alt+Digit3")
        assert last_prevented(p, "Digit3") is False
        assert now(p)[1] == "de"


def test_slash_opens_the_filter_but_not_from_inside_a_text(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-tab-de").focus()
        p.keyboard.press("/")
        assert p.evaluate("document.activeElement.id") == "doc-tree-filter"
        expect(p.locator("#doc-tree-filter")).to_have_value("")
        into_draft(p)
        p.keyboard.press("/")
        assert p.evaluate("document.activeElement.id") != "doc-tree-filter"
        assert last_prevented(p, "Slash") is False


def test_cmd_k_on_a_mac_ctrl_k_elsewhere_opens_the_filter_and_ctrl_k_on_a_mac_is_left_to_the_text(browser):
    with doc(browser) as e:
        p = e.page
        mac = p.evaluate("/Mac|iPhone|iPad/.test(navigator.platform || '')")
        into_draft(p)
        p.keyboard.press("Meta+KeyK" if mac else "Control+KeyK")
        assert p.evaluate("document.activeElement.id") == "doc-tree-filter"
        assert last_prevented(p, "KeyK") is True
        if mac:
            into_draft(p)
            p.keyboard.press("Control+KeyK")                          # "delete to end of line": the text's
            assert last_prevented(p, "KeyK") is False
            assert p.evaluate("document.activeElement.id") != "doc-tree-filter"


# ── the path row ───────────────────────────────────────────────────────────────────────────────────
def test_the_website_text_switch_keeps_its_storage_key(browser):
    with doc(browser) as e:
        p = e.page
        p.locator("label.doc-switch").click()
        expect(p.locator("#doc-weglot")).to_be_checked()
        assert p.evaluate("localStorage.getItem('cel-doc-weglot')") == "true"
        expect(p.locator("#doc-blocks")).to_have_attribute("data-weglot", "on")


@pytest.mark.parametrize("width", [1024, 1280, 1440, 1920, 2560])
def test_no_sideways_scroll_and_the_path_is_never_cut_at_any_desktop_width(browser, width):
    with doc(browser, key="how-long-to-learn-english", width=width) as e:
        p = e.page
        assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        assert p.evaluate("(() => { const s = document.querySelector('.doc-path'); return s.scrollWidth <= s.clientWidth + 1; })()"), width
        bar = p.locator("#doc-bar").bounding_box()
        assert abs(bar["height"] - 52) <= 1, bar
        tabs = p.locator("#doc-tabs").bounding_box()
        assert abs(tabs["height"] - 38) <= 1, tabs
        # every action is inside the row, none clipped
        for sel in ("label.doc-switch", "#doc-rules", "#doc-export"):
            box = p.locator(sel).bounding_box()
            assert box and box["x"] + box["width"] <= bar["x"] + bar["width"] + 1, (sel, box, bar)
        expect(p.locator(".doc-tabs-hint")).to_be_visible() if width >= 1280 else expect(p.locator(".doc-tabs-hint")).to_be_hidden()


# ── the rules page ─────────────────────────────────────────────────────────────────────────────────
def test_the_rules_page_takes_alt_digit_and_its_desk_link_carries_the_language(browser):
    with doc(browser, path="rules") as e:
        p = e.page
        expect(p.locator("#rules-desk")).to_have_attribute("href", "/admin/localization/document/?lang=de")
        p.keyboard.press("Alt+Digit3")
        expect(p.locator("#rulesTab-es")).to_have_attribute("aria-selected", "true")
        assert last_prevented(p, "Digit3") is True
        expect(p.locator("#rules-desk")).to_have_attribute("href", "/admin/localization/document/?lang=es")
        p.keyboard.press("Control+Alt+Digit4")                       # AltGr: not a switch
        assert last_prevented(p, "Digit4") is False
        expect(p.locator("#rulesTab-es")).to_have_attribute("aria-selected", "true")
