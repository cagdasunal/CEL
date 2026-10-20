"""The rules page of the localization desk: /admin/localization/rules/ (CEL-046).

The client reads and edits the translation rules the engine gives Gemini: the shared rules,
one language's rules, its glossary and the four page briefs, each its own versioned scope in
the Worker's D1 store (ruling 2026-10-19 23:32). Layout: option A, "two sheets" (monorepo
runtime/out/loc2/design-rules/option-a.html), with no white or near-white backgrounds
(ruling 2026-10-20 00:29). Spec: runtime/out/loc2/rules-editor-spec.md (CEL-040).

This file writes ONE page and no data: the rule bodies are the client's documents and this
repository is public, so the page reads them from the Worker at run time, behind sign-in.
Every word comes from COPY.md (the "Rules page" section).

    cd tools && python3 -m localize_desk.generate_rules_page
"""
from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from localize_desk import desk_shared as S  # noqa: E402
from localize_desk.copy_text import JS_HELPERS, js_table, t  # noqa: E402
from localize_desk.generate_document_page import DESK_CHANGELOG_URL, DESK_VERSION  # noqa: E402

from dashboard import render_admin_close, render_admin_open  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = S.OUT_ROOT / "rules"
PAGE_JS = HERE / "rules_page.js"
MD_JS = HERE / "rules_md.js"

# Languages with no rules from the client yet: the seed holds one "no rules" line for them.
NO_RULES = ("ja", "ko", "ar")

# The labelled rules a tools/localize/rules check enforces (CLIENT_RULES, gate 18): editing one
# shows "an automatic check still expects the old rule". Matched on the item's bold label.
CHECKED = {
    "de": ["Form of address", "Orthography"],          # DE-REGISTER-01, DE-ORTH-01
    "fr": ["Form of address", "Typography"],           # FR-REGISTER-01, FR-TYPO-01/02
    "es": ["Form of address", "Regional variant"],     # ES-REGISTER-01, ES-LEX-01
    "pt": ["Regional variant"],                        # PT-LEX-01/02
    "it": ["Form of address", "Notes"],                # IT-REGISTER-01, IT-TERM-01
}

# CEL's own suggestions for a language with no rules (paraphrases of the monorepo's
# runtime/out/loc2/E-rules.md, shown as "Suggested by CEL (not confirmed)"), never client text.
SUGGESTED = {
    "ja": [["Register", "です・ます (polite)"], ["Currency", "C$1,890; no bare $, no full-width digits"],
           ["Dates", "2026年3月15日"], ["Brand", "never written in katakana"]],
    "ko": [["Register", "합니다체; 해요체 only on buttons"], ["Currency", "C$1,890; no bare $ or 달러"],
           ["Dates", "2026년 3월 15일"]],
    "ar": [["Register", "Modern Standard Arabic, formal, no dialect"], ["Currency", "C$1,890; no bare $"],
           ["Digits", "1, 2, 3 (Eastern digits optional)"], ["Direction", "right to left"]],
}

# A page brief's sections, in the order of the existing brief files (spec §1).
BRIEF_SECTIONS = ("Page topic", "Page intent", "Main keyword", "Required keyword concepts", "Natural variants",
                  "AEO/GEO questions to answer", "Cultural translation guidance", "Cannibalization guardrails",
                  "Translation improvement priorities", "Suggested answer block")

# Page CSS: tokens only (no hex, no rgba, no !important). Option A's look, with every sheet,
# card, menu, modal, drawer, bar and toast on the cream surface and the stage one step deeper.
RULES_CSS = """
.rules { --pad: 48px; --muted: color-mix(in srgb, var(--fg) 76%, transparent); --faint: color-mix(in srgb, var(--fg) 74%, transparent); }
/* WCAG AA on this page (review CEL-046 fix 4): the dashboard's --muted (--fg at 65%) is 3.93:1 on the cream and
   3.68:1 on the selected stage, --faint (45%) 2.40:1. Here they are --fg at 76% (5.30 / 4.82) and 74% (5.01 / 4.58). */
.rules .r-top { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 12px 24px; flex-wrap: wrap; padding: 12px 24px; }
.rules .crumb { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; margin: 0; font-size: var(--fs-xl); font-weight: 650; }
.rules .sep { color: var(--faint); }
.rules .cw { position: relative; }
.rules .crumb-b { font: inherit; color: inherit; background: none; border: 0; border-bottom: 1px dotted var(--border-strong); padding: 2px 0; cursor: pointer; }
.rules .acts { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.rules .menu { position: absolute; top: calc(100% + 6px); left: 0; z-index: 40; min-width: 240px; background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius); box-shadow: 0 8px 24px var(--border-strong); padding: 6px; display: flex; flex-direction: column; font-size: var(--fs-md); font-weight: 400; }
.rules .menu-item { text-align: left; background: none; border: 1px solid transparent; border-radius: var(--radius-sm); padding: 7px 10px; font: inherit; color: inherit; cursor: pointer; }
.rules .menu-item:hover { background: var(--stripe); }
.rules .menu-item.is-on { border-color: var(--fg); font-weight: 700; }
.rules .menu-item .none { font-weight: 400; color: var(--muted); }
.rules .shell { display: grid; grid-template-columns: 240px minmax(0, 1fr); align-items: start; }
.rules .rail { position: sticky; top: 0; max-height: calc(100vh - 44px); overflow: auto; padding: 20px 12px 20px 24px; }
.rules .ol-h { margin: 0 0 10px 12px; font-size: var(--fs-xs); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
.rules .ol-item { display: block; width: 100%; text-align: left; background: none; border: 0; border-left: 2px solid transparent; padding: 7px 10px; cursor: pointer; color: inherit; font: inherit; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.rules .ol-item:hover { background: var(--stripe); }
.rules .ol-item.is-cur { border-left-color: var(--fg); background: var(--selected); }
.rules .ol-item.ol-sub { padding-left: 22px; }
.rules .ol-l { font-size: var(--fs-md); line-height: 1.3; }
.rules .ol-c { font-size: var(--fs-xs); color: var(--muted); margin-top: 2px; }
.rules .stage { min-width: 0; background: var(--selected); border-left: 1px solid var(--border); padding: 24px; min-height: 100vh; }
.rules .sheets { max-width: 1400px; margin: 0 auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 24px; align-items: start; }
.rules .sheet { min-width: 0; background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius); padding: 0 var(--pad) 40px; scroll-margin-top: 12px; }
.rules .sheet-head { position: sticky; top: 0; z-index: 6; margin: 0 calc(var(--pad) * -1); padding: 14px var(--pad) 10px; background: var(--surface); border-bottom: 1px solid var(--border); border-radius: var(--radius) var(--radius) 0 0; font-size: var(--fs-sm); font-weight: 650; }
.rules .sheet-body { padding-top: 32px; }
.rules .shared-block { border: 1px solid var(--border-strong); border-radius: var(--radius); padding: 14px 16px; }
.rules .blk-label { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; color: var(--muted); }
.rules .card { border-top: 1px solid var(--border); padding: 12px 0 4px; margin-top: 12px; scroll-margin-top: 56px; }
.rules .blk-label + .card { border-top: 0; margin-top: 6px; }
.rules .sec-h { margin: 28px 0 8px; font-size: var(--fs-lg); font-weight: 600; scroll-margin-top: 56px; }
.rules .sec-h:first-child { margin-top: 0; }
.rules .r-b { position: relative; margin: 0 0 6px; font-size: var(--fs-base); line-height: 1.5; }
.rules .r-h1 { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; margin-top: 10px; }
.rules .r-h2 { font-size: var(--fs-doc-body, 16px); font-weight: 650; margin-top: 4px; }
.rules .r-h3, .rules .r-h4, .rules .r-h5, .rules .r-h6 { font-weight: 650; margin-top: 12px; }
.rules .r-quote { border-left: 2px solid var(--border-strong); padding-left: 10px; color: var(--muted); }
.rules .r-items { margin: 4px 0 8px; padding-left: 20px; }
.rules .r-hr { border: 0; border-top: 1px solid var(--border); margin: 12px 0; }
.rules .r-table { display: grid; gap: 0; margin: 6px 0 10px; border-top: 1px solid var(--border); }
.rules .r-row { display: grid; grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr)); column-gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--border); margin: 0; font-size: var(--fs-md); }
.rules .r-cell { min-width: 0; }
.rules .ed { display: block; padding: 2px 6px; margin: -2px -6px; border-radius: var(--radius-sm); overflow-wrap: anywhere; white-space: pre-wrap; cursor: text; min-width: 0; min-height: 1.5em; }
.rules .ed:hover { background: var(--stripe); }
.rules .ed:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.rules .ed.is-editing { background: transparent; outline: 2px solid var(--accent); }
.rules .ed.is-empty::before { content: attr(data-ph); color: var(--faint); }
.rules .ed code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .92em; }
.rules .is-edited::before { content: ""; position: absolute; left: -12px; top: 2px; bottom: 2px; width: 3px; border-radius: 2px; background: var(--muted); }
.rules li.is-edited::before { left: -22px; }
.rules .flash { background: var(--selected); border-radius: var(--radius-sm); }
.rules .under { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; margin-top: 4px; font-size: var(--fs-xs); color: var(--muted); }
.rules .link { background: none; border: 0; padding: 0; font-size: var(--fs-xs); color: var(--muted); text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.rules .link:hover { color: var(--fg); }
.rules .tag { display: inline-block; white-space: nowrap; margin-top: 4px; font-size: var(--fs-xs); border: 1px solid var(--border-strong); border-radius: 999px; padding: 1px 8px; color: var(--muted); }
.rules .notice, .rules .r-notice { margin: 6px 0; background: var(--notice-bg); border: 1px solid var(--notice-border); color: var(--notice-fg); border-radius: var(--radius-sm); padding: 6px 10px; font-size: var(--fs-md); }
.rules .r-notice p { margin: 0 0 6px; }
.rules .r-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.rules .gl-head, .rules .gl-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto auto; column-gap: 16px; align-items: start; }
.rules .gl-head { padding: 0 0 6px; font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; color: var(--muted); }
.rules .gl-row { position: relative; padding: 8px 0; border-top: 1px solid var(--border); font-size: var(--fs-base); }
.rules .gl-row .under { grid-column: 1 / -1; }
.rules .chk { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.rules .chk input { accent-color: var(--accent); width: 16px; height: 16px; margin: 0; cursor: pointer; }
.rules .gl-add { margin-top: 10px; }
.rules .bcard { position: relative; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px; margin-bottom: 10px; font-size: var(--fs-base); }
.rules .bcard h4 { margin: 0 0 8px; font-size: var(--fs-base); }
.rules .bnone { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.rules .bnone p { margin: 0; }
.rules .muted { color: var(--muted); }
.rules .empty { font-style: normal; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.rules .empty-t { margin: 0 0 16px; font-size: var(--fs-doc-body, 16px); }
.rules .empty h4 { margin: 0 0 6px; font-size: var(--fs-md); font-weight: 600; color: var(--muted); }
.rules .sugg { margin: 0 0 18px; color: var(--muted); }
.rules .sugg div { display: grid; grid-template-columns: 120px minmax(0, 1fr); column-gap: 16px; padding: 4px 0; }
.rules .sugg dt { font-weight: 600; font-size: var(--fs-sm); }
.rules .sugg dd { margin: 0; overflow-wrap: anywhere; }
.rules .r-skel-line { height: 12px; margin: 12px 0; border-radius: var(--radius-sm); background: var(--stripe); }
.rules .r-bar { position: sticky; bottom: 0; z-index: 20; min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 6px 16px; padding: 6px 24px; background: var(--surface); border-top: 1px solid var(--border-strong); }
.rules .bar-l, .rules .bar-c { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: var(--fs-sm); }
.rules .bar-c { flex: 1 1 auto; justify-content: center; }
.rules .bar-r { font-size: var(--fs-sm); color: var(--muted); text-align: right; display: flex; align-items: center; gap: 12px; }
.rules .bar-r a { color: var(--muted); text-decoration: none; white-space: nowrap; }
.rules .bar-r a:hover, .rules .bar-r a:focus-visible { color: var(--fg); text-decoration: underline; }
.rules .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); flex: none; }
.rules .dot.muted { background: var(--faint); }
.rules .dot.warn { background: var(--warn); }
.rules kbd { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: var(--fs-xs); color: var(--muted); margin-left: 6px; }
.rules .drawer { position: fixed; left: 0; right: 0; bottom: 0; height: 50vh; z-index: 30; display: flex; flex-direction: column; background: var(--surface); border-top: 1px solid var(--border-strong); box-shadow: 0 -8px 24px var(--border); transform: translateY(100%); visibility: hidden; transition: transform .25s, visibility 0s .25s; }
.rules .drawer.open { transform: none; visibility: visible; transition: transform .25s; }
.rules .dr-h { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 24px 0; }
.rules .dr-h h2 { margin: 0; font-size: var(--fs-lg); }
.rules .tl { flex: 1; display: flex; gap: 16px; overflow: auto; padding: 14px 24px 20px; align-items: flex-start; }
.rules .vcard { flex: 0 0 280px; min-width: 0; border: 1px solid var(--border-strong); border-radius: var(--radius); padding: 14px; background: var(--panel); }
.rules .vcard.is-cur { border-color: var(--fg); }
.rules .vc-top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 8px; font-size: var(--fs-sm); color: var(--muted); }
.rules .vc-top strong { color: var(--fg); font-size: var(--fs-base); }
.rules .vc-s { margin-top: 4px; font-size: var(--fs-md); font-weight: 600; }
.rules .vc-t { margin-top: 6px; font-size: var(--fs-xs); font-weight: 700; }
.rules .vc-a { margin-top: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
.rules .detail { margin-top: 10px; background: var(--panel); border-radius: var(--radius-sm); padding: 8px 10px; font-size: var(--fs-sm); overflow-wrap: anywhere; white-space: pre-wrap; }
.rules .detail .was { display: block; color: var(--muted); text-decoration: line-through; }
.rules .detail .now { display: block; color: var(--fg); }
.r-modal .cpw-modal { background: var(--surface); }
.r-modal .r-dlg-t { margin: 0 0 10px; font-size: var(--fs-xl); }
.r-modal .r-dlg-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.rules .toast-stack .toast { background: var(--surface); }
.rules [hidden] { display: none; }
@media (max-width: 1280px) { .rules { --pad: 32px; } }
@media (max-width: 1100px) {
  .rules .shell { grid-template-columns: 200px minmax(0, 1fr); }
  .rules { --pad: 28px; }
  .rules .stage { padding: 20px 16px; }
}
"""

_SCRIPT_END = re.compile(r"</(script)", re.I)
_STYLE_END = re.compile(r"</(style)", re.I)


def _read(path: Path, what: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{what} is missing at {path}: the rules page inlines it")
    return path.read_text(encoding="utf-8")


def _script(js: str) -> str:
    body = _SCRIPT_END.sub(r"<\\/\1", js)
    return "<script>\n" + body + ("" if body.endswith("\n") else "\n") + "</script>"


def _config() -> str:
    cfg = {
        "locales": [{"code": code, "name": S.lang_name(code), "flag": flag, "none": code in NO_RULES}
                    for code, _endonym, _dir, flag in S.LOCALES],
        "pages": [{"slug": key, "name": t("page." + key)} for key in S.PAGE_KEYS],
        "checked": CHECKED,
        "suggested": {k: [{"label": a, "value": b} for a, b in rows] for k, rows in SUGGESTED.items()},
        "briefSections": list(BRIEF_SECTIONS),
    }
    return json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _dom() -> str:
    """The server-rendered frame; the runtime fills the sheets, the rail and the bar."""
    e = lambda key, **kw: escape(t(key, **kw))  # noqa: E731
    return (
        '<main id="rules-app" class="rules" data-state="loading">\n'
        '  <header class="r-top">\n'
        f'    <h1 class="crumb"><span>{e("rules.title")}</span><span class="sep" aria-hidden="true">/</span>'
        '<span class="cw"><button id="rulesLang" class="crumb-b" type="button" aria-haspopup="true" '
        f'aria-expanded="false" aria-label="{e("rules.language")}"></button></span></h1>\n'
        '    <div class="acts">\n'
        f'      <a class="desk-btn" href="/admin/localization/document/">{e("rules.desk")}</a>\n'
        f'      <button id="rulesHistory" class="desk-btn" type="button" aria-expanded="false" '
        f'aria-controls="rulesDrawer">{e("rules.history")}</button>\n'
        f'      <button id="rulesUse" class="desk-btn is-primary" type="button" disabled>{e("rules.use")}</button>\n'
        '    </div>\n'
        '  </header>\n'
        '  <div class="shell">\n'
        f'    <nav class="rail" aria-label="{e("rules.outline")}"><h2 class="ol-h">{e("rules.outline")}</h2>'
        '<div id="rulesOutline"></div></nav>\n'
        '    <div class="stage">\n'
        '      <div class="sheets">\n'
        f'        <section id="sheet-shared" class="sheet" aria-label="{e("rules.shared")}">'
        f'<h2 class="sheet-head">{e("rules.shared.all")}</h2></section>\n'
        '        <section id="sheet-lang" class="sheet" aria-labelledby="sheet-lang-h">'
        '<h2 id="sheet-lang-h" class="sheet-head"></h2></section>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '  <div class="r-bar">\n'
        '    <div class="bar-l"><span id="rulesDot" class="dot" aria-hidden="true"></span>'
        '<span id="rulesSave" aria-live="polite"></span></div>\n'
        '    <div class="bar-c">'
        f'<button id="rulesUndo" class="desk-btn" type="button" disabled>{e("doc.undo")}<kbd></kbd></button>'
        f'<button id="rulesRedo" class="desk-btn" type="button" disabled>{e("doc.redo")}<kbd></kbd></button></div>\n'
        '    <div class="bar-r"><span id="rulesNote"></span>'
        f'<a href="{escape(DESK_CHANGELOG_URL)}" target="_blank" rel="noopener">'
        f'{e("doc.version", version=DESK_VERSION)}</a></div>\n'
        '  </div>\n'
        f'  <section id="rulesDrawer" class="drawer" role="dialog" aria-label="{e("rules.history.title")}">\n'
        f'    <div class="dr-h"><h2 tabindex="-1">{e("rules.history.title")}</h2>'
        f'<button id="rulesHistoryClose" class="desk-btn" type="button">{e("rules.close")}</button></div>\n'
        f'    <div id="rulesTimeline" class="tl" role="group" aria-label="{e("rules.history.title")}"></div>\n'
        '  </section>\n'
        '  <div id="rulesToasts" class="toast-stack" aria-live="polite"></div>\n'
        '</main>\n'
    )


def render_page() -> str:
    page_js = _read(PAGE_JS, "rules_page.js")
    md_js = _read(MD_JS, "rules_md.js")
    head = S._head(t("rules.meta.title"), t("rules.meta.description"))
    assert head[-2:] == ["</head>", "<body>"], "desk_shared._head changed its ending"
    style = "<style>\n" + _STYLE_END.sub(r"<\\/\1", RULES_CSS) + "</style>"
    globals_js = (
        "var SAVE_OFF = " + ("true" if S.SAVE_OFF else "false") + ";\n"
        "var COPY = " + js_table() + ";\n"
        + JS_HELPERS + S._PROXY_JS + S._TIP_JS
    )
    parts = head[:-2] + [style] + head[-2:]
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    parts.append(_dom() + "  </div>")
    parts.append(render_admin_close())
    parts.append(_script(globals_js))
    parts.append('<script type="application/json" id="rules-config">' + _config() + "</script>")
    parts.append(_script(md_js))
    parts.append(_script(page_js))
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def main() -> int:
    try:
        page = render_page()
    except FileNotFoundError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "index.html"
    target.write_text(page, encoding="utf-8")
    print(f"  wrote {target} ({target.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
