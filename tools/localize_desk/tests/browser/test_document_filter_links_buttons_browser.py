"""Robot click-tests for the Links and Buttons choices of the document page's bottom bar (CEL-107).

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/,
the mock Worker). What the bar's `Show` list must do after the three older filters (CEL-036):

  - end with `Links (n)` and `Buttons (n)`, n = the texts of the OPEN page in that group, in COPY.md's words;
  - Links keeps a text that is a link (the engine's `link` block tag) or has one in it (an anchor marker in the
    English); Buttons keeps the engine's `button` block tag; a button that is an anchor is in both;
  - the numbers follow the page (and not the language), the plain word shows while a page loads;
  - a group with no text on the page leaves the page empty, with the filter's own line, and All texts brings it back.

The expected sets are worked out here from the page's data (`b` and `en`), never from the page. Where a test needs
every kind of text it rewrites the first few blocks of the staged copy before the page loads (`craft`), so the
test does not depend on what the engine's last run found. Expected wording comes from COPY.md through `copy_text.t`.
The harness helpers are COPIED from test_document_browser.py (the convention of this folder: no imports between test files).
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

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import harness as H  # noqa: E402

PAGES = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]
LANG = "de"
READY = '#doc[data-state="ready"]'
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
LINK_MARK = re.compile(r'<a wg-\d+="">')


# ── the harness, copied from test_document_browser.py ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk():
    """The harness on a free port: a temporary copy of docs/ and the mock Worker."""
    root = H.stage_copy(save_on=True, save_off=False)
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
    key: str
    lang: str
    data: dict
    page: object = None
    errors: list = field(default_factory=list)


def _data_path(root: Path, name: str) -> Path:
    return root / "admin" / "localization" / "document" / "data" / f"{name}.json"


def _committed(name: str) -> dict:
    """The generated page data as committed in docs/ (what the harness copies)."""
    path = H.REPO_DOCS / "admin" / "localization" / "document" / "data" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def doc(browser, *, key: str = "vancouver", lang: str = LANG, craft=None):
    """The document page open and ready. `craft(blocks)` rewrites the staged page's blocks before the page loads.
    On a normal exit it asserts no page error and no console error happened."""
    with desk() as (base, root, _worker):
        path = _data_path(root, key)
        data = json.loads(path.read_text(encoding="utf-8"))
        if craft:
            craft(data["blocks"])
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        env = Env(base=base, root=root, key=key, lang=lang, data=data)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
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
        pg.goto(f"{base}/admin/localization/document/?page={key}&lang={lang}")
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


# ── what is a link, what is a button: worked out from the data ────────────────────────────────────
def is_button(b: dict) -> bool:
    return b["b"] == "button"


def is_link(b: dict) -> bool:
    return b["b"] == "link" or bool(LINK_MARK.search(b["en"]))


def ids(blocks, test) -> list[str]:
    return [b["id"] for b in blocks if test(b)]


def craft(blocks: list[dict]) -> None:
    """Block 0..4 become one of each kind of text; every other block stays as the engine wrote it."""
    blocks[0].update(b="button", en="Send it")                                    # a button, no anchor
    blocks[1].update(b="button", en='<a wg-1="">Apply now</a>')                   # a button that is an anchor
    blocks[2].update(b="link", en="Courses")                                      # a label inside a link block
    blocks[3].update(b="p", en='Read <a wg-1="">the guide</a> first.')            # a link inside a sentence
    blocks[4].update(b="p", en="Tuition is included.")                            # neither


def _choose(page, value: str) -> None:
    """Pick a choice the way a reader does: the click on the list takes the caret out of any text first."""
    page.evaluate("() => { const a = document.activeElement; if (a && a !== document.body && a.blur) a.blur(); }")
    page.select_option("#doc-filter", value=value)


def _shown(page) -> list[str]:
    return page.eval_on_selector_all("li.doc-block", "els => els.filter(l => !l.hidden).map(l => l.dataset.uid)")


def _labels(page) -> list[str]:
    return page.eval_on_selector_all("#doc-filter option", "els => els.map(o => o.textContent.trim())")


def _counted(word_key: str, n: int) -> str:
    return C.t("doc.filter.counted", filter=C.t(word_key), n=n)


def _go(page, key: str) -> None:
    """Open another page of the same desk through the page tree."""
    page.wait_for_function("() => document.querySelectorAll('.doc-tree-page').length >= 4", timeout=20000)
    page.locator(f'.doc-tree-page[data-page="{key}"]').click()
    page.wait_for_function(
        """k => { const r = document.querySelector('.doc-tree-page[aria-current="page"]');
                 return !!r && r.dataset.page === k && !!document.querySelector('#doc[data-state="ready"]'); }""",
        arg=key, timeout=20000)


# ── the list and its numbers ──────────────────────────────────────────────────────────────────────
def test_the_list_ends_with_links_and_buttons_each_with_the_count_of_the_open_page(browser):
    data = _committed("vancouver")["blocks"]
    nl, nb = len(ids(data, is_link)), len(ids(data, is_button))
    assert nl > 0 and nb > 0, "the committed vancouver page has a link and a button to count"
    with doc(browser) as e:
        values = e.page.eval_on_selector_all("#doc-filter option", "els => els.map(o => o.value)")
        assert values == ["all", "new", "edited", "flagged", "links", "buttons"]
        words = _labels(e.page)
        assert words[:4] == [C.t(k) for k in ("doc.filter.all", "doc.filter.new", "doc.filter.edited", "doc.filter.flagged")]
        assert words[4] == _counted("doc.filter.links", nl) and words[5] == _counted("doc.filter.buttons", nb)
        assert words[4].startswith("Links (") and words[5].startswith("Buttons ("), words


@pytest.mark.parametrize("key", PAGES)
def test_every_page_shows_its_own_numbers_and_the_language_does_not_change_them(browser, key):
    data = _committed(key)["blocks"]
    want = [_counted("doc.filter.links", len(ids(data, is_link))), _counted("doc.filter.buttons", len(ids(data, is_button)))]
    assert len(ids(data, is_link)) > 0
    for lang in ("de", "ja"):
        with doc(browser, key=key, lang=lang) as e:
            assert _labels(e.page)[4:] == want, (key, lang)


# ── the choices keep exactly their texts ──────────────────────────────────────────────────────────
def test_links_keeps_exactly_the_texts_that_are_a_link_or_hold_one_and_its_number_is_what_is_shown(browser):
    with doc(browser, craft=craft) as e:
        blocks = e.data["blocks"]
        want = ids(blocks, is_link)
        first = [b["id"] for b in blocks[:5]]
        assert [u in want for u in first] == [False, True, True, True, False]         # the truth table of craft()
        _choose(e.page, "links")
        assert _shown(e.page) == want
        assert e.page.locator("li.doc-block:visible").count() == len(want)             # a hidden text takes no room
        assert _labels(e.page)[4] == _counted("doc.filter.links", len(want))


def test_buttons_keeps_exactly_the_button_texts_and_a_button_that_is_an_anchor_is_in_both_lists(browser):
    with doc(browser, craft=craft) as e:
        blocks = e.data["blocks"]
        want = ids(blocks, is_button)
        first = [b["id"] for b in blocks[:5]]
        assert [u in want for u in first] == [True, True, False, False, False]
        _choose(e.page, "buttons")
        assert _shown(e.page) == want
        assert e.page.locator("li.doc-block:visible").count() == len(want)
        assert _labels(e.page)[5] == _counted("doc.filter.buttons", len(want))
        anchor_button = first[1]
        assert anchor_button in _shown(e.page)
        _choose(e.page, "links")
        assert anchor_button in _shown(e.page)                                         # also under Links
        assert first[0] not in _shown(e.page)                                          # a button with no link is not


def test_all_texts_brings_the_whole_page_back_after_links_and_after_buttons(browser):
    with doc(browser, craft=craft) as e:
        everything = [b["id"] for b in e.data["blocks"]]
        for choice in ("links", "buttons"):
            _choose(e.page, choice)
            assert 0 < len(_shown(e.page)) < len(everything)
            _choose(e.page, "all")
            assert _shown(e.page) == everything
            expect(e.page.locator("#doc-filter-empty")).to_be_hidden()


def test_a_choice_follows_the_reader_to_another_page_with_that_pages_numbers_and_an_empty_group_says_so(browser):
    vanc, howlong = _committed("vancouver")["blocks"], _committed("how-long-to-learn-english")["blocks"]
    assert len(ids(vanc, is_button)) > 0 and len(ids(howlong, is_button)) == 0 and len(ids(howlong, is_link)) > 0
    with doc(browser, key="vancouver") as e:
        _choose(e.page, "buttons")
        assert _shown(e.page) == ids(vanc, is_button)
        _go(e.page, "how-long-to-learn-english")
        words = _labels(e.page)
        assert words[4] == _counted("doc.filter.links", len(ids(howlong, is_link)))
        assert words[5] == _counted("doc.filter.buttons", 0)
        assert e.page.locator("#doc-filter").input_value() == "buttons"                # the choice stays
        assert _shown(e.page) == []
        expect(e.page.locator("#doc-filter-empty")).to_be_visible()
        expect(e.page.locator("#doc-filter-empty")).to_contain_text(C.t("doc.filter.empty"))
        rows = e.page.eval_on_selector_all("#doc-outline-list > li", "els => els.map(l => l.hidden)")
        assert rows and all(rows), rows                                                # no section has a button
        _choose(e.page, "links")
        assert _shown(e.page) == ids(howlong, is_link)
        expect(e.page.locator("#doc-filter-empty")).to_be_hidden()
        _go(e.page, "vancouver")                                                       # and back: the first page's numbers
        assert _labels(e.page)[4] == _counted("doc.filter.links", len(ids(vanc, is_link)))
        assert _shown(e.page) == ids(vanc, is_link)


def test_while_a_page_cannot_be_read_the_two_choices_go_back_to_their_plain_words(browser):
    """The numbers are of the open page: a page that fails to load has none, so the list must not keep the last page's."""
    with doc(browser, key="vancouver") as e:
        assert _labels(e.page)[4].startswith("Links (")
        e.page.route("**/how-long-to-learn-english.json", lambda route: route.abort())
        e.page.wait_for_function("() => document.querySelectorAll('.doc-tree-page').length >= 4", timeout=20000)
        e.page.locator('.doc-tree-page[data-page="how-long-to-learn-english"]').click()
        e.page.wait_for_selector('#doc[data-state="error"]', timeout=20000)
        assert _labels(e.page)[4:] == [C.t("doc.filter.links"), C.t("doc.filter.buttons")]
        e.errors[:] = [x for x in e.errors if "Failed to load resource" not in x]       # the abort we asked for
