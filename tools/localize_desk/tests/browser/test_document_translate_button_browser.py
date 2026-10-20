"""Robot click-tests for the ONE Translate page button of the document page (desk v2, CEL-073).

The page used to offer two page-level buttons that did nearly the same thing: "Translate page" (the first-translation
confirm, a `translate-page` job that keeps edited texts) and "Re-translate page" (a window with "Include my edits", the
same `translate-page` job with `keepEdited` off when ticked). The operator: they make no sense, and Translate page
after a translation must translate again. This file holds the page to the one button:
  * in every state exactly ONE button reads "Translate page", and nothing outside a window reads "Re-translate page";
  * a page with no translation: it asks the first-translation confirm and starts a `translate-page` job;
  * a page that has one: the same button opens the whole-page window, and its job keeps the reviewer's edited texts
    (`keepEdited: true`) unless "Include my edits" is ticked, in which case the window first says how many edited
    texts that would replace;
  * if the export module is missing the button still translates (the confirm);
  * the paragraph-level "Re-translate" is where it was.

A real Chromium drives `/admin/localization/document/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text`, never typed here.
The harness helpers are COPIED from test_document_export_browser.py (the convention of this folder: no imports between
test files). Desktop only (Ruling 23:48).
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

OTHER = "other@example.test"

PAGE_KEY = "cost-of-studying-english"

PAGES = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]

LANGS = ["de", "fr", "es", "pt", "it", "ja", "ko", "ar"]

LANG = "de"

READY = '#doc[data-state="ready"]'

# Autosave in ~0.2 s instead of 2 s / 10 s; the poll for a running job every 0.2 s.
TIMING = {"quiet": 150, "maxWait": 600, "undoPause": 120, "poll": 200, "timeout": 5000}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")

MARK = re.compile(r'<a wg-[0-9]+="">|</a>|<br>')


# ── the harness, copied from test_document_export_browser.py ────────────────────────────────────────
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


def draft(store, uid, text, lang=LANG, at="2026-10-01T10:00:00.000Z"):
    store.drafts[(lang, uid)] = {"text": text, "arrivedAt": at}


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


def blocks_of(key: str = PAGE_KEY) -> list[dict]:
    return _stage_data(key)["blocks"]


def jobs_of(store, kind: str, lang: str = LANG) -> list[dict]:
    return [j for j in store.jobs.values() if j["locale"] == lang and j["kind"] == kind]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ONE Translate page
# ══════════════════════════════════════════════════════════════════════════════════════════════════
TRANSLATE_BUTTONS_JS = """() => [...document.querySelectorAll('button')]
    .filter(b => b.getClientRects().length > 0 && getComputedStyle(b).visibility !== 'hidden')
    .map(b => ({id: b.id, text: b.textContent.trim().replace(/\\s+/g, ' ')}))
    .filter(b => /translate page/i.test(b.text))"""


def visible_translate_buttons(page) -> list[dict]:
    return page.evaluate(TRANSLATE_BUTTONS_JS)


def page_jobs(store, lang=LANG) -> list[dict]:
    return jobs_of(store, "translate-page", lang)


def toasts(page):
    return page.locator("#doc-toasts")


def edited(env, uids, lang=LANG):
    """The reviewer's own edit on each text (a saved record with `text`, version 1)."""
    for i, uid in enumerate(uids):
        put(env.store, uid, {"text": f"MEINE {i}"}, lang=lang)


def approved(env, uids, lang=LANG):
    """An approval with no text of its own (`tray: 'csv'`): the website's wording, approved as it stands."""
    for uid in uids:
        put(env.store, uid, {"tray": "csv", "approvedAgainst": "Original"}, lang=lang)


def translating(env, key, lang=LANG, keep=True):
    """A translate-page job is out in this language for `key`, as another reviewer's click (or another tab) leaves it;
    the page under test has not seen it start."""
    code, body = env.store.handle("desk-job-start", {"locale": lang, "kind": "translate-page",
                                                     "ref": {"page": key, "keepEdited": keep}}, H.REVIEWER)
    assert code == 200, body
    return body["job"]


def test_in_every_state_exactly_one_button_reads_translate_page_and_none_reads_re_translate_page(browser):
    """No translation (the banner's button), a translation (the header's), and a job under way (the header's, off):
    one visible button each time, always the same words, and the old second page button is gone."""
    (a,) = pick(_stage_data(), 1)
    label = C.t("doc.translate")
    with doc(browser, lang="fr") as e:                                       # no translation in French
        assert visible_translate_buttons(e.page) == [{"id": "doc-banner-translate", "text": label}]
        assert e.page.locator("#doc-retranslate-page").count() == 0
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf")) as e:      # a draft in German
        assert visible_translate_buttons(e.page) == [{"id": "doc-translate", "text": label}]
        assert e.page.locator("#doc-retranslate-page").count() == 0
        expect(e.page.locator("#doc-translate")).to_be_enabled()
        e.page.locator("#doc-translate").click()
        expect(e.page.locator("#rp-modal")).to_be_visible()                  # the window's own buttons are not the page's
        e.page.locator("#rp-go").click()
        until(lambda: len(page_jobs(e.store)) == 1, what="the translate-page job")
        # the job is the desk's own now: the banner says Gemini is working and the one button is off
        assert [b["id"] for b in visible_translate_buttons(e.page)] == ["doc-translate"]
        expect(e.page.locator("#doc-translate")).to_be_disabled()
        expect(e.page.locator("#doc-banner-text")).to_have_text(C.t("doc.job.queued"))


def test_a_page_with_no_translation_asks_the_first_translation_confirm_and_starts_a_translate_page_job(browser):
    with doc(browser, lang="fr") as e:
        e.page.locator("#doc-banner-translate").click()
        expect(e.page.locator("#doc-confirm")).to_be_visible()
        expect(e.page.locator("#rp-modal")).to_be_hidden()                   # not the whole-page window
        e.page.locator("#doc-confirm-ok").click()
        until(lambda: len(page_jobs(e.store, "fr")) == 1, what="the translate-page job")
        assert json.loads(page_jobs(e.store, "fr")[0]["ref"]) == {"page": PAGE_KEY, "keepEdited": True}
        assert jobs_of(e.store, "retranslate", "fr") == []


def test_a_page_with_a_translation_opens_the_window_and_its_job_keeps_the_reviewers_edits(browser):
    a, b, c = pick(_stage_data(), 3)

    def seed(env):
        for i, uid in enumerate((a, b, c)):
            draft(env.store, uid, f"Entwurf {i}")
        edited(env, (a,))

    with doc(browser, seed=seed) as e:
        p = e.page
        p.locator("#doc-translate").click()
        expect(p.locator("#rp-modal")).to_be_visible()
        expect(p.locator("#doc-confirm")).to_be_hidden()                     # not the first-translation confirm
        expect(p.locator("#rp-title")).to_have_text(C.t("retr.page.title"))
        expect(p.locator("#rp-mine")).not_to_be_checked()                    # edits are kept unless the reviewer says so
        expect(p.locator("#rp-count")).to_be_hidden()
        p.locator("#rp-go").click()
        (job,) = until(lambda: page_jobs(e.store) or None, 10.0, what="the translate-page job")
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "keepEdited": True}
        assert jobs_of(e.store, "retranslate") == [], "the page was sent as a `retranslate` job"
        assert field_value(p, a) == "MEINE 0"                                # the edited text is untouched


def test_the_window_cancel_and_escape_start_nothing_and_give_the_button_back_its_focus(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf")) as e:
        p = e.page
        for how in ("cancel", "escape"):
            p.locator("#doc-translate").click()
            expect(p.locator("#rp-modal")).to_be_visible()
            if how == "cancel":
                p.locator("#rp-cancel").click()
            else:
                p.keyboard.press("Escape")
            expect(p.locator("#rp-modal")).to_be_hidden()
            expect(p.locator("#doc-translate")).to_be_focused()
        time.sleep(0.3)
        assert not e.store.jobs and "desk-job-start" not in e.worker.calls


@pytest.mark.parametrize("n_edited,n_approved", [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)])
def test_the_window_names_how_many_edited_or_approved_texts_include_my_edits_would_replace(browser, n_edited, n_approved):
    """The engine re-asks every SETTLED text when `keepEdited` is off: an edit OR an approval with no text of its own
    (`tools/localize/job.py` `settled()`). The count names both, so an approved text is not replaced unannounced."""
    ids = pick(_stage_data(), 4)
    n = n_edited + n_approved

    def seed(env):
        for i, uid in enumerate(ids):
            draft(env.store, uid, f"Entwurf {i}")
        edited(env, ids[:n_edited])
        approved(env, ids[n_edited:n])

    with doc(browser, seed=seed) as e:
        p = e.page
        p.locator("#doc-translate").click()
        count = p.locator("#rp-count")
        expect(count).to_be_hidden()                                         # unticked: nothing would be replaced
        p.locator("#rp-mine").check()
        if n == 0:
            expect(count).to_be_hidden()                                     # ticked, but nothing settled: nothing to name
        else:
            expect(count).to_be_visible()
            expect(count).to_have_text(C.tn("retr.page.count", n))
        p.locator("#rp-mine").uncheck()
        expect(count).to_be_hidden()
        p.locator("#rp-mine").check()
        p.locator("#rp-go").click()
        (job,) = until(lambda: page_jobs(e.store) or None, 10.0, what="the translate-page job")
        assert json.loads(job["ref"]) == {"page": PAGE_KEY, "keepEdited": False}   # ticked: the edits are handed over


def test_the_count_is_recounted_each_time_the_window_opens(browser):
    ids = pick(_stage_data(), 2)

    def seed(env):
        for i, uid in enumerate(ids):
            draft(env.store, uid, f"Entwurf {i}")
        edited(env, ids[:1])

    with doc(browser, seed=seed) as e:
        p = e.page
        p.locator("#doc-translate").click()
        p.locator("#rp-mine").check()
        expect(p.locator("#rp-count")).to_have_text(C.tn("retr.page.count", 1))
        p.locator("#rp-cancel").click()
        edit(p, ids[1], "NEU GETIPPT")                                       # a second edit, made in the page
        until(lambda: dtext(e.store, ids[1]) == "NEU GETIPPT" or None, 10.0, what="the edit saved")
        p.locator("#doc-translate").click()
        expect(p.locator("#rp-mine")).not_to_be_checked()                    # reopened unticked, count hidden again
        expect(p.locator("#rp-count")).to_be_hidden()
        p.locator("#rp-mine").check()
        expect(p.locator("#rp-count")).to_have_text(C.tn("retr.page.count", 2))


def test_without_the_export_module_the_one_button_still_translates_through_the_confirm(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf")) as e:
        p = e.page
        p.evaluate("() => { delete window.DocDesk.retranslatePage; }")
        p.locator("#doc-translate").click()
        expect(p.locator("#doc-confirm")).to_be_visible()
        expect(p.locator("#rp-modal")).to_be_hidden()
        p.locator("#doc-confirm-ok").click()
        until(lambda: len(page_jobs(e.store)) == 1, what="the translate-page job")
        assert json.loads(page_jobs(e.store)[0]["ref"]) == {"page": PAGE_KEY, "keepEdited": True}


def test_the_paragraph_level_re_translate_is_where_it_was(browser):
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf")) as e:
        p = e.page
        tool = blk(p, a).locator(".doc-tool-retranslate")
        expect(tool).to_have_count(1)
        expect(tool).to_have_text(C.t("retr.button"))
        tgt(p, a).click()                                                    # focus the text so its toolbar floats up
        expect(tool).to_be_visible()
        tool.click()
        expect(p.locator("#rt-modal")).to_be_visible()
        expect(p.locator("#rp-modal")).to_be_hidden()


def test_the_count_includes_an_approved_text_that_has_no_edit(browser):
    """The case behind the count (live data: two German approvals with no text, decided 2026-10-06): the page has one
    edit and one approval, and the box says two."""
    a, b, c = pick(_stage_data(), 3)

    def seed(env):
        for i, uid in enumerate((a, b, c)):
            draft(env.store, uid, f"Entwurf {i}")
        edited(env, (a,))
        approved(env, (b,))

    with doc(browser, seed=seed) as e:
        p = e.page
        p.locator("#doc-translate").click()
        p.locator("#rp-mine").check()
        expect(p.locator("#rp-count")).to_have_text(C.tn("retr.page.count", 2))
        assert "exported" in C.tn("retr.page.count", 2), "the line names the exported texts too"   # CEL-093: v2 has no Approve


def test_a_translated_page_whose_language_is_busy_with_another_page_is_queued_not_refused(browser):
    """Before this patch the same click went through the desk's confirm and was queued behind the running page; the window's
    job started outside that queue and got a 409 and a 'busy' toast. Now it waits its turn and says so."""
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf"), http_errors=True) as e:   # the 409 starts the queue
        p = e.page
        other = translating(e, "vancouver")                               # another page runs in German
        p.locator("#doc-translate").click()
        p.locator("#rp-go").click()
        expect(p.locator("#doc-banner-text")).to_have_text(
            C.t("doc.job.waiting", page=C.t("page.vancouver"), language=C.t("lang.de")))
        expect(p.locator("#doc-translate")).to_be_disabled()
        assert C.t("retr.busy") not in (toasts(p).inner_text() or ""), "the click was refused with the busy toast"
        assert len(page_jobs(e.store)) == 1                                # nothing started yet: ours waits
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 0})    # the running page ends...
        until(lambda: len(page_jobs(e.store)) == 2, 10.0, what="the queued page's job")     # ...and ours starts by itself
        queued = [j for j in page_jobs(e.store) if j["id"] != other["id"]][0]
        assert json.loads(queued["ref"]) == {"page": PAGE_KEY, "keepEdited": True}


@pytest.mark.parametrize("mine", [False, True])
def test_a_queued_window_job_keeps_the_choice_made_in_the_window(browser, mine):
    """Waiting changes nothing about what was chosen: the box's answer is the job's `keepEdited` when its turn comes."""
    (a,) = pick(_stage_data(), 1)
    with doc(browser, seed=lambda env: draft(env.store, a, "Entwurf"), http_errors=True) as e:   # the 409 starts the queue
        p = e.page
        other = translating(e, "vancouver")
        p.locator("#doc-translate").click()
        if mine:
            p.locator("#rp-mine").check()
        p.locator("#rp-go").click()
        expect(p.locator("#doc-banner-text")).to_have_text(
            C.t("doc.job.waiting", page=C.t("page.vancouver"), language=C.t("lang.de")))
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 0})
        until(lambda: len(page_jobs(e.store)) == 2, 10.0, what="the queued page's job")
        queued = [j for j in page_jobs(e.store) if j["id"] != other["id"]][0]
        assert json.loads(queued["ref"]) == {"page": PAGE_KEY, "keepEdited": not mine}


def test_the_texts_a_queued_window_job_replaces_are_adopted_when_it_finishes(browser):
    """`done` runs after the queue's turn, not at the click: the new draft is shown, and the edited wording goes on the
    undo stack, as in the unqueued case."""
    (a,) = pick(_stage_data(), 1)

    def seed(env):
        draft(env.store, a, "Alt")
        edited(env, (a,))

    with doc(browser, seed=seed, http_errors=True) as e:      # the 409 starts the queue
        p = e.page
        translating(e, "vancouver")
        p.locator("#doc-translate").click()
        p.locator("#rp-mine").check()
        p.locator("#rp-go").click()
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 0})
        until(lambda: len(page_jobs(e.store)) == 2, 10.0, what="the queued page's job")
        draft(e.store, a, "NEU VOM ENGINE", at="2026-10-20T20:00:00.000Z")
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 1})
        expect(toasts(p)).to_contain_text(C.t("retr.done"))
        wait_value(p, a, "NEU VOM ENGINE", timeout=8000)


def test_include_my_edits_on_a_page_already_translating_keeps_the_edit_and_runs_its_own_job_after(browser):
    """Round 2 review, fix 1: this page's own job was started elsewhere, keeping edits, and this window never saw it start.
    Translate page -> Include my edits -> Go meets a 409 for the same page. The window's choice must not ride on that job
    (its `done` would put the old drafts over the edit): the running job ends with the edit untouched, then the window's
    own job starts with `keepEdited: false`, and only ITS end brings the new draft (the edit goes on the undo stack)."""
    (a,) = pick(_stage_data(), 1)

    def seed(env):
        draft(env.store, a, "Alt")
        edited(env, (a,))

    with doc(browser, seed=seed, http_errors=True) as e:              # the same-page start meets a 409
        p = e.page
        running = translating(e, PAGE_KEY)                                # this page, keeping edits, started elsewhere
        p.locator("#doc-translate").click()
        p.locator("#rp-mine").check()
        p.locator("#rp-go").click()
        expect(p.locator("#doc-translate")).to_be_disabled()             # the desk watches the running job now
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 0})
        until(lambda: len(page_jobs(e.store)) == 2, 10.0, what="the window's own job after the running one")
        ours = [j for j in page_jobs(e.store) if j["id"] != running["id"]][0]
        assert json.loads(ours["ref"]) == {"page": PAGE_KEY, "keepEdited": False}
        assert dec(e.store, a)["record"] == {"text": "MEINE 0"}, "the running job's end touched the edit"
        expect(blk(p, a).locator(".doc-tgt")).to_have_text("MEINE 0")
        # the window's own job ends: the new draft is adopted, as when nothing was running
        draft(e.store, a, "NEU VOM ENGINE", at="2026-10-20T20:00:00.000Z")
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 1})
        expect(toasts(p)).to_contain_text(C.t("retr.done"))
        wait_value(p, a, "NEU VOM ENGINE", timeout=8000)


@pytest.mark.parametrize("mine,running_keeps", [(False, True), (True, False), (False, False)],
                         ids=["box-off", "box-on-running-includes-edits", "box-off-running-includes-edits"])
def test_a_page_already_translating_as_asked_starts_nothing_more_and_the_window_choice_rides_on_nothing(
        browser, mine, running_keeps):
    """The running job for this page already does what the window asked (or more): it is watched, no second job starts,
    and the window's `done` never runs for it (only the desk's own 'done' toast)."""
    (a,) = pick(_stage_data(), 1)

    def seed(env):
        draft(env.store, a, "Alt")
        edited(env, (a,))

    with doc(browser, seed=seed, http_errors=True) as e:              # the same-page start meets a 409
        p = e.page
        translating(e, PAGE_KEY, keep=running_keeps)
        p.locator("#doc-translate").click()
        if mine:
            p.locator("#rp-mine").check()
        p.locator("#rp-go").click()
        expect(p.locator("#doc-translate")).to_be_disabled()
        e.store.finish_job(LANG, "translate-page", "done", {"drafts": 0})
        expect(toasts(p)).to_contain_text(C.t("doc.job.done"))
        expect(p.locator("#doc-translate")).to_be_enabled()
        time.sleep(1.0)                                                   # a second job would have started by now
        assert len(page_jobs(e.store)) == 1, page_jobs(e.store)
        assert C.t("retr.done") not in (toasts(p).inner_text() or "")
        if running_keeps:
            assert dec(e.store, a)["record"] == {"text": "MEINE 0"}, "the edit was touched"
