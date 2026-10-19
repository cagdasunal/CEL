"""Robot click-tests for the document page of the localization desk (desk v2, CEL-026).

A real Chromium drives `/admin/localization/document/` in the click-test harness: a temporary copy of
docs/ with saving switched on, the storage's stand-in behind a mock Worker (`harness.MockWorker`, whose
`store` is a `DeskStore`). A test plays ANOTHER editor, or the engine, by calling `store.handle(...)`,
`store.finish_job(...)` and by writing `store.drafts` / `store.pipeline` directly.

What it holds the page to (the contract is runtime/out/loc2/CEL-026/contract.md, sections 3, 4, 7 and the
Manager's rulings that followed): document order without the site's menu and footer; every text editable;
the pages x languages grid and its states; edit -> autosave -> reload; markers that cannot be lost or
forged; ONE undo stack (buttons, keys inside and outside a text, redo); History and Restore; the toolbar;
the Weglot column; conflicts that never overwrite; the outline; Translate page (confirm, job, queue,
failure); layout at 1440 / 1024 / 375 / 320; failing saves; chunking and the max wait.

Expected wording comes from COPY.md through `copy_text.t` / `tn`, never typed here. Autosave runs in about
0.2 s here because every page gets `window.DOC_TIMING` before it loads. Every test also asserts the page
raised no error and logged none to the console (scenario 14), through `doc()`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timedelta, timezone
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
OTHER = "other@example.test"
READY = '#doc[data-state="ready"]'
# Autosave in ~0.2 s instead of 2 s / 10 s; the poll for a running job every 0.2 s.
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')
LINK_ONLY = re.compile(r'<a wg-\d+="">.*?</a>', re.S)
CHROME_LIST = Path(__file__).resolve().parents[1] / "fixtures" / "document_chrome_en.json"


# ── the harness, copied from test_desk_browser.py ─────────────────────────────────────────────────
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


# ── small helpers ─────────────────────────────────────────────────────────────────────────────────
def plain(text: str) -> str:
    return MARK.sub("", text or "")


def conflict_text(who: str, text: str) -> str:
    """`doc.conflict.text` filled by hand: copy_text.t() cannot take a placeholder named `text`."""
    return C.load()["doc.conflict.text"].replace("{who}", who).replace("{text}", text)


def maybe_t(key: str, **values):
    """COPY.md's text, or None while the key is not there yet (the wording check is then skipped)."""
    try:
        return C.t(key, **values)
    except KeyError:
        return None


def until(fn, timeout: float = 6.0, step: float = 0.05, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    raise AssertionError(f"timed out waiting for {what}")


def dec(store, uid, lang=LANG):
    return store.decisions.get((lang, uid))


def dtext(store, uid, lang=LANG):
    d = dec(store, uid, lang)
    return d["record"].get("text") if d else None


def dver(store, uid, lang=LANG) -> int:
    d = dec(store, uid, lang)
    return d["version"] if d else 0


def wait_text(store, uid, text, lang=LANG, timeout=6.0):
    until(lambda: dtext(store, uid, lang) == text, timeout,
          what=f"the server's text of {uid} to be {text!r} (it is {dtext(store, uid, lang)!r})")


def wait_ver(store, uid, version, lang=LANG, timeout=6.0):
    until(lambda: dver(store, uid, lang) == version, timeout,
          what=f"the server's version of {uid} to be {version} (it is {dver(store, uid, lang)})")


def draft(store, uid, text, lang=LANG, at="2026-10-01T10:00:00.000Z"):
    store.drafts[(lang, uid)] = {"text": text, "arrivedAt": at}


def other_write(store, uid, text, base, *, page=PAGE_KEY, lang=LANG, email=OTHER):
    """ANOTHER editor saving behind the page's back (text None = they cleared it)."""
    code, body = store.handle("desk-write", {
        "locale": lang, "client": 1,
        "changes": [{"unit": uid, "page": page, "base": base,
                     "record": {"text": text} if text is not None else None}]}, email)
    assert code == 200 and body["applied"], body
    return body["applied"][0]["version"]


def blk(page, uid):
    return page.locator(f'li.doc-block[data-uid="{uid}"]')


def tgt(page, uid):
    return blk(page, uid).locator(".doc-tgt")


def field_value(page, uid) -> str:
    return page.evaluate("""uid => RichField.serialize(
        document.querySelector('li.doc-block[data-uid="' + uid + '"] .doc-tgt'))""", uid)


def wait_value(page, uid, text, timeout=6000):
    page.wait_for_function("""([uid, v]) => {
        const el = document.querySelector('li.doc-block[data-uid="' + uid + '"] .doc-tgt');
        return !!el && RichField.serialize(el) === v; }""", arg=[uid, text], timeout=timeout)


def edit(page, uid, text):
    """Click into a translation, select everything and type the new text."""
    tgt(page, uid).click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type(text)


def caret_at_start(page, uid):
    page.evaluate("""uid => {
        const f = document.querySelector('li.doc-block[data-uid="' + uid + '"] .doc-tgt'); f.focus();
        const r = document.createRange(); r.selectNodeContents(f); r.collapse(true);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""", uid)


def caret_end_of_first_text(page, uid):
    """The caret at the end of the field's first plain text (inside a link, between its chips)."""
    page.evaluate("""uid => {
        const f = document.querySelector('li.doc-block[data-uid="' + uid + '"] .doc-tgt'); f.focus();
        const tn = [...f.childNodes].find(n => n.nodeType === 3 && n.nodeValue.length);
        const r = document.createRange(); r.setStart(tn, tn.nodeValue.length); r.collapse(true);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""", uid)


def on_top(loc) -> bool:
    """The element is what a click at its centre (and near its left edge) would hit: nothing is painted over it.
    `expect(...).to_be_visible()` is not this -- it only asks for a box and `visibility`."""
    loc.scroll_into_view_if_needed()
    return loc.evaluate("""el => [[0.5, 0.5], [0.05, 0.5]].every(([fx, fy]) => {
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy);
        return !!hit && (hit === el || el.contains(hit)); })""")


def box(loc) -> dict:
    b = loc.bounding_box()
    assert b, "the element has no box on screen"
    return b


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


def pick_no_w(data: dict, n: int = 1, *, lang: str = LANG) -> list[str]:
    """Plain paragraph/list texts on no other page that the website has NO wording for in `lang` (their `w`
    has no entry for it): on these pages that is a number, a name, a level code -- short, so `clean()`'s
    12-character floor does not apply."""
    out = [b["id"] for b in data["blocks"]
           if not b["lock"] and b["b"] in ("p", "li") and not b.get("also") and not b.get("out")
           and not MARK.search(b["en"]) and 3 <= len(b["en"]) <= 400 and not b.get("w", {}).get(lang)][:n]
    assert len(out) == n, "the page data has too few plain texts without a Weglot wording for this test"
    return out


def engine_takes(uid: str, record: dict, block: dict, live: str, text: str) -> None:
    """The engine's own export rule (monorepo `tools/localize/export.py` `approved_rows`) takes the record the
    page stored: one row with the typed wording, while the same record without `tray` / `approvedAgainst`
    (what the page wrote before round 2) is skipped as not approved. Runs where the engine repo is on this
    machine (ENGINE_REPO, default the monorepo); CEL's own CI does not have it, and the exact-shape asserts
    beside each call are CEL's half of the same contract."""
    root = Path(os.environ.get("ENGINE_REPO", "/Users/cagdas/Desktop/dev/webflow"))
    if not (root / "tools" / "localize" / "export.py").is_file():
        return
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.localize.export import approved_rows  # noqa: E402
    unit = {"word_from": block["en"], "word_to": live, "type": "Text", "role": "body", "markup_class": "plain"}
    rows, skipped = approved_rows({uid: record}, {uid: unit}, LANG)
    assert [r.word_to for r in rows] == [text], skipped
    rows, skipped = approved_rows({uid: {"text": text}}, {uid: unit}, LANG)
    assert rows == [] and skipped["EXPORT-SKIP-NOT-APPROVED"] == [uid]


def block_of(data: dict, uid: str) -> dict:
    return next(b for b in data["blocks"] if b["id"] == uid)


def sections(data: dict) -> list[dict]:
    """The outline (CEL-031): Search result, then one entry per SECTION. A section is what a block's own `sec`
    field (plain text, in the page JSON) names: a new entry starts where `sec` changes, at the block that
    starts it, named by that `sec`; a block with an empty `sec` starts none and belongs to the entry before
    it. n counts the editable texts from that block to the next entry's (the first block included)."""
    out = [{"name": C.t("doc.outline.search"), "target": None, "ids": []}]
    cur = None
    for b in data["blocks"]:
        if b["b"] in ("meta-title", "meta-description"):
            out[0]["target"] = out[0]["target"] or b["id"]
            if not b["lock"]:
                out[0]["ids"].append(b["id"])
            continue
        sec = plain(b.get("sec") or "")
        if sec and (cur is None or cur["sec"] != sec):
            cur = {"name": sec, "sec": sec, "target": b["id"], "ids": []}
            out.append(cur)
        if cur is not None and not b["lock"]:
            cur["ids"].append(b["id"])
    return out


def section_names(data: dict) -> list[str]:
    """The distinct consecutive `sec` values of the page's blocks (meta texts left out), read straight from
    the data and independently of `sections()`: what the rail must name, after 'Search result'."""
    names: list[str] = []
    for b in data["blocks"]:
        sec = plain(b.get("sec") or "")
        if b["b"] in ("meta-title", "meta-description") or not sec:
            continue
        if not names or names[-1] != sec:
            names.append(sec)
    return names


def cell(page, key, lang):
    return page.locator(f'.doc-cell[data-page="{key}"][data-lang="{lang}"]')


def wait_cells_known(page):
    page.wait_for_function("document.querySelectorAll('.doc-cell[data-status=\"unknown\"]').length === 0",
                           timeout=15000)


def bar(page):
    return page.locator("#doc-save")


def open_cell(page, key, lang):
    cell(page, key, lang).click()
    page.wait_for_function(
        """([k, l]) => document.querySelector('#doc').dataset.state === 'ready'
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.page === k
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.lang === l""",
        arg=[key, lang], timeout=20000)


def ids_unique_to(pages: dict, key: str) -> list[str]:
    others = set()
    for p in pages["pages"]:
        if p["key"] != key:
            others |= set(p["ids"])
    mine = next(p for p in pages["pages"] if p["key"] == key)["ids"]
    return [i for i in mine if i not in others]


def iso_after(iso: str, seconds: int) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


STATES_JS = """uid => {
    const li = document.querySelector('li.doc-block[data-uid="' + uid + '"]');
    window.__old = [];
    new MutationObserver(rs => rs.forEach(r => window.__old.push(r.oldValue)))
        .observe(li, {attributes: true, attributeFilter: ['data-state'], attributeOldValue: true});
}"""


def states_seen(page, uid) -> list[str]:
    return page.evaluate("""uid => window.__old.concat(
        document.querySelector('li.doc-block[data-uid="' + uid + '"]').dataset.state)""", uid)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. order and structure
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_blocks_come_in_document_order_without_menu_or_footer(browser):
    with doc(browser) as e:
        rows = e.page.eval_on_selector_all(
            "li.doc-block", "els => els.map(l => [l.dataset.uid, l.dataset.b, l.dataset.lock])")
        blocks = e.data["blocks"]
        assert [r[0] for r in rows] == [b["id"] for b in blocks]
        assert [r[1] for r in rows] == [b["b"] for b in blocks]
        assert [r[1] for r in rows[:3]] == ["meta-title", "meta-description", "meta-title"]
        assert e.data["chrome"] > 0, "the menu and footer were not dropped from the page data"
        assert len(rows) == len(blocks)
        info = next(p for p in e.pages["pages"] if p["key"] == PAGE_KEY)
        assert info["count"] == len(blocks) and info["chrome"] == e.data["chrome"]


def test_every_text_is_editable_nothing_is_read_only(browser):
    """Operator 21:00: summary-owned, link-only and noise texts are editable like the rest."""
    with doc(browser) as e:
        assert all(b["lock"] == "" for b in e.data["blocks"]), "a block is still locked in the page data"
        n = e.page.eval_on_selector_all(
            "li.doc-block .doc-tgt", "els => els.filter(x => x.getAttribute('contenteditable') === 'true').length")
        assert n == len(e.data["blocks"])
        locked = e.page.eval_on_selector_all("li.doc-block", "els => els.filter(l => l.dataset.lock).length")
        assert locked == 0
        assert e.page.locator("li.doc-block .doc-tools").count() == len(e.data["blocks"])


def test_a_link_only_text_accepts_typing_and_keeps_its_markers(browser):
    data = _stage_data()
    cands = [b for b in data["blocks"]
             if b["en"].strip().startswith("<a wg-") and not LINK_ONLY.sub("", b["en"]).strip()
             and MARK.search(b.get("w", {}).get(LANG, "")) and plain(b["w"][LANG]).strip()]
    assert cands, "no link-only text with a translation on the page"
    b = cands[0]
    w = b["w"][LANG]
    first = next(seg for seg in MARK.split(w) if seg)
    expected = w.replace(first, first + "X", 1)

    with doc(browser, seed=lambda env: draft(env.store, b["id"], w)) as e:
        assert field_value(e.page, b["id"]) == w
        caret_end_of_first_text(e.page, b["id"])
        e.page.keyboard.type("X")
        wait_text(e.store, b["id"], expected)
        assert MARK.findall(dtext(e.store, b["id"])) == MARK.findall(w)
        assert tgt(e.page, b["id"]).locator(".rf-token").count() == len(MARK.findall(w))


@pytest.mark.parametrize("variant", ["home", "one", "many"])
def test_a_text_used_outside_the_four_pages_is_editable_and_says_so(browser, variant):
    data = _stage_data()
    shared = [b for b in data["blocks"] if b.get("out")]
    assert shared, "no text on this page is used outside the four pages"
    pick_ = {"home": lambda b: b.get("outEg") == "/",
             "one": lambda b: b["out"] == 1 and b.get("outEg") != "/",
             "many": lambda b: b["out"] > 1}[variant]
    found = [b for b in shared if pick_(b)]
    if not found:
        pytest.skip(f"no shared text of kind {variant!r} on this page")
    b = found[0]
    eg = C.t("row.shared.home") if b.get("outEg") == "/" else b.get("outEg", "")
    with doc(browser) as e:
        li = blk(e.page, b["id"])
        assert li.get_attribute("data-lock") == ""
        expect(li.locator(".doc-tgt")).to_have_attribute("contenteditable", "true")
        expect(li.locator(".doc-note")).to_contain_text(C.tn("doc.shared", b["out"], example=eg))


def test_a_text_that_is_also_on_another_page_of_the_four_says_so(browser):
    data = _stage_data()
    also = [b for b in data["blocks"] if b.get("also")]
    assert also, "no text on this page is also on another of the four"
    b = next((x for x in also if len(x["also"]) == 1), also[0])
    labels = [C.t(f"page.{p}") for p in b["also"]]
    with doc(browser) as e:
        note = blk(e.page, b["id"]).locator(".doc-note")
        if len(labels) == 1:
            expect(note).to_contain_text(C.t("doc.also", pages=labels[0]))
        else:
            head, tail = C.t("doc.also", pages="\0").split("\0")
            expect(note).to_contain_text(head.strip())
            expect(note).to_contain_text(tail.strip())
            for label in labels:
                expect(note).to_contain_text(label)


@pytest.mark.parametrize("key", PAGES)
def test_no_site_menu_or_footer_text_is_among_the_english_texts(browser, key):
    """Ruling 21:01: the menu and footer are out on ALL pages. The check is an EXPLICIT per-page list
    (fixtures/document_chrome_en.json: every text the English page's own nav / header / footer landmarks hold,
    built by tools/localize/align.py's landmark finder, not by the desk's >= 30 pages rule), so a menu or footer
    text that slipped below that rule is a difference here. A text is the unit with its link markers: the plain
    "General English" of the body is not the menu's `<a wg-1="">General English</a>`, so the comparison is exact."""
    listed = json.loads(CHROME_LIST.read_text(encoding="utf-8"))["pages"][key]
    kept = set(listed["kept_on_purpose"])
    dropped = [t for t in listed["landmark_texts"] if t not in kept] + listed["outside_landmarks"]
    assert dropped and len(set(dropped)) == len(dropped), f"{key}: the list holds no (or doubled) menu/footer texts"
    with doc(browser, key=key) as e:
        shown = e.page.eval_on_selector_all("li.doc-block .doc-en", "els => els.map(x => RichField.serialize(x))")
        assert shown == [b["en"] for b in e.data["blocks"]], "the page does not show exactly the page data's blocks"
        on_page = set(shown)
        hits = [t for t in dropped if t in on_page]
        assert not hits, f"{key}: site menu/footer texts are on the page: {hits}"
        # the exceptions are real: a landmark text kept on purpose is on the page ...
        gone = sorted(t for t in kept if t not in on_page)
        assert not gone, f"{key}: kept on purpose, but not on the page: {gone}"
        # ... and they are the ONLY listed texts that are: every text of the list is dropped or kept on purpose
        listed_all = set(listed["landmark_texts"]) | set(listed["outside_landmarks"])
        assert {s for s in shown if s in listed_all} == kept
        # the dropped texts are all the generator reports as dropped (distinct texts: one per list entry)
        assert len(dropped) == e.data["chrome"], (key, len(dropped), e.data["chrome"])


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. the grid
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_grid_is_four_pages_by_eight_languages_and_marks_the_open_cell(browser):
    with doc(browser) as e:
        rows = e.page.locator("#doc-grid tbody tr")
        assert rows.count() == 4
        assert e.page.eval_on_selector_all("#doc-grid tbody tr", "els => els.map(r => r.dataset.page)") == PAGES
        for i in range(4):
            assert rows.nth(i).locator(".doc-cell").count() == 8
        assert e.page.eval_on_selector_all(
            "#doc-grid thead th.doc-grid-lang", "els => els.map(x => x.dataset.lang)") == LANGS
        expect(e.page.locator('#doc-grid thead th[data-lang="de"]')).to_contain_text(C.t("lang.de"))
        pressed = e.page.locator('.doc-cell[aria-pressed="true"]')
        assert pressed.count() == 1
        assert pressed.get_attribute("data-page") == PAGE_KEY and pressed.get_attribute("data-lang") == "de"
        wait_cells_known(e.page)
        # a fresh store has nothing anywhere
        for key in PAGES:
            for lang in LANGS:
                c = cell(e.page, key, lang)
                assert c.get_attribute("data-status") == "none", (key, lang)
                expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.none"))
                # the Ask's own words (the empty state "Not translated yet" is another key, doc.banner.*)
                expect(c.locator(".doc-cell-status")).to_have_text("Not translated")
                expect(c.locator(".doc-cell-count")).to_have_text("")
        expect(cell(e.page, PAGE_KEY, "de")).to_have_attribute(
            "aria-label", C.t("doc.cell.aria", page=C.t(f"page.{PAGE_KEY}"), language=C.t("lang.de"),
                              status=C.t("doc.status.none")))


def test_the_grid_reads_drafted_edited_exported_and_not_translated(browser):
    plan = {}

    def seed(env):
        for key in PAGES:
            plan[key] = ids_unique_to(env.pages, key)
            assert len(plan[key]) >= 3, key
        for uid in plan["vancouver"][:3]:
            draft(env.store, uid, "Entwurf " + uid)
        for uid in plan[PAGE_KEY][:2]:
            draft(env.store, uid, "Entwurf " + uid)
        other_write(env.store, plan[PAGE_KEY][2], "Bearbeitet", 0)
        for uid in plan["how-long-to-learn-english"][:2]:
            draft(env.store, uid, "Entwurf " + uid)
            env.store.pipeline[(LANG, uid)] = {"exportedAt": "2026-10-18T12:00:00.000Z"}

    with doc(browser, seed=seed) as e:
        wait_cells_known(e.page)
        total = {p["key"]: len(p["ids"]) for p in e.pages["pages"]}
        want = {"vancouver": ("drafted", 3), PAGE_KEY: ("edited", 3),
                "how-long-to-learn-english": ("exported", 2), "vs-toronto": ("none", 0)}
        for key, (status, n) in want.items():
            c = cell(e.page, key, "de")
            assert c.get_attribute("data-status") == status, key
            expect(c.locator(".doc-cell-status")).to_have_text(C.t(f"doc.status.{status}"))
            expect(c.locator(".doc-cell-count")).to_have_text(
                C.tn("doc.cell.count", n, total=total[key]) if n else "")
        # the four labels of the Ask, word for word: Not translated / Drafted / Edited / Exported
        for key, label in (("vs-toronto", "Not translated"), ("vancouver", "Drafted"), (PAGE_KEY, "Edited"),
                           ("how-long-to-learn-english", "Exported")):
            expect(cell(e.page, key, "de").locator(".doc-cell-status")).to_have_text(label)
        for key in PAGES:                                      # a language with nothing
            c = cell(e.page, key, "fr")
            assert c.get_attribute("data-status") == "none"
            expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.none"))
            expect(c.locator(".doc-cell-status")).to_have_text("Not translated")


def test_clicking_a_cell_opens_that_page_and_language(browser):
    with doc(browser) as e:
        open_cell(e.page, "vancouver", "fr")
        expect(e.page.locator("#doc-title")).to_have_text(
            C.t("doc.title", page=C.t("page.vancouver"), language=C.t("lang.fr")))
        query = e.page.evaluate("() => location.search")
        assert "page=vancouver" in query and "lang=fr" in query
        van = _json(e.root, "vancouver")
        ids = e.page.eval_on_selector_all("li.doc-block", "els => els.map(l => l.dataset.uid)")
        assert ids == [b["id"] for b in van["blocks"]]
        assert e.page.locator('.doc-cell[aria-pressed="true"]').count() == 1
        assert e.page.locator('.doc-tgt').first.get_attribute("lang") == "fr"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. edit -> autosave -> reload
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_an_edit_autosaves_and_is_still_there_after_a_reload(browser):
    (uid,) = pick(_stage_data(), 1)
    text = "Neue Übersetzung eins"
    block = block_of(_stage_data(), uid)
    with doc(browser) as e:
        e.page.evaluate(STATES_JS, uid)
        edit(e.page, uid, text)
        wait_text(e.store, uid, text)
        # the stored record is the v1 decision (see the next test), the website's wording being Weglot's or English
        assert dec(e.store, uid)["record"] == {"tray": "csv", "text": text,
                                               "approvedAgainst": block.get("w", {}).get(LANG) or block["en"]}
        assert dver(e.store, uid) == 1
        assert dec(e.store, uid)["by"] == H.REVIEWER
        e.page.wait_for_function("""([uid, s]) => {
            const li = document.querySelector('li.doc-block[data-uid="' + uid + '"]');
            return li.dataset.state === 'saved' && li.querySelector('.doc-note').textContent.includes(s); }""",
                                 arg=[uid, C.t("doc.text.saved")], timeout=3000)
        expect(bar(e.page)).to_have_attribute("data-state", "saved")
        expect(bar(e.page)).to_have_text(C.t("autosave.saved"))
        seen = states_seen(e.page, uid)
        assert "saving" in seen and seen[-1] == "saved", seen
        # what the page shows after a reload comes from the server, not from this browser
        e.page.evaluate("() => localStorage.clear()")
        e.page.reload()
        e.page.wait_for_selector(READY)
        assert field_value(e.page, uid) == text
        assert blk(e.page, uid).get_attribute("data-source") == "edit"


@pytest.mark.parametrize("wording", ["weglot", "english"])
def test_an_edit_is_stored_as_the_v1_decision_so_the_export_can_take_it(browser, wording):
    """Ruling #55 A11 / #63: leaving a changed field approves it with your edit. The export (tools/localize/
    export.py) skips every record that is not `tray: 'csv'`, so a typed text must be stored as the v1 desk stores
    one: tray csv, the text, and `approvedAgainst` = the wording the website shows now (Weglot's where it has
    one for this language, else the English), in exactly that order."""
    data = _stage_data()
    (uid,) = pick(data, 1, need_w=True) if wording == "weglot" else pick_no_w(data)
    block = block_of(data, uid)
    against = block["w"][LANG] if wording == "weglot" else block["en"]
    assert bool(block.get("w", {}).get(LANG)) == (wording == "weglot")
    text = "Neue Übersetzung eins"
    with doc(browser) as e:
        edit(e.page, uid, text)
        wait_text(e.store, uid, text)
        record = dec(e.store, uid)["record"]
        assert record == {"tray": "csv", "text": text, "approvedAgainst": against}
        assert list(record) == ["tray", "text", "approvedAgainst"]
        assert dver(e.store, uid) == 1
        engine_takes(uid, record, block, against, text)
        # a second typed change builds on the first and is the same shape again
        edit(e.page, uid, text + " zwei")
        wait_text(e.store, uid, text + " zwei")
        assert dec(e.store, uid)["record"] == {"tray": "csv", "text": text + " zwei", "approvedAgainst": against}
        assert dver(e.store, uid) == 2


def test_restore_and_use_weglots_text_write_the_v1_decision_and_undo_this_clears_it(browser):
    (a,) = pick(_stage_data(), 1, need_w=True)
    wde = block_of(_stage_data(), a)["w"][LANG]
    with doc(browser, seed=lambda env: draft(env.store, a, DA)) as e:
        li = blk(e.page, a)
        edit(e.page, a, "Erste Fassung")
        wait_text(e.store, a, "Erste Fassung")
        edit(e.page, a, "Zweite Fassung")
        wait_text(e.store, a, "Zweite Fassung")
        wait_ver(e.store, a, 2)
        # History > Restore the older version
        li.locator(".doc-history-btn").click()
        cards = e.page.locator("#doc-history .doc-version")
        expect(cards).to_have_count(3)                                  # Gemini's draft, the two typed texts
        cards.nth(1).locator(".doc-restore").click()
        wait_text(e.store, a, "Erste Fassung")
        wait_ver(e.store, a, 3)
        record = dec(e.store, a)["record"]
        assert record == {"tray": "csv", "text": "Erste Fassung", "approvedAgainst": wde}
        assert list(record) == ["tray", "text", "approvedAgainst"]
        # Use Weglot's text (its button shows with Show Weglot on)
        e.page.locator("#doc-weglot").check()
        tgt(e.page, a).click()
        li.locator(".doc-tool-weglot").click()
        wait_text(e.store, a, wde)
        wait_ver(e.store, a, 4)
        record = dec(e.store, a)["record"]
        assert record == {"tray": "csv", "text": wde, "approvedAgainst": wde}
        assert list(record) == ["tray", "text", "approvedAgainst"]
        # Undo this: back to Gemini's draft. The record keeps no text, no tray, no approvedAgainst
        tgt(e.page, a).click()
        li.locator(".doc-tool-revert").click()
        wait_ver(e.store, a, 5)
        assert dec(e.store, a)["record"] == {}
        wait_value(e.page, a, DA)


@pytest.mark.parametrize("what", ["shared", "also", "state", "conflict"])
def test_what_is_written_under_a_text_is_not_painted_over(browser, what):
    """The notes and the conflict box live in the translation column's grid cell, which the block's own
    background is drawn in; whatever is drawn there must be on top of it (a click at its centre reaches it)."""
    data = _stage_data()
    with doc(browser) as e:
        if what in ("shared", "also"):
            b = next(x for x in data["blocks"] if x.get("out" if what == "shared" else "also"))
            note = blk(e.page, b["id"]).locator(".doc-note")
            expect(note).not_to_be_empty()
            assert on_top(note), "the note is painted under the block's column background"
        elif what == "state":
            (u,) = pick(data, 1)
            edit(e.page, u, "Ein Text")
            li = blk(e.page, u)
            e.page.wait_for_function("""uid => document.querySelector('li.doc-block[data-uid="' + uid + '"]')
                .dataset.state === 'saved'""", arg=u, timeout=4000)
            expect(li.locator(".doc-note")).to_contain_text(C.t("doc.text.saved"))
            assert on_top(li.locator(".doc-note")), "the state note is painted under the column background"
        else:
            (u,) = pick(data, 1)
            other_write(e.store, u, "Their text", 0)
            edit(e.page, u, "My text")
            li = blk(e.page, u)
            expect(li.locator(".doc-conflict")).to_be_visible()
            for sel in (".doc-conflict", ".doc-keep-mine", ".doc-take-theirs"):
                assert on_top(li.locator(sel)), f"{sel} is painted under the block's column background"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. markers survive
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _marked_block() -> dict:
    data = _stage_data()
    cands = [b for b in data["blocks"]
             if not b["lock"] and MARK.search(b.get("w", {}).get(LANG, "")) and not b["w"][LANG].startswith("<")
             and b["b"] not in ("meta-title", "meta-description")]
    assert cands, "no text on the page has link markers in its translation"
    return cands[0]


@pytest.mark.parametrize("source", ["draft", "decision"])
def test_typing_in_the_text_part_keeps_every_marker_byte_for_byte(browser, source):
    b = _marked_block()
    w = b["w"][LANG]

    def seed(env):
        if source == "draft":
            draft(env.store, b["id"], w)
        else:
            other_write(env.store, b["id"], w, 0, page=PAGE_KEY)

    with doc(browser, seed=seed) as e:
        assert field_value(e.page, b["id"]) == w
        caret_at_start(e.page, b["id"])
        e.page.keyboard.type("Neu ")
        wait_text(e.store, b["id"], "Neu " + w)
        assert MARK.findall(dtext(e.store, b["id"])) == MARK.findall(w)
        assert tgt(e.page, b["id"]).locator(".rf-token").count() == len(MARK.findall(w))


def test_a_typed_marker_is_stripped_not_saved(browser):
    b = _marked_block()
    w = b["w"][LANG]
    with doc(browser, seed=lambda env: draft(env.store, b["id"], w)) as e:
        caret_at_start(e.page, b["id"])
        e.page.keyboard.type('X<a wg-9="">Y</a>Z')
        wait_text(e.store, b["id"], "XYZ" + w)
        assert "wg-9" not in dtext(e.store, b["id"])


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. undo / redo: ONE stack
# ══════════════════════════════════════════════════════════════════════════════════════════════════
DA, DB, DC = "Entwurf Alpha", "Entwurf Beta", "Entwurf Gamma"


def _two_edited(e, a, b):
    """A edited, then B edited (clicking B ends A's undo step); both on the server."""
    edit(e.page, a, "Alpha eins")
    edit(e.page, b, "Beta zwei")
    wait_text(e.store, a, "Alpha eins")
    wait_text(e.store, b, "Beta zwei")
    time.sleep(0.3)                                  # the undo pause: B's burst is one step


def _seed_ab(a, b):
    def seed(env):
        draft(env.store, a, DA)
        draft(env.store, b, DB)
    return seed


def test_undo_and_redo_buttons_walk_the_edits_back_and_forth(browser):
    a, b = pick(_stage_data(), 2)
    with doc(browser, seed=_seed_ab(a, b)) as e:
        undo, redo = e.page.locator("#doc-undo"), e.page.locator("#doc-redo")
        expect(undo).to_be_disabled()
        expect(redo).to_be_disabled()
        edit(e.page, a, "Alpha eins")
        edit(e.page, b, "Beta zwei")                  # clicking B closes A's step
        e.page.keyboard.press("Escape")               # and B's
        wait_text(e.store, a, "Alpha eins")
        wait_text(e.store, b, "Beta zwei")
        assert (dver(e.store, a), dver(e.store, b)) == (1, 1)
        expect(undo).to_be_enabled()
        expect(redo).to_be_disabled()

        undo.click()                                  # B returns to Gemini's draft
        wait_value(e.page, b, DB)
        wait_ver(e.store, b, 2)
        assert dtext(e.store, b) is None and field_value(e.page, a) == "Alpha eins"
        undo.click()                                  # then A
        wait_value(e.page, a, DA)
        wait_ver(e.store, a, 2)
        assert dtext(e.store, a) is None
        expect(undo).to_be_disabled()
        expect(redo).to_be_enabled()

        redo.click()                                  # A is typed again
        wait_value(e.page, a, "Alpha eins")
        wait_text(e.store, a, "Alpha eins")
        wait_ver(e.store, a, 3)
        redo.click()
        wait_value(e.page, b, "Beta zwei")
        wait_text(e.store, b, "Beta zwei")
        wait_ver(e.store, b, 3)
        expect(redo).to_be_disabled()
        expect(undo).to_be_enabled()


def test_undo_and_redo_keys_outside_a_text(browser):
    a, b = pick(_stage_data(), 2)
    with doc(browser, seed=_seed_ab(a, b)) as e:
        edit(e.page, a, "Alpha eins")
        edit(e.page, b, "Beta zwei")
        e.page.keyboard.press("Escape")
        wait_text(e.store, b, "Beta zwei")
        assert e.page.evaluate("() => !document.activeElement.closest('.doc-tgt')")   # focus is NOT in a text
        e.page.keyboard.press("ControlOrMeta+z")
        wait_value(e.page, b, DB)
        wait_ver(e.store, b, 2)
        e.page.keyboard.press("ControlOrMeta+Shift+z")
        wait_value(e.page, b, "Beta zwei")
        wait_ver(e.store, b, 3)
        assert dtext(e.store, b) == "Beta zwei"
        e.page.keyboard.press("ControlOrMeta+z")
        wait_value(e.page, b, DB)
        e.page.keyboard.press("Control+y")             # Ctrl+Y is redo too
        wait_value(e.page, b, "Beta zwei")
        wait_text(e.store, b, "Beta zwei")


def test_ctrl_z_inside_a_text_runs_the_page_undo_not_the_browsers(browser):
    """Ruling: ONE undo stack. After a burst and a pause, Cmd/Ctrl+Z in the focused text reverts THAT text
    through the document stack (a new server version, Redo enabled, the caret stays); pressed again it
    walks back to the earlier text although the caret is still in this one."""
    a, b = pick(_stage_data(), 2)
    with doc(browser, seed=_seed_ab(a, b)) as e:
        _two_edited(e, a, b)                           # the caret is still in B
        assert e.page.evaluate("uid => document.activeElement === document.querySelector("
                               "'li.doc-block[data-uid=\"' + uid + '\"] .doc-tgt')", b)
        e.page.keyboard.press("ControlOrMeta+z")
        wait_value(e.page, b, DB)
        wait_ver(e.store, b, 2)
        assert dtext(e.store, b) is None
        expect(e.page.locator("#doc-redo")).to_be_enabled()
        assert e.page.evaluate("uid => document.activeElement === document.querySelector("
                               "'li.doc-block[data-uid=\"' + uid + '\"] .doc-tgt')", b), "the caret left the text"
        # ONE press is ONE undo step: only B went back. With the browser's own undo let through as well, the
        # same keystroke undid A too (the page's key handler without its preventDefault); autosave is ~0.2 s
        # here, so after 0.6 s a second undo would be on the server.
        time.sleep(0.6)
        assert field_value(e.page, a) == "Alpha eins", "one press undid more than one step (A went back too)"
        assert dtext(e.store, a) == "Alpha eins" and dver(e.store, a) == 1
        assert dtext(e.store, b) is None and dver(e.store, b) == 2
        e.page.keyboard.press("ControlOrMeta+z")       # the browser has nothing left to undo here: the page does
        wait_value(e.page, a, DA)
        wait_ver(e.store, a, 2)
        assert field_value(e.page, b) == DB
        e.page.keyboard.press("ControlOrMeta+Shift+z")
        wait_value(e.page, a, "Alpha eins")
        wait_ver(e.store, a, 3)
        e.page.keyboard.press("Control+y")
        wait_value(e.page, b, "Beta zwei")
        wait_ver(e.store, b, 3)
        assert dtext(e.store, b) == "Beta zwei" and dtext(e.store, a) == "Alpha eins"


def test_the_browsers_own_undo_event_is_cancelled_and_the_page_undo_runs(browser):
    (b,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, b, DB)) as e:
        edit(e.page, b, "Beta zwei")
        wait_text(e.store, b, "Beta zwei")
        time.sleep(0.3)
        cancelled = e.page.evaluate("""uid => {
            const el = document.querySelector('li.doc-block[data-uid="' + uid + '"] .doc-tgt');
            return !el.dispatchEvent(new InputEvent('beforeinput',
                {inputType: 'historyUndo', cancelable: true, bubbles: true})); }""", b)
        assert cancelled, "beforeinput historyUndo was not cancelled"
        wait_value(e.page, b, DB)
        wait_ver(e.store, b, 2)
        expect(e.page.locator("#doc-redo")).to_be_enabled()


def test_a_typing_burst_is_one_undo_step_and_a_pause_makes_another(browser):
    (c,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, c, DC)) as e:
        undo = e.page.locator("#doc-undo")
        tgt(e.page, c).click()
        e.page.keyboard.press("ControlOrMeta+a")
        e.page.keyboard.type("Ein langer Satz wird getippt", delay=25)   # gaps far under the undo pause
        wait_text(e.store, c, "Ein langer Satz wird getippt")
        # the 0.6 s max wait may send the burst in two writes (v1 part way, v2 whole): the undo is the next version
        after_burst = dver(e.store, c)
        undo.click()                                    # ONE click takes the whole burst back
        wait_value(e.page, c, DC)
        wait_ver(e.store, c, after_burst + 1)
        assert dtext(e.store, c) is None
        expect(undo).to_be_disabled()
        expect(e.page.locator("#doc-redo")).to_be_enabled()
        # a pause between two bursts makes two steps
        e.page.locator("#doc-redo").click()
        wait_value(e.page, c, "Ein langer Satz wird getippt")
        tgt(e.page, c).click()
        e.page.keyboard.press("ControlOrMeta+a")
        e.page.keyboard.type("eins")
        time.sleep(0.4)                                 # longer than undoPause (120 ms)
        e.page.keyboard.type(" zwei")
        wait_text(e.store, c, "eins zwei")
        e.page.keyboard.press("Escape")
        undo.click()
        wait_value(e.page, c, "eins")
        undo.click()
        wait_value(e.page, c, "Ein langer Satz wird getippt")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. history and restore
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_history_lists_versions_oldest_to_newest_and_restore_can_be_undone(browser):
    (a,) = pick(_stage_data(), 1)
    gem = "Gemini Entwurf"
    with doc(browser, seed=lambda env: draft(env.store, a, gem)) as e:
        edit(e.page, a, "Erste Fassung")
        wait_text(e.store, a, "Erste Fassung")
        wait_ver(e.store, a, 1)
        edit(e.page, a, "Zweite Fassung")
        wait_text(e.store, a, "Zweite Fassung")
        wait_ver(e.store, a, 2)
        li = blk(e.page, a)
        expect(li.locator(".doc-tools")).to_be_visible()      # the focus is in the text
        li.locator(".doc-history-btn").click()
        drawer = e.page.locator("#doc-history")
        expect(drawer).to_be_visible()
        cards = drawer.locator(".doc-version")
        expect(cards).to_have_count(3)
        texts = cards.locator(".doc-version-text").all_inner_texts()
        assert [t.strip() for t in texts] == [gem, "Erste Fassung", "Zweite Fassung"]
        expect(cards.nth(0)).to_contain_text(C.t("doc.history.draft"))
        xs = [box(cards.nth(i))["x"] for i in range(3)]
        assert xs[0] < xs[1] < xs[2], xs                      # oldest on the left, newest on the right

        cards.nth(1).locator(".doc-restore").click()          # the older version
        wait_text(e.store, a, "Erste Fassung")
        wait_ver(e.store, a, 3)
        expect(e.page.locator("#doc-toasts")).to_contain_text(C.t("doc.history.restored"))
        expect(drawer).to_be_hidden()
        e.page.locator("#doc-undo").click()                    # Undo brings the later text back
        wait_text(e.store, a, "Zweite Fassung")
        wait_ver(e.store, a, 4)
        wait_value(e.page, a, "Zweite Fassung")


def test_history_of_an_untouched_text_says_so(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        tgt(e.page, a).click()
        blk(e.page, a).locator(".doc-history-btn").click()
        expect(e.page.locator("#doc-history")).to_be_visible()
        expect(e.page.locator("#doc-history-list")).to_contain_text(C.t("doc.history.empty"))
        e.page.locator("#doc-history-close").click()
        expect(e.page.locator("#doc-history")).to_be_hidden()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 7. the toolbar
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_use_weglots_text_shows_with_weglot_on_and_can_be_undone(browser):
    (a,) = pick(_stage_data(), 1, need_w=True)
    w = _stage_data()
    wde = next(b for b in w["blocks"] if b["id"] == a)["w"][LANG]
    with doc(browser, seed=lambda env: draft(env.store, a, DA)) as e:
        li = blk(e.page, a)
        tgt(e.page, a).click()
        expect(li.locator(".doc-tools")).to_be_visible()
        expect(li.locator(".doc-tool-weglot")).to_be_hidden()           # Show Weglot is off
        e.page.locator("#doc-weglot").check()
        tgt(e.page, a).click()
        expect(li.locator(".doc-tool-weglot")).to_be_visible()
        expect(li.locator(".doc-tool-weglot")).to_have_text(C.t("doc.tool.weglot"))
        li.locator(".doc-tool-weglot").click()
        wait_value(e.page, a, wde)
        wait_text(e.store, a, wde)
        e.page.locator("#doc-undo").click()
        wait_value(e.page, a, DA)
        wait_ver(e.store, a, 2)
        assert dtext(e.store, a) is None


def test_no_use_weglots_text_button_when_weglot_has_no_wording(browser):
    """With no Weglot wording for the language, the button would put the draft back and erase the edit: it is
    not in the block at all. A text that has a wording has it."""
    data = _stage_data()
    (with_w,) = pick(data, 1, need_w=True)
    (without_w,) = pick_no_w(data)
    wanted = sum(1 for b in data["blocks"] if b.get("w", {}).get(LANG))
    assert 0 < wanted < len(data["blocks"]), "the page needs texts with and without a Weglot wording"
    with doc(browser) as e:
        e.page.locator("#doc-weglot").check()
        tgt(e.page, with_w).click()
        expect(blk(e.page, with_w).locator(".doc-tool-weglot")).to_be_visible()
        assert blk(e.page, with_w).locator(".doc-tool-weglot").count() == 1
        tgt(e.page, without_w).click()
        li = blk(e.page, without_w)
        expect(li.locator(".doc-tools")).to_be_visible()
        assert li.locator(".doc-tool-weglot").count() == 0
        expect(li.locator(".doc-history-btn")).to_be_visible()             # its other actions are still there
        assert li.locator(".doc-tool-revert").count() == 1
        # the whole page: one button per text that has a wording, none for the others
        assert e.page.locator("li.doc-block .doc-tool-weglot").count() == wanted


def test_undo_this_shows_only_on_an_edited_text_and_goes_back_to_geminis_draft(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, DA)) as e:
        li = blk(e.page, a)
        tgt(e.page, a).click()
        expect(li.locator(".doc-tools")).to_be_visible()
        expect(li.locator(".doc-tool-revert")).to_be_hidden()           # nothing edited yet
        edit(e.page, a, "Meine Fassung")
        wait_text(e.store, a, "Meine Fassung")
        expect(li).to_have_attribute("data-source", "edit")
        expect(li.locator(".doc-tool-revert")).to_be_visible()
        expect(li.locator(".doc-tool-revert")).to_have_text(C.t("doc.tool.revert"))
        li.locator(".doc-tool-revert").click()
        wait_value(e.page, a, DA)
        wait_ver(e.store, a, 2)
        assert "text" not in dec(e.store, a)["record"]
        expect(li).to_have_attribute("data-source", "draft")
        e.page.keyboard.press("Escape")                                   # leave the text: the toolbar goes
        expect(li.locator(".doc-tools")).to_be_hidden()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 8. the Weglot column
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_weglot_column_is_off_until_asked_and_the_choice_survives_a_reload(browser):
    data = _stage_data()
    plain_w = next(b for b in data["blocks"] if clean(b, need_w=True))
    marked_w = next(b for b in data["blocks"] if MARK.search(b.get("w", {}).get(LANG, "")))
    with doc(browser) as e:
        toggle = e.page.locator("#doc-weglot")
        expect(toggle).not_to_be_checked()
        expect(e.page.locator("#doc-blocks")).to_have_attribute("data-weglot", "off")
        expect(e.page.locator(".doc-head-weglot")).to_be_hidden()
        assert e.page.eval_on_selector_all(".doc-weglot", "els => els.filter(x => !x.hidden).length") == 0
        expect(blk(e.page, plain_w["id"]).locator(".doc-weglot")).to_be_hidden()

        toggle.check()
        expect(e.page.locator("#doc-blocks")).to_have_attribute("data-weglot", "on")
        expect(e.page.locator(".doc-head-weglot")).to_be_visible()
        expect(e.page.locator(".doc-head-weglot")).to_have_text(C.t("doc.head.weglot"))
        n = len(data["blocks"])
        assert e.page.eval_on_selector_all(".doc-weglot", "els => els.filter(x => !x.hidden).length") == n
        for b in (plain_w, marked_w):
            cellw = blk(e.page, b["id"]).locator(".doc-weglot")
            cellw.scroll_into_view_if_needed()
            expect(cellw).to_be_visible()
            assert e.page.evaluate("el => RichField.serialize(el)", cellw.element_handle()) == b["w"][LANG]
            assert cellw.get_attribute("lang") == LANG

        toggle.uncheck()
        expect(e.page.locator("#doc-blocks")).to_have_attribute("data-weglot", "off")
        expect(e.page.locator(".doc-head-weglot")).to_be_hidden()
        expect(blk(e.page, plain_w["id"]).locator(".doc-weglot")).to_be_hidden()

        toggle.check()
        e.page.reload()
        e.page.wait_for_selector(READY)
        expect(e.page.locator("#doc-weglot")).to_be_checked()
        expect(e.page.locator("#doc-blocks")).to_have_attribute("data-weglot", "on")
        expect(e.page.locator(".doc-head-weglot")).to_be_visible()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 9. conflicts
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("choice", ["theirs", "mine"])
def test_a_text_someone_else_saved_first_is_never_overwritten(browser, choice):
    (u,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        other_write(e.store, u, "Their text", 0)                       # behind the page's back
        edit(e.page, u, "My text")
        li = blk(e.page, u)
        box_ = li.locator(".doc-conflict")
        expect(box_).to_be_visible()
        expect(box_).to_contain_text(conflict_text(OTHER, "Their text"))
        expect(box_.locator(".doc-keep-mine")).to_have_text(C.t("doc.conflict.mine"))
        expect(box_.locator(".doc-take-theirs")).to_have_text(C.t("doc.conflict.theirs"))
        expect(li).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_contain_text(C.tn("autosave.conflict", 1))
        assert dtext(e.store, u) == "Their text" and dver(e.store, u) == 1 and dec(e.store, u)["by"] == OTHER
        time.sleep(0.5)                                                  # nothing is resent behind the box
        assert dtext(e.store, u) == "Their text" and dver(e.store, u) == 1

        if choice == "theirs":
            box_.locator(".doc-take-theirs").click()
            wait_value(e.page, u, "Their text")
            expect(box_).to_be_hidden()
            expect(bar(e.page)).to_have_attribute("data-state", "saved")
            time.sleep(0.5)
            assert dtext(e.store, u) == "Their text" and dver(e.store, u) == 1
        else:
            box_.locator(".doc-keep-mine").click()
            wait_text(e.store, u, "My text")
            assert dver(e.store, u) == 2 and dec(e.store, u)["by"] == H.REVIEWER
            expect(box_).to_be_hidden()
            expect(bar(e.page)).to_have_attribute("data-state", "saved")
            assert field_value(e.page, u) == "My text"


def test_undo_never_overwrites_a_newer_version_saved_by_someone_else(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        edit(e.page, u, "Mine eins")
        wait_text(e.store, u, "Mine eins")
        e.page.keyboard.press("Escape")
        assert other_write(e.store, u, "Their newer text", 1) == 2
        e.page.locator("#doc-undo").click()
        li = blk(e.page, u)
        expect(li.locator(".doc-conflict")).to_be_visible()
        expect(li.locator(".doc-conflict")).to_contain_text(conflict_text(OTHER, "Their newer text"))
        expect(bar(e.page)).to_have_attribute("data-state", "conflict")
        time.sleep(0.5)
        assert dtext(e.store, u) == "Their newer text" and dver(e.store, u) == 2


@pytest.mark.parametrize("choice", ["theirs", "mine"])
@pytest.mark.parametrize("step", ["undo", "redo"])
def test_undo_after_a_reload_never_overwrites_a_newer_version(browser, step, choice):
    """The undo stacks live in the browser's storage and outlive a reload: after one, the text can stand at
    somebody else's version. Undo / Redo is then NOT written; it is held as a conflict (keep mine writes the
    step on top of their version, take theirs drops it). Nothing reaches the server before the reviewer chooses."""
    (u,) = pick(_stage_data(), 1)
    mine = "Mine eins"
    with doc(browser, seed=lambda env: other_write(env.store, u, "Basis", 0)) as e:
        edit(e.page, u, mine)
        wait_text(e.store, u, mine)
        wait_ver(e.store, u, 2)
        typed = dec(e.store, u)["record"]
        e.page.keyboard.press("Escape")                                   # ends the typing step: it is on the stack
        until(lambda: u in (e.page.evaluate("() => localStorage.getItem('cel-doc-undo')") or ""),
              what="the undo step to be kept in the browser's storage")
        if step == "redo":
            e.page.locator("#doc-undo").click()                           # saved: back to "Basis", the step waits for Redo
            wait_text(e.store, u, "Basis")
            wait_ver(e.store, u, 3)
            expect(e.page.locator("#doc-redo")).to_be_enabled()
        base = dver(e.store, u)
        theirs = other_write(e.store, u, "Their newer text", base)         # somebody else, behind the page's back
        assert theirs == base + 1

        e.page.reload()                                                    # the stacks stay in localStorage
        e.page.wait_for_selector(READY)
        wait_value(e.page, u, "Their newer text")
        button = e.page.locator("#doc-undo" if step == "undo" else "#doc-redo")
        expect(button).to_be_enabled()
        button.click()

        li = blk(e.page, u)
        box_ = li.locator(".doc-conflict")
        expect(box_).to_be_visible()
        expect(box_).to_contain_text(conflict_text(OTHER, "Their newer text"))
        expect(box_.locator(".doc-keep-mine")).to_have_text(C.t("doc.conflict.mine"))
        expect(box_.locator(".doc-take-theirs")).to_have_text(C.t("doc.conflict.theirs"))
        expect(li).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_contain_text(C.tn("autosave.conflict", 1))
        time.sleep(0.6)                                                    # nothing is written behind the box
        assert dtext(e.store, u) == "Their newer text" and dver(e.store, u) == theirs
        assert dec(e.store, u)["by"] == OTHER

        if choice == "theirs":
            box_.locator(".doc-take-theirs").click()
            expect(box_).to_be_hidden()
            wait_value(e.page, u, "Their newer text")
            expect(bar(e.page)).to_have_attribute("data-state", "saved")
            time.sleep(0.6)
            assert dtext(e.store, u) == "Their newer text" and dver(e.store, u) == theirs
        else:
            box_.locator(".doc-keep-mine").click()                         # the step goes on top of their version
            wait_ver(e.store, u, theirs + 1)
            want = {"text": "Basis"} if step == "undo" else typed
            assert dec(e.store, u)["record"] == want
            assert dec(e.store, u)["by"] == H.REVIEWER
            expect(box_).to_be_hidden()
            expect(bar(e.page)).to_have_attribute("data-state", "saved")
            wait_value(e.page, u, want["text"])


def test_a_conflict_is_still_there_after_a_reload(browser):
    """The Worker reported a conflict and the page is closed (or reloaded) before the reviewer chooses: the
    edit stays kept, the box shows again with what the other editor saved, and nothing is sent over it."""
    (u,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        other_write(e.store, u, "Their text", 0)                           # saved first, behind the page's back
        edit(e.page, u, "My text")
        li = blk(e.page, u)
        expect(li.locator(".doc-conflict")).to_be_visible()
        expect(li).to_have_attribute("data-state", "conflict")
        sent = e.worker.calls.count("desk-write")

        e.page.reload()
        e.page.wait_for_selector(READY)
        box_ = li.locator(".doc-conflict")
        expect(box_).to_be_visible()
        expect(box_).to_contain_text(conflict_text(OTHER, "Their text"))
        expect(box_.locator(".doc-keep-mine")).to_have_text(C.t("doc.conflict.mine"))
        expect(box_.locator(".doc-take-theirs")).to_have_text(C.t("doc.conflict.theirs"))
        expect(li).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_have_attribute("data-state", "conflict")
        expect(bar(e.page)).to_have_text(C.tn("autosave.conflict", 1))
        assert field_value(e.page, u) == "My text"                         # the edit is kept, not lost
        time.sleep(0.8)                                                    # nothing is sent over their version
        assert dtext(e.store, u) == "Their text" and dver(e.store, u) == 1
        assert e.worker.calls.count("desk-write") == sent, "the page sent a write over the conflict"

        box_.locator(".doc-keep-mine").click()
        wait_text(e.store, u, "My text")
        assert dver(e.store, u) == 2 and dec(e.store, u)["by"] == H.REVIEWER
        expect(box_).to_be_hidden()
        expect(bar(e.page)).to_have_attribute("data-state", "saved")


def test_undo_while_the_write_is_in_flight_ends_with_page_and_store_equal(browser):
    """Undo pressed while the text's write is still on its way: the write lands (version 1), then the undone
    state is sent on top of it (version 2). The page and the server end equal, never the page on the draft
    with the server holding the typed text."""
    (u,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, u, DA)) as e:
        e.worker.desk_fault = {"delay": 1.5}                               # a slow storage: the answer is held back
        edit(e.page, u, "Mine eins")
        li = blk(e.page, u)
        expect(li).to_have_attribute("data-state", "saving")               # the write is in flight
        assert dec(e.store, u) is None
        e.page.locator("#doc-undo").click()
        e.worker.desk_fault = None                                         # the second write is not held back
        wait_value(e.page, u, DA)

        wait_ver(e.store, u, 2, timeout=10.0)                              # 'Mine eins' landed, then the undo on top
        assert dec(e.store, u)["record"] == {}, dec(e.store, u)["record"]
        assert dtext(e.store, u) is None
        assert [h["version"] for h in e.store.history if h["unit"] == u] == [1, 2]
        assert field_value(e.page, u) == DA
        e.page.wait_for_function("""uid => ['idle', 'saved'].includes(
            document.querySelector('li.doc-block[data-uid="' + uid + '"]').dataset.state)""", arg=u, timeout=5000)
        expect(li).to_have_attribute("data-source", "draft")
        expect(bar(e.page)).to_have_attribute("data-state", "saved")
        expect(bar(e.page)).to_have_text(C.t("autosave.saved"))
        assert json.loads(e.page.evaluate("() => localStorage.getItem('cel-doc-pending')") or "{}") == {}
        # what a fresh page reads from the server is what this page shows
        e.page.reload()
        e.page.wait_for_selector(READY)
        assert field_value(e.page, u) == DA
        assert blk(e.page, u).get_attribute("data-source") == "draft"


def test_a_text_someone_else_cleared_says_they_undid_it(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        other_write(e.store, u, "Their text", 0)
        other_write(e.store, u, None, 1)                                  # they undid it: no text left
        edit(e.page, u, "My text")
        expect(blk(e.page, u).locator(".doc-conflict")).to_contain_text(C.t("doc.conflict.gone"))
        assert dtext(e.store, u) is None and dver(e.store, u) == 2


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 10. the outline
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _scroll_target(e, entries) -> tuple[int, str]:
    """An outline entry (not "Search result") whose first block can really be scrolled to the top."""
    geo = e.page.evaluate("""ids => {
        const max = document.documentElement.scrollHeight - innerHeight;
        return ids.map(id => document.querySelector('li.doc-block[data-uid="' + id + '"]')
            .getBoundingClientRect().top + scrollY).map(t => [t, max]); }""", [s["target"] for s in entries[1:]])
    ok = [i + 1 for i, (top, mx) in enumerate(geo) if top > 900 and top <= mx - 10]
    assert ok, "no heading on the page is far enough from the top and the end to be scrolled to"
    i = ok[0]
    return i, entries[i]["target"]


def _settle_at_top(page, uid):
    page.wait_for_selector(f'.doc-outline-item[data-target="{uid}"][aria-current="true"], '
                           f'#doc-sections', state="attached")
    page.wait_for_function("""uid => { const r = document.querySelector('li.doc-block[data-uid="' + uid + '"]')
        .getBoundingClientRect(); return r.top > -2 && r.top < 200; }""", arg=uid, timeout=8000)
    time.sleep(0.4)                                    # a smooth scroll may still be arriving
    return page.evaluate("""uid => document.querySelector('li.doc-block[data-uid="' + uid + '"]')
        .getBoundingClientRect().top""", uid)


def test_the_outline_lists_search_result_and_every_section_with_its_counts(browser):
    want = sections(_stage_data())
    assert len(want) >= 2, "the page has no block with a section (`sec`)"
    with doc(browser) as e:
        items = e.page.locator("#doc-outline-list .doc-outline-item")
        expect(items).to_have_count(len(want))
        for i, s in enumerate(want):
            item = items.nth(i)
            expect(item.locator(".doc-outline-name")).to_have_text(s["name"])
            expect(item.locator(".doc-outline-count")).to_have_text(
                C.tn("doc.outline.count", len(s["ids"]), edited=0))
        expect(e.page.locator("#doc-outline-title")).to_have_text(C.t("doc.outline.title"))
        assert e.page.locator('#doc-outline-list [aria-current="true"]').count() == 1


def test_editing_in_a_section_raises_that_entrys_edited_count_at_once(browser):
    data = _stage_data()
    by_id = {b["id"]: b for b in data["blocks"]}
    want = sections(data)
    k, uid = next((i, x) for i, s_ in enumerate(want) if i >= 1 for x in s_["ids"] if clean(by_id[x]))
    slow = dict(TIMING, quiet=4000, maxWait=8000)       # the server has not been written when the count moves
    with doc(browser, timing=slow) as e:
        items = e.page.locator("#doc-outline-list .doc-outline-item")
        n = len(want[k]["ids"])
        expect(items.nth(k).locator(".doc-outline-count")).to_have_text(C.tn("doc.outline.count", n, edited=0))
        edit(e.page, uid, "Neuer Text unter der Überschrift")
        expect(items.nth(k).locator(".doc-outline-count")).to_have_text(
            C.tn("doc.outline.count", n, edited=1), timeout=2000)
        assert dec(e.store, uid) is None, "the count waited for the server instead of moving at once"
        for i in range(len(want)):
            if i != k:
                expect(items.nth(i).locator(".doc-outline-count")).to_have_text(
                    C.tn("doc.outline.count", len(want[i]["ids"]), edited=0))


def test_clicking_an_outline_entry_scrolls_its_first_block_near_the_top_and_marks_it_current(browser):
    want = sections(_stage_data())
    with doc(browser) as e:
        i, target = _scroll_target(e, want)
        e.page.locator(f'.doc-outline-item[data-target="{target}"]').click()
        top = _settle_at_top(e.page, target)
        assert -2 <= top < 200, top
        current = e.page.locator('#doc-outline-list [aria-current="true"]')
        assert current.count() == 1
        assert current.get_attribute("data-target") == target
        assert e.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_on_a_phone_the_rail_gives_way_to_a_sections_select_that_works(browser):
    want = sections(_stage_data())
    with doc(browser, size=(375, 812)) as e:
        expect(e.page.locator("#doc-outline")).to_be_hidden()
        expect(e.page.locator("#doc-sections")).to_be_visible()
        opts = e.page.locator("#doc-sections option").all_inner_texts()
        assert [" ".join(o.split()) for o in opts] == [" ".join(s["name"].split()) for s in want]
        i, target = _scroll_target(e, want)
        e.page.select_option("#doc-sections", value=target)
        top = _settle_at_top(e.page, target)
        assert -2 <= top < 200, top


def test_at_1024_the_rail_is_hidden_and_the_sections_select_takes_over(browser):
    """Contract 7.4 says the rail is hidden at <= 1024 and also that the select shows only <= 767: the
    sentence in brackets (select visible from <= 1024) is taken, or a 768-1024 page has no way round."""
    with doc(browser, size=(1024, 800)) as e:
        expect(e.page.locator("#doc-outline")).to_be_hidden()
        expect(e.page.locator("#doc-sections")).to_be_visible()


@pytest.mark.parametrize("key", PAGES)
def test_the_outline_of_every_page_has_one_entry_per_section(browser, key):
    """CEL-031: the rail names every section the page's blocks carry in `sec` (a new entry where it changes),
    not only the h1/h2 headings: a page with 12 sections shows 12 entries after 'Search result' (13)."""
    data = _stage_data(key)
    names = section_names(data)
    assert names, "the page data has no section (`sec`) at all"
    first_blocks = [s["target"] for s in sections(data)]
    with doc(browser, key=key) as e:
        items = e.page.locator("#doc-outline-list .doc-outline-item")
        expect(items).to_have_count(1 + len(names))
        got = e.page.locator("#doc-outline-list .doc-outline-name").all_text_contents()
        assert [" ".join(g.split()) for g in got] == [" ".join(n.split())
                                                      for n in [C.t("doc.outline.search")] + names]
        targets = e.page.eval_on_selector_all("#doc-outline-list .doc-outline-item",
                                              "els => els.map(x => x.dataset.target)")
        assert targets == first_blocks, "an entry must lead to the FIRST block of its section"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 11. Translate page
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _ids(e, key=PAGE_KEY) -> list[str]:
    return next(p for p in e.pages["pages"] if p["key"] == key)["ids"]


def _start_from_banner(e):
    e.page.locator("#doc-banner-translate").click()
    expect(e.page.locator("#doc-confirm")).to_be_visible()
    e.page.locator("#doc-confirm-ok").click()


def _jobs(e, lang="fr"):
    return [j for j in e.store.jobs.values() if j["locale"] == lang and j["kind"] == "translate-page"]


def test_translate_page_asks_first_and_starts_one_job_for_the_page(browser):
    with doc(browser, lang="fr") as e:
        banner = e.page.locator("#doc-banner")
        expect(banner).to_be_visible()
        expect(e.page.locator("#doc-banner-text")).to_have_text(C.t("doc.banner.none", language=C.t("lang.fr")))
        go = e.page.locator("#doc-banner-translate")
        expect(go).to_be_visible()
        expect(go).to_have_text(C.t("doc.translate"))
        go.click()
        confirm = e.page.locator("#doc-confirm")
        expect(confirm).to_be_visible()
        expect(e.page.locator("#doc-confirm-title")).to_have_text(C.t("doc.confirm.title"))
        expect(e.page.locator("#doc-confirm-body")).to_have_text(
            C.tn("doc.confirm.body", len(_ids(e)), language=C.t("lang.fr")))
        expect(e.page.locator("#doc-confirm-cancel")).to_have_text(C.t("doc.confirm.cancel"))
        e.page.keyboard.press("Escape")                              # Esc cancels: nothing is sent
        expect(confirm).to_be_hidden()
        e.page.locator("#doc-banner-translate").click()
        e.page.locator("#doc-confirm-cancel").click()
        expect(confirm).to_be_hidden()
        time.sleep(0.3)
        assert "desk-job-start" not in e.worker.calls and not e.store.jobs

        e.page.locator("#doc-banner-translate").click()
        e.page.locator("#doc-confirm-ok").click()
        until(lambda: len(_jobs(e)) == 1, what="the translate-page job")
        (job,) = _jobs(e)
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "keepEdited": True}
        assert job["status"] in ("queued", "running") and job["requested_by"] == H.REVIEWER
        expect(e.page.locator("#doc-banner-text")).to_have_text(C.t("doc.job.queued"))
        expect(e.page.locator("#doc-banner-translate")).to_be_hidden()
        expect(e.page.locator("#doc-translate")).to_be_disabled()
        expect(confirm).to_be_hidden()


def test_the_header_button_translates_a_page_that_already_has_drafts(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, DA)) as e:
        expect(e.page.locator("#doc-banner")).to_be_hidden()
        e.page.locator("#doc-translate").click()
        expect(e.page.locator("#doc-confirm")).to_be_visible()
        e.page.locator("#doc-confirm-ok").click()
        until(lambda: len(_jobs(e, LANG)) == 1, what="the translate-page job")
        assert json.loads(_jobs(e, LANG)[0]["ref"]) == {"page": PAGE_KEY, "keepEdited": True}


def test_only_one_filled_primary_button_is_visible_while_the_banner_offers_translate(browser):
    """CEL-031: the banner's Translate page is `is-strong`, not `is-primary`: the only filled primary button
    on the page (at most one visible at a time) is Export."""
    with doc(browser, lang="fr") as e:
        go = e.page.locator("#doc-banner-translate")
        expect(go).to_be_visible()
        expect(go).not_to_have_class(re.compile(r"\bis-primary\b"))
        primary = e.page.evaluate("""() => [...document.querySelectorAll('.desk-btn.is-primary')]
            .filter(el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')
            .map(el => el.id || el.className)""")
        assert len(primary) <= 1, primary
        assert set(primary) <= {"doc-export"}, primary


def test_the_header_translate_button_hides_while_the_banners_shows_and_returns_with_a_translation(browser):
    """CEL-031: one Translate page at a time. While the page has no translation in the language the
    banner's button is the one on screen; once it has one (a draft) the banner goes and the header's is back."""
    (a,) = pick(_stage_data(), 1)
    with doc(browser, lang="fr") as e:
        expect(e.page.locator("#doc-banner-translate")).to_be_visible()
        expect(e.page.locator("#doc-translate")).to_be_hidden()
    with doc(browser, lang="fr", seed=lambda env: draft(env.store, a, "Brouillon", lang="fr")) as e:
        expect(e.page.locator("#doc-banner")).to_be_hidden()
        expect(e.page.locator("#doc-banner-translate")).to_be_hidden()
        expect(e.page.locator("#doc-translate")).to_be_visible()


def test_a_finished_translation_clears_the_banner_and_shows_the_drafts(browser):
    with doc(browser, lang="fr") as e:
        _start_from_banner(e)
        until(lambda: len(_jobs(e)) == 1, what="the job")
        status = maybe_t("doc.status.translating")
        c = cell(e.page, PAGE_KEY, "fr")
        expect(c).to_have_attribute("data-status", "translating")
        if status:
            expect(c.locator(".doc-cell-status")).to_have_text(status)
        mine = _ids(e)[:3]
        for i, uid in enumerate(mine):
            draft(e.store, uid, f"Brouillon {i}", lang="fr")
        e.store.finish_job("fr", "translate-page", "done", {"drafts": 3})
        expect(e.page.locator("#doc-banner")).to_be_hidden()
        expect(e.page.locator("#doc-toasts")).to_contain_text(C.t("doc.job.done"))
        expect(c).to_have_attribute("data-status", "drafted")
        expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.drafted"))
        expect(c.locator(".doc-cell-count")).to_have_text(C.tn("doc.cell.count", 3, total=len(_ids(e))))
        for i, uid in enumerate(mine):
            wait_value(e.page, uid, f"Brouillon {i}")
            assert blk(e.page, uid).get_attribute("data-source") == "draft"


def test_every_page_asked_while_a_job_runs_waits_in_line_in_order(browser):
    """The Worker allows one open translate-page job per language. A page asked while one runs waits, and so
    does a third: the grid shows every one as queued, and each starts by itself when the one before it ends,
    in the order asked (the first page, then the second, then the third)."""
    first, second, third = PAGE_KEY, "vancouver", "vs-toronto"
    with doc(browser, lang="fr", http_errors=True) as e:         # the Worker's 409 is how the queue starts
        _start_from_banner(e)
        until(lambda: len(_jobs(e)) == 1, what="the first job")
        for key in (second, third):
            open_cell(e.page, key, "fr")
            _start_from_banner(e)
            expect(cell(e.page, key, "fr")).to_have_attribute("data-status", "queued")
        # the third did not replace the second: both wait, behind the first, which runs
        for key, status in ((first, "translating"), (second, "queued"), (third, "queued")):
            expect(cell(e.page, key, "fr")).to_have_attribute("data-status", status)
        queued = maybe_t("doc.status.queued")
        if queued:
            for key in (second, third):
                expect(cell(e.page, key, "fr").locator(".doc-cell-status")).to_have_text(queued)
        assert cell(e.page, "how-long-to-learn-english", "fr").get_attribute("data-status") == "none"
        time.sleep(0.5)
        assert len(_jobs(e)) == 1, "a waiting page created a second job"

        e.store.finish_job("fr", "translate-page", "done", {"drafts": 0})      # the first ends: the second starts
        until(lambda: len(_jobs(e)) == 2, 8, what="the second page's job to start by itself")
        expect(cell(e.page, second, "fr")).to_have_attribute("data-status", "translating")
        expect(cell(e.page, third, "fr")).to_have_attribute("data-status", "queued")
        assert cell(e.page, first, "fr").get_attribute("data-status") != "translating"
        time.sleep(0.5)
        assert len(_jobs(e)) == 2, "the third page started before the second ended"

        e.store.finish_job("fr", "translate-page", "failed", None, error="engine-stopped")   # a failed one frees the line too
        until(lambda: len(_jobs(e)) == 3, 8, what="the third page's job to start by itself")
        expect(cell(e.page, third, "fr")).to_have_attribute("data-status", "translating")
        assert cell(e.page, second, "fr").get_attribute("data-status") != "queued"
        order = [json.loads(j["ref"])["page"] for j in sorted(_jobs(e), key=lambda j: j["created_at"])]
        assert order == [first, second, third], order

        e.store.finish_job("fr", "translate-page", "done", {"drafts": 0})
        e.page.wait_for_function(
            "document.querySelectorAll('.doc-cell[data-status=\"translating\"], .doc-cell[data-status=\"queued\"]')"
            ".length === 0", timeout=8000)


@pytest.mark.parametrize("code,reason_key", [("engine-stopped", "job.failed.engine-stopped"),
                                             ("a-code-nobody-knows", "doc.job.failed.unknown")])
def test_a_failed_translation_says_why(browser, code, reason_key):
    with doc(browser, lang="fr") as e:
        _start_from_banner(e)
        until(lambda: len(_jobs(e)) == 1, what="the job")
        e.store.finish_job("fr", "translate-page", "failed", None, error=code)
        expect(e.page.locator("#doc-banner")).to_be_visible()
        expect(e.page.locator("#doc-banner-text")).to_have_text(
            C.t("doc.job.failed", reason=C.t(reason_key)))
        expect(e.page.locator("#doc-translate")).to_be_enabled()
        assert cell(e.page, PAGE_KEY, "fr").get_attribute("data-status") == "none"


@pytest.mark.parametrize("outcome", ["done", "failed"])
def test_a_second_page_waits_in_line_and_starts_by_itself_when_the_first_ends(browser, outcome):
    with doc(browser, lang="fr", http_errors=True) as e:         # the Worker's 409 is how the queue starts
        _start_from_banner(e)
        until(lambda: len(_jobs(e)) == 1, what="the first job")
        open_cell(e.page, "vancouver", "fr")
        # the first page is translating, the grid says so; nothing else changed
        assert cell(e.page, PAGE_KEY, "fr").get_attribute("data-status") == "translating"
        assert cell(e.page, "vancouver", "fr").get_attribute("data-status") == "none"
        _start_from_banner(e)                                           # Translate page for vancouver
        waiting = maybe_t("doc.job.waiting", page=C.t(f"page.{PAGE_KEY}"), language=C.t("lang.fr"))
        expect(e.page.locator("#doc-banner")).to_be_visible()
        if waiting:
            expect(e.page.locator("#doc-banner-text")).to_have_text(waiting)
        else:
            expect(e.page.locator("#doc-banner-text")).not_to_have_text(C.t("doc.job.queued"))
        expect(e.page.locator("#doc-banner-text")).not_to_have_text(C.t("doc.banner.none", language=C.t("lang.fr")))
        c_van = cell(e.page, "vancouver", "fr")
        expect(c_van).to_have_attribute("data-status", "queued")        # it waits behind the first
        queued = maybe_t("doc.status.queued")
        if queued:
            expect(c_van.locator(".doc-cell-status")).to_have_text(queued)
        expect(cell(e.page, PAGE_KEY, "fr")).to_have_attribute("data-status", "translating")
        assert cell(e.page, "vs-toronto", "fr").get_attribute("data-status") == "none"
        time.sleep(0.5)
        assert len(_jobs(e)) == 1, "the confirm click created a second job"
        assert "desk-job-start" in e.worker.calls

        if outcome == "done":
            e.store.finish_job("fr", "translate-page", "done", {"drafts": 0})
        else:
            e.store.finish_job("fr", "translate-page", "failed", None, error="engine-stopped")
        until(lambda: len(_jobs(e)) == 2, 8, what="the second job to start by itself")
        first, second = sorted(_jobs(e), key=lambda j: j["created_at"])
        assert first["status"] == outcome and json.loads(first["ref"])["page"] == PAGE_KEY
        assert json.loads(second["ref"]) == {"page": "vancouver", "keepEdited": True}
        assert second["status"] in ("queued", "running")
        expect(e.page.locator("#doc-banner-text")).to_have_text(C.t("doc.job.queued"))
        expect(c_van).to_have_attribute("data-status", "translating")    # it runs now: no longer waiting
        assert cell(e.page, PAGE_KEY, "fr").get_attribute("data-status") != "translating"
        # when that one ends, nothing in the grid is translating or queued any more
        e.store.finish_job("fr", "translate-page", "done", {"drafts": 0})
        e.page.wait_for_function(
            "document.querySelectorAll('.doc-cell[data-status=\"translating\"], .doc-cell[data-status=\"queued\"]')"
            ".length === 0", timeout=8000)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 12. layout
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_an_h3_text_is_set_like_an_h2_and_bigger_than_an_h4(browser):
    """CEL-031: the page's section titles are h3 blocks; they use the h2 rule (size and weight), while h4 and
    smaller keep the body-plus-one size. Read from the computed style of the English column."""
    data = _stage_data()
    kinds = {b["b"] for b in data["blocks"]}
    assert {"h2", "h3"} <= kinds, "the page has no h2 and h3 block to compare"
    smaller = "h4" if "h4" in kinds else "p"
    with doc(browser) as e:
        def look(kind):
            return e.page.evaluate("""k => { const el = document.querySelector(
                    'li.doc-block[data-b="' + k + '"] .doc-en');
                if (!el) return null;
                const s = getComputedStyle(el); return [parseFloat(s.fontSize), s.fontWeight]; }""", kind)
        h2, h3, other = look("h2"), look("h3"), look(smaller)
        assert h2 and h3 and other, (h2, h3, other)
        assert h3 == h2, f"an h3 must look like an h2: h3 {h3}, h2 {h2}"
        assert h3[0] > other[0], f"an h3 must be bigger than {smaller}: h3 {h3}, {smaller} {other}"


def test_layout_at_1440_two_columns_then_three_with_the_rail_and_the_status_bar(browser):
    (a,) = pick(_stage_data(), 1, need_w=True)
    with doc(browser) as e:
        li = blk(e.page, a)
        li.scroll_into_view_if_needed()
        en, tg = box(li.locator(".doc-en")), box(li.locator(".doc-tgt"))
        assert tg["x"] >= en["x"] + en["width"] - 1, (en, tg)            # the translation is right of English
        assert tg["y"] < en["y"] + en["height"] and en["y"] < tg["y"] + tg["height"], (en, tg)   # side by side
        expect(e.page.locator("#doc-outline")).to_be_visible()
        expect(e.page.locator("#doc-sections")).to_be_hidden()
        status = e.page.locator("#doc-status")
        expect(status).to_be_visible()
        sb = box(status)
        vh = e.page.evaluate("() => innerHeight")
        assert abs(sb["y"] + sb["height"] - vh) <= 1.5, (sb, vh)          # stuck to the bottom edge
        # the sheet's head row sits over its columns: each head spans the cell below it
        heads = {k: box(e.page.locator(f".doc-head-{k}")) for k in ("en", "tgt")}
        for k, cellbox in (("en", en), ("tgt", tg)):
            hb = heads[k]
            assert hb["x"] <= cellbox["x"] + 1 and cellbox["x"] + cellbox["width"] <= hb["x"] + hb["width"] + 1, (k, hb, cellbox)
        assert heads["en"]["x"] + heads["en"]["width"] <= heads["tgt"]["x"] + 1

        e.page.locator("#doc-weglot").check()
        li.scroll_into_view_if_needed()
        en, tg, wg = (box(li.locator(s)) for s in (".doc-en", ".doc-tgt", ".doc-weglot"))
        assert en["x"] < tg["x"] < wg["x"], (en, tg, wg)
        assert tg["x"] >= en["x"] + en["width"] - 1 and wg["x"] >= tg["x"] + tg["width"] - 1
        assert min(en["width"], tg["width"], wg["width"]) > 150
        for sel in (".doc-en", ".doc-tgt", ".doc-weglot"):             # and nothing is painted over a column
            assert on_top(li.locator(sel)), f"{sel} is covered by something else"


OVERFLOW_JS = """root => {
    const W = innerWidth, out = [];
    function clipped(e) {
        for (let a = e.parentElement; a && a !== root.parentElement; a = a.parentElement)
            if (getComputedStyle(a).overflowX !== 'visible') return true;
        return false;
    }
    root.querySelectorAll('*').forEach(e => {
        const r = e.getBoundingClientRect();
        if (!r.width || getComputedStyle(e).position === 'fixed' || clipped(e)) return;
        if (r.right > W + 1 || r.left < -1) out.push([e.tagName + '.' + String(e.className).slice(0, 40), Math.round(r.left), Math.round(r.right)]);
    });
    return out.slice(0, 8);
}"""


@pytest.mark.parametrize("width", [375, 320])
def test_on_a_phone_the_columns_stack_and_nothing_of_the_page_sticks_out(browser, width):
    (a,) = pick(_stage_data(), 1, need_w=True)
    with doc(browser, size=(width, 800)) as e:
        e.page.locator("#doc-weglot").check()
        li = blk(e.page, a)
        li.scroll_into_view_if_needed()
        en, tg, wg = (box(li.locator(s)) for s in (".doc-en", ".doc-tgt", ".doc-weglot"))
        assert en["y"] + en["height"] <= tg["y"] + 1, (en, tg)            # English above the translation
        assert tg["y"] + tg["height"] <= wg["y"] + 1, (tg, wg)            # and that above Weglot
        expect(e.page.locator(".doc-heads")).to_be_hidden()
        assert box(li)["x"] >= 0 and box(li)["x"] + box(li)["width"] <= width + 1
        # everything the document page itself draws (the grid scrolls inside its own box) fits the width
        assert e.page.eval_on_selector("#doc", OVERFLOW_JS) == []
        e.page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        assert e.page.eval_on_selector("#doc", OVERFLOW_JS) == []


@pytest.mark.parametrize("width", [375, 320])
def test_the_whole_page_does_not_scroll_sideways_on_a_phone(browser, width):
    with doc(browser, size=(width, 800)) as e:
        assert e.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")


def test_the_status_bar_never_covers_the_text_that_has_focus(browser):
    with doc(browser) as e:
        pad = e.page.evaluate("() => parseFloat(getComputedStyle(document.documentElement).scrollPaddingBottom)")
        sb = box(e.page.locator("#doc-status"))
        assert pad >= sb["height"], f"scroll-padding-bottom {pad} is under the status bar's {sb['height']}"
        first = pick(e.data, 1)[0]
        tgt(e.page, first).focus()
        for i in range(45):
            e.page.keyboard.press("Tab")
            r = e.page.evaluate("""() => {
                const a = document.activeElement, b = document.getElementById('doc-status').getBoundingClientRect();
                const r = a.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + Math.min(r.width / 2, 40), r.top + Math.min(r.height / 2, 10));
                return {inBar: !!a.closest('#doc-status'), isText: a.classList.contains('doc-tgt'),
                        bottom: r.bottom, top: r.top, barTop: b.top, covered: !!hit && !a.contains(hit) && !hit.contains(a),
                        what: a.tagName + '.' + a.className}; }""")
            if r["inBar"]:
                break
            # a short control is wholly above the bar; a tall (several-line) text at least shows its first
            # line, where the caret is -- the browser decides how much of a long text to scroll in
            shown = r["top"] + min(r["bottom"] - r["top"], 28) if r["isText"] else r["bottom"]
            assert shown <= r["barTop"] + 1, (i, r)
            if r["isText"]:
                assert r["top"] >= 0 and not r["covered"], (i, r)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 13. failures
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_a_failing_server_keeps_the_text_retries_and_try_again_saves_it(browser):
    (u,) = pick(_stage_data(), 1)
    text = "Text während der Störung"
    with doc(browser, http_errors=True) as e:
        e.worker.desk_fault = {"status": 503, "error": "down"}
        edit(e.page, u, text)
        expect(bar(e.page)).to_have_attribute("data-state", "retrying")
        expect(bar(e.page)).to_contain_text(C.tn("autosave.retrying", 1, reason=C.t("save.reason.unavailable")))
        retry = e.page.locator("#doc-save-retry")
        expect(retry).to_have_text(C.t("autosave.retry"))
        li = blk(e.page, u)
        expect(li).to_have_attribute("data-state", "error")                # the per-text error state
        expect(li.locator(".doc-note")).to_contain_text(C.t("doc.text.error"))
        assert dec(e.store, u) is None
        assert text in (e.page.evaluate("() => localStorage.getItem('cel-doc-pending')") or "")   # kept here
        e.worker.desk_fault = None
        retry.click()
        wait_text(e.store, u, text)
        expect(bar(e.page)).to_have_attribute("data-state", "saved")
        expect(li).to_have_attribute("data-state", "saved")
        expect(li.locator(".doc-note")).to_contain_text(C.t("doc.text.saved"))


def test_after_the_fault_clears_the_text_saves_by_itself(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, http_errors=True) as e:
        e.worker.desk_fault = {"status": 502, "error": "bad gateway"}
        edit(e.page, u, "Text ohne Knopf")
        li = blk(e.page, u)
        expect(li).to_have_attribute("data-state", "error")
        e.worker.desk_fault = None
        wait_text(e.store, u, "Text ohne Knopf", timeout=8.0)               # the 2 s retry
        expect(li).to_have_attribute("data-state", "saved")


@pytest.mark.parametrize("status,error,reason", [(401, "signed out", "signed_out"),
                                                 (429, "over the cap", "cap"),
                                                 (429, "over the daily limit", "daily")])
def test_a_stopped_save_says_why_and_try_again_goes_on(browser, status, error, reason):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, http_errors=True) as e:
        e.worker.desk_fault = {"status": status, "error": error}
        edit(e.page, u, "Text vor dem Halt")
        expect(bar(e.page)).to_have_attribute("data-state", "stopped")
        expect(bar(e.page)).to_contain_text(C.t("autosave.stopped", reason=C.t(f"save.reason.{reason}")))
        assert dec(e.store, u) is None
        e.worker.desk_fault = None
        e.page.locator("#doc-save-retry").click()
        wait_text(e.store, u, "Text vor dem Halt")
        expect(bar(e.page)).to_have_attribute("data-state", "saved")


def test_unsent_changes_go_out_when_the_page_is_opened_again(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, http_errors=True) as e:
        e.worker.desk_fault = {"status": 503, "error": "down"}
        edit(e.page, u, "Text über den Neustart")
        expect(bar(e.page)).to_have_attribute("data-state", "retrying")
        e.worker.desk_fault = None
        e.page.reload()
        e.page.wait_for_selector(READY)
        wait_text(e.store, u, "Text über den Neustart")
        wait_value(e.page, u, "Text über den Neustart")


def test_typing_without_a_pause_is_saved_after_the_max_wait(browser):
    (u,) = pick(_stage_data(), 1)
    slow = {"quiet": 5000, "maxWait": 700, "undoPause": 120, "poll": 200, "timeout": 5000}
    text = "Dauernd tippen ohne Pause"
    with doc(browser, timing=slow) as e:
        tgt(e.page, u).click()
        e.page.keyboard.press("ControlOrMeta+a")
        started = time.monotonic()
        first_seen = None
        for i, ch in enumerate(text):
            e.page.keyboard.type(ch)
            time.sleep(0.15)
            if first_seen is None and dtext(e.store, u):
                first_seen = (i, time.monotonic() - started)
        assert first_seen is not None, "nothing reached the server while typing"
        assert first_seen[0] < len(text) - 1, first_seen                     # before the typing stopped
        assert first_seen[1] < 2.0, first_seen
        assert text.startswith(dtext(e.store, u)) or dtext(e.store, u) in text


def test_a_big_backlog_is_sent_fifty_at_a_time(browser):
    """120 unsent edits are in the browser's storage before the page loads (an earlier visit that could not
    save): every desk-write carries at most 50 changes, and all 120 reach the server."""
    pages = _stage_json("pages")
    backlog, seen = {}, set()
    for p in pages["pages"]:
        for uid in p["ids"]:
            if uid not in seen and len(backlog) < 120:
                seen.add(uid)
                backlog[uid] = {"record": {"text": f"Text {len(backlog)}"}, "base": 0, "page": p["key"]}
    assert len(backlog) == 120
    init = "localStorage.setItem('cel-doc-pending', " + json.dumps(json.dumps({LANG: backlog})) + ");"
    sizes: list[int] = []

    def seed(env):
        original = env.store.handle

        def spy(action, body, email):
            if action == "desk-write":
                sizes.append(len(body["changes"]))
            return original(action, body, email)

        env.store.handle = spy

    with doc(browser, seed=seed, init=(init,)) as e:
        have = lambda: sum(1 for k in e.store.decisions if k[0] == LANG)   # noqa: E731
        until(lambda: have() == 120, 20.0, what=f"all 120 texts to reach the server (now {have()})")
        assert max(sizes) <= 50 and sum(sizes) == 120 and len(sizes) >= 3, sizes
        for uid, rec in backlog.items():
            assert dtext(e.store, uid) == rec["record"]["text"], uid
        expect(bar(e.page)).to_have_attribute("data-state", "saved", timeout=8000)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# the grid, once more: Exported falls back to Edited and comes back only with a newer export
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_an_exported_page_turns_edited_at_once_and_exported_again_only_after_a_newer_export(browser):
    d1, d2 = pick(_stage_data(), 2)

    def seed(env):
        for uid in (d1, d2):
            draft(env.store, uid, "Entwurf " + uid)
            env.store.pipeline[(LANG, uid)] = {"exportedAt": "2026-10-18T12:00:00.000Z"}

    slow = dict(TIMING, quiet=3000, maxWait=6000)
    with doc(browser, seed=seed, timing=slow) as e:
        c = cell(e.page, PAGE_KEY, LANG)
        expect(c).to_have_attribute("data-status", "exported")
        expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.exported"))
        edit(e.page, d1, "Neu bearbeitet")
        expect(c).to_have_attribute("data-status", "edited", timeout=1500)         # no reload, no save yet
        assert dec(e.store, d1) is None
        expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.edited"))
        wait_text(e.store, d1, "Neu bearbeitet", timeout=8.0)
        expect(c).to_have_attribute("data-status", "edited")                       # saved: still not exported

        e.page.reload()                                                            # the old export is older than it
        e.page.wait_for_selector(READY)
        wait_cells_known(e.page)
        expect(cell(e.page, PAGE_KEY, LANG)).to_have_attribute("data-status", "edited")

        decided = dec(e.store, d1)["at"]
        e.store.pipeline[(LANG, d1)] = {"exportedAt": iso_after(decided, 5)}      # a new export, after the decision
        e.page.reload()
        e.page.wait_for_selector(READY)
        wait_cells_known(e.page)
        expect(cell(e.page, PAGE_KEY, LANG)).to_have_attribute("data-status", "exported")
