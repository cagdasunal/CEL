"""Robot click-tests for the IMPORT tab of the rules page (CEL-114): /admin/localization/rules/?tab=import.

Three steps (CEL-110 option A): get the files (Copy prompt to the clipboard, Download current rules as one .md for a
chosen language with the rule IDs, Download template), upload one changes file, check what the reader understood
before anything is saved (Before -> After, removals in red, "Couldn't place these lines"), then Apply: ONE
`desk-rules-import-apply` call that writes every language or none. Reading writes nothing.

The fake reader is the template's own example: `answer_from_template()` turns the "filled example" of
rules_import_template.md into the answer Gemini would give, so the template and the expected change list cannot drift.
The expected list itself is written out below by hand. The stand-in (desk_store.DeskStore) checks the proposals in
code exactly as the Worker does. Harness helpers (page_with_clipboard, upload, download_text, respond) come from
harness.py. Expected wording comes from COPY.md through `copy_text.t`. Desktop only by ruling (2026-10-19 23:48). Every
test asserts the page raised no error. Chromium needs the sandbox off to launch.
"""
from __future__ import annotations

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
TEMPLATE = Path(H.__file__).resolve().parent / "rules_import_template.md"

# Short synthetic bodies (no client text): the IDs and terms the template's example names.
DE_RULES = "- Dates are written freely [DE-9]\n- Currency is written as in English [DE-12]\n- Other rule [DE-3]\n"
FR_RULES = "- Sentences are long [FR-9]\n- Other rule [FR-2]\n"
IT_RULES = "- Old rule [IT-4]\n- Kept rule [IT-1]\n"
HEAD = "| Term | Translation | Type |\n|---|---|---|\n"
DE_WORDS = HEAD + "| exam prep | Prüfungsvorbereitung | Always translate as |\n"
FR_WORDS = HEAD + "| homestay | hébergement | Always translate as |\n"
IT_WORDS = HEAD + "| La Jolla |  | Keep as is |\n"
SEEDS = {"de": DE_RULES, "fr": FR_RULES, "it": IT_RULES, "words:de": DE_WORDS, "words:fr": FR_WORDS, "words:it": IT_WORDS}

# What the template's example must give, written out by hand: (kind, tag, kind label, Before has, After has).
NEW_DE = t("rules.new.id", lang="DE")
WORD_TAG = t("rules.change.words")
EXPECTED = {
    "de": [
        ("add_rule", NEW_DE, "rules.change.add", [], ["Write dates as 31.12.2026."]),
        ("edit_rule", "DE-12", "rules.change.chg", ["Currency is written as in English"], ['Use "Studiengebühren" for "tuition fees".']),
        ("remove_rule", "DE-9", "rules.change.del", ["Dates are written freely"], []),
        ("add_word", WORD_TAG, "rules.change.add", [], ["Pacific Beach", t("words.same"), t("words.keep")]),
        ("add_word", WORD_TAG, "rules.change.add", [], ["homestay", "Gastfamilie", t("words.always")]),
        ("remove_word", WORD_TAG, "rules.change.del", ["exam prep", "Prüfungsvorbereitung", t("words.always")], []),
    ],
    "fr": [
        ("edit_rule", "FR-9", "rules.change.chg", ["Sentences are long"], ["Keep sentences under 20 words."]),
        ("add_word", WORD_TAG, "rules.change.add", [], ["école d'anglais San Diego", t("words.keyword")]),
        ("edit_word", WORD_TAG, "rules.change.chg", ["homestay", "hébergement"], ["homestay", "famille d'accueil", t("words.always")]),
    ],
    "it": [
        ("remove_rule", "IT-4", "rules.change.del", ["Old rule"], []),
        ("add_word", WORD_TAG, "rules.change.add", [], ["corso di inglese a San Diego", t("words.keyword")]),
        ("remove_word", WORD_TAG, "rules.change.del", ["La Jolla", t("words.keep")], []),
    ],
}
TOTAL = sum(len(v) for v in EXPECTED.values())
NAMES = {"de": "German", "fr": "French", "it": "Italian"}


# ── the fake reader: the template's own example -> the answer the reader would give ──────────────────────────────
def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def example_of(template: str) -> str:
    part = template.split("## 3. A filled example", 1)[1]
    return re.search(r"~~~\n(.*?)\n~~~", part, re.S).group(1)


def prompt_of(template: str) -> str:
    return re.search(r"^={10}\n(.*?)\n={10}$", template, re.S | re.M).group(1).strip() + "\n"


def answer_from_template(template: str | None = None) -> dict:
    changes, lang, section = [], None, None

    def add(kind, target=None, term=None, after=None, typ=None, by=None, src=""):
        changes.append({"language": lang, "kind": kind, "target_id": target, "term": term, "before": None,
                        "after": after, "type": typ, "matched_by": by, "source_text": src})
    for line in example_of(template or template_text()).splitlines():
        m = re.match(r"## .*\(([A-Z]{2})\)", line)
        if m:
            lang = m.group(1).lower()
        elif line.startswith("### "):
            section = line[4:].strip()
        elif section == "Rules":
            if (m := re.match(r"- ADD: (.*)", line)):
                add("add_rule", after=m.group(1), src=line)
            elif (m := re.match(r"- EDIT ([A-Z]{2}-\d+): (.*)", line)):
                add("edit_rule", target=m.group(1), after=m.group(2), by="id", src=line)
            elif (m := re.match(r"- REMOVE ([A-Z]{2}-\d+)", line)):
                add("remove_rule", target=m.group(1), by="id", src=line)
        elif section == "Words" and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0] in ("ADD", "EDIT", "REMOVE"):
                action, term, tr, typ = (cells + ["", "", ""])[:4]
                add(f"{action.lower()}_word", term=term, after=tr or None, typ=typ or None, src=line)
    return {"changes": changes, "unplaced": []}


# ── harness helpers (copied from test_rules_editor_browser.py: no imports between test files) ────────────────────
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
    calls: list = field(default_factory=list)        # (action, body) of every call that reached the storage
    errors: list = field(default_factory=list)

    def of(self, action: str) -> list:
        return [b for a, b in self.calls if a == action]

    def body(self, scope: str) -> str:
        return self.store.rules[scope]["body"]


def seed(store) -> None:
    for scope, body in SEEDS.items():
        code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": 0}, "seed:client-md")
        assert code == 200 and out["ok"], out


@contextmanager
def imp(browser, *, tab: str = "import", lang: str = "de", width: int = 1440, answer="template", configure=None):
    """The rules page open on `tab`, in a page that may use the clipboard. `answer`: 'template' = the fake reader answers
    with the template's example; a dict or callable is set as the reader's answer instead."""
    with desk() as (base, root, worker):
        env = Env(base=base, worker=worker, store=worker.store)
        seed(env.store)
        env.store.import_answer = (lambda text, langs: answer_from_template()) if answer == "template" else answer
        raw = env.store.handle

        def spy(action, body, who):
            env.calls.append((action, dict(body or {})))
            return raw(action, body, who)

        env.store.handle = spy
        if configure:
            configure(env)
        with H.page_with_clipboard(browser, width=width) as pg:
            pg.set_default_timeout(10000)
            pg.route(THIRD_PARTY, lambda route: route.fulfill(status=200, content_type="text/javascript", body=""))
            env.page = pg

            def on_console(msg):
                url = (msg.location or {}).get("url", "") or ""
                if msg.type == "error" and not url.endswith("/favicon.ico") and not (
                        "Failed to load resource" in msg.text and "__worker" in url):
                    env.errors.append(f"console.error: {msg.text} ({url})")

            pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
            pg.on("console", on_console)
            pg.goto(f"{base}/admin/localization/rules/?lang={lang}&tab={tab}")
            pg.wait_for_selector(READY, timeout=20000)
            yield env
        assert not env.errors, env.errors


def upload_template(env) -> None:
    H.upload(env.page, "#imp-file", "changes-2026-10-28.md", template_text())
    expect(env.page.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))



# ── 1. Step 1: the three files ───────────────────────────────────────────────────────────────────────────────────
def test_the_import_tab_has_three_steps_and_the_files_to_get(browser):
    with imp(browser) as env:
        p = env.page
        expect(p.locator(".r-nav-b[aria-selected=true]")).to_have_text(t("rules.tab.import"))
        expect(p.locator(".r-step-h")).to_have_text([t("import.step1"), t("import.step2"), t("import.step3")])
        expect(p.locator(".r-file-h")).to_have_text([t("import.prompt"), t("import.current"), t("import.template")])
        expect(p.get_by_role("button", name=t("import.prompt.copy"))).to_have_count(1)
        expect(p.get_by_role("button", name=t("import.current.download"))).to_have_count(1)
        expect(p.get_by_role("button", name=t("import.template.download"))).to_have_count(1)
        expect(p.locator("#imp-drop")).to_contain_text(t("import.limits"))
        expect(p.locator("#imp-preview")).to_have_text(t("import.empty"))
        assert [c for c in env.calls if c[0] != "desk-rules-read"] == []


def test_copy_prompt_puts_the_templates_prompt_on_the_clipboard(browser):
    with imp(browser) as env:
        p = env.page
        btn = p.locator("#imp-copy")
        btn.click()
        expect(btn).to_have_text(t("import.prompt.copied"))
        got = p.evaluate("navigator.clipboard.readText()")
        assert got.strip() == prompt_of(template_text()).strip()
        assert got.startswith("You help me change the translation rules") and "MY CHANGES:" in got
        assert "==========" not in got and "Publish" not in got
        expect(btn).to_have_text(t("import.prompt.copy"), timeout=5000)           # back to its own word after 2 s


def test_download_current_rules_is_one_md_for_the_chosen_language_with_ids_and_words(browser):
    with imp(browser, lang="de") as env:
        p = env.page
        sel = p.locator("#imp-dl-lang")
        expect(sel).to_have_value("de")                                           # the page's language
        name, text = H.download_text(p, lambda: p.locator("#imp-dl").click())
        assert name == "cel-rules-de.md"
        assert text.startswith("# German translation rules\n")
        assert "- Currency is written as in English [DE-12]\n" in text and "[DE-9]" in text
        assert "| exam prep | Prüfungsvorbereitung | Always translate as |" in text
        sel.select_option("fr")
        name, text = H.download_text(p, lambda: p.locator("#imp-dl").click())
        assert name == "cel-rules-fr.md" and text.startswith("# French translation rules\n")
        assert "[FR-9]" in text and "[DE-" not in text
        assert "| homestay | hébergement | Always translate as |" in text
        assert [c for c in env.calls if c[0] not in ("desk-rules-read",)] == []        # a download writes nothing


def test_download_template_is_a_new_md_file_without_the_maintainer_note(browser):
    with imp(browser) as env:
        p = env.page
        name, text = H.download_text(p, lambda: p.get_by_role("button", name=t("import.template.download")).click())
        assert name == "cel-rules-import-template.md"
        assert text.startswith("# Translation rules: changes template\n")
        assert "MAINTAINER NOTE" not in text and "<!--" not in text
        assert "nothing changes until you Apply" in text and "Publish" not in text
        assert prompt_of(text) == prompt_of(template_text())
        assert example_of(text) == example_of(template_text())
        assert text.rstrip().endswith("---")


# ── 2. Step 2 and 3: the upload and the preview ──────────────────────────────────────────────────────────────────
def test_the_templates_example_gives_the_expected_change_list_and_writes_nothing(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        expect(p.locator(".r-upl-name")).to_have_text("changes-2026-10-28.md")
        expect(p.locator(".r-upl-meta")).to_contain_text(re.compile(r"KB · read at \d\d:\d\d"))
        heads = p.locator("#imp-preview .r-plang")
        expect(heads).to_have_count(3)
        for i, code in enumerate(("de", "fr", "it")):
            expect(heads.nth(i)).to_contain_text(NAMES[code])
            expect(heads.nth(i).locator(".r-plang-n")).to_have_text(tn("import.lang.count", len(EXPECTED[code])))
        all_rows = p.locator("#imp-preview .r-pchg")
        expect(all_rows).to_have_count(TOTAL)
        i = 0
        for code in ("de", "fr", "it"):
            for kind, tag, label, before_has, after_has in EXPECTED[code]:
                row = all_rows.nth(i)
                i += 1
                assert row.get_attribute("data-kind") == kind, (code, kind)
                expect(row.locator(".r-id")).to_have_text(tag)
                expect(row.locator(".r-kind")).to_have_text(t(label))
                cols = row.locator(".r-pcol")
                expect(cols.nth(0).locator(".r-pcap")).to_have_text(t("import.before"))
                expect(cols.nth(1).locator(".r-pcap")).to_have_text(t("import.after"))
                before, after = cols.nth(0).inner_text(), cols.nth(1).inner_text()
                for needle in before_has:
                    assert needle in before, (code, kind, needle, before)
                for needle in after_has:
                    assert needle in after, (code, kind, needle, after)
                if not before_has:
                    assert before.split("\n", 1)[1].strip() == "\u2014"
                if not after_has:
                    assert after.split("\n", 1)[1].strip() == "\u2014"
        # the reader only proposed: one read, no write, no apply, and the rules are untouched
        assert len(env.of("desk-rules-import-read")) == 1
        assert env.of("desk-rules-write") == [] and env.of("desk-rules-import-apply") == []
        for scope, body in SEEDS.items():
            assert env.body(scope) == body
        expect(p.get_by_role("button", name=tn("import.apply", TOTAL))).to_be_enabled()
        expect(p.locator("#imp-unplaced")).to_have_count(0)


def test_removals_are_red_and_struck_through(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        gone = p.locator("#imp-preview .r-gone")
        expect(gone).to_have_count(4)                                              # DE-9, exam prep, IT-4, La Jolla
        probe = p.evaluate("""() => {
            const d = document.createElement('i'); d.style.color = 'var(--err)'; document.body.appendChild(d);
            const c = getComputedStyle(d).color; d.remove(); return c; }""")
        got = gone.first.evaluate("e => [getComputedStyle(e).color, getComputedStyle(e).textDecorationLine]")
        assert got[0] == probe and "line-through" in got[1], (got, probe)
        expect(p.locator("#imp-preview .r-pchg.is-del .r-kind").first).to_have_text(t("rules.change.del"))


def test_lines_the_reader_could_not_place_are_listed_with_their_reason(browser):
    def answer(text, langs):
        a = answer_from_template()
        a["changes"].append({"language": "de", "kind": "edit_rule", "target_id": "DE-99", "term": None, "before": None,
                             "after": "Anything", "type": None, "matched_by": "id", "source_text": "- EDIT DE-99: Anything"})
        a["unplaced"] += [
            {"source_text": "Make the tone friendlier on the Toronto page.", "language": None, "reason": "unknown_language"},
            {"source_text": "Perhaps something about numbers?", "language": "de", "reason": "unreadable"},
        ]
        return a
    with imp(browser, answer=answer) as env:
        p = env.page
        H.upload(p, "#imp-file", "changes.md", template_text())
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))      # DE-99 is not a change
        box = p.locator("#imp-unplaced")
        expect(box.locator(".r-un-h")).to_contain_text(t("import.unplaced"))
        expect(box.locator(".r-un-h .r-plang-n")).to_have_text("3")
        items = box.locator(".r-un-i")
        expect(items).to_have_count(3)
        texts = items.all_inner_texts()
        joined = "\n".join(texts)
        assert "Make the tone friendlier on the Toronto page." in joined and t("import.why.page") in joined
        assert "Perhaps something about numbers?" in joined and t("import.why.unreadable") in joined
        assert "EDIT DE-99: Anything" in joined and t("import.why.noid", id="DE-99", language="German") in joined
        expect(p.locator("#imp-apply")).to_have_text(tn("import.apply", TOTAL))               # the listed lines are not applied


def test_a_file_over_64_kb_is_refused_in_the_page_and_a_failed_read_says_why(browser):
    with imp(browser) as env:
        p = env.page
        H.upload(p, "#imp-file", "big.md", "- ADD: x\n" * 9000)
        expect(p.locator("#imp-preview")).to_contain_text(t("import.too.big"))
        assert env.of("desk-rules-import-read") == []
        expect(p.locator("#imp-apply")).to_have_count(0)
        env.worker.respond("desk-rules-import-read", {"ok": False, "error": "the reader timed out"}, status=504)
        H.upload(p, "#imp-file", "small.md", "- ADD: x\n")                                       # "Upload another file" path
        expect(p.locator("#imp-preview")).to_contain_text(t("import.read.failed", reason="the reader timed out"))
        expect(p.locator("#imp-apply")).to_have_count(0)


def test_cancel_drops_the_file_and_nothing_was_written(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        p.get_by_role("button", name=t("import.cancel")).click()
        expect(p.locator("#imp-preview")).to_have_text(t("import.empty"))
        expect(p.locator("#imp-drop")).to_have_count(1)
        assert env.of("desk-rules-write") == [] and env.of("desk-rules-import-apply") == []


# ── 3. Apply ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_apply_sends_one_apply_call_and_writes_every_language(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(p.locator("#rules-toasts .toast")).to_contain_text(tn("import.applied", TOTAL))
        applies = env.of("desk-rules-import-apply")
        assert len(applies) == 1 and env.of("desk-rules-write") == []
        assert len(applies[0]["changes"]) == TOTAL
        assert set(applies[0]["bases"]) >= {"de", "words:de", "fr", "it"}
        # the new bodies: built by the code, IDs kept, a new rule numbered after the highest ever used
        de = env.body("de")
        assert "[DE-9]" not in de and "Dates are written freely" not in de
        assert 'Use "Studiengebühren" for "tuition fees". [DE-12]' in de
        assert "Write dates as 31.12.2026. [DE-13]" in de
        assert "Keep sentences under 20 words. [FR-9]" in env.body("fr")
        assert "[IT-4]" not in env.body("it")
        assert "| Pacific Beach |" in env.body("words:de") and "exam prep" not in env.body("words:de")
        assert "famille d'accueil" in env.body("words:fr") and "La Jolla" not in env.body("words:it")
        # and the tab is ready for the next file
        expect(p.locator("#imp-preview")).to_have_text(t("import.empty"))
        expect(p.locator("#imp-drop")).to_have_count(1)


def test_apply_with_one_stale_language_changes_nothing(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        peer = env.store.rules["de"]
        code, out = env.store.handle("desk-rules-write", {"scope": "de", "body": DE_RULES + "- Peer rule [DE-20]\n",
                                                          "baseVersion": peer["version"]}, "peer@example.org")
        assert code == 200, out
        before = {s: env.body(s) for s in SEEDS}
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(p.locator("#imp-preview .r-notice")).to_have_text(t("rules.apply.stale", language="German"))
        assert len(env.of("desk-rules-import-apply")) == 1
        assert {s: env.body(s) for s in SEEDS} == before                              # all or none
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)               # the preview stays, nothing lost
        expect(p.locator("#imp-apply")).to_be_enabled()


# ── 4. Wide screens ──────────────────────────────────────────────────────────────────────────────────────────────
def test_at_2560_the_import_column_is_as_wide_as_the_rules_tabs_content(browser):
    with imp(browser, width=2560) as env:
        p = env.page
        p.evaluate("window.scrollTo(0, 0)")

        def box(sel):
            return p.locator(sel).evaluate("e => { const r = e.getBoundingClientRect(); return [r.left, r.width]; }")
        imp_box = box("#rules-import .r-steps")
        upload_template(env)
        imp_loaded = box("#rules-import .r-steps")
        p.locator(".r-nav-b", has_text=t("rules.tab.rules")).click()
        p.wait_for_selector(READY)                                                     # the rules are read: the column has its size
        p.wait_for_selector("#rules-lang")
        rules_box = box("#rules-lang")
        assert imp_box == imp_loaded                                                   # the preview does not widen it
        assert abs(imp_box[0] - rules_box[0]) < 1 and abs(imp_box[1] - rules_box[1]) < 1, (imp_box, rules_box)
        assert imp_box[1] <= 1360 and imp_box[1] > 1100, imp_box                        # capped like the rules, not a strip
        band = p.locator(".r-tabs").evaluate("e => e.getBoundingClientRect().width")
        assert band > 2400 and imp_box[1] < band / 1.5                                 # the band is full width, the column is not
        p.locator(".r-nav-b", has_text=t("rules.tab.import")).click()
        assert p.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


# ── 5. Refusals: every way a read, an Apply, a download or a copy can be turned down ─────────────────────────────────
# Each has its own test; BUILD-NOTE lists the mutation that turns each one red.
def notice(env, where="#imp-preview"):
    return env.page.locator(f"{where} .r-notice")


def test_a_signed_out_read_says_so_and_proposes_nothing(browser):
    with imp(browser) as env:
        env.worker.respond("desk-rules-import-read", {"ok": False, "error": "unauthorized"}, status=401)
        H.upload(env.page, "#imp-file", "changes.md", template_text())
        expect(notice(env)).to_have_text(t("rules.error.signed_out"))
        expect(env.page.locator("#imp-apply")).to_have_count(0)
        assert env.worker.calls.count("desk-rules-import-read") == 1
        assert env.of("desk-rules-write") == [] and env.of("desk-rules-import-apply") == []


def test_a_read_over_the_request_cap_says_so_and_proposes_nothing(browser):
    with imp(browser) as env:
        env.worker.respond("desk-rules-import-read", {"ok": False, "error": "rate limited"}, status=429)
        H.upload(env.page, "#imp-file", "changes.md", template_text())
        expect(notice(env)).to_have_text(t("rules.error.cap"))
        expect(env.page.locator("#imp-apply")).to_have_count(0)


def test_a_read_whose_answer_is_lost_says_so_and_the_same_file_can_be_sent_again(browser):
    with imp(browser) as env:
        p = env.page
        env.worker.action_faults["desk-rules-import-read"] = {"drop": True}
        H.upload(p, "#imp-file", "changes.md", template_text())
        expect(notice(env)).to_have_text(t("rules.error.read"))
        expect(p.locator("#imp-apply")).to_have_count(0)
        env.worker.action_faults.clear()
        H.upload(p, "#imp-file", "changes.md", template_text())
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))
        expect(p.locator("#imp-preview .r-notice")).to_have_count(0)


def test_a_read_answer_without_a_change_list_is_refused(browser):
    with imp(browser) as env:
        env.worker.respond("desk-rules-import-read", {"ok": True, "hello": "there"}, status=200)
        H.upload(env.page, "#imp-file", "changes.md", template_text())
        expect(notice(env)).to_have_text(t("import.read.failed", reason=200))
        expect(env.page.locator("#imp-apply")).to_have_count(0)


def test_a_second_file_while_the_first_is_being_read_is_ignored(browser):
    with imp(browser) as env:
        p = env.page
        env.worker.action_faults["desk-rules-import-read"] = {"delay": 1.5}
        H.upload(p, "#imp-file", "first.md", template_text())
        expect(p.locator("#imp-preview")).to_have_text(t("import.reading"))
        expect(p.locator("#imp-another")).to_be_disabled()                           # busy: no other file can be chosen
        H.upload(p, "#imp-file", "second.md", "- ADD: x\n")
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))
        expect(p.locator(".r-upl-name")).to_have_text("first.md")
        assert env.worker.calls.count("desk-rules-import-read") == 1


def test_a_refused_apply_says_why_keeps_the_preview_and_writes_nothing(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        before = {s: env.body(s) for s in SEEDS}
        env.worker.respond("desk-rules-import-apply", {"ok": False, "error": "storage busy"}, status=503)
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.apply.failed", reason="storage busy"))
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)
        expect(p.locator("#imp-apply")).to_be_enabled()
        expect(p.locator("#rules-toasts .toast")).to_have_count(0)
        assert {s: env.body(s) for s in SEEDS} == before


def test_an_apply_the_code_turns_down_gives_its_reason_without_the_invalid_prefix(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        env.worker.respond("desk-rules-import-apply", {"ok": False, "error": "invalid: some changes do not fit the current rules"}, status=400)
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.apply.failed", reason="some changes do not fit the current rules"))
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)


def test_a_signed_out_apply_says_so_and_keeps_the_preview(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        env.worker.respond("desk-rules-import-apply", {"ok": False, "error": "unauthorized"}, status=401)
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.error.signed_out"))
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)


def test_an_apply_over_the_request_cap_says_so_and_keeps_the_preview(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        env.worker.respond("desk-rules-import-apply", {"ok": False, "error": "rate limited"}, status=429)
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.error.cap"))
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)


def test_an_apply_whose_answer_is_lost_cannot_land_twice(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        env.worker.action_faults["desk-rules-import-apply"] = {"drop": True}       # the write lands, the answer does not
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.error.read"))
        landed = {s: env.body(s) for s in SEEDS}
        assert "Write dates as 31.12.2026. [DE-13]" in landed["de"]                  # it did land
        env.worker.action_faults.clear()
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()             # the client tries again
        # the code checks the changes against the rules as they now stand: they are already in, so it turns them down
        expect(notice(env)).to_have_text(t("rules.apply.failed", reason="some changes do not fit the current rules"))
        assert env.worker.calls.count("desk-rules-import-apply") == 2
        assert {s: env.body(s) for s in SEEDS} == landed                              # no second copy
        assert landed["de"].count("Write dates as 31.12.2026.") == 1


def test_a_second_click_on_apply_while_it_is_sending_sends_nothing_more(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        env.worker.action_faults["desk-rules-import-apply"] = {"delay": 1.5}
        p.evaluate("(() => { const b = document.getElementById('imp-apply'); b.click(); b.click(); })()")
        for busy in ("#imp-apply", "#imp-cancel", "#imp-another"):                  # sending: nothing else can be pressed
            expect(p.locator(busy)).to_be_disabled()
        p.evaluate("document.getElementById('imp-cancel').click()")                  # a press on the disabled Cancel does nothing
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)
        expect(p.locator("#rules-toasts .toast")).to_contain_text(tn("import.applied", TOTAL))
        assert env.worker.calls.count("desk-rules-import-apply") == 1


def test_download_current_rules_that_cannot_be_read_says_so_gives_no_file_and_works_again(browser):
    with imp(browser) as env:
        p = env.page
        got = []
        p.on("download", lambda d: got.append(d))
        env.worker.action_faults["desk-rules-read"] = {"status": 503}
        p.locator("#imp-dl").click()
        expect(p.locator("#rules-toasts .toast")).to_contain_text(t("rules.error.read"))
        p.wait_for_timeout(300)
        assert got == []
        env.worker.action_faults.clear()
        name, text = H.download_text(p, lambda: p.locator("#imp-dl").click())
        assert name == "cel-rules-de.md" and "DE-12" in text


def test_copy_prompt_falls_back_to_a_selected_text_when_the_clipboard_refuses(browser):
    with imp(browser) as env:
        p = env.page
        p.evaluate("(() => { navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); })()")
        btn = p.locator("#imp-copy")
        btn.click()
        expect(btn).to_have_text(t("import.prompt.copied"))
        assert p.evaluate("navigator.clipboard.readText()").strip() == prompt_of(template_text()).strip()


def test_copy_prompt_never_says_copied_when_nothing_can_copy_it(browser):
    with imp(browser) as env:
        p = env.page
        p.evaluate("navigator.clipboard.writeText('sentinel')")
        p.evaluate("(() => { navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); document.execCommand = () => false; })()")
        btn = p.locator("#imp-copy")
        btn.click()
        p.wait_for_timeout(600)
        assert btn.inner_text() == t("import.prompt.copy")        # read once: a retrying expect would wait out a wrong "Copied" (2 s)
        assert p.evaluate("navigator.clipboard.readText()") == "sentinel"


def test_every_reason_the_reader_gives_for_a_line_it_did_not_place_has_its_own_words(browser):
    def answer(text, langs):
        a = answer_from_template()
        a["unplaced"] += [
            {"source_text": "The Toronto page: friendlier tone.", "language": None, "reason": "unknown_language"},
            {"source_text": "DE-77 is wrong somewhere.", "language": "de", "reason": "rule_not_found"},
            {"source_text": "Fix the dates rule.", "language": "de", "reason": "ambiguous"},
            {"source_text": "Add visa | somewhere.", "language": "de", "reason": "type_unclear"},
            {"source_text": "Add exam prep again.", "language": "de", "reason": "already_exists"},
            {"source_text": "Perhaps numbers?", "language": "de", "reason": "unreadable"},
        ]
        return a
    with imp(browser, answer=answer) as env:
        p = env.page
        H.upload(p, "#imp-file", "changes.md", template_text())
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))
        items = p.locator("#imp-unplaced .r-un-i")
        expect(items).to_have_count(6)
        want = {
            "The Toronto page: friendlier tone.": t("import.why.page"),
            "DE-77 is wrong somewhere.": t("import.why.noid", id="DE-77", language="German"),
            "Fix the dates rule.": t("import.why.ambiguous"),
            "Add visa | somewhere.": t("import.why.type"),
            "Add exam prep again.": t("import.why.exists"),
            "Perhaps numbers?": t("import.why.unreadable"),
        }
        got = {i.locator(".r-un-q").inner_text().strip("“”\"' “”"): i.locator(".r-un-why").inner_text() for i in items.all()}
        assert got == want, got


def test_every_reason_the_code_gives_for_a_change_it_turned_down_has_its_own_words(browser):
    def ch(kind, source, **kw):
        base = {"language": "de", "kind": kind, "target_id": None, "term": None, "before": None, "after": None,
                "type": None, "matched_by": None, "source_text": source}
        base.update(kw)
        return base

    def answer(text, langs):
        a = answer_from_template()
        a["changes"] += [
            ch("edit_rule", "EDIT DE-77 x", target_id="DE-77", after="x", matched_by="id"),                 # rule_not_found
            ch("add_rule", "ADD empty", after="   "),                                                         # empty_rule
            ch("add_rule", "ADD two lines", after="line one\nline two"),                                      # multiline
            ch("add_rule", "ADD an old one", after="Other rule"),                                             # already_exists
            ch("add_word", "ADD visa", term="visa", after="Visum"),                                           # type_unclear
            ch("edit_word", "EDIT no such word", term="no such word", after="x", type="Always translate as"),  # term_not_found
            ch("edit_rule", "EDIT DE-12 same", target_id="DE-12", after="Currency is written as in English", matched_by="id"),  # unchanged
        ]
        return a
    with imp(browser, answer=answer) as env:
        p = env.page
        H.upload(p, "#imp-file", "changes.md", template_text())
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))
        items = p.locator("#imp-unplaced .r-un-i")
        expect(items).to_have_count(7)
        got = {i.locator(".r-un-q").inner_text().strip("“”\"' “”"): i.locator(".r-un-why").inner_text() for i in items.all()}
        assert got == {
            "EDIT DE-77 x": t("import.why.noid", id="DE-77", language="German"),
            "ADD empty": t("import.why.unreadable"),
            "ADD two lines": t("import.why.unreadable"),
            "ADD an old one": t("import.why.exists"),
            "ADD visa": t("import.why.type"),
            "EDIT no such word": t("import.why.other"),
            "EDIT DE-12 same": t("import.why.other"),
        }, got


# ── 6. Rework round 1: the paths the first review found untested ─────────────────────────────────────────────────────
def wrap_reads(env, scope, change):
    """On top of the spy: a desk-rules-read of exactly `scope` answers change(code, out); every other read is the store's."""
    inner = env.store.handle

    def handle(action, body, who):
        code, out = inner(action, body, who)
        if action == "desk-rules-read" and (body or {}).get("scope") == scope:
            return change(code, out)
        return code, out
    env.store.handle = handle
    return inner


def watch_downloads(page):
    got = []
    page.on("download", lambda d: got.append(d))
    return got


def download_refused(env, scope, change):
    """Download current rules with only `scope` read badly: an error toast, no file, and the button works again."""
    p = env.page
    got = watch_downloads(p)
    healthy = wrap_reads(env, scope, change)
    p.locator("#imp-dl").click()
    expect(p.locator("#rules-toasts .toast")).to_contain_text(t("rules.error.read"))
    p.wait_for_timeout(300)
    assert got == []
    env.store.handle = healthy
    name, text = H.download_text(p, lambda: p.locator("#imp-dl").click())
    assert name == "cel-rules-de.md" and "DE-12" in text and "exam prep" in text


def test_download_current_rules_fails_when_only_the_word_list_cannot_be_read(browser):
    with imp(browser) as env:
        download_refused(env, "words:de", lambda code, out: (503, {"ok": False, "error": "storage busy"}))


def test_download_current_rules_fails_when_the_rules_text_is_blank(browser):
    with imp(browser) as env:
        download_refused(env, "de", lambda code, out: (code, dict(out, body="  \n")))


def test_download_current_rules_fails_when_the_word_list_text_is_blank(browser):
    with imp(browser) as env:
        download_refused(env, "words:de", lambda code, out: (code, dict(out, body="")))


def test_two_clicks_on_download_current_rules_read_once_and_give_one_file(browser):
    with imp(browser) as env:
        p = env.page
        got = watch_downloads(p)
        before = env.worker.calls.count("desk-rules-read")
        env.worker.action_faults["desk-rules-read"] = {"delay": 0.8}
        p.evaluate("(() => { const b = document.getElementById('imp-dl'); b.click(); b.click(); })()")
        p.wait_for_timeout(2500)
        assert env.worker.calls.count("desk-rules-read") - before == 2                 # one pair: the rules and the word list
        assert len(got) == 1


def test_a_file_of_exactly_64_kb_is_read_and_one_byte_more_is_refused(browser):
    with imp(browser) as env:
        p = env.page
        edge = "- ADD: x\n" * 7281 + "\n" * 7
        assert len(edge.encode("utf-8")) == 65536
        H.upload(p, "#imp-file", "edge.md", edge)
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", TOTAL))
        assert env.worker.calls.count("desk-rules-import-read") == 1
        H.upload(p, "#imp-file", "over.md", edge + "\n")
        expect(p.locator("#imp-preview")).to_contain_text(t("import.too.big"))
        expect(p.locator("#imp-apply")).to_have_count(0)
        assert env.worker.calls.count("desk-rules-import-read") == 1                  # the 65,537-byte file never left the page


def test_an_answer_with_no_change_in_it_shows_zero_changes_and_no_apply_button(browser):
    answer = {"changes": [], "unplaced": [{"source_text": "Perhaps numbers?", "language": "de", "reason": "unreadable"}]}
    with imp(browser, answer=answer) as env:
        p = env.page
        H.upload(p, "#imp-file", "changes.md", "Perhaps numbers?\n")
        expect(p.locator("#imp-preview .r-sub-a")).to_have_text(tn("import.found", 0))
        expect(p.locator("#imp-unplaced .r-un-i")).to_have_count(1)
        expect(p.locator("#imp-apply")).to_have_count(0)
        expect(p.get_by_role("button", name=t("import.cancel"))).to_have_count(1)
        assert env.of("desk-rules-import-apply") == []


def test_a_stale_apply_names_each_stale_language_once(browser):
    with imp(browser) as env:
        p = env.page
        upload_template(env)
        for scope, extra in (("de", "- Peer rule [DE-20]\n"), ("fr", "- Peer rule [FR-20]\n"),
                             ("words:fr", "| peer word | x | Always translate as |\n")):
            cur = env.store.rules[scope]
            code, out = env.store.handle("desk-rules-write", {"scope": scope, "body": cur["body"] + extra,
                                                              "baseVersion": cur["version"]}, "peer@example.org")
            assert code == 200, out
        before = {s: env.body(s) for s in SEEDS}
        p.get_by_role("button", name=tn("import.apply", TOTAL)).click()
        expect(notice(env)).to_have_text(t("rules.apply.stale", language="German, French"))   # de, fr, words:fr -> two names
        assert {s: env.body(s) for s in SEEDS} == before
        expect(p.locator("#imp-preview .r-pchg")).to_have_count(TOTAL)


def test_the_downloaded_template_cannot_be_uploaded_with_its_example(browser):
    with imp(browser) as env:
        p = env.page
        name, text = H.download_text(p, lambda: p.locator("#imp-tpl").click())
        assert text == TEMPLATE.read_text(encoding="utf-8").split("<!--\nMAINTAINER NOTE", 1)[0].rstrip() + "\n"
        assert "## 3. A filled example (to read, not to upload)" in text                      # the example is for reading
        part4 = text.split("## 4. Your changes", 1)[1]
        assert "Save the AI's answer as its own .md file and upload that file." in part4
        assert "delete everything above the line before you upload it" in part4
        assert "Delete nothing above it" not in text
        above, below = text.rsplit("\n---\n", 1)
        assert below.strip() == ""                                                            # the Your changes area is empty
        assert "EDIT DE-12" in above                                                          # ... and the example is above the line
        mine = "## German (DE)\n### Rules\n- REMOVE DE-9\n"
        followed = below + mine                                                               # what part 4 asks the client to upload
        assert "EDIT DE-12" not in followed and "ADD: Write dates" not in followed and "REMOVE DE-9" in followed
