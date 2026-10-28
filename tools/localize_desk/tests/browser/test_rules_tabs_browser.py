"""Robot click-tests for the rules page's language tabs and the wording CEL-106 settled (CEL repo, monorepo CEL-106).

  * each of the 8 language tabs starts with its country flag, the one `desk_shared.LOCALES` holds and the desk's
    Export grid prints (`span.doc-flag`, aria-hidden), then the language's name; no dot, and the tab's accessible
    name is still the language's name alone;
  * the Done-by rows an engine check carries out say the check acts when a Weglot file is built, not on a "draft"
    (CEL-099 Verify: no check looks at a draft yet), and "Our quality checks" says "characters", not "half-width
    units";
  * a search typed on one language does not carry over: the next language starts unsearched and, with no
    client rules yet, still lists our own checks (CEL-099 review; the Done-by cards went with CEL-113).

The harness helpers are COPIED from test_rules_quality_browser.py (the convention of this folder: no imports between
test files). Expected wording comes from COPY.md through `copy_text.t`, never typed here. Desktop only (ruling
2026-10-19 23:48). Every test asserts the page raised no error.
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

from localize_desk import desk_shared as S  # noqa: E402
from localize_desk import harness as H  # noqa: E402
from localize_desk.copy_text import t  # noqa: E402

THIRD_PARTY = re.compile(r"^https?://([^/]*\.)?bugherd\.com/")
READY = '#rules-app[data-state="ready"]'
DE_A = ("## 2. Workflow\n\n- SYNTH-CHECKED line\n- SYNTH-PLAIN line\n\n## 6. Numbers\n\n- SYNTH-RULE line\n\n"
        "## 12. Flag\n\n- SYNTH-NOTYET line\n")


def fnv(text: str) -> str:
    """rules_page.js fnv(): FNV-1a 32 of the trimmed UTF-8 text."""
    x = 0x811C9DC5
    for b in text.strip().encode("utf-8"):
        x = ((x ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{x:08x}"


DONE_A = {fnv("- SYNTH-CHECKED line"): ["check", "meta"], fnv("- SYNTH-RULE line"): ["check", "rule"],
          fnv("- SYNTH-NOTYET line"): ["none", "slug"]}


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
    store: object
    page: object = None
    errors: list = field(default_factory=list)


def prime(store, scope: str, body: str) -> None:
    code, out = store.handle("desk-rules-write", {"scope": scope, "body": body, "baseVersion": 0}, "seed:client-md")
    assert code == 200 and out["ok"], out


def seed_a(store) -> None:
    prime(store, "de", DE_A)
    prime(store, "fr", "## 7. Language rules\n\n- **Form of address:** vous\n")


@contextmanager
def rules(browser, *, lang: str = "de", seed=seed_a, done_by: dict | None = None, width: int = 1440):
    with desk() as (base, root, worker):
        env = Env(base=base, store=worker.store)
        seed(env.store)
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
            if msg.type == "error" and not url.endswith("/favicon.ico"):
                env.errors.append(f"console.error: {msg.text} ({url})")

        pg.on("pageerror", lambda e: env.errors.append(f"pageerror: {e}"))
        pg.on("console", on_console)
        pg.goto(f"{base}/admin/localization/rules/?lang={lang}")
        pg.wait_for_selector(READY, timeout=20000)
        try:
            yield env
        finally:
            pg.close()
        assert not env.errors, env.errors


def tab(page, code: str):
    return page.locator(f"#rulesTab-{code}")


# ── 1. the tabs show their flag, not a dot ───────────────────────────────────────────────────────────────
def test_each_language_tab_starts_with_its_flag_and_then_its_name(browser):
    with rules(browser) as env:
        p = env.page
        expect(p.locator('.r-tab[role="tab"]')).to_have_count(len(S.LOCALES))
        for code, _endonym, _dir, flag in S.LOCALES:
            t_ = tab(p, code)
            expect(t_.locator(".r-flag")).to_have_text(flag)
            expect(t_.locator(".r-flag")).to_have_attribute("aria-hidden", "true")
            assert t_.evaluate("el => el.firstElementChild.className") == "r-flag", code        # the flag comes first
            assert t_.inner_text().strip() == f"{flag}{S.lang_name(code)}", code


def test_the_flags_are_the_ones_the_desk_uses_and_each_language_has_its_own(browser):
    flags = [flag for _c, _e, _d, flag in S.LOCALES]
    assert len(flags) == len(set(flags)) == 8 and all(f.strip() and f.isascii() is False for f in flags)
    with rules(browser) as env:
        cfg = env.page.evaluate("JSON.parse(document.getElementById('rules-config').textContent).locales")
        assert [(x["code"], x["flag"]) for x in cfg] == [(c, f) for c, _e, _d, f in S.LOCALES]


def test_a_tab_has_no_dot_and_its_accessible_name_is_the_language_alone(browser):
    with rules(browser) as env:
        p = env.page
        for code, *_ in S.LOCALES:
            assert tab(p, code).locator('[class*="dot"], .doc-st, .r-mk').count() == 0, code
            expect(p.get_by_role("tab", name=S.lang_name(code), exact=True)).to_have_count(1)


def test_the_flags_do_not_change_how_the_tabs_work(browser):
    with rules(browser) as env:
        p = env.page
        expect(tab(p, "de")).to_have_attribute("aria-selected", "true")
        tab(p, "de").focus()
        p.keyboard.press("ArrowRight")
        expect(tab(p, "fr")).to_have_attribute("aria-selected", "true")
        p.keyboard.press("End")
        expect(tab(p, "ar")).to_have_attribute("aria-selected", "true")
        assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# ── 2. the wording: a check acts when a Weglot file is built, not on a draft ─────────────────────────────
@pytest.mark.parametrize("key", ["rules.how.check.meta", "rules.how.check.rule", "rules.qc.auto"])
def test_no_check_line_says_it_acts_on_a_draft(key):
    text = t(key)
    assert "draft" not in text.lower(), text
    if key != "rules.qc.auto":
        assert "Weglot file" in text, text


def test_the_length_lines_say_characters_not_half_width_units():
    for key in ("rules.qc.length", "rules.qc.g5_formatter"):
        text = t(key, title=55, description=130)
        assert "half-width" not in text and "characters" in text and "counts as 2" in text, text


def test_the_also_warns_tooltip_does_not_say_a_check_looks_at_a_draft():
    text = t("rules.by.warn.tip")
    assert "draft" not in text.lower() and "never stops" in text, text


def test_the_also_warns_mark_on_the_page_carries_that_tooltip(browser):
    warn_row = {**DONE_A, fnv("- SYNTH-PLAIN line"): ["prompt", "", "FR-TYPO-01"]}
    with rules(browser, done_by=warn_row) as env:
        mark = env.page.locator("#rules-lang .r-by.warn")
        expect(mark).to_have_count(1)
        expect(mark).to_have_attribute("data-tip", t("rules.by.warn.tip"))
        assert "draft" not in (mark.get_attribute("data-tip") or "").lower()


def test_the_duplicates_line_says_what_the_check_does():
    text = t("rules.qc.g7_duplicates")
    assert text == "No English text twice in the same kind of row" and "once per language" not in text


def test_the_requests_an_engine_check_carries_out_show_the_file_build_wording_on_the_page(browser):
    with rules(browser, done_by=DONE_A) as env:
        how = env.page.locator("#rules-lang .r-rule .r-how")
        expect(how).to_have_text([t("rules.how.check.meta"), t("rules.how.prompt"), t("rules.how.check.rule"),
                                  t("rules.how.none.slug")])
        for text in how.all_inner_texts()[:1] + how.all_inner_texts()[2:3]:
            assert "draft" not in text.lower() and "Weglot file" in text, text


# ── 3. a search does not follow the reviewer to another language ────────────────────────────────────────
def test_a_search_is_gone_on_a_language_without_the_clients_rules_and_ours_still_shows(browser):
    with rules(browser, done_by=DONE_A) as env:
        p = env.page
        p.locator("input[data-search]").fill("zzz")
        expect(p.locator("input[data-search]")).to_have_value("zzz")
        tab(p, "ko").click()
        expect(p.locator("#rules-lang .r-empty")).to_have_text(t("rules.empty", language="Korean"))
        expect(p.locator("input[data-search]")).to_have_count(0)
        expect(p.locator("#rules-quality")).to_have_count(1)
        assert p.locator("#rules-quality .r-qc").count() > 20
        tab(p, "de").click()
        expect(p.locator("input[data-search]")).to_have_value("")                 # coming back starts unsearched
