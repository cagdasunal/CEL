"""Robot click-tests for the Export window and the Re-translate windows of the document page (desk v2, CEL-027).

A real Chromium drives `/admin/localization/document/` in the click-test harness: a temporary copy of docs/
with saving switched on, the storage's stand-in behind a mock Worker (`harness.MockWorker`, whose `store` is
a `DeskStore`). A test plays ANOTHER editor, or the ENGINE, by calling `store.handle(...)`,
`store.finish_job(...)`, `store.seed_export(...)` and by writing `store.drafts` / `store.pipeline` itself.
Every storage action the page makes is recorded by a small spy around `store.handle` (`Spy`), so a test can
read what was written, in what chunks, and in what order.

The contract is runtime/out/loc2/CEL-027/contract.md. What this file holds the page to:
  * the buttons and the toolbar button, the Export window's grid (only the open page x language ticked, the
    row / column / all boxes with their in-between state, the count, Export off with nothing ticked, Cancel,
    Escape, focus back on the button, Tab kept inside);
  * ONE page x ONE language end to end: the decisions written (exactly the texts that have an edit or a
    draft, `tray: csv`, `approvedAgainst`), the job, the file lines going waiting -> saving -> queued ->
    running -> done, the download with the exact bytes, the result view's groups and a working Show;
  * several files -> ONE zip, strictly one job at a time, page by page (pages in page order, then languages);
    a failed job, nothing to export (no job), a stale file (410); writes in chunks of 50 ([50, 50, 20] for 120);
    a text someone else saved meanwhile is never overwritten; an edit the autosave refused (or that is a
    conflict) is listed (`unsaved` / `conflict`) and never holds the export up; a group of more than 50 shows
    50 and one "Show N more" button;
  * the menu and the footer of every page are in no write, no list and no job (Ruling 21:01);
  * Re-translate a text (the job's ref, the note on ONE line, the new draft, Undo and Redo, busy, failed, nothing
    arrived) and a page (the engine's `translate-page` job; Include my edits).

Expected wording comes from COPY.md through `copy_text.t` / `tn`, never typed here. Autosave and the job poll
run in about 0.2 s because every page gets `window.DOC_TIMING` before it loads. Every test also asserts the
page raised no error and logged none to the console, through `doc()`.

The harness helpers are COPIED from test_document_browser.py (the convention of this folder: no imports
between test files).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
import zipfile
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
# The box that ticks everything. The contract names it `input#ex-all`; it is found by its place (first row,
# not a column box) so the rest of the toggle checks still run -- `test_the_all_box_is_input_ex_all` holds the id.
ALL = "#ex-grid tbody tr:not([data-page]) input:not([data-col])"
ZIP_NAME = re.compile(r"^weglot-export-\d{8}-\d{4}\.zip$")
ORDER = ["waiting", "saving", "queued", "running", "done"]
OBSERVE_JS = """(() => {
  window.__ex = [];
  new MutationObserver(rs => rs.forEach(r => {
    if (r.target.classList && r.target.classList.contains('ex-file') && r.oldValue)
      window.__ex.push([r.target.dataset.page, r.target.dataset.lang, r.oldValue]);
  })).observe(document, {subtree: true, attributes: true, attributeOldValue: true, attributeFilter: ['data-state']});
})();"""


# ── the harness, copied from test_document_browser.py ──────────────────────────────────────────────
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
    """The document page open and ready, with a `DOC_TIMING` that makes autosave and the job poll quick.

    `seed(env)` runs before the page loads (put drafts, decisions, pipeline stamps in `env.store`).
    On a normal exit it asserts no page error and no console error happened (scenario 14); an HTTP
    failure the test asked for (`http_errors`: the Worker's 409 / 410) and a missing favicon are not errors."""
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


# ── small helpers (copied) ─────────────────────────────────────────────────────────────────────────
def plain(text: str) -> str:
    return MARK.sub("", text or "")


def squash(text: str) -> str:
    return " ".join((text or "").split())


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


def put(store, uid, record, *, lang=LANG, page=PAGE_KEY, base=0, email=H.REVIEWER):
    """A decision written straight into the stand-in (before the page loads, or behind its back)."""
    code, body = store.handle("desk-write", {
        "locale": lang, "client": 1,
        "changes": [{"unit": uid, "page": page, "base": base, "record": record}]}, email)
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


def cell(page, key, lang):
    return page.locator(f'.doc-cell[data-page="{key}"][data-lang="{lang}"]')


def wait_open(page, key, lang):
    page.wait_for_function(
        """([k, l]) => document.querySelector('#doc').dataset.state === 'ready'
            && !!document.querySelector('.doc-cell[aria-pressed="true"]')
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.page === k
            && document.querySelector('.doc-cell[aria-pressed="true"]').dataset.lang === l""",
        arg=[key, lang], timeout=20000)


def open_cell(page, key, lang):
    cell(page, key, lang).click()
    wait_open(page, key, lang)


def iso_after(iso: str, seconds: int) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def ids_unique_to(pages: dict, key: str) -> list[str]:
    others = set()
    for p in pages["pages"]:
        if p["key"] != key:
            others |= set(p["ids"])
    mine = next(p for p in pages["pages"] if p["key"] == key)["ids"]
    return [i for i in mine if i not in others]


def on_screen(loc) -> bool:
    """Any part of the element is inside the viewport."""
    return loc.evaluate("""el => { const r = el.getBoundingClientRect();
        return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; }""")


# ── what this file adds ────────────────────────────────────────────────────────────────────────────
class Spy:
    """Every storage action that reaches the stand-in, in order: what the PAGE sends (email = the test
    reviewer) and, with `mark()`, the moments the test itself did something (the engine finishing a job)."""

    def __init__(self):
        self.log: list[dict] = []
        self.raw = None

    def attach(self, store):
        self.raw = store.handle

        def spy(action, body, email):
            code, out = self.raw(action, body, email)
            self.log.append({"action": action, "body": body, "email": email, "code": code, "out": out})
            return code, out

        store.handle = spy

    def calls(self, action: str, email: str = H.REVIEWER, code: int | None = None) -> list[dict]:
        return [c for c in self.log if c["action"] == action and c["email"] == email
                and (code is None or c["code"] == code)]

    def mark(self, name: str):
        self.log.append({"action": "mark", "name": name, "email": None, "body": {}, "code": 0, "out": {}})

    def at(self, action: str, email: str = H.REVIEWER) -> list[int]:
        return [i for i, c in enumerate(self.log) if c["action"] == action and c["email"] == email]


def against(b: dict, lang: str = LANG) -> str:
    """The wording an approval is given against: Weglot's, else the English."""
    return (b.get("w") or {}).get(lang) or b["en"]


def blocks_of(key: str = PAGE_KEY) -> list[dict]:
    return _stage_data(key)["blocks"]


def early(key: str, lang: str, n: int, *, skip=()) -> list[dict]:
    """Plain texts with Weglot wording near the top of the page, in document order."""
    out = [b for b in blocks_of(key) if clean(b, lang, True) and b["id"] not in skip][:n]
    assert len(out) == n, f"{key}: too few plain texts with a {lang} translation"
    return out


def far(key: str, lang: str, *, after: int = 120, skip=()) -> dict:
    """A plain text well below the first screen (so Show has to scroll to it)."""
    for i, b in enumerate(blocks_of(key)):
        if i > after and clean(b, lang, True) and b["id"] not in skip:
            return b
    raise AssertionError(f"{key}: no plain text with a {lang} translation after block {after}")


@lru_cache(maxsize=None)
def chrome_units(key: str) -> tuple:
    """The menu and footer texts of a page as the staged units file marks them (`"chrome": true`): (id, English)
    pairs. They are in no page JSON, so the document can never show them; the storage stand-in knows them
    (it is built from the same units files), so a write for one would be accepted."""
    doc_ = json.loads((H.UNITS_DIR / f"{key}.json").read_text(encoding="utf-8"))
    return tuple((u["unit_id"], u["word_from"]) for u in doc_["units"] if u.get("chrome"))


def snip(en: str) -> str:
    """A text as the result lists show it (document_export.js `snippet`): tags dropped, white space
    collapsed, cut to 80 characters."""
    s = " ".join(re.sub(r"<[^>]*>", "", en or "").split())
    return s if len(s) <= 80 else s[:79] + "…"


def make_csv(lang: str, key: str) -> str:
    """A stand-in for the engine's import file: CRLF rows, a comma and a line break inside quotes, non-ASCII."""
    word = {"de": "Übersetzung ü ß – schön", "fr": "Traduction é à ç «oui»", "ja": "翻訳 日本語"}.get(lang, lang)
    return ("Original,Translation\r\n"
            f'"Hello, {key}","{word}"\r\n'
            f'"Two\nlines","{word}\nzwei"\r\n')


def open_job(store, lang: str, page: str | None = None, kind: str = "export"):
    for j in list(store.jobs.values()):
        if j["locale"] == lang and j["kind"] == kind and j["status"] in ("queued", "running"):
            if page is None or (json.loads(j["ref"] or "null") or {}).get("page") == page:
                return j
    return None


def jobs_of(store, kind: str, lang: str = LANG) -> list[dict]:
    return [j for j in store.jobs.values() if j["locale"] == lang and j["kind"] == kind]


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


def open_export(page):
    page.locator("#doc-export").click()
    expect(page.locator("#ex-modal")).to_be_visible()


def ex_box(page, key, lang):
    return page.locator(f'#ex-grid input[data-page="{key}"][data-lang="{lang}"]')


def ex_file(page, key, lang):
    return page.locator(f'li.ex-file[data-page="{key}"][data-lang="{lang}"]')


def ticked(page) -> set:
    return set(map(tuple, page.eval_on_selector_all(
        "#ex-grid input[data-page][data-lang]:checked", "els => els.map(e => [e.dataset.page, e.dataset.lang])")))


def select_cells(page, wanted):
    """Make the ticked set exactly `wanted` (pairs of (page, language)) with real clicks."""
    wanted = set(wanted)
    have = ticked(page)
    for key, lang in sorted(have - wanted):
        ex_box(page, key, lang).uncheck()
    for key, lang in sorted(wanted - have):
        ex_box(page, key, lang).check()
    assert ticked(page) == wanted


def tri(page, sel):
    """(checked, indeterminate) of one box."""
    return tuple(page.eval_on_selector(sel, "e => [e.checked, e.indeterminate]"))


def group(page, kind):
    return page.locator(f'#ex-result .ex-group[data-kind="{kind}"]')


def item(page, kind, uid, key=None, lang=None):
    sel = f'li.ex-item[data-uid="{uid}"]'
    if key:
        sel += f'[data-page="{key}"]'
    if lang:
        sel += f'[data-lang="{lang}"]'
    return group(page, kind).locator(sel)


def ex_states(page, key, lang) -> list[str]:
    """The states one file line went through (collapsed): the old values the observer saw, then the current."""
    seen = page.evaluate("""([k, l]) => {
        const old = (window.__ex || []).filter(x => x[0] === k && x[1] === l).map(x => x[2]);
        const el = document.querySelector('li.ex-file[data-page="' + k + '"][data-lang="' + l + '"]');
        return old.concat(el ? [el.dataset.state] : []); }""", [key, lang])
    out: list[str] = []
    for s in seen:
        if not out or out[-1] != s:
            out.append(s)
    return out


def is_subsequence(want, seen) -> bool:
    it = iter(seen)
    return all(any(s == w for s in it) for w in want)


def start_export(page, cells):
    """Open the window, tick exactly `cells`, press Export."""
    open_export(page)
    select_cells(page, cells)
    page.locator("#ex-go").click()


def serve_file(e, spy, key, lang, step, *, k, later=(), hold=0.45):
    """Play the engine for the k-th file that gets a job (0-based): wait for ITS job, check that no other
    file's job has started and that the files after it still wait, then finish it as `step` says."""
    until(lambda: open_job(e.store, lang, key), 10.0, what=f"the export job {k + 1} ({key} / {lang}) to start")
    assert len(spy.calls("desk-job-start")) == k + 1, \
        f"{len(spy.calls('desk-job-start'))} jobs were started when job {k + 1} began: not one at a time"
    for later_key, later_lang in later:
        assert ex_file(e.page, later_key, later_lang).get_attribute("data-state") == "waiting", (later_key, later_lang)
    time.sleep(hold)                                       # a second job must not start while this one is open
    assert len(spy.calls("desk-job-start")) == k + 1, "a second job started while the first one was still open"
    spy.mark(f"finish-{k}")
    if step[0] == "failed":
        e.store.finish_job(lang, "export", "failed", None, error=step[1])
    else:
        _, csv, rows, refused, stamp = step
        engine_done(e.store, lang, key, csv, rows, refused=refused, stamp=stamp)


def assert_one_job_at_a_time(spy):
    starts = spy.at("desk-job-start")
    marks = {c["name"]: i for i, c in enumerate(spy.log) if c["action"] == "mark"}
    for k in range(1, len(starts)):
        assert marks[f"finish-{k - 1}"] < starts[k], f"job {k + 1} started before job {k} was finished"


def read_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        assert zf.testzip() is None
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, f"{info.filename} is not stored"
        return {i.filename: zf.read(i.filename) for i in zf.infolist()}


def toasts(page):
    return page.locator("#doc-toasts")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. the buttons and the Export window's grid
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_two_page_buttons_sit_in_the_action_bar_in_their_places(browser):
    with doc(browser) as e:
        ids = e.page.eval_on_selector("#doc-bar .doc-actions", "el => [...el.children].map(c => c.id)")
        assert "doc-retranslate-page" in ids and "doc-translate" in ids and "doc-export" in ids, ids
        assert ids.index("doc-retranslate-page") + 1 == ids.index("doc-translate"), ids   # right BEFORE Translate page
        assert ids[-1] == "doc-export", ids                                               # and Export is last
        rp, ex = e.page.locator("#doc-retranslate-page"), e.page.locator("#doc-export")
        expect(rp).to_have_text(C.t("retr.page.button"))
        expect(ex).to_have_text(C.t("export.button"))
        expect(rp).to_have_class(re.compile(r"\bdesk-btn\b"))
        expect(ex).to_have_class(re.compile(r"\bdesk-btn\b"))
        expect(ex).to_have_class(re.compile(r"\bis-primary\b"))
        expect(ex).to_be_enabled()
        expect(e.page.locator("#ex-modal")).to_be_hidden()
        expect(e.page.locator("#rt-modal")).to_be_hidden()
        expect(e.page.locator("#rp-modal")).to_be_hidden()


def test_every_text_has_a_retranslate_button_first_in_its_toolbar_also_on_the_next_page(browser):
    with doc(browser) as e:
        n = len(e.data["blocks"])
        assert e.page.locator(".doc-tools .doc-tool-retranslate").count() == n
        firsts = e.page.eval_on_selector_all(
            "li.doc-block .doc-tools",
            "els => els.filter(t => t.firstElementChild && t.firstElementChild.classList.contains('doc-tool-retranslate')).length")
        assert firsts == n, "the Re-translate button is not first in every toolbar"
        (a,) = pick(e.data, 1)
        btn = blk(e.page, a).locator(".doc-tool-retranslate")
        tgt(e.page, a).click()                                  # the toolbar floats up while focus is in the text
        expect(btn).to_be_visible()
        expect(btn).to_have_text(C.t("retr.button"))
        expect(btn).to_have_class(re.compile(r"\bdesk-btn\b"))
        open_cell(e.page, "vancouver", "fr")                     # the texts are built again for another page
        van = _stage_data("vancouver")["blocks"]
        assert e.page.locator(".doc-tools .doc-tool-retranslate").count() == len(van)
        (v,) = pick(_stage_data("vancouver"), 1, lang="fr")
        tgt(e.page, v).click()
        expect(blk(e.page, v).locator(".doc-tool-retranslate")).to_be_visible()


def test_the_export_window_opens_with_only_the_open_page_and_language_ticked(browser):
    with doc(browser, seed=lambda env: seed_cells(env, ALL_CELLS)) as e:        # CEL-037: no cell is greyed
        p = e.page
        modal = p.locator("#ex-modal")
        expect(modal).to_be_hidden()
        expect(modal).to_have_class(re.compile(r"\bcpw-overlay\b"))
        open_export(p)
        dlg = modal.locator(".cpw-modal")
        expect(dlg).to_have_attribute("role", "dialog")
        expect(dlg).to_have_attribute("aria-modal", "true")
        expect(dlg).to_have_attribute("aria-labelledby", "ex-title")
        expect(p.locator("#ex-title")).to_have_text(C.t("export.title"))
        expect(p.locator("#ex-title")).to_have_class(re.compile(r"\bcpw-title\b"))
        # the grid: eight languages across, four pages down, the "all pages" row first
        assert p.eval_on_selector_all("#ex-grid th[data-lang]", "els => els.map(x => x.dataset.lang)") == LANGS
        assert p.eval_on_selector_all("#ex-grid tr[data-page]", "els => els.map(x => x.dataset.page)") == PAGES
        assert p.eval_on_selector_all("#ex-grid input[data-col]", "els => els.map(x => x.dataset.col)") == LANGS
        assert p.eval_on_selector_all("#ex-grid input[data-row]", "els => els.map(x => x.dataset.row)") == PAGES
        assert p.locator("#ex-grid input[data-page][data-lang]").count() == 32
        for lang in LANGS:                                    # the flag and the CODE in capitals; the name is the aria-label
            th = p.locator(f'#ex-grid th[data-lang="{lang}"]')
            expect(th).to_contain_text(lang.upper())
            expect(th).to_have_attribute("aria-label", C.t(f"lang.{lang}"))
        for key in PAGES:
            expect(p.locator(f'#ex-grid tr[data-page="{key}"]')).to_contain_text(C.t(f"page.{key}"))
        grid = p.locator("#ex-grid")
        for key in ("export.grid.page", "export.all.pages", "export.all.languages"):
            expect(grid).to_contain_text(C.t(key))
        # every box has a name a screen reader can say
        expect(p.locator(ALL)).to_have_attribute("aria-label", C.t("export.aria.all"))
        for lang in LANGS:
            expect(p.locator(f'#ex-grid input[data-col="{lang}"]')).to_have_attribute(
                "aria-label", C.t("export.aria.col", language=C.t(f"lang.{lang}")))
        for key in PAGES:
            expect(p.locator(f'#ex-grid input[data-row="{key}"]')).to_have_attribute(
                "aria-label", C.t("export.aria.row", page=C.t(f"page.{key}")))
            for lang in LANGS:
                expect(ex_box(p, key, lang)).to_have_attribute(
                    "aria-label", C.t("export.aria.cell", page=C.t(f"page.{key}"), language=C.t(f"lang.{lang}")))
        # only the open page in the open language is ticked; the count says one file
        assert ticked(p) == {(PAGE_KEY, LANG)}
        count = p.locator("#ex-count")
        expect(count).to_have_attribute("aria-live", "polite")
        expect(count).to_have_text(C.tn("export.count", 1))
        expect(p.locator("#ex-go")).to_be_enabled()
        expect(p.locator("#ex-go")).to_have_text(C.t("export.go"))
        expect(p.locator("#ex-cancel")).to_have_text(C.t("export.cancel"))
        expect(p.locator("#ex-go")).to_have_class(re.compile(r"\bcpw-save\b"))
        expect(p.locator("#ex-cancel")).to_have_class(re.compile(r"\bcpw-cancel\b"))


def test_the_all_box_is_input_ex_all(browser):
    """Contract 3, DOM: the first row of the grid has `input#ex-all`."""
    with doc(browser) as e:
        open_export(e.page)
        assert e.page.locator("#ex-all").count() == 1, "the all-pages-all-languages box has no id `ex-all`"
        assert e.page.evaluate("sel => document.getElementById('ex-all') === document.querySelector(sel)", ALL) is True


def test_the_window_opened_from_another_page_ticks_that_page_and_language(browser):
    with doc(browser, lang="fr", key="vancouver", seed=lambda env: seed_cells(env, ALL_CELLS)) as e:
        open_export(e.page)
        assert ticked(e.page) == {("vancouver", "fr")}
        expect(e.page.locator("#ex-count")).to_have_text(C.tn("export.count", 1))


def test_the_row_column_and_all_boxes_tick_the_right_cells(browser):
    with doc(browser, seed=lambda env: seed_cells(env, ALL_CELLS)) as e:        # CEL-037: no cell is greyed
        p = e.page
        open_export(p)
        row = lambda k: f'#ex-grid input[data-row="{k}"]'   # noqa: E731
        col = lambda k: f'#ex-grid input[data-col="{k}"]'   # noqa: E731
        # one of 32 is ticked: the boxes over it are in between, the others are plain
        assert tri(p, ALL) == (False, True)
        assert tri(p, row(PAGE_KEY)) == (False, True)
        assert tri(p, col("de")) == (False, True)
        assert tri(p, row("vancouver")) == (False, False)
        assert tri(p, col("fr")) == (False, False)

        p.locator(row("vancouver")).check()                       # a page: its eight languages
        assert ticked(p) == {("vancouver", lang) for lang in LANGS} | {(PAGE_KEY, "de")}
        assert tri(p, row("vancouver")) == (True, False)
        assert tri(p, col("de")) == (False, True)                 # 2 of 4
        assert tri(p, col("fr")) == (False, True)                 # 1 of 4
        assert tri(p, col("es")) == (False, True)
        assert tri(p, ALL) == (False, True)
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 9))

        p.locator(col("fr")).check()                              # a language, from the in-between state
        want = {("vancouver", lang) for lang in LANGS} | {(PAGE_KEY, "de")} | {(k, "fr") for k in PAGES}
        assert ticked(p) == want
        assert tri(p, col("fr")) == (True, False)
        assert tri(p, row(PAGE_KEY)) == (False, True)             # 2 of 8
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", len(want)))

        p.locator(col("fr")).uncheck()                            # and off again
        assert ticked(p) == {("vancouver", lang) for lang in LANGS if lang != "fr"} | {(PAGE_KEY, "de")}
        assert tri(p, col("fr")) == (False, False)
        assert tri(p, row("vancouver")) == (False, True)          # 7 of 8
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 8))

        p.locator(ALL).check()                              # everything
        assert len(ticked(p)) == 32
        assert tri(p, ALL) == (True, False)
        for k in PAGES:
            assert tri(p, row(k)) == (True, False), k
        for lang in LANGS:
            assert tri(p, col(lang)) == (True, False), lang
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 32))

        ex_box(p, "vs-toronto", "ko").uncheck()                   # one off: everything over it is in between
        assert len(ticked(p)) == 31
        assert tri(p, ALL) == (False, True)
        assert tri(p, row("vs-toronto")) == (False, True)
        assert tri(p, col("ko")) == (False, True)
        assert tri(p, row("vancouver")) == (True, False)


def test_export_is_off_with_nothing_ticked_and_the_count_follows_the_boxes(browser):
    with doc(browser, seed=lambda env: seed_cells(env, ALL_CELLS)) as e:        # CEL-037: no cell is greyed
        p = e.page
        open_export(p)
        ex_box(p, PAGE_KEY, LANG).uncheck()
        assert ticked(p) == set()
        expect(p.locator("#ex-go")).to_be_disabled()
        expect(p.locator("#ex-count")).to_have_text(C.t("export.count.none"))
        assert tri(p, ALL) == (False, False)
        p.locator("#ex-go").click(force=True)                      # a disabled button does nothing
        time.sleep(0.3)
        expect(p.locator("#ex-grid")).to_be_visible()
        assert not e.store.jobs and "desk-job-start" not in e.worker.calls
        ex_box(p, "vs-toronto", "ko").check()
        expect(p.locator("#ex-go")).to_be_enabled()
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 1))
        p.locator(ALL).check()
        p.locator(ALL).uncheck()
        assert ticked(p) == set()
        expect(p.locator("#ex-go")).to_be_disabled()
        expect(p.locator("#ex-count")).to_have_text(C.t("export.count.none"))


def seed_cells(env, cells):
    """One Gemini draft in each (page, language) of `cells`: those cells have something to export, every
    other one has nothing (the grid says "not translated" and the picker greys it, CEL-037)."""
    for key, lang in cells:
        uid = next(b["id"] for b in _stage_data(key)["blocks"] if not b["lock"])
        draft(env.store, uid, "Entwurf", lang=lang)


HAVE = {(PAGE_KEY, LANG), ("vancouver", "fr"), ("vs-toronto", "ko")}
ALL_CELLS = {(key, lang) for key in PAGES for lang in LANGS}


def translating(env, key, lang):
    """A translate-page job for this page and language is out: the grid shows the cell as "translating", which
    is not "nothing" (the picker keeps it pickable, CEL-037), though it has no draft yet."""
    code, body = env.store.handle("desk-job-start", {"locale": lang, "kind": "translate-page",
                                                     "ref": {"page": key, "keepEdited": True}}, H.REVIEWER)
    assert code == 200, body


def grid_status(page, key, lang):
    return cell(page, key, lang).get_attribute("data-status")


def grid_settled(page):
    """Every language has been read, so no cell is still "unknown". The picker takes its greyed-out map once, when
    the window opens, and an "unknown" cell stays pickable: opened early under load, "all" ticks cells that are
    greyed a moment later (CEL-039: 3 of 5 solo runs failed before this wait)."""
    expect(page.locator('.doc-cell[data-status="unknown"]')).to_have_count(0)


def test_a_page_in_a_language_with_nothing_to_export_is_greyed_in_the_picker(browser):
    """CEL-037 (ux-pass #3): the grid already knows which page x language has no draft and no edit; the picker
    shows those boxes disabled instead of letting the client press Export and read "Nothing to export yet"."""
    with doc(browser, seed=lambda env: seed_cells(env, HAVE)) as e:
        p = e.page
        grid_settled(p)
        open_export(p)
        for key in PAGES:
            for lang in LANGS:
                status = grid_status(p, key, lang)
                if (key, lang) in HAVE:
                    assert status != "none", (key, lang, status)
                    expect(ex_box(p, key, lang)).to_be_enabled()
                else:
                    assert status == "none", (key, lang, status)
                    expect(ex_box(p, key, lang)).to_be_disabled()
        # a greyed box keeps the name a screen reader says; nothing new is written on the window
        expect(ex_box(p, "how-long-to-learn-english", "ja")).to_have_attribute(
            "aria-label", C.t("export.aria.cell", page=C.t("page.how-long-to-learn-english"), language=C.t("lang.ja")))
        assert ticked(p) == {(PAGE_KEY, LANG)}
        expect(p.locator("#ex-go")).to_be_enabled()


def test_the_row_column_and_all_boxes_tick_only_the_cells_that_are_not_greyed(browser):
    with doc(browser, seed=lambda env: seed_cells(env, HAVE)) as e:
        p = e.page
        grid_settled(p)
        open_export(p)
        row = lambda k: f'#ex-grid input[data-row="{k}"]'   # noqa: E731
        col = lambda k: f'#ex-grid input[data-col="{k}"]'   # noqa: E731
        # a page or a language with nothing to export anywhere has its own box greyed too
        expect(p.locator(row("how-long-to-learn-english"))).to_be_disabled()
        expect(p.locator(col("es"))).to_be_disabled()
        expect(p.locator(row("vancouver"))).to_be_enabled()
        expect(p.locator(col("fr"))).to_be_enabled()
        # a row: only its cell that has a translation
        p.locator(row("vancouver")).check()
        assert ticked(p) == {(PAGE_KEY, LANG), ("vancouver", "fr")}
        assert tri(p, row("vancouver")) == (True, False)          # all of what could be ticked
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", 2))
        # a language
        p.locator(col("ko")).check()
        assert ticked(p) == {(PAGE_KEY, LANG), ("vancouver", "fr"), ("vs-toronto", "ko")}
        assert tri(p, col("ko")) == (True, False)
        # everything: exactly the three cells, and the all box is ticked, not in between
        p.locator(ALL).uncheck()
        assert ticked(p) == set()
        p.locator(ALL).check()
        assert ticked(p) == HAVE
        assert tri(p, ALL) == (True, False)
        expect(p.locator("#ex-count")).to_have_text(C.tn("export.count", len(HAVE)))
        ex_box(p, "vancouver", "fr").uncheck()
        assert tri(p, ALL) == (False, True)


def test_when_the_open_page_has_no_translation_in_that_language_nothing_is_ticked_and_export_is_off(browser):
    """The open cell is greyed like any other: the window opens with nothing ticked rather than with a box
    nobody can untick that leads to "Nothing to export yet"."""
    with doc(browser, seed=lambda env: seed_cells(env, [("vancouver", "fr")])) as e:
        p = e.page
        grid_settled(p)
        open_export(p)
        assert grid_status(p, PAGE_KEY, LANG) == "none"
        expect(ex_box(p, PAGE_KEY, LANG)).to_be_disabled()
        assert ticked(p) == set()
        expect(p.locator("#ex-go")).to_be_disabled()
        expect(p.locator("#ex-count")).to_have_text(C.t("export.count.none"))
        p.locator(ALL).check()                                    # only what can be exported
        assert ticked(p) == {("vancouver", "fr")}
        expect(p.locator("#ex-go")).to_be_enabled()


@pytest.mark.parametrize("how", ["cancel", "escape"])
def test_cancel_and_escape_close_the_export_window_and_focus_goes_back_to_the_button(browser, how):
    with doc(browser) as e:
        p = e.page
        open_export(p)
        if how == "cancel":
            p.locator("#ex-cancel").click()
        else:
            p.keyboard.press("Escape")
        expect(p.locator("#ex-modal")).to_be_hidden()
        expect(p.locator("#doc-export")).to_be_focused()
        assert not e.store.jobs and "desk-write" not in e.worker.calls and "desk-job-start" not in e.worker.calls
        open_export(p)                                             # and it opens again
        expect(p.locator("#ex-grid")).to_be_visible()


def test_tab_and_shift_tab_stay_inside_the_export_window(browser):
    with doc(browser) as e:
        p = e.page
        open_export(p)
        inside = "() => !!document.activeElement && !!document.activeElement.closest('#ex-modal')"
        assert p.evaluate(inside), "focus did not move into the window when it opened"
        for i in range(60):                                        # 45 boxes and two buttons: more than a lap
            p.keyboard.press("Tab")
            assert p.evaluate(inside), f"focus left the window on Tab {i + 1}"
        for i in range(60):
            p.keyboard.press("Shift+Tab")
            assert p.evaluate(inside), f"focus left the window on Shift+Tab {i + 1}"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. ONE page x ONE language, end to end
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_one_page_in_one_language_end_to_end(browser, tmp_path):
    blocks = blocks_of()
    d1, d2, e1, e2, e3 = early(PAGE_KEY, LANG, 5)
    f = far(PAGE_KEY, LANG, after=150, skip={b["id"] for b in (d1, d2, e1, e2, e3)})
    d3 = next(b for b in blocks if not (b.get("w") or {}).get(LANG) and not b["lock"])   # no Weglot wording: the English
    orphan = ids_unique_to(_stage_json("pages"), "vancouver")[0]                         # not on this page at all
    assert orphan not in {b["id"] for b in blocks}
    draft_text = {d1["id"]: "Entwurf eins", d2["id"]: "Entwurf zwei", d3["id"]: "Entwurf drei ohne Weglot",
                  e1["id"]: "Entwurf vier", e3["id"]: "Entwurf fuenf", f["id"]: "Entwurf sechs weit unten"}
    edited = {e1["id"]: "Bearbeitet vier", e2["id"]: "Nur bearbeitet zwei"}
    written = [d1, d2, d3, e1, e2, e3, f]
    uids = {b["id"] for b in written}
    want = {b["id"]: {"tray": "csv", "text": edited.get(b["id"], draft_text.get(b["id"])),
                      "approvedAgainst": against(b)} for b in written}
    want[e3["id"]]["rejected"] = ["Alt eins"]
    want_ver = {b["id"]: 2 if b["id"] in (e1["id"], e2["id"], e3["id"]) else 1 for b in written}
    assert want[d3["id"]]["approvedAgainst"] == d3["en"], "d3 was meant to have no German wording"
    left_out = [b["id"] for b in blocks if b["id"] not in uids]
    rows = len(written) - 1                                                              # the far text is refused
    spy = Spy()

    def seed(env):
        for uid, text in draft_text.items():
            draft(env.store, uid, text)
        put(env.store, e1["id"], {"text": edited[e1["id"]]})                              # reviewer edits, saved earlier
        put(env.store, e2["id"], {"text": edited[e2["id"]]})
        put(env.store, e3["id"], {"rejected": ["Alt eins"]})                              # an older decision with a field
        put(env.store, orphan, {"tray": "csv", "text": "Verwaister Text", "approvedAgainst": "Old English"},
            page="vancouver")
        spy.attach(env.store)

    csv = make_csv(LANG, PAGE_KEY)
    refused = [{"unit": f["id"], "rule": "PLACEHOLDER-ORDER"},
               {"unit": orphan, "rule": "EXPORT-SKIP-NO-LONGER-ON-THE-PAGE"}]
    warned = [{"unit": d1["id"], "rule": "CLIENT-RULE-WARN"}]       # an old-style result: the page ignores it
    with doc(browser, seed=seed, init=(OBSERVE_JS,)) as e:
        p = e.page
        assert not on_screen(blk(p, f["id"])), "the far text is on the first screen: the jump proves nothing"
        open_export(p)
        p.locator("#ex-go").click()
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "queued", timeout=10000)
        expect(li).to_contain_text(C.t("export.step.queued"))
        expect(li).to_contain_text(C.t(f"page.{PAGE_KEY}"))
        expect(li).to_contain_text(C.t(f"lang.{LANG}"))
        expect(p.locator("#ex-grid")).to_be_hidden()               # the run replaces the choice
        expect(p.locator("#ex-progress")).to_be_visible()

        # the decisions: exactly the texts that have an edit or a draft, nothing else, nowhere else
        assert {k for k in e.store.decisions if k[0] == LANG} == {(LANG, u) for u in uids | {orphan}}
        assert not {k for k in e.store.decisions if k[0] != LANG}
        for uid in uids:
            assert dec(e.store, uid)["record"] == want[uid], uid
            assert dver(e.store, uid) == want_ver[uid], uid
            assert dec(e.store, uid)["page"] == PAGE_KEY and dec(e.store, uid)["by"] == H.REVIEWER
        for uid in left_out:
            assert dec(e.store, uid) is None, f"{uid} has neither an edit nor a draft but was written"
        # what the page sent: version 2 clients, this language, in chunks, this page
        writes = spy.calls("desk-write")
        assert writes and all(w["body"]["locale"] == LANG and w["body"]["client"] == 1 for w in writes)
        sent = [c for w in writes for c in w["body"]["changes"]]
        assert {c["unit"] for c in sent} == uids and len(sent) == len(uids)
        assert all(c["page"] == PAGE_KEY for c in sent)
        assert {c["unit"]: c["base"] for c in sent} == {u: want_ver[u] - 1 for u in uids}
        # then one job, started after the last write
        starts = spy.calls("desk-job-start")
        assert len(starts) == 1 and starts[0]["code"] == 200
        assert starts[0]["body"]["locale"] == LANG and starts[0]["body"]["kind"] == "export"
        assert starts[0]["body"]["ref"] == {"page": PAGE_KEY}
        assert max(spy.at("desk-write")) < spy.at("desk-job-start")[0]
        (job,) = e.store.jobs.values()
        assert (job["kind"], job["locale"], json.loads(job["ref"]), job["requested_by"]) == \
            ("export", LANG, {"page": PAGE_KEY}, H.REVIEWER)

        # the engine picks it up, makes the file, finishes
        e.store.finish_job(LANG, "export", "running")
        expect(li).to_have_attribute("data-state", "running")
        expect(li).to_contain_text(C.t("export.step.running"))
        with p.expect_download() as dl:
            engine_done(e.store, LANG, PAGE_KEY, csv, rows, refused=refused, warned=warned,
                        stamp=[u for u in uids if u != f["id"]])
        expect(li).to_have_attribute("data-state", "done")
        expect(li).to_contain_text(C.tn("export.step.done", rows))
        seen = ex_states(p, PAGE_KEY, LANG)
        assert is_subsequence(["saving", "queued", "running", "done"], seen), seen
        assert seen[0] in ("waiting", "saving"), seen
        assert set(seen) <= set(ORDER), seen

        # the download: its name and exactly the engine's bytes
        got = dl.value
        assert got.suggested_filename == f"weglot-{LANG}-{PAGE_KEY}.csv"
        saved = tmp_path / "first.csv"
        got.save_as(saved)
        assert saved.read_bytes() == csv.encode("utf-8")

        # the result view
        expect(p.locator("#ex-result")).to_be_visible()
        kinds = set(p.eval_on_selector_all("#ex-result .ex-group", "els => els.map(x => x.dataset.kind)"))
        assert kinds == {"empty", "refused", "orphan"}, kinds       # the `warned` group is gone (Ruling 21:00)
        # left out: no edit and no draft (the list may be cut short with "and N more")
        emp = group(p, "empty")
        expect(emp.locator("h3")).to_have_text(C.tn("export.group.empty", len(left_out)))
        listed = emp.locator("li.ex-item").evaluate_all("els => els.map(x => x.dataset.uid)")
        assert listed and set(listed) <= set(left_out), "a text with an edit or a draft is listed as left out"
        assert not set(listed) & uids
        assert emp.locator("li.ex-item").first.get_attribute("data-page") == PAGE_KEY
        assert emp.locator("li.ex-item").first.get_attribute("data-lang") == LANG
        if len(listed) < len(left_out):
            expect(emp).to_contain_text(C.t("export.more", n=len(left_out) - len(listed)))
        # refused by a check: the English (cut to 80), the reason, and a Show that really shows it
        ref = group(p, "refused")
        expect(ref.locator("h3")).to_have_text(C.tn("export.group.refused", 1))
        it = item(p, "refused", f["id"], PAGE_KEY, LANG)
        expect(it).to_have_count(1)
        expect(it).to_contain_text(squash(plain(f["en"]))[:60])
        expect(it).to_contain_text(C.t("refusal.PLACEHOLDER-ORDER"))
        expect(it.locator("button.ex-jump")).to_have_text(C.t("export.jump"))
        # the engine's result still carries a `warned` array (above): it is ignored. No group of that name, and
        # the text it names (it is in the file) is listed nowhere
        assert p.locator('#ex-result .ex-group[data-kind="warned"]').count() == 0
        assert p.locator(f'#ex-result li.ex-item[data-uid="{d1["id"]}"]').count() == 0
        # an edit whose English left the page: the saved wording, not the English
        orp = group(p, "orphan")
        expect(orp.locator("h3")).to_have_text(C.tn("export.group.orphan", 1))
        expect(orp.locator(f'li.ex-item[data-uid="{orphan}"]')).to_have_count(1)
        expect(orp.locator(f'li.ex-item[data-uid="{orphan}"]')).to_contain_text("Verwaister Text")
        # nothing the engine refused is listed in two groups
        assert item(p, "empty", f["id"]).count() == 0 and item(p, "refused", d1["id"]).count() == 0

        # Download again: the same file
        expect(p.locator("#ex-download")).to_have_text(C.t("export.download"))
        with p.expect_download() as dl2:
            p.locator("#ex-download").click()
        again = tmp_path / "again.csv"
        dl2.value.save_as(again)
        assert dl2.value.suggested_filename == got.suggested_filename and again.read_bytes() == saved.read_bytes()
        expect(p.locator("#ex-close")).to_have_text(C.t("export.close"))

        # the grid re-read what the engine stamped
        expect(cell(p, PAGE_KEY, LANG)).to_have_attribute("data-status", "edited")   # the far text was not stamped
        # Show: the window goes, the text is on screen and flashes
        it.locator("button.ex-jump").click()
        expect(p.locator("#ex-modal")).to_be_hidden()
        p.wait_for_function("uid => document.querySelector('li.doc-block[data-uid=\"' + uid + '\"]')"
                            ".hasAttribute('data-flash')", arg=f["id"], timeout=3000)
        assert on_screen(blk(p, f["id"])), "Show did not bring the text into view"
        wait_open(p, PAGE_KEY, LANG)


def test_the_files_turn_exported_in_the_grid_when_the_engine_stamped_them(browser):
    a, b = early(PAGE_KEY, LANG, 2)
    with doc(browser, seed=lambda env: [draft(env.store, x["id"], f"Entwurf {i}") for i, x in enumerate((a, b))]) as e:
        p = e.page
        expect(cell(p, PAGE_KEY, LANG)).to_have_attribute("data-status", "drafted")
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 2, stamp=[a["id"], b["id"]])
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "done")
        c = cell(p, PAGE_KEY, LANG)
        expect(c).to_have_attribute("data-status", "exported", timeout=8000)
        expect(c.locator(".doc-cell-status")).to_have_text(C.t("doc.status.exported"))


def test_export_waits_for_an_unsent_edit_and_exports_the_saved_version(browser):
    """Contract 3, step 1: the language has no unsent edit before anything is exported."""
    (a,) = early(PAGE_KEY, LANG, 1)
    (b,) = early(PAGE_KEY, LANG, 2)[1:]
    slow = dict(TIMING, quiet=1500, maxWait=3000)
    spy = Spy()

    def seed(env):
        draft(env.store, b["id"], "Entwurf zwei")
        spy.attach(env.store)

    with doc(browser, seed=seed, timing=slow) as e:
        p = e.page
        edit(p, a["id"], "Frisch getippt")
        assert dec(e.store, a["id"]) is None, "the typing was saved at once: the test slow-down is not in place"
        start_export(p, {(PAGE_KEY, LANG)})                        # while the typing is still unsent
        until(lambda: spy.calls("desk-job-start"), 12.0, what="the export job to start")
        writes = spy.calls("desk-write")
        # The reviewer's typing is the FIRST thing written, alone (the export's own write of the draft comes
        # after it). Since CEL-026 the page stamps the v1 decision (tray csv, approvedAgainst) on every edit,
        # so that very write already is what the export would write for this text: it is not written twice.
        assert [c["unit"] for c in writes[0]["body"]["changes"]] == [a["id"]], \
            "the export wrote before the reviewer's unsent typing was saved"
        first = writes[0]["body"]["changes"][0]
        assert first["base"] == 0 and first["record"]["text"] == "Frisch getippt", first
        later = [c["unit"] for w in writes[1:] for c in w["body"]["changes"]]
        assert later == [b["id"]], f"the saved typing was written again, or something else was: {later}"
        assert dec(e.store, a["id"])["record"] == {"tray": "csv", "text": "Frisch getippt",
                                                   "approvedAgainst": against(a)}
        assert dver(e.store, a["id"]) == 1
        assert dtext(e.store, b["id"]) == "Entwurf zwei"
        assert max(spy.at("desk-write")) < spy.at("desk-job-start")[0]


def test_exporting_an_unchanged_page_writes_nothing_but_still_makes_the_file(browser):
    """Contract 3, steps 2-3: a record equal to the stored one is not written; but a page whose decisions
    already are in the file's tray still gets its job."""
    a, b = early(PAGE_KEY, LANG, 2)
    spy = Spy()

    def seed(env):
        for x, txt in ((a, "Eins"), (b, "Zwei")):
            put(env.store, x["id"], {"tray": "csv", "text": txt, "approvedAgainst": against(x)})
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        start_export(e.page, {(PAGE_KEY, LANG)})
        li = ex_file(e.page, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "queued", timeout=10000)
        assert spy.calls("desk-write") == [], "an unchanged decision was written again"
        assert (dver(e.store, a["id"]), dver(e.store, b["id"])) == (1, 1)
        assert len(spy.calls("desk-job-start")) == 1 and open_job(e.store, LANG, PAGE_KEY)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. several files: one zip, one job at a time
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_several_files_make_one_zip_and_the_jobs_run_one_at_a_time(browser, tmp_path):
    v1 = early("vancouver", "de", 1)[0]
    v2 = far("vancouver", "de", after=120, skip={v1["id"]})
    c1, c2 = early(PAGE_KEY, "de", 2)
    plan = {("vancouver", "de"): [v1, v2], (PAGE_KEY, "de"): [c1, c2], (PAGE_KEY, "fr"): [c1, c2]}
    order = [("vancouver", "de"), (PAGE_KEY, "de"), (PAGE_KEY, "fr")]            # pages in page order, then languages
    csvs = {cl: make_csv(cl[1], cl[0]) for cl in order}
    spy = Spy()

    def seed(env):
        for (key, lang), bs in plan.items():
            for i, b in enumerate(bs):
                draft(env.store, b["id"], f"Entwurf {lang} {i}", lang=lang)
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        start_export(p, order)
        lines = p.eval_on_selector_all("li.ex-file", "els => els.map(x => [x.dataset.page, x.dataset.lang])")
        assert [tuple(x) for x in lines] == order, lines
        v_refused = [{"unit": v2["id"], "rule": "PLACEHOLDER-ORDER"}]
        steps = [
            (("vancouver", "de"), ("done", csvs[order[0]], 1, v_refused, [v1["id"]])),
            ((PAGE_KEY, "de"), ("done", csvs[order[1]], 2, [], [c1["id"], c2["id"]])),
            ((PAGE_KEY, "fr"), ("done", csvs[order[2]], 2, [], [c1["id"], c2["id"]])),
        ]
        for k, ((key, lang), step) in enumerate(steps):
            if k == len(steps) - 1:
                with p.expect_download() as dl:
                    serve_file(e, spy, key, lang, step, k=k, later=[x for x, _ in steps[k + 1:]])
            else:
                serve_file(e, spy, key, lang, step, k=k, later=[x for x, _ in steps[k + 1:]])
        assert_one_job_at_a_time(spy)
        assert [e.store.jobs[i]["locale"] for i in e.store.jobs] == ["de", "de", "fr"]
        for key, lang in order:
            expect(ex_file(p, key, lang)).to_have_attribute("data-state", "done")

        # ONE zip, with a file for each, exactly as the Worker returned them
        assert ZIP_NAME.match(dl.value.suggested_filename), dl.value.suggested_filename
        z = tmp_path / "all.zip"
        dl.value.save_as(z)
        files = read_zip(z)
        assert files == {f"weglot-{lang}-{key}.csv": csvs[(key, lang)].encode("utf-8") for key, lang in order}

        # Download again gives the same files
        with p.expect_download() as dl2:
            p.locator("#ex-download").click()
        z2 = tmp_path / "again.zip"
        dl2.value.save_as(z2)
        assert ZIP_NAME.match(dl2.value.suggested_filename)
        assert read_zip(z2) == files

        # the grid shows what was exported
        for key, lang in ((PAGE_KEY, "de"), (PAGE_KEY, "fr")):
            expect(cell(p, key, lang)).to_have_attribute("data-status", "exported", timeout=8000)

        # a refused text of ANOTHER page: Show opens that page and language and flashes the text
        it = item(p, "refused", v2["id"], "vancouver", "de")
        expect(it).to_have_count(1)
        it.locator("button.ex-jump").click()
        expect(p.locator("#ex-modal")).to_be_hidden()
        wait_open(p, "vancouver", "de")
        expect(p.locator("#doc-title")).to_have_text(
            C.t("doc.title", page=C.t("page.vancouver"), language=C.t("lang.de")))
        p.wait_for_function("uid => { const li = document.querySelector('li.doc-block[data-uid=\"' + uid + '\"]');"
                            " return !!li && li.hasAttribute('data-flash'); }", arg=v2["id"], timeout=4000)
        assert on_screen(blk(p, v2["id"]))
        query = p.evaluate("() => location.search")
        assert "page=vancouver" in query and "lang=de" in query


def test_the_files_are_made_page_by_page_in_page_order_then_language_order(browser, tmp_path):
    """Page-major, whatever order the boxes were ticked in. These three cells are chosen so the two orders
    DIFFER: page by page is (vancouver, de), (vancouver, fr), (vs-toronto, de); language by language
    (and the order they are ticked in here, German first) would be (vancouver, de), (vs-toronto, de),
    (vancouver, fr). The file lines, the jobs and the zip's entries all follow the first."""
    page_major = [("vancouver", "de"), ("vancouver", "fr"), ("vs-toronto", "de")]
    language_major = [("vancouver", "de"), ("vs-toronto", "de"), ("vancouver", "fr")]
    assert page_major != language_major
    plan = {cl: early(cl[0], cl[1], 1)[0] for cl in page_major}
    csvs = {cl: make_csv(cl[1], cl[0]) for cl in page_major}
    spy = Spy()

    def seed(env):
        for (key, lang), b in plan.items():
            draft(env.store, b["id"], f"Entwurf {key} {lang}", lang=lang)
        spy.attach(env.store)

    with doc(browser, lang="de", key="vancouver", seed=seed) as e:
        p = e.page
        open_export(p)
        assert ticked(p) == {("vancouver", "de")}
        ex_box(p, "vs-toronto", "de").check()                      # ticked in language order: de, de, then fr
        ex_box(p, "vancouver", "fr").check()
        assert ticked(p) == set(page_major)
        p.locator("#ex-go").click()
        lines = [tuple(x) for x in p.eval_on_selector_all(
            "li.ex-file", "els => els.map(x => [x.dataset.page, x.dataset.lang])")]
        assert lines == page_major, f"the file lines are not page by page, languages in order: {lines}"
        steps = [(cl, ("done", csvs[cl], 1, [], [plan[cl]["id"]])) for cl in page_major]
        for k, ((key, lang), step) in enumerate(steps):
            later = [x for x, _ in steps[k + 1:]]
            if k == len(steps) - 1:
                with p.expect_download() as dl:
                    serve_file(e, spy, key, lang, step, k=k, later=later)
            else:
                serve_file(e, spy, key, lang, step, k=k, later=later)
        assert_one_job_at_a_time(spy)
        started = [(c["body"]["ref"]["page"], c["body"]["locale"]) for c in spy.calls("desk-job-start")]
        assert started == page_major, f"the jobs were started in this order: {started}"
        made = [(j["locale"], json.loads(j["ref"])["page"]) for j in e.store.jobs.values()]
        assert made == [(lang, key) for key, lang in page_major], made
        z = tmp_path / "order.zip"
        dl.value.save_as(z)
        files = read_zip(z)
        assert list(files) == [f"weglot-{lang}-{key}.csv" for key, lang in page_major], list(files)
        assert files == {f"weglot-{lang}-{key}.csv": csvs[(key, lang)].encode("utf-8") for key, lang in page_major}
        assert [tuple(x) for x in p.eval_on_selector_all(
            "li.ex-file", "els => els.map(x => [x.dataset.page, x.dataset.lang])")] == page_major


def test_a_run_with_one_file_that_failed_and_one_with_nothing_zips_only_the_two_that_were_made(browser, tmp_path):
    c1, c2 = early(PAGE_KEY, "de", 2)
    f1, f2 = early(PAGE_KEY, "fr", 2)
    h1, h2 = early("how-long-to-learn-english", "fr", 2)
    # Vancouver in Spanish is the file with nothing in it: a greyed cell cannot be picked (CEL-037), so it is a
    # cell whose translate job is out and has written nothing yet. Spanish has no other file, so that job
    # (one open job per language) does not hold up the German and French exports.
    order = [("vancouver", "es"), (PAGE_KEY, "de"), (PAGE_KEY, "fr"), ("how-long-to-learn-english", "fr")]
    spy = Spy()

    def seed(env):
        for lang, bs in (("de", (c1, c2)), ("fr", (f1, f2, h1, h2))):
            for i, b in enumerate(bs):
                draft(env.store, b["id"], f"Entwurf {lang} {i}", lang=lang)
        translating(env, "vancouver", "es")
        spy.attach(env.store)

    csv_c, csv_h = make_csv("de", PAGE_KEY), make_csv("fr", "how-long-to-learn-english")
    with doc(browser, seed=seed) as e:
        p = e.page
        start_export(p, order)
        steps = [
            ((PAGE_KEY, "de"), ("done", csv_c, 2, [], [c1["id"], c2["id"]])),
            ((PAGE_KEY, "fr"), ("failed", "storage-error")),
            (("how-long-to-learn-english", "fr"), ("done", csv_h, 2, [], [h1["id"], h2["id"]])),
        ]
        for k, ((key, lang), step) in enumerate(steps):
            if k == 0:                                                         # Vancouver in Spanish has nothing yet
                until(lambda: ex_file(p, "vancouver", "es").get_attribute("data-state") == "nothing", 10.0,
                      what="the empty file to be skipped")
            later = [x for x, _ in steps[k + 1:]]
            if k == len(steps) - 1:
                with p.expect_download() as dl:
                    serve_file(e, spy, key, lang, step, k=k, later=later)
            else:
                serve_file(e, spy, key, lang, step, k=k, later=later)
        assert_one_job_at_a_time(spy)
        assert not [j for j in e.store.jobs.values()
                    if j["kind"] == "export" and json.loads(j["ref"])["page"] == "vancouver"]
        expect(ex_file(p, "vancouver", "es")).to_have_attribute("data-state", "nothing")
        expect(ex_file(p, "vancouver", "es")).to_contain_text(C.t("export.step.nothing"))
        failed = ex_file(p, PAGE_KEY, "fr")
        expect(failed).to_have_attribute("data-state", "failed")
        expect(failed).to_contain_text(C.t("export.step.failed", reason=C.t("job.failed.storage-error")))
        expect(ex_file(p, PAGE_KEY, "de")).to_have_attribute("data-state", "done")
        expect(ex_file(p, "how-long-to-learn-english", "fr")).to_have_attribute("data-state", "done")
        assert ZIP_NAME.match(dl.value.suggested_filename), dl.value.suggested_filename
        z = tmp_path / "two.zip"
        dl.value.save_as(z)
        assert read_zip(z) == {f"weglot-de-{PAGE_KEY}.csv": csv_c.encode("utf-8"),
                               "weglot-fr-how-long-to-learn-english.csv": csv_h.encode("utf-8")}
        expect(p.locator("#ex-download")).to_be_visible()


def test_a_second_export_of_the_same_language_waits_for_the_one_already_running(browser, tmp_path):
    a, b = early(PAGE_KEY, LANG, 2)
    spy = Spy()

    def seed(env):
        draft(env.store, a["id"], "Entwurf eins")
        draft(env.store, b["id"], "Entwurf zwei")
        code, _ = env.store.handle("desk-job-start",
                                   {"locale": LANG, "kind": "export", "ref": {"page": "vancouver"}}, OTHER)
        assert code == 200
        spy.attach(env.store)

    with doc(browser, seed=seed, http_errors=True) as e:                      # the Worker's 409 is how the wait starts
        p = e.page
        (foreign,) = list(e.store.jobs)
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: spy.calls("desk-job-start", code=409), 10.0, what="the Worker's 409")
        time.sleep(0.6)
        assert len(e.store.jobs) == 1, "a second export job was created while the first was still open"
        expect(ex_file(p, PAGE_KEY, LANG)).not_to_have_attribute("data-state", "failed")
        spy.mark("foreign-done")
        e.store.finish_job(LANG, "export", "done", result_of("b-foreign", 1))        # the other one ends
        job = until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="our own export job to start by itself")
        assert job["id"] != foreign and len(e.store.jobs) == 2
        done_at = next(i for i, c in enumerate(spy.log) if c["action"] == "mark")
        assert spy.at("desk-job-start", H.REVIEWER)[-1] > done_at, "our job started before the other one ended"
        with p.expect_download() as dl:
            engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 2)
        assert dl.value.suggested_filename == f"weglot-{LANG}-{PAGE_KEY}.csv"
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "done")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. failures
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_a_failed_job_says_why_and_no_file_is_offered(browser):
    (a,) = early(PAGE_KEY, LANG, 1)
    with doc(browser, seed=lambda env: draft(env.store, a["id"], "Entwurf eins")) as e:
        p = e.page
        downloads = []
        p.on("download", lambda d: downloads.append(d))
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        e.store.finish_job(LANG, "export", "failed", None, error="storage-error")
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "failed")
        expect(li).to_contain_text(C.t("job.failed.storage-error"))
        expect(li).to_contain_text(C.t("export.step.failed", reason=C.t("job.failed.storage-error")))
        expect(p.locator("#ex-result")).to_be_visible()
        expect(p.locator("#ex-download")).to_be_hidden()
        expect(p.locator("#ex-close")).to_be_visible()
        time.sleep(0.5)
        assert downloads == [], "a file was downloaded although none was made"
        p.locator("#ex-close").click()
        expect(p.locator("#ex-modal")).to_be_hidden()


def test_a_failed_job_that_names_the_texts_it_refused_still_lists_them(browser):
    """Builder's update to the contract: a job that ends `failed` (export-refused) but carries
    result.refused still fills the result groups; the file's line is failed with the job.failed sentence."""
    a, b = early(PAGE_KEY, LANG, 2)
    with doc(browser, seed=lambda env: [draft(env.store, x["id"], f"Entwurf {i}") for i, x in enumerate((a, b))]) as e:
        p = e.page
        downloads = []
        p.on("download", lambda d: downloads.append(d))
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        e.store.finish_job(LANG, "export", "failed", {"refused": [{"unit": a["id"], "rule": "NUMBER-PARITY"}],
                                                      "warned": [], "notes": [], "skipped": {}},
                           error="export-refused")
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "failed")
        expect(li).to_contain_text(C.t("export.step.failed", reason=C.t("job.failed.export-refused")))
        expect(p.locator("#ex-result")).to_be_visible()
        expect(group(p, "refused").locator("h3")).to_have_text(C.tn("export.group.refused", 1))
        it = item(p, "refused", a["id"], PAGE_KEY, LANG)
        expect(it).to_have_count(1)
        expect(it).to_contain_text(C.t("refusal.NUMBER-PARITY"))
        expect(it.locator("button.ex-jump")).to_have_text(C.t("export.jump"))
        assert item(p, "refused", b["id"]).count() == 0
        expect(p.locator("#ex-download")).to_be_hidden()
        time.sleep(0.4)
        assert downloads == [], "a file was downloaded although the job failed"


def test_a_refused_text_that_is_on_thirty_pages_or_more_is_listed_like_any_other(browser):
    """CEL-039 (CEL-027 note, operator 21:00): a shared body text on 30+ pages (an FAQ answer, a course name)
    goes in the file like any other, and when a gate refuses it the result lists it with its sentence:
    nothing about its page count hides it."""
    shared = next(b for b in _stage_data()["blocks"] if b.get("out", 0) >= 29 and not b["lock"])
    with doc(browser, seed=lambda env: draft(env.store, shared["id"], "Entwurf geteilt")) as e:
        p = e.page
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        e.store.finish_job(LANG, "export", "failed", {"refused": [{"unit": shared["id"], "rule": "NUMBER-PARITY"}],
                                                      "warned": [], "notes": [], "skipped": {}},
                           error="export-refused")
        it = item(p, "refused", shared["id"], PAGE_KEY, LANG)
        expect(it).to_have_count(1)
        expect(it).to_contain_text(C.t("refusal.NUMBER-PARITY"))


def test_a_code_nobody_knows_gets_the_general_sentence(browser):
    (a,) = early(PAGE_KEY, LANG, 1)
    with doc(browser, seed=lambda env: draft(env.store, a["id"], "Entwurf eins")) as e:
        start_export(e.page, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        e.store.finish_job(LANG, "export", "failed", None, error="a-code-nobody-knows")
        li = ex_file(e.page, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "failed")
        expect(li).to_contain_text(C.t("export.step.failed", reason=C.t("doc.job.failed.unknown")))


def test_a_page_in_a_language_with_nothing_in_it_starts_no_job(browser):
    """A cell with no draft and no edit is greyed in the picker (CEL-037), so this reaches the same answer from a
    cell the picker still allows: a page whose translate job is out and has written nothing yet."""
    spy = Spy()

    def seed(env):
        translating(env, PAGE_KEY, LANG)
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        downloads = []
        p.on("download", lambda d: downloads.append(d))
        start_export(p, {(PAGE_KEY, LANG)})
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "nothing")
        expect(li).to_contain_text(C.t("export.step.nothing"))
        expect(p.locator("#ex-result")).to_be_visible()
        expect(p.locator("#ex-download")).to_be_hidden()
        time.sleep(0.5)
        assert not jobs_of(e.store, "export") and spy.calls("desk-job-start", code=None) == []
        assert spy.calls("desk-write") == [], "something was written for a page with nothing in it"
        assert downloads == []
        p.locator("#ex-close").click()
        expect(p.locator("#ex-modal")).to_be_hidden()


def test_a_file_older_than_an_hour_says_it_is_out_of_date(browser):
    (a,) = early(PAGE_KEY, LANG, 1)
    with doc(browser, seed=lambda env: draft(env.store, a["id"], "Entwurf eins"), http_errors=True) as e:
        p = e.page
        downloads = []
        p.on("download", lambda d: downloads.append(d))
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 1, created_at="2026-10-01T00:00:00.000Z")
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "failed")                       # the Worker answered 410
        expect(li).to_contain_text(C.t("flow.file.stale"))
        expect(p.locator("#ex-download")).to_be_hidden()
        time.sleep(0.5)
        assert downloads == []
        p.keyboard.press("Escape")                                                  # the run ended: Escape closes
        expect(p.locator("#ex-modal")).to_be_hidden()
        expect(p.locator("#doc-export")).to_be_focused()


def test_escape_is_ignored_until_the_run_has_ended(browser):
    (a,) = early(PAGE_KEY, LANG, 1)
    with doc(browser, seed=lambda env: draft(env.store, a["id"], "Entwurf eins")) as e:
        p = e.page
        start_export(p, {(PAGE_KEY, LANG)})
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "queued", timeout=10000)
        p.keyboard.press("Escape")
        time.sleep(0.3)
        expect(p.locator("#ex-modal")).to_be_visible()
        expect(li).to_be_visible()
        e.store.finish_job(LANG, "export", "failed", None, error="engine-stopped")
        expect(li).to_have_attribute("data-state", "failed")
        p.keyboard.press("Escape")
        expect(p.locator("#ex-modal")).to_be_hidden()
        expect(p.locator("#doc-export")).to_be_focused()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. chunks and conflicts
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_a_big_page_is_written_fifty_texts_at_a_time(browser):
    ids = [b["id"] for b in blocks_of()][:120]
    assert len(ids) == 120
    spy = Spy()

    def seed(env):
        for i, uid in enumerate(ids):
            draft(env.store, uid, f"Entwurf {i}")
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 20.0, what="the export job")
        writes = [w for w in spy.calls("desk-write")]
        sizes = [len(w["body"]["changes"]) for w in writes]
        assert sizes == [50, 50, 20], sizes                         # 120 changes: two full requests, then the rest, in order
        assert all(w["code"] == 200 and not w["out"]["conflicts"] and not w["out"]["refused"] for w in writes)
        sent = [c for w in writes for c in w["body"]["changes"]]
        assert [c["unit"] for c in sent] == ids, "the texts were not written in the page's order, 50 at a time"
        assert all(c["page"] == PAGE_KEY and c["base"] == 0 and c["record"]["tray"] == "csv" for c in sent)
        for i, uid in enumerate(ids):
            assert dtext(e.store, uid) == f"Entwurf {i}", uid
        assert max(spy.at("desk-write")) < spy.at("desk-job-start")[0]
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 120)
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "done")


def test_an_edit_the_autosave_refused_is_listed_as_unsaved_and_does_not_hold_the_export_up(browser):
    """Amendment 3-4: the Worker refused the reviewer's typing earlier, so it sits in the page's pending list for
    good. The export neither waits for it (it used to wait a minute) nor writes over it; it lists the text."""
    a, b, c = early(PAGE_KEY, LANG, 3)
    spy = Spy()

    def seed(env):
        draft(env.store, b["id"], "Entwurf zwei")
        draft(env.store, c["id"], "Entwurf drei")
        # The storage knows a text only on the pages it belongs to: without this page for `a`, it answers a write
        # of `a` with "refused" (not on this page) -- the one way to make the stand-in refuse ONE text.
        env.store.units.discard((a["id"], PAGE_KEY))
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        assert (a["id"], PAGE_KEY) not in e.store.units and (b["id"], PAGE_KEY) in e.store.units
        edit(p, a["id"], "Getippt, aber abgelehnt")
        until(lambda: [w for w in spy.calls("desk-write")
                       if a["id"] in [r["unit"] for r in w["out"].get("refused", [])]], 6.0,
              what="the Worker to refuse the typed text")
        expect(p.locator("#doc-save")).to_have_attribute("data-state", "refused")   # held back for good, not retried
        assert dec(e.store, a["id"]) is None
        tried = len(spy.calls("desk-write"))

        t0 = time.monotonic()
        start_export(p, {(PAGE_KEY, LANG)})
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "queued", timeout=10000)         # a minute's wait would time out here
        waited = time.monotonic() - t0
        assert waited < 8, f"the export waited {waited:.1f} s for an edit that can never be sent"
        assert dtext(e.store, b["id"]) == "Entwurf zwei" and dtext(e.store, c["id"]) == "Entwurf drei"
        assert dec(e.store, a["id"]) is None, "the refused text was written by the export"
        # the export wrote the other two and did not send the refused text again
        sent = [ch["unit"] for w in spy.calls("desk-write")[tried:] for ch in w["body"]["changes"]]
        assert sent == [b["id"], c["id"]], sent
        (start,) = spy.calls("desk-job-start")
        assert start["body"]["ref"] == {"page": PAGE_KEY}

        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 2, stamp=[b["id"], c["id"]])
        expect(li).to_have_attribute("data-state", "done")
        expect(group(p, "unsaved").locator("h3")).to_have_text(C.tn("export.group.unsaved", 1))
        it = item(p, "unsaved", a["id"], PAGE_KEY, LANG)
        expect(it).to_have_count(1)
        expect(it).to_contain_text(snip(a["en"])[:60])
        expect(it).to_contain_text(C.t("export.reason.refused-by-server"))
        expect(it.locator("button.ex-jump")).to_have_text(C.t("export.jump"))
        assert p.locator('#ex-result .ex-group[data-kind="conflict"]').count() == 0     # not a conflict
        assert item(p, "empty", a["id"]).count() == 0 and item(p, "refused", a["id"]).count() == 0
        assert p.locator(f'#ex-result li.ex-item[data-uid="{b["id"]}"]').count() == 0   # the others are in the file
        assert p.locator(f'#ex-result li.ex-item[data-uid="{c["id"]}"]').count() == 0


def test_an_edit_that_met_someone_elses_newer_version_is_listed_as_a_conflict_and_does_not_hold_the_export_up(browser):
    """The other half of amendment 4: a pending edit that is a conflict also stays in the list for good."""
    a, b = early(PAGE_KEY, LANG, 2)
    spy = Spy()

    def seed(env):
        draft(env.store, b["id"], "Entwurf zwei")
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        other_write(e.store, a["id"], "Their text", 0)                              # after the page read the language
        edit(p, a["id"], "Meine Fassung")
        expect(p.locator("#doc-save")).to_have_attribute("data-state", "conflict")
        t0 = time.monotonic()
        start_export(p, {(PAGE_KEY, LANG)})
        li = ex_file(p, PAGE_KEY, LANG)
        expect(li).to_have_attribute("data-state", "queued", timeout=10000)
        assert time.monotonic() - t0 < 8, "the export waited for an edit that is held back as a conflict"
        assert dtext(e.store, b["id"]) == "Entwurf zwei"
        mine = dec(e.store, a["id"])
        assert mine["record"] == {"text": "Their text"} and mine["version"] == 1 and mine["by"] == OTHER
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 1, stamp=[b["id"]])
        expect(li).to_have_attribute("data-state", "done")
        expect(group(p, "conflict").locator("h3")).to_have_text(C.tn("export.group.conflict", 1))
        expect(item(p, "conflict", a["id"], PAGE_KEY, LANG)).to_have_count(1)
        assert p.locator('#ex-result .ex-group[data-kind="unsaved"]').count() == 0
        mine = dec(e.store, a["id"])
        assert mine["record"] == {"text": "Their text"} and mine["version"] == 1, "the other editor's text was overwritten"


def test_a_group_of_more_than_fifty_shows_fifty_and_one_button_that_shows_the_rest(browser):
    a, b = early(PAGE_KEY, LANG, 2)
    left_out = [x["id"] for x in blocks_of() if x["id"] not in (a["id"], b["id"])]
    assert len(left_out) > 100, "the page is too short to test a long list"
    rest = len(left_out) - 50
    with doc(browser, seed=lambda env: [draft(env.store, x["id"], f"Entwurf {i}") for i, x in enumerate((a, b))]) as e:
        p = e.page
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job")
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 2, stamp=[a["id"], b["id"]])
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "done")
        emp = group(p, "empty")
        expect(emp.locator("h3")).to_have_text(C.tn("export.group.empty", len(left_out)))   # the title counts them all
        items = emp.locator("li.ex-item")
        expect(items).to_have_count(50)
        assert items.evaluate_all("els => els.map(x => x.dataset.uid)") == left_out[:50]
        more = emp.locator("button.ex-show-more")
        expect(more).to_have_count(1)
        expect(more).to_have_text(C.t("export.more", n=rest))
        expect(more).to_have_class(re.compile(r"\bdesk-btn\b"))
        assert emp.locator("li.ex-more button.ex-show-more").count() == 1, "the button is not inside li.ex-more"
        assert more.get_attribute("type") == "button"
        # no other group is long enough to need one
        assert p.locator("#ex-result .ex-show-more").count() == 1
        more.click()                                                                       # the rest, every text, once
        expect(items).to_have_count(len(left_out))
        assert items.evaluate_all("els => els.map(x => x.dataset.uid)") == left_out
        expect(emp.locator("button.ex-show-more")).to_have_count(0)
        expect(emp.locator("li.ex-more")).to_have_count(0)
        expect(emp.locator("h3")).to_have_text(C.tn("export.group.empty", len(left_out)))


def test_a_text_someone_else_saved_meanwhile_is_reported_and_never_overwritten(browser):
    x, y = early(PAGE_KEY, LANG, 2)
    spy = Spy()

    def seed(env):
        draft(env.store, x["id"], "Entwurf fuer x")
        draft(env.store, y["id"], "Entwurf fuer y")
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        assert dec(e.store, x["id"]) is None
        other_write(e.store, x["id"], "Their text", 0)                              # after the page read the language
        start_export(p, {(PAGE_KEY, LANG)})
        until(lambda: open_job(e.store, LANG, PAGE_KEY), 10.0, what="the export job (y was written)")
        mine = dec(e.store, x["id"])
        assert mine["record"] == {"text": "Their text"} and mine["version"] == 1 and mine["by"] == OTHER
        assert dec(e.store, y["id"])["record"]["tray"] == "csv" and dver(e.store, y["id"]) == 1
        engine_done(e.store, LANG, PAGE_KEY, make_csv(LANG, PAGE_KEY), 1, stamp=[y["id"]])
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "done")
        expect(group(p, "conflict").locator("h3")).to_have_text(C.tn("export.group.conflict", 1))
        it = item(p, "conflict", x["id"], PAGE_KEY, LANG)
        expect(it).to_have_count(1)
        expect(it).to_contain_text(squash(plain(x["en"]))[:60])
        assert item(p, "conflict", y["id"]).count() == 0
        time.sleep(0.5)
        mine = dec(e.store, x["id"])
        assert mine["record"] == {"text": "Their text"} and mine["version"] == 1 and mine["by"] == OTHER, \
            "the other editor's text was overwritten"


def test_when_every_text_is_a_conflict_nothing_is_written_and_no_job_starts(browser):
    (x,) = early(PAGE_KEY, LANG, 1)
    spy = Spy()

    def seed(env):
        draft(env.store, x["id"], "Entwurf fuer x")
        spy.attach(env.store)

    with doc(browser, seed=seed) as e:
        p = e.page
        other_write(e.store, x["id"], "Their text", 0)
        start_export(p, {(PAGE_KEY, LANG)})
        expect(ex_file(p, PAGE_KEY, LANG)).to_have_attribute("data-state", "nothing", timeout=10000)
        time.sleep(0.4)
        assert not e.store.jobs
        assert dec(e.store, x["id"])["record"] == {"text": "Their text"} and dver(e.store, x["id"]) == 1
        expect(item(p, "conflict", x["id"])).to_have_count(1)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. Re-translate a text
# ══════════════════════════════════════════════════════════════════════════════════════════════════
OLD, EDIT, NEW = "Alter Entwurf von Gemini", "Meine bearbeitete Fassung", "Neuer Entwurf von Gemini"


def open_retranslate_text(p, uid):
    """Focus the text so its toolbar floats up, press Re-translate, and check the window it opens."""
    tgt(p, uid).click()
    btn = blk(p, uid).locator(".doc-tool-retranslate")
    expect(btn).to_be_visible()
    btn.click()
    modal = p.locator("#rt-modal")
    expect(modal).to_be_visible()
    expect(modal).to_have_class(re.compile(r"\bcpw-overlay\b"))
    expect(modal.locator(".cpw-modal")).to_have_attribute("role", "dialog")
    expect(p.locator("#rt-title")).to_have_text(C.t("retr.text.title"))
    expect(p.locator("#rt-body")).to_have_text(C.t("retr.text.body"))
    expect(p.locator('label[for="rt-note"]')).to_have_text(C.t("retr.note.label"))
    expect(p.locator("#rt-note")).to_have_attribute("maxlength", "500")
    expect(p.locator("#rt-go")).to_have_text(C.t("retr.text.go"))
    expect(p.locator("#rt-cancel")).to_have_text(C.t("retr.cancel"))
    return modal


@pytest.mark.parametrize("variant", ["edited", "drafted"])
def test_retranslating_a_text_shows_the_new_draft_and_undo_and_redo_walk_back_and_forth(browser, variant):
    (a,) = pick(_stage_data(), 1)
    shown = EDIT if variant == "edited" else OLD

    def seed(env):
        draft(env.store, a, OLD)

    with doc(browser, seed=seed) as e:
        p = e.page
        if variant == "edited":
            edit(p, a, EDIT)
            wait_text(e.store, a, EDIT)
            wait_ver(e.store, a, 1)
        assert field_value(p, a) == shown
        modal = open_retranslate_text(p, a)
        p.locator("#rt-note").fill("  Use du, not Sie.  ")
        p.locator("#rt-go").click()
        expect(modal).to_be_hidden()
        (job,) = until(lambda: jobs_of(e.store, "retranslate") or None, 10.0, what="the retranslate job")
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "unit": a, "note": "Use du, not Sie.", "keepEdited": True}
        assert job["status"] in ("queued", "running") and job["requested_by"] == H.REVIEWER
        expect(toasts(p)).to_contain_text(C.t("retr.started"))
        assert field_value(p, a) == shown, "the text changed before Gemini answered"

        # the engine writes the new draft and finishes
        draft(e.store, a, NEW, at="2026-10-19T20:00:00.000Z")
        e.store.finish_job(LANG, "retranslate", "done", {"drafts": 1})
        wait_value(p, a, NEW, timeout=8000)
        expect(blk(p, a)).to_have_attribute("data-source", "draft")
        if variant == "edited":                                                     # the edit is cleared on the server too
            wait_ver(e.store, a, 2)
        until(lambda: dtext(e.store, a) is None, 6.0, what="the old edit to be cleared")
        undo, redo = p.locator("#doc-undo"), p.locator("#doc-redo")
        expect(undo).to_be_enabled()
        expect(redo).to_be_disabled()

        undo.click()                                                                # ONE Undo: the old wording is back
        wait_value(p, a, shown)
        wait_text(e.store, a, shown)
        assert dec(e.store, a)["record"]["text"] == shown
        if variant == "edited":
            wait_ver(e.store, a, 3)
        expect(redo).to_be_enabled()
        redo.click()                                                                # Redo: the new draft is shown again
        wait_value(p, a, NEW)
        until(lambda: dtext(e.store, a) is None, 6.0, what="the edit to be cleared again")
        if variant == "edited":
            wait_ver(e.store, a, 4)
        expect(blk(p, a)).to_have_attribute("data-source", "draft")
        expect(redo).to_be_disabled()


def test_cancel_closes_the_text_window_and_an_empty_note_sends_no_note_at_all(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, OLD)) as e:
        p = e.page
        modal = open_retranslate_text(p, a)
        p.locator("#rt-note").fill("will be dropped")
        p.locator("#rt-cancel").click()
        expect(modal).to_be_hidden()
        time.sleep(0.3)
        assert not e.store.jobs and "desk-job-start" not in e.worker.calls
        modal = open_retranslate_text(p, a)                                          # Escape closes it too
        p.keyboard.press("Escape")
        expect(modal).to_be_hidden()
        assert not e.store.jobs
        modal = open_retranslate_text(p, a)
        p.locator("#rt-note").fill("   ")                                            # only spaces: no note
        p.locator("#rt-go").click()
        (job,) = until(lambda: jobs_of(e.store, "retranslate") or None, 10.0, what="the retranslate job")
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "unit": a, "keepEdited": True}
        expect(modal).to_be_hidden()


@pytest.mark.parametrize("typed,sent", [
    ("make it\nfriendlier\tplease", "make it friendlier please"),         # a new line and a tab: one space each
    ("  one\r\n\r\n\ttwo \x07\x7f three  ", "one two three"),             # runs of control characters: ONE space
    ("\n\n\t\n", None),                                                    # only breaks: no note at all
], ids=["line-break-and-tab", "runs-of-control-characters", "only-line-breaks"])
def test_a_note_with_line_breaks_or_tabs_is_sent_as_one_line_and_a_note_of_only_breaks_sends_none(browser, typed, sent):
    """The Worker refuses a note with a control character (`_CONTROL`): what the page sends must not have one."""
    (a,) = pick(_stage_data(), 1)
    spy = Spy()
    with doc(browser, seed=lambda env: (draft(env.store, a, OLD), spy.attach(env.store))) as e:
        p = e.page
        modal = open_retranslate_text(p, a)
        p.locator("#rt-note").fill(typed)
        assert p.locator("#rt-note").input_value() == typed, \
            "the control characters did not reach the note box: the test would prove nothing"
        p.locator("#rt-go").click()
        expect(modal).to_be_hidden()
        (job,) = until(lambda: jobs_of(e.store, "retranslate") or None, 10.0, what="the retranslate job")
        (start,) = spy.calls("desk-job-start")
        assert start["code"] == 200, start["out"]                            # the Worker did not refuse the ref
        want = {"page": PAGE_KEY, "unit": a, "keepEdited": True}
        if sent is not None:
            want["note"] = sent
        assert start["body"]["ref"] == want, start["body"]["ref"]
        assert ("note" in start["body"]["ref"]) is (sent is not None)
        assert json.loads(job["ref"]) == want


def test_a_retranslation_already_running_in_the_language_says_so(browser):
    (a,) = pick(_stage_data(), 1)
    other = ids_unique_to(_stage_json("pages"), PAGE_KEY)[0]

    def seed(env):
        code, _ = env.store.handle("desk-job-start", {"locale": LANG, "kind": "retranslate", "ref": {
            "page": PAGE_KEY, "unit": other, "keepEdited": True}}, OTHER)
        assert code == 200

    with doc(browser, seed=seed, http_errors=True) as e:
        p = e.page
        open_retranslate_text(p, a)
        p.locator("#rt-go").click()
        expect(toasts(p)).to_contain_text(C.t("retr.busy"))
        assert len(e.store.jobs) == 1, "a second retranslate job was created"
        (only,) = e.store.jobs.values()
        assert only["requested_by"] == OTHER


def test_a_failed_retranslation_says_why_and_leaves_the_text_alone(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        p = e.page
        edit(p, a, EDIT)
        wait_text(e.store, a, EDIT)
        open_retranslate_text(p, a)
        p.locator("#rt-go").click()
        until(lambda: jobs_of(e.store, "retranslate") or None, 10.0, what="the retranslate job")
        e.store.finish_job(LANG, "retranslate", "failed", None, error="engine-error")
        expect(toasts(p)).to_contain_text(C.t("retr.failed", reason=C.t("job.failed.engine-error")))
        assert field_value(p, a) == EDIT and dtext(e.store, a) == EDIT and dver(e.store, a) == 1


def test_a_retranslation_that_brings_no_new_text_changes_nothing(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser) as e:
        p = e.page
        edit(p, a, EDIT)
        wait_text(e.store, a, EDIT)
        open_retranslate_text(p, a)
        p.locator("#rt-go").click()
        until(lambda: jobs_of(e.store, "retranslate") or None, 10.0, what="the retranslate job")
        e.store.finish_job(LANG, "retranslate", "done", {"drafts": 0})
        expect(toasts(p)).to_contain_text(C.t("retr.none-arrived"))
        time.sleep(0.4)
        assert field_value(p, a) == EDIT and dtext(e.store, a) == EDIT and dver(e.store, a) == 1, \
            "an edit was cleared although no new text arrived"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 7. Re-translate the page
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("mine", [False, True])
def test_retranslating_the_page_keeps_my_edits_unless_include_my_edits_is_ticked(browser, mine):
    ids = [b["id"] for b in blocks_of()][:3]
    with doc(browser, seed=lambda env: [draft(env.store, u, f"Alt {i}") for i, u in enumerate(ids)]) as e:
        p = e.page
        btn = p.locator("#doc-retranslate-page")
        modal = p.locator("#rp-modal")
        btn.click()
        expect(modal).to_be_visible()
        expect(modal).to_have_class(re.compile(r"\bcpw-overlay\b"))
        expect(modal.locator(".cpw-modal")).to_have_attribute("role", "dialog")
        expect(p.locator("#rp-title")).to_have_text(C.t("retr.page.title"))
        expect(p.locator("#rp-body")).to_have_text(C.t("retr.page.body"))
        expect(modal.locator("label").filter(has=p.locator("#rp-mine"))).to_contain_text(C.t("retr.page.mine"))
        mine_box = p.locator("#rp-mine")
        expect(mine_box).to_have_attribute("type", "checkbox")
        expect(mine_box).not_to_be_checked()                                        # unchecked by default
        expect(p.locator("#rp-go")).to_have_text(C.t("retr.page.go"))
        expect(p.locator("#rp-cancel")).to_have_text(C.t("retr.cancel"))
        if not mine:                                                                # Cancel starts nothing
            p.locator("#rp-cancel").click()
            expect(modal).to_be_hidden()
            time.sleep(0.3)
            assert not e.store.jobs
            btn.click()
            expect(modal).to_be_visible()
        if mine:
            mine_box.check()
        p.locator("#rp-go").click()
        expect(modal).to_be_hidden()
        # the whole page is the engine's `translate-page` job (a `retranslate` with no text always keeps edits)
        (job,) = until(lambda: jobs_of(e.store, "translate-page") or None, 10.0, what="the translate-page job")
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "keepEdited": not mine}
        assert job["requested_by"] == H.REVIEWER and job["status"] in ("queued", "running")
        assert jobs_of(e.store, "retranslate") == [], "the page was re-translated as a `retranslate` job"
        expect(toasts(p)).to_contain_text(C.t("retr.started"))
        # the engine brings new drafts; the page reads them
        for i, uid in enumerate(ids):
            draft(e.store, uid, f"Neu {i}", at="2026-10-19T20:00:00.000Z")
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 3})
        expect(toasts(p)).to_contain_text(C.t("retr.done"))
        for i, uid in enumerate(ids):
            wait_value(p, uid, f"Neu {i}", timeout=8000)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 8. the menu and the footer are in no export (Ruling 21:01: "Menu and footer must be excluded from all pages")
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("key", PAGES)
def test_the_menu_and_footer_texts_are_never_written_listed_or_asked_for_in_an_export(browser, key):
    """Every menu / footer text of the page (the staged units file's `chrome: true`; they are in no page JSON) is
    given BOTH a Gemini draft and a saved edit in German. Exporting the page must still write none of them, list
    none of them in any group (not even as "no translation yet": they have one), and ask the engine for the page
    only -- the file is the engine's, but what the page asks for is the page's."""
    chrome = chrome_units(key)
    assert len(chrome) >= 50, f"{key}: the staged units file marks only {len(chrome)} texts as menu or footer"
    ids = {uid for uid, _ in chrome}
    blocks = blocks_of(key)
    on_page = {b["id"] for b in blocks}
    assert not ids & on_page, "a menu or footer text is on the document page: the sweep proves nothing"
    a, b = early(key, LANG, 2)
    spy = Spy()
    marks = {}

    def seed(env):
        for i, (uid, _en) in enumerate(chrome):
            draft(env.store, uid, f"CHROME-DRAFT {i}")
            marks[uid] = {"text": f"CHROME-EDIT {i}"}
            put(env.store, uid, marks[uid], page=key)                              # a saved edit, version 1
        draft(env.store, a["id"], "Entwurf eins")
        draft(env.store, b["id"], "Entwurf zwei")
        spy.attach(env.store)

    with doc(browser, key=key, seed=seed) as e:
        p = e.page
        start_export(p, {(key, LANG)})
        until(lambda: open_job(e.store, LANG, key), 15.0, what="the export job")
        engine_done(e.store, LANG, key, make_csv(LANG, key), 2, stamp=[a["id"], b["id"]])
        expect(ex_file(p, key, LANG)).to_have_attribute("data-state", "done")
        expect(p.locator("#ex-result")).to_be_visible()
        while p.locator("#ex-result button.ex-show-more").count():                 # open every list in full
            p.locator("#ex-result button.ex-show-more").first.click()

        # what the page WROTE: the two real texts only; no chrome id, no chrome wording
        writes = spy.calls("desk-write")
        sent = [c for w in writes for c in w["body"]["changes"]]
        assert sorted(c["unit"] for c in sent) == sorted([a["id"], b["id"]]), \
            f"{key}: the export wrote {len(sent)} texts, chrome among them: {sorted({c['unit'] for c in sent} & ids)[:3]}"
        assert not {c["unit"] for c in sent} & ids
        assert "CHROME-" not in json.dumps([w["body"] for w in writes]), "chrome wording was sent in a write"
        for uid in ids:                                                            # and the saved edits are as they were
            assert dec(e.store, uid)["record"] == marks[uid] and dver(e.store, uid) == 1, uid
        # what the page ASKED the engine for: one job, this page, this language
        starts = spy.calls("desk-job-start")
        assert len(starts) == 1 and len(e.store.jobs) == 1, [c["body"] for c in starts]
        assert starts[0]["body"]["locale"] == LANG and starts[0]["body"]["kind"] == "export"
        assert starts[0]["body"]["ref"] == {"page": key}, starts[0]["body"]
        # what the page SHOWED: every list item is a text of the page, with the page's own English; none is chrome
        shown = p.eval_on_selector_all(
            "#ex-result li.ex-item",
            "els => els.map(x => [x.dataset.uid, x.dataset.page, x.dataset.lang, x.querySelector('.ex-item-text').textContent])")
        assert shown, "nothing is listed: the empty group should hold the page's other texts"
        assert not {uid for uid, *_ in shown} & ids, "a menu or footer text is listed in the result"
        by_id = {x["id"]: x for x in blocks}
        for uid, page_key, lang, text in shown:
            assert (page_key, lang) == (key, LANG) and uid in by_id, (uid, page_key, lang)
            assert text == snip(by_id[uid]["en"]), (uid, text)
        leaked = {snip(en) for _, en in chrome} & {text for *_, text in shown}
        assert leaked <= {snip(x["en"]) for x in blocks}, f"menu or footer wording is listed: {sorted(leaked)[:3]}"
        # the "no translation yet" title counts the page's texts only: all but the two that were exported
        expect(group(p, "empty").locator("h3")).to_have_text(C.tn("export.group.empty", len(blocks) - 2))
        assert len(shown) == len(blocks) - 2
