"""Robot click-tests for the READ-ONLY rules page of the localization desk (CEL-080): /admin/localization/rules/.

Version 1 of the page only shows the rules: the client picks a language and reads that language's own rule
set (one self-contained block per language since CEL-085: no shared section, and a stale `global` row is never
read), then its glossary as a plain table, then the client's keyword brief per page, collapsed. Nothing on
the page edits, saves or publishes. This file replaces the editor's two
browser files (CEL-046 / CEL-076), whose edit tests went with the editor.

A real Chromium drives the page in the click-test harness: a temporary copy of docs/, the storage's stand-in
behind a mock Worker (`harness.MockWorker`). The rules are primed with SHORT synthetic bodies (no client
text). Expected wording comes from COPY.md through `copy_text.t`, never typed here. The harness helpers are
copied from the editor's old browser file (the convention of this folder: no imports between test files). Desktop only by ruling
(2026-10-19 23:48): 1280, 1440 and 2560 wide. Every test asserts the page raised no error.
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

from localize_desk import harness as H  # noqa: E402
from localize_desk.copy_text import t  # noqa: E402

THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#rules-app[data-state="ready"]'
GLOBAL_V1 = "## Purpose\n\n- Shared rule A\n- Shared rule B\n"
DE_V1 = "## German\n\n- **Form of address:** du\n- **Markets:** CH\n"
FR_V1 = "## French\n\n- **Form of address:** vous\n"
JA_V1 = "The client has not supplied Japanese-specific rules yet.\n\n## Purpose\n\n- Generic rule A\n"
GLOSSARY_DE = "| English | German | Keep as is |\n| --- | --- | --- |\n| Language level | Sprachniveau | |\n| CEL | CEL | yes |\n"
GLOSSARY_FR = "| English | French | Keep as is |\n| --- | --- | --- |\n| Language level | Niveau de langue | |\n"
BRIEF = "## Page topic\n\nBRIEFTEXT-UNIQUE the page-level brief\n"
BRIEF_IT_HOW_LONG = "## Main keyword\n\nquanto dura un corso di inglese\n"
BRIEF_IT_COST = "## Main keyword\n\ncosto corso inglese Vancouver\n"
DE, FR, IT, JA, KO = "German", "French", "Italian", "Japanese", "Korean"


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
    seen: list = field(default_factory=list)          # (action, scope) of every call that reached the storage
    errors: list = field(default_factory=list)


def prime(store, scope: str, body: str) -> None:
    code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": 0}, "seed:client-md")
    assert code == 200 and out["ok"], out


def seed_default(store) -> None:
    prime(store, "global", GLOBAL_V1)
    prime(store, "de", DE_V1)
    prime(store, "fr", FR_V1)
    prime(store, "glossary:de", GLOSSARY_DE)
    prime(store, "glossary:fr", GLOSSARY_FR)
    prime(store, "ja", JA_V1)
    prime(store, "it", "## Italian\n\n- **Form of address:** tu\n")
    prime(store, "brief:vancouver:de", BRIEF)
    prime(store, "brief:how-long-to-learn-english:it", BRIEF_IT_HOW_LONG)
    prime(store, "brief:cost-of-studying-english:it", BRIEF_IT_COST)


@contextmanager
def rules(browser, *, lang: str = "de", seed=seed_default, http_errors: bool = False, faults: dict | None = None,
          ready: str = READY, width: int = 1440):
    """The rules page open and ready. `seed(store)` runs before the page loads; every call that reaches the
    storage after that is noted in `env.seen`. On a normal exit it asserts no page error and no console
    error happened (an HTTP failure the test asked for and a missing favicon are not errors)."""
    with desk() as (base, root, worker):
        env = Env(base=base, worker=worker, store=worker.store)
        seed(env.store)
        raw = env.store.handle

        def spy(action, body, who):
            env.seen.append((action, (body or {}).get("scope")))
            return raw(action, body, who)

        env.store.handle = spy
        env.worker.action_faults.update(faults or {})
        pg = browser.new_page(viewport={"width": width, "height": 900})
        pg.set_default_timeout(10000)
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
        pg.goto(f"{base}/admin/localization/rules/?lang={lang}")
        pg.wait_for_selector(ready, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def tab(page, code: str):
    return page.locator(f"#rulesTab-{code}")


def section_texts(page) -> list[str]:
    return page.locator("#rulesPanel section").evaluate_all("els => els.map(e => e.id)")


# ── 1. a language shows its own rules first, then its glossary, then its keyword briefs ────────────
def test_a_language_shows_its_own_rules_first_then_its_glossary_then_its_briefs(browser):
    with rules(browser) as env:
        p = env.page
        assert section_texts(p) == ["rules-lang", "rules-glossary", "rules-briefs"]     # no shared section
        expect(p.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=DE))
        expect(p.locator("#rules-glossary h2")).to_have_text(t("rules.glossary"))
        expect(p.locator("#rules-briefs h2")).to_have_text(t("rules.briefs"))
        expect(p.locator("#rules-lang li")).to_have_text(["Form of address: du", "Markets: CH"])
        text = p.locator("#rulesPanel").inner_text()
        assert "Shared rule A" not in text and "Form of address: vous" not in text      # nothing of global or fr
        expect(p.locator("#rules-lang li strong").first).to_have_text("Form of address:")
        head = p.locator("#rules-glossary table tr").first.locator("th")
        expect(head).to_have_text([t("rules.glossary.en"), DE, t("rules.glossary.keep")])
        rows = p.locator("#rules-glossary table tr").evaluate_all(
            "els => els.slice(1).map(e => Array.from(e.children).map(c => c.textContent))")
        assert rows == [["Language level", "Sprachniveau", ""], ["CEL", "CEL", t("rules.glossary.yes")]]


# ── 2. the language tabs ───────────────────────────────────────────────────────────────────────────
def test_picking_another_language_shows_that_languages_rules(browser):
    with rules(browser) as env:
        p = env.page
        expect(tab(p, "de")).to_have_attribute("aria-selected", "true")
        tab(p, "fr").click()
        expect(tab(p, "fr")).to_have_attribute("aria-selected", "true")
        expect(tab(p, "de")).to_have_attribute("aria-selected", "false")
        expect(p.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=FR))
        expect(p.locator("#rules-lang li")).to_have_text(["Form of address: vous"])
        expect(p.locator("#rules-glossary tr").nth(1)).to_contain_text("Niveau de langue")
        text = p.locator("#rulesPanel").inner_text()
        assert "Sprachniveau" not in text and "Form of address: du" not in text and "Shared rule A" not in text
        assert "lang=fr" in p.url and "lang=de" not in p.url


def test_the_language_in_the_address_is_the_one_shown_and_an_unknown_one_falls_back_to_german(browser):
    with rules(browser, lang="fr") as env:
        expect(tab(env.page, "fr")).to_have_attribute("aria-selected", "true")
        expect(env.page.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=FR))
    with rules(browser, lang="xx") as env:
        expect(tab(env.page, "de")).to_have_attribute("aria-selected", "true")


def test_the_tabs_work_from_the_keyboard(browser):
    with rules(browser) as env:
        p = env.page
        tab(p, "de").focus()
        p.keyboard.press("ArrowRight")
        expect(p.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=FR))     # the tabs are in the desk's order
        p.keyboard.press("End")
        expect(tab(p, "ar")).to_have_attribute("aria-selected", "true")
        p.keyboard.press("Home")
        expect(tab(p, "de")).to_have_attribute("aria-selected", "true")
        assert p.evaluate("document.activeElement.id") == "rulesTab-de"


# ── 3. nothing on the page can be edited ───────────────────────────────────────────────────────────
def test_nothing_on_the_page_can_be_edited_and_nothing_is_written(browser):
    with rules(browser) as env:
        p = env.page
        assert p.locator("#rules-app [contenteditable], #rules-app textarea, #rules-app input, "
                         "#rules-app select, #rules-app [role=textbox]").count() == 0
        # the only buttons are the language tabs (a notice's Try again exists only after a failed read)
        assert p.locator("#rules-app button:not([role=tab])").count() == 0
        for gone in ("#rulesUse", "#rulesUndo", "#rulesRedo", "#rulesHistory", "#rulesDrawer", "#rulesSave", "#rulesDot"):
            assert p.locator(gone).count() == 0, gone
        before = p.locator("#rulesPanel").inner_text()
        p.locator("#rules-lang li").first.click()
        p.keyboard.type("EDITED")
        p.keyboard.press("Enter")
        p.locator("#rules-glossary td").first.dblclick()
        p.keyboard.type("EDITED")
        assert p.locator("#rulesPanel").inner_text() == before
        tab(p, "fr").click()
        expect(p.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=FR))
        drafts = p.evaluate("Object.keys(localStorage).filter(k => k.indexOf('cel-rules-draft') === 0)")
        assert drafts == []
        actions = {a for a, _scope in env.seen}
        assert actions == {"desk-rules-read"}, env.seen         # the page never calls a write or history route


def test_the_stale_shared_scope_is_never_read_and_only_this_languages_scopes_are(browser):
    with rules(browser) as env:
        p = env.page
        tab(p, "fr").click()
        expect(p.locator("#rules-lang h2")).to_have_text(t("rules.lang", language=FR))
        assert "Shared rule A" not in p.content()
        scopes = {s for _a, s in env.seen}
        pages = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]
        want = {x for l in ("de", "fr") for x in [l, f"glossary:{l}"] + [f"brief:{pg}:{l}" for pg in pages]}
        assert scopes == want, scopes                                   # never 'global', never another language


def test_the_italian_tab_shows_the_clients_keyword_briefs_collapsed_under_the_pages_english_names(browser):
    with rules(browser, lang="it") as env:
        p = env.page
        boxes = p.locator("#rules-briefs details.r-brief")
        expect(boxes).to_have_count(2)                                  # only the pages with a brief, desk order
        expect(boxes.locator("summary")).to_have_text([t("page.cost-of-studying-english"),
                                                       t("page.how-long-to-learn-english")])
        assert boxes.evaluate_all("els => els.map(e => e.open)") == [False, False]     # collapsed
        expect(boxes.nth(1).locator(".r-text")).to_be_hidden()
        boxes.nth(1).locator("summary").click()
        expect(boxes.nth(1).locator(".r-text")).to_contain_text("quanto dura un corso di inglese")
        assert p.locator("#rules-app button:not([role=tab])").count() == 0          # still nothing to press


def test_a_language_without_a_keyword_brief_says_so(browser):
    with rules(browser, lang="fr") as env:
        expect(env.page.locator("#rules-briefs .r-empty")).to_have_text(t("rules.briefs.empty"))
        expect(env.page.locator("#rules-briefs details")).to_have_count(0)
        assert "quanto dura" not in env.page.locator("#rulesPanel").inner_text()


# ── 4. a language without rules, a read that fails ─────────────────────────────────────────────────
def test_a_language_the_client_wrote_no_rules_for_shows_its_block_opening_with_the_not_supplied_line(browser):
    with rules(browser, lang="ja") as env:
        p = env.page
        expect(p.locator("#rules-lang .r-p").first).to_have_text("The client has not supplied Japanese-specific rules yet.")
        expect(p.locator("#rules-lang li")).to_have_text(["Generic rule A"])
        expect(p.locator("#rules-glossary .r-empty")).to_have_text(t("rules.glossary.empty"))
        expect(p.locator("#rules-briefs .r-empty")).to_have_text(t("rules.briefs.empty"))


def test_a_language_with_no_row_at_all_says_so(browser):
    with rules(browser, lang="ko") as env:
        expect(env.page.locator("#rules-lang .r-empty")).to_have_text(t("rules.empty", language=KO))
        assert "Shared rule A" not in env.page.locator("#rulesPanel").inner_text()


def test_a_read_that_fails_says_why_and_try_again_reads_it_again(browser):
    with rules(browser, http_errors=True, ready='#rules-app[data-state="error"]',
               faults={"desk-rules-read": {"status": 500, "error": "internal"}}) as env:
        p = env.page
        notices = p.locator("#rulesPanel .r-notice")
        expect(notices).to_have_count(3)                       # the language's rules, its glossary, its briefs
        expect(notices.first).to_contain_text(t("rules.error.read"))
        env.worker.action_faults.clear()
        notices.first.get_by_role("button", name=t("rules.retry")).click()
        expect(p.locator("#rules-lang li")).to_have_count(2)
        expect(p.locator("#rulesPanel .r-notice")).to_have_count(0)
        expect(p.locator("#rules-app")).to_have_attribute("data-state", "ready")


# ── 5. one column of readable text, desktop 1280-2560 ──────────────────────────────────────────────
@pytest.mark.parametrize("width", [1280, 1440, 2560])
def test_the_text_is_one_readable_column_at_every_desktop_width(browser, width):
    with rules(browser, width=width) as env:
        p = env.page
        boxes = p.locator("#rulesPanel section").evaluate_all(
            "els => els.map(e => { const r = e.getBoundingClientRect(); return [r.left, r.width, r.top]; })")
        assert len(boxes) == 3
        assert len({round(b[0]) for b in boxes}) == 1, boxes               # one column: every section starts at the same edge
        assert [b[2] for b in boxes] == sorted(b[2] for b in boxes)         # one under the other
        assert all(b[1] <= 760 for b in boxes), boxes                       # a readable line length
        left, w = boxes[0][0], boxes[0][1]
        assert abs((left + w / 2) - width / 2) <= 60, boxes                 # the column is centred
        assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll


# ── 6. the desk's link ─────────────────────────────────────────────────────────────────────────────
def test_the_desks_translation_rules_link_opens_the_rules_page_on_the_desks_language(browser):
    with desk() as (base, root, worker):
        seed_default(worker.store)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(10000)
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        errors = []
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        try:
            pg.goto(f"{base}/admin/localization/document/?page=cost-of-studying-english&lang=fr")
            pg.wait_for_selector('#doc[data-state="ready"]', timeout=20000)
            link = pg.locator("#doc-rules")
            expect(link).to_have_text(t("doc.rules"))
            expect(link).to_have_attribute("href", "/admin/localization/rules/?lang=fr")
            # the desk moves to another language: the link follows it
            pg.locator('.doc-cell[data-page="cost-of-studying-english"][data-lang="de"]').click()
            expect(link).to_have_attribute("href", "/admin/localization/rules/?lang=de")
            link.click()
            pg.wait_for_selector(READY, timeout=20000)
            expect(tab(pg, "de")).to_have_attribute("aria-selected", "true")
            expect(pg.locator("#rules-lang li")).to_have_text(["Form of address: du", "Markets: CH"])
        finally:
            pg.close()
        assert not errors, errors
