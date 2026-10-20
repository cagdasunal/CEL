#!/usr/bin/env python3
"""Build the document page (desk v2, CEL-026) under /admin/localization/document/.

    cd tools && python3 -m localize_desk.generate_document_page

The v1 desk is a list of texts. This page is one page of the website read as a document:
every text in the order the page shows it, English on one sheet and the translation on the
next, edited in place and saved by itself; an outline of the page beside the sheets, a status
bar below them (design B, chosen by the operator 2026-10-19). It is a second page beside the
v1 desk, not a change to it: nothing here touches `generate_desk_page.py` or the v1 pages, and
it reuses their pieces (`LOCALES`, `PAGE_KEYS`, `_head`, the proxy and tooltip scripts,
COPY.md) by import.

What it writes (all under `OUT_DIR`):

    index.html           the page: server-rendered shell + the runtime, inlined
    data/pages.json      per page: key, path, how many blocks, how many left out, which can be edited
    data/<page>.json     one document: its blocks in page order, English, lock, translations

The site's menu and footer texts (the units files' per-unit `chrome` flag, written by the engine's
manifest: also on 30 pages or more, and outside every heading) are not part of the page a reviewer
reads and are left out; each file says how many (`chrome`). Every other text is shown and editable.

The page reads those files once it is open, so a reviewer opens a page in the language they
work in without downloading the other seven. The runtime (`document_desk.js`) is readable
source beside this module and is inlined into the page; it is never served as its own file.

The contract between this generator, the runtime and the tests is
`runtime/out/loc2/CEL-026/contract.md` in the working repository (section 7 is design B).
Every word on the page is a COPY.md line (`doc.*`, then the v1 `lang.*` and `page.*`); this
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
DESK_VERSION = "2.1.0"
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
/* The document page (desk v2, design B): an outline beside the sheets, a status bar below them. */
html { scroll-padding-top: 72px; scroll-padding-bottom: 64px; }
.doc { --doc-topbar: 53px; padding: 8px 0 0; }

/* The pages x languages grid */
.doc-gridwrap { margin: 8px 0 28px; }
.doc-grid-title { margin: 0 0 8px; font-size: var(--fs-base); font-weight: 600; }
.doc-grid { width: 100%; min-width: 720px; border-collapse: collapse; }
.doc-grid th, .doc-grid td { padding: 4px; text-align: start; vertical-align: top; }
.doc-grid thead th { font-size: var(--fs-sm); font-weight: 600; color: var(--muted); white-space: nowrap; }
.doc-grid-page { padding-inline-end: 12px; font-size: var(--fs-md); font-weight: 600; white-space: nowrap; }
.doc-flag { margin-inline-end: 4px; }
.doc-cell { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: none; color: var(--fg); font: inherit; font-size: var(--fs-sm); text-align: start; cursor: pointer; }
.doc-cell:hover { background: var(--stripe); }
.doc-cell:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-cell-status { font-weight: 600; }
.doc-cell-count { color: var(--muted); font-size: var(--fs-xs); }
.doc-cell[data-status="unknown"] .doc-cell-status, .doc-cell[data-status="none"] .doc-cell-status { color: var(--muted); font-weight: 400; }
.doc-cell[data-status="exported"] .doc-cell-status { color: var(--ok); }
.doc-cell[aria-pressed="true"] { border-color: var(--fg); }
.doc-cell[aria-pressed="true"] .doc-cell-status, .doc-cell[aria-pressed="true"] .doc-cell-count { font-weight: 700; }

/* The title and the one button above the sheets */
.doc-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 24px; min-height: 72px; padding: 12px 0; border-top: 1px solid var(--border); }
.doc-title { margin: 0; font-size: var(--fs-xl); font-weight: 650; }
.doc-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.doc-banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px; margin: 0 0 16px; padding: 12px 16px; border: 1px solid var(--notice-border); border-radius: var(--radius); background: var(--notice-bg); color: var(--notice-fg); }
.doc-banner p { flex: 1 1 320px; margin: 0; font-size: var(--fs-base); }

/* The outline rail, then the sheets on a recessed area */
.doc-layout { display: grid; grid-template-columns: 240px minmax(0, 1fr); align-items: start; }
.doc-outline { position: sticky; top: calc(var(--doc-topbar) + 16px); max-height: calc(100vh - var(--doc-topbar) - 76px); overflow-y: auto; padding: 4px 12px 16px 0; }
.doc-outline-title { margin: 0 0 10px 12px; font-size: var(--fs-xs); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.doc-outline-list { margin: 0; padding: 0; list-style: none; }
.doc-outline-item { display: block; width: 100%; padding: 7px 10px; border: 0; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; background: none; color: var(--fg); font: inherit; text-align: start; cursor: pointer; }
.doc-outline-item:hover { background: var(--stripe); }
.doc-outline-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.doc-outline-item[aria-current="true"] { box-shadow: inset 2px 0 0 var(--fg); font-weight: 700; }
.doc-outline-name { display: block; font-size: var(--fs-md); line-height: 1.3; }
.doc-outline-count { display: block; margin-top: 2px; font-size: var(--fs-xs); font-weight: 400; color: var(--muted); }
.doc-sheets { --doc-pad: 48px; min-width: 0; min-height: 60vh; padding: 24px; border-inline-start: 1px solid var(--border); background: var(--panel); }
.doc-sheets:has(.doc-blocks[data-weglot="on"]) { --doc-pad: 28px; }
.doc-sections-wrap { display: none; align-items: center; gap: 8px; max-width: 1400px; margin: 0 auto 12px; font-size: var(--fs-sm); font-weight: 600; }
.doc-sections { flex: 1 1 auto; min-width: 0; }

/* The sheet heads, and the blocks: one grid row across the sheets */
.doc-heads { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); column-gap: 24px; max-width: 1400px; margin: 0 auto; }
.doc-head { padding: 14px var(--doc-pad) 10px; border: 1px solid var(--border); border-radius: var(--radius) var(--radius) 0 0; background: var(--elevated); font-size: var(--fs-sm); font-weight: 650; }
.doc-blocks { max-width: 1400px; margin: 0 auto; padding: 0; list-style: none; }
.doc-blocks[data-weglot="on"] { --doc-pad: 28px; }
.doc-block { --doc-mt: 16px; --doc-mb: 10px; position: relative; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: auto auto auto 1fr; column-gap: 24px; scroll-margin-top: 64px; }
.doc-blocks[data-weglot="on"] .doc-block { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.doc-block::before, .doc-block::after { content: ""; grid-row: 1 / -1; border-inline: 1px solid var(--border); background: var(--elevated); }
.doc-block::before { grid-column: 1; }
.doc-block::after { grid-column: 2; }
.doc-block:last-child::before, .doc-block:last-child::after, .doc-block:last-child > .doc-weglot { border-bottom: 1px solid var(--border); border-radius: 0 0 var(--radius) var(--radius); }
.doc-block:hover::before, .doc-block:hover::after, .doc-block:hover > .doc-weglot, .doc-block:focus-within::before, .doc-block:focus-within::after, .doc-block:focus-within > .doc-weglot { background-image: linear-gradient(var(--stripe), var(--stripe)); }
.doc-block[data-flash] { background: var(--selected); }
.doc-block[data-flash]::before, .doc-block[data-flash]::after, .doc-block[data-flash] > .doc-weglot { background-image: linear-gradient(var(--selected), var(--selected)); }
.doc-en, .doc-block > .doc-tgt { margin: var(--doc-mt) var(--doc-pad) var(--doc-mb); }
.doc-en { grid-column: 1; grid-row: 1; white-space: pre-wrap; }
.doc-block > .doc-tgt { position: relative; grid-column: 2; grid-row: 1; padding: 0; border: 0; border-radius: var(--radius-sm); background: none; }
.doc-weglot { grid-column: 3; grid-row: 1 / -1; padding: var(--doc-mt) var(--doc-pad) var(--doc-mb); border-inline: 1px solid var(--border); background: var(--elevated); color: var(--muted); cursor: default; white-space: pre-wrap; }
.doc-tag { position: absolute; z-index: 2; top: 2px; inset-inline-start: var(--doc-pad); font-size: var(--fs-xs); line-height: 1.3; color: var(--muted); opacity: 0; pointer-events: none; transition: opacity 0.12s; }
.doc-block:hover .doc-tag, .doc-block:focus-within .doc-tag { opacity: 1; }

/* Type of text, from the block's tag: the page's own hierarchy, at the page's own sizes. Structure
   comes from the type alone; there is no gutter. */
.doc-block .doc-en, .doc-block .doc-tgt, .doc-block .doc-weglot { font-size: var(--fs-doc-body); line-height: 1.6; overflow-wrap: anywhere; }
.doc-block[data-b="h1"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-doc-h1); font-weight: 700; line-height: 1.2; }
.doc-block:is([data-b="h2"], [data-b="h3"]) :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-doc-h2); font-weight: 650; line-height: 1.3; }
.doc-block:is([data-b="h4"], [data-b="h5"], [data-b="h6"]) :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: calc(var(--fs-doc-body) + 1px); font-weight: 650; line-height: 1.35; }
.doc-block[data-b="button"] :is(.doc-en, .doc-tgt) { width: fit-content; max-width: calc(100% - 2 * var(--doc-pad)); padding: 6px 18px; border: 1px solid var(--border-strong); border-radius: 999px; font-size: var(--fs-base); font-weight: 600; line-height: 1.4; }
.doc-block:is([data-b="meta-title"], [data-b="meta-description"]) :is(.doc-en, .doc-tgt) { padding: 10px 16px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.doc-block[data-b="meta-title"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-lg); font-weight: 600; line-height: 1.35; }
.doc-block[data-b="meta-description"] :is(.doc-en, .doc-tgt, .doc-weglot) { font-size: var(--fs-md); color: var(--muted); line-height: 1.5; }
.doc-block[data-b="h1"] { --doc-mt: 28px; --doc-mb: 12px; }
.doc-block[data-b="h2"] { --doc-mt: 28px; --doc-mb: 8px; }
.doc-block:is([data-b="h3"], [data-b="h4"], [data-b="h5"], [data-b="h6"]) { --doc-mt: 20px; --doc-mb: 6px; }
.doc-block[data-b="li"] { --doc-mt: 4px; --doc-mb: 4px; }
.doc-block[data-b="button"] { --doc-mt: 12px; --doc-mb: 12px; }
.doc-block:is([data-b="meta-title"], [data-b="meta-description"]) { --doc-mt: 8px; --doc-mb: 8px; }
.doc-block:last-child { --doc-mb: 28px; }

/* The open text: indigo is the focus ring and the outline of the text being edited, nothing else.
   An edited text carries a 3px bar of the text colour at reduced opacity; a locked one is muted. */
.doc-block > .doc-tgt:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.doc-tgt:empty::before, .doc-weglot:empty::before { content: attr(data-placeholder); color: var(--muted); pointer-events: none; }
.doc-block[data-source="edit"] .doc-tgt::after { content: ""; position: absolute; inset-block: 2px; inset-inline-start: -14px; width: 3px; border-radius: var(--radius-sm); background: var(--fg); opacity: 0.35; }
.doc-block:not([data-lock=""]) :is(.doc-en, .doc-tgt) { color: var(--muted); cursor: default; }

/* What a block says about itself, under its translation: the colour of the note, nothing else moves */
.doc-note { position: relative; grid-column: 2; grid-row: 2; display: flex; flex-wrap: wrap; align-items: center; gap: 2px 12px; margin: 0 var(--doc-pad); font-size: var(--fs-xs); line-height: 1.4; color: var(--muted); }
.doc-note:empty, .doc-note > :empty { display: none; }
.doc-note > * { padding-bottom: 8px; }
.doc-note-chars { font-size: var(--fs-xs); color: var(--muted); }
.doc-note-same { font-size: var(--fs-xs); color: var(--muted); }
.doc-blocks:not([data-weglot="on"]) .doc-note-same { display: none; }
.doc-block[data-state="saving"] .doc-note { color: var(--muted); }
.doc-block[data-state="error"] .doc-note { color: var(--err); }
.doc-block[data-state="conflict"] .doc-note { color: var(--warn); }
.doc-conflict { position: relative; grid-column: 2; grid-row: 3; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 var(--doc-pad) var(--doc-mb); font-size: var(--fs-sm); color: var(--warn); }
.doc-conflict > span { flex: 1 0 100%; }

/* The toolbar floats just above the open translation, right-aligned, only while focus is in the block */
.doc-tools { position: absolute; z-index: 4; top: -12px; inset-inline-end: 12px; display: flex; overflow: hidden; border: 1px solid var(--border-strong); border-radius: 999px; background: var(--elevated); box-shadow: 0 8px 24px var(--border); visibility: hidden; opacity: 0; transition: opacity 0.12s; }
.doc-blocks[data-weglot="on"] .doc-tools { inset-inline-end: calc((100% - 48px) / 3 + 36px); }
.doc-block:focus-within .doc-tools { visibility: visible; opacity: 1; }
.doc-tools .desk-btn { padding: 5px 12px; border: 0; border-radius: 0; font-size: var(--fs-xs); }
.doc-tools .desk-btn + .desk-btn { border-inline-start: 1px solid var(--border); }
.doc-tool-weglot, .doc-tool-revert { display: none; }
.doc-blocks[data-weglot="on"] .doc-tool-weglot { display: inline-block; }
.doc-block[data-source="edit"] .doc-tool-revert { display: inline-block; }

/* The status bar: where saving stands, undo / redo, Show Weglot and the page's size */
.doc-status { position: sticky; bottom: 0; z-index: 20; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 16px; min-height: 44px; padding: 6px 24px; border-top: 1px solid var(--border); background: var(--elevated); }
.doc-save { display: flex; align-items: center; gap: 8px; min-width: 0; margin: 0; font-size: var(--fs-sm); }
.doc-save::before { content: ""; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); }
.doc-save:empty::before { display: none; }
.doc-save[data-state="loading"], .doc-save[data-state="saving"] { color: var(--muted); }
.doc-save[data-state="loading"]::before, .doc-save[data-state="saving"]::before { background: var(--faint); }
.doc-save[data-state="retrying"], .doc-save[data-state="offline"], .doc-save[data-state="conflict"] { color: var(--warn); }
.doc-save[data-state="retrying"]::before, .doc-save[data-state="offline"]::before, .doc-save[data-state="conflict"]::before { background: var(--warn); }
.doc-save[data-state="error"], .doc-save[data-state="refused"], .doc-save[data-state="stopped"] { color: var(--err); }
.doc-save[data-state="error"]::before, .doc-save[data-state="refused"]::before, .doc-save[data-state="stopped"]::before { background: var(--err); }
.doc-save .desk-btn { padding: 2px 10px; font-size: var(--fs-xs); }
.doc-status-mid { display: flex; flex: 1 1 auto; align-items: center; justify-content: center; gap: 8px; min-width: 0; }
.doc-status-end { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; }
.doc-desk-version { font-size: var(--fs-sm); color: var(--muted); text-decoration: none; white-space: nowrap; }
.doc-desk-version:hover, .doc-desk-version:focus-visible { color: var(--fg); text-decoration: underline; }
.doc-status .desk-btn { padding: 4px 12px; }
.doc-kbd { margin-inline-start: 6px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: var(--fs-xs); font-weight: 400; color: var(--muted); }
.doc-kbd:empty { display: none; }
.doc-filter-wrap { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 600; }
.doc-next-count { font-size: var(--fs-sm); color: var(--muted); }
.doc-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 600; cursor: pointer; }
.doc-toggle input { width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
.doc-toggle input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.doc-words { font-size: var(--fs-sm); color: var(--muted); }
.doc .toast-stack { bottom: 60px; }

/* The history of one text: a drawer over the foot of the sheets, versions side by side, newest on the right */
.doc-drawer { position: fixed; left: 0; right: 0; bottom: 44px; z-index: 30; display: flex; flex-direction: column; max-height: 50vh; overflow: auto; border-top: 1px solid var(--border-strong); background: var(--elevated); animation: doc-slide 0.25s ease-out; }
@keyframes doc-slide { from { transform: translateY(100%); } to { transform: none; } }
.doc-drawer > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 24px 0; }
.doc-drawer > header h2 { margin: 0; font-size: var(--fs-lg); }
.doc-history-note { margin: 4px 24px 0; font-size: var(--fs-sm); color: var(--muted); }
.doc-history-list { display: flex; flex-direction: row; align-items: flex-start; gap: 16px; margin: 0; padding: 12px 24px 20px; overflow-x: auto; list-style: none; }
.doc-version { flex: 0 0 260px; min-width: 260px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); }
.doc-version-meta { display: block; font-size: var(--fs-sm); color: var(--muted); }
.doc-version-text { margin-top: 6px; font-size: var(--fs-md); overflow-wrap: anywhere; }
.doc-version .doc-restore { margin-top: 12px; }
.doc-version-empty { font-size: var(--fs-sm); color: var(--muted); }

/* A tablet loses the rail (the Sections list takes its place) and gives the sheets the room */
@media (max-width: 1024px) {
  .doc-layout { grid-template-columns: minmax(0, 1fr); }
  .doc-outline { display: none; }
  .doc-sections-wrap { display: flex; }
  .doc-sheets { --doc-pad: 32px; padding: 20px 16px; }
  .doc-sheets:has(.doc-blocks[data-weglot="on"]), .doc-blocks[data-weglot="on"] { --doc-pad: 20px; }
}
/* A phone: one column. English (muted, small) above the translation above Weglot; the toolbar sits under the text */
@media (max-width: 767px) {
  .doc-heads { display: none; }
  .doc-sheets { padding: 12px; }
  .doc-block, .doc-blocks[data-weglot="on"] .doc-block { --doc-pad: 0px; display: block; padding: 0 16px; border-inline: 1px solid var(--border); background: var(--elevated); }
  .doc-block::before, .doc-block::after { display: none; }
  .doc-block:last-child { border-bottom: 1px solid var(--border); border-radius: 0 0 var(--radius) var(--radius); }
  .doc-tag { position: static; display: block; padding-top: 8px; opacity: 1; }
  .doc-block .doc-en { font-size: var(--fs-base); color: var(--muted); }
  .doc-weglot { padding: 4px 0 8px; border-inline: 0; background: none; }
  .doc-block[data-source="edit"] .doc-tgt::after { inset-inline-start: -10px; }
  .doc-note, .doc-conflict { margin-inline: 0; }
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


def _grid() -> str:
    """The pages x languages table. The cells say "checking" until the runtime has read the
    language; their count and status are the runtime's."""
    heads = "".join(
        f'<th scope="col" class="doc-grid-lang" data-lang="{code}">'
        f'<span class="doc-flag" aria-hidden="true">{flag}</span>{escape(S.lang_name(code))}</th>'
        for code, _endonym, _dir, flag in S.LOCALES)
    unknown = escape(t("doc.status.unknown"))
    rows = []
    for key in S.PAGE_KEYS:
        cells = "".join(
            f'<td><button type="button" class="doc-cell" data-page="{key}" data-lang="{code}" '
            f'data-status="unknown" aria-pressed="false">'
            f'<span class="doc-cell-status">{unknown}</span><span class="doc-cell-count"></span>'
            f'</button></td>'
            for code, *_ in S.LOCALES)
        rows.append(f'<tr data-page="{key}"><th scope="row" class="doc-grid-page">'
                    f'{escape(t("page." + key))}</th>{cells}</tr>')
    return (
        '    <section class="doc-gridwrap" aria-labelledby="doc-grid-title">\n'
        f'      <h2 id="doc-grid-title" class="doc-grid-title">{escape(t("doc.grid.label"))}</h2>\n'
        '      <div class="scroll-x"><table id="doc-grid" class="doc-grid">\n'
        f'        <thead><tr><th scope="col">{escape(t("doc.grid.corner"))}</th>{heads}</tr></thead>\n'
        '        <tbody>\n          ' + "\n          ".join(rows) + '\n        </tbody>\n'
        '      </table></div>\n'
        '    </section>\n'
    )


def _dom() -> str:
    """The server-rendered shell (contract section 7.2). The runtime fills what is empty here."""
    translate = escape(t("doc.translate"))
    return (
        '<main id="doc" class="doc" data-state="loading">\n'
        + _grid() +
        '    <header id="doc-bar" class="doc-bar">\n'
        '      <h1 id="doc-title" class="doc-title"></h1>\n'
        '      <div class="doc-actions">\n'
        f'        <a id="doc-rules" class="desk-btn" href="/admin/localization/rules/">{escape(t("doc.rules"))}</a>\n'
        f'        <button type="button" id="doc-translate" class="desk-btn">{translate}</button>\n'
        '      </div>\n'
        '    </header>\n'
        '    <div id="doc-banner" class="doc-banner" hidden><p id="doc-banner-text"></p>\n'
        f'      <button type="button" id="doc-banner-translate" class="desk-btn is-strong" hidden>{translate}</button></div>\n'
        '    <div class="doc-layout">\n'
        '      <nav id="doc-outline" class="doc-outline" aria-labelledby="doc-outline-title">\n'
        f'        <h2 id="doc-outline-title" class="doc-outline-title">{escape(t("doc.outline.title"))}</h2>\n'
        '        <ol id="doc-outline-list" class="doc-outline-list"></ol>\n'
        '      </nav>\n'
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
        '        <label class="doc-toggle"><input type="checkbox" id="doc-weglot">'
        f' <span>{escape(t("doc.weglot.toggle"))}</span></label>\n'
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
    assert head[-2:] == ["</head>", "<body>"], "generate_desk_page._head changed its ending"
    style = "<style>\n" + _STYLE_END.sub(r"<\\/\1", rich_css + "\n" + DOC_CSS + "\n" + export_css) + "</style>"

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
