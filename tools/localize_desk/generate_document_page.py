#!/usr/bin/env python3
"""Build the document page (desk v2, CEL-026) under /admin/localization/document/.

    cd tools && python3 -m localize_desk.generate_document_page

This page is one page of the website read as a document: every text in the order the page
shows it, English on one sheet and the translation on the next, edited in place and saved by
itself; an outline of the page beside the sheets, a status bar below them (design B, chosen by
the operator 2026-10-19). The desk's shared pieces (`LOCALES`, `PAGE_KEYS`, `_head`, the proxy
and tooltip scripts, the root redirect) come from `desk_shared.py`, its words from COPY.md.

What it writes (under `OUT_DIR`, and one file beside it):

    index.html           the page: server-rendered shell + the runtime, inlined
    data/pages.json      per page: key, path, how many blocks, how many left out, which can be edited
    data/<page>.json     one document: its blocks in page order, English, lock, translations
    ../index.html        /admin/localization/: the redirect every dashboard Localization tab opens

The site's menu and footer texts (the units files' per-unit `chrome` flag, written by the engine's
manifest: also on 30 pages or more, and outside every heading) are not part of the page a reviewer
reads and are left out; each file says how many (`chrome`). Every other text is shown and editable.

The page reads those files once it is open, so a reviewer opens a page in the language they
work in without downloading the other seven. The runtime (`document_desk.js`) is readable
source beside this module and is inlined into the page; it is never served as its own file.

The contract between this generator, the runtime and the tests is
`runtime/out/loc2/CEL-026/contract.md` in the working repository (section 7 is design B).
Every word on the page is a COPY.md line (`doc.*`, then the shared `lang.*` and `page.*`); this
module types no sentence.
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

from dashboard import render_admin_close, render_admin_open  # noqa: E402

HERE = Path(__file__).resolve().parent

# Where the page reads from and writes to. Module-level so a test can point them elsewhere.
UNITS_DIR = S.UNITS_DIR
OUT_DIR = S.OUT_ROOT / "document"
DOC_JS = HERE / "document_desk.js"
EXPORT_JS = HERE / "document_export.js"       # Export + Re-translate (CEL-027), inlined after DOC_JS
EXPORT_CSS = HERE / "document_export.css"
RICH_JS = HERE / "spike" / "rich_field.js"
RICH_CSS = HERE / "spike" / "rich_field.css"

# The data files' address on the site, as the runtime asks for them.
DATA_URL = "/admin/localization/document/data/"
VERSION = "desk-v2"

# The site's menu and footer are not part of the page a reviewer reads, so they are left out of
# the data altogether (contract section 10). The engine decides which texts those are and writes the
# answer into each unit of the units files as `chrome: true` (monorepo tools/localize/gates.py
# `is_chrome`, CEL-039 / Manager ruling 2026-10-19 21:18); this generator reads that flag and holds no
# copy of the rule. A unit is chrome when ALL of these hold:
#   1. it is also on a page outside the four (gate 12);
#   2. it is used on 30 paths or more (gates.CHROME_MIN_PAGES);
#   3. it stands outside every heading (its `section` is empty: the menu before the first heading,
#      the footer after the last) and its block is not the page's title or description.
# Page count alone is not enough: body texts sit on 30 pages too (FAQ answers on 35, course and
# housing names on 78). Every other text is shown and editable; one that is also on other pages
# says so under itself (`out`, `outEg`).

# The localization desk's version (semver), the ONE source of the number the document page shows in its
# status bar. A release step bumps it with its CHANGELOG entry and the tag `desk-v<version>` (decisions
# 2026-10-19 23:44, CEL-042). DESK_CHANGELOG_URL is where the link goes: the desk's section of the CHANGELOG in the PUBLIC CEL repo
# (the monorepo is private: the client could not open its CHANGELOG; ruling 2026-10-19 23:58).
DESK_VERSION = "2.3.0"
DESK_CHANGELOG_URL = "https://github.com/cagdasunal/CEL/blob/main/CHANGELOG.md"


# ── The data ────────────────────────────────────────────────────────────────

def _outside(unit: dict, in_scope: set[str]) -> list[str]:
    """The pages outside the four that carry the same English, sorted (gate 12's `outside_scope`).

    Weglot keeps one translation per English string, so a wording saved here is also the wording
    on those pages: the page says so under the text. Nothing is locked for it, nor for the other
    gates' reasons (a blog summary, a text of only links, numbers and symbols): since the operator's
    ruling of 2026-10-19 21:00 every shown text is editable, and `lock` stays in the data, always
    empty, for the day a gate flags a row as broken."""
    return sorted(p for p in unit.get("pages") or [] if p not in in_scope)


def _in_order(doc: dict) -> list[tuple[dict, str]]:
    """(unit, block) for every unit of one page file, in the order the page shows them.

    The file's `order` list is the document order (`block` = the HTML element). A file
    without one falls back to the units' `ord`, then their place in the file, and the block
    is the unit's `tag` (default `p`). A unit the list forgot is kept, after the listed ones,
    rather than dropped; a listed id with no unit, or listed twice, is passed over.
    """
    units = doc.get("units") or []
    by_id = {u["unit_id"]: u for u in units}
    out: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for entry in doc.get("order") or []:
        unit = by_id.get(entry.get("unit_id"))
        if unit is None or unit["unit_id"] in seen:
            continue
        seen.add(unit["unit_id"])
        out.append((unit, entry.get("block") or unit.get("tag") or "p"))
    rest = [(i, u) for i, u in enumerate(units) if u["unit_id"] not in seen]
    rest.sort(key=lambda iu: (iu[1].get("ord", 0), iu[0]))
    out += [(u, u.get("tag") or "p") for _i, u in rest]
    return out


def load_documents(units_dir: Path | str | None = None) -> dict[str, dict]:
    """page key -> its document, for the pages of `PAGE_KEYS` found in `units_dir`.

    A document is `{"page", "path", "built", "chrome", "blocks": [...]}` and is what
    `data/<page>.json` holds; `chrome` is how many menu / footer texts (the unit's own `chrome` flag,
    written by the engine) were left out of `blocks`. Keys come out in `PAGE_KEYS` order, whatever
    order the files are read in.
    """
    units_dir = Path(units_dir) if units_dir is not None else UNITS_DIR
    raw: dict[str, dict] = {}
    for path in sorted(units_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("page") in S.PAGE_KEYS:
            raw[doc["page"]] = doc
    keys = [k for k in S.PAGE_KEYS if k in raw]
    path_of = {k: raw[k]["path"] for k in keys}
    in_scope = set(path_of.values())

    out: dict[str, dict] = {}
    for key in keys:
        doc = raw[key]
        blocks = []
        chrome = 0
        for unit, block in _in_order(doc):
            outside = _outside(unit, in_scope)
            pages = unit.get("pages") or []
            if unit.get("chrome"):                       # the engine's answer (gates.is_chrome), not ours
                chrome += 1
                continue
            also = [k for k in keys if k != key and path_of[k] in pages]
            words = {}
            for code, *_ in S.LOCALES:
                cur = (unit.get("current") or {}).get(code) or {}
                if cur.get("translated") and cur.get("word_to"):
                    words[code] = cur["word_to"]
            item = {"id": unit["unit_id"], "b": block, "r": unit.get("role") or "body",
                    "sec": unit.get("section") or "", "en": unit.get("word_from") or "",
                    "lock": ""}
            if also:
                item["also"] = also
            if outside:
                item["out"] = len(outside)
                item["outEg"] = outside[0]
                item["outAll"] = outside                 # the popover lists them (CEL-072); outEg stays for the sentence
            item["w"] = words
            blocks.append(item)
        out[key] = {"page": key, "path": path_of[key], "built": doc.get("built_at") or "",
                    "chrome": chrome, "blocks": blocks}
    return out


def pages_payload(docs: dict[str, dict]) -> dict:
    """`data/pages.json`: what the grid and the page switcher need before a page is opened.

    `count` is every block WRITTEN for the page (the menu and footer texts are not: `chrome`
    says how many were left out); `ids` the ones that can be edited, which is all of them unless
    a block carries a `lock` (the runtime counts a language's progress against those)."""
    return {
        "built": max((d["built"] for d in docs.values()), default=""),
        "pages": [{"key": key, "path": d["path"], "count": len(d["blocks"]), "chrome": d["chrome"],
                   "ids": [b["id"] for b in d["blocks"] if not b["lock"]]}
                  for key, d in docs.items()],
    }


def _dump(obj) -> str:
    """Compact JSON, as committed: git stores this on every regeneration."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ── The page ────────────────────────────────────────────────────────────────

# The document view's own colours and two type sizes (CEL-070, from the designer's spec CEL-068 doc-spec.md). The
# only place the page's colours are written down: DOC_CSS below holds no hex and uses these by name. No white or
# near-white anywhere (ruling 2026-10-20 00:29): the sheets are the page cream on a recessed tray one step deeper.
# Every text pair is 4.5:1 or more and every mark 3:1 or more (tests/test_generate_document_page.py reads this block).
# `--fs-doc-h1` / `--fs-doc-h2` are the dashboard's tokens, narrowed to this page (28 / 21 px; the docs pages keep 30 / 22).
DOC_TOKENS = """\
.doc {
  --doc-tray: #E7DEC7;
  --doc-sheet: #F1EAD8;
  --doc-sheet-hover: #ECE4CF;
  --doc-weglot-bg: #EAE2CC;
  --doc-ink: #2B2722;
  --doc-ink-src: #47423A;
  --doc-muted: #645D51;
  --doc-placeholder: #6A6255;
  --doc-edited: #A85F0A;
  --doc-edited-ink: #8A4D07;
  --doc-flag: #A3361F;
  --doc-flag-bg: #EDDCC6;
  --fs-doc-h1: 28px;
  --fs-doc-h2: 21px;
}
"""

# The page's own rules (contract section 7.4, design B). Colours are the dashboard's tokens and
# nothing else; indigo (--accent) is the focus ring, the outline of the text being edited and the
# checkbox. The one filled button is the dashboard's own .desk-btn.is-primary. No !important, no
# hex, no rgba: tests/test_generate_document_page.py reads this string and holds it to that.
#
# How a row is drawn. A block is one grid row across the sheets. The English sheet and the
# translation sheet are two pseudo-elements of the row (`::before`, `::after`) that fill its
# whole height, so a note or a conflict line under the translation stays on the paper; the
# texts sit on them with margins. A third sheet (Weglot) is the Weglot cell itself.
DOC_CSS = """\
/* The document page (desk v2, design B) in the Option B shell (CEL-069, CEL-068 shell-spec.md): a page tree on
   the left, a path row and language tabs over the sheets, a status bar below them. */
html { scroll-padding-top: 115px; scroll-padding-bottom: 64px; }   /* + a block's 64 px margin: it lands just under the sticky rows (bar 40, path 52, tabs 38, heads) */
.dashboard-shell:has(> .doc) { padding: 0; }
.doc { --doc-topbar: 40px; padding: 0; }
.doc-app { display: grid; grid-template-columns: var(--tree-w) minmax(0, 1fr); align-items: start; }
.doc-main { min-width: 0; }
.doc-sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

/* A status mark: Option B's shapes, shell-spec §1 colours (3:1 on every shell background) */
.doc-st { display: inline-block; flex: none; width: 8px; height: 8px; border: 1.5px solid var(--doc-muted); border-radius: 50%; }
.doc-st[data-s="queued"] { border-color: var(--doc-progress); border-style: dashed; }
.doc-st[data-s="translating"] { border-color: var(--doc-progress); background: var(--doc-progress); }
.doc-st[data-s="drafted"] { border-color: var(--accent); background: var(--accent); }
.doc-st[data-s="edited"] { border-color: var(--accent); background-image: linear-gradient(var(--accent), var(--accent)); background-size: 50% 100%; background-repeat: no-repeat; }
.doc-st[data-s="exported"] { border-color: var(--ok); background: var(--ok); }
.doc-st[data-s="failed"] { border-color: var(--err); }
.doc-st[data-s="unknown"] { border-style: dotted; }

/* The page tree (left): filter, folders, pages, the open page's sections */
.doc-tree { position: sticky; top: var(--doc-topbar); display: flex; flex-direction: column; height: calc(100vh - var(--doc-topbar) - 44px); border-inline-end: 1px solid var(--border); background: var(--tree-bg); }
.doc-tree-filter { display: flex; align-items: center; gap: 6px; height: 32px; margin: 12px 12px 6px; padding: 0 8px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--doc-sheet); }
.doc-tree-filter:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-tree-filter input { flex: 1; min-width: 0; border: 0; background: none; color: var(--doc-ink); font: inherit; font-size: var(--fs-md); outline: none; }
.doc-tree-filter input::placeholder { color: var(--doc-placeholder); opacity: 1; }
.doc-kbd-hint { padding: 0 5px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--stage); color: var(--doc-muted); font-family: var(--mono); font-size: var(--fs-xs); line-height: 16px; }
.doc-tree-list { flex: 1; overflow-y: auto; padding: 4px 8px 12px; }
.doc-tree-fold { display: flex; align-items: center; gap: 6px; width: 100%; padding: 8px 6px 4px; border: 0; background: none; color: var(--doc-muted); font-family: var(--mono); font-size: var(--fs-sm); text-align: start; cursor: pointer; }
.doc-tree-fold svg { width: 11px; height: 11px; transition: transform .12s; }
.doc-tree-fold[aria-expanded="false"] svg { transform: rotate(-90deg); }
.doc-tree-n { margin-inline-start: auto; font-family: inherit; font-size: var(--fs-xs); }
.doc-tree-page { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 2px 8px; width: 100%; padding: 6px 8px 6px 23px; border: 0; border-radius: var(--radius-sm); background: none; color: var(--doc-ink); font: inherit; text-align: start; cursor: pointer; }
.doc-tree-page:hover { background: var(--doc-sheet-hover); }
.doc-tree-page.is-kb, .doc-tree-page[aria-current="page"] { background: var(--doc-sheet); }
.doc-tree-slug { overflow: hidden; font-family: var(--mono); font-size: var(--fs-md); white-space: nowrap; text-overflow: ellipsis; }
.doc-tree-page[aria-current="page"] .doc-tree-slug { color: var(--accent-strong); }
.doc-tree-name { grid-column: 1; overflow: hidden; color: var(--doc-muted); font-size: var(--fs-sm); white-space: nowrap; text-overflow: ellipsis; }
.doc-tree-page .doc-st { grid-row: 1 / span 2; grid-column: 2; }
.doc-tree-page:focus-visible, .doc-tree-fold:focus-visible, .doc-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-tree-none { margin: 0; padding: 12px 8px; color: var(--doc-muted); font-size: var(--fs-md); }

/* The open page's sections, nested under its row in the tree (today's outline, moved in) */
.doc-outline { margin: 2px 0 6px 23px; padding-inline-start: 10px; border-inline-start: 1px solid var(--border-strong); }
.doc-outline-list { margin: 0; padding: 0; list-style: none; }
.doc-outline-item { display: block; width: 100%; padding: 4px 8px; border: 0; border-radius: var(--radius-sm); background: none; color: var(--doc-muted); font: inherit; text-align: start; cursor: pointer; }
.doc-outline-item:hover { background: var(--doc-sheet-hover); color: var(--doc-ink); }
.doc-outline-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.doc-outline-item[aria-current="true"] { background: var(--doc-sheet-hover); color: var(--doc-ink); }
.doc-outline-name { display: block; font-size: var(--fs-sm); line-height: 1.35; }
.doc-outline-count { display: block; margin-top: 1px; font-size: var(--fs-xs); color: var(--doc-muted); }

/* The path row: the page's path and name, then its actions. It and the tabs stay under the top bar (z-index 30):
   the bar's menus drop over them (CEL-069 #2). */
.doc-bar { position: sticky; top: var(--doc-topbar); z-index: 12; display: flex; align-items: center; gap: 12px; height: var(--ctx-h); padding: 0 24px; background: var(--bg); }
.doc-title { display: flex; align-items: baseline; gap: 10px; min-width: 0; margin: 0; font-size: var(--fs-path); font-weight: 400; }
.doc-path { overflow: hidden; font-family: var(--mono); white-space: nowrap; text-overflow: ellipsis; }
.doc-path-dir { color: var(--doc-muted); }
.doc-path-leaf { color: var(--doc-ink); }
.doc-path-name { color: var(--doc-muted); font-size: var(--fs-md); white-space: nowrap; }
.doc-actions { display: flex; flex: none; align-items: center; gap: 8px; margin-inline-start: auto; }
.doc-switch { display: inline-flex; align-items: center; gap: 6px; color: var(--doc-ink); font-size: var(--fs-md); white-space: nowrap; cursor: pointer; }
.doc-switch input { appearance: none; position: relative; width: 28px; height: 16px; margin: 0; border: 1px solid var(--border-strong); border-radius: 999px; background: var(--doc-tray); cursor: pointer; }
.doc-switch input::after { content: ""; position: absolute; top: 1px; left: 1px; width: 12px; height: 12px; border-radius: 50%; background: var(--doc-muted); transition: transform .12s; }
.doc-switch input:checked { border-color: var(--accent); background: var(--accent); }
.doc-switch input:checked::after { background: var(--doc-sheet); transform: translateX(12px); }
.doc-switch input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* The language tabs over the sheets */
.doc-tabs { position: sticky; top: calc(var(--doc-topbar) + var(--ctx-h)); z-index: 11; display: flex; align-items: flex-end; gap: 2px; height: var(--tabs-h); padding: 0 24px; border-bottom: 1px solid var(--border); background: var(--bg); }
.doc-tab { position: relative; display: inline-flex; align-items: center; gap: 6px; height: var(--tabs-h); padding: 0 10px; border: 0; border-bottom: 2px solid var(--bg); background: none; color: var(--doc-muted); font: inherit; font-size: var(--fs-md); white-space: nowrap; cursor: pointer; }
.doc-tab:hover { color: var(--doc-ink); }
.doc-tab[aria-selected="true"] { border-bottom-color: var(--accent); color: var(--doc-ink); font-weight: 500; }
.doc-tabs-hint { align-self: center; margin-inline-start: auto; color: var(--doc-muted); font-size: var(--fs-xs); white-space: nowrap; }
@media (max-width: 1439px) {
  .doc-path-name { display: none; }
}
@media (max-width: 1279px) {
  .doc { --tree-w: 248px; }
  .doc-tabs-hint { display: none; }
}

.doc-banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px; margin: 16px 24px; padding: 12px 16px; border: 1px solid var(--notice-border); border-radius: var(--radius); background: var(--notice-bg); color: var(--notice-fg); }
.doc-banner p { flex: 1 1 320px; margin: 0; font-size: var(--fs-base); }

/* The sheets on a recessed area */
.doc-layout { display: block; }
.doc-sheets { --doc-pad: 48px; min-width: 0; min-height: 60vh; padding: 24px; border-inline-start: 1px solid var(--border); background: var(--doc-tray); }
.doc-sheets:has(.doc-blocks[data-weglot="on"]) { --doc-pad: 28px; }
.doc-sections-wrap { display: none; align-items: center; gap: 8px; max-width: 1400px; margin: 0 auto 12px; font-size: var(--fs-sm); font-weight: 600; }
.doc-sections { flex: 1 1 auto; min-width: 0; }

/* The sheet heads, and the blocks: one grid row across the sheets */
.doc-heads { position: sticky; top: calc(var(--doc-topbar) + var(--ctx-h) + var(--tabs-h)); z-index: 10; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); column-gap: 24px; max-width: 1400px; margin: 0 auto; }
.doc-head { padding: 14px var(--doc-pad) 10px; border: 1px solid var(--border); border-radius: var(--radius) var(--radius) 0 0; background: var(--doc-sheet); color: var(--doc-ink-src); font-size: var(--fs-md); font-weight: 500; letter-spacing: 0.01em; }
.doc-blocks { max-width: 1400px; margin: 0 auto; padding: 0; list-style: none; }
.doc-blocks[data-weglot="on"] { --doc-pad: 28px; }
.doc-block { --doc-mt: 16px; --doc-mb: 10px; position: relative; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: auto auto auto 1fr; column-gap: 24px; scroll-margin-top: 64px; }
.doc-blocks[data-weglot="on"] .doc-block { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.doc-block::before, .doc-block::after { content: ""; grid-row: 1 / -1; border-inline: 1px solid var(--border); background: var(--doc-sheet); }
.doc-block::before { grid-column: 1; }
.doc-block::after { grid-column: 2; }
.doc-block:last-child::before, .doc-block:last-child::after, .doc-block:last-child > .doc-weglot { border-bottom: 1px solid var(--border); border-radius: 0 0 var(--radius) var(--radius); }
.doc-block:hover::before, .doc-block:hover::after, .doc-block:hover > .doc-weglot, .doc-block:focus-within::before, .doc-block:focus-within::after, .doc-block:focus-within > .doc-weglot { background-image: linear-gradient(var(--doc-sheet-hover), var(--doc-sheet-hover)); }
.doc-block[data-flash] { background: var(--selected); }
.doc-block[data-flash]::before, .doc-block[data-flash]::after, .doc-block[data-flash] > .doc-weglot { background-image: linear-gradient(var(--selected), var(--selected)); }
.doc-en, .doc-block > .doc-tgt { margin: var(--doc-mt) var(--doc-pad) var(--doc-mb); }
.doc-en { grid-column: 1; grid-row: 1; white-space: pre-wrap; }
.doc-block > .doc-tgt { position: relative; grid-column: 2; grid-row: 1; padding: 0; border: 0; border-radius: var(--radius-sm); background: none; }
.doc-weglot { grid-column: 3; grid-row: 1 / -1; padding: var(--doc-mt) var(--doc-pad) var(--doc-mb); border-inline: 1px solid var(--border); background: var(--doc-weglot-bg); color: var(--doc-muted); cursor: default; white-space: pre-wrap; }
.doc-tag { position: absolute; z-index: 2; top: 2px; inset-inline-start: var(--doc-pad); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: var(--fs-xs); line-height: 1.3; color: var(--doc-muted); opacity: 0; pointer-events: none; transition: opacity 0.12s; }
.doc-block:hover .doc-tag, .doc-block:focus-within .doc-tag { opacity: 1; }

/* Type of text, from the block's tag: the page's own hierarchy, at the page's own sizes. Structure
   comes from the type alone; there is no gutter. */
.doc-block .doc-en, .doc-block .doc-tgt, .doc-block .doc-weglot { font-size: var(--fs-doc-body); line-height: 1.65; overflow-wrap: anywhere; }
.doc-block .doc-en { color: var(--doc-ink-src); }
.doc-block .doc-tgt { color: var(--doc-ink); }
.doc-block[data-b="h1"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-doc-h1); font-weight: 500; line-height: 1.25; letter-spacing: -0.012em; }
.doc-block:is([data-b="h2"], [data-b="h3"]) :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-doc-h2); font-weight: 500; line-height: 1.32; letter-spacing: -0.006em; }
.doc-block:is([data-b="h4"], [data-b="h5"], [data-b="h6"]) :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: calc(var(--fs-doc-body) + 1px); font-weight: 500; line-height: 1.4; }
.doc-block[data-b="button"] :is(.doc-en, .doc-tgt) { width: fit-content; max-width: calc(100% - 2 * var(--doc-pad)); padding: 6px 18px; border: 1px solid var(--border-strong); border-radius: 999px; font-size: var(--fs-base); font-weight: 500; line-height: 1.4; }
.doc-block:is([data-b="meta-title"], [data-b="meta-description"]) :is(.doc-en, .doc-tgt) { padding: 10px 16px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--doc-sheet-hover); }
.doc-block[data-b="meta-title"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: calc(var(--fs-doc-body) + 1px); font-weight: 500; line-height: 1.4; }
.doc-block[data-b="meta-description"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-base); color: var(--doc-muted); line-height: 1.55; }
.doc-block[data-b="h1"] { --doc-mt: 28px; --doc-mb: 12px; }
.doc-block[data-b="h2"] { --doc-mt: 28px; --doc-mb: 8px; }
.doc-block:is([data-b="h3"], [data-b="h4"], [data-b="h5"], [data-b="h6"]) { --doc-mt: 20px; --doc-mb: 6px; }
.doc-block[data-b="li"] { --doc-mt: 4px; --doc-mb: 4px; }
.doc-block[data-b="button"] { --doc-mt: 12px; --doc-mb: 12px; }
.doc-block:is([data-b="meta-title"], [data-b="meta-description"]) { --doc-mt: 8px; --doc-mb: 8px; }
.doc-block:last-child { --doc-mb: 28px; }

/* The open text: indigo is the focus ring and the outline of the text being edited, nothing else.
   An edited text carries a 3px ochre bar (and the word Edited in ochre), a flagged one a brick bar and tint; a locked one is muted. */
.doc-block > .doc-tgt:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
.doc-tgt:empty::before, .doc-weglot:empty::before { content: attr(data-placeholder); color: var(--doc-placeholder); pointer-events: none; }
.doc-block[data-source="edit"] .doc-tgt::after { content: ""; position: absolute; inset-block: 2px; inset-inline-start: -14px; width: 3px; border-radius: var(--radius-sm); background: var(--doc-edited); }
.doc-block:not([data-lock=""]) :is(.doc-en, .doc-tgt) { color: var(--doc-muted); cursor: default; }
/* A text a check flagged: a tint under the translation with a 6px ring and a 3px bar left of it, drawn with two shadows
   (no layout change). `data-flagged` is set by paintBlock (document_desk.js). */
.doc-block[data-flagged] > .doc-tgt { background: var(--doc-flag-bg); box-shadow: 0 0 0 6px var(--doc-flag-bg), -6px 0 0 3px var(--doc-flag); }

/* A text that is also on other pages: one small count in the translation's right gutter, a popover on click, and the
   sentence in the note row under the text while it has focus. The marker and the popover are overlays: no row or column changes size (CEL-072). An absolutely
   positioned grid item with `grid-column: 2` alone reaches the container's far edge (its auto end is the padding edge), so the
   cell is named with both lines: `2 / 3`, `1 / 2`. */
.doc-shared { position: absolute; z-index: 3; grid-column: 2 / 3; grid-row: 1 / 2; inset-inline-end: 2px; inset-block-end: 6px; }
.doc-shared-mark { min-width: 18px; height: 20px; padding: 0 4px; border: 1px solid var(--border); border-radius: 999px; background: var(--surface); color: var(--fg); font-size: var(--fs-xs); line-height: 18px; text-align: center; cursor: pointer; }
.doc-shared-mark:hover, .doc-shared-mark[aria-expanded="true"] { border-color: var(--border-strong); color: var(--fg); }
.doc-shared-mark:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-shared-pop { position: absolute; z-index: 6; top: calc(100% + 6px); inset-inline-end: 0; width: 340px; max-width: 70vw; max-height: 260px; overflow: auto; padding: 12px 14px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); box-shadow: 0 8px 24px var(--border-strong); color: var(--fg); font-size: var(--fs-sm); font-weight: 400; line-height: 1.5; text-align: start; }
.doc-shared-pop:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-shared-pop-up { top: auto; bottom: calc(100% + 6px); }
.doc-shared-pop-text { margin: 0 0 8px; }
.doc-shared-pop-list { margin: 0; padding: 0; list-style: none; color: var(--fg); font-size: var(--fs-xs); }
.doc-shared-pop-list li { padding: 2px 0; overflow-wrap: anywhere; }
.doc-shared-warn { flex: 1 1 100%; }

/* What a block says about itself, under its translation: the colour of the note, nothing else moves */
.doc-note { position: relative; grid-column: 2; grid-row: 2; display: flex; flex-wrap: wrap; align-items: center; gap: 2px 12px; margin: 0 var(--doc-pad); font-size: var(--fs-sm); line-height: 1.45; color: var(--doc-muted); }
.doc-note:empty, .doc-note > :empty { display: none; }
.doc-note > * { padding-bottom: 8px; }
.doc-note-chars { font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-note-same { font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-note-links { flex: 1 1 100%; font-size: var(--fs-sm); color: var(--doc-flag); }   /* a link the text lacks (CEL-096); empty = no room */
.doc-blocks:not([data-weglot="on"]) .doc-note-same { display: none; }
.doc-block[data-state="saving"] .doc-note { color: var(--doc-muted); }
.doc-block[data-source="edit"][data-state="idle"] .doc-note-state { color: var(--doc-edited-ink); font-weight: 500; }
.doc-block[data-state="error"] .doc-note { color: var(--err); }
.doc-block[data-state="conflict"] .doc-note { color: var(--notice-fg); }
.doc-conflict { position: relative; grid-column: 2; grid-row: 3; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 var(--doc-pad) var(--doc-mb); font-size: var(--fs-sm); color: var(--notice-fg); }
.doc-conflict > span { flex: 1 0 100%; }

/* The toolbar floats just above the open translation, right-aligned, only while focus is in the block or the pointer is over it */
.doc-tools { position: absolute; z-index: 4; top: -12px; inset-inline-end: 12px; display: flex; overflow: hidden; border: 1px solid var(--border-strong); border-radius: 999px; background: var(--doc-sheet); box-shadow: 0 8px 24px var(--border); visibility: hidden; opacity: 0; transition: opacity 0.12s; }
.doc-blocks[data-weglot="on"] .doc-tools { inset-inline-end: calc((100% - 48px) / 3 + 36px); }
.doc-block:focus-within .doc-tools, .doc-block:hover .doc-tools { visibility: visible; opacity: 1; }
.doc-tools .desk-btn { padding: 5px 12px; border: 0; border-radius: 0; font-size: var(--fs-xs); }
.doc-tools .desk-btn + .desk-btn { border-inline-start: 1px solid var(--border); }
.doc-tool-weglot, .doc-tool-revert { display: none; }
.doc-blocks[data-weglot="on"] .doc-tool-weglot { display: inline-block; }
.doc-block[data-source="edit"] .doc-tool-revert { display: inline-block; }

/* The status bar: where saving stands, undo / redo, Show the website's text and the page's size */
.doc-status { position: sticky; bottom: 0; z-index: 20; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 16px; min-height: 44px; padding: 6px 110px 6px 24px; border-top: 1px solid var(--border); background: var(--doc-sheet); }
.doc-save { display: flex; align-items: center; gap: 8px; min-width: 0; margin: 0; font-size: var(--fs-sm); }
.doc-save::before { content: ""; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); }
.doc-save:empty::before { display: none; }
.doc-save[data-state="loading"], .doc-save[data-state="saving"] { color: var(--doc-muted); }
.doc-save[data-state="loading"]::before, .doc-save[data-state="saving"]::before { background: var(--faint); }
.doc-save[data-state="retrying"], .doc-save[data-state="offline"], .doc-save[data-state="conflict"] { color: var(--notice-fg); }
.doc-save[data-state="retrying"]::before, .doc-save[data-state="offline"]::before, .doc-save[data-state="conflict"]::before { background: var(--warn); }
.doc-save[data-state="error"], .doc-save[data-state="refused"], .doc-save[data-state="stopped"] { color: var(--err); }
.doc-save[data-state="error"]::before, .doc-save[data-state="refused"]::before, .doc-save[data-state="stopped"]::before { background: var(--err); }
.doc-save .desk-btn { padding: 2px 10px; font-size: var(--fs-xs); }
.doc-save-more { display: inline-flex; align-items: center; gap: 8px; font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-save-more:empty { display: none; }
.doc-save-more .desk-btn, .doc-seen-reset { padding: 2px 10px; font-size: var(--fs-xs); }
.doc-seen-reset[hidden] { display: none; }
.doc-status-mid { display: flex; flex: 1 1 auto; align-items: center; justify-content: center; gap: 8px; min-width: 0; }
.doc-status-end { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; }
.doc-desk-version { font-size: var(--fs-sm); color: var(--doc-muted); text-decoration: none; white-space: nowrap; }
.doc-desk-version:hover, .doc-desk-version:focus-visible { color: var(--fg); text-decoration: underline; }
.doc-status .desk-btn { padding: 4px 12px; }
.doc-kbd { margin-inline-start: 6px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: var(--fs-xs); font-weight: 400; color: var(--doc-muted); }
.doc-kbd:empty { display: none; }
.doc-filter-wrap { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 500; }
.doc-next-count { font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-words { font-size: var(--fs-sm); color: var(--doc-muted); }
/* Messages stay above the BugHerd tab (fixed, right 0, bottom 10 px, 70 px high): 110 px, as much as the status bar keeps free at its right end */
.doc .toast-stack { bottom: 110px; }
.doc .toast-close { width: auto; height: auto; padding: 2px 8px; border-radius: var(--radius-sm); color: var(--fg); font-size: var(--fs-sm); }

/* The history of one text: a drawer over the foot of the sheets, versions side by side, newest on the right */
.doc-drawer { position: fixed; left: 0; right: 0; bottom: 44px; z-index: 30; display: flex; flex-direction: column; max-height: 50vh; overflow: auto; border-top: 1px solid var(--border-strong); background: var(--doc-sheet); animation: doc-slide 0.25s ease-out; }
@keyframes doc-slide { from { transform: translateY(100%); } to { transform: none; } }
.doc-drawer > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 24px 0; }
.doc-drawer > header h2 { margin: 0; font-size: var(--fs-lg); }
.doc-history-note { margin: 4px 24px 0; font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-history-list { display: flex; flex-direction: row; align-items: flex-start; gap: 16px; margin: 0; padding: 12px 24px 20px; overflow-x: auto; list-style: none; }
.doc-version { flex: 0 0 260px; min-width: 260px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); }
.doc-version-meta { display: block; font-size: var(--fs-sm); color: var(--doc-muted); }
.doc-version-text { margin-top: 6px; font-size: var(--fs-md); overflow-wrap: anywhere; }
.doc-version .doc-restore { margin-top: 12px; }
.doc-version-empty { font-size: var(--fs-sm); color: var(--doc-muted); }

/* A tablet loses the rail (the Sections list takes its place) and gives the sheets the room */
@media (max-width: 1024px) {
  .doc-outline { display: none; }
  .doc-sections-wrap { display: flex; }
  .doc-sheets { --doc-pad: 32px; padding: 20px 16px; }
  .doc-sheets:has(.doc-blocks[data-weglot="on"]), .doc-blocks[data-weglot="on"] { --doc-pad: 20px; }
}
/* A phone: one column. English (muted, small) above the translation above Weglot; the toolbar sits under the text */
@media (max-width: 767px) {
  .doc-app { grid-template-columns: minmax(0, 1fr); }
  .doc-tree { position: static; height: auto; max-height: 40vh; border-inline-end: 0; border-bottom: 1px solid var(--border); }
  .doc-bar { position: static; flex-wrap: wrap; height: auto; padding: 8px 12px; }
  .doc-title { flex-wrap: wrap; }
  .doc-path { white-space: normal; overflow-wrap: anywhere; }
  .doc-actions { flex: 1 1 100%; flex-wrap: wrap; margin-inline-start: 0; }
  .doc-tabs { position: static; overflow-x: auto; padding: 0 12px; }
  .doc-heads { display: none; }
  .doc-sheets { padding: 12px; }
  .doc-block, .doc-blocks[data-weglot="on"] .doc-block { --doc-pad: 0px; display: block; padding: 0 16px; border-inline: 1px solid var(--border); background: var(--doc-sheet); }
  .doc-block::before, .doc-block::after { display: none; }
  .doc-block:last-child { border-bottom: 1px solid var(--border); border-radius: 0 0 var(--radius) var(--radius); }
  .doc-tag { position: static; display: block; padding-top: 8px; opacity: 1; }
  .doc-block .doc-en { font-size: var(--fs-base); color: var(--doc-muted); }
  .doc-weglot { padding: 4px 0 8px; border-inline: 0; background: none; }
  .doc-block[data-source="edit"] .doc-tgt::after { inset-inline-start: -10px; }
  .doc-note, .doc-conflict { margin-inline: 0; }
  .doc-shared { position: relative; inset: auto; display: block; margin: 0 0 8px; text-align: end; }
  .doc-tools, .doc-blocks[data-weglot="on"] .doc-tools { position: static; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; overflow: visible; border: 0; border-radius: 0; background: none; box-shadow: none; display: none; }
  .doc-block:focus-within .doc-tools, .doc-blocks[data-weglot="on"] .doc-block:focus-within .doc-tools { display: flex; visibility: visible; opacity: 1; }
  .doc-tools .desk-btn, .doc-tools .desk-btn + .desk-btn { border: 1px solid var(--border-strong); border-radius: 999px; }
  .doc-status { padding: 8px 12px; }
  .doc-status-mid { flex-basis: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .doc-status .doc-kbd { display: none; }
  .doc-status-mid { gap: 6px; }
  .doc-status-mid .desk-btn { padding: 4px 8px; }
  .doc-filter-wrap .desk-select { padding-inline: 6px; }
  .doc-filter-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .doc .toast-stack { bottom: 100px; }
  .doc-drawer { bottom: 0; max-height: 60vh; }
  .doc-drawer > header { padding: 14px 12px 0; }
  .doc-history-note { margin-inline: 12px; }
  .doc-history-list { padding-inline: 12px; }
}
@media (prefers-reduced-motion: reduce) {
  .doc-drawer { animation: none; }
  .doc-tag, .doc-tools { transition: none; }
}

.doc-weglot[hidden], .doc-head-weglot[hidden], .doc-conflict[hidden], .doc-banner[hidden], .doc-drawer[hidden], .doc-sections-wrap[hidden], .doc-tools[hidden] { display: none; }
.doc [hidden] { display: none; }
"""

_SCRIPT_END = re.compile(r"</(script)", re.I)
_STYLE_END = re.compile(r"</(style)", re.I)


def _read(path: Path, what: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(
            f"{what} is missing at {path}: the document page inlines it, so it cannot be built without it")
    return path.read_text(encoding="utf-8")


def _script(js: str) -> str:
    """A `<script>` holding `js` as it is. Only a `</script` would end it early, so only that
    is escaped (`<\\/script`, the same text to a JS string or regex)."""
    body = _SCRIPT_END.sub(r"<\\/\1", js)
    return "<script>\n" + body + ("" if body.endswith("\n") else "\n") + "</script>"


def _config() -> str:
    """What the runtime must know that is not copy: the languages, the pages, where the data is."""
    cfg = {
        "locales": [{"code": code, "endonym": endonym, "dir": direction, "flag": flag}
                    for code, endonym, direction, flag in S.LOCALES],
        "pages": list(S.PAGE_KEYS),
        "data": DATA_URL,
        "version": VERSION,
    }
    return _dump(cfg).replace("</", "<\\/")      # `</` would end the enclosing <script>


def _tree() -> str:
    """The page tree's frame (CEL-069): the filter and an empty list the runtime fills from pages.json (each page's
    path, grouped by folder), plus the open page's sections (today's outline, moved under its row by the runtime)."""
    return (
        f'    <nav id="doc-tree" class="doc-tree" aria-label="{escape(t("nav.tree.label"))}">\n'
        '      <label class="doc-tree-filter">'
        f'<span class="doc-sr">{escape(t("nav.tree.filter"))}</span>'
        f'<input type="search" id="doc-tree-filter" placeholder="{escape(t("nav.tree.filter"))}" autocomplete="off" '
        'spellcheck="false" aria-controls="doc-tree-list" aria-keyshortcuts="/ Control+K Meta+K">'
        '<kbd class="doc-kbd-hint" aria-hidden="true">/</kbd></label>\n'
        '      <div id="doc-tree-list" class="doc-tree-list"></div>\n'
        '      <p id="doc-tree-none" class="doc-tree-none" hidden></p>\n'
        '      <nav id="doc-outline" class="doc-outline" aria-labelledby="doc-outline-title" hidden>\n'
        f'        <h2 id="doc-outline-title" class="doc-sr">{escape(t("doc.outline.title"))}</h2>\n'
        '        <ol id="doc-outline-list" class="doc-outline-list"></ol>\n'
        '      </nav>\n'
        '    </nav>\n'
    )


def _tabs() -> str:
    """The language tabs (CEL-069): one per language in the LOCALES order, each with the open page's status mark."""
    tabs = "".join(
        f'<button type="button" id="doc-tab-{code}" class="doc-tab" role="tab" data-lang="{code}" aria-selected="false" '
        f'tabindex="-1" aria-keyshortcuts="Alt+{i}"><span class="doc-st" data-s="unknown" aria-hidden="true"></span>'
        f'<span class="doc-tab-name">{escape(S.lang_name(code))}</span><span class="doc-st-word doc-sr"></span></button>'
        for i, (code, *_rest) in enumerate(S.LOCALES, 1))
    return (
        f'      <div id="doc-tabs" class="doc-tabs" role="tablist" aria-label="{escape(t("nav.tabs.label"))}">{tabs}'
        f'<span class="doc-tabs-hint" aria-hidden="true">{escape(t("nav.tabs.hint"))}</span></div>\n'
    )


def _dom() -> str:
    """The server-rendered shell (contract section 7.2). The runtime fills what is empty here."""
    translate = escape(t("doc.translate"))
    return (
        '<main id="doc" class="doc" data-state="loading">\n'
        '  <div class="doc-app">\n'
        + _tree() +
        '    <div class="doc-main">\n'
        '    <header id="doc-bar" class="doc-bar">\n'
        '      <h1 id="doc-title" class="doc-title"><span class="doc-path"><span class="doc-path-dir"></span>'
        '<span class="doc-path-leaf"></span></span><span class="doc-path-name"></span></h1>\n'
        '      <div class="doc-actions">\n'
        '        <label class="doc-switch"><input type="checkbox" id="doc-weglot" role="switch">'
        f'<span>{escape(t("doc.weglot.toggle"))}</span></label>\n'
        f'        <a id="doc-rules" class="desk-btn" href="/admin/localization/rules/">{escape(t("doc.rules"))}</a>\n'
        f'        <button type="button" id="doc-translate" class="desk-btn">{translate}</button>\n'
        '      </div>\n'
        '    </header>\n'
        + _tabs() +
        '    <div id="doc-banner" class="doc-banner" hidden><p id="doc-banner-text"></p>\n'
        f'      <button type="button" id="doc-banner-translate" class="desk-btn is-strong" hidden>{translate}</button></div>\n'
        '    <div class="doc-layout">\n'
        '      <div class="doc-sheets">\n'
        f'        <label class="doc-sections-wrap"><span class="doc-sections-label">{escape(t("doc.sections"))}</span>\n'
        '          <select id="doc-sections" class="desk-select doc-sections"></select></label>\n'
        f'        <div id="doc-filter-empty" class="doc-banner" hidden><p>{escape(t("doc.filter.empty"))}</p></div>\n'
        '        <div id="doc-heads" class="doc-heads" aria-hidden="true">\n'
        '          <span class="doc-head doc-head-en"></span><span class="doc-head doc-head-tgt"></span>'
        '<span class="doc-head doc-head-weglot" hidden></span></div>\n'
        '        <ol id="doc-blocks" class="doc-blocks" data-weglot="off"></ol>\n'
        '      </div>\n'
        '    </div>\n'
        '    </div>\n'
        '  </div>\n'
        '    <footer id="doc-status" class="doc-status">\n'
        '      <p id="doc-save" class="doc-save" role="status" aria-live="polite" data-state="loading"></p>\n'
        '      <div class="doc-status-mid">\n'
        f'        <button type="button" id="doc-undo" class="desk-btn" disabled><span class="doc-btn-label">{escape(t("doc.undo"))}</span> <kbd class="doc-kbd"></kbd></button>\n'
        f'        <button type="button" id="doc-redo" class="desk-btn" disabled><span class="doc-btn-label">{escape(t("doc.redo"))}</span> <kbd class="doc-kbd"></kbd></button>\n'
        f'        <label class="doc-filter-wrap"><span class="doc-filter-label">{escape(t("doc.filter.label"))}</span>\n'
        '          <select id="doc-filter" class="desk-select doc-filter">\n'
        f'            <option value="all">{escape(t("doc.filter.all"))}</option>\n'
        f'            <option value="new">{escape(t("doc.filter.new"))}</option>\n'
        f'            <option value="edited">{escape(t("doc.filter.edited"))}</option>\n'
        f'            <option value="flagged">{escape(t("doc.filter.flagged"))}</option>\n'
        '          </select></label>\n'
        f'        <button type="button" id="doc-next" class="desk-btn" aria-keyshortcuts="Alt+Enter" disabled><span class="doc-btn-label">{escape(t("doc.next"))}</span> <kbd class="doc-kbd"></kbd></button>\n'
        '        <span id="doc-next-count" class="doc-next-count"></span>\n'
        '      </div>\n'
        '      <div class="doc-status-end">\n'
        f'        <a id="doc-desk-version" class="doc-desk-version" href="{escape(DESK_CHANGELOG_URL)}" target="_blank" '
        f'rel="noopener" data-tip="{escape(t("doc.version.tip"))}">{escape(t("doc.version", version=DESK_VERSION))}</a>\n'
        '        <span id="doc-words" class="doc-words"></span>\n'
        '      </div>\n'
        '    </footer>\n'
        '    <aside id="doc-history" class="doc-drawer" role="dialog" aria-modal="false" '
        'aria-labelledby="doc-history-title" hidden>\n'
        f'      <header><h2 id="doc-history-title">{escape(t("doc.history.title"))}</h2>\n'
        f'        <button type="button" id="doc-history-close" class="desk-btn">{escape(t("doc.history.close"))}</button></header>\n'
        f'      <p class="doc-history-note">{escape(t("doc.history.note"))}</p>\n'
        '      <ol id="doc-history-list" class="doc-history-list"></ol>\n'
        '    </aside>\n'
        '    <div id="doc-confirm" class="cpw-overlay" hidden><div class="cpw-modal" role="dialog" '
        'aria-modal="true" aria-labelledby="doc-confirm-title">\n'
        '      <h2 id="doc-confirm-title" class="cpw-title"></h2><p id="doc-confirm-body"></p>\n'
        '      <div class="cpw-actions">'
        f'<button type="button" id="doc-confirm-cancel" class="cpw-btn cpw-cancel">{escape(t("doc.confirm.cancel"))}</button>\n'
        f'        <button type="button" id="doc-confirm-ok" class="cpw-btn cpw-save">{translate}</button></div></div></div>\n'
        '    <div id="doc-toasts" class="toast-stack" aria-live="polite"></div>\n'
        '</main>\n'
    )


def render_page() -> str:
    """`index.html`, whole. Raises FileNotFoundError, naming the file, if the runtime or the
    field it builds on is not there to inline."""
    doc_js = _read(DOC_JS, "document_desk.js")
    rich_js = _read(RICH_JS, "spike/rich_field.js")
    rich_css = _read(RICH_CSS, "spike/rich_field.css")
    export_js = _read(EXPORT_JS, "document_export.js")
    export_css = _read(EXPORT_CSS, "document_export.css")

    head = S._head(t("doc.meta.title"), t("doc.meta.description"))
    assert head[-2:] == ["</head>", "<body>"], "desk_shared._head changed its ending"
    style = "<style>\n" + _STYLE_END.sub(r"<\\/\1", rich_css + "\n" + DOC_TOKENS + "\n" + SHELL_TOKENS + "\n" + DOC_CSS + "\n" + export_css) + "</style>"

    # Globals first: the switch back to "saving off", the copy, and the helpers v1 shares
    # (t / tn, the sign-in Worker call, the tooltip). The runtime and the field come after.
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
    parts.append('<script type="application/json" id="doc-config">' + _config() + "</script>")
    parts.append(_script(rich_js))
    parts.append(_script(doc_js))
    parts.append(_script(export_js))
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


# The shell's own tokens (CEL-069, CEL-068 shell-spec §1): the sizes, the in-progress brown of a status mark, the tree's
# ground; the ink, muted and cream tokens are CEL-070's DOC_TOKENS (both are set on .doc, which holds the whole shell).
SHELL_TOKENS = """\
.doc {
  --doc-progress: #7A4314;
  --tree-w: 288px; --ctx-h: 52px; --tabs-h: 38px; --tree-bg: var(--doc-tray); --fs-path: 15px;
  --mono: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}
"""


# ── The build ───────────────────────────────────────────────────────────────

def main() -> int:
    if not UNITS_DIR.is_dir():
        print(f"ERROR: no unit data at {UNITS_DIR}", file=sys.stderr)
        return 2
    docs = load_documents(UNITS_DIR)
    # A document page with a page missing or empty is not a document page: the grid names
    # four, and a reader who opens the fifth cell of an empty one finds nothing and no reason.
    short = [k for k in S.PAGE_KEYS if k not in docs or not docs[k]["blocks"]]
    if short:
        print(f"ERROR: no texts found for {', '.join(short)} in {UNITS_DIR} — refusing to write "
              "an incomplete document page", file=sys.stderr)
        return 2
    # The menu and footer are left out by the engine's per-unit `chrome` flag. Every real page has some
    # (75 or 76 of them today); not one flagged anywhere means the units files predate the flag, and writing
    # the page would put the site's menu and footer into the desk without a word.
    if not any(d["chrome"] for d in docs.values()):
        print(f"ERROR: no unit on any of the four pages is flagged `chrome` in {UNITS_DIR} -- these units files "
              "were written before the engine's chrome flag; refresh the manifest first. Refusing to write "
              "a document page that would show the site's menu and footer.", file=sys.stderr)
        return 2
    try:
        page = render_page()           # before anything is written: a missing file writes nothing
    except FileNotFoundError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    (OUT_DIR / "data").mkdir(parents=True, exist_ok=True)
    written = []
    index = OUT_DIR / "index.html"
    index.write_text(page, encoding="utf-8")
    written.append(index)
    # /admin/localization/ itself is only a redirect to this page (CEL-045); the dashboard's Localization tabs point at it
    root_index = OUT_DIR.parent / "index.html"
    root_index.write_text(S.render_index_redirect(), encoding="utf-8")
    written.append(root_index)
    for name, payload in [("pages", pages_payload(docs))] + list(docs.items()):
        target = OUT_DIR / "data" / f"{name}.json"
        target.write_text(_dump(payload), encoding="utf-8")
        written.append(target)

    print(f"{sum(len(d['blocks']) for d in docs.values())} texts on {len(docs)} pages "
          f"({sum(d['chrome'] for d in docs.values())} menu and footer texts left out)")
    for p in written:
        print(f"  wrote {p} ({p.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
