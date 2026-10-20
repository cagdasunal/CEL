"""Robot click-tests for the READ-ONLY rules page of the localization desk (CEL-080): /admin/localization/rules/.

The page only shows the rules: the client picks a language and reads that language's own rule set (one
self-contained block per language since CEL-085: no shared section, and a stale `global` row is never read).
Since CEL-089 (option A of CEL-088) it opens with a summary (N requests, three Done-by cards that filter), then
the client's numbered sections with one row per request and how the tool carries it out, the glossary as a plain
table and the client's keyword brief per page as a collapsed card. Nothing on the page edits, saves or
publishes; the three cards only filter. This file replaces the editor's two
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
DE_V1 = "## 7. Language rules\n\n- **Form of address:** du\n- **Markets:** CH\n"
FR_V1 = "## 7. Language rules\n\n- **Form of address:** vous\n"
JA_V1 = "The client has not supplied Japanese-specific rules yet.\n\n## 2. Workflow\n\n- Generic rule A\n"
# CEL-089: a body with a lead-in, a table and a line the Done-by map names (the map is patched into the served page)
DE_A = ("## 2. Workflow\n\n- SYNTH-CHECKED line\n- SYNTH-PLAIN line\n\n## 6. Numbers\n\nIn practice:\n\n"
        "| Element | DE |\n|---|---|\n| SYNTH-CELL | x |\n\n## 12. Flag\n\n- SYNTH-NOTYET line\n\n## 13. Other\n\n- SYNTH-HIDDEN\n")


def fnv(text: str) -> str:
    """rules_page.js fnv(): FNV-1a 32 of the trimmed UTF-8 text (build_done_by.py in the monorepo is the same)."""
    x = 0x811C9DC5
    for b in text.strip().encode("utf-8"):
        x = ((x ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{x:08x}"
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


def seed_default(store, de: str = DE_V1) -> None:
    prime(store, "global", GLOBAL_V1)
    prime(store, "de", de)
    prime(store, "fr", FR_V1)
    prime(store, "glossary:de", GLOSSARY_DE)
    prime(store, "glossary:fr", GLOSSARY_FR)
    prime(store, "ja", JA_V1)
    prime(store, "it", "## 7. Language rules\n\n- **Form of address:** tu\n")
    prime(store, "brief:vancouver:de", BRIEF)
    prime(store, "brief:how-long-to-learn-english:it", BRIEF_IT_HOW_LONG)
    prime(store, "brief:cost-of-studying-english:it", BRIEF_IT_COST)


@contextmanager
def rules(browser, *, lang: str = "de", seed=seed_default, http_errors: bool = False, faults: dict | None = None,
          ready: str = READY, width: int = 1440, done_by: dict | None = None):
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
        if done_by:
            def patch(route):
                html = route.fetch().text()
                add = ",".join(f'"{k}":{json.dumps(v)}' for k, v in done_by.items())
                assert '"de":{' in html
                route.fulfill(status=200, content_type="text/html", body=html.replace('"de":{', '"de":{' + add + ",", 1))
            pg.route(re.compile(r".*/admin/localization/rules/(\?.*)?$"), patch)
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


def words(page):
    return page.locator("#rules-lang .r-req:visible .r-words")


# ── 1. a language shows its own rules first, then its glossary, then its keyword briefs ────────────
def test_a_language_shows_its_own_rules_first_then_its_glossary_then_its_briefs(browser):
    with rules(browser) as env:
        p = env.page
        # no shared section; our quality checks under the client's sections (CEL-099)
        assert section_texts(p) == ["rules-s7", "rules-quality", "rules-glossary", "rules-briefs"]
        expect(p.locator("#rules-s7 h2")).to_have_text("Language rules")
        expect(p.locator("#rules-glossary h2")).to_have_text(t("rules.glossary"))
        expect(p.locator("#rules-briefs h2")).to_have_text(t("rules.briefs"))
        expect(words(p)).to_have_text(["Form of address: du", "Markets: CH"])
        text = p.locator("#rulesPanel").inner_text()
        assert "Shared rule A" not in text and "Form of address: vous" not in text      # nothing of global or fr
        expect(p.locator("#rules-lang .r-words strong").first).to_have_text("Form of address:")
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
        expect(words(p)).to_have_text(["Form of address: vous"])
        expect(p.locator("#rules-glossary tr").nth(1)).to_contain_text("Niveau de langue")
        text = p.locator("#rulesPanel").inner_text()
        assert "Sprachniveau" not in text and "Form of address: du" not in text and "Shared rule A" not in text
        assert "lang=fr" in p.url and "lang=de" not in p.url


def test_the_language_in_the_address_is_the_one_shown_and_an_unknown_one_falls_back_to_german(browser):
    with rules(browser, lang="fr") as env:
        expect(tab(env.page, "fr")).to_have_attribute("aria-selected", "true")
        expect(words(env.page)).to_have_text(["Form of address: vous"])
    with rules(browser, lang="xx") as env:
        expect(tab(env.page, "de")).to_have_attribute("aria-selected", "true")


def test_the_tabs_work_from_the_keyboard(browser):
    with rules(browser) as env:
        p = env.page
        tab(p, "de").focus()
        p.keyboard.press("ArrowRight")
        expect(words(p)).to_have_text(["Form of address: vous"])     # the tabs are in the desk's order
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
        # the only buttons are the language tabs and the three Done-by cards, which filter (a notice's Try again
        # exists only after a failed read)
        assert p.locator("#rules-app button:not([role=tab])").count() == 3
        assert p.locator("#rules-app button.r-stat[aria-pressed]").count() == 3
        for gone in ("#rulesUse", "#rulesUndo", "#rulesRedo", "#rulesHistory", "#rulesDrawer", "#rulesSave", "#rulesDot"):
            assert p.locator(gone).count() == 0, gone
        before = p.locator("#rulesPanel").inner_text()
        p.locator("#rules-lang .r-words").first.click()
        p.keyboard.type("EDITED")
        p.keyboard.press("Enter")
        p.locator("#rules-glossary td").first.dblclick()
        p.keyboard.type("EDITED")
        assert p.locator("#rulesPanel").inner_text() == before
        tab(p, "fr").click()
        expect(words(p)).to_have_text(["Form of address: vous"])
        drafts = p.evaluate("Object.keys(localStorage).filter(k => k.indexOf('cel-rules-draft') === 0)")
        assert drafts == []
        actions = {a for a, _scope in env.seen}
        assert actions == {"desk-rules-read"}, env.seen         # the page never calls a write or history route


def test_the_stale_shared_scope_is_never_read_and_only_this_languages_scopes_are(browser):
    with rules(browser) as env:
        p = env.page
        tab(p, "fr").click()
        expect(words(p)).to_have_text(["Form of address: vous"])
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
        expect(boxes.locator("summary .r-brief-name")).to_have_text([t("page.cost-of-studying-english"),
                                                                     t("page.how-long-to-learn-english")])
        expect(boxes.locator("summary .r-by.prompt")).to_have_count(2)            # each brief is in the prompt
        assert boxes.evaluate_all("els => els.map(e => e.open)") == [False, False]     # collapsed
        expect(boxes.nth(1).locator(".r-text")).to_be_hidden()
        boxes.nth(1).locator("summary").click()
        expect(boxes.nth(1).locator(".r-text")).to_contain_text("quanto dura un corso di inglese")
        assert p.locator("#rules-app button:not([role=tab])").count() == 3          # still only the three filters


def test_a_language_without_a_keyword_brief_says_so(browser):
    with rules(browser, lang="fr") as env:
        expect(env.page.locator("#rules-briefs .r-empty")).to_have_text(t("rules.briefs.empty"))
        expect(env.page.locator("#rules-briefs details")).to_have_count(0)
        assert "quanto dura" not in env.page.locator("#rulesPanel").inner_text()


# ── 4. a language without rules, a read that fails ─────────────────────────────────────────────────
def test_a_language_the_client_wrote_no_rules_for_shows_its_block_opening_with_the_not_supplied_line(browser):
    with rules(browser, lang="ja") as env:
        p = env.page
        expect(p.locator("#rules-lang .r-intro").first).to_have_text("The client has not supplied Japanese-specific rules yet.")
        expect(words(p)).to_have_text(["Generic rule A"])
        expect(p.locator("#rules-lang .r-big")).to_have_text(t("rules.summary", n=1))
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
        expect(notices).to_have_count(1)                       # the language's rules: nothing else is drawn without them
        expect(notices.first).to_contain_text(t("rules.error.read"))
        env.worker.action_faults.clear()
        notices.first.get_by_role("button", name=t("rules.retry")).click()
        expect(words(p)).to_have_count(2)
        expect(p.locator("#rulesPanel .r-notice")).to_have_count(0)
        expect(p.locator("#rules-app")).to_have_attribute("data-state", "ready")


# ── 5. option A at every desktop width: summary on top, the section list beside the requests ───────────────
@pytest.mark.parametrize("width", [1280, 1440, 2560])
def test_the_summary_sits_on_top_and_the_section_list_beside_the_requests_at_every_desktop_width(browser, width):
    with rules(browser, width=width) as env:
        p = env.page
        box = lambda sel: p.locator(sel).first.evaluate(  # noqa: E731
            "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.bottom]; }")
        stats = p.locator(".r-stat").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().top))")
        assert len(stats) == 3 and len(set(stats)) == 1, stats                      # the three cards in one row
        rail, doc, lead = box(".r-rail"), box(".r-doc"), box(".r-lead")
        assert lead[3] <= rail[1] and lead[3] <= doc[1], (lead, rail, doc)          # the summary is above both
        assert rail[0] + rail[2] <= doc[0], (rail, doc)                            # the list left of the requests
        assert p.locator(".r-rail a").count() == 4                     # §7, our quality checks, glossary, briefs
        assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll


# ── 5b. Done by: the summary counts, the filter, the map ─────────────────────────────────────────
def seed_a(store) -> None:
    seed_default(store, de=DE_A)


DONE_A = {fnv("- SYNTH-CHECKED line"): ["check", "meta"], fnv("- SYNTH-NOTYET line"): ["none", "slug"]}


def test_each_request_shows_how_it_is_carried_out_and_the_summary_counts_them(browser):
    with rules(browser, seed=seed_a, done_by=DONE_A) as env:
        p = env.page
        assert section_texts(p)[:3] == ["rules-s2", "rules-s6", "rules-s12"]          # §13 is not a section shown
        assert "SYNTH-HIDDEN" not in p.locator("#rulesPanel").inner_text()
        expect(words(p)).to_have_text(["SYNTH-CHECKED line", "SYNTH-PLAIN line", "ElementSYNTH-CELLDEx",
                                       "SYNTH-NOTYET line"])
        expect(p.locator("#rules-s6 .r-ctx")).to_have_text(["In practice:"])          # a lead-in is not a request
        by = p.locator("#rules-lang .r-req").evaluate_all("els => els.map(e => e.dataset.by)")
        assert by == ["check", "prompt", "prompt", "none"]
        expect(p.locator("#rules-lang .r-req .r-how")).to_have_text([
            t("rules.how.check.meta"), t("rules.how.prompt"), t("rules.how.prompt"),
            t("rules.how.none.slug")])
        expect(p.locator(".r-big")).to_have_text(t("rules.summary", n=4))
        expect(p.locator(".r-stat .r-num")).to_have_text(["1", "2", "1"])
        expect(p.locator(".r-filterline")).to_have_text(t("rules.filter.all", n=4))


def test_a_card_filters_the_requests_and_pressing_it_again_or_show_all_clears_it(browser):
    with rules(browser, seed=seed_a, done_by=DONE_A) as env:
        p = env.page
        p.locator('.r-stat[data-by="prompt"]').click()
        expect(p.locator('.r-stat[data-by="prompt"]')).to_have_attribute("aria-pressed", "true")
        expect(words(p)).to_have_text(["SYNTH-PLAIN line", "ElementSYNTH-CELLDEx"])
        expect(p.locator(".r-filterline")).to_contain_text(t("rules.filter.some", k=2, n=4))
        # §2 and §6 only: §12 holds no such request, and the quality checks, glossary and briefs hold none (CEL-099)
        expect(p.locator(".r-rail a .r-rail-n")).to_have_text(["1", "1"])
        assert section_texts(p) == ["rules-s2", "rules-s6"]
        p.locator('.r-stat[data-by="prompt"]').click()
        expect(words(p)).to_have_count(4)
        p.locator('.r-stat[data-by="none"]').click()
        expect(words(p)).to_have_text(["SYNTH-NOTYET line"])
        p.get_by_role("button", name=t("rules.filter.clear")).click()
        expect(words(p)).to_have_count(4)
        tab(p, "fr").click()                                                     # another language starts unfiltered
        expect(p.locator(".r-stat[aria-pressed=true]")).to_have_count(0)
        actions = {a for a, _scope in env.seen}
        assert actions == {"desk-rules-read"}, env.seen                        # filtering reads nothing new, writes nothing


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
            pg.locator('#doc-tab-de').click()                               # CEL-069: the language tab (the page stays)
            expect(link).to_have_attribute("href", "/admin/localization/rules/?lang=de")
            link.click()
            pg.wait_for_selector(READY, timeout=20000)
            expect(tab(pg, "de")).to_have_attribute("aria-selected", "true")
            expect(words(pg)).to_have_text(["Form of address: du", "Markets: CH"])
        finally:
            pg.close()
        assert not errors, errors
