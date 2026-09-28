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
LINKED = '<a wg-1="">Get Directions</a> from the \u00a0station, then <a wg-2="">call us</a>.'


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
    assert "\u00a0" in _value(page)


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
    text = '<a wg-1="">اتصل بنا</a> للمزيد\u00a0من المعلومات.'
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


# ---- #5 review (2026-09-28): edits over a selection, the live field, the character classes ----

@pytest.fixture()
def secure_page(browser):
    """A page with a real clipboard: a secure origin and the clipboard permissions, so a
    trusted Cmd+V fires only `paste` -- the path a synthetic ClipboardEvent does not take."""
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    pg = ctx.new_page()
    pg.route("https://desk.test/", lambda r: r.fulfill(status=200, content_type="text/html",
                                                        body="<!doctype html><title>t</title>"))
    pg.goto("https://desk.test/")
    yield pg
    ctx.close()


def _markers(text: str) -> list[str]:
    import re
    return re.findall(r'<a wg-[0-9]+="">|</a>|<br>', text)


def _select(page, a: int, a_off: int, b: int, b_off: int):
    """Select from text node `a` at `a_off` to text node `b` at `b_off` (the field's own
    text nodes, chips skipped)."""
    page.evaluate("""([a, ao, b, bo]) => {
        const f = document.getElementById('f'); f.focus();
        const tn = [...f.childNodes].filter(n => n.nodeType === 3);
        const r = document.createRange(); r.setStart(tn[a], ao); r.setEnd(tn[b], bo);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }""", [a, a_off, b, b_off])


def _select_all(page):
    page.evaluate("""() => {
        const f = document.getElementById('f'); f.focus();
        const r = document.createRange(); r.selectNodeContents(f);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    }""")


def _real_paste(page, text: str):
    page.evaluate("t => navigator.clipboard.writeText(t)", text)
    page.keyboard.press("ControlOrMeta+V")


def _chips_untouched(page) -> bool:
    """The field's own chip elements are all still in it: the edit was REFUSED. A rollback
    by the backstop re-renders them, which would leave the kept references detached."""
    return page.evaluate("() => window.keptChips.every(c => c.isConnected)")


def _keep_chips(page):
    page.evaluate("() => { window.keptChips = [...document.querySelectorAll('#f .rf-token')]; }")


def test_a_real_paste_over_everything_keeps_every_marker(secure_page):
    """E-1: Cmd+A, Cmd+V on a linked text left 'Neue Übersetzung' -- all four markers gone.
    A paste over a selection that takes a marker changes nothing, as typing over it does."""
    _field(secure_page, LINKED)
    _keep_chips(secure_page)
    _select_all(secure_page)
    _real_paste(secure_page, "Neue Übersetzung")
    assert _value(secure_page) == LINKED
    assert _chips_untouched(secure_page)


def test_a_real_paste_across_a_closing_marker_keeps_it(secure_page):
    """E-1: from 'Get |' to 'from|' crosses </a>: the paste gave '<a wg-1="">Get X the ...'."""
    _field(secure_page, LINKED)
    _keep_chips(secure_page)
    _select(secure_page, 0, 4, 1, 5)
    _real_paste(secure_page, "X")
    assert _value(secure_page) == LINKED
    assert _chips_untouched(secure_page)


def test_a_real_paste_inside_plain_text_still_replaces_the_selection(secure_page):
    _field(secure_page, LINKED)
    _select(secure_page, 1, 1, 1, 5)                       # ' from' -> ' X'
    _real_paste(secure_page, "X")
    assert _value(secure_page) == LINKED.replace(" from the", " X the", 1)


@pytest.mark.parametrize("where", ["across </a>", "everything"])
def test_an_ime_composition_over_a_marker_keeps_every_marker(page, where):
    """E-1: a composition cannot be cancelled; over a selection across </a> it gave
    '<a wg-1="">Get 하 the ...'. Whatever the IME inserts, no marker is lost."""
    _field(page, LINKED, lang="ko")
    if where == "everything":
        _select_all(page)
    else:
        _select(page, 0, 4, 1, 5)
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": "하", "selectionStart": 1, "selectionEnd": 1})
    cdp.send("Input.insertText", {"text": "하"})
    got = _value(page)
    assert _markers(got) == _markers(LINKED), got
    assert got.replace("하", "") == LINKED, got           # nothing selected was deleted
    assert "하" in got, got                               # and the composed text was kept


def test_any_edit_that_loses_a_marker_is_rolled_back(page):
    """The backstop: an editing path the guards do not foresee (here execCommand, which fires
    no beforeinput) still cannot change the markers -- the field goes back to its last text."""
    _field(page, LINKED)
    _caret_at_end(page)
    page.keyboard.type(" ok")
    _select(page, 0, 4, 1, 5)
    page.evaluate("() => document.execCommand('delete')")
    assert _value(page) == LINKED + " ok"


def test_every_distinct_text_survives_editing_in_the_live_field(page):
    """E-2: the corpus test above goes through a detached element. Here each distinct text is
    attached to a real, styled, focused field and edited at both ends through the browser's
    own editing commands (insert, then delete); it must come back exactly. Compared inside
    the page, so a lone surrogate is not rewritten on its way out.

    One named exception: a text with no visible character. The corpus has one -- a Vancouver
    unit whose English is a lone U+200D, copied by all eight languages. Chrome deletes "y" +
    ZWJ as one cluster there, so its edit-and-undo cannot come back exactly; there is nothing
    in it to review, and the engine should drop it as noise (#5 review, 2026-09-28). It is
    held to exactly that set, and still has to load and read back unchanged."""
    import unicodedata
    texts = sorted(set(_corpus()))
    assert len(texts) > 7000
    invisible = [t for t in texts if not any(unicodedata.category(c)[0] in "LNPS" for c in t)]
    assert invisible == ["\u200d"], invisible
    texts = [t for t in texts if t not in invisible]
    _field(page, "")
    assert page.evaluate("""ts => ts.every(t => {
        const el = document.createElement('div'); document.body.appendChild(el);
        const rf = RichField.attach(el, { text: t }); el.focus();
        const ok = rf.value() === t; rf.detach(); el.remove(); return ok;
    })""", invisible)
    bad = page.evaluate("""texts => {
        const out = [];
        for (const t of texts) {
            const el = document.createElement('div');
            document.body.appendChild(el);
            const rf = RichField.attach(el, { text: t });
            el.focus();
            const s = getSelection(), r = document.createRange();
            r.selectNodeContents(el); r.collapse(false); s.removeAllRanges(); s.addRange(r);
            document.execCommand('insertText', false, 'x');
            document.execCommand('delete');
            r.selectNodeContents(el); r.collapse(true); s.removeAllRanges(); s.addRange(r);
            document.execCommand('insertText', false, 'y');
            document.execCommand('delete');
            if (rf.value() !== t) out.push([t, rf.value()]);
            rf.detach(); el.remove();
            if (out.length >= 5) break;
        }
        return out;
    }""", texts)
    assert bad == []


# Written with escapes: an editor cannot quietly turn one into a space.
VECTORS = [
    "a b", "a b", "a b", "a​b", "a‌b", "a‍b", "‎ab‏",
    "؜ab", "a b", "a b", "a\tb", "a\rb", "a\nb", "a\r\nb", "é café",
    "  lead", "trail  ", "a   b", "\U0001F600 ❤️", "1 < 2 & 3 > 2", "&amp; &lt;b&gt; <b>",
    "العربية ‏(١)", "日本語　漢字",
    '<a wg-1="">x y</a> <a wg-2="">z</a>', "x" * 20000 + " ",
]


@pytest.mark.parametrize("attached", [False, True], ids=["detached", "live field"])
def test_every_character_class_round_trips(page, attached):
    """E-3: the corpus holds none of U+202F, U+2009, U+200B, ZWNJ, bidi marks, U+2028/9, tab,
    CR/LF, NFD, edge spaces or astral emoji, so mutants that drop or normalise them survived.
    Each vector goes through render/serialise, and through the live field with an edit at the
    end, and must come back exactly -- no trimming, no normalisation."""
    _field(page, "")
    bad = page.evaluate("""([texts, attached]) => {
        const out = [];
        for (const t of texts) {
            const el = document.createElement('div');
            document.body.appendChild(el);
            let got;
            if (!attached) { RichField.render(el, t); got = RichField.serialize(el); }
            else {
                const rf = RichField.attach(el, { text: t });
                el.focus();
                const s = getSelection(), r = document.createRange();
                r.selectNodeContents(el); r.collapse(false); s.removeAllRanges(); s.addRange(r);
                document.execCommand('insertText', false, 'x');
                document.execCommand('delete');
                got = rf.value(); rf.detach();
            }
            el.remove();
            if (got !== t) out.push([t.slice(0, 40), got.slice(0, 40)]);
        }
        return out;
    }""", [VECTORS, attached])
    assert bad == []


def test_a_lone_surrogate_round_trips(page):
    """Compared in the page: Playwright rewrites a lone surrogate to U+FFFD on its way out."""
    _field(page, "")
    assert page.evaluate("""() => {
        const t = 'a\\ud800b\\udc00c', el = document.createElement('div');
        RichField.render(el, t);
        return RichField.serialize(el) === t;
    }""")


def test_a_pasted_no_break_space_is_kept(page):
    """E-4: Word and Google Docs clipboards carry U+00A0 and U+202F; the paste keeps both."""
    _field(page, "Prix")
    _caret_at_end(page)
    page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.setData('text/plain', '\\u00a0: 100\\u202f000\\u00a0C$');
        document.getElementById('f').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    }""")
    assert _value(page) == "Prix : 100 000 C$"


def test_an_html_only_clipboard_pastes_its_text(page):
    """A clipboard holding only text/html pasted nothing. Its text arrives -- as text."""
    _field(page, "Hallo")
    _caret_at_end(page)
    page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.setData('text/html', '<p> <b>Welt</b><img src=x onerror="window.pwned=1"></p>');
        document.getElementById('f').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    }""")
    assert _value(page) == "Hallo Welt"
    assert page.evaluate("() => window.pwned === undefined")


def test_attaching_twice_does_not_double_a_paste(page):
    """A field attached again (a re-render into the same element) had two paste listeners."""
    _field(page, "Hallo")
    page.evaluate("() => { window.rf = RichField.attach(document.getElementById('f'), { text: 'Hallo' }); }")
    _caret_at_end(page)
    page.evaluate("""() => {
        const dt = new DataTransfer(); dt.setData('text/plain', 'X');
        document.getElementById('f').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    }""")
    assert _value(page) == "HalloX"


def test_show_html_keeps_an_arabic_field_right_to_left(page):
    """dir=auto read the Latin letters of a chip's raw marker, and an Arabic field that starts
    with a link flipped to left-to-right under "Show HTML"."""
    _field(page, '<a wg-1="">اتصل بنا</a> للمزيد.', lang="ar")
    page.evaluate("() => rf.showHtml(true)")
    assert page.evaluate("() => getComputedStyle(document.getElementById('f')).direction") == "rtl"
