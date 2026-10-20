"""Robot click-tests for the rules page's UX fixes (CEL-076): items 4, 7, 8, 9, 10, 11, 16, 22, 23 and 24 of
the UX sweep (.team/CEL/runtime/out/loc2/ux-sweep/findings.md, in the monorepo).

The rules page never publishes or un-publishes by surprise, and every label says what it does. One test per
item; each was shown red once against the old behaviour (the monorepo step's Build records how).

A real Chromium drives `/admin/localization/rules/` in the click-test harness (a temporary copy of docs/, the
storage's stand-in behind a mock Worker). Expected wording comes from COPY.md through `copy_text.t`, never
typed here, except where a test pins the MEANING of a word (item 8: "Not in use yet"; item 24: "Don't
translate"). The harness helpers are COPIED from test_rules_browser.py (the convention of this folder: no
imports between test files). Desktop only (Ruling 23:48).
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

from localize_desk import harness as H  # noqa: E402
from localize_desk.copy_text import t, tn  # noqa: E402

OTHER = "other@example.test"
THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#rules-app[data-state="ready"]'
GLOBAL_V1 = "## Purpose\n\n- Rule A\n- Rule B\n"
DE_V1 = "## German\n\n- **Form of address:** du\n- **Markets:** CH\n"
DE = "German"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def desk():
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
    code, out = store.handle("desk-rules-read", {"scope": scope}, "reader")
    assert code == 200, out
    return out["version"], out["body"]


@contextmanager
def rules(browser, *, lang: str = "de", http_errors: bool = False, timing: dict | None = None, seed=None):
    """The rules page open and ready (German rules in use). On a normal exit it asserts no page error and no
    console error happened; an HTTP failure the test asked for (`http_errors`) is not an error."""
    with desk() as (base, root, worker):
        env = Env(base=base, worker=worker, store=worker.store)
        if seed:
            seed(env.store)
        else:
            prime(env.store, "global", GLOBAL_V1)
            prime(env.store, "de", DE_V1)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(10000)
        # The dashboard's BugHerd tag is a third party: answered here with an empty script (CEL-067).
        pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
        env.page = pg

        def on_console(msg):
            url = (msg.location or {}).get("url", "") or ""
            if msg.type != "error" or url.endswith("/favicon.ico"):
                return
            if http_errors and "Failed to load resource" in msg.text and "__worker" in url:
                return
            env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.add_init_script("window.RULES_TIMING=" + json.dumps(timing or {"draftDelay": 0}))
        pg.goto(f"{base}/admin/localization/rules/?lang={lang}")
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def until(fn, timeout: float = 6.0, what: str = "the condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def lang_item(page, n: int = 0):
    return page.locator("#sheet-lang li .ed").nth(n)


def edit_item(page, locator, suffix: str = " EDITED") -> None:
    locator.click()
    page.keyboard.press("End")
    page.keyboard.type(suffix)
    page.keyboard.press("Escape")


def scope_name(scope: str) -> str:
    p = scope.split(":")
    if scope == "global":
        return t("rules.scope.global")
    if p[0] == "glossary":
        return t("rules.scope.glossary", language=DE)
    return t("rules.scope.lang", language=DE)


def publish(page) -> None:
    page.click("#rulesUse")
    page.click(".r-modal .is-primary")


def published_once(env, suffix: str = " EDITED") -> None:
    """German rules edited and published: version 2 in use, an Undo entry on the stack."""
    edit_item(env.page, lang_item(env.page, 0), suffix)
    publish(env.page)
    until(lambda: stored(env.store, "de")[0] == 2, what="de version 2")
    expect(env.page.locator("#rulesUndo")).to_be_enabled()


# ── 4. Undo (and Redo) of a publish asks first; the toast promises only what Undo can do ──────────
def test_item_4_undo_of_a_publish_asks_first_and_names_what_it_writes(browser):
    with rules(browser) as env:
        pg = env.page
        published_once(env)
        pg.click("#rulesUndo")                                   # the button
        modal = pg.locator(".r-modal")
        expect(modal).to_be_visible()
        expect(modal).to_contain_text(t("rules.undo.confirm.title"))
        expect(modal).to_contain_text(t("rules.undo.confirm.body", list=scope_name("de")))
        assert stored(env.store, "de")[0] == 2, "Undo wrote before the client confirmed"
        modal.get_by_role("button", name=t("doc.confirm.cancel")).click()
        time.sleep(0.3)
        assert stored(env.store, "de")[0] == 2
        pg.locator("body").click(position={"x": 5, "y": 5})
        pg.keyboard.press("ControlOrMeta+z")                     # the keys ask too
        expect(pg.locator(".r-modal")).to_be_visible()
        pg.click(".r-modal .is-primary")
        until(lambda: stored(env.store, "de")[0] == 3, what="de version 3 after the confirmed Undo")
        assert stored(env.store, "de") == (3, DE_V1)
        pg.click("#rulesRedo")                                   # Redo asks too
        expect(pg.locator(".r-modal")).to_contain_text(t("rules.redo.confirm.title"))
        assert stored(env.store, "de")[0] == 3
        pg.click(".r-modal .is-primary")
        until(lambda: stored(env.store, "de")[0] == 4, what="de version 4 after the confirmed Redo")


def test_item_4_a_first_publish_does_not_promise_an_undo(browser):
    with rules(browser, http_errors=False) as env:
        pg = env.page
        pg.get_by_role("button", name=t("rules.glossary.add")).click()
        pg.locator('[data-rid="glossary:de#2.en"]').click()
        pg.keyboard.type("Tuition")
        pg.keyboard.press("Escape")
        pg.locator('[data-rid="glossary:de#2.to"]').click()
        pg.keyboard.type("Kursgebuehren")
        pg.keyboard.press("Escape")
        publish(pg)
        toast = pg.locator("#rulesToasts")
        expect(toast).to_contain_text(t("rules.toast.used", list=scope_name("glossary:de")))
        assert t("rules.toast.used.undo") not in toast.inner_text(), "a first publish promised Undo"
        # an edit of a scope that HAS an earlier version does promise it
        edit_item(pg, lang_item(pg, 0))
        publish(pg)
        expect(pg.locator("#rulesToasts")).to_contain_text(t("rules.toast.used.undo"))


# ── 7. the conflict buttons say what they do ─────────────────────────────────────────────────
def test_item_7_conflict_buttons_say_what_they_do(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        theirs = "## German\n\n- Their rule\n"
        code, out = env.store.handle("desk-rules-write", {"scope": "de", "body": theirs, "baseVersion": 1}, OTHER)
        assert code == 200 and out["ok"], out
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_be_visible()
        labels = notice.locator("button").all_inner_texts()
        assert labels == [t("rules.conflict.theirs"), t("rules.conflict.mine")], labels
        assert labels == ["Use theirs", "Keep mine and use it"], labels


# ── 8. a draft does not read as saved ────────────────────────────────────────────────────────
def test_item_8_the_bar_says_a_draft_is_not_in_use_yet(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        expect(pg.locator("#rulesSave")).to_have_text(t("rules.draft.saved"))
        text = pg.locator("#rulesSave").inner_text()
        assert "not in use yet" in text.lower() and "only in this browser" in text.lower(), text
        assert "saved" not in text.lower(), "the bar still reads as saved"


# ── 9. the confirm says when the change reaches all eight languages ───────────────────────────
def test_item_9_a_shared_rule_change_says_it_changes_all_languages(browser):
    with rules(browser) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))                          # a German rule only
        pg.click("#rulesUse")
        expect(pg.locator(".r-modal")).to_contain_text(t("rules.use.body", language=DE))
        assert t("rules.use.body.shared") not in pg.locator(".r-modal").inner_text()
        pg.locator(".r-modal").get_by_role("button", name=t("doc.confirm.cancel")).click()
        edit_item(pg, pg.locator("#sheet-shared li .ed").first)  # now a shared rule too
        pg.click("#rulesUse")
        expect(pg.locator(".r-modal")).to_contain_text(t("rules.use.body.shared"))


# ── 10. drafts in other languages are marked ──────────────────────────────────────────────────
def test_item_10_a_draft_in_another_language_is_marked_in_the_menu(browser):
    with rules(browser, timing={"draftDelay": 60000}) as env:      # the draft timer never fires on its own
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        pg.click("#rulesLang")
        pg.get_by_role("menuitem", name=re.compile("French")).click()
        pg.wait_for_function("new URL(location.href).searchParams.get('lang') === 'fr'")
        expect(pg.locator(".menu")).to_have_count(0)             # choosing a language closes the menu
        pg.click("#rulesLang")
        expect(pg.locator(".menu")).to_have_count(1)
        german = pg.get_by_role("menuitem", name=re.compile("German"))
        expect(german).to_contain_text(t("rules.lang.pending"))
        assert pg.get_by_role("menuitem", name=re.compile("French")).inner_text().count(t("rules.lang.pending")) == 0
        pg.keyboard.press("Escape")
        assert pg.locator("#rulesLang").get_attribute("title") == t("rules.lang.pending.btn")
        # it was written to this browser when we left the language (the 60 s timer had not run)
        assert json.loads(pg.evaluate("localStorage.getItem('cel-rules-draft-de')"))["body"].count("EDITED") == 1
        pg.reload()
        pg.wait_for_selector(READY)
        pg.click("#rulesLang")
        expect(pg.get_by_role("menuitem", name=re.compile("German"))).to_contain_text(t("rules.lang.pending"))


# ── 11. disabled controls say why ─────────────────────────────────────────────────────────────
def test_item_11_disabled_controls_say_why_on_hover(browser):
    with rules(browser) as env:
        pg = env.page
        for sel, key in (("#rulesUse", "rules.use.disabled"), ("#rulesUndo", "doc.undo.none"),
                         ("#rulesRedo", "doc.redo.none")):
            expect(pg.locator(sel)).to_be_disabled()
            pg.locator(sel).hover(force=True)                    # the pointer rests on a disabled button
            assert pg.locator(sel).get_attribute("title") == t(key), sel
        edit_item(pg, lang_item(pg, 0))
        expect(pg.locator("#rulesUse")).to_be_enabled()
        assert not pg.locator("#rulesUse").get_attribute("title")
        expect(pg.locator("#rulesUndo")).to_be_enabled()
        assert pg.locator("#rulesUndo").get_attribute("title") != t("doc.undo.none")


# ── 16. the same thing has the same word ──────────────────────────────────────────────────────
def test_item_16_the_history_button_and_its_drawer_use_one_word(browser):
    with rules(browser) as env:
        pg = env.page
        button = pg.locator("#rulesHistory").inner_text().strip()
        pg.click("#rulesHistory")
        drawer = pg.locator("#rulesDrawer h2").inner_text().strip()
        assert button == drawer == t("rules.history") == "History", (button, drawer)


# ── 22. the checked tag is quiet until you point at a rule; no dead end; no version numbers ───
def test_item_22_the_checked_tag_shows_on_hover_and_there_is_no_dead_end(browser):
    with rules(browser) as env:
        pg = env.page
        item = pg.locator("#sheet-lang li").first
        tag = item.locator(".tag")
        assert tag.evaluate("el => getComputedStyle(el).display") == "none"
        item.hover()
        expect(tag).to_be_visible()
        expect(tag).to_have_text(t("rules.checked"))
        pg.mouse.move(5, 5)
        assert tag.evaluate("el => getComputedStyle(el).display") == "none"
        # keyboard: focus inside the rule shows it too
        lang_item(pg, 0).focus()
        expect(tag).to_be_visible()
        # the notice under an edited checked rule gives no one to call
        edit_item(pg, lang_item(pg, 0))
        warn = pg.locator("#sheet-lang .notice").first
        expect(warn).to_have_text(t("rules.checked.warn"))
        assert "contact" not in warn.inner_text().lower()
        # the status bar carries no version numbers
        assert not re.search(r"\bv\d", pg.locator("#rulesNote").inner_text()), pg.locator("#rulesNote").inner_text()


# ── 23. Try again resends what the confirm covered, with no second confirm ────────────────────
def test_item_23_try_again_resends_the_confirmed_rules_and_never_a_later_edit(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0))
        env.worker.action_faults["desk-rules-write"] = {"status": 429, "error": "over the cap"}
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_contain_text(t("rules.error.cap"))
        edit_item(pg, pg.locator("#sheet-shared li .ed").first)  # an edit made AFTER the confirm
        env.worker.action_faults.pop("desk-rules-write")
        notice.get_by_role("button", name=t("rules.retry")).click()
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2 after Try again")
        expect(pg.locator(".r-modal")).to_have_count(0)          # no second confirm
        assert "du EDITED" in stored(env.store, "de")[1]
        assert stored(env.store, "global") == (1, GLOBAL_V1)     # the later edit was NOT sent
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))   # it is still a draft


# ── 24. the glossary column says what a ticked term does ──────────────────────────────────────
def test_item_24_the_glossary_column_says_dont_translate_and_the_stored_header_does_not_change(browser):
    with rules(browser) as env:
        pg = env.page
        pg.get_by_role("button", name=t("rules.glossary.add")).click()
        expect(pg.locator(".gl-head")).to_contain_text(t("rules.glossary.keep"))
        assert t("rules.glossary.keep") == "Don't translate"
        pg.locator('[data-rid="glossary:de#2.en"]').click()
        pg.keyboard.type("Tuition")
        pg.keyboard.press("Escape")
        pg.locator('[data-rid="glossary:de#2.to"]').click()
        pg.keyboard.type("Kursgebuehren")
        pg.keyboard.press("Escape")
        publish(pg)
        until(lambda: stored(env.store, "glossary:de")[0] == 1, what="glossary version 1")
        # the engine's prompt and the stored table keep their own header
        assert "Keep as is" in stored(env.store, "glossary:de")[1]


# ── rework 1 (CEL-076 round 1) ────────────────────────────────────────────────────────────────
def test_item_22_only_the_checked_tag_hides_a_brief_cards_in_use_tag_stays_shown(browser):
    """Item 22 quiets the "Checked automatically" tag of a rule; a page brief card's "v{n} in use" tag is
    another thing and stays shown, without hovering anything."""
    brief = "brief:cost-of-studying-english:de"

    def seed(store):
        prime(store, "global", GLOBAL_V1)
        prime(store, "de", DE_V1)
        prime(store, brief, "## Page topic\n\nCosts of a course\n")

    with rules(browser, seed=seed) as env:
        pg = env.page
        pg.mouse.move(5, 5)
        card_tag = pg.locator(".bcard > .tag", has_text=t("rules.brief.inuse", n=1))
        card_tag.scroll_into_view_if_needed()
        pg.mouse.move(5, 5)
        expect(card_tag).to_be_visible()
        assert card_tag.evaluate("el => getComputedStyle(el).display") == "inline-block"
        checked = pg.locator("#sheet-lang li").first.locator(".tag")
        assert checked.evaluate("el => getComputedStyle(el).display") == "none"


def test_item_23_a_later_edit_of_the_same_rules_is_not_a_conflict_with_my_own_retry(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0), " FIRST")
        env.worker.action_faults["desk-rules-write"] = {"status": 429, "error": "over the cap"}
        publish(pg)
        notice = pg.locator("#sheet-lang .r-notice")
        expect(notice).to_contain_text(t("rules.error.cap"))
        edit_item(pg, lang_item(pg, 1), " SECOND")                # the SAME scope, after the confirm
        env.worker.action_faults.pop("desk-rules-write")
        notice.get_by_role("button", name=t("rules.retry")).click()
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2 after Try again")
        v2 = stored(env.store, "de")[1]
        assert "FIRST" in v2 and "SECOND" not in v2              # the confirmed body only
        expect(pg.locator("#rulesNote")).to_contain_text(tn("rules.pending", 1))
        publish(pg)                                              # the later edit, confirmed now
        until(lambda: stored(env.store, "de")[0] == 3, what="de version 3, the later edit")
        assert "SECOND" in stored(env.store, "de")[1]
        expect(pg.locator("#sheet-lang .r-notice")).to_have_count(0)   # no conflict with my own write


def test_item_23_another_writer_between_retry_and_publish_is_still_a_conflict(browser):
    with rules(browser, http_errors=True) as env:
        pg = env.page
        edit_item(pg, lang_item(pg, 0), " FIRST")
        env.worker.action_faults["desk-rules-write"] = {"status": 429, "error": "over the cap"}
        publish(pg)
        expect(pg.locator("#sheet-lang .r-notice")).to_contain_text(t("rules.error.cap"))
        edit_item(pg, lang_item(pg, 1), " SECOND")
        env.worker.action_faults.pop("desk-rules-write")
        pg.locator("#sheet-lang .r-notice").get_by_role("button", name=t("rules.retry")).click()
        until(lambda: stored(env.store, "de")[0] == 2, what="de version 2 after Try again")
        theirs = "## German\n\n- Their rule\n"
        code, out = env.store.handle("desk-rules-write", {"scope": "de", "body": theirs, "baseVersion": 2}, OTHER)
        assert code == 200 and out["ok"], out
        publish(pg)
        expect(pg.locator("#sheet-lang .r-notice")).to_contain_text(OTHER)
        assert stored(env.store, "de") == (3, theirs)            # a real conflict never overwrites
