#!/usr/bin/env python3
"""Build the Localization Desk pages under /admin/localization/.

Basecamp #451. The desk is where a reviewer works through the machine translations
Weglot currently serves for the four Vancouver pages, in each of the 8 locales.

DESIGN
------
Nothing here invents chrome. The page is `render_admin_open("localization")` +
`.dashboard-shell`, the stylesheet is the generated `/assets/css/dashboard.css`, the
"How this works" popup is the `.cpw-overlay` / `.cpw-modal` component the account
menu already uses, and the buttons follow the hierarchy that modal established:
exactly one filled indigo pill for the primary action, ghost pills for the rest,
0.5 opacity when disabled. Desk-specific rules live in `dashboard.DESK_CSS` and
resolve entirely to existing :root tokens -- no new colour, radius or type size.

PROCESS (why the buttons are shaped this way)
---------------------------------------------
Each unit carries one review state per locale:

    unreviewed -> approved   (keep what Weglot serves; idempotent)
               -> edited     (reviewer supplies the text; idempotent)
               -> flagged    (needs a decision later; toggle)
               -> queued     (wants a fresh machine draft; add-only)

`queued` is deliberately a SET MEMBERSHIP, not a job. Clicking "Re-translate" five
times by accident queues one unit, five times over, which is one unit -- there is
no in-flight window to protect and nothing is spent at click time. Cost is incurred
only at the separate, explicit batch approval, which names the count and the
estimate before anything is sent. That is the whole reason the flow is
queue-then-approve rather than fire-on-click.

Decisions apply instantly and locally (localStorage, per locale) so a reviewer can
move through a few hundred rows without a network round trip per keystroke. The
sticky footer shows how many decisions are unsaved.

NOT WIRED YET (stated in the UI, not hidden): pushing decisions back to the repo,
and the batch submission itself. Those arrive with the Gemini phase; the desk is
built first so the interaction can be judged before any spend exists.
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

# Locale code -> (English name, endonym, dir). Codes are the ones the unit files
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

    A unit that appears on several pages is ONE reviewable thing -- it is one
    Weglot translation unit, and approving it approves it everywhere. The page
    list is unioned so the page filter still finds it from either page.
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
        <p>Every row is one translation unit &mdash; a single string Weglot serves on
        the live site. The left column is the English source, the right column is what
        visitors in this language see today. All of it is machine translation.</p>

        <h3>The four decisions</h3>
        <ul>
          <li><strong>Approve</strong> &mdash; the current text is fine. Nothing is sent
          to Weglot; approving simply records that a human has read it.</li>
          <li><strong>Edit</strong> &mdash; type the wording you want. Your text wins over
          everything else.</li>
          <li><strong>Flag</strong> &mdash; something is wrong but you do not want to fix
          it now. Flagged rows stay easy to find.</li>
          <li><strong>Re-translate</strong> &mdash; add the row to the queue for a fresh
          machine draft. The button then reads <em>Queued</em> and stops responding;
          take it back out from <em>Review queue</em>.</li>
        </ul>

        <h3>Why Re-translate does not do anything immediately</h3>
        <p>It adds the row to a queue and nothing more. Clicking it repeatedly cannot
        start five jobs or spend five times &mdash; a row is either in the queue or it is
        not, and clicking again only ever adds, so a stray double-click cannot quietly
        undo itself either. Removing is done from <em>Review queue</em>, where you can see
        what you are removing. The queue is sent as one batch, and only after a separate
        confirmation that shows you how many rows and roughly what it costs.</p>

        <h3>Your decisions are kept in this browser</h3>
        <p>They apply instantly and survive a reload. Saving them back to the repository,
        and sending the queue, are not wired up yet &mdash; the desk is being built before
        the machine translation is connected, so the review flow can be judged first.</p>

        <h3>Keyboard</h3>
        <p><code>J</code> / <code>K</code> move between rows, <code>A</code> approves,
        <code>F</code> flags, <code>R</code> queues, <code>E</code> edits,
        <code>Esc</code> closes this box.</p>
      </div>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-save" id="how-close">Got it</button>
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
            f'        <a class="desk-locale-card" href="/admin/localization/{code}/" '
            f'data-locale="{code}" data-total="{have}">'
        )
        parts.append(f'          <p class="desk-locale-name">{escape(name)}</p>')
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
        parts.append("        </a>")
    parts.append("      </div>")

    parts.append(
        '      <p class="subtle">Nothing on these pages writes to the live site. '
        "Approving records a human read; it does not re-publish anything.</p>"
    )
    parts.append("    </main>")
    parts.append("  </div>")
    parts.append(_index_js())
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _index_js() -> str:
    """Fill each card's meter from that locale's saved review progress.

    The server cannot know this -- decisions live in the reviewer's browser -- so the
    card ships with the honest static number and this upgrades it in place. Without
    it the meter showed translation COVERAGE, which is 100% for every locale because
    Weglot machine-translates everything, i.e. a full bar that means nothing.
    """
    return """\
  <script>
  (function () {
    'use strict';
    Array.prototype.forEach.call(document.querySelectorAll('[data-locale]'), function (card) {
      var code = card.getAttribute('data-locale');
      var total = parseInt(card.getAttribute('data-total'), 10) || 0;
      var done = 0;
      try {
        var raw = JSON.parse(localStorage.getItem('cel-desk-' + code) || '{}') || {};
        for (var k in raw) { if (raw[k] && (raw[k].approved || raw[k].text != null)) done++; }
      } catch (e) { return; }
      var pct = total ? Math.round(100 * done / total) : 0;
      card.querySelector('.desk-meter-fill').style.width = pct + '%';
      card.querySelector('.desk-locale-stat').textContent =
        done ? (done + ' of ' + total + ' reviewed (' + pct + '%)')
             : (total + ' units — not started');
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
    parts.append('            <option value="todo">Needs review</option>')
    parts.append('            <option value="">Everything</option>')
    parts.append('            <option value="approved">Approved</option>')
    parts.append('            <option value="edited">Edited</option>')
    parts.append('            <option value="flagged">Flagged</option>')
    parts.append('            <option value="queued">Queued</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append('        <label class="desk-field">Search')
    parts.append('          <input class="desk-select" id="f-q" type="search" placeholder="source or translation" autocomplete="off">')
    parts.append("        </label>")
    parts.append('        <span class="desk-toolbar-spacer"></span>')
    parts.append('        <button type="button" class="desk-btn" id="how-open">How this works</button>')
    parts.append("      </div>")
    parts.append('      <p class="subtle" id="count-line"></p>')
    parts.append("    </div>")

    parts.append('    <main class="dashboard-main">')
    parts.append('      <div class="scroll-x">')
    parts.append('        <table class="doc-table desk-table">')
    parts.append("          <thead><tr>")
    parts.append('            <th scope="col">English source</th>')
    parts.append(f'            <th scope="col">{escape(name)} (live today)</th>')
    parts.append('            <th scope="col" class="desk-col-state">State</th>')
    parts.append('            <th scope="col" class="desk-col-act">Decision</th>')
    parts.append("          </tr></thead>")
    # Rows are built in the browser from units.json, not baked in here. Server-rendering
    # 990 rows x 8 locales produced 11 MB of HTML that git had to store again on EVERY
    # regeneration; the same content as JSON is ~300 KB per locale and the page shell
    # stays ~20 KB. Nothing about the interaction changes -- paint()/applyFilters() run
    # over the same DOM either way.
    parts.append('          <tbody id="desk-body"></tbody>')

    parts.append("          </tbody>")
    parts.append("        </table>")
    parts.append('        <p class="empty" id="no-rows" hidden>Nothing matches these filters.</p>')
    parts.append("      </div>")
    parts.append("    </main>")

    # Sticky footer
    parts.append('    <div class="desk-savebar" id="savebar" hidden>')
    parts.append('      <p class="desk-savebar-text" id="savebar-text"></p>')
    parts.append('      <span class="desk-savebar-spacer"></span>')
    parts.append('      <span class="desk-status" id="savebar-status" role="status"></span>')
    parts.append('      <button type="button" class="desk-btn" id="btn-reset">Discard</button>')
    parts.append('      <button type="button" class="desk-btn is-primary" id="btn-queue">Review queue</button>')
    parts.append("    </div>")

    parts.append("  </div>")
    parts.append(HOW_MODAL)
    parts.append(_queue_modal())
    parts.append(_desk_js(code, direction == "rtl"))
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _queue_modal() -> str:
    return """\
  <div class="cpw-overlay" id="q-overlay" hidden>
    <div class="cpw-modal desk-modal-wide" role="dialog" aria-modal="true" aria-labelledby="q-title">
      <h2 class="cpw-title" id="q-title">Queued for re-translation</h2>
      <div class="desk-modal-body">
        <p id="q-summary"></p>
        <ul class="desk-queue-list" id="q-list"></ul>
        <p class="desk-notice">Sending is not connected yet. The queue is kept so the
        review flow works end to end first; the batch goes out once the Gemini step is
        wired, and it will ask you to confirm the count and the cost before spending
        anything.</p>
      </div>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-cancel" id="q-clear">Empty the queue</button>
        <button type="button" class="cpw-btn cpw-save" id="q-close">Close</button>
      </div>
    </div>
  </div>
"""


def _desk_js(code: str, rtl: bool) -> str:
    """Per-locale desk behaviour. IIFE, no globals, no framework."""
    return """\
  <script>
  (function () {
    'use strict';
    var KEY = 'cel-desk-__CODE__';
    var state = {};
    try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }

    var body = document.getElementById('desk-body');
    var rows = [];
    var RTL = __RTL__;

    // Build the table from units.json with DOM APIs only -- never by assigning markup.
    // The source and translation are arbitrary site copy, and textContent cannot be
    // talked into executing any of it. (Spelling out the banned property here would
    // trip the test that greps this script for it, which is the point of that test.)
    function buildRows(units) {
      var frag = document.createDocumentFragment();
      units.forEach(function (u) {
        var tr = document.createElement('tr');
        tr.className = 'desk-row';
        tr.setAttribute('data-uid', u.id);
        tr.setAttribute('data-pages', u.pages.join(' '));
        tr.setAttribute('data-q', (u.src + ' ' + u.tgt).toLowerCase());

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
        var ta = document.createElement('textarea');
        ta.className = 'desk-edit';
        ta.hidden = true;
        ta.setAttribute('aria-label', 'Your wording');
        ta.value = u.tgt;
        tdTgt.appendChild(live); tdTgt.appendChild(ta);

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
        // Ghost, not filled. 990 rows means 990 buttons, and making each row's Approve
        // a filled indigo pill turns the single-primary rule into wallpaper. Indigo here
        // means STATE (this row is approved), set by .is-on in paint().
        [['approve', 'Approve'], ['edit', 'Edit'], ['flag', 'Flag'], ['queue', 'Re-translate']]
          .forEach(function (pair) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'desk-btn';
            b.setAttribute('data-act', pair[0]);
            b.textContent = pair[1];
            acts.appendChild(b);
          });
        tdAct.appendChild(acts);

        tr.appendChild(tdSrc); tr.appendChild(tdTgt);
        tr.appendChild(tdState); tr.appendChild(tdAct);
        frag.appendChild(tr);
      });
      body.appendChild(frag);
      rows = Array.prototype.slice.call(body.querySelectorAll('.desk-row'));
    }
    var fPage = document.getElementById('f-page');
    var fState = document.getElementById('f-state');
    var fQ = document.getElementById('f-q');
    var countLine = document.getElementById('count-line');
    var noRows = document.getElementById('no-rows');
    var savebar = document.getElementById('savebar');
    var savebarText = document.getElementById('savebar-text');
    var cursor = -1;

    function persist() {
      try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
    }

    function rec(uid) { return state[uid] || (state[uid] = {}); }

    // ── Render one row from state ──────────────────────────────────────
    function paint(tr) {
      var uid = tr.getAttribute('data-uid');
      var s = state[uid] || {};
      var badge = tr.querySelector('.desk-state');
      var label = 'unreviewed', cls = 'badge-partial';
      if (s.text != null) { label = 'edited'; cls = 'badge-ok'; }
      else if (s.approved) { label = 'approved'; cls = 'badge-ok'; }
      if (s.flagged) { label = label === 'unreviewed' ? 'flagged' : label + ' · flagged'; cls = 'badge-failed'; }
      if (s.queued) { label = label === 'unreviewed' ? 'queued' : label + ' · queued'; }
      badge.className = 'desk-state ' + cls;
      badge.textContent = label;
      tr.classList.toggle('is-done', !!(s.approved || s.text != null));

      var bApprove = tr.querySelector('[data-act="approve"]');
      var bFlag = tr.querySelector('[data-act="flag"]');
      var bQueue = tr.querySelector('[data-act="queue"]');
      bApprove.classList.toggle('is-on', !!s.approved);
      bApprove.textContent = s.approved ? 'Approved' : 'Approve';
      bFlag.classList.toggle('is-flagged', !!s.flagged);
      bQueue.classList.toggle('is-on', !!s.queued);
      bQueue.textContent = s.queued ? 'Queued' : 'Re-translate';
      // Nothing left to do on a queued row here: adding again is a no-op and removing
      // belongs on the queue screen, so the control stops accepting clicks entirely.
      bQueue.disabled = !!s.queued;
      // A queued row is waiting on a machine draft, so approving it now would be
      // approving text that is about to be replaced.
      bApprove.disabled = !!s.queued;
    }

    function decided() {
      var n = 0, q = 0;
      for (var k in state) {
        var s = state[k];
        if (!s) continue;
        if (s.approved || s.text != null || s.flagged) n++;
        if (s.queued) q++;
      }
      return { n: n, q: q };
    }

    function paintBar() {
      var d = decided();
      if (!d.n && !d.q) { savebar.hidden = true; return; }
      savebar.hidden = false;
      var bits = [];
      if (d.n) bits.push(d.n + (d.n === 1 ? ' decision' : ' decisions'));
      if (d.q) bits.push(d.q + ' queued for re-translation');
      savebarText.textContent = bits.join(' · ') + ' — kept in this browser';
      document.getElementById('btn-queue').disabled = !d.q;
    }

    // ── Filters ────────────────────────────────────────────────────────
    function matches(tr) {
      var uid = tr.getAttribute('data-uid');
      var s = state[uid] || {};
      var p = fPage.value;
      if (p && (' ' + tr.getAttribute('data-pages') + ' ').indexOf(' ' + p + ' ') === -1) return false;
      var want = fState.value;
      if (want === 'todo' && (s.approved || s.text != null)) return false;
      if (want === 'approved' && !s.approved) return false;
      if (want === 'edited' && s.text == null) return false;
      if (want === 'flagged' && !s.flagged) return false;
      if (want === 'queued' && !s.queued) return false;
      var q = fQ.value.trim().toLowerCase();
      if (q && tr.getAttribute('data-q').indexOf(q) === -1) return false;
      return true;
    }

    function applyFilters() {
      var shown = 0;
      rows.forEach(function (tr) {
        var ok = matches(tr);
        tr.hidden = !ok;
        if (ok) shown++;
      });
      noRows.hidden = shown !== 0;
      countLine.textContent = shown + ' of ' + rows.length + ' units shown';
      if (cursor >= 0 && rows[cursor] && rows[cursor].hidden) focusRow(-1);
    }

    // ── Actions ────────────────────────────────────────────────────────
    function act(tr, what) {
      var uid = tr.getAttribute('data-uid');
      var s = rec(uid);
      if (what === 'approve') {
        if (s.queued) return;              // guarded in paint(), belt-and-braces here
        s.approved = !s.approved;
      } else if (what === 'flag') {
        s.flagged = !s.flagged;
      } else if (what === 'queue') {
        // ADD, never toggle. A toggle survives five clicks (odd -> still queued) but
        // NOT four, and a double-click is the most common mis-click there is -- it
        // would have silently un-queued the row while looking like it did nothing.
        // Adding is idempotent under any number of clicks; removal is deliberate,
        // from the queue screen, where you can see what you are removing.
        s.queued = true;
        s.approved = false;
      } else if (what === 'edit') {
        var ta = tr.querySelector('.desk-edit');
        var live = tr.querySelector('.desk-live');
        var opening = ta.hidden;
        ta.hidden = !opening;
        live.hidden = opening;
        if (opening) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
        return;
      }
      persist(); paint(tr); paintBar(); applyFilters();
    }

    body.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-act]');
      if (!btn) return;
      var tr = btn.closest('.desk-row');
      focusRow(rows.indexOf(tr));
      act(tr, btn.getAttribute('data-act'));
    });

    body.addEventListener('change', function (ev) {
      var ta = ev.target.closest('.desk-edit');
      if (!ta) return;
      var tr = ta.closest('.desk-row');
      var uid = tr.getAttribute('data-uid');
      var live = tr.querySelector('.desk-live');
      var val = ta.value.trim();
      if (val && val !== live.textContent) { rec(uid).text = val; }
      else { delete rec(uid).text; }
      persist(); paint(tr); paintBar();
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
      if (k === 'a') { ev.preventDefault(); act(rows[cursor], 'approve'); }
      else if (k === 'f') { ev.preventDefault(); act(rows[cursor], 'flag'); }
      else if (k === 'r') { ev.preventDefault(); act(rows[cursor], 'queue'); }
      else if (k === 'e') { ev.preventDefault(); act(rows[cursor], 'edit'); }
    });

    // ── Overlays ───────────────────────────────────────────────────────
    var howOverlay = document.getElementById('how-overlay');
    var qOverlay = document.getElementById('q-overlay');
    function closeOverlays() { howOverlay.hidden = true; qOverlay.hidden = true; }
    document.getElementById('how-open').addEventListener('click', function () {
      howOverlay.hidden = false;
      document.getElementById('how-close').focus();
    });
    document.getElementById('how-close').addEventListener('click', closeOverlays);
    document.getElementById('q-close').addEventListener('click', closeOverlays);
    [howOverlay, qOverlay].forEach(function (ov) {
      ov.addEventListener('click', function (ev) { if (ev.target === ov) closeOverlays(); });
    });

    var qList = document.getElementById('q-list');

    function paintQueue() {
      var d = decided();
      document.getElementById('q-summary').textContent =
        d.q + (d.q === 1 ? ' unit is' : ' units are') + ' queued for a fresh machine draft.';
      qList.textContent = '';
      rows.forEach(function (tr) {
        var uid = tr.getAttribute('data-uid');
        if (!state[uid] || !state[uid].queued) return;
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
          delete state[uid].queued;
          persist(); paint(tr); paintBar(); applyFilters(); paintQueue();
        });
        li.appendChild(span); li.appendChild(rm);
        qList.appendChild(li);
      });
    }

    document.getElementById('btn-queue').addEventListener('click', function () {
      paintQueue();
      qOverlay.hidden = false;
      document.getElementById('q-close').focus();
    });
    document.getElementById('q-clear').addEventListener('click', function () {
      for (var k in state) { if (state[k]) delete state[k].queued; }
      persist(); rows.forEach(paint); paintBar(); applyFilters(); paintQueue(); closeOverlays();
    });
    document.getElementById('btn-reset').addEventListener('click', function () {
      if (!window.confirm('Discard every decision recorded in this browser for this language?')) return;
      state = {}; persist(); rows.forEach(paint); paintBar(); applyFilters();
    });

    [fPage, fState].forEach(function (el) { el.addEventListener('change', applyFilters); });
    fQ.addEventListener('input', applyFilters);

    fetch('units.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (units) {
        buildRows(units);
        rows.forEach(paint);
        paintBar();
        applyFilters();
      })
      .catch(function (err) {
        // Say so in the page. A desk that silently shows zero rows looks like
        // "nothing to review", which is the opposite of what has happened.
        countLine.textContent = 'Could not load the units (' + err.message + ').';
        countLine.className = 'subtle desk-status is-error';
        noRows.hidden = true;
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
