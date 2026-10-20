"""Robot click-tests for the rules page of the localization desk (CEL-046): /admin/localization/rules/.

A real Chromium drives the page in the click-test harness: a temporary copy of docs/ with saving
switched on, the storage's stand-in behind a mock Worker (`harness.MockWorker`, whose `store` is a
`DeskStore` with the rules actions). A test plays ANOTHER writer by calling `store.handle(...)`.

What it holds the page to: the sheets render what is in use; an edit is a DRAFT kept in this browser
(localStorage cel-rules-draft-<scope>) until "Use these rules" publishes it (one desk-rules-write per
changed scope, global then language then glossary); a conflict never overwrites; a publish that stops
leaves the scopes already written in use; Undo of a publish; History and Restore; a language without
rules; the glossary; the Worker's refusals.

Rules are primed with SHORT synthetic bodies (no client text). Expected wording comes from COPY.md
through `copy_text.t` / `tn`, never typed here. Drafts are saved at once because every page gets
`window.RULES_TIMING = {draftDelay: 0}` before it loads. Desktop only (1440x900) by ruling. Every test
asserts the page raised no error and logged none to the console.
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
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright lives in the monorepo's .venv314; the CEL hook and the "
                           "browser CI job run this file with it")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import harness as H  # noqa: E402
from localize_desk.copy_text import t, tn  # noqa: E402

OTHER = "other@example.test"
READY = '#rules-app[data-state="ready"]'
TIMING = {"draftDelay": 0}
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
GLOBAL_V1 = "## Purpose\n\n- Rule A\n- Rule B\n"
DE_V1 = "## German\n\n- **Form of address:** du\n- **Markets:** CH\n"
JA_NONE = "> no rules line\n"
DE = "German"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk():
    """The harness on a free port: a temporary copy of docs/ and the mock Worker."""
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
    base: str
    worker: object
    store: object
    page: object = None
    errors: list = field(default_factory=list)


def prime(store, scope: str, body: str, email: str = "seed:client-md") -> None:
    code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": 0}, email)
    assert code == 200 and out["ok"], out


def stored(store, scope: str) -> tuple[int, str | None]:
    """(version, body) of a scope as the storage holds it; (0, None) if never published."""
    code, out = store.handle("desk-rules-read", {"scope": scope}, "reader")
    assert code == 200, out
    return out["version"], out["body"]


def other_publish(store, scope: str, body: str, base: int) -> int:
    code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": base}, OTHER)
    assert code == 200 and out["ok"], out
    return out["version"]


@contextmanager
def rules(browser, *, lang: str = "de", seed=None, http_errors: bool = False, faults: dict | None = None,
          ready: str = READY):
    """The rules page open and ready. `seed(store)` runs before the page loads. On a normal exit it
    asserts no page error and no console error happened; an HTTP failure the test asked for
    (`http_errors`: a 409 or a refusal from the Worker) and a missing favicon are not errors."""
    with desk() as (base, root, worker):
        env = Env(base=base, worker=worker, store=worker.store)
        if seed is None:
            def seed(store):
                prime(store, "global", GLOBAL_V1)
                prime(store, "de", DE_V1)
        seed(env.store)
        env.worker.action_faults.update(faults or {})       # an action that fails from the first call on
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(10000)
        # The dashboard's BugHerd tag is a third party: it is answered here with an empty script, so a console
        # error from BugHerd's own pages (CI run 39399858432: 'X-Frame-Options') can never fail a test, and the
        # no-console-error check below stays about our own code (CEL-067, CEL-078).
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
        pg.add_init_script("window.RULES_TIMING=" + json.dumps(TIMING))
        pg.goto(f"{base}/admin/localization/rules/?lang={lang}")
        pg.wait_for_selector(ready, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────
def until(fn, timeout: float = 6.0, step: float = 0.05, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    raise AssertionError(f"timed out waiting for {what}")


def note(page) -> str:
    return page.locator("#rulesNote").inner_text().strip()


def lang_item(page, n: int = 0):
    return page.locator("#sheet-lang li .ed").nth(n)


def edit_item(page, locator, suffix: str = " EDITED") -> None:
    """Click an item, type at its end, Escape: one draft change."""
    locator.click()
    page.keyboard.press("End")
    page.keyboard.type(suffix)
    page.keyboard.press("Escape")


def publish(page) -> None:
    page.click("#rulesUse")
    page.click(".r-modal .is-primary")


def add_term(page, en: str, to: str) -> None:
    """Glossary: Add a term, type both cells (one draft of glossary:de)."""
    page.get_by_role("button", name=t("rules.glossary.add")).click()
    n = page.locator(".gl-row").count() + 1
    page.locator(f'[data-rid="glossary:de#{n}.en"]').click()
    page.keyboard.type(en)
    page.keyboard.press("Escape")
    page.locator(f'[data-rid="glossary:de#{n}.to"]').click()
    page.keyboard.type(to)
    page.keyboard.press("Escape")


def draft_in_storage(page, scope: str):
    raw = page.evaluate("s => localStorage.getItem('cel-rules-draft-' + s)", scope)
    return json.loads(raw) if raw else None


def scope_name(scope: str) -> str:
    p = scope.split(":")
    if scope == "global":
        return t("rules.scope.global")
    if p[0] == "glossary":
        return t("rules.scope.glossary", language=DE)
    return t("rules.scope.lang", language=DE)


def before(key_text: str, **values) -> str:
    """The text of a COPY key up to the placeholder `{time}` (a client-formatted value)."""
    return t(key_text, time="@@", **values).split("@@")[0]


# ── 1. loads ready ────────────────────────────────────────────────────────────────────────────────
def test_loads_ready(browser):
    with rules(browser) as env:
        pg = env.page
        expect(pg.locator("#sheet-shared li .ed")).to_have_count(2)
        expect(pg.locator("#sheet-shared li .ed").nth(0)).to_have_text("Rule A")
        expect(pg.locator("#sheet-shared li .ed").nth(1)).to_have_text("Rule B")
        expect(pg.locator("#sheet-lang li .ed")).to_have_count(2)
        expect(lang_item(pg, 0)).to_have_text("Form of address: du")
        expect(lang_item(pg, 1)).to_have_text("Markets: CH")
        expect(pg.locator("#rulesNote")).to_have_text(t("rules.next", g=1, language=DE, l=1, x=0))
        expect(pg.locator("#rulesUse")).to_be_disabled()
        assert pg.evaluate("window.RulesPage.changeCount()") == 0


# ── 2. edit -> draft -> publish ───────────────────────────────────────────────────────────────────
def test_edit_draft_publish(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        expect(pg.locator("#rulesNote")).to_have_text(
            t("rules.next", g=1, language=DE, l=1, x=0) + " " + tn("rules.pending", 1))
        expect(pg.locator("#sheet-lang li.is-edited")).to_have_count(1)
        expect(pg.locator("#sheet-lang li.is-edited .under")).to_contain_text(t("rules.edited"))
        until(lambda: draft_in_storage(pg, "de"), what="the draft in localStorage")
        d = draft_in_storage(pg, "de")
        assert "du EDITED" in d["body"] and d["baseVersion"] == 1
        assert stored(env.store, "de") == (1, DE_V1)           # a draft never changes what is in use
        expect(pg.locator("#rulesUse")).to_be_enabled()
        publish(pg)
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2")
        v, body = stored(env.store, "de")
        assert body == "## German\n\n- **Form of address:** du EDITED\n- **Markets:** CH\n"
        expect(pg.locator("#rulesNote")).to_have_text(t("rules.next", g=1, language=DE, l=2, x=0))
        expect(pg.locator("#rulesUse")).to_be_disabled()
        until(lambda: draft_in_storage(pg, "de") is None, what="the draft cleared")
        assert stored(env.store, "global") == (1, GLOBAL_V1)   # untouched scopes stay as they were


# ── 3. reload keeps a draft ───────────────────────────────────────────────────────────────────────
def test_reload_keeps_draft(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        until(lambda: draft_in_storage(pg, "de"), what="the draft in localStorage")
        pg.reload()
        pg.wait_for_selector(READY)
        expect(lang_item(pg, 0)).to_have_text("Form of address: du EDITED")
        expect(pg.locator("#rulesNote")).to_have_text(
            t("rules.next", g=1, language=DE, l=1, x=0) + " " + tn("rules.pending", 1))
        assert stored(env.store, "de") == (1, DE_V1)


# ── 4. conflict ───────────────────────────────────────────────────────────────────────────────────
def test_conflict_see_theirs_then_undo(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        theirs = "## German\n\n- Their rule\n"
        assert other_publish(env.store, "de", theirs, 1) == 2
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_be_visible()
        expect(notice).to_contain_text(before("rules.conflict", name=OTHER, scope=scope_name("de"), n=2))
        assert stored(env.store, "de") == (2, theirs)          # a conflict never overwrites
        notice.get_by_role("button", name=t("rules.conflict.theirs")).click()
        expect(pg.locator("#sheet-lang .r-notice")).to_have_count(0)
        expect(lang_item(pg, 0)).to_have_text("Their rule")
        expect(pg.locator("#rulesNote")).to_have_text(t("rules.next", g=1, language=DE, l=2, x=0))
        pg.click("#rulesUndo")
        expect(lang_item(pg, 0)).to_have_text("Form of address: du EDITED")
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))
        assert stored(env.store, "de") == (2, theirs)


# ── 5. partly in use ──────────────────────────────────────────────────────────────────────────────
def test_partly_in_use(browser):
    # The harness fault answers EVERY call of an action, so the second write is made to fail by
    # another writer: global (written first) succeeds, de answers 409.
    # Three scopes change (global, de, glossary) and the MIDDLE one conflicts: the run must stop there, so the
    # glossary after it keeps its old version and its draft (review fix 7: a runner that kept writing after a
    # failure passed the two-scope version of this test).
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, pg.locator("#sheet-shared li .ed").first)
        edit_item(pg, lang_item(pg, 0))
        add_term(pg, "Tuition", "Kursgebuehren")
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 3))
        theirs = "## German\n\n- Their rule\n"
        other_publish(env.store, "de", theirs, 1)
        publish(pg)
        expect(pg.locator("#rulesToasts")).to_contain_text(t("rules.toast.partial", done=scope_name("global"),
                                                             rest=scope_name("de") + ", " + scope_name("glossary:de")))
        v, body = stored(env.store, "global")
        assert v == 2 and "Rule A EDITED" in body
        assert stored(env.store, "de") == (2, theirs)          # the other writer's version, not ours
        assert stored(env.store, "glossary:de") == (0, None)   # after the stop: not written
        until(lambda: draft_in_storage(pg, "glossary:de"), what="the glossary draft")
        assert "Kursgebuehren" in draft_in_storage(pg, "glossary:de")["body"]
        expect(pg.locator("#sheet-lang .r-notice").first).to_be_visible()
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 2))


# ── 6. undo of a publish ──────────────────────────────────────────────────────────────────────────
def test_undo_of_a_publish(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        publish(pg)
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2")
        expect(pg.locator("#rulesUndo")).to_be_enabled()
        pg.click("#rulesUndo")
        until(lambda: stored(env.store, "de")[0] == 3, what="de version 3")
        assert stored(env.store, "de") == (3, DE_V1)
        expect(lang_item(pg, 0)).to_have_text("Form of address: du")
        expect(pg.locator("#rulesNote")).to_have_text(t("rules.next", g=1, language=DE, l=3, x=0))


# ── 7. history + restore ──────────────────────────────────────────────────────────────────────────
def test_history_and_restore(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        publish(pg)
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2")
        pg.click("#rulesHistory")
        cards = pg.locator("#rulesTimeline .vcard").filter(has=pg.locator(".vc-s", has_text=scope_name("de")))
        expect(cards).to_have_count(2)
        expect(cards.nth(0).locator("strong")).to_have_text("v2")
        expect(cards.nth(1).locator("strong")).to_have_text("v1")
        expect(cards.nth(0)).to_contain_text(t("rules.inuse"))
        expect(cards.nth(0).get_by_role("button", name=t("rules.restore"))).to_have_count(0)
        cards.nth(1).get_by_role("button", name=t("rules.restore")).click()
        pg.click(".r-modal .is-primary")
        until(lambda: stored(env.store, "de")[0] == 3, what="de version 3")
        assert stored(env.store, "de") == (3, DE_V1)
        expect(pg.locator("#rulesToasts")).to_contain_text(t("rules.toast.restored", n=1, m=2))
        expect(lang_item(pg, 0)).to_have_text("Form of address: du")


# ── 8. a language without rules ───────────────────────────────────────────────────────────────────
def test_empty_language_suggested(browser):
    def seed(store):
        prime(store, "global", GLOBAL_V1)
        prime(store, "ja", JA_NONE)

    with rules(browser, lang="ja", seed=seed) as env:
        pg = env.page
        expect(pg.locator("#sheet-lang .empty .empty-t")).to_have_text(t("rules.empty", language="Japanese"))
        expect(pg.locator("#sheet-lang .sugg dt").first).to_have_text(t("rules.suggested.first"))
        expect(pg.locator("#sheet-lang .sugg dt")).to_have_count(4)
        pg.get_by_role("button", name=t("rules.suggested.use")).click()
        expect(pg.locator("#sheet-lang .empty")).to_have_count(0)
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))
        assert pg.evaluate("window.RulesPage.changeCount()") > 0
        expect(pg.locator("#sheet-lang li .ed").first).to_contain_text(t("rules.suggested.first"))
        expect(pg.locator("#rulesToasts")).to_contain_text(t("rules.toast.suggested"))
        assert stored(env.store, "ja") == (1, JA_NONE)


# ── 9. glossary ───────────────────────────────────────────────────────────────────────────────────
def test_glossary_add_term_publish(browser):
    with rules(browser) as env:
        pg = env.page
        assert stored(env.store, "glossary:de") == (0, None)
        pg.get_by_role("button", name=t("rules.glossary.add")).click()
        expect(pg.locator(".gl-row")).to_have_count(1)
        en = pg.locator('[data-rid="glossary:de#2.en"]')
        to = pg.locator('[data-rid="glossary:de#2.to"]')
        en.click()
        pg.keyboard.type("Tuition")
        pg.keyboard.press("Escape")
        to.click()
        pg.keyboard.type("Studiengebuehren")
        pg.keyboard.press("Escape")
        pg.locator(".gl-row input[type=checkbox]").check()
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))
        publish(pg)
        until(lambda: stored(env.store, "glossary:de")[0] == 1, what="glossary:de version 1")
        v, body = stored(env.store, "glossary:de")
        lines = body.strip().split("\n")
        assert [c.strip() for c in lines[0].strip("|").split("|")] == ["English", DE, "Keep as is"]
        assert re.fullmatch(r"\|\s*---\s*\|\s*---\s*\|\s*---\s*\|", lines[1]), lines[1]
        assert [c.strip() for c in lines[2].strip("|").split("|")] == ["Tuition", "Studiengebuehren", "yes"]
        assert len(lines) == 3
        expect(pg.locator("#rulesNote")).to_have_text(t("rules.next", g=1, language=DE, l=1, x=1))
        expect(pg.locator(".gl-row")).to_have_count(1)


# ── 10. the Worker refuses ────────────────────────────────────────────────────────────────────────
def test_errors_cap_then_signed_out(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        env.worker.action_faults["desk-rules-write"] = {"status": 429, "error": "over the cap"}
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_have_text(re.compile("^" + re.escape(t("rules.error.cap"))))
        assert stored(env.store, "de") == (1, DE_V1)
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))   # the draft is kept
        # the fault answers every call: a second try fails the new way
        env.worker.action_faults["desk-rules-write"] = {"status": 401, "error": "signed out"}
        notice.get_by_role("button", name=t("rules.retry")).click()
        expect(pg.locator(".r-modal")).to_be_visible()          # Try again goes through the confirm (fix 9)
        pg.click(".r-modal .is-primary")
        expect(pg.locator("#sheet-lang .r-notice")).to_contain_text(t("rules.error.signed_out"))
        assert stored(env.store, "de") == (1, DE_V1)
        # and when the storage works again the same draft goes in
        env.worker.action_faults.pop("desk-rules-write")
        pg.locator("#sheet-lang .r-notice").get_by_role("button", name=t("rules.retry")).click()
        pg.click(".r-modal .is-primary")
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2 after the fault cleared")


# ── 11. review round 1 (CEL-046) ─────────────────────────────────────────────
def test_the_rail_marks_the_section_in_view(browser):
    """Ruling 07:30: the rail marks the section being read, as the desk's outline does."""
    with rules(browser) as env:
        pg = env.page
        pg.set_viewport_size({"width": 1440, "height": 500})       # room to scroll a heading past the line
        first = pg.locator(".ol-item").first
        expect(first).to_have_attribute("aria-current", "true")
        pg.evaluate("() => document.getElementById('sec-glossary').scrollIntoView({ block: 'start' })")
        cur = pg.locator('.ol-item[data-target="sec-glossary"]')
        expect(cur).to_have_attribute("aria-current", "true")
        expect(cur).to_have_class(re.compile(r"\bis-cur\b"))
        assert pg.locator('.ol-item[aria-current="true"]').count() == 1
        # at the very end of the page the last heading on screen is current, even if it never passed the line
        pg.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        expect(pg.locator('.ol-item[data-target="sec-briefs"]')).to_have_attribute("aria-current", "true")
        pg.evaluate("() => window.scrollTo(0, 0)")
        expect(first).to_have_attribute("aria-current", "true")


def test_a_draft_reloaded_after_a_newer_publish_meets_the_409_and_never_overwrites_it(browser):
    """Spec §2: a draft is {body, baseVersion}. A draft made on v1, reloaded after someone published v2,
    goes out against v1, so the Worker's 409 brings up the conflict notice and v2 stays."""
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        until(lambda: draft_in_storage(pg, "de"), what="the draft in localStorage")
        theirs = "## German\n\n- Their rule\n"
        assert other_publish(env.store, "de", theirs, 1) == 2
        pg.reload()
        pg.wait_for_selector(READY)
        expect(lang_item(pg, 0)).to_have_text("Form of address: du EDITED")
        assert draft_in_storage(pg, "de")["baseVersion"] == 1       # never rewritten to the fresh version
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_be_visible()
        expect(notice).to_contain_text(before("rules.conflict", name=OTHER, scope=scope_name("de"), n=2))
        assert stored(env.store, "de") == (2, theirs)


def test_a_rules_read_that_fails_says_it_could_not_be_read(browser):
    """Spec §3: a read that fails (a 500) says the read's own sentence, not 'could not be put in use'."""
    with rules(browser, http_errors=True, ready="#sheet-lang .r-notice",       # nothing loads: no 'ready' state
               faults={"desk-rules-read": {"status": 500, "error": "internal"}}) as env:
        pg = env.page
        notice = pg.locator("#sheet-lang .r-notice").first
        expect(notice).to_contain_text(t("rules.error.read"))
        assert t("rules.error") not in notice.inner_text()           # not the publish failure's sentence


def test_undo_after_a_first_publish_never_leaves_an_empty_draft(browser):
    """A scope's first publish is not an Undo step (no empty version exists); the edits before it are. Undoing
    them must not leave an empty draft, which no publish could ever write (the Worker refuses an empty body)."""
    with rules(browser) as env:
        pg = env.page
        add_term(pg, "Tuition", "Kursgebuehren")
        publish(pg)
        until(lambda: stored(env.store, "glossary:de")[0] == 1, what="glossary:de version 1")
        # The store answers before the page has taken the answer in: wait until the page has settled (the
        # publish toast is up, Use is off and Undo is on) so the loop below is not racing the page.
        expect(pg.locator("#rulesToasts")).to_contain_text(t("rules.toast.used", list=scope_name("glossary:de")))
        expect(pg.locator("#rulesUse")).to_be_disabled()
        expect(pg.locator("#rulesUndo")).to_be_enabled()
        clicks = 0
        for _ in range(10):
            if pg.locator("#rulesUndo").is_disabled():
                break
            pg.click("#rulesUndo")
            clicks += 1
            time.sleep(0.1)
        assert clicks >= 1, "no Undo was clicked: the test proved nothing"
        assert pg.evaluate("window.RulesPage.changeCount()") == 0
        expect(pg.locator("#rulesUse")).to_be_disabled()
        d = draft_in_storage(pg, "glossary:de")
        assert d is None or d["body"].strip(), d
        assert stored(env.store, "glossary:de")[0] == 1


def test_a_page_brief_is_written_as_its_own_scope(browser):
    """Ruling 23:32 (1): a brief is the scope brief:<page>:<lang>, the page key the engine's KEYWORD_FILES uses."""
    page_key = "cost-of-studying-english"
    with rules(browser) as env:
        pg = env.page
        card = pg.locator(".bcard", has=pg.locator("h4", has_text=t("page." + page_key)))
        card.get_by_role("button", name=t("rules.brief.add")).click()
        slot = pg.locator(f'[data-rid^="brief:{page_key}:de#"]').first
        slot.click()
        pg.keyboard.type("Keyword: Kosten Sprachkurs")
        pg.keyboard.press("Escape")
        publish(pg)
        until(lambda: stored(env.store, f"brief:{page_key}:de")[0] == 1, what="the brief's version 1")
        v, body = stored(env.store, f"brief:{page_key}:de")
        assert "Keyword: Kosten Sprachkurs" in body and body.lstrip().startswith("## ")


def test_keep_mine_sends_that_scopes_draft_only(browser):
    """Spec §3: Keep mine re-sends YOUR draft of that scope, not every changed scope of the language."""
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        theirs = "## German\n\n- Their rule\n"
        other_publish(env.store, "de", theirs, 1)
        publish(pg)
        expect(pg.locator("#sheet-lang .r-notice")).to_be_visible()
        edit_item(pg, pg.locator("#sheet-shared li .ed").first)     # an edit made after the confirm
        pg.locator("#sheet-lang .r-notice").get_by_role("button", name=t("rules.conflict.mine")).click()
        until(lambda: stored(env.store, "de")[0] == 3, what="de version 3, mine")
        assert "du EDITED" in stored(env.store, "de")[1]
        assert stored(env.store, "global") == (1, GLOBAL_V1)        # not sent without a confirm
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))
