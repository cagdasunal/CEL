"""Robot click-tests for "Our quality checks" on the rules page (CEL-099): /admin/localization/rules/.

Under the client's sections each language lists the rules we add to Gemini's prompt and the checks the engine
runs, one line each, tagged "In the prompt" or "Checked automatically". The list is built in the monorepo from the
engine's own sources (runtime/out/loc2/CEL-099/build_quality.py writes rules_quality.json, which the page
inlines): the words are COPY.md's `rules.qc.<key>`, every number in them is the source's. With a Done-by card
pressed, a section holding no matching request is not drawn, nor its rail entry (CEL-089 Found 3).

The harness helpers are COPIED from test_rules_readonly_browser.py (the convention of this folder: no imports
between test files). Expected wording comes from COPY.md through `copy_text.t`, never typed here. Desktop only
(ruling 2026-10-19 23:48). Every test asserts the page raised no error.
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
QUALITY = json.loads((Path(__file__).resolve().parents[2] / "rules_quality.json").read_text(encoding="utf-8"))
NAMES = {"de": "German", "fr": "French", "ko": "Korean"}
DE_V1 = "## 7. Language rules\n\n- **Form of address:** du\n- **Markets:** CH\n"
FR_V1 = "## 7. Language rules\n\n- **Form of address:** vous\n"
# a body with three sections; the Done-by map below names one line of §2 "check" and one of §12 "none"
DE_A = ("## 2. Workflow\n\n- SYNTH-CHECKED line\n- SYNTH-PLAIN line\n\n## 6. Numbers\n\n- SYNTH-SIX line\n\n"
        "## 12. Flag\n\n- SYNTH-NOTYET line\n")


def fnv(text: str) -> str:
    """rules_page.js fnv(): FNV-1a 32 of the trimmed UTF-8 text."""
    x = 0x811C9DC5
    for b in text.strip().encode("utf-8"):
        x = ((x ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{x:08x}"


DONE_A = {fnv("- SYNTH-CHECKED line"): ["check", "meta"], fnv("- SYNTH-NOTYET line"): ["none", "slug"]}


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


def seed_default(store, de: str = DE_V1) -> None:
    prime(store, "de", de)
    prime(store, "fr", FR_V1)


@contextmanager
def rules(browser, *, lang: str = "de", seed=seed_default, done_by: dict | None = None, width: int = 1440):
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


def expected(lang: str) -> list[str]:
    return [t(f"rules.qc.{key}", language=NAMES[lang], **params) for _kind, key, params in QUALITY["langs"][lang]]


def section_ids(page) -> list[str]:
    return page.locator("#rulesPanel section").evaluate_all("els => els.map(e => e.id)")


# ── 1. the list: one line per rule and check, tagged, under the client's sections ─────────────────────────
def test_the_page_inlines_the_quality_list_it_was_built_with(browser):
    with rules(browser) as env:
        cfg = env.page.evaluate("JSON.parse(document.getElementById('rules-config').textContent).quality")
        assert cfg == QUALITY


@pytest.mark.parametrize("lang", ["de", "fr"])
def test_each_language_lists_our_rules_and_checks_one_line_each_under_the_clients_sections(browser, lang):
    with rules(browser, lang=lang) as env:
        p = env.page
        assert section_ids(p) == ["rules-s7", "rules-quality"]
        sec = p.locator("#rules-quality")
        expect(sec.locator("h2")).to_have_text(t("rules.quality"))
        expect(sec.locator(".r-qc .r-words")).to_have_text(expected(lang))
        tags = [t("rules.by.prompt") if kind == "prompt" else t("rules.qc.auto") for kind, *_ in QUALITY["langs"][lang]]
        expect(sec.locator(".r-qc .r-by")).to_have_text(tags)
        expect(p.locator(".r-rail a").nth(1)).to_contain_text(t("rules.quality"))
        assert sec.locator("[contenteditable], input, textarea, select, button").count() == 0      # ours: not editable


def test_a_language_shows_its_own_checks_and_not_another_languages(browser):
    de_only, fr_only = t("rules.qc.informal_du"), t("rules.qc.vous_not_tu")
    with rules(browser, lang="de") as env:
        lines = env.page.locator("#rules-quality .r-words").all_inner_texts()
        assert de_only in lines and fr_only not in lines


def test_the_numbers_on_the_page_are_the_ones_the_list_was_built_with(browser):
    with rules(browser) as env:
        params = {key: p for _k, key, p in QUALITY["langs"]["de"]}
        text = env.page.locator("#rules-quality").inner_text()
        for key in ("length", "g5_formatter", "g11_size"):
            assert params[key] and all(str(v) in text for v in params[key].values()), (key, params[key])
        assert "{" not in text, "a placeholder was left unfilled"


def test_a_language_without_the_clients_rules_still_lists_ours(browser):
    with rules(browser, lang="ko") as env:
        expect(env.page.locator("#rules-lang .r-empty")).to_have_text(t("rules.empty", language=NAMES["ko"]))
        expect(env.page.locator("#rules-quality .r-qc .r-words")).to_have_text(expected("ko"))


# ── 2. a search hides the sections with nothing to show, and their rail entries ───────────────────────────
def test_a_search_hides_every_section_without_a_match_and_its_rail_entry(browser):
    with rules(browser, seed=lambda s: seed_default(s, de=DE_A), done_by=DONE_A) as env:
        p = env.page
        visible = lambda: [x for x in section_ids(p) if p.locator(f"#{x}").is_visible()]    # noqa: E731
        assert section_ids(p) == ["rules-s2", "rules-s6", "rules-s12", "rules-quality"]
        p.locator("input[data-search]").fill("synth-checked")
        assert visible() == ["rules-s2"]
        expect(p.locator(".r-rail a:visible")).to_have_count(1)
        p.locator("input[data-search]").fill("synth-notyet")
        assert visible() == ["rules-s12"]
        p.locator("input[data-search]").fill("")
        assert visible() == ["rules-s2", "rules-s6", "rules-s12", "rules-quality"]
        expect(p.locator(".r-rail a:visible")).to_have_count(4)
