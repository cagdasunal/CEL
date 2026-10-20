"""Robot click-tests for the document view's colour and type (CEL-070): /admin/localization/document/.

The designer's spec (CEL-068 doc-spec.md) is painted onto the page the client already likes: the two columns stay,
the colours and the type change. What these tests hold: the computed colours and sizes the spec names, at 1280,
1440 and 1920; every text pair of the page really rendered at 4.5:1 or more; an edited text's ochre bar and its word;
a flagged text carries `data-flagged` and the brick mark. The unit side (tokens, contrast of the token pairs, no
white, no near-white, weights 400 and 500) is in test_generate_document_page.py.

A real Chromium drives the page in the click-test harness (a temporary copy of docs/, the storage's stand-in behind
a mock Worker). Expected wording comes from COPY.md through `copy_text`. The helpers are copied from
test_document_states_browser.py (the convention of this folder: no imports between test files). Desktop only.
"""

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
        http_errors: bool = False, width: int = 1440):
    """The document page open and ready; asserts no page error and no console error on a normal exit."""
    with desk() as (base, root, worker):
        env = Env(base=base, root=root, worker=worker, store=worker.store)
        if seed:
            seed(env)
        pg = browser.new_page(viewport={"width": width, "height": 900})
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


# ── helpers for this file ─────────────────────────────────────────────────────────────────────────
def rgb(value: str) -> tuple[int, int, int]:
    nums = re.findall(r"[\d.]+", value)[:3]
    assert len(nums) == 3, value
    return tuple(int(float(n)) for n in nums)


def lum(c) -> float:
    ch = [v / 255 for v in c]
    ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a, b) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def css(page, selector: str, prop: str, pseudo: str | None = None) -> str:
    return page.evaluate("([s, p, ps]) => getComputedStyle(document.querySelector(s), ps)[p]", [selector, prop, pseudo])


def first_block(kind: str) -> str:
    return next(b["id"] for b in _stage_data()["blocks"] if b["b"] == kind and not b["lock"])


def weglot_ids(n: int) -> list[str]:
    out = [b["id"] for b in _stage_data()["blocks"]
           if not b["lock"] and b["b"] in ("p", "li") and b.get("w", {}).get(LANG) and not b.get("also") and not b.get("out")
           and not MARK.search(b["en"]) and 12 <= len(b["en"]) <= 400][:n]
    assert len(out) == n, "the page data has too few texts with a Weglot wording for this test"
    return out


SHEET, TRAY, HOVER, WEGLOT_BG = (241, 234, 216), (231, 222, 199), (236, 228, 207), (234, 226, 204)
INK, INK_SRC, MUTED = (43, 39, 34), (71, 66, 58), (100, 93, 81)
EDITED, EDITED_INK, FLAG, FLAG_BG = (168, 95, 10), (138, 77, 7), (163, 54, 31), (237, 220, 198)
ERR = (160, 38, 36)                                             # the dashboard's --err #A02624


# ── 1. surfaces, ink and type, at the three desktop widths ────────────────────────────────────────
@pytest.mark.parametrize("width", [1280, 1440, 1920])
def test_the_document_view_paints_the_spec_surfaces_ink_and_type(browser, width):
    (body,) = plain_ids(1)
    h1 = first_block("h1")
    with doc(browser, width=width, seed=lambda e: draft(e.store, body, "Entwurf")) as e:
        p = e.page
        li = f'li.doc-block[data-uid="{body}"]'
        assert rgb(css(p, ".doc-sheets", "backgroundColor")) == TRAY
        assert rgb(css(p, ".doc-head", "backgroundColor")) == SHEET
        assert rgb(css(p, li, "backgroundColor", "::before")) == SHEET            # the English sheet
        assert rgb(css(p, li, "backgroundColor", "::after")) == SHEET             # the translation sheet
        assert rgb(css(p, ".doc-status", "backgroundColor")) == SHEET
        assert rgb(css(p, f"{li} .doc-en", "color")) == INK_SRC                   # English: the reference, one step back
        assert rgb(css(p, f"{li} .doc-tgt", "color")) == INK                      # the translation: the text being worked on
        assert css(p, f"{li} .doc-en", "fontSize") == "16px" and css(p, f"{li} .doc-en", "lineHeight") == "26.4px"
        assert css(p, ".doc-head", "fontSize") == "13px" and css(p, ".doc-head", "fontWeight") == "500"
        head = f'li.doc-block[data-uid="{h1}"] .doc-en'
        assert css(p, head, "fontSize") == "28px" and css(p, head, "fontWeight") == "500"
        assert css(p, f"{li} .doc-note", "fontSize") == "12px"
        # no white and no near-white anywhere on the sheets, the tray or the bars
        for sel, pseudo in ((".doc-sheets", None), (".doc-head", None), (".doc-status", None),
                            (li, "::before"), (li, "::after")):
            assert lum(rgb(css(p, sel, "backgroundColor", pseudo))) < 0.86, (sel, pseudo)


def test_the_weglot_column_is_a_step_apart_from_the_sheets(browser):
    (u,) = weglot_ids(1)
    with doc(browser) as e:
        p = e.page
        p.locator("#doc-weglot").check()
        cell = f'li.doc-block[data-uid="{u}"] .doc-weglot'
        expect(p.locator(cell)).to_be_visible()
        assert rgb(css(p, cell, "backgroundColor")) == WEGLOT_BG
        assert rgb(css(p, cell, "color")) == MUTED
        assert contrast(MUTED, WEGLOT_BG) >= 4.5


# ── 2. what the reader actually sees is readable ─────────────────────────────────────────────────
def test_every_text_the_reader_sees_is_4_5_to_1_or_more_against_its_own_ground(browser):
    (body,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, body, "Entwurf")) as e:
        p = e.page
        li = f'li.doc-block[data-uid="{body}"]'
        page_bg = rgb(css(p, "body", "backgroundColor"))
        pairs = {
            "English on its sheet": (css(p, f"{li} .doc-en", "color"), css(p, li, "backgroundColor", "::before")),
            "the translation on its sheet": (css(p, f"{li} .doc-tgt", "color"), css(p, li, "backgroundColor", "::after")),
            "the note under the translation": (css(p, f"{li} .doc-note", "color"), css(p, li, "backgroundColor", "::after")),
            "the sheet heads": (css(p, ".doc-head", "color"), css(p, ".doc-head", "backgroundColor")),
            # CEL-069: the outline lives in the page tree (its title is for screen readers only); the shell's own texts
            "an outline name, in the tree": (css(p, ".doc-outline-name", "color"), css(p, ".doc-tree", "backgroundColor")),
            "a page name in the tree": (css(p, ".doc-tree-name", "color"), css(p, ".doc-tree", "backgroundColor")),
            "a folder row in the tree": (css(p, ".doc-tree-fold", "color"), css(p, ".doc-tree", "backgroundColor")),
            "a language tab at rest": (css(p, '.doc-tab[aria-selected="false"]', "color"), None),
            "the path's folder": (css(p, ".doc-path-dir", "color"), None),
            "the words count in the bar": (css(p, ".doc-words", "color"), css(p, ".doc-status", "backgroundColor")),
            "the desk version in the bar": (css(p, ".doc-desk-version", "color"), css(p, ".doc-status", "backgroundColor")),
        }
        for what, (fg, bg) in pairs.items():
            ratio = contrast(rgb(fg), rgb(bg) if bg else page_bg)
            assert ratio >= 4.5, f"{what}: {ratio:.2f}:1"


# ── 3. an edited text: an ochre bar and the word in ochre ─────────────────────────────────────────
def test_an_edited_text_has_an_ochre_bar_and_its_word_in_ochre(browser):
    (u,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, u, "Alter Entwurf")) as e:
        p = e.page
        edit(p, u, "Geaenderter Text")
        li = f'li.doc-block[data-uid="{u}"]'
        expect(p.locator(li)).to_have_attribute("data-source", "edit")
        expect(p.locator(li)).to_have_attribute("data-state", "idle", timeout=10000)     # "Edited" is the idle word
        assert rgb(css(p, f"{li} .doc-tgt", "backgroundColor", "::after")) == EDITED
        assert css(p, f"{li} .doc-tgt", "width", "::after") == "3px"
        assert css(p, f"{li} .doc-tgt", "opacity", "::after") == "1"
        assert rgb(css(p, f"{li} .doc-note-state", "color")) == EDITED_INK
        assert css(p, f"{li} .doc-note-state", "fontWeight") == "500"
        assert contrast(EDITED, SHEET) >= 3 and contrast(EDITED_INK, SHEET) >= 4.5



def test_only_the_word_edited_is_ochre_an_edited_texts_other_states_keep_their_colours(browser):
    """CEL-070 round 1, fix 1: doc-spec.md §3 keeps the saving and error notes as they were; only "Edited" is
    ochre. The same edited text, painted saving, not saved and idle."""
    (u,) = plain_ids(1)
    with doc(browser, seed=lambda e: draft(e.store, u, "Alter Entwurf")) as e:
        p = e.page
        edit(p, u, "Geaenderter Text")
        li = f'li.doc-block[data-uid="{u}"]'
        expect(p.locator(li)).to_have_attribute("data-source", "edit")
        expect(p.locator(li)).to_have_attribute("data-state", "idle", timeout=10000)
        seen = {}
        for state in ("error", "saving", "idle"):
            p.evaluate("([s, st]) => document.querySelector(s).setAttribute('data-state', st)", [li, state])
            seen[state] = (rgb(css(p, f"{li} .doc-note-state", "color")), css(p, f"{li} .doc-note-state", "fontWeight"))
        assert seen["error"] == (ERR, "400"), seen
        assert seen["saving"] == (MUTED, "400"), seen
        assert seen["idle"] == (EDITED_INK, "500"), seen


# ── 4. a flagged text carries a mark ──────────────────────────────────────────────────────────────
def test_a_flagged_text_carries_a_brick_bar_and_tint_and_the_others_do_not(browser):
    import hashlib
    flagged, other = plain_ids(2)
    by_id = {b["id"]: b for b in _stage_data()["blocks"]}

    def seed(e):
        live = by_id[flagged].get("w", {}).get(LANG) or by_id[flagged]["en"]
        e.store.seed_findings(LANG, [{"unit_id": flagged, "subject": "live", "subject_sha": hashlib.sha256(live.encode()).hexdigest(),
                                      "rule": "test-rule", "severity": "warn", "message": "A test finding",
                                      "cite": "A test guideline", "hits": [by_id[flagged]["en"][:8]]}])

    with doc(browser, seed=seed) as e:
        p = e.page
        hit, miss = f'li.doc-block[data-uid="{flagged}"]', f'li.doc-block[data-uid="{other}"]'
        expect(p.locator(hit)).to_have_attribute("data-flagged", "")
        assert p.locator(miss).get_attribute("data-flagged") is None
        assert rgb(css(p, f"{hit} .doc-tgt", "backgroundColor")) == FLAG_BG
        shadow = css(p, f"{hit} .doc-tgt", "boxShadow")
        assert "rgb(163, 54, 31)" in shadow and "rgb(237, 220, 198)" in shadow, shadow
        assert css(p, f"{miss} .doc-tgt", "boxShadow") == "none"
        assert contrast(INK, FLAG_BG) >= 4.5 and contrast(FLAG, SHEET) >= 3
