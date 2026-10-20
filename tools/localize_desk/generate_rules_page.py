"""The rules page of the localization desk: /admin/localization/rules/ (CEL-046, read-only since CEL-080,
option A of CEL-088 since CEL-089: a summary per language, the client's sections with "Done by" per request).

The client picks a language and reads the translation rules the engine gives Gemini for it: the
shared rules, that language's own rules and its glossary, each its own versioned scope in the Worker's
D1 store. Version 1 only SHOWS them: nothing on the page edits, saves or publishes, and the page-level
briefs are not shown. One column of readable text under language tabs, no white or near-white
backgrounds (ruling 2026-10-20 00:29). The editor this page used to be is in git history (CEL-046,
spec runtime/out/loc2/rules-editor-spec.md in the monorepo).

This file writes ONE page and no data: the rule bodies are the client's documents and this
repository is public, so the page reads them from the Worker at run time, behind sign-in. The page
inlines only rules_done_by.json (how the tool carries each line out, keyed by a hash of the line: no
client words; built in the monorepo by runtime/out/loc2/CEL-089/build_done_by.py) and rules_quality.json
(our own quality checks per language, "Our quality checks": COPY keys and the numbers they show, built from
the engine's draft.py, gates.py and rules/ by runtime/out/loc2/CEL-099/build_quality.py).
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
DONE_BY = HERE / "rules_done_by.json"
QUALITY = HERE / "rules_quality.json"

# Page CSS: tokens only (no hex, no rgba, no !important). One readable column on the page's own cream.
RULES_CSS = """
.rules { --muted: color-mix(in srgb, var(--fg) 76%, transparent); --faint: color-mix(in srgb, var(--fg) 74%, transparent); }
/* WCAG AA on this page (review CEL-046 fix 4): the dashboard's --muted (--fg at 65%) is 3.93:1 on the cream,
   --faint (45%) 2.40:1. Here they are --fg at 76% (5.30) and 74% (5.01). */
.rules .r-top { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 12px 24px; flex-wrap: wrap; padding: 12px 24px; }
.rules .r-title { margin: 0; font-size: var(--fs-xl); font-weight: 500; }
.rules .r-tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 24px; border-bottom: 1px solid var(--border); }
.rules .r-tab { margin: 0 0 -1px; padding: 10px 14px; border: 0; border-bottom: 2px solid transparent; background: none; font: inherit; font-size: var(--fs-base); color: var(--muted); cursor: pointer; }
.rules .r-tab:hover { background: var(--stripe); color: var(--fg); }
.rules .r-tab[aria-selected="true"] { color: var(--fg); font-weight: 500; border-bottom-color: var(--fg); }
.rules .r-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.rules .r-flag { margin-inline-end: 6px; }
.rules .r-main { max-width: 1360px; padding: 20px 24px 48px; }
.rules .r-sum { display: grid; grid-template-columns: 1.4fr repeat(3, 1fr); gap: 12px; margin: 0 0 8px; }
.rules .r-lead { display: flex; flex-direction: column; justify-content: center; }
.rules .r-big { font-size: 28px; font-weight: 500; letter-spacing: -0.012em; line-height: 1.2; }
.rules .r-sub, .rules .r-intro { margin: 4px 0 0; font-size: var(--fs-md); color: var(--muted); }
.rules .r-stat { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 12px 14px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--panel); font: inherit; color: var(--fg); text-align: start; cursor: pointer; }
.rules .r-stat:hover { background: var(--stripe); }
.rules .r-stat[aria-pressed="true"] { border-color: var(--fg); background: var(--selected); }
.rules .r-stat:focus-visible, .rules .r-clear:focus-visible, .rules .r-rail-a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.rules .r-num { font-size: 24px; font-weight: 500; line-height: 1.2; }
.rules .r-cap { font-size: var(--fs-sm); color: var(--muted); }
.rules .r-filterline { margin: 0 0 16px; font-size: var(--fs-sm); color: var(--muted); }
.rules .r-clear { padding: 0; border: 0; background: none; font: inherit; color: var(--accent-strong); cursor: pointer; }
.rules .r-layout { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 32px; }
/* the dashboard's sticky shell header is 59 px tall: the list and the jump targets sit below it */
.rules .r-rail { position: sticky; top: 76px; align-self: start; display: flex; flex-direction: column; gap: 1px; padding-top: 8px; }
.rules .r-rail-a { display: grid; grid-template-columns: 34px 1fr auto; gap: 6px; align-items: baseline; padding: 6px 8px; border-radius: var(--radius-sm); font-size: var(--fs-md); color: var(--fg); text-decoration: none; }
.rules .r-rail-a:hover { background: var(--stripe); }
.rules .r-rail-n { font-size: var(--fs-xs); color: var(--muted); }
.rules .r-no { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: var(--fs-sm); color: var(--muted); }
.rules .r-doc { min-width: 0; }
.rules .r-sec-head { display: flex; align-items: baseline; gap: 10px; margin: 0 0 4px; padding-bottom: 8px; border-bottom: 1px solid var(--border-strong); }
.rules .r-sec-head .r-sec-h { margin: 0; padding: 0; border: 0; }
.rules .r-sec { scroll-margin-top: 76px; }
.rules .r-sub { margin: 16px 0 4px; font-size: var(--fs-base); font-weight: 500; }
.rules .r-ctx { margin: 12px 0 0; font-size: var(--fs-md); color: var(--muted); }
.rules .r-req, .rules .r-qc { display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 4px 24px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.rules .r-words { font-size: 15px; line-height: 1.55; overflow-wrap: anywhere; }
.rules .r-cell { display: inline-block; margin: 0 18px 2px 0; }
.rules .r-cell-h { display: block; font-size: var(--fs-xs); color: var(--muted); }
.rules .r-side { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.rules .r-how { font-size: var(--fs-sm); color: var(--muted); }
.rules .r-by { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px; border-radius: 999px; font-size: var(--fs-sm); font-weight: 500; white-space: nowrap; }
.rules .r-mk { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid currentColor; flex: none; }
.rules .r-by.check { color: var(--ok); background: color-mix(in srgb, var(--ok) 14%, transparent); }
.rules .r-by.check .r-mk { background: currentColor; }
.rules .r-by.prompt { color: var(--accent-strong); background: color-mix(in srgb, var(--accent-strong) 10%, transparent); }
.rules .r-by.prompt .r-mk { background: linear-gradient(90deg, currentColor 50%, transparent 50%); }
.rules .r-by.none { color: var(--notice-fg); background: color-mix(in srgb, var(--warn) 16%, transparent); }
.rules .r-by.warn { color: var(--notice-fg); border: 1px dashed var(--notice-fg); }
.rules .r-by.warn .r-mk { border-style: dashed; }
.rules .r-pairs { display: grid; gap: 16px; padding-top: 12px; }
.rules .r-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rules .r-pair-k { grid-column: 1 / -1; font-size: var(--fs-md); font-weight: 500; }
.rules .r-good, .rules .r-bad { padding: 12px 14px; border-radius: 8px; font-size: var(--fs-base); line-height: 1.6; }
.rules .r-good { background: color-mix(in srgb, var(--ok) 10%, transparent); }
.rules .r-bad { background: color-mix(in srgb, var(--warn) 12%, transparent); }
.rules .r-lbl { display: block; margin-bottom: 4px; font-size: var(--fs-xs); font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
.rules .r-good .r-lbl { color: var(--ok); }
.rules .r-bad .r-lbl { color: var(--notice-fg); }
.rules .r-why { grid-column: 2; font-size: var(--fs-sm); color: var(--muted); }
.rules .r-drift { padding: 10px 14px; border-left: 3px solid var(--notice-fg); border-radius: 0 8px 8px 0; background: var(--stripe); font-size: var(--fs-md); }
.rules .r-briefs { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; padding-top: 12px; }
.rules .r-sec { margin: 0 0 32px; }
.rules .r-sec-h { margin: 0 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); font-size: var(--fs-lg); font-weight: 500; }
.rules .r-text { font-size: var(--fs-doc-body, 16px); line-height: 1.65; overflow-wrap: anywhere; }
.rules .r-h { margin: 22px 0 6px; font-size: var(--fs-base); font-weight: 500; line-height: 1.4; }
.rules .r-h:first-child { margin-top: 0; }
.rules .r-p { margin: 0 0 10px; white-space: pre-wrap; }
.rules .r-items { margin: 0 0 12px; padding-left: 22px; }
.rules .r-item { margin: 0 0 6px; }
.rules .r-quote { margin: 0 0 10px; padding-left: 12px; border-left: 2px solid var(--border-strong); color: var(--muted); }
.rules .r-hr { border: 0; border-top: 1px solid var(--border); margin: 16px 0; }
.rules .r-text code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .92em; }
.rules .r-table { width: 100%; margin: 4px 0 14px; border-collapse: collapse; font-size: var(--fs-base); line-height: 1.5; }
.rules .r-table th, .rules .r-table td { padding: 8px 12px 8px 0; border-bottom: 1px solid var(--border); text-align: start; vertical-align: top; overflow-wrap: anywhere; }
.rules .r-table th { font-size: var(--fs-sm); font-weight: 500; color: var(--muted); }
.rules .r-empty { margin: 0; color: var(--muted); }
.rules .r-brief { padding: 0 16px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--panel); }
.rules .r-brief-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 14px 0; font-size: var(--fs-base); font-weight: 500; cursor: pointer; }
.rules .r-brief-h:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.rules .r-brief > .r-text { padding: 0 0 14px; }
.rules .r-skel-line { height: 12px; margin: 12px 0; border-radius: var(--radius-sm); background: var(--stripe); }
.rules .r-notice { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; padding: 8px 12px; border: 1px solid var(--notice-border); border-radius: var(--radius-sm); background: var(--notice-bg); color: var(--notice-fg); font-size: var(--fs-base); }
.rules .r-notice p { margin: 0; }
.rules .r-foot { padding: 0 24px 32px; font-size: var(--fs-sm); }
.rules .r-foot a { color: var(--muted); text-decoration: none; white-space: nowrap; }
.rules .r-foot a:hover, .rules .r-foot a:focus-visible { color: var(--fg); text-decoration: underline; }
.rules [hidden] { display: none; }
@media (max-width: 1100px) {
  .rules .r-main { padding: 20px 16px 40px; }
  .rules .r-layout { grid-template-columns: 200px minmax(0, 1fr); gap: 24px; }
  .rules .r-tabs, .rules .r-top { padding-inline: 16px; }
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
    cfg = {"locales": [{"code": code, "name": S.lang_name(code), "flag": flag}
                       for code, _endonym, _dir, flag in S.LOCALES],
           "pages": list(S.PAGE_KEYS),
           "doneBy": json.loads(_read(DONE_BY, "rules_done_by.json")),
           "quality": json.loads(_read(QUALITY, "rules_quality.json"))}
    return json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _dom() -> str:
    """The server-rendered frame; the runtime fills the panel. The language tabs are real buttons in the frame."""
    e = lambda key, **kw: escape(t(key, **kw))  # noqa: E731
    tabs = "".join(
        f'<button id="rulesTab-{code}" class="r-tab" type="button" role="tab" data-lang="{code}" '
        f'aria-selected="false" aria-controls="rulesPanel" tabindex="-1">'
        f'<span class="r-flag" aria-hidden="true">{escape(flag)}</span>{escape(S.lang_name(code))}</button>'
        for code, _endonym, _dir, flag in S.LOCALES
    )
    return (
        '<main id="rules-app" class="rules" data-state="loading">\n'
        '  <header class="r-top">\n'
        f'    <h1 class="r-title">{e("rules.title")}</h1>\n'
        f'    <a id="rules-desk" class="desk-btn" href="/admin/localization/document/">{e("rules.desk")}</a>\n'
        '  </header>\n'
        f'  <div class="r-tabs" role="tablist" aria-label="{e("rules.language")}">{tabs}</div>\n'
        '  <div id="rulesPanel" class="r-main" role="tabpanel" aria-live="polite"></div>\n'
        f'  <footer class="r-foot"><a href="{escape(DESK_CHANGELOG_URL)}" target="_blank" rel="noopener">'
        f'{e("doc.version", version=DESK_VERSION)}</a></footer>\n'
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
