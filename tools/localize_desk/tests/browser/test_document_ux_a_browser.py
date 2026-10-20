"""Robot click-tests for the desk and export UX fixes A of the sweep (CEL-075): one test per item.

Expected wording comes from COPY.md through `copy_text.t` / `tn`, never typed here (the two words a test pins on purpose are
named in it). Every test also asserts the page raised no error and logged none to the console, through `doc()`.

The harness helpers are COPIED from test_document_browser.py (the convention of this folder: no imports between test files).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
OTHER = "other@example.test"
READY = '#doc[data-state="ready"]'
# Autosave in ~0.2 s instead of 2 s / 10 s; the poll for a running job every 0.2 s.
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')


# ── the harness, copied from test_document_browser.py ─────────────────────────────────────────────
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


def plain(text: str) -> str:
    return MARK.sub("", text or "")


def conflict_text(who: str, text: str) -> str:
    """`doc.conflict.text` filled by hand: copy_text.t() cannot take a placeholder named `text`."""
    return C.load()["doc.conflict.text"].replace("{who}", who).replace("{text}", text)


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


def _now(page):
    """CEL-069: the open page (the tree row marked current) and the open language (the selected tab)."""
    return page.evaluate("""() => [(document.querySelector('.doc-tree-page[aria-current="page"]') || {dataset: {}}).dataset.page || null,
        (document.querySelector('.doc-tab[aria-selected="true"]') || {dataset: {}}).dataset.lang || null]""")


def cell(page, key, lang):
    """CEL-069 (the grid's cell before): where the shell shows (page, language) -- the tree row while `lang` is the
    open language, the language tab while `key` is the open page; neither: the tab is clicked first (the page
    stays). Either carries data-status, the status word (.doc-st-word) and the count in its data-tip."""
    cur_page, cur_lang = _now(page)
    if lang == cur_lang:
        return page.locator(f'.doc-tree-page[data-page="{key}"]')
    if key == cur_page:
        return page.locator(f'#doc-tab-{lang}')
    page.locator(f'#doc-tab-{lang}').click()
    page.wait_for_function("""l => document.querySelector('#doc').dataset.state === 'ready'
        && document.querySelector('.doc-tab[aria-selected="true"]').dataset.lang === l""", arg=lang, timeout=20000)
    return page.locator(f'.doc-tree-page[data-page="{key}"]')


def expect_count(c, text):
    """The count the grid's cell printed is the end of the row's / tab's hover text now (empty: no count)."""
    if text:
        expect(c).to_have_attribute("data-tip", re.compile(re.escape(" · " + text) + "$"))
    else:
        expect(c).not_to_have_attribute("data-tip", re.compile(r" · \d+ of \d+"))


def wait_cells_known(page):
    """CEL-069: every tree row and every language tab knows its status."""
    page.wait_for_function("document.querySelectorAll('.doc-tree-page').length > 0 && document.querySelectorAll("
                           "'.doc-tree-page[data-status=\"unknown\"], .doc-tab[data-status=\"unknown\"], .doc-tab:not([data-status])').length === 0",
                           timeout=15000)


def bar(page):
    return page.locator("#doc-save")



# ── copied from test_document_export_browser.py ──
def make_csv(lang: str, key: str) -> str:
    """A stand-in for the engine's import file: CRLF rows, a comma and a line break inside quotes, non-ASCII."""
    word = {"de": "Übersetzung ü ß – schön", "fr": "Traduction é à ç «oui»", "ja": "翻訳 日本語"}.get(lang, lang)
    return ("Original,Translation\r\n"
            f'"Hello, {key}","{word}"\r\n'
            f'"Two\nlines","{word}\nzwei"\r\n')


def result_of(batch: str, rows: int, refused=(), warned=()) -> dict:
    return {"batchId": batch, "rows": rows, "refused": list(refused), "warned": list(warned),
            "notes": [], "skipped": {}}


def engine_done(store, lang: str, key: str, csv: str, rows: int, *, refused=(), warned=(), stamp=(),
                created_at: str | None = None) -> str:
    """The engine finishing the open export job of a language: the file is in `exports`, the texts it put in
    the file are stamped as exported, and the job is `done` with the result the page reads."""
    batch = f"b-{lang}-{key}"
    store.seed_export(batch, lang, csv, rows, list(refused), created_at)
    for uid in stamp:
        store.pipeline[(lang, uid)] = {"exportedAt": iso_after(store.decisions[(lang, uid)]["at"], 5)}
    store.finish_job(lang, "export", "done", result_of(batch, rows, refused, warned))
    return batch


def iso_after(iso: str, seconds: int) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def open_export(page):
    page.locator("#doc-export").click()
    expect(page.locator("#ex-modal")).to_be_visible()


def ex_box(page, key, lang):
    return page.locator(f'#ex-grid input[data-page="{key}"][data-lang="{lang}"]')


def ex_file(page, key, lang):
    return page.locator(f'li.ex-file[data-page="{key}"][data-lang="{lang}"]')


def group(page, kind):
    return page.locator(f'#ex-result .ex-group[data-kind="{kind}"]')


def item(page, kind, uid, key=None, lang=None):
    sel = f'li.ex-item[data-uid="{uid}"]'
    if key:
        sel += f'[data-page="{key}"]'
    if lang:
        sel += f'[data-lang="{lang}"]'
    return group(page, kind).locator(sel)


def put(store, uid, record, *, lang=LANG, page=PAGE_KEY, base=0, email=H.REVIEWER):
    """A decision written straight into the stand-in (before the page loads, or behind its back)."""
    code, body = store.handle("desk-write", {
        "locale": lang, "client": 1,
        "changes": [{"unit": uid, "page": page, "base": base, "record": record}]}, email)
    assert code == 200 and body["applied"], body
    return body["applied"][0]["version"]



# ── copied from test_document_browser.py ──
def _start_from_banner(e):
    e.page.locator("#doc-banner-translate").click()
    expect(e.page.locator("#doc-confirm")).to_be_visible()
    e.page.locator("#doc-confirm-ok").click()


def _jobs(e, lang="fr"):
    return [j for j in e.store.jobs.values() if j["locale"] == lang and j["kind"] == "translate-page"]


def _edit_served_block(env, uid, **fields):
    """Change a block in the page data the harness serves, before the page (re)loads: another build of the page."""
    f = env.root / "admin" / "localization" / "document" / "data" / f"{env.key}.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    block = next(b for b in data["blocks"] if b["id"] == uid)
    for k, v in fields.items():
        if isinstance(v, dict):
            block.setdefault(k, {}).update(v)
        else:
            block[k] = v
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")



# ── copied from test_document_browser.py ──
def open_cell(page, key, lang):
    """CEL-069: the language tab, then the page's row in the tree (each keeps the other)."""
    cur_page, cur_lang = _now(page)
    if lang != cur_lang:
        page.locator(f'#doc-tab-{lang}').click()
    if key != cur_page:
        page.locator(f'.doc-tree-page[data-page="{key}"]').click()
    page.wait_for_function(
        """([k, l]) => document.querySelector('#doc').dataset.state === 'ready'
            && !!document.querySelector('.doc-tree-page[aria-current="page"]')
            && document.querySelector('.doc-tree-page[aria-current="page"]').dataset.page === k
            && document.querySelector('.doc-tab[aria-selected="true"]').dataset.lang === l""",
        arg=[key, lang], timeout=20000)


# ── the tests ─────────────────────────────────────────────────────────────────────────────────────


# 1. 'Take theirs' no longer drops the reviewer's wording for good (the sweep's only data-loss item)
def test_item_1_take_theirs_is_one_undo_step_that_gives_the_reviewers_wording_back(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        other_write(e.store, u, "Their text", 0)                      # somebody else, behind the page's back
        edit(e.page, u, "My text")
        li = blk(e.page, u)
        expect(li.locator(".doc-conflict")).to_be_visible()
        li.locator(".doc-take-theirs").click()
        wait_value(e.page, u, "Their text")
        expect(li.locator(".doc-conflict")).to_be_hidden()
        assert dtext(e.store, u) == "Their text" and dver(e.store, u) == 1
        e.page.locator("#doc-undo").click()                           # the step 'Take theirs' pushed
        wait_value(e.page, u, "My text")                              # the reviewer's wording is back ...
        wait_text(e.store, u, "My text")                              # ... and saved, on top of theirs
        assert dver(e.store, u) == 2 and dec(e.store, u)["by"] == H.REVIEWER
        expect(li.locator(".doc-conflict")).to_be_hidden()
        expect(e.page.locator("#doc-redo")).to_be_enabled()           # and Redo goes back to theirs


# 2. Export no longer approves unread Gemini drafts without saying so
def test_item_2_the_export_window_counts_the_edits_and_the_unread_gemini_drafts_that_go_in(browser):
    u_edit, u_seen, u_new1, u_new2 = pick(_stage_data(), 4)
    seen = "localStorage.setItem('cel-doc-seen', JSON.stringify({" + json.dumps(f"{LANG}|{u_seen}") + ": 1}))"

    def seed(env):
        other_write(env.store, u_edit, "Edited wording", 0)                # a text with the reviewer's wording
        for u in (u_seen, u_new1, u_new2):
            draft(env.store, u, "Gemini draft " + u[-4:])                  # three drafts, one of them looked at

    with doc(browser, seed=seed, init=(seen,)) as e:
        e.page.locator("#doc-export").click()
        expect(e.page.locator("#ex-modal")).to_be_visible()
        line = e.page.locator("#ex-drafts")
        expect(line).to_be_visible()
        expect(line).to_have_text(C.tn("export.drafts", 2, edited=1))       # 1 edited, 2 unread drafts; the looked-at one is not counted
        ex_box(e.page, PAGE_KEY, LANG).uncheck()                        # no cell picked: nothing to say
        expect(line).to_be_hidden()
        ex_box(e.page, PAGE_KEY, LANG).check()
        expect(line).to_have_text(C.tn("export.drafts", 2, edited=1))


# ── 3 and 21: a finished export ───────────────────────────────────────────────────────────────────────
def export_one_page(e, uid):
    """Drive one real export of the open page in the open language to its result view (the stand-in engine makes the file)."""
    p = e.page
    open_export(p)
    p.locator("#ex-go").click()
    li = ex_file(p, PAGE_KEY, LANG)
    expect(li).to_have_attribute("data-state", "queued", timeout=10000)
    e.store.finish_job(LANG, "export", "running")
    with p.expect_download():
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 1, stamp=[uid])
    expect(li).to_have_attribute("data-state", "done")
    expect(p.locator("#ex-result")).to_be_visible()


# 3. 'Exported' says what it is: in a Weglot file, not on the website; the result says how to import it
def test_item_3_a_finished_export_says_how_to_import_it_and_the_grid_says_in_a_weglot_file(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, u, "Entwurf eins")) as e:
        export_one_page(e, u)
        p = e.page
        steps = p.locator("#ex-result .ex-how")
        expect(steps).to_have_count(1)
        expect(steps.locator("p.ex-how-title")).to_have_text(C.t("export.how.title"))
        expect(steps.locator("ol li")).to_have_text([C.t(k) for k in (
            "export.how.upload", "export.how.check", "export.how.switches", "export.how.press")])
        expect(steps.locator("p.ex-how-note")).to_have_text(C.t("export.how.errors"))
        assert p.evaluate("() => document.querySelector('#ex-result').firstElementChild.className") == "ex-how"
        p.locator("#ex-close").click()
        status = cell(p, PAGE_KEY, LANG).locator(".doc-st-word")
        expect(cell(p, PAGE_KEY, LANG)).to_have_attribute("data-status", "exported")
        expect(status).to_have_text("In a Weglot file")                  # the words of the fix, pinned on purpose
        assert C.t("doc.status.exported") == "In a Weglot file"


# 21. 'Show' no longer stands for five things: the button beside a left-out text goes to the text
def test_item_21_the_button_beside_a_left_out_text_reads_go_to_text(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, u, "Entwurf eins")) as e:
        export_one_page(e, u)
        jump = e.page.locator("#ex-result button.ex-jump").first
        expect(jump).to_be_visible()
        expect(jump).to_have_text("Go to text")                          # the words of the fix, pinned on purpose
        assert C.t("export.jump") == "Go to text"
        # and the other Show rows keep their own meaning
        assert C.t("export.more", n=3) == "Show 3 more" and C.t("doc.filter.label") == "Show"


# 6. an error or a warning stays until the reviewer closes it; a plain message still goes by itself
def test_item_6_an_error_stays_until_closed_and_a_plain_message_goes_after_four_seconds(browser):
    plain_msg, err_msg, warn_msg = C.t("doc.history.restored"), C.t("doc.job.error"), C.t("retr.busy")
    with doc(browser) as e:
        p = e.page
        p.evaluate("""([a, b, c]) => { DocDesk.toast(a); DocDesk.toast(b, 'err'); DocDesk.toast(c, 'warn'); }""",
                   [plain_msg, err_msg, warn_msg])
        toasts = p.locator("#doc-toasts .toast")
        expect(toasts).to_have_count(3)
        err, warn = toasts.filter(has_text=err_msg), toasts.filter(has_text=warn_msg)
        expect(toasts.filter(has_text=plain_msg).locator("button")).to_have_count(0)    # a plain message has no Close
        expect(err.locator("button.toast-close")).to_have_text(C.t("toast.close"))
        p.wait_for_timeout(4600)                                                         # past the 4 s a message used to last
        expect(toasts.filter(has_text=plain_msg)).to_have_count(0)
        expect(err).to_have_count(1)
        expect(warn).to_have_count(1)
        err.locator("button.toast-close").click()
        expect(err).to_have_count(0)
        expect(warn).to_have_count(1)                                                    # closing one leaves the other


# 11. a greyed-out button says why
def tip_of(page, loc):
    """Hover (pointer) `loc` and return the desk tooltip's text."""
    loc.hover()
    tip = page.locator(".desk-tip")
    expect(tip).to_be_visible()
    return tip.inner_text()


def test_item_11_a_greyed_translate_button_and_a_greyed_export_box_and_button_say_why(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, u, "Entwurf")) as e:
        p = e.page
        # the Translate button while this page is being translated
        p.locator("#doc-translate").click()
        p.locator("#rp-go").click()
        until(lambda: any(j["kind"] == "translate-page" for j in e.store.jobs.values()), what="the translate-page job")
        expect(p.locator("#doc-translate")).to_be_disabled()
        assert tip_of(p, p.locator("#doc-translate")) == C.t("doc.job.queued")
        # the Export window: a box with nothing behind it, and the Export button with nothing picked
        open_export(p)
        grey = p.locator('#ex-grid input[data-lang="fr"]').first
        expect(grey).to_be_disabled()
        assert tip_of(p, grey) == C.t("export.step.nothing")
        ex_box(p, PAGE_KEY, LANG).uncheck()
        expect(p.locator("#ex-go")).to_be_disabled()
        assert tip_of(p, p.locator("#ex-go")) == C.t("export.count.none")
        ex_box(p, PAGE_KEY, LANG).check()
        expect(p.locator("#ex-go")).to_be_enabled()
        assert p.locator("#ex-go").get_attribute("data-tip") is None             # the reason goes when the button is on


# 14. the toolbar is there on hover, not only on focus, and its revert button says what it does
def test_item_14_the_toolbar_shows_on_hover_and_the_revert_button_goes_back_to_geminis_draft(browser):
    (u,) = pick(_stage_data(), 1)

    def seed(env):
        draft(env.store, u, "Entwurf")
        other_write(env.store, u, "Bearbeitet", 0)                    # an edit: the revert button belongs to it

    with doc(browser, seed=seed) as e:
        p = e.page
        li = blk(p, u)
        tools = li.locator(".doc-tools")
        li.scroll_into_view_if_needed()
        p.mouse.move(2, 2)                                            # the pointer is nowhere near, nothing has focus
        expect(tools).to_be_hidden()
        li.locator(".doc-en").hover()                                 # hover, no click: no focus in the block
        expect(tools).to_be_visible()
        assert p.evaluate("() => document.activeElement === document.body")
        revert = tools.locator(".doc-tool-revert")
        expect(revert).to_be_visible()
        expect(revert).to_have_text("Back to Gemini's draft")         # the words of the fix, pinned on purpose
        assert C.t("doc.tool.revert") == "Back to Gemini's draft"
        p.mouse.move(2, 2)
        expect(tools).to_be_hidden()                                  # and it goes when the pointer leaves
        tgt(p, u).focus()                                             # focus still shows it, as before
        p.mouse.move(2, 2)
        expect(tools).to_be_visible()
        revert.click()                                                # the button does what it says: Gemini's draft is back
        wait_value(p, u, "Entwurf")


# 15. "Weglot" means one thing: the website's text is called that, not Weglot
def test_item_15_the_website_s_text_is_not_called_weglot(browser):
    (u,) = pick(_stage_data(), 1, need_w=True)
    with doc(browser) as e:
        p = e.page
        toggle = p.locator("label.doc-switch")                          # CEL-069: the path row's switch (same checkbox)
        expect(toggle).to_have_text("Show the website's text")           # the words of the fix, pinned on purpose
        toggle.locator("input").check()
        expect(p.locator(".doc-head-weglot")).to_have_text("The website's text")
        tgt(p, u).focus()
        tool = blk(p, u).locator(".doc-tool-weglot")
        expect(tool).to_be_visible()
        expect(tool).to_have_text("Use the website's text")
        for key in ("doc.weglot.toggle", "doc.head.weglot", "doc.tool.weglot"):
            assert "Weglot" not in C.t(key), key
    # COPY.md's "Shown where" cells follow the rename (Reviewer round 1, fix 5): nothing names the old toggle
    raw = (Path(C.__file__).parent / "COPY.md").read_text(encoding="utf-8")
    assert "Show Weglot" not in raw and "Use Weglot's text" not in raw


# 16. one name for each thing: the terms table, and no desk label that still uses another word
def test_item_16_gemini_s_wording_has_one_name_and_the_terms_table_says_so(browser):
    (u,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, u, "Entwurf eins")) as e:
        p = e.page
        wait_cells_known(p)
        expect(cell(p, PAGE_KEY, LANG).locator(".doc-st-word")).to_have_text("Gemini's draft")
        expect(p.locator("#doc-filter option[value=new]")).to_have_text("Gemini's draft")
        expect(p.locator(".doc-head-tgt")).to_have_text(f"{C.t('lang.' + LANG)} — Gemini's draft and your edits")
    words = C.load()
    for old in ("Drafted", "New from Gemini"):
        assert not [k for k, v in words.items() if old in v], (old, [k for k, v in words.items() if old in v])
    table = (Path(C.__file__).parent / "COPY.md").read_text(encoding="utf-8")
    for row in ("| What Gemini wrote for a text | **Gemini's draft** |", "| A text you changed yourself | **edited** |",
                "| The other reviewer's saved wording in a conflict | **theirs** |",
                "| The saved earlier wordings of a text | **History** |",
                "| Texts that are in the Weglot file but not on the website yet | **in a Weglot file** |"):
        assert row in table, row


# 18. a locked text says Locked and the reason is a tip; nothing repeats the save status under a text; the count has a target
def test_item_18_locked_has_a_tip_nothing_repeats_the_save_status_and_the_count_has_a_target(browser):
    (u, v) = pick(_stage_data(), 2)
    titles = [b["id"] for b in _stage_data()["blocks"] if b["b"] == "meta-title"]
    descs = [b["id"] for b in _stage_data()["blocks"] if b["b"] == "meta-description"]
    assert titles and descs

    def seed(env):
        _edit_served_block(env, v, lock="noise")

    with doc(browser, seed=seed, http_errors=True) as e:
        p = e.page
        lock = blk(p, v).locator(".doc-note-lock")
        expect(lock).to_have_text("Locked")                                           # the word, pinned on purpose
        expect(lock).to_have_attribute("data-tip", C.t("doc.locked.noise"))          # the reason is the tip
        lock.scroll_into_view_if_needed()                                            # a scroll hides the tip: settle first
        p.wait_for_timeout(300)
        lock.hover()
        expect(p.locator(".desk-tip")).to_have_text(C.t("doc.locked.noise"))
        # a text that is edited and saved has no line under it (the status bar says it)
        edit(p, u, "Ein Text")
        wait_text(e.store, u, "Ein Text")
        expect(blk(p, u)).to_have_attribute("data-state", "saved")
        expect(bar(p)).to_have_attribute("data-state", "saved")
        assert blk(p, u).locator(".doc-note").inner_text().strip() == ""              # read at once: 'saved' lasts 3 s, a retrying expect would outlast it
        # ... until a save does not go through: that line shows
        e.worker.desk_fault = {"status": 503, "error": "down"}
        edit(p, u, "Ein Text, nicht gespeichert")
        expect(blk(p, u)).to_have_attribute("data-state", "error")
        expect(blk(p, u).locator(".doc-note")).to_have_text(C.t("doc.text.error"), use_inner_text=True)
        e.worker.desk_fault = None
        # the count says how long the page title and description should be
        edit(p, titles[0], "x" * 10)
        expect(blk(p, titles[0]).locator(".doc-note-chars")).to_have_text("10 of 60")
        edit(p, descs[0], "y" * 25)
        expect(blk(p, descs[0]).locator(".doc-note-chars")).to_have_text("25 of 160")


# 20. a page whose translation failed reads Failed in the grid, not Not translated
def test_item_20_a_failed_translation_reads_failed_in_the_grid(browser):
    with doc(browser, lang="fr") as e:
        p = e.page
        expect(cell(p, PAGE_KEY, "fr")).to_have_attribute("data-status", "none")
        expect(cell(p, PAGE_KEY, "fr").locator(".doc-st-word")).to_have_text(C.t("doc.status.none"))
        _start_from_banner(e)
        until(lambda: len(_jobs(e)) == 1, what="the job")
        e.store.finish_job("fr", "translate-page", "failed", None, error="engine-stopped")
        open_cell(p, "vancouver", "fr")                                           # away from the failed page: the grid still says so
        expect(cell(p, PAGE_KEY, "fr")).to_have_attribute("data-status", "failed")
        expect(cell(p, PAGE_KEY, "fr").locator(".doc-st-word")).to_have_text("Failed")      # the word of the fix, pinned on purpose
        assert C.t("doc.status.failed") == "Failed"
        expect(cell(p, "vancouver", "fr")).to_have_attribute("data-status", "none")   # another page is not Failed
        # the Export window treats a Failed page as it treats a Not translated one: nothing to export, greyed, with its reason
        open_export(p)
        for key in (PAGE_KEY, "vancouver"):
            box_ = ex_box(p, key, "fr")
            expect(box_).to_be_disabled()
            assert box_.get_attribute("data-tip") == C.t("export.step.nothing"), key


def test_item_3_a_zip_of_several_files_says_to_unzip_it_and_import_each_file(browser):
    """Reviewer round 1, fix 2: two picked cells make ONE zip; the steps may not tell the reviewer to upload "the file"."""
    (u,) = pick(_stage_data(), 1)

    def seed(env):
        draft(env.store, u, "Entwurf de")
        draft(env.store, u, "Entwurf fr", lang="fr")

    with doc(browser, seed=seed) as e:
        p = e.page
        open_export(p)
        ex_box(p, PAGE_KEY, "fr").check()
        p.locator("#ex-go").click()
        for lang, last in (("de", False), ("fr", True)):
            li = ex_file(p, PAGE_KEY, lang)
            expect(li).to_have_attribute("data-state", "queued", timeout=10000)
            e.store.finish_job(lang, "export", "running")
            if last:
                with p.expect_download() as dl:
                    engine_done(e.store, lang, PAGE_KEY, make_csv(lang, PAGE_KEY), 1, stamp=[u])
                assert dl.value.suggested_filename.endswith(".zip")
            else:
                engine_done(e.store, lang, PAGE_KEY, make_csv(lang, PAGE_KEY), 1, stamp=[u])
        steps = p.locator("#ex-result .ex-how ol li")
        expect(steps).to_have_text([C.t(k) for k in ("export.how.unzip", "export.how.upload", "export.how.check",
                                                    "export.how.switches", "export.how.press")])
        assert "zip" in C.t("export.how.unzip") and "each file" in C.t("export.how.unzip")
