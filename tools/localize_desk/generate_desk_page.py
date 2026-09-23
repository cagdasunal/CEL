#!/usr/bin/env python3
"""Build the Localization Desk pages under /admin/localization/.

Basecamp #451. The desk is where a reviewer works through the machine translations
Weglot currently serves for the four Vancouver pages, in each of the 8 locales.

DESIGN
------
Nothing here invents chrome. The page is `render_admin_open("localization")` +
`.dashboard-shell`, the stylesheet is the generated `/assets/css/dashboard.css`, the
popups are the `.cpw-overlay` / `.cpw-modal` component the account menu already uses,
and the buttons follow the hierarchy that modal established: one filled indigo pill
for the primary action, ghost pills for the rest, 0.5 opacity when disabled.
Desk-specific rules live in `dashboard.DESK_CSS` (monorepo SSOT -- this repo's
`tools/dashboard.py` is a vendored copy, see rules/dashboard-deploy.md) and resolve
entirely to existing :root tokens: no new colour, radius or type size.

THE MODEL: ONE DECISION PER ROW, TWO DESTINATIONS
-------------------------------------------------
A row is in exactly one of three states:

    (nothing yet)  --approve / edit-->  tray "csv"    --> Weglot import CSV
                   --re-translate --->  tray "draft"  --> Gemini batch, comes back for review

The two trays are NOT two shopping baskets competing for the same item. They are the
two ways a row can LEAVE this screen, and they are mutually exclusive: approving a
queued row takes it out of the draft tray, queueing an approved row takes it out of
the CSV tray. That is why there is one tray field rather than two booleans -- the
data model cannot represent the contradictory state, so no code has to handle it.

Editing implies approval. A reviewer who has typed the wording they want has made the
decision; making them type it and then also click Approve is a second click that can
only ever be "yes".

Each tray is sent separately and each needs its own confirmation, which is where cost
and irreversibility live:
  - the draft tray is submitted as ONE Gemini batch (50% cheaper than per-row calls,
    and one shared cached prompt prefix across the locale);
  - the CSV tray is rendered to a Weglot import file.
Neither is wired yet -- the desk is built first so the interaction can be judged
before any spend exists. The UI says so rather than pretending.

WHY ADDING TO A TRAY IS NOT A TOGGLE
------------------------------------
A toggle survives five clicks (odd -> still queued) but NOT four, and a double-click
is the commonest mis-click there is: it would have silently undone itself while
looking like it did nothing. Setting a tray is idempotent under any number of clicks.
Taking something back out is deliberate, from the tray screen, where the reviewer can
see what they are removing.

HISTORY
-------
Every state change appends to a capped local log (`cel-desk-log-<locale>`), readable
from the console with `deskLog()`. It is not surfaced in the UI -- it exists so that
"it did something strange" can be answered later.
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import (  # noqa: E402
    AUTH_SCRIPT_TAG,
    EXTERNAL_REPO_ROOT,
    render_admin_close,
    render_admin_open,
    render_favicon_tag,
    render_page_chrome,
)

# parents[1] is tools/ (that is what sys.path wants, for `import dashboard`);
# parents[2] is the repo root, which is where data/ lives.
REPO_ROOT = Path(__file__).resolve().parents[2]
UNITS_DIR = REPO_ROOT / "data" / "localize" / "units"
OUT_ROOT = EXTERNAL_REPO_ROOT / "admin" / "localization"

# Locale code -> (English name, endonym, direction). Codes are the ones the unit files
# carry (`pt`, not `pt-BR`) so the desk and the data cannot drift apart.
LOCALES = [
    ("de", "German", "Deutsch", "ltr"),
    ("fr", "French", "Français", "ltr"),
    ("es", "Spanish", "Español", "ltr"),
    ("pt", "Portuguese", "Português", "ltr"),
    ("it", "Italian", "Italiano", "ltr"),
    ("ja", "Japanese", "日本語", "ltr"),
    ("ko", "Korean", "한국어", "ltr"),
    ("ar", "Arabic", "العربية", "rtl"),
]

PAGE_LABELS = {
    "vancouver": "Vancouver",
    "vs-toronto": "Vancouver vs Toronto",
    "cost-of-studying-english": "Cost of studying English",
    "how-long-to-learn-english": "How long to learn English",
}


def load_units() -> list[dict]:
    """Merge the per-page unit files into one list, de-duplicated by unit_id.

    A unit that appears on several pages is ONE reviewable thing -- it is one Weglot
    translation unit, and approving it approves it everywhere. The page list is
    unioned so the page filter still finds it from either page.
    """
    by_id: dict[str, dict] = {}
    for path in sorted(UNITS_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        page = doc["page"]
        for unit in doc["units"]:
            if unit.get("noise") or unit.get("summary_owned"):
                continue
            uid = unit["unit_id"]
            existing = by_id.get(uid)
            if existing is None:
                unit = dict(unit)
                unit["_pages"] = {page}
                by_id[uid] = unit
            else:
                existing["_pages"].add(page)
    return list(by_id.values())


def locale_payload(code: str, units: list[dict]) -> list[dict]:
    """The rows one locale's page needs, and nothing else.

    Keys are short because this is committed and re-committed: `id/src/tgt/sec/pages`
    rather than the unit's full record, which carries type, role, markup_class and the
    other seven locales the page will never show.
    """
    out = []
    for unit in units:
        current = (unit.get("current") or {}).get(code)
        if not current:
            continue
        out.append({
            "id": unit["unit_id"],
            "src": unit["word_from"],
            "tgt": current.get("word_to", ""),
            "sec": unit.get("section") or "",
            "pages": sorted(unit["_pages"]),
        })
    return out


def _head(title: str, description: str) -> list[str]:
    return [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        f"  {AUTH_SCRIPT_TAG}",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"  <title>{escape(title)}</title>",
        f'  <meta name="description" content="{escape(description)}">',
        '  <meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">',
        '  <meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet, noimageindex">',
        f"  {render_favicon_tag()}",
        '  <link rel="stylesheet" href="/assets/css/dashboard.css">',
        "</head>",
        "<body>",
    ]


HOW_MODAL = """\
  <div class="cpw-overlay" id="how-overlay" hidden>
    <div class="cpw-modal desk-modal-wide" role="dialog" aria-modal="true" aria-labelledby="how-title">
      <h2 class="cpw-title" id="how-title">How this works</h2>
      <div class="desk-modal-body">
        <h3>What you are looking at</h3>
        <p>Every row is one translation unit &mdash; a single string Weglot serves on the
        live site. The left column is the English source, the right is what visitors in
        this language see today. All of it is machine translation.</p>

        <h3>Every row leaves in one of two directions</h3>
        <ul>
          <li><strong>Approve</strong> &mdash; the wording is right. The row joins the
          <em>ready for CSV</em> tray, which becomes the Weglot import file.</li>
          <li><strong>Edit</strong> &mdash; type the wording you want. Saving counts as
          approving, so the row joins the same tray with your text instead.</li>
          <li><strong>Re-translate</strong> &mdash; the wording is wrong and you would
          like the machine to try again. The row joins the <em>re-translate</em> tray.</li>
        </ul>
        <p>A row can only be in one tray. Approving something you had queued takes it
        out of the re-translate tray, and vice versa &mdash; you never have to
        remember to undo the other one.</p>

        <h3>Working in bulk</h3>
        <p>Tick the box on any row, or the box in the header to take everything
        currently shown. A bar appears at the bottom with the same two actions applied
        to the whole selection. Filter first &mdash; <em>Show: Needs review</em> plus a
        search term, then select all &mdash; and a few hundred rows go quickly.</p>

        <h3>The trays are sent separately</h3>
        <p>Nothing leaves this screen on its own. Each tray has its own review screen
        where you can take rows back out, and its own confirmation. The re-translate
        tray goes to the machine as one batch; the CSV tray becomes a file you import
        into Weglot. Clicking a tray button repeatedly cannot send anything twice.</p>

        <h3>When the machine sends drafts back</h3>
        <p>Rows you queued come back marked <em>needs your review</em>, and that is where
        this page opens &mdash; you see what changed while you were away without looking
        for it. Each one shows the English, what is live today, and the new suggestion
        side by side, so you are never accepting something without seeing what it
        replaces. <strong>Accept</strong> takes it, <strong>Edit</strong> takes your
        wording instead, and <strong>Reject</strong> sends it back to be tried again
        &mdash; remembering what was refused, so you do not get the same suggestion
        twice.</p>

        <h3>Your decisions are kept in this browser</h3>
        <p>They apply instantly and survive a reload, but not a different computer.
        <strong>Download a backup</strong> writes them to a file you can keep. You never
        need to load anything back by hand &mdash; machine drafts arrive on their own.</p>
        <p>Sending the batch and building the CSV are not wired up yet &mdash; the desk
        is being built before the machine translation is connected, so the review flow
        can be judged first.</p>

        <h3>Keyboard</h3>
        <p><code>J</code> / <code>K</code> move between rows, <code>A</code> approves,
        <code>R</code> queues a re-translation, <code>E</code> edits, <code>X</code>
        ticks the box, <code>Esc</code> closes this box.</p>
      </div>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-save" id="how-close">Got it</button>
      </div>
    </div>
  </div>
"""

TRAY_MODAL = """\
  <div class="cpw-overlay" id="tray-overlay" hidden>
    <div class="cpw-modal desk-modal-wide" role="dialog" aria-modal="true" aria-labelledby="tray-title">
      <h2 class="cpw-title" id="tray-title"></h2>
      <div class="desk-modal-body">
        <p id="tray-summary"></p>
        <ul class="desk-queue-list" id="tray-list"></ul>
        <p class="desk-notice" id="tray-notice"></p>
      </div>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-cancel" id="tray-empty">Empty this tray</button>
        <button type="button" class="cpw-btn cpw-save" id="tray-close">Close</button>
      </div>
    </div>
  </div>
"""


def render_index(units: list[dict]) -> str:
    total = len(units)
    parts = _head(
        "Localization Desk — English College",
        "Review the machine translations served on the four Vancouver pages, per locale.",
    )
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    parts.append(
        render_page_chrome(
            "LOCALIZATION DESK",
            "Review what Weglot serves on the four Vancouver pages, one language at a time.",
        )
    )
    parts.append('    <main class="dashboard-main">')
    parts.append('      <section class="status status-ok">')
    parts.append('        <p class="status-label">Ready for review</p>')
    parts.append(
        f"        <p><strong>{total}</strong> reviewable units across "
        f"<strong>{len(PAGE_LABELS)}</strong> pages and <strong>{len(LOCALES)}</strong> "
        "languages. Pick a language to start.</p>"
    )
    parts.append("      </section>")

    parts.append('      <div class="desk-locales">')
    for code, name, endonym, _dir in LOCALES:
        have = sum(1 for u in units if (u.get("current") or {}).get(code))
        parts.append(
            f'        <div class="desk-locale-card" data-locale="{code}" data-total="{have}">'
        )
        parts.append(
            f'          <a class="desk-locale-open" href="/admin/localization/{code}/">'
            f'<span class="desk-locale-name">{escape(name)}</span></a>'
        )
        parts.append(
            f'          <p class="desk-locale-sub"><bdi>{escape(endonym)}</bdi> '
            f'&middot; <span class="mono">{code}</span></p>'
        )
        parts.append('          <div class="desk-meter" role="presentation">')
        parts.append('            <div class="desk-meter-fill" style="width:0%"></div>')
        parts.append("          </div>")
        parts.append(
            f'          <p class="desk-locale-stat">{have} units &mdash; not started</p>'
        )
        parts.append('          <div class="desk-trays"></div>')
        parts.append("        </div>")
    parts.append("      </div>")

    parts.append(
        '      <p class="subtle">Nothing on these pages writes to the live site. '
        "Approving records a decision; it does not re-publish anything.</p>"
    )
    parts.append("    </main>")
    parts.append("  </div>")
    parts.append(_index_js())
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _index_js() -> str:
    """Fill each card's progress and tray chips from that locale's saved decisions.

    The server cannot know any of this -- decisions live in the reviewer's browser --
    so the card ships with the honest static number and this upgrades it in place.
    Without it the meter showed translation COVERAGE, which is 100% for every locale
    because Weglot machine-translates everything: a full bar that means nothing.

    The chips link straight into the matching filter, and "undo" empties that tray for
    that locale, so the index is a place to fix a mistake and not only to read one.
    """
    return """\
  <script>
  (function () {
    'use strict';
    function read(code) {
      try { return JSON.parse(localStorage.getItem('cel-desk-' + code) || '{}') || {}; }
      catch (e) { return {}; }
    }
    function chip(cls, label, href) {
      var a = document.createElement(href ? 'a' : 'span');
      a.className = 'desk-tray ' + cls;
      if (href) a.href = href;
      a.textContent = label;
      return a;
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-locale]'), function (card) {
      var code = card.getAttribute('data-locale');
      var total = parseInt(card.getAttribute('data-total'), 10) || 0;
      var st = read(code);
      var csv = 0, draft = 0, proposed = 0;
      for (var k in st) {
        if (!st[k]) continue;
        if (st[k].proposed && st[k].proposed.text != null) { proposed++; continue; }
        if (st[k].tray === 'csv') csv++;
        else if (st[k].tray === 'draft') draft++;
      }
      var done = csv + draft;
      var pct = total ? Math.round(100 * done / total) : 0;
      card.querySelector('.desk-meter-fill').style.width = pct + '%';
      card.querySelector('.desk-locale-stat').textContent =
        done ? (done + ' of ' + total + ' decided (' + pct + '%)')
             : (total + ' units — not started');

      var trays = card.querySelector('.desk-trays');
      trays.textContent = '';
      var base = '/admin/localization/' + code + '/';
      if (!csv && !draft && !proposed) {
        trays.appendChild(chip('desk-tray-none', 'nothing queued', null));
        return;
      }
      // Waiting-on-you comes first: it is the only chip that is a request.
      if (proposed) trays.appendChild(chip('desk-tray-proposed', proposed + ' need your review', base + '?show=proposed'));
      if (csv) trays.appendChild(chip('desk-tray-csv', csv + ' ready for CSV', base + '?show=csv'));
      if (draft) trays.appendChild(chip('desk-tray-draft', draft + ' to re-translate', base + '?show=draft'));

      var undo = document.createElement('button');
      undo.type = 'button';
      undo.className = 'desk-btn';
      undo.textContent = 'Undo all';
      undo.addEventListener('click', function () {
        if (!window.confirm('Clear every decision recorded for ' + code + ' in this browser?')) return;
        try { localStorage.removeItem('cel-desk-' + code); } catch (e) {}
        location.reload();
      });
      trays.appendChild(undo);
    });
  })();
  </script>
"""


def render_locale(code: str, name: str, endonym: str, direction: str,
                  units: list[dict]) -> str:
    rows = [u for u in units if (u.get("current") or {}).get(code)]
    parts = _head(
        f"{name} — Localization Desk — English College",
        f"Review the {name} machine translations served on the four Vancouver pages.",
    )
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    parts.append(
        render_page_chrome(
            f"LOCALIZATION DESK &middot; {escape(name.upper())}",
            f"<bdi>{escape(endonym)}</bdi> &mdash; {len(rows)} units. "
            "Decisions apply instantly and stay in this browser.",
        )
    )

    # Toolbar
    parts.append('    <div class="controls">')
    parts.append('      <div class="desk-toolbar">')
    parts.append('        <label class="desk-field">Page')
    parts.append('          <select class="desk-select" id="f-page">')
    parts.append('            <option value="">All pages</option>')
    for slug, label in PAGE_LABELS.items():
        parts.append(f'            <option value="{slug}">{escape(label)}</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append('        <label class="desk-field">Show')
    parts.append('          <select class="desk-select" id="f-state">')
    parts.append('            <option value="proposed">Needs your review (new drafts)</option>')
    parts.append('            <option value="todo">Not yet decided</option>')
    parts.append('            <option value="">Everything</option>')
    parts.append('            <option value="csv">Ready for CSV</option>')
    parts.append('            <option value="draft">To re-translate</option>')
    parts.append('            <option value="edited">Edited by me</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append('        <label class="desk-field">Search')
    parts.append('          <input class="desk-select" id="f-q" type="search" '
                 'placeholder="source or translation" autocomplete="off">')
    parts.append("        </label>")
    parts.append('        <span class="desk-toolbar-spacer"></span>')
    # No Import control: the reviewer never imports decisions. Machine drafts arrive
    # through the batch ingest, not through a file picker. Download stays, as a backup
    # of work that otherwise exists only in one browser.
    parts.append('        <button type="button" class="desk-btn" id="io-export">Download a backup</button>')
    parts.append('        <button type="button" class="desk-btn" id="how-open">How this works</button>')
    parts.append("      </div>")
    parts.append('      <p class="subtle" id="count-line"></p>')
    parts.append("    </div>")

    parts.append('    <main class="dashboard-main">')
    parts.append('      <div class="scroll-x">')
    parts.append('        <table class="doc-table desk-table">')
    parts.append("          <thead><tr>")
    parts.append('            <th scope="col" class="desk-col-pick">'
                 '<input type="checkbox" class="desk-pick" id="pick-all" '
                 'aria-label="Select every row shown"></th>')
    parts.append('            <th scope="col">English source</th>')
    parts.append(f'            <th scope="col">{escape(name)} (live today)</th>')
    parts.append('            <th scope="col" class="desk-col-state">State</th>')
    parts.append('            <th scope="col" class="desk-col-act">Decision</th>')
    parts.append("          </tr></thead>")
    # Rows are built in the browser from units.json, not baked in here. Server-rendering
    # 990 rows x 8 locales produced 11 MB of HTML that git had to store again on EVERY
    # regeneration; the same content as JSON is ~292 KB per locale and the page shell
    # stays ~31 KB.
    parts.append('          <tbody id="desk-body"></tbody>')
    parts.append("        </table>")
    parts.append('        <p class="empty" id="no-rows" hidden>Nothing matches these filters.</p>')
    parts.append("      </div>")
    parts.append("    </main>")

    # Sticky two-zone action bar
    parts.append('    <div class="desk-savebar" id="savebar" hidden>')
    parts.append('      <div class="desk-bar-row" id="bar-select" hidden>')
    parts.append('        <p class="desk-savebar-text"><strong id="sel-count">0</strong> selected</p>')
    parts.append('        <span class="desk-savebar-spacer"></span>')
    parts.append('        <button type="button" class="desk-btn" id="bulk-clear">Clear selection</button>')
    parts.append('        <button type="button" class="desk-btn" id="bulk-draft">Re-translate these</button>')
    parts.append('        <button type="button" class="desk-btn is-primary" id="bulk-approve">Approve these</button>')
    parts.append("      </div>")
    parts.append('      <div class="desk-bar-row" id="bar-trays" hidden>')
    parts.append('        <p class="desk-savebar-text" id="tray-line"></p>')
    parts.append('        <span class="desk-savebar-spacer"></span>')
    parts.append('        <button type="button" class="desk-btn" id="open-draft">Review re-translate tray</button>')
    parts.append('        <button type="button" class="desk-btn" id="open-csv">Review CSV tray</button>')
    parts.append("      </div>")
    parts.append("    </div>")

    parts.append("  </div>")
    parts.append(HOW_MODAL)
    parts.append(TRAY_MODAL)
    parts.append(_desk_js(code, direction == "rtl"))
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _desk_js(code: str, rtl: bool) -> str:
    """Per-locale desk behaviour. IIFE, no globals but the debug hook, no framework."""
    return """\
  <script>
  (function () {
    'use strict';
    var CODE = '__CODE__';
    var KEY = 'cel-desk-' + CODE;
    var LOGKEY = 'cel-desk-log-' + CODE;
    var LOG_CAP = 4000;
    var RTL = __RTL__;

    var state = {};
    try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
    var hist = [];
    try { hist = JSON.parse(localStorage.getItem(LOGKEY) || '[]') || []; } catch (e) { hist = []; }

    var body = document.getElementById('desk-body');
    var rows = [];
    var picked = Object.create(null);
    var lastPicked = -1;
    var cursor = -1;

    var fPage = document.getElementById('f-page');
    var fState = document.getElementById('f-state');
    var fQ = document.getElementById('f-q');
    var countLine = document.getElementById('count-line');
    var noRows = document.getElementById('no-rows');
    var savebar = document.getElementById('savebar');
    var barSelect = document.getElementById('bar-select');
    var barTrays = document.getElementById('bar-trays');
    var trayLine = document.getElementById('tray-line');
    var selCount = document.getElementById('sel-count');
    var pickAll = document.getElementById('pick-all');

    // ── Persistence + history ──────────────────────────────────────────
    function persist() {
      try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
    }
    function note(action, uid, from, to) {
      // Capped so a long session cannot fill the origin's storage quota and start
      // throwing on the writes that actually matter.
      hist.push({ t: new Date().toISOString(), a: action, u: uid || null, f: from || null, x: to || null });
      if (hist.length > LOG_CAP) hist = hist.slice(hist.length - LOG_CAP);
      try { localStorage.setItem(LOGKEY, JSON.stringify(hist)); } catch (e) {}
    }
    function rec(uid) { return state[uid] || (state[uid] = {}); }

    // Not surfaced in the UI on purpose; it exists so "it did something strange" can
    // be answered after the fact.
    window.deskLog = function (n) { return hist.slice(-(n || 200)); };
    window.deskState = function () { return JSON.parse(JSON.stringify(state)); };

    function setTray(uid, tray, why) {
      var s = rec(uid);
      var from = s.tray || null;
      if (from === tray) return false;
      // One tray field, not two booleans: the contradictory state (queued AND
      // approved) cannot be represented, so nothing downstream has to resolve it.
      if (tray) s.tray = tray; else delete s.tray;
      note(why || ('tray:' + (tray || 'none')), uid, from, tray || null);
      return true;
    }

    // ── Row construction ───────────────────────────────────────────────
    // DOM APIs only -- never by assigning markup. The source and translation are
    // arbitrary site copy, and textContent cannot be talked into executing any of it.
    // (Spelling out the banned property here would trip the test that greps this
    // script for it, which is the point of that test.)
    function buildRows(units) {
      var frag = document.createDocumentFragment();
      units.forEach(function (u) {
        var tr = document.createElement('tr');
        tr.className = 'desk-row';
        tr.setAttribute('data-uid', u.id);
        tr.setAttribute('data-pages', u.pages.join(' '));
        tr.setAttribute('data-q', (u.src + ' ' + u.tgt).toLowerCase());

        var tdPick = document.createElement('td');
        tdPick.className = 'desk-col-pick';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'desk-pick';
        cb.setAttribute('data-pick', '');
        cb.setAttribute('aria-label', 'Select this row');
        tdPick.appendChild(cb);

        var tdSrc = document.createElement('td');
        tdSrc.className = 'desk-src';
        if (u.sec) {
          var sec = document.createElement('span');
          sec.className = 'desk-sec';
          sec.textContent = u.sec;
          tdSrc.appendChild(sec);
        }
        var srcText = document.createElement('span');
        srcText.className = 'desk-srctext';
        srcText.textContent = u.src;
        tdSrc.appendChild(srcText);

        var tdTgt = document.createElement('td');
        tdTgt.className = 'desk-tgt';
        if (RTL) tdTgt.setAttribute('dir', 'rtl');
        var live = document.createElement('span');
        live.className = 'desk-live';
        live.textContent = u.tgt;
        var prop = document.createElement('div');
        prop.className = 'desk-proposed';
        prop.hidden = true;
        var propLabel = document.createElement('span');
        propLabel.className = 'desk-proposed-label';
        propLabel.textContent = 'proposed';
        var propText = document.createElement('span');
        propText.className = 'desk-proposed-text';
        prop.appendChild(propLabel); prop.appendChild(propText);
        var ta = document.createElement('textarea');
        ta.className = 'desk-edit';
        ta.hidden = true;
        ta.setAttribute('aria-label', 'Your wording');
        ta.value = u.tgt;
        tdTgt.appendChild(live);
        tdTgt.appendChild(prop);
        tdTgt.appendChild(ta);

        var tdState = document.createElement('td');
        tdState.className = 'desk-col-state';
        var badge = document.createElement('span');
        badge.className = 'desk-state badge-partial';
        badge.textContent = 'unreviewed';
        tdState.appendChild(badge);

        var tdAct = document.createElement('td');
        tdAct.className = 'desk-col-act';
        var acts = document.createElement('div');
        acts.className = 'desk-actions';
        // Ghost, not filled. 990 rows means 990 buttons, and a filled primary on each
        // turns the single-primary rule into wallpaper. Indigo on a row means STATE.
        [['approve', 'Approve'], ['edit', 'Edit'], ['queue', 'Re-translate'], ['reject', 'Reject']]
          .forEach(function (pair) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'desk-btn';
            b.setAttribute('data-act', pair[0]);
            b.textContent = pair[1];
            acts.appendChild(b);
          });
        tdAct.appendChild(acts);

        tr.appendChild(tdPick); tr.appendChild(tdSrc); tr.appendChild(tdTgt);
        tr.appendChild(tdState); tr.appendChild(tdAct);
        frag.appendChild(tr);
      });
      body.appendChild(frag);
      rows = Array.prototype.slice.call(body.querySelectorAll('.desk-row'));
    }

    // ── Painting ───────────────────────────────────────────────────────
    function paint(tr) {
      var uid = tr.getAttribute('data-uid');
      var s = state[uid] || {};
      var proposed = s.proposed && s.proposed.text != null;
      var badge = tr.querySelector('.desk-state');
      var label = 'unreviewed', cls = 'badge-partial';
      if (proposed) { label = 'needs your review'; cls = 'badge-proposed'; }
      else if (s.tray === 'csv') { label = s.text != null ? 'edited' : 'approved'; cls = 'badge-ok'; }
      else if (s.tray === 'draft') { label = 'to re-translate'; cls = 'badge-failed'; }
      badge.className = 'desk-state ' + cls;
      badge.textContent = label;
      tr.classList.toggle('is-done', !proposed && s.tray === 'csv');
      tr.classList.toggle('is-proposed', !!proposed);
      tr.classList.toggle('is-picked', !!picked[uid]);

      // A proposal is a THIRD text, shown next to what it would replace. Accepting
      // without seeing what is being replaced is not review, so the live wording
      // stays on screen rather than being swapped out underneath the reviewer.
      var box = tr.querySelector('.desk-proposed');
      if (proposed) {
        box.hidden = false;
        box.querySelector('.desk-proposed-text').textContent = s.proposed.text;
      } else {
        box.hidden = true;
      }

      var acts = tr.querySelector('.desk-actions');
      acts.classList.toggle('is-proposal', !!proposed);

      var bApprove = tr.querySelector('[data-act="approve"]');
      var bQueue = tr.querySelector('[data-act="queue"]');
      var bReject = tr.querySelector('[data-act="reject"]');
      bReject.hidden = !proposed;

      if (proposed) {
        // On a proposal the two existing buttons change meaning, not position:
        // Approve accepts the machine's wording, Re-translate is replaced by Reject.
        bApprove.classList.remove('is-on');
        bApprove.textContent = 'Accept';
        bApprove.disabled = false;
        bQueue.hidden = true;
      } else {
        bQueue.hidden = false;
        bApprove.classList.toggle('is-on', s.tray === 'csv');
        bApprove.textContent = s.tray === 'csv' ? 'Approved' : 'Approve';
        bApprove.disabled = s.tray === 'csv';
        bQueue.classList.toggle('is-on', s.tray === 'draft');
        bQueue.textContent = s.tray === 'draft' ? 'Queued' : 'Re-translate';
        // Nothing left to do on a row already in that tray: adding again is a no-op,
        // and taking it back out belongs on the tray screen.
        bQueue.disabled = s.tray === 'draft';
      }

      var cb = tr.querySelector('[data-pick]');
      if (cb) cb.checked = !!picked[uid];

      if (!proposed && s.text != null) {
        var live = tr.querySelector('.desk-live');
        if (live.textContent !== s.text) live.textContent = s.text;
      }
    }

    function counts() {
      var csv = 0, draft = 0, proposed = 0;
      for (var k in state) {
        if (!state[k]) continue;
        if (state[k].proposed && state[k].proposed.text != null) { proposed++; continue; }
        if (state[k].tray === 'csv') csv++;
        else if (state[k].tray === 'draft') draft++;
      }
      return { csv: csv, draft: draft, proposed: proposed };
    }

    function pickedIds() { return Object.keys(picked); }

    function paintBar() {
      var c = counts();
      var n = pickedIds().length;
      selCount.textContent = n;
      barSelect.hidden = n === 0;
      barTrays.hidden = (c.csv + c.draft + c.proposed) === 0;
      savebar.hidden = barSelect.hidden && barTrays.hidden;
      var bits = [];
      if (c.proposed) bits.push(c.proposed + ' need your review');
      if (c.csv) bits.push(c.csv + ' ready for CSV');
      if (c.draft) bits.push(c.draft + ' to re-translate');
      trayLine.textContent = bits.join('  ·  ');
      document.getElementById('open-csv').disabled = !c.csv;
      document.getElementById('open-draft').disabled = !c.draft;
    }

    // ── Filters ────────────────────────────────────────────────────────
    function matches(tr) {
      var s = state[tr.getAttribute('data-uid')] || {};
      var p = fPage.value;
      if (p && (' ' + tr.getAttribute('data-pages') + ' ').indexOf(' ' + p + ' ') === -1) return false;
      var want = fState.value;
      var isProposed = !!(s.proposed && s.proposed.text != null);
      if (want === 'proposed' && !isProposed) return false;
      // A proposal is never "done", whatever tray it came from.
      if (want === 'todo' && (s.tray && !isProposed)) return false;
      if (want === 'csv' && s.tray !== 'csv') return false;
      if (want === 'draft' && s.tray !== 'draft') return false;
      if (want === 'edited' && s.text == null) return false;
      var q = fQ.value.trim().toLowerCase();
      if (q && tr.getAttribute('data-q').indexOf(q) === -1) return false;
      return true;
    }

    function shown() { return rows.filter(function (tr) { return !tr.hidden; }); }

    function applyFilters() {
      rows.forEach(function (tr) { tr.hidden = !matches(tr); });
      var vis = shown();
      noRows.hidden = vis.length !== 0;
      countLine.textContent = vis.length + ' of ' + rows.length + ' units shown';
      syncPickAll();
      if (cursor >= 0 && rows[cursor] && rows[cursor].hidden) focusRow(-1);
    }

    function syncPickAll() {
      var vis = shown();
      var on = vis.filter(function (tr) { return picked[tr.getAttribute('data-uid')]; }).length;
      pickAll.checked = vis.length > 0 && on === vis.length;
      pickAll.indeterminate = on > 0 && on < vis.length;
    }

    // ── Actions ────────────────────────────────────────────────────────
    function apply(tr, what) {
      var uid = tr.getAttribute('data-uid');
      var st = state[uid] || {};
      if (what === 'approve') {
        if (st.proposed && st.proposed.text != null) {
          // Accepting a proposal takes the machine's wording as the decision and
          // clears the proposal, so the row leaves PROPOSED for good.
          rec(uid).text = st.proposed.text;
          delete rec(uid).proposed;
          note('accept-proposal', uid, null, null);
          setTray(uid, 'csv', 'accept');
          persist(); paint(tr);
          return;
        }
        if (setTray(uid, 'csv', 'approve')) { persist(); paint(tr); }
      } else if (what === 'reject') {
        if (!st.proposed) return;
        // Read the text BEFORE deleting: `st` is the same object as state[uid], so
        // touching st.proposed afterwards throws and the handler dies half-done --
        // rejected recorded in memory, nothing persisted, nothing repainted.
        var refused = st.proposed.text;
        // A rejection is information the next batch needs, not just a deletion: the
        // refused wording is kept so the draft can be told what not to produce again.
        var s2 = rec(uid);
        s2.rejected = (s2.rejected || []).concat([refused]);
        delete s2.proposed;
        note('reject-proposal', uid, refused, null);
        setTray(uid, 'draft', 'reject');
        persist(); paint(tr);
      } else if (what === 'queue') {
        // ADD, never toggle -- see the module docstring. Idempotent under any number
        // of clicks; removal is deliberate, from the tray screen.
        if (setTray(uid, 'draft', 'queue')) { persist(); paint(tr); }
      } else if (what === 'edit') {
        var ta = tr.querySelector('.desk-edit');
        var live = tr.querySelector('.desk-live');
        var opening = ta.hidden;
        ta.hidden = !opening;
        live.hidden = opening;
        if (opening) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
        return;
      }
    }

    body.addEventListener('click', function (ev) {
      var cb = ev.target.closest('[data-pick]');
      if (cb) {
        var tr = cb.closest('.desk-row');
        var i = rows.indexOf(tr);
        if (ev.shiftKey && lastPicked >= 0) {
          var a = Math.min(lastPicked, i), b = Math.max(lastPicked, i);
          for (var k = a; k <= b; k++) {
            if (rows[k].hidden) continue;
            if (cb.checked) picked[rows[k].getAttribute('data-uid')] = 1;
            else delete picked[rows[k].getAttribute('data-uid')];
            paint(rows[k]);
          }
        } else {
          if (cb.checked) picked[tr.getAttribute('data-uid')] = 1;
          else delete picked[tr.getAttribute('data-uid')];
          paint(tr);
        }
        lastPicked = i;
        paintBar(); syncPickAll();
        return;
      }
      var btn = ev.target.closest('[data-act]');
      if (!btn) return;
      var row = btn.closest('.desk-row');
      focusRow(rows.indexOf(row));
      apply(row, btn.getAttribute('data-act'));
      paintBar();
      applyFilters();
    });

    body.addEventListener('change', function (ev) {
      var ta = ev.target.closest('.desk-edit');
      if (!ta) return;
      var tr = ta.closest('.desk-row');
      var uid = tr.getAttribute('data-uid');
      var live = tr.querySelector('.desk-live');
      var val = ta.value.trim();
      var s = rec(uid);
      if (val && val !== live.textContent) {
        s.text = val;
        note('edit', uid, null, null);
        // Typing the wording you want IS the decision; a separate Approve click
        // afterwards could only ever be "yes".
        setTray(uid, 'csv', 'edit-approve');
      } else if (!val) {
        delete s.text;
        note('edit-cleared', uid, null, null);
      }
      persist(); paint(tr); paintBar(); applyFilters();
    });

    pickAll.addEventListener('change', function () {
      shown().forEach(function (tr) {
        var uid = tr.getAttribute('data-uid');
        if (pickAll.checked) picked[uid] = 1; else delete picked[uid];
        paint(tr);
      });
      paintBar(); syncPickAll();
    });

    function bulk(tray, why) {
      var ids = pickedIds();
      if (!ids.length) return;
      var changed = 0;
      ids.forEach(function (uid) { if (setTray(uid, tray, why)) changed++; });
      note(why + ':bulk', null, String(ids.length), String(changed));
      picked = Object.create(null);
      lastPicked = -1;
      persist();
      rows.forEach(paint);
      paintBar(); applyFilters();
    }
    document.getElementById('bulk-approve').addEventListener('click', function () { bulk('csv', 'approve'); });
    document.getElementById('bulk-draft').addEventListener('click', function () { bulk('draft', 'queue'); });
    document.getElementById('bulk-clear').addEventListener('click', function () {
      picked = Object.create(null); lastPicked = -1;
      rows.forEach(paint); paintBar(); syncPickAll();
    });

    // ── Keyboard ───────────────────────────────────────────────────────
    function focusRow(i) {
      if (cursor >= 0 && rows[cursor]) rows[cursor].style.outline = '';
      cursor = i;
      if (i < 0 || !rows[i]) return;
      rows[i].style.outline = '2px solid var(--accent)';
      rows[i].scrollIntoView({ block: 'nearest' });
    }
    function step(dir) {
      var i = cursor;
      for (var n = 0; n < rows.length; n++) {
        i += dir;
        if (i < 0 || i >= rows.length) return;
        if (!rows[i].hidden) { focusRow(i); return; }
      }
    }
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { closeOverlays(); return; }
      var t = ev.target.tagName;
      if (t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      var k = ev.key.toLowerCase();
      if (k === 'j') { ev.preventDefault(); step(1); return; }
      if (k === 'k') { ev.preventDefault(); step(-1); return; }
      if (cursor < 0 || !rows[cursor]) return;
      var tr = rows[cursor];
      if (k === 'a') { ev.preventDefault(); apply(tr, 'approve'); paintBar(); applyFilters(); }
      else if (k === 'r') { ev.preventDefault(); apply(tr, 'queue'); paintBar(); applyFilters(); }
      else if (k === 'e') { ev.preventDefault(); apply(tr, 'edit'); }
      else if (k === 'x') {
        ev.preventDefault();
        var uid = tr.getAttribute('data-uid');
        if (picked[uid]) delete picked[uid]; else picked[uid] = 1;
        lastPicked = cursor;
        paint(tr); paintBar(); syncPickAll();
      }
    });

    // ── Overlays ───────────────────────────────────────────────────────
    var howOverlay = document.getElementById('how-overlay');
    var trayOverlay = document.getElementById('tray-overlay');
    var trayList = document.getElementById('tray-list');
    var openTray = null;

    function closeOverlays() { howOverlay.hidden = true; trayOverlay.hidden = true; }
    document.getElementById('how-open').addEventListener('click', function () {
      howOverlay.hidden = false;
      document.getElementById('how-close').focus();
    });
    document.getElementById('how-close').addEventListener('click', closeOverlays);
    document.getElementById('tray-close').addEventListener('click', closeOverlays);
    [howOverlay, trayOverlay].forEach(function (ov) {
      ov.addEventListener('click', function (ev) { if (ev.target === ov) closeOverlays(); });
    });

    var TRAY_COPY = {
      draft: {
        title: 'Re-translate tray',
        one: 'unit is queued for a fresh machine draft.',
        many: 'units are queued for a fresh machine draft.',
        notice: 'Sending is not connected yet. When it is, this tray goes to the ' +
                'machine as ONE batch — cheaper than a call per row, and it will ask ' +
                'you to confirm the count and the estimated cost first.'
      },
      csv: {
        title: 'CSV tray',
        one: 'unit is approved and ready for the Weglot import file.',
        many: 'units are approved and ready for the Weglot import file.',
        notice: 'Building the file is not connected yet. When it is, this tray becomes ' +
                'one Weglot import CSV, and you confirm before it is written. The ' +
                'import into Weglot stays a manual step.'
      }
    };

    function paintTray() {
      if (!openTray) return;
      var copy = TRAY_COPY[openTray];
      var c = counts();
      var n = openTray === 'csv' ? c.csv : c.draft;
      document.getElementById('tray-title').textContent = copy.title;
      document.getElementById('tray-summary').textContent =
        n + ' ' + (n === 1 ? copy.one : copy.many);
      document.getElementById('tray-notice').textContent = copy.notice;
      trayList.textContent = '';
      rows.forEach(function (tr) {
        var uid = tr.getAttribute('data-uid');
        if (!state[uid] || state[uid].tray !== openTray) return;
        var li = document.createElement('li');
        li.className = 'desk-queue-item';
        var span = document.createElement('span');
        span.className = 'desk-queue-src';
        span.textContent = tr.querySelector('.desk-srctext').textContent;
        var rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'desk-btn';
        rm.textContent = 'Remove';
        rm.addEventListener('click', function () {
          setTray(uid, null, 'remove');
          persist(); paint(tr); paintBar(); applyFilters(); paintTray();
        });
        li.appendChild(span); li.appendChild(rm);
        trayList.appendChild(li);
      });
      if (!n) closeOverlays();
    }

    function showTray(which) {
      openTray = which;
      paintTray();
      trayOverlay.hidden = false;
      document.getElementById('tray-close').focus();
    }
    document.getElementById('open-draft').addEventListener('click', function () { showTray('draft'); });
    document.getElementById('open-csv').addEventListener('click', function () { showTray('csv'); });
    document.getElementById('tray-empty').addEventListener('click', function () {
      if (!openTray) return;
      if (!window.confirm('Take every row out of the ' + TRAY_COPY[openTray].title + '?')) return;
      var n = 0;
      for (var k in state) {
        if (state[k] && state[k].tray === openTray) { setTray(k, null, 'empty-tray'); n++; }
      }
      note('empty-tray', null, openTray, String(n));
      persist(); rows.forEach(paint); paintBar(); applyFilters(); closeOverlays();
    });

    // ── Export / import ────────────────────────────────────────────────
    // Decisions live in this browser, which means they do not survive a different
    // machine and cannot be read by the batch or CSV steps. This file is the handoff:
    // the reviewer exports it, it goes into the repo, and the pipeline consumes it.
    // A one-click save would need the dispatch Worker's workflow allowlist extended
    // and the Worker redeployed -- a security boundary, deliberately not touched here.
    function exportDecisions() {
      var c = counts();
      var doc = {
        schema: 'cel-localization-desk/1',
        locale: CODE,
        exported_at: new Date().toISOString(),
        counts: { csv: c.csv, draft: c.draft, total_rows: rows.length },
        decisions: state,
        history: hist
      };
      var blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'localization-' + CODE + '-decisions.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      note('export', null, String(c.csv + c.draft), null);
    }

    // The INGEST seam, not a UI affordance. Machine drafts land here when the batch
    // returns; `deskIngest()` is the same door, callable from the console while the
    // batch step is being built. The reviewer has no import button -- they never
    // import decisions, and a file picker that says otherwise invites the mistake.
    function ingest(doc) {
      if (!doc || doc.schema !== 'cel-localization-desk/1') return { ok: false, why: 'not a desk document' };
      // A document for another locale would attach its ids to strings that mean
      // something different here.
      if (doc.locale !== CODE) return { ok: false, why: 'document is for ' + doc.locale + ', this desk is ' + CODE };
      var incoming = doc.decisions || {};
      var n = 0;
      for (var uid in incoming) {
        if (!incoming[uid]) continue;
        var s = rec(uid);
        // Merge, never replace: a returning batch carries proposals for the rows it
        // was asked about, and must not erase decisions made on every other row.
        if (incoming[uid].proposed) { s.proposed = incoming[uid].proposed; n++; }
        if (incoming[uid].tray) s.tray = incoming[uid].tray;
      }
      note('ingest', null, String(n), doc.exported_at || null);
      persist();
      rows.forEach(paint); paintBar(); applyFilters();
      return { ok: true, proposals: n };
    }
    window.deskIngest = ingest;

    document.getElementById('io-export').addEventListener('click', exportDecisions);

    [fPage, fState].forEach(function (el) { el.addEventListener('change', applyFilters); });
    fQ.addEventListener('input', applyFilters);

    // ── Boot ───────────────────────────────────────────────────────────
    fetch('units.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (units) {
        buildRows(units);
        // ?show= lets the locale index link straight into a tray.
        var want = new URLSearchParams(location.search).get('show');
        if (want && ['todo', 'csv', 'draft', 'edited', 'proposed', ''].indexOf(want) !== -1) {
          fState.value = want;
        } else if (counts().proposed > 0) {
          // The reviewer coming back after a batch is asking "what did the machine do
          // while I was away", not "where was I". Land them on exactly those rows.
          fState.value = 'proposed';
        }
        rows.forEach(paint);
        paintBar();
        applyFilters();
        note('load', null, String(units.length), null);
      })
      .catch(function (err) {
        // Say so in the page. A desk that silently shows zero rows looks like
        // "nothing to review", which is the opposite of what has happened.
        countLine.textContent = 'Could not load the units (' + err.message + ').';
        countLine.className = 'subtle desk-status is-error';
        noRows.hidden = true;
        note('load-failed', null, err.message, null);
      });
  })();
  </script>
""".replace("__CODE__", code).replace("__RTL__", "true" if rtl else "false")


def main() -> int:
    if not UNITS_DIR.is_dir():
        print(f"ERROR: no unit data at {UNITS_DIR}", file=sys.stderr)
        return 2
    units = load_units()
    # A desk with no rows is not a desk. The first run of this generator wrote eight
    # complete, correctly-styled, entirely EMPTY pages because REPO_ROOT pointed one
    # directory too high and Path.glob on a missing directory returns nothing --
    # which looks exactly like "no units matched".
    if not units:
        print(f"ERROR: 0 reviewable units found in {UNITS_DIR} — refusing to write empty pages",
              file=sys.stderr)
        return 2
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    written = []

    index = OUT_ROOT / "index.html"
    index.write_text(render_index(units), encoding="utf-8")
    written.append(index)

    for code, name, endonym, direction in LOCALES:
        out_dir = OUT_ROOT / code
        out_dir.mkdir(parents=True, exist_ok=True)

        payload = locale_payload(code, units)
        data_file = out_dir / "units.json"
        # separators= keeps the committed artefact compact; git stores this on every
        # regeneration, so the difference between 300 KB and 400 KB is not cosmetic.
        data_file.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        written.append(data_file)

        target = out_dir / "index.html"
        target.write_text(render_locale(code, name, endonym, direction, units), encoding="utf-8")
        written.append(target)

    print(f"{len(units)} reviewable units")
    for p in written:
        print(f"  wrote {p} ({p.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
