"""Robot click-tests for the EDITOR on the Rules tab and the Word list tab of the rules page (CEL-113): /admin/localization/rules/.

Option A of CEL-110 with the top menu of option B: every rule shows its ID as a tag (the ` [DE-2]` at the end of
its line, shown apart), Edit opens the row with Save / Cancel, Remove drops it, "Add a rule" ends each section.
Each Save, Remove and Add is ONE `desk-rules-write` that applies at once (no draft, no publish step), sent with
the version the page read as `baseVersion`; the desk's note "<ID> applied." carries Undo (one more write); a 409
says someone changed the language first and keeps the typed text. The "Done by" pill is looked up on the line
WITHOUT its ID, so a rule the map names keeps its pill.

The Word list tab (from section 5 down) is one table of the language's words (scope `words:<lang>`: Term, Translation,
Type) with Type chips, a search, "Add a word" and Edit / Remove per row. Each Save, Remove and Add is ONE write of that
scope with its own version; the rows of the body are changed one by one, so a line the page does not know stays as it
was. A language with nothing written in `words:<lang>` starts from its `glossary:<lang>`. Import is tested in its own file.

The harness helpers are COPIED from test_rules_readonly_browser.py (the convention of this folder: no imports
between test files). The rules are SHORT synthetic bodies (no client text). Expected wording comes from COPY.md
through `copy_text.t`, never typed here. Desktop only by ruling (2026-10-19 23:48). Every test asserts the page
raised no error.
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
from localize_desk.copy_text import t, tn  # noqa: E402

THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#rules-app[data-state="ready"]'
DE = "German"
DE_ED = ("## 2. Workflow\n\n- Alpha rule one [DE-1]\n- Beta rule two [DE-2]\n\n"
         "## 6. Numbers\n\n- Gamma rule three [DE-3]\n")


def fnv(text: str) -> str:
    """rules_page.js fnv(): FNV-1a 32 of the trimmed UTF-8 text."""
    x = 0x811C9DC5
    for b in text.strip().encode("utf-8"):
        x = ((x ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{x:08x}"


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
    calls: list = field(default_factory=list)        # (action, body) of every call that reached the storage
    errors: list = field(default_factory=list)

    def writes(self) -> list:
        return [b for a, b in self.calls if a == "desk-rules-write"]

    def body(self, scope: str = "de") -> str:
        return self.store.rules[scope]["body"]


def seed_ed(store) -> None:
    code, out = store.handle("desk-rules-write", {"scope": "de", "body": DE_ED, "baseVersion": 0}, "seed:client-md")
    assert code == 200 and out["ok"], out


@contextmanager
def rules(browser, *, lang: str = "de", seed=seed_ed, done_by: dict | None = None, width: int = 1440, tab: str = "rules"):
    """The rules page open and ready; `env.calls` notes every call that reaches the storage after the page loaded."""
    with desk() as (base, root, worker):
        env = Env(base=base, worker=worker, store=worker.store)
        seed(env.store)
        raw = env.store.handle

        def spy(action, body, who):
            env.calls.append((action, dict(body or {})))
            return raw(action, body, who)

        env.store.handle = spy
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
            url = (msg.location or {}).get("url", "") or ""
            if msg.type == "error" and not url.endswith("/favicon.ico") and not (
                    "Failed to load resource" in msg.text and "__worker" in url):
                env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.goto(f"{base}/admin/localization/rules/?lang={lang}" + ("" if tab == "rules" else f"&tab={tab}"))
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def rule(page, rid: str):
    return page.locator(f'#rules-lang .r-rule[data-id="{rid}"]')


def words(page):
    return page.locator("#rules-lang .r-rule:visible .r-words")


def toast(page):
    return page.locator("#rules-toasts .toast")


# ── 1. IDs as tags, the page tabs ─────────────────────────────────────────────────────────────────
def test_every_rule_shows_its_id_as_a_tag_and_the_words_do_not_repeat_it(browser):
    with rules(browser) as env:
        p = env.page
        expect(p.locator("#rules-lang .r-rule .r-id")).to_have_text(["DE-1", "DE-2", "DE-3"])
        expect(words(p)).to_have_text(["Alpha rule one", "Beta rule two", "Gamma rule three"])
        assert "[DE-" not in p.locator("#rulesPanel").inner_text()
        expect(p.locator(".r-big")).to_have_text(tn("rules.count", 3))
        expect(rule(p, "DE-2").get_by_role("button", name=t("rules.edit"))).to_have_count(1)
        expect(rule(p, "DE-2").get_by_role("button", name=t("rules.remove"))).to_have_count(1)


def test_the_top_menu_has_rules_word_list_and_import_and_rules_is_open(browser):
    with rules(browser) as env:
        p = env.page
        nav = p.locator(".r-nav .r-nav-b")
        expect(nav).to_have_text([t("rules.tab.rules"), t("rules.tab.words"), t("rules.tab.import")])
        expect(nav.nth(0)).to_have_attribute("aria-selected", "true")
        nav.nth(1).click()
        expect(nav.nth(1)).to_have_attribute("aria-selected", "true")
        assert p.locator("#rules-lang").count() == 0 and "tab=words" in p.url and "lang=de" in p.url
        nav.nth(0).click()
        expect(words(p)).to_have_count(3)
        assert not [c for c in env.calls if c[0] != "desk-rules-read"]


def test_the_done_by_pill_is_looked_up_on_the_line_without_its_id_and_an_edited_line_falls_back_to_the_prompt(browser):
    done = {fnv("- Alpha rule one"): ["check", "meta"]}          # the map was built from the line WITHOUT the ID
    with rules(browser, done_by=done) as env:
        p = env.page
        expect(rule(p, "DE-1").locator(".r-by")).to_have_text(t("rules.by.check"))
        expect(rule(p, "DE-2").locator(".r-by")).to_have_text(t("rules.by.prompt"))
        rule(p, "DE-1").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("Alpha rule one, reworded")
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(rule(p, "DE-1").locator(".r-words")).to_have_text("Alpha rule one, reworded")
        expect(rule(p, "DE-1").locator(".r-by")).to_have_text(t("rules.by.prompt"))      # edited text: not in the map


# ── 2. Edit + Save applies at once, Undo, Cancel, empty ─────────────────────────────────────────────
def test_edit_then_save_applies_at_once_with_one_write_and_the_desk_note(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        box = p.locator("#rules-ed")
        expect(box).to_have_value("Beta rule two")                       # the text without its ID
        expect(box).to_be_focused()
        expect(rule(p, "DE-2")).to_have_class(re.compile("is-editing"))
        box.fill("Beta rule changed")
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(toast(p)).to_contain_text(t("rules.applied", id="DE-2"))
        expect(toast(p).get_by_role("button", name=t("rules.undo"))).to_have_count(1)
        expect(words(p)).to_have_text(["Alpha rule one", "Beta rule changed", "Gamma rule three"])
        assert p.locator("#rules-lang textarea").count() == 0            # the row closed
        writes = env.writes()
        assert len(writes) == 1, writes                                  # ONE write
        assert writes[0]["scope"] == "de" and writes[0]["baseVersion"] == 1
        assert env.body() == DE_ED.replace("Beta rule two [DE-2]", "Beta rule changed [DE-2]")     # the ID kept on the line
        assert env.store.rules["de"]["version"] == 2
        assert p.evaluate("Object.keys(localStorage).filter(k => k.indexOf('cel-rules-draft') === 0)") == []


def test_undo_writes_the_text_back(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("Beta rule changed")
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        toast(p).get_by_role("button", name=t("rules.undo")).click()
        expect(words(p)).to_have_text(["Alpha rule one", "Beta rule two", "Gamma rule three"])
        expect(toast(p)).to_have_count(0)
        assert env.body() == DE_ED and env.store.rules["de"]["version"] == 3
        assert len(env.writes()) == 2 and env.writes()[1]["baseVersion"] == 2      # the Undo is the one more write


def test_cancel_and_an_unchanged_save_write_nothing_and_an_empty_rule_is_refused(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("typed and abandoned")
        p.get_by_role("button", name=t("rules.cancel")).click()
        expect(words(p)).to_have_text(["Alpha rule one", "Beta rule two", "Gamma rule three"])
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        p.get_by_role("button", name=t("rules.save"), exact=True).click()             # nothing changed
        assert p.locator("#rules-lang textarea").count() == 0
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("   ")
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(p.locator("#rules-lang .r-editbox [role=alert]")).to_have_text(t("rules.empty.rule"))
        p.keyboard.press("Escape")
        assert p.locator("#rules-lang textarea").count() == 0
        assert env.writes() == [] and env.body() == DE_ED


# ── 3. Remove, Add ──────────────────────────────────────────────────────────────────────────────────
def test_remove_drops_the_rule_at_once_with_one_write_and_undo_brings_it_back(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-2").get_by_role("button", name=t("rules.remove")).click()
        expect(toast(p)).to_contain_text(t("rules.removed", id="DE-2"))
        expect(words(p)).to_have_text(["Alpha rule one", "Gamma rule three"])
        expect(p.locator(".r-big")).to_have_text(tn("rules.count", 2))
        assert len(env.writes()) == 1 and env.body() == DE_ED.replace("- Beta rule two [DE-2]\n", "")
        toast(p).get_by_role("button", name=t("rules.undo")).click()
        expect(words(p)).to_have_count(3)
        assert env.body() == DE_ED


def test_add_a_rule_ends_the_section_takes_the_next_id_and_a_removed_number_is_not_given_again(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-3").get_by_role("button", name=t("rules.remove")).click()           # DE-3 is the highest ever used
        expect(words(p)).to_have_count(2)
        sec = p.locator("#rules-s2")
        sec.get_by_role("button", name=t("rules.add")).click()
        expect(sec.get_by_role("button", name=t("rules.add"))).to_be_hidden()           # hidden while its row is open
        expect(sec.locator(".r-rule.is-new .r-id")).to_have_text(t("rules.new.id", lang="DE"))
        expect(sec.locator(".r-rule.is-new #rules-ed")).to_have_attribute("placeholder", t("rules.new.placeholder"))
        sec.locator("#rules-ed").fill("Delta rule four")
        sec.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(toast(p).last).to_contain_text(t("rules.applied", id="DE-4"))
        expect(sec.locator(".r-rule .r-id")).to_have_text(["DE-1", "DE-2", "DE-4"])
        expect(sec.locator(".r-rule .r-words")).to_have_text(["Alpha rule one", "Beta rule two", "Delta rule four"])
        assert len(env.writes()) == 2                                                    # the Remove and the Add: one write each
        assert env.body() == "## 2. Workflow\n\n- Alpha rule one [DE-1]\n- Beta rule two [DE-2]\n- Delta rule four [DE-4]\n\n## 6. Numbers\n\n"
        assert [a for a, _ in env.calls].count("desk-rules-history") == 1               # the counter looked at the history once


def test_known_limit_a_removed_rule_number_comes_back_once_its_version_left_the_history_window(browser):
    """KNOWN LIMIT (CEL-113 Found, the Manager's call): the page learns the highest number a language ever used from
    `desk-rules-history`, which answers only the last RULES_HISTORY_LIMIT versions (the Worker's LIMIT 50). A number removed
    longer ago than that is given again. A full floor needs a field on the RE 3 route; when it exists this test flips."""
    from localize_desk.desk_store import RULES_HISTORY_LIMIT

    def seed(store):
        seed_scope(store, "de", "## 2. Workflow\n\n- Alpha [DE-1]\n- Beta [DE-2]\n- Gamma [DE-3]\n")       # version 1 holds DE-3
        for n in range(1, RULES_HISTORY_LIMIT + 1):                                                          # then DE-3 is gone from every version
            code, out = store.handle("desk-rules-write", {"scope": "de", "baseVersion": n,
                                                          "body": f"## 2. Workflow\n\n- Alpha {n} [DE-1]\n- Beta [DE-2]\n"}, "seed:client-md")
            assert code == 200 and out["ok"], out

    with rules(browser, seed=seed) as env:
        p = env.page
        sec = p.locator("#rules-s2")
        sec.get_by_role("button", name=t("rules.add")).click()
        sec.locator("#rules-ed").fill("Delta")
        sec.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(toast(p).last).to_contain_text(t("rules.applied", id="DE-3"))               # DE-3 again: the floor is the window


def test_add_a_rule_writes_to_the_language_it_was_written_in_when_the_tab_is_switched_during_the_history_read(browser):
    """Review round 1, fix 1: Save on an Add first reads the history for the next number. A switch to another,
    already-read language while that read is out must not send this body, or its ID, to the other language."""
    FR_ED = "## 2. Workflow\n\n- Un [FR-1]\n"

    def seed(store):
        seed_ed(store)
        seed_scope(store, "fr", FR_ED)

    with rules(browser, seed=seed) as env:
        p = env.page
        p.locator("#rulesTab-fr").click()                                                # French read once, so the switch below reads nothing
        expect(p.locator("#rules-lang .r-rule .r-id")).to_have_text(["FR-1"])
        p.locator("#rulesTab-de").click()
        expect(p.locator("#rules-lang .r-rule .r-id")).to_have_text(["DE-1", "DE-2", "DE-3"])
        arrived, gate = threading.Event(), threading.Event()
        inner = env.store.handle

        def hold(action, body, who):
            if action == "desk-rules-history":
                arrived.set()
                gate.wait(30)
            return inner(action, body, who)

        env.store.handle = hold
        sec = p.locator("#rules-s2")
        sec.get_by_role("button", name=t("rules.add")).click()
        sec.locator("#rules-ed").fill("Delta rule four")
        sec.get_by_role("button", name=t("rules.save"), exact=True).click()
        assert arrived.wait(10), "the Add did not read the history"
        p.locator("#rulesTab-fr").click()                                                # while the read is out
        expect(p.locator("#rules-lang .r-rule .r-id")).to_have_text(["FR-1"])
        gate.set()
        expect(toast(p).last).to_contain_text(t("rules.applied", id="DE-4"))
        assert [b["scope"] for b in env.writes()] == ["de"]                              # the one write, to German
        assert "- Delta rule four [DE-4]\n" in env.body("de") and "[FR-" not in env.body("de")
        assert env.body("fr") == FR_ED and env.store.rules["fr"]["version"] == 1          # French untouched
        expect(p.locator("#rules-lang .r-rule .r-id")).to_have_text(["FR-1"])            # the French tab shown stays French
        assert [b["scope"] for a, b in env.calls if a == "desk-rules-history"] == ["de"]


# ── 4. a stale base keeps the typed text ──────────────────────────────────────────────────────────
def test_a_409_says_someone_changed_the_language_and_keeps_the_typed_text(browser):
    with rules(browser) as env:
        p = env.page
        rule(p, "DE-2").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("My careful rewrite")
        # someone else applies a change first: the page's version (1) is now stale
        code, out = env.store.handle("desk-rules-write", {"scope": "de", "baseVersion": 1,
                                                          "body": DE_ED.replace("Alpha rule one", "Alpha by someone else")}, "other@example.com")
        assert code == 200, out
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(p.locator("#rules-lang .r-editbox [role=alert]")).to_have_text(t("rules.apply.stale", language=DE))
        expect(p.locator("#rules-ed")).to_have_value("My careful rewrite")            # the typed text is still there
        expect(rule(p, "DE-2")).to_have_class(re.compile("is-editing"))
        expect(toast(p)).to_have_count(0)
        assert "My careful rewrite" not in env.body() and "Alpha by someone else" in env.body()
        assert env.store.rules["de"]["version"] == 2                                  # nothing of ours was written


def test_a_refused_write_says_why_and_keeps_the_row_open(browser):
    with rules(browser) as env:
        p = env.page
        env.worker.action_faults["desk-rules-write"] = {"status": 400, "error": "invalid: body is not valid text"}
        rule(p, "DE-1").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#rules-ed").fill("Alpha reworded")
        p.get_by_role("button", name=t("rules.save"), exact=True).click()
        expect(p.locator("#rules-lang .r-editbox [role=alert]")).to_have_text(
            t("rules.apply.failed", reason="invalid: body is not valid text"))
        expect(p.locator("#rules-ed")).to_have_value("Alpha reworded")
        assert env.body() == DE_ED


# ── 5. The Word list tab: one table, Type chips, search, Add a word, Edit / Remove ─────────────────────
KO = "Korean"
KEEP, ALWAYS, KW = t("words.keep"), t("words.always"), t("words.keyword")
HEAD = "| Term | Translation | Type |\n|---|---|---|\n"
WORDS_DE = HEAD + ("| Acme | | Keep as is |\n| Alpha Hall | Alpha-Halle | Always translate as |\n"
                   "| Zeta Lab | | Keep as is |\n| Vorlage | | Search keyword |\n")
GLOSSARY_DE = ("| English | German | Keep as is |\n| --- | --- | --- |\n| Acme | Acme | yes |\n| Alpha Hall | Alpha-Halle | |\n"
               "| Neither | | |\n")      # a row with neither `yes` nor a rendering is not a word (rules_store.words_from_glossary)


def seed_scope(store, scope: str, body: str) -> None:
    code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": 0}, "seed:client-md")
    assert code == 200 and out["ok"], out


def seed_words(store) -> None:
    seed_ed(store)
    seed_scope(store, "words:de", WORDS_DE)


def seed_glossary(store) -> None:
    seed_ed(store)
    seed_scope(store, "glossary:de", GLOSSARY_DE)


def wterms(page):
    return page.locator("#rules-words .r-wtable tbody tr[data-type]:visible .r-w-term")


def wrow(page, term: str):
    return page.locator(f'#rules-words .r-wtable tbody tr[data-type]:has(.r-w-term:text-is("{term}"))')


def wwrites(env) -> list:
    return [b for b in env.writes() if str(b.get("scope", "")).startswith("words:")]


def read_scopes(env) -> list:
    return [b["scope"] for a, b in env.calls if a == "desk-rules-read"]


def wbody(env, lang: str = "de") -> str:
    return env.store.rules[f"words:{lang}"]["body"]


def open_add(page):
    page.get_by_role("button", name=t("words.add")).click()


def save(page):
    page.get_by_role("button", name=t("rules.save"), exact=True).click()


def test_the_word_list_is_one_table_with_type_pills_and_chips_that_count(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        expect(p.locator(".r-nav .r-nav-b").nth(1)).to_have_attribute("aria-selected", "true")
        expect(p.locator("#rules-words .r-wtable thead th")).to_have_text(
            [t("words.term"), t("words.translation"), t("words.type"), t("words.actions")])
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall", "Zeta Lab", "Vorlage"])
        cells = p.locator("#rules-words .r-wtable tbody tr[data-type] td:nth-child(2)")
        expect(cells).to_have_text([t("words.same"), "Alpha-Halle", t("words.same"), "–" + t("words.none.sr")])
        expect(p.locator("#rules-words .r-type")).to_have_text([KEEP, ALWAYS, KEEP, KW])
        chips = p.locator("#rules-words .r-chip")
        expect(chips).to_have_text([f"{t('words.all')} 4", f"{KEEP} 2", f"{ALWAYS} 1", f"{KW} 1"])
        expect(chips.nth(0)).to_have_attribute("aria-pressed", "true")
        assert read_scopes(env) == ["words:de"]                       # its own scope; no glossary behind a written list
        assert [a for a, _ in env.calls if a != "desk-rules-read"] == []


def test_add_a_word_sits_with_the_count_and_the_chips_and_the_search_have_their_own_row_below(browser):
    """Operator OL-335: Add a word and the search must not sit side by side as if one control (CEL-110's revised A)."""
    def both(store):
        seed_words(store)
        seed_scope(store, "words:fr", HEAD + "| Acme | | Keep as is |\n")

    with rules(browser, seed=both, tab="words") as env:
        p = env.page
        head, tools = p.locator("#rules-words .r-sum-a"), p.locator("#rules-words .r-wtools")
        expect(head.locator(".r-big")).to_have_text(tn("words.count", 4))
        expect(head.get_by_role("button", name=t("words.add"))).to_have_count(1)
        expect(tools.get_by_role("button", name=t("words.add"))).to_have_count(0)
        expect(tools.locator(".r-chip")).to_have_count(4)
        expect(tools.get_by_placeholder(t("words.search"))).to_have_count(1)
        add = head.get_by_role("button", name=t("words.add")).bounding_box()
        chips, search = tools.locator(".r-chips").bounding_box(), tools.locator(".r-search").bounding_box()
        assert add["y"] + add["height"] <= search["y"], (add, search)                    # the button is a row above the search
        assert search["x"] >= chips["x"] + chips["width"], (chips, search)                # the search is right of the chips,
        assert abs((search["y"] + search["height"] / 2) - (chips["y"] + chips["height"] / 2)) < 4     # on their row
        p.locator("#rulesTab-fr").click()
        expect(p.locator("#rules-words .r-sum-a .r-big")).to_have_text(tn("words.count", 1))   # "1 word"


def test_a_language_without_words_starts_from_its_glossary_and_the_first_save_writes_the_whole_table(browser):
    with rules(browser, seed=seed_glossary, tab="words") as env:
        p = env.page
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall"])
        expect(p.locator("#rules-words .r-type")).to_have_text([KEEP, ALWAYS])
        assert read_scopes(env) == ["words:de", "glossary:de"]
        open_add(p)
        p.locator("#words-ed-term").fill("Beta Cafe")
        p.locator("#words-ed-tr").fill("Beta-Kaffee")
        save(p)
        expect(toast(p)).to_contain_text(t("words.applied", term="Beta Cafe"))
        assert [(b["scope"], b["baseVersion"]) for b in wwrites(env)] == [("words:de", 0)]
        start = HEAD + "| Acme |  | Keep as is |\n| Alpha Hall | Alpha-Halle | Always translate as |\n"
        assert wbody(env) == start + "| Beta Cafe | Beta-Kaffee | Always translate as |\n"
        assert env.store.rules["glossary:de"]["body"] == GLOSSARY_DE   # the glossary itself is not touched
        toast(p).get_by_role("button", name=t("rules.undo")).click()   # a blank body cannot be written: the starting table is
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall"])
        assert wbody(env) == start and len(wwrites(env)) == 2


def test_a_language_with_no_words_says_so_and_its_first_word_starts_the_table(browser):
    with rules(browser, lang="ko", seed=seed_ed, tab="words") as env:
        p = env.page
        expect(p.locator("#rules-words .r-empty").first).to_have_text(t("words.empty", language=KO))
        assert read_scopes(env) == ["words:ko", "glossary:ko"]
        open_add(p)
        expect(p.locator("#rules-words .r-empty").first).to_be_hidden()
        p.locator("#words-ed-type").select_option("keep")
        p.locator("#words-ed-term").fill("Kappa")
        save(p)
        expect(wterms(p)).to_have_text(["Kappa"])
        assert wbody(env, "ko") == HEAD + "| Kappa |  | Keep as is |\n"
        assert [(b["scope"], b["baseVersion"]) for b in wwrites(env)] == [("words:ko", 0)]
        toast(p).get_by_role("button", name=t("rules.undo")).click()
        expect(wterms(p)).to_have_count(0)
        assert wbody(env, "ko") == HEAD


def test_add_a_word_opens_one_row_hides_its_button_and_one_save_writes_one_line_at_the_end(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        add = p.get_by_role("button", name=t("words.add"))
        add.click()
        expect(add).to_be_hidden()                                              # hidden while its row is open
        expect(p.locator("#words-ed-term")).to_be_focused()
        expect(p.locator("#words-ed-term")).to_have_attribute("placeholder", t("words.new.term"))
        expect(p.locator("#words-ed-type")).to_have_value("always")
        expect(p.locator("#words-ed-tr")).to_have_attribute("placeholder", t("words.translation"))
        p.locator("#words-ed-term").fill("Beta Cafe")
        p.locator("#words-ed-tr").fill("Beta-Kaffee")
        save(p)
        expect(toast(p)).to_contain_text(t("words.applied", term="Beta Cafe"))
        expect(toast(p).get_by_role("button", name=t("rules.undo"))).to_have_count(1)
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall", "Zeta Lab", "Vorlage", "Beta Cafe"])
        expect(add).to_be_visible()
        assert p.locator("#rules-words .is-adding").count() == 0
        assert [(b["scope"], b["baseVersion"]) for b in wwrites(env)] == [("words:de", 1)]      # ONE write, the scope's own version
        assert wbody(env) == WORDS_DE + "| Beta Cafe | Beta-Kaffee | Always translate as |\n"
        assert env.store.rules["de"]["version"] == 1                                            # the rules scope was not written
        assert p.evaluate("Object.keys(localStorage).filter(k => k.indexOf('cel-rules-draft') === 0)") == []


def test_the_translation_field_is_off_unless_the_type_is_always_translate_as_and_the_stored_line_follows_the_type(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        open_add(p)
        tr, kind = p.locator("#words-ed-tr"), p.locator("#words-ed-type")
        kind.select_option("keep")
        expect(tr).to_be_disabled()
        expect(tr).to_have_attribute("placeholder", t("words.new.none"))
        kind.select_option("always")
        expect(tr).to_be_enabled()
        kind.select_option("kw")
        expect(tr).to_be_disabled()
        p.locator("#words-ed-term").fill("Kappa phrase")
        save(p)
        expect(wrow(p, "Kappa phrase").locator(".r-type")).to_have_text(KW)
        assert wbody(env).endswith("| Kappa phrase |  | Search keyword |\n")


def test_edit_a_word_changes_its_own_line_and_nothing_else_moves(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        wrow(p, "Alpha Hall").get_by_role("button", name=t("rules.edit")).click()
        expect(p.locator("#words-ed-term")).to_have_value("Alpha Hall")
        expect(p.locator("#words-ed-tr")).to_have_value("Alpha-Halle")
        expect(p.locator("#words-ed-type")).to_have_value("always")
        expect(p.locator("#words-ed-term")).to_be_focused()
        p.locator("#words-ed-tr").fill("Alpha-Saal")
        save(p)
        expect(toast(p)).to_contain_text(t("words.applied", term="Alpha Hall"))
        expect(wrow(p, "Alpha Hall").locator("td").nth(1)).to_have_text("Alpha-Saal")
        assert wbody(env) == WORDS_DE.replace("Alpha-Halle", "Alpha-Saal")
        assert len(wwrites(env)) == 1
        wrow(p, "Alpha Hall").get_by_role("button", name=t("rules.edit")).click()          # to Keep as is: the Translation goes
        p.locator("#words-ed-type").select_option("keep")
        save(p)
        expect(wrow(p, "Alpha Hall").locator(".r-type")).to_have_text(KEEP)
        assert wbody(env) == WORDS_DE.replace("| Alpha Hall | Alpha-Halle | Always translate as |", "| Alpha Hall |  | Keep as is |")


def test_cancel_and_an_unchanged_save_write_nothing_on_the_word_list(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        wrow(p, "Acme").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#words-ed-term").fill("typed and abandoned")
        p.get_by_role("button", name=t("rules.cancel")).click()
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall", "Zeta Lab", "Vorlage"])
        wrow(p, "Acme").get_by_role("button", name=t("rules.edit")).click()
        save(p)                                                                            # nothing changed
        assert p.locator("#rules-words .is-adding").count() == 0
        open_add(p)
        p.keyboard.press("Escape")
        assert p.locator("#rules-words .is-adding").count() == 0
        assert wwrites(env) == [] and wbody(env) == WORDS_DE


def test_enter_saves_and_escape_cancels_an_open_word_row(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        open_add(p)
        p.locator("#words-ed-type").select_option("keep")
        p.locator("#words-ed-term").fill("Kappa")
        p.locator("#words-ed-term").press("Enter")
        expect(wrow(p, "Kappa")).to_have_count(1)
        assert len(wwrites(env)) == 1
        open_add(p)
        p.locator("#words-ed-term").fill("never saved")
        p.locator("#words-ed-term").press("Escape")
        expect(p.locator("#rules-words .is-adding")).to_have_count(0)
        assert len(wwrites(env)) == 1


def test_remove_a_word_applies_at_once_and_undo_puts_it_back(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        wrow(p, "Zeta Lab").get_by_role("button", name=t("rules.remove")).click()
        expect(toast(p)).to_contain_text(t("rules.removed", id="Zeta Lab"))
        expect(wterms(p)).to_have_text(["Acme", "Alpha Hall", "Vorlage"])
        assert len(wwrites(env)) == 1 and wbody(env) == WORDS_DE.replace("| Zeta Lab | | Keep as is |\n", "")
        toast(p).get_by_role("button", name=t("rules.undo")).click()
        expect(wterms(p)).to_have_count(4)
        assert wbody(env) == WORDS_DE and env.store.rules["words:de"]["version"] == 3
        assert len(wwrites(env)) == 2 and wwrites(env)[1]["baseVersion"] == 2             # the Undo is the one more write


def test_the_chips_and_the_search_hide_words_in_place_and_nothing_is_read_or_written(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        before = len(env.calls)
        chips = p.locator("#rules-words .r-chip")
        search = p.get_by_placeholder(t("words.search"))
        chips.nth(1).click()                                                                # Keep as is
        expect(wterms(p)).to_have_text(["Acme", "Zeta Lab"])
        expect(chips.nth(1)).to_have_attribute("aria-pressed", "true")
        expect(chips.nth(0)).to_have_attribute("aria-pressed", "false")
        search.fill("zeta")
        expect(wterms(p)).to_have_text(["Zeta Lab"])
        chips.nth(0).click()
        expect(wterms(p)).to_have_text(["Zeta Lab"])
        search.fill("alpha-h")                                                              # the Translation is searched too
        expect(wterms(p)).to_have_text(["Alpha Hall"])
        search.fill("nothing like this")
        expect(wterms(p)).to_have_count(0)
        expect(p.locator("#rules-words [data-noresult]")).to_have_text(t("words.noresult"))
        search.fill("")
        expect(p.locator("#rules-words [data-noresult]")).to_be_hidden()
        expect(wterms(p)).to_have_count(4)
        assert len(env.calls) == before


def test_an_empty_word_a_missing_translation_and_a_duplicate_are_refused_and_the_row_stays_open(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        open_add(p)
        alert = p.locator("#rules-words [role=alert]")
        save(p)
        expect(alert).to_have_text(t("words.empty.term"))
        p.locator("#words-ed-term").fill("New word")
        save(p)
        expect(alert).to_have_text(t("words.empty.translation"))
        p.locator("#words-ed-term").fill("acme")                                            # the same word in another case
        p.locator("#words-ed-tr").fill("x")
        save(p)
        expect(alert).to_have_text(t("words.duplicate", term="acme"))
        expect(p.locator("#words-ed-term")).to_have_value("acme")
        assert wwrites(env) == [] and wbody(env) == WORDS_DE


def test_a_409_on_the_word_list_says_so_and_keeps_the_typed_word(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        open_add(p)
        p.locator("#words-ed-term").fill("Beta Cafe")
        p.locator("#words-ed-tr").fill("Beta-Kaffee")
        code, out = env.store.handle("desk-rules-write", {"scope": "words:de", "baseVersion": 1,
                                                          "body": WORDS_DE + "| Other | | Keep as is |\n"}, "other@example.com")
        assert code == 200, out
        save(p)
        expect(p.locator("#rules-words [role=alert]")).to_have_text(t("rules.apply.stale", language=DE))
        expect(p.locator("#words-ed-term")).to_have_value("Beta Cafe")
        expect(p.locator("#words-ed-tr")).to_have_value("Beta-Kaffee")
        expect(toast(p)).to_have_count(0)
        assert "Beta Cafe" not in wbody(env) and env.store.rules["words:de"]["version"] == 2


def test_a_refused_word_write_says_why_and_keeps_the_row_open(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        env.worker.action_faults["desk-rules-write"] = {"status": 400, "error": "invalid: body is not valid text"}
        open_add(p)
        p.locator("#words-ed-term").fill("Beta Cafe")
        p.locator("#words-ed-tr").fill("Beta-Kaffee")
        save(p)
        expect(p.locator("#rules-words [role=alert]")).to_have_text(t("rules.apply.failed", reason="invalid: body is not valid text"))
        expect(p.locator("#words-ed-term")).to_have_value("Beta Cafe")
        assert wbody(env) == WORDS_DE


def test_a_word_list_that_cannot_be_read_says_why_and_try_again_reads_it_again(browser):
    with rules(browser, seed=seed_words) as env:
        p = env.page
        env.worker.action_faults["desk-rules-read"] = {"status": 500, "error": "internal"}
        p.locator(".r-nav .r-nav-b").nth(1).click()
        expect(p.locator("#rules-app")).to_have_attribute("data-state", "error")
        notice = p.locator("#rules-words .r-notice")
        expect(notice).to_contain_text(t("rules.error.read"))
        env.worker.action_faults.clear()
        notice.get_by_role("button", name=t("rules.retry")).click()
        expect(wterms(p)).to_have_count(4)
        expect(p.locator("#rules-app")).to_have_attribute("data-state", "ready")


def test_each_language_has_its_own_word_list_and_a_switch_starts_with_no_search_and_all_chips(browser):
    def both(store):
        seed_words(store)
        seed_scope(store, "words:fr", HEAD + "| Acme | | Keep as is |\n")

    with rules(browser, seed=both, tab="words") as env:
        p = env.page
        search = p.get_by_placeholder(t("words.search"))
        p.locator("#rules-words .r-chip").nth(2).click()
        search.fill("alpha")
        p.locator("#rulesTab-fr").click()
        expect(wterms(p)).to_have_text(["Acme"])
        expect(p.locator("#rules-words .r-chip").first).to_have_attribute("aria-pressed", "true")
        expect(p.get_by_placeholder(t("words.search"))).to_have_value("")
        assert "lang=fr" in p.url and "tab=words" in p.url
        assert read_scopes(env) == ["words:de", "words:fr"]


def test_a_tab_already_read_is_not_asked_again(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        nav = p.locator(".r-nav .r-nav-b")
        nav.nth(0).click()
        expect(words(p)).to_have_count(3)
        nav.nth(1).click()
        expect(wterms(p)).to_have_count(4)
        nav.nth(0).click()
        expect(words(p)).to_have_count(3)
        assert read_scopes(env) == ["words:de", "de"]


def test_a_body_with_lines_the_page_does_not_know_keeps_them_when_a_word_is_changed(browser):
    body = ("# Words\n\nIntro line.\n\n" + HEAD + "| Acme | | Keep as is |\n| Odd | x | Whatever type |\n"
            "| Four | cells | Keep as is | extra |\n|  | no term | Keep as is |\n\nTrailing note.\n")

    def odd(store):
        seed_ed(store)
        seed_scope(store, "words:de", body)

    with rules(browser, seed=odd, tab="words") as env:
        p = env.page
        # the engine skips a row with an unknown Type, four cells or no term (rules_store.parse_words): so does the page
        expect(wterms(p)).to_have_text(["Acme"])
        expect(p.locator("#rules-words .r-chip").first).to_have_text(f"{t('words.all')} 1")
        wrow(p, "Acme").get_by_role("button", name=t("rules.edit")).click()
        p.locator("#words-ed-term").fill("Acme2")
        save(p)
        expect(wrow(p, "Acme2")).to_have_count(1)                                           # the write has landed
        assert wbody(env) == body.replace("| Acme | | Keep as is |", "| Acme2 |  | Keep as is |")
        open_add(p)
        p.locator("#words-ed-term").fill("New")
        p.locator("#words-ed-tr").fill("Neu")
        save(p)
        expect(wrow(p, "New")).to_have_count(1)
        assert wbody(env) == body.replace("| Acme | | Keep as is |", "| Acme2 |  | Keep as is |").replace(
            "|  | no term | Keep as is |\n", "|  | no term | Keep as is |\n| New | Neu | Always translate as |\n")


def test_a_vertical_bar_is_refused_and_the_same_word_with_other_spacing_is_a_duplicate(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        alert = p.locator("#rules-words [role=alert]")
        open_add(p)
        p.locator("#words-ed-term").fill("a|b")                  # the engine splits a table row at every pipe
        p.locator("#words-ed-tr").fill("x")
        save(p)
        expect(alert).to_have_text(t("words.pipe"))
        p.locator("#words-ed-term").fill("fine")
        p.locator("#words-ed-tr").fill("x|y")
        save(p)
        expect(alert).to_have_text(t("words.pipe"))
        p.locator("#words-ed-term").fill("  alpha    HALL ")  # spacing and case do not make another word
        p.locator("#words-ed-tr").fill("x")
        save(p)
        expect(alert).to_have_text(t("words.duplicate", term="alpha HALL"))
        assert wwrites(env) == [] and wbody(env) == WORDS_DE


def test_a_typed_word_is_stored_as_one_line_with_single_spaces(browser):
    with rules(browser, seed=seed_words, tab="words") as env:
        p = env.page
        open_add(p)
        p.locator("#words-ed-type").select_option("keep")
        p.locator("#words-ed-term").fill("two   words\tand   more")
        save(p)
        expect(wrow(p, "two words and more")).to_have_count(1)
        assert wbody(env).endswith("| two words and more |  | Keep as is |\n")
