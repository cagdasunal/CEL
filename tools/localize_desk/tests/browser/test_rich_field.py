"""The text-fidelity matrix (guard G13) for WO-22's always-open field -- the spike.

Monorepo runbook WO-22: "First, a spike in the harness: the editable field with link
chips, tested against the text-fidelity matrix -- no-break spaces survive and typing never
adds one; Japanese and Korean IME (nothing acts mid-composition, R28); Arabic RTL with
chips; paste arrives as plain text; every link serialization in the corpus round-trips its
<a wg-N=""> markers byte for byte (R29); undo. If the spike fails the matrix, stop and
report -- do not build on it." This is that matrix, in a real Chromium, against
`tools/localize_desk/spike/rich_field.{js,css}`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api",
                    reason="Playwright lives in the monorepo's .venv314; the CEL hook and the "
                           "browser CI job run this file with it")
from playwright.sync_api import sync_playwright  # noqa: E402

TOOLS = Path(__file__).resolve().parents[3]
SPIKE = TOOLS / "localize_desk" / "spike"
UNITS = TOOLS.parent / "data" / "localize" / "units"
LINKED = '<a wg-1="">Get Directions</a> from the  station, then <a wg-2="">call us</a>.'


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()


def _field(page, text, *, lang="de", css=True):
    page.set_content(f'<!doctype html><html><body><div id="f" lang="{lang}"></div></body></html>')
    if css:
        page.add_style_tag(path=str(SPIKE / "rich_field.css"))
    page.add_script_tag(path=str(SPIKE / "rich_field.js"))
    page.evaluate("""t => {
        window.commits = []; window.cancels = 0;
        window.rf = RichField.attach(document.getElementById('f'),
            { text: t, onCommit: v => commits.push(v), onCancel: () => { cancels++; } });
    }""", text)


def _value(page) -> str:
    return page.evaluate("() => rf.value()")


def _caret_at_end(page):
    page.evaluate("""() => {
        const f = document.getElementById('f'); f.focus();
        const r = document.createRange(); r.selectNodeContents(f); r.collapse(false);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }""")


def _corpus() -> list[str]:
    out = []
    for f in sorted(UNITS.glob("*.json")):
        for u in json.loads(f.read_text(encoding="utf-8"))["units"]:
            out.append(u["word_from"])
            out += [c.get("word_to", "") for c in (u.get("current") or {}).values() if c]
    return [t for t in out if t]


def test_every_text_in_the_corpus_round_trips_byte_for_byte(page):
    """R29: render, serialise, compare -- every English text and every live translation."""
    texts = _corpus()
    assert len(texts) > 11000 and sum('<a wg-' in t for t in texts) > 1800
    _field(page, "")
    bad = page.evaluate("""texts => texts.filter(t => {
        const d = document.createElement('div');
        RichField.render(d, t);
        return RichField.serialize(d) !== t;
    }).slice(0, 5)""", texts)
    assert bad == []


def test_a_linked_text_survives_being_attached_and_focused(page):
    _field(page, LINKED)
    _caret_at_end(page)
    assert _value(page) == LINKED
    assert page.locator("#f .rf-token").count() == 4


def test_typing_spaces_never_adds_a_no_break_space(page):
    _field(page, "Hallo")
    _caret_at_end(page)
    page.keyboard.type("  Welt ")
    assert _value(page) == "Hallo  Welt "


def test_the_stylesheet_is_what_keeps_no_break_spaces_out(page):
    """Verify the verifier: without pre-wrap, Chrome types U+00A0 -- so the test above can fail."""
    _field(page, "Hallo", css=False)
    _caret_at_end(page)
    page.keyboard.type("  Welt ")
    assert " " in _value(page)


def test_nothing_acts_while_a_composition_is_open(page):
    """R28: mid-composition, Enter picks an IME candidate; it must not commit the row."""
    _field(page, "こんにちは", lang="ja")
    _caret_at_end(page)
    page.evaluate("() => document.getElementById('f').dispatchEvent(new CompositionEvent('compositionstart', {bubbles: true}))")
    page.keyboard.press("ControlOrMeta+Enter")
    assert page.evaluate("() => commits.length") == 0
    page.evaluate("() => document.getElementById('f').dispatchEvent(new CompositionEvent('compositionend', {bubbles: true}))")
    page.keyboard.press("ControlOrMeta+Enter")
    assert page.evaluate("() => commits") == ["こんにちは"]


def test_a_real_ime_composition_commits_its_text(page):
    """Through Chrome's own IME path (DevTools Input.imeSetComposition / insertText)."""
    _field(page, "안녕", lang="ko")
    _caret_at_end(page)
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": "하세", "selectionStart": 2, "selectionEnd": 2})
    cdp.send("Input.insertText", {"text": "하세요"})
    assert _value(page) == "안녕하세요"


def test_arabic_runs_right_to_left_with_its_chips(page):
    text = '<a wg-1="">اتصل بنا</a> للمزيد من المعلومات.'
    _field(page, text, lang="ar")
    assert page.evaluate("() => getComputedStyle(document.getElementById('f')).direction") == "rtl"
    _caret_at_end(page)
    page.keyboard.type(" شكرا")
    assert _value(page) == text + " شكرا"


def test_paste_arrives_as_plain_text_and_cannot_forge_a_marker(page):
    _field(page, "Hallo")
    _caret_at_end(page)
    page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.setData('text/plain', ' <a wg-9="">fake</a>\\nline two');
        dt.setData('text/html', '<b>bold</b>');
        document.getElementById('f').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    }""")
    assert _value(page) == "Hallo fake line two"
    assert page.locator("#f b").count() == 0


def test_typed_marker_syntax_is_not_a_marker(page):
    _field(page, "Hallo")
    _caret_at_end(page)
    page.keyboard.type(' <a wg-9="">x</a>')
    assert _value(page) == "Hallo x"


def test_backspace_cannot_delete_a_link_marker(page):
    _field(page, LINKED)
    # the caret just after the first chip (<a wg-1="">)
    page.evaluate("""() => {
        const f = document.getElementById('f'); f.focus();
        const r = document.createRange(); r.setStartAfter(f.querySelector('.rf-token')); r.collapse(true);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }""")
    page.keyboard.press("Backspace")
    assert _value(page) == LINKED
    _caret_at_end(page)
    page.keyboard.press("Backspace")           # plain text still deletes
    assert _value(page) == LINKED[:-1]


def test_selecting_across_a_marker_and_typing_changes_nothing(page):
    _field(page, LINKED)
    page.evaluate("""() => {
        const f = document.getElementById('f'); f.focus();
        const r = document.createRange(); r.selectNodeContents(f);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }""")
    page.keyboard.type("x")
    assert _value(page) == LINKED


def test_undo_takes_back_typing(page):
    _field(page, "Hallo")
    _caret_at_end(page)
    page.keyboard.type(" Welt")
    assert _value(page) == "Hallo Welt"
    page.keyboard.press("ControlOrMeta+z")
    assert _value(page) == "Hallo"


def test_enter_adds_no_line_and_escape_restores(page):
    _field(page, "Hallo")
    _caret_at_end(page)
    page.keyboard.press("Enter")
    assert _value(page) == "Hallo" and page.evaluate("() => commits.length") == 0
    page.keyboard.type(" Welt")
    page.keyboard.press("Escape")
    assert _value(page) == "Hallo" and page.evaluate("() => cancels") == 1


def test_show_html_shows_the_markers_and_changes_nothing(page):
    _field(page, LINKED)
    page.evaluate("() => rf.showHtml(true)")
    labels = page.locator("#f .rf-token").all_inner_texts()
    assert labels == ['<a wg-1="">', "</a>", '<a wg-2="">', "</a>"]
    assert _value(page) == LINKED
    page.evaluate("() => rf.showHtml(false)")
    assert page.locator("#f .rf-token").first.inner_text() == "‹1"
