"""The desk's colours say one thing each (ruling #53; runbook WO-07, guard G12).

Indigo is the dashboard's button colour. The operator read the filled indigo language tab
as a button (2026-09-23), and an audit found indigo meaning seven things at once — the
primary button, the active tab, selection, requests, arrivals, the progress bar, focus
(R32, R33). The role table (process contract §8 U1) gives each state one colour; this
lints the desk's stylesheet against it, so a later edit cannot quietly bring it back.

It reads the vendored `tools/dashboard.py` (the monorepo is its source; the CEL hook runs
this whenever that file is mirrored) and the desk's own `STAGE_BADGE`.
"""
from __future__ import annotations

import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
DASH = (TOOLS / "dashboard.py").read_text(encoding="utf-8")
GEN = (TOOLS / "localize_desk" / "generate_desk_page.py").read_text(encoding="utf-8")

INDIGO = re.compile(r"var\(--accent\)|93,\s*96,\s*238|#5d60ee", re.I)
# The only places indigo may appear: focus (keyboard and focus rings), the checkbox tick,
# and the page's one primary button.
INDIGO_OK = (":focus-visible", ".desk-pick", ".desk-btn.is-primary", ".is-cursor")


def _desk_css() -> str:
    i = DASH.index('DESK_CSS = """') + len('DESK_CSS = """')
    return DASH[i:DASH.index('"""', i)]


def _rules(css: str):
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = " ".join(m.group(1).split("*/")[-1].split())
        yield sel, " ".join(m.group(2).split())


def _rule(css: str, selector: str) -> str:
    bodies = [b for s, b in _rules(css) if selector in [x.strip() for x in s.split(",")]]
    assert bodies, f"no rule for {selector}"
    return " ".join(bodies)


def test_indigo_only_on_focus_the_tick_and_the_one_primary():
    wrong = [f"{s} {{ {b} }}" for s, b in _rules(_desk_css())
             if INDIGO.search(b) and not any(ok in s for ok in INDIGO_OK)]
    assert not wrong, "indigo outside its roles:\n" + "\n".join(wrong)


def test_no_hard_coded_colours():
    hits = re.findall(r"#fff(?:fff)?\b|#4e51be|rgba\(255,\s*255,\s*255", _desk_css(), re.I)
    assert not hits, f"hard-coded colours in DESK_CSS (use tokens): {hits}"


def test_every_status_label_has_a_style():
    classes = set(re.findall(r"\[t\('status\.[a-z]+'\), '([a-z-]+)'\]", GEN))
    classes |= set(re.findall(r"badge\.className = 'desk-state ([a-z-]+)'", GEN))
    assert classes, "STAGE_BADGE not found"
    missing = [c for c in classes if not re.search(r"\." + re.escape(c) + r"\b[^{]*\{", DASH)]
    assert not missing, f"status labels with no style: {missing}"


def test_the_active_language_tab_is_not_a_filled_button():
    body = _rule(_desk_css(), ".desk-loc.is-active")
    assert "background" not in body, f"the active tab is filled: {body}"


def test_waiting_rows_carry_no_tint_and_only_selection_is_neutral():
    css = _desk_css()
    for sel in (".desk-row.is-queued > td", ".desk-row.is-sending > td"):
        tinted = [b for s, b in _rules(css) if sel in [x.strip() for x in s.split(",")] and "background" in b]
        assert not tinted, f"{sel} is tinted: {tinted}"


def test_progress_is_green():
    assert "var(--ok)" in _rule(_desk_css(), ".desk-meter-fill")


def test_no_browser_title_tooltips():
    """Ruling #51 (runbook WO-08): the browser's own `title` tooltip waits about a second,
    never shows on keyboard focus or touch, and doubles up with ours. Desk controls carry
    `data-tip` (from COPY.md) and keep `aria-label`; `title` is left to the page's <title>."""
    # `document.title` is the page's <title> (the browser tab), renamed on a language switch.
    typed = re.findall(r"(?<!document)\.title\s*=", GEN)
    markup = [m for m in re.findall(r"""\btitle=['"{]""", GEN)]
    assert not typed, f"script sets .title {len(typed)} times"
    assert not markup, f"markup carries title= {len(markup)} times"
