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

from localize_desk.recommend import LEVEL_CHECK, recommend  # noqa: E402

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
# code, English name, endonym, direction, flag.
# `pt` is Brazilian Portuguese for CEL, hence Brazil rather than Portugal. Arabic has
# no country, so it takes the one the client's own locale list implies; the language
# NAME is always shown beside the flag precisely because a flag is not a language.
LOCALES = [
    ("de", "German", "Deutsch", "ltr", "\U0001F1E9\U0001F1EA"),
    ("fr", "French", "Français", "ltr", "\U0001F1EB\U0001F1F7"),
    ("es", "Spanish", "Español", "ltr", "\U0001F1EA\U0001F1F8"),
    ("pt", "Portuguese", "Português", "ltr", "\U0001F1E7\U0001F1F7"),
    ("it", "Italian", "Italiano", "ltr", "\U0001F1EE\U0001F1F9"),
    ("ja", "Japanese", "日本語", "ltr", "\U0001F1EF\U0001F1F5"),
    ("ko", "Korean", "한국어", "ltr", "\U0001F1F0\U0001F1F7"),
    ("ar", "Arabic", "العربية", "rtl", "\U0001F1F8\U0001F1E6"),
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
    in_scope: set[str] = set()
    for path in sorted(UNITS_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        page = doc["page"]
        if doc.get("path"):
            in_scope.add(doc["path"])
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
    # A unit's `pages` is every page on the SITE that carries the same English (the
    # manifest reads it from the site index, and it agrees with gate 12's
    # `outside_scope` on all 1,246 units). Weglot keeps one translation per English
    # string, so a wording approved here would change those pages too -- which is
    # exactly why gate 12 refuses it. 254 of the 823 importable units per locale are
    # like that, and the desk used to present them as ordinary rows: approvals that
    # could never reach a file.
    for unit in by_id.values():
        unit["_outside"] = sorted(p for p in unit.get("pages") or [] if p not in in_scope)
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
        level, why = recommend(unit["word_from"], current.get("word_to", ""), code)
        row = {
            "id": unit["unit_id"],
            "src": unit["word_from"],
            "tgt": current.get("word_to", ""),
            "sec": unit.get("section") or "",
            "pages": sorted(unit["_pages"]),
        }
        # Only carried when there is something to say -- `fine` is the absence of a
        # finding, not a claim, and writing it 7,500 times would bloat the artefact
        # git re-stores on every rebuild.
        if level == LEVEL_CHECK:
            row["why"] = why
        outside = unit.get("_outside") or []
        if outside:
            row["shared"] = len(outside)
            row["sharedEg"] = outside[0]
        out.append(row)
    return out


def worth_a_look(code: str, units: list[dict]) -> list[str]:
    """Unit ids the desk puts in "Worth a look first" for one locale.

    One definition, used by the locale page's filter, its language-tab badges and the
    index card, so the three cannot disagree. A site-wide row is not in it: a finding
    on it is real, but no decision made here can reach the website (gate 12).
    """
    out = []
    for unit in units:
        current = (unit.get("current") or {}).get(code)
        if not current or unit.get("_outside"):
            continue
        if recommend(unit["word_from"], current.get("word_to", ""), code)[0] == LEVEL_CHECK:
            out.append(unit["unit_id"])
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
        <p>Every row is one piece of text from the live website. On the left is the
        English; on the right is what visitors in this language see today. All of it was
        translated by machine, and none of it has been checked by a person.</p>

        <h3>Your three choices</h3>
        <ul>
          <li><strong>Approve</strong> &mdash; the wording is right. It will go to the
          website as it is.</li>
          <li><strong>Edit</strong> &mdash; type what it should say. Saving your wording
          approves the row, with your text instead.</li>
          <li><strong>Needs a new translation</strong> &mdash; the wording is wrong and
          you would like Gemini to try again.</li>
        </ul>
        <p>A row can only be one of these. Choosing one clears the other, and clicking a
        choice you have already made undoes it.</p>

        <h3>Start with the rows worth a look</h3>
        <p>The desk checks every translation for things that are almost always wrong:
        English left untranslated, a price or date that changed, a missing link, a
        formal &ldquo;Sie&rdquo; where the client asked for the informal form. Those rows
        say why underneath, and <em>Worth a look first</em> shows only them. It is a few
        dozen rows per language rather than a thousand.</p>

        <h3>Working quickly</h3>
        <p>Tick any row, or the box in the header to take everything on screen, and the
        bar at the bottom applies one choice to all of them. <code>J</code> and
        <code>K</code> move between rows; <code>A</code> approves, <code>E</code> edits,
        <code>R</code> asks for a new translation, <code>X</code> ticks the box.</p>

        <h3>Nothing leaves this page by itself</h3>
        <p>Approved rows wait until you make the import file. Rows needing a new
        translation wait until you send them, and you will see how many and roughly what
        it costs before anything is spent. Both lists are openable from the bottom bar,
        and you can undo anything in them.</p>

        <h3>Saving</h3>
        <p>Your choices are kept on this page as you make them. <strong>Save</strong>
        stores them properly, so you can close the tab, come back tomorrow, or carry on
        from a different computer.</p>
      </div>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-save" id="how-close">Close</button>
      </div>
    </div>
  </div>
"""


REVIEW_MODAL = """\
  <div class="cpw-overlay" id="tray-overlay" hidden>
    <div class="desk-review" role="dialog" aria-modal="true" aria-labelledby="tray-title">
      <header class="desk-review-head">
        <div>
          <h2 class="desk-review-title" id="tray-title"></h2>
          <p class="desk-review-sub" id="tray-summary"></p>
        </div>
        <button type="button" class="desk-icon-btn desk-review-x" id="tray-close"
                title="Close" aria-label="Close">&#215;</button>
      </header>
      <div class="desk-review-toolbar">
        <label class="desk-review-all">
          <input type="checkbox" class="desk-pick" id="tray-all"
                 aria-label="Select every row listed">
          <span id="tray-selcount">Select all</span>
        </label>
        <span class="desk-savebar-spacer"></span>
        <button type="button" class="desk-btn" id="tray-remove-sel" disabled>Undo</button>
        <button type="button" class="desk-btn" id="tray-empty">Undo all</button>
      </div>
      <ul class="desk-review-list" id="tray-list"></ul>
      <footer class="desk-review-foot">
        <p class="desk-notice" id="tray-notice"></p>
        <div class="desk-review-actions">
          <button type="button" class="desk-btn" id="tray-done">Close</button>
          <button type="button" class="desk-btn is-primary" id="tray-save" hidden></button>
        </div>
      </footer>
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
    for code, name, endonym, _dir, flag in LOCALES:
        have = sum(1 for u in units if (u.get("current") or {}).get(code))
        # The recommendation count is the only number that is useful on a FIRST visit:
        # decisions all start at zero, so without this every card said the same thing
        # and the index answered nothing.
        flagged = len(worth_a_look(code, units))
        parts.append(
            f'        <div class="desk-locale-card" data-locale="{code}" '
            f'data-name="{escape(name)}" '
            f'data-total="{have}" data-flagged="{flagged}">'
        )
        parts.append(
            f'          <a class="desk-locale-open" href="/admin/localization/{code}/?show=check">'
            f'<span class="desk-loc-flag" aria-hidden="true">{flag}</span> '
            f'<span class="desk-locale-name">{escape(name)}</span></a>'
        )
        parts.append(
            f'          <p class="desk-locale-sub"><bdi>{escape(endonym)}</bdi> '
            f'&middot; {have} units</p>'
        )
        parts.append('          <div class="desk-meter" role="presentation">')
        parts.append('            <div class="desk-meter-fill" style="width:0%"></div>')
        parts.append("          </div>")
        parts.append(
            f'          <p class="desk-locale-stat">{flagged} need attention</p>'
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
    parts.append(_index_js(_worth_js(units)))
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


# The ONE decider of what a row is (process doc §1). It is emitted into the locale
# pages AND the index from this single string: the index used to carry its own copy
# that knew nothing about `liveAt`/`exportedAt`, so the two pages could disagree about
# the same record.
_STAGE_JS = """\
    function stageOf(s) {
      s = s || {};
      // A live row the reviewer has decided about again is NOT live any more from
      // their point of view -- the new decision is what is outstanding. So anything
      // in flight or freshly decided outranks where the text currently sits.
      if (s.failed) return 'failed';
      if (s.sentAt && !s.arrivedAt) return 'sending';
      if (s.arrivedAt && !s.tray) return 'arrived';
      if (s.tray === 'draft') return 'queued';
      if (s.tray === 'csv') {
        if (s.liveAt) return 'live';          // confirmed on the site by reconciliation
        if (s.exportedAt) return 'exported';  // in a file, waiting to be imported
        return s.text != null ? 'edited' : 'approved';
      }
      if (s.liveAt) return 'live';
      return 'todo';
    }
"""


def _worth_js(units: list[dict]) -> str:
    """`{locale: [unit ids worth a look]}` for every locale, as a JS literal."""
    return json.dumps({c: worth_a_look(c, units) for c, *_ in LOCALES},
                      separators=(",", ":"))


def _index_js(worth_js: str = "{}") -> str:
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
    var WORTH = __WORTH__;
__STAGE_JS__
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
      // The desk's own stageOf(), emitted from the same string, so the index cannot
      // disagree with the page it links to.
      var st = read(code);
      var csv = 0, draft = 0, arrived = 0, sending = 0, failed = 0, done = 0;
      for (var k in st) {
        var stg = stageOf(st[k]);
        if (stg === 'todo') continue;
        done++;
        if (stg === 'failed') failed++;
        else if (stg === 'sending') sending++;
        else if (stg === 'arrived') arrived++;
        else if (stg === 'approved' || stg === 'edited') csv++;
        else if (stg === 'queued') draft++;
      }
      var flagged = (WORTH[code] || []).filter(function (uid) {
        return stageOf(st[uid]) === 'todo';
      }).length;
      var pct = total ? Math.round(100 * done / total) : 0;
      card.querySelector('.desk-meter-fill').style.width = pct + '%';
      // Once there is progress, progress is the more useful number; before that, the
      // number of rows actually asking for attention is.
      card.querySelector('.desk-locale-stat').textContent =
        done ? (done + ' of ' + total + ' decided (' + pct + '%)')
             : (flagged === 1 ? '1 worth a look' : flagged + ' worth a look');

      var trays = card.querySelector('.desk-trays');
      trays.textContent = '';
      var base = '/admin/localization/' + code + '/';
      if (!csv && !draft && !arrived && !sending && !failed) {
        trays.appendChild(chip('desk-tray-none', 'nothing decided yet', null));
        return;
      }
      // Ordered by what is waiting on the reviewer, not by what the system did.
      if (arrived) trays.appendChild(chip('desk-tray-arrived', arrived + ' new to read', base + '?show=arrived'));
      if (failed) trays.appendChild(chip('desk-tray-failed',
        failed + (failed === 1 ? ' translation failed' : ' translations failed'),
        base + '?show=failed'));
      if (sending) trays.appendChild(chip('desk-tray-sending', sending + ' being translated', base + '?show=sending'));
      if (csv) trays.appendChild(chip('desk-tray-csv', csv + ' approved', base + '?show=csv'));
      if (draft) trays.appendChild(chip('desk-tray-draft', draft + ' need a new translation', base + '?show=draft'));

      // This used to say "Undo all" and warn "This cannot be undone" -- both wrong.
      // It removed one browser key, so anything already saved came straight back
      // from the server on the next visit, and the warning frightened the reviewer
      // about an action that had almost no effect. What it can honestly offer is
      // throwing away the work this browser has not sent yet.
      var unsaved = 0, base0 = read('saved-' + code);
      for (var uk in st) { if (JSON.stringify(st[uk]) !== JSON.stringify(base0[uk])) unsaved++; }
      if (unsaved) {
        var undo = document.createElement('button');
        undo.type = 'button';
        undo.className = 'desk-btn';
        undo.textContent = 'Discard ' + unsaved + ' unsaved';
        undo.title = 'Throw away what this browser has not saved. Anything already saved stays.';
        undo.addEventListener('click', function () {
          var nm = card.getAttribute('data-name') || code;
          if (!window.confirm('Throw away ' + unsaved + ' unsaved change' +
                              (unsaved === 1 ? '' : 's') + ' in ' + nm +
                              '? Anything already saved stays where it is.')) return;
          try {
            localStorage.setItem('cel-desk-' + code,
                                 localStorage.getItem('cel-desk-saved-' + code) || '{}');
          } catch (e) {}
          location.reload();
        });
        trays.appendChild(undo);
      }
    });
  })();
  </script>
""".replace("__STAGE_JS__", _STAGE_JS).replace("__WORTH__", worth_js)


def render_locale(code: str, name: str, endonym: str, direction: str,
                  units: list[dict]) -> str:
    rows = [u for u in units if (u.get("current") or {}).get(code)]
    parts = _head(
        f"{name} — Localization Desk — English College",
        f"Review the {name} machine translations served on the four Vancouver pages.",
    )
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    # Same markup and classes as render_page_chrome(), written out here so the help
    # control can live IN the header rather than down among the filters. It is not a
    # filter, and sitting next to Page/Show/Search it read like one.
    parts.append('    <header class="dashboard-header">')
    parts.append('      <div class="brand-text">')
    parts.append(f'        <p class="eyebrow">LOCALIZATION DESK &middot; {escape(name.upper())}</p>')
    parts.append(
        f'        <p class="subtitle"><bdi>{escape(endonym)}</bdi> &middot; {len(rows)} units</p>'
    )
    parts.append("      </div>")
    parts.append('      <button type="button" class="desk-btn desk-header-btn" id="how-open">'
                 "How this works</button>")
    parts.append("    </header>")

    # Toolbar. The locale strip comes FIRST because switching language while staying
    # on the same page and filter is the move the reviewer makes most: the old desk
    # forced a trip back to the index and lost the filters on the way.
    parts.append('    <div class="controls">')
    parts.append('      <nav class="desk-locales-strip" aria-label="Language">')
    for lcode, lname, _endo, _dir, lflag in LOCALES:
        cls = "desk-loc is-active" if lcode == code else "desk-loc"
        aria = ' aria-current="page"' if lcode == code else ""
        parts.append(
            f'        <a class="{cls}" href="/admin/localization/{lcode}/" '
            f'data-loc="{lcode}"{aria}>'
            f'<span class="desk-loc-flag" aria-hidden="true">{lflag}</span>'
            f'<span class="desk-loc-name">{escape(lname)}</span>'
            f'<span class="desk-loc-count" data-loc-count="{lcode}" hidden></span></a>'
        )
    parts.append("      </nav>")
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
    # Ordered by what the reviewer should do next, and every label carries a live
    # count -- so the dropdown answers "where is the work" without selecting anything.
    for value, label in [
        ("check", "Worth a look first"),
        ("arrived", "New translations — read these first"),
        ("todo", "Not reviewed"),
        ("", "Everything"),
        ("csv", "Approved"),
        ("edited", "Approved \u00b7 your wording"),
        ("draft", "Needs a new translation"),
        ("sending", "Being translated"),
        ("failed", "Translation failed"),
        ("exported", "In the export file"),
        ("live", "Already on the website"),
    ]:
        parts.append(f'            <option value="{value}" data-base="{escape(label)}">{escape(label)}</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append('        <label class="desk-field">Search')
    parts.append('          <input class="desk-select" id="f-q" type="search" '
                 'placeholder="source or translation" autocomplete="off">')
    parts.append("        </label>")
    # Neither Import nor Download: the reviewer imports nothing, and asking them to
    # take backups is asking them to spend the time this project exists to save.
    # Durability is the system's job, not a button. "How this works" moved up into the
    # header — it is help, not a filter.
    parts.append("      </div>")
    parts.append('      <p class="subtle" id="count-line"></p>')
    parts.append("    </div>")

    parts.append('    <main class="dashboard-main">')
    parts.append('      <div class="scroll-x">')
    parts.append('        <table class="doc-table desk-table">')
    # Explicit columns, because the table is `table-layout: fixed`. Under `auto`,
    # max-width on a cell clamps the BOX but not the content, so at 820px the English
    # ran 66px into the German column -- boxes that did not overlap, text that did.
    parts.append("          <colgroup>")
    parts.append('            <col class="col-pick"><col class="col-src"><col class="col-tgt">')
    parts.append('            <col class="col-state"><col class="col-act">')
    parts.append("          </colgroup>")
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
    parts.append('        <button type="button" class="desk-btn" id="bulk-clear">Clear</button>')
    parts.append('        <button type="button" class="desk-btn" id="bulk-draft">Needs a new translation</button>')
    parts.append('        <button type="button" class="desk-btn is-strong" id="bulk-approve">Approve</button>')
    parts.append("      </div>")
    parts.append('      <div class="desk-bar-row" id="bar-trays" hidden>')
    parts.append('        <p class="desk-savebar-text" id="tray-line"></p>')
    parts.append('        <span class="desk-savebar-spacer"></span>')
    # These OPEN a list; the two in the row above ACT on the selection. They used to
    # read "Needs a new translation" and "Approved" -- byte-identical to, and one
    # letter from, the action buttons sitting directly above them in the same bar.
    parts.append('        <button type="button" class="desk-btn" id="open-draft">See marked</button>')
    parts.append('        <button type="button" class="desk-btn" id="open-csv">See approved</button>')
    parts.append('        <button type="button" class="desk-btn is-primary" id="btn-save" hidden>Save</button>')
    parts.append('        <span class="desk-status" id="save-elsewhere" hidden></span>')
    parts.append('        <span class="desk-status" id="save-status" role="status"></span>')
    parts.append("      </div>")
    parts.append("    </div>")

    parts.append("  </div>")
    parts.append('  <div class="toast-stack" id="toast-stack" role="status" aria-live="polite"></div>')
    parts.append(HOW_MODAL)
    parts.append(REVIEW_MODAL)
    parts.append(_desk_js(code, direction == "rtl", _worth_js(units)))
    parts.append(render_admin_close())
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _desk_js(code: str, rtl: bool, worth_js: str = "{}") -> str:
    """Per-locale desk behaviour. IIFE, no globals but the debug hook, no framework."""
    return """\
  <script>
  (function () {
    'use strict';
    // Monochrome line icons, drawn in currentColor so they take the button's colour
    // and nothing else. No brand colours: 990 rows of coloured marks would compete
    // with the one thing colour is reserved for here, which is state.
    //
    // Held as path DATA and built with createElementNS rather than assigned as markup.
    // These are constants, so a string assignment would have been safe -- but the desk
    // has a test asserting this script never assigns markup at all, and an invariant
    // with an exception is not an invariant. It is also how the row text stays safe.
    var SVG_NS = 'http://www.w3.org/2000/svg';
    var ICONS = {
      tick:   { stroke: 1.9, d: ['M3 8.5 6.5 12 13 4.5'] },
      pencil: { stroke: 1.6, d: ['M11.2 2.3a1.6 1.6 0 0 1 2.3 2.3L5.6 12.4 2.5 13.5l1.1-3.1z',
                                 'M10.2 3.4 12.6 5.8'] },
      // Gemini's mark is a four-pointed star.
      // An arrow curving back on itself: take this row back out.
      undo:   { stroke: 1.7, d: ['M3 8a5 5 0 1 1 1.6 3.7', 'M3 4.5V8h3.5'] },
      // The operator's own AI mark: one large four-pointed star with two smaller ones.
      // My hand-drawn single star kept reading as a plus no matter how the arms were
      // tapered -- a symmetric 4-point star simply has too little information left at
      // 15px. Three stars of different sizes fix it, because the shape is then
      // recognised by its composition rather than by one outline. 32-unit viewBox.
      spark:  { fill: true, size: 17, vb: '0 0 32 32', d: [
        'm13.294 7.436.803 2.23c.892 2.475 2.841 4.424 5.316 5.316l2.23.803c.201.073.201.358 0 .43'
        + 'l-2.23.803c-2.475.892-4.424 2.841-5.316 5.316l-.803 2.23c-.073.201-.358.201-.43 0'
        + 'l-.803-2.23c-.892-2.475-2.841-4.424-5.316-5.316l-2.23-.803c-.201-.073-.201-.358 0-.43'
        + 'l2.23-.803c2.475-.892 4.424-2.841 5.316-5.316l.803-2.23c.072-.202.357-.202.43 0z',
        'm23.332 2.077.407 1.129c.452 1.253 1.439 2.24 2.692 2.692l1.129.407c.102.037.102.181 0 .218'
        + 'l-1.129.407c-1.253.452-2.24 1.439-2.692 2.692l-.407 1.129c-.037.102-.181.102-.218 0'
        + 'l-.407-1.129c-.452-1.253-1.439-2.24-2.692-2.692l-1.129-.407c-.102-.037-.102-.181 0-.218'
        + 'l1.129-.407c1.253-.452 2.24-1.439 2.692-2.692l.407-1.129c.037-.103.182-.103.218 0z',
        'm23.332 21.25.407 1.129c.452 1.253 1.439 2.24 2.692 2.692l1.129.407c.102.037.102.181 0 .218'
        + 'l-1.129.407c-1.253.452-2.24 1.439-2.692 2.692l-.407 1.129c-.037.102-.181.102-.218 0'
        + 'l-.407-1.129c-.452-1.253-1.439-2.24-2.692-2.692l-1.129-.407c-.102-.037-.102-.181 0-.218'
        + 'l1.129-.407c1.253-.452 2.24-1.439 2.692-2.692l.407-1.129c.037-.102.182-.102.218 0z'] }
    };

    function icon(name) {
      var spec = ICONS[name];
      var svg = document.createElementNS(SVG_NS, 'svg');
      svg.setAttribute('viewBox', spec.vb || '0 0 16 16');
      var px = String(spec.size || 15);
      svg.setAttribute('width', px);
      svg.setAttribute('height', px);
      svg.setAttribute('aria-hidden', 'true');
      svg.setAttribute('fill', spec.fill ? 'currentColor' : 'none');
      if (!spec.fill) {
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', String(spec.stroke));
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
      }
      spec.d.forEach(function (d) {
        var path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', d);
        svg.appendChild(path);
      });
      return svg;
    }

    var LOCALES = __LOCALES__;
    // Per locale, the ids "Worth a look first" starts from -- the same list the index
    // card counts, so a tab badge, the filter and the index say one number.
    var WORTH = __WORTH__;
    var CODE = '__CODE__';
    var KEY = 'cel-desk-' + CODE;
    var LOGKEY = 'cel-desk-log-' + CODE;
    var LOG_CAP = 4000;
    var RTL = __RTL__;

    var state = {};
    // What the website serves for each row, as loaded -- never what is on screen. The
    // `.desk-live` span shows the reviewer's edit when there is one, and reading the
    // wording back from it recorded a DISCARDED edit as the text an approval was given
    // to (audit 2026-09-23): export then refused the row as "moved since approval".
    var liveText = Object.create(null);
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
    var storageBroken = false;
    function persist() {
      try {
        localStorage.setItem(KEY, JSON.stringify(state));
        storageBroken = false;
        return true;
      } catch (e) {
        // Swallowing this silently let every caller toast "saved" while nothing had
        // been written -- the screen stayed right and a reload lost the lot. Say so
        // once, then stop repeating it.
        if (!storageBroken) {
          storageBroken = true;
          toast('This browser will not store your work', { level: 'err',
            detail: 'What you see is still correct, but a reload would lose it. ' +
                    'Save now so it reaches the server.' });
        }
        return false;
      }
    }
    function note(action, uid, from, to) {
      // Capped so a long session cannot fill the origin's storage quota and start
      // throwing on the writes that actually matter.
      hist.push({ t: new Date().toISOString(), a: action, u: uid || null, f: from || null, x: to || null });
      if (hist.length > LOG_CAP) hist = hist.slice(hist.length - LOG_CAP);
      try { localStorage.setItem(LOGKEY, JSON.stringify(hist)); } catch (e) {}
    }
    function rec(uid) { return state[uid] || (state[uid] = {}); }

    // Who approved, when, and — the one that matters — WHAT they were looking at.
    //
    // An approval is an approval OF A WORDING, not of a row. Without `approvedAgainst`
    // there is no way to tell later whether the text moved after the approval, so a
    // Weglot re-translation would be exported under a signature given to something
    // else. The export refuses that case, but only because this is recorded here.
    //
    // `by` comes from the dashboard's own session (auth.js puts the signed-in user on
    // window.__CEL_USER__). The CSV's signature gate also wants a cryptographic
    // signature, which is a later phase — but an identity has to exist before there is
    // anything to sign.
    function stampApproval(uid, tr, approving) {
      var s = rec(uid);
      if (!approving) { delete s.by; delete s.at; delete s.approvedAgainst; return; }
      var who = (window.__CEL_USER__ && window.__CEL_USER__.email) || '';
      if (who) s.by = who;
      s.at = new Date().toISOString();
      if (s.text == null) {
        // A bare approval: record the live wording it was given to.
        s.approvedAgainst = liveText[uid];
      }
    }

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
      // Deciding a row IS the way out of a failed translation. Without this the
      // badge stayed red for ever, the Approved filter refused the row, and the
      // exporter -- which tests only the tray -- would still have shipped it.
      if (tray && s.failed) delete s.failed;
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
        liveText[u.id] = u.tgt;
        tr.setAttribute('data-pages', u.pages.join(' '));
        tr.setAttribute('data-q', (u.src + ' ' + u.tgt).toLowerCase());
        // A site-wide row keeps its finding on screen but is not "worth a look first":
        // nothing decided here can reach the website for it (see `shared` below).
        if (u.why && !u.shared) tr.setAttribute('data-why', '1');
        if (u.shared) tr.setAttribute('data-shared', String(u.shared));

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
        // `auto`, not the column's rtl: an English string in the Arabic column was laid
        // out right-to-left, so "5 Things That Surprise..." read "Things That
        // Surprise... 5" and a sentence's full stop jumped to the front. The reviewer
        // was being shown a defect that is not on the website.
        live.setAttribute('dir', 'auto');
        live.textContent = u.tgt;
        // The recommendation is advice, not an action: it says why a row is worth a
        // second look and does nothing else. Computed at build time from the text
        // already on the page, so it costs nothing and no model was asked.
        var why = null;
        if (u.why) {
          why = document.createElement('p');
          why.className = 'desk-why';
          why.setAttribute('dir', 'auto');   // English advice in an RTL column
          why.textContent = u.why;
        }
        // Weglot keeps ONE translation per English string, so this wording is also the
        // wording on those other pages -- and gate 12 keeps it out of the import file
        // for exactly that reason. Say so where the decision is made, in what-happens-
        // next words, instead of letting an approval disappear at export.
        var shared = null;
        if (u.shared) {
          shared = document.createElement('p');
          shared.className = 'desk-shared';
          shared.setAttribute('dir', 'auto');
          var eg = u.sharedEg === '/' ? 'the home page' : u.sharedEg;
          shared.textContent = 'Shared with ' + u.shared + (u.shared === 1 ? ' other page' : ' other pages') +
            ' (' + eg + (u.shared > 1 ? ', …' : '') + '). Weglot keeps one wording for all of ' +
            'them, so a decision here cannot reach the website yet.';
        }
        var editWrap = document.createElement('div');
        editWrap.className = 'desk-editor';
        editWrap.hidden = true;
        var ta = document.createElement('textarea');
        ta.className = 'desk-edit';
        ta.setAttribute('aria-label', 'Your wording');
        ta.setAttribute('dir', 'auto');
        ta.value = u.tgt;
        // Seeded here as well as on open, so `editorDirty` answers honestly for a
        // box the reviewer never touched. Without it a never-opened editor reads
        // as dirty and any flush treats the machine original as a decision.
        ta.setAttribute('data-opened-with', ta.value);
        var editBar = document.createElement('div');
        editBar.className = 'desk-editor-bar';
        var editHint = document.createElement('span');
        editHint.className = 'desk-editor-hint';
        var bCancel = document.createElement('button');
        bCancel.type = 'button';
        bCancel.className = 'desk-btn';
        bCancel.setAttribute('data-edit', 'cancel');
        bCancel.textContent = 'Cancel';
        var bSave = document.createElement('button');
        bSave.type = 'button';
        // Ghost, not filled. Save in the bottom bar is the page's one primary, and a
        // second filled pill inline in a table row competes with it for the same job.
        bSave.className = 'desk-btn is-strong';
        bSave.setAttribute('data-edit', 'save');
        bSave.textContent = 'Save changes';
        editBar.appendChild(editHint);
        editBar.appendChild(bCancel);
        editBar.appendChild(bSave);
        editWrap.appendChild(ta);
        editWrap.appendChild(editBar);
        tdTgt.appendChild(live);
        if (why) tdTgt.appendChild(why);
        if (shared) tdTgt.appendChild(shared);
        tdTgt.appendChild(editWrap);

        var tdState = document.createElement('td');
        tdState.className = 'desk-col-state';
        var badge = document.createElement('span');
        badge.className = 'desk-state badge-partial';
        badge.textContent = 'Not reviewed';
        tdState.appendChild(badge);

        var tdAct = document.createElement('td');
        tdAct.className = 'desk-col-act';
        var acts = document.createElement('div');
        acts.className = 'desk-actions';
        // Icons, not words, for the three per-row actions: at ~990 rows the labels were
        // most of the visual weight on the page. One colour for all three (currentColor,
        // so they inherit) -- colour here means STATE, never identity, and a decided row
        // is the only place indigo appears. Every one keeps a title and an aria-label,
        // so the meaning survives a screen reader and a hover.
        [['approve', 'Approve', 'tick'],
         ['edit', 'Edit wording', 'pencil'],
         ['queue', 'Needs a new translation', 'spark']]
          .forEach(function (spec) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'desk-btn desk-icon-btn';
            b.setAttribute('data-act', spec[0]);
            b.title = spec[1];
            b.setAttribute('aria-label', spec[1]);
            b.appendChild(icon(spec[2]));
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
    // The whole lifecycle of a row, in the order it happens. `stage()` is the ONLY
    // place that decides what a row is; badges, filters, counts and the index all read
    // it, so they cannot drift apart the way the wording did.
    //
    //   not-reviewed  nobody has looked
    //   arrived       a new translation came back -- read this one first
    //   approved      going to the website (with `edited` when it is the reviewer's text)
    //   queued        marked for a new translation, NOT sent yet
    //   sending       sent to Gemini, waiting
    //   failed        Gemini could not do it
__STAGE_JS__
    function stage(uid) { return stageOf(state[uid]); }

    var STAGE_BADGE = {
      todo:     ['Not reviewed', 'badge-partial'],
      arrived:  ['New translation', 'badge-proposed'],
      approved: ['Approved', 'badge-ok'],
      edited:   ['Approved · your wording', 'badge-ok'],
      queued:   ['Needs a new translation', 'badge-failed'],
      sending:  ['Being translated…', 'badge-partial'],
      failed:   ['Translation failed', 'badge-failed'],
      exported: ['In the export file', 'badge-ok'],
      live:     ['On the website', 'badge-ok']
    };

    function paint(tr) {
      var uid = tr.getAttribute('data-uid');
      var s = state[uid] || {};
      var badge = tr.querySelector('.desk-state');
      // The badge says what YOU decided; the reason line under the translation says
      // what the system noticed. They are different questions, so the badge must not
      // repeat "needs attention" directly beside a line already explaining why.
      // "Reworded" described what the reviewer DID; it said nothing about what
      // happens next, and what happens next is identical either way -- the wording
      // goes to the website. So both are Approved, and the edit is a note on it.
      var st = stage(uid);
      var spec = STAGE_BADGE[st];
      badge.className = 'desk-state ' + spec[1];
      badge.textContent = spec[0];
      badge.title = st === 'failed' && s.failed ? String(s.failed) : '';
      tr.setAttribute('data-stage', st);
      tr.classList.toggle('is-approved', st === 'approved' || st === 'edited' ||
                                          st === 'exported' || st === 'live');
      tr.classList.toggle('is-live', st === 'live');
      tr.classList.toggle('is-queued', st === 'queued');
      tr.classList.toggle('is-arrived', st === 'arrived');
      tr.classList.toggle('is-sending', st === 'sending');
      tr.classList.toggle('is-failed', st === 'failed');
      // A row Gemini is still working on must not be decided out from under it.
      tr.querySelectorAll('[data-act]').forEach(function (b) { b.disabled = st === 'sending'; });
      tr.classList.toggle('is-picked', !!picked[uid]);

      var bApprove = tr.querySelector('[data-act="approve"]');
      var bQueue = tr.querySelector('[data-act="queue"]');
      // The label lives in title/aria-label, so state is said there -- an icon button
      // with no text has nowhere else to say what it currently means. Neither is ever
      // disabled: the active one IS the undo.
      bApprove.classList.toggle('is-on', s.tray === 'csv');
      bApprove.title = s.tray === 'csv' ? 'Approved — click to undo'
        : 'Approve — this wording goes to the website when the import file is made';
      bApprove.setAttribute('aria-label', bApprove.title);
      bApprove.disabled = false;
      bQueue.classList.toggle('is-on', s.tray === 'draft');
      bQueue.title = s.tray === 'draft'
        ? 'Needs a new translation — click to undo'
        : 'Needs a new translation — ask Gemini to try again';
      bQueue.setAttribute('aria-label', bQueue.title);
      bQueue.disabled = false;

      var cb = tr.querySelector('[data-pick]');
      if (cb) cb.checked = !!picked[uid];

      // The reviewer's wording while there is one; the website's again once it is cleared.
      var live = tr.querySelector('.desk-live');
      var shown = s.text != null ? s.text : liveText[uid];
      if (live.textContent !== shown) live.textContent = shown;
    }

    function counts() {
      var csv = 0, draft = 0;
      for (var k in state) {
        if (!state[k]) continue;
        if (state[k].tray === 'csv') csv++;
        else if (state[k].tray === 'draft') draft++;
      }
      return { csv: csv, draft: draft };
    }

    function pickedIds() { return Object.keys(picked); }

    function paintBar() {
      paintLocaleCounts();
      var c = counts();
      var n = pickedIds().length;
      var all = unsavedByLocale();
      var unsaved = 0;
      for (var lc in all) unsaved += all[lc].n;
      selCount.textContent = n;
      barSelect.hidden = n === 0;
      // The bar stays while ANY language has unsaved work, so switching language can
      // never make pending work disappear from view.
      barTrays.hidden = (c.csv + c.draft) === 0 && unsaved === 0;
      savebar.hidden = barSelect.hidden && barTrays.hidden;
      var bits = [];
      if (c.csv) bits.push(c.csv + ' approved');
      if (c.draft) bits.push(c.draft + (c.draft === 1 ? ' needs' : ' need') + ' a new translation');
      trayLine.textContent = bits.join('  ·  ');
      var oc = document.getElementById('open-csv');
      var od = document.getElementById('open-draft');
      oc.disabled = !c.csv;
      od.disabled = !c.draft;
      oc.textContent = c.csv ? 'See ' + c.csv + ' approved' : 'See approved';
      od.textContent = c.draft ? 'See ' + c.draft + ' marked' : 'See marked';
      paintSave();
    }

    // ── Filters ────────────────────────────────────────────────────────
    // A row you have just acted on stays where it is. Without this, approving under
    // "Worth a look first" made the row vanish mid-click: the list shifted, the next
    // click landed on a different row, and there was no way to undo the thing you had
    // just done. Cleared whenever you change the view yourself.
    var justActed = Object.create(null);

    function matches(tr) {
      if (justActed[tr.getAttribute('data-uid')]) return true;
      var s = state[tr.getAttribute('data-uid')] || {};
      var p = fPage.value;
      if (p && (' ' + tr.getAttribute('data-pages') + ' ').indexOf(' ' + p + ' ') === -1) return false;
      var want = fState.value;
      var st = stage(tr.getAttribute('data-uid'));
      // Rows already on the website never appear in the work views. That is the
      // whole no-rework rule: the reviewer settled it, we exported it, Weglot serves
      // it. It stays reachable through "Already on the website" if they want to
      // change their mind, and acting on it puts it straight back in the queue.
      if (want === 'check' && !(tr.hasAttribute('data-why') && st === 'todo')) return false;
      if (want === 'arrived' && st !== 'arrived') return false;
      if (want === 'todo' && st !== 'todo') return false;
      if (want === 'csv' && !(st === 'approved' || st === 'edited')) return false;
      if (want === 'edited' && st !== 'edited') return false;
      if (want === 'exported' && st !== 'exported') return false;
      if (want === 'live' && st !== 'live') return false;
      if (want === 'draft' && st !== 'queued') return false;
      if (want === 'sending' && st !== 'sending') return false;
      if (want === 'failed' && st !== 'failed') return false;
      var q = fQ.value.trim().toLowerCase();
      if (q && tr.getAttribute('data-q').indexOf(q) === -1) return false;
      return true;
    }

    function shown() { return rows.filter(function (tr) { return !tr.hidden; }); }

    // Live counts on every option. An empty group is disabled rather than hidden, so
    // the list does not reshuffle under the cursor between renders.
    function paintFilterCounts() {
      var tally = { arrived: 0, check: 0, todo: 0, csv: 0, edited: 0,
                    draft: 0, sending: 0, failed: 0, exported: 0, live: 0 };
      rows.forEach(function (tr) {
        var st = stage(tr.getAttribute('data-uid'));
        if (st === 'arrived') tally.arrived++;
        else if (st === 'todo') { tally.todo++; if (tr.hasAttribute('data-why')) tally.check++; }
        else if (st === 'approved') tally.csv++;
        else if (st === 'edited') { tally.csv++; tally.edited++; }
        else if (st === 'queued') tally.draft++;
        else if (st === 'sending') tally.sending++;
        else if (st === 'failed') tally.failed++;
        else if (st === 'exported') tally.exported++;
        else if (st === 'live') tally.live++;
      });
      Array.prototype.forEach.call(fState.options, function (opt) {
        var base = opt.getAttribute('data-base') || opt.textContent;
        if (opt.value === '') { opt.textContent = base + ' (' + rows.length + ')'; return; }
        var n = tally[opt.value] || 0;
        opt.textContent = base + ' (' + n + ')';
        // Never disable the option currently selected, or the select goes blank.
        opt.disabled = n === 0 && opt.value !== fState.value;
      });
    }

    function applyFilters() {
      rows.forEach(function (tr) { tr.hidden = !matches(tr); });
      paintFilterCounts();
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
      var cur = (state[uid] || {}).tray;
      // Clicking the decision a row already carries UNDOES it. The earlier add-only
      // rule made a mis-click harmless but left no way back except the tray screen,
      // which is not where anyone looks. Undoing costs nothing -- nothing is sent
      // until a tray is explicitly submitted -- and a stray double-click is now
      // visible rather than silent, because the row loses its colour wash and the
      // icon stops being filled.
      justActed[uid] = 1;
      if (what === 'approve') {
        if (setTray(uid, cur === 'csv' ? null : 'csv',
                    cur === 'csv' ? 'un-approve' : 'approve')) {
          stampApproval(uid, tr, cur !== 'csv');
          persist(); paint(tr);
        }
      } else if (what === 'queue') {
        if (setTray(uid, cur === 'draft' ? null : 'draft',
                    cur === 'draft' ? 'un-queue' : 'queue')) { persist(); paint(tr); }
      } else if (what === 'edit') {
        toggleEditor(tr, tr.querySelector('.desk-editor').hidden);
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
      apply(row, btn.getAttribute('data-act'));
      paintBar();
      applyFilters();
    });

    // The editor is a small form, so it behaves like one: it opens on the current
    // wording, tracks whether that wording has changed, and never discards a change
    // without asking. Before this it had no controls at all -- it saved on blur, which
    // meant there was no way to close it without committing and no sign anything had
    // been committed.
    function toggleEditor(tr, open) {
      var wrap = tr.querySelector('.desk-editor');
      var live = tr.querySelector('.desk-live');
      var ta = tr.querySelector('.desk-edit');
      if (open) {
        var uid = tr.getAttribute('data-uid');
        var s = state[uid] || {};
        ta.value = s.text != null ? s.text : liveText[uid];
        ta.setAttribute('data-opened-with', ta.value);
        wrap.hidden = false;
        live.hidden = true;
        paintEditor(tr);
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      } else {
        wrap.hidden = true;
        live.hidden = false;
      }
    }

    function editorDirty(tr) {
      var ta = tr.querySelector('.desk-edit');
      return ta.value.trim() !== (ta.getAttribute('data-opened-with') || '').trim();
    }

    function paintEditor(tr) {
      var dirty = editorDirty(tr);
      tr.querySelector('.desk-editor-hint').textContent = dirty ? 'unsaved' : '';
      tr.querySelector('[data-edit="save"]').disabled = !dirty;
    }

    function commitEditor(ta) {
      var tr = ta.closest('.desk-row');
      if (!tr) return false;
      var uid = tr.getAttribute('data-uid');
      var val = ta.value.trim();
      var s = rec(uid);
      var changed = false;
      if (val && val !== liveText[uid] && val !== s.text) {
        s.text = val;
        note('edit', uid, null, null);
        // Typing the wording you want IS the decision; a separate Approve click
        // afterwards could only ever be "yes".
        setTray(uid, 'csv', 'edit-approve');
        var who = (window.__CEL_USER__ && window.__CEL_USER__.email) || '';
        if (who) s.by = who;
        s.at = new Date().toISOString();
        delete s.approvedAgainst;   // the wording is the reviewer's own, not the live one
        changed = true;
      } else if ((!val || val === liveText[uid]) && s.text != null) {
        // Emptying the box, or typing the website's wording back, both mean "no edit".
        delete s.text;
        note('edit-cleared', uid, null, null);
        // Clearing the box leaves a bare approval, and a bare approval has to record
        // the wording it was given to. Without this the row kept `tray:'csv'` with no
        // `approvedAgainst`, so the export skipped its drift check and shipped
        // whatever Weglot happened to be serving that day -- the exact substitution
        // `approvedAgainst` exists to refuse.
        if (s.tray === 'csv') stampApproval(uid, tr, true);
        changed = true;
      }
      if (changed) { persist(); paint(tr); paintBar(); }
      return changed;
    }

    // Nothing typed may be lost on the way out. `change` alone is not enough: it
    // fires on blur, and a click straight from an open editor onto a language link
    // races the navigation. So every open editor is committed BEFORE leaving --
    // localStorage writes are synchronous, so once this returns the work is safe.
    function flushEditors() {
      var any = false;
      Array.prototype.forEach.call(body.querySelectorAll('.desk-edit'), function (ta) {
        // `hidden` is on the WRAPPER, and HTMLElement.hidden does not reflect
        // ancestors -- so `ta.hidden` was always false and this committed EVERY
        // row's closed editor on the way out. On a fresh load a closed editor
        // holds the machine original, so the flush overwrote the reviewer's own
        // wording with the text they had rejected. Ask the wrapper, and require
        // the box to have actually been opened and changed.
        var wrap = ta.closest('.desk-editor');
        if (!wrap || wrap.hidden) return;
        if (!editorDirty(ta.closest('.desk-row'))) return;
        if (commitEditor(ta)) any = true;
      });
      if (any) applyFilters();
      return any;
    }

    body.addEventListener('input', function (ev) {
      if (ev.target.closest('.desk-edit')) paintEditor(ev.target.closest('.desk-row'));
    });

    body.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-edit]');
      if (!btn) return;
      var tr = btn.closest('.desk-row');
      if (btn.getAttribute('data-edit') === 'save') {
        if (commitEditor(tr.querySelector('.desk-edit'))) {
          applyFilters();
          toast('Your wording saved', { level: 'ok',
            detail: 'This row is approved and will use your wording.' });
        }
        toggleEditor(tr, false);
      } else {
        // Closing with changes is allowed, but never silently.
        if (editorDirty(tr) &&
            !window.confirm('Discard your changes to this wording?')) return;
        toggleEditor(tr, false);
      }
    });

    // Both doors out of this page.
    window.addEventListener('beforeunload', flushEditors);
    document.addEventListener('click', function (ev) {
      var link = ev.target.closest('a[data-loc]');
      if (link) flushEditors();
    }, true);

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
      var inFlight = ids.filter(function (uid) { return stage(uid) === 'sending'; });
      ids = ids.filter(function (uid) { return stage(uid) !== 'sending'; });
      if (!ids.length) {
        toast('Nothing changed', { level: 'warn',
          detail: inFlight.length + (inFlight.length === 1
            ? ' row is out for translation. It can be decided when it comes back.'
            : ' rows are out for translation. They can be decided when they come back.') });
        return;
      }
      var changed = 0;
      ids.forEach(function (uid) {
        if (!setTray(uid, tray, why)) return;
        changed++;
        if (tray === 'csv') {
          var row = rows.find(function (r) { return r.getAttribute('data-uid') === uid; });
          if (row) stampApproval(uid, row, true);
        }
      });
      note(why + ':bulk', null, String(ids.length), String(changed));
      picked = Object.create(null);
      lastPicked = -1;
      justActed = Object.create(null);   // a deliberate sweep may clear the view
      persist();
      rows.forEach(paint);
      paintBar(); applyFilters();
      var extra = changed !== ids.length ? (ids.length - changed) + ' were already set. ' : '';
      toast(changed + (changed === 1 ? ' row ' : ' rows ') +
            (tray === 'csv' ? 'approved' : 'marked for a new translation'), {
        level: 'ok',
        detail: extra + (tray === 'csv'
          ? 'They go to the website when you make the file.'
          : 'Nothing is sent to Gemini yet.')
      });
    }
    document.getElementById('bulk-approve').addEventListener('click', function () { bulk('csv', 'approve'); });
    document.getElementById('bulk-draft').addEventListener('click', function () { bulk('draft', 'queue'); });
    document.getElementById('bulk-clear').addEventListener('click', function () {
      picked = Object.create(null); lastPicked = -1;
      rows.forEach(paint); paintBar(); syncPickAll();
    });

    // ── Keyboard ───────────────────────────────────────────────────────
    // The keyboard cursor is a thin marker on the left edge, set by a class rather
    // than an inline outline. A 2px indigo outline around the whole row was loud
    // enough to read as an alert, and it appeared on every mouse click as well --
    // so simply using the page left a trail of heavy borders behind it.
    function focusRow(i) {
      if (cursor >= 0 && rows[cursor]) rows[cursor].classList.remove('is-cursor');
      cursor = i;
      if (i < 0 || !rows[i]) return;
      rows[i].classList.add('is-cursor');
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

    // The notices describe what IS, not what is planned. They used to promise a send
    // button and a make-the-file button, each with a confirmation step -- none of
    // which exists. A reviewer went looking for controls that were never built, and
    // the standing rule is to say what is not switched on, in their words.
    var TRAY_COPY = {
      draft: {
        title: 'Needs a new translation',
        one: 'row is marked for a fresh translation.',
        many: 'rows are marked for a fresh translation.',
        notice: 'Save keeps these marks so nobody has to find them again. ' +
                'Sending them to Gemini is not switched on yet — when it is, they go ' +
                'in one request and you see the count and the cost before anything is ' +
                'spent.'
      },
      csv: {
        title: 'Approved',
        one: 'row is approved and waiting to go to the website.',
        many: 'rows are approved and waiting to go to the website.',
        notice: 'Nothing reaches the website on its own. Save stores these approvals ' +
                'for everyone. Making the Weglot import file is not switched on yet; ' +
                'your approvals are kept and waiting for it.'
      }
    };

    // The review list is a working screen, not a confirmation dialog: the reviewer
    // came here to take things back out, so it supports the same multi-select the main
    // table does and puts Remove on every row as an icon rather than a word.
    var trayPicked = Object.create(null);

    function trayRows() {
      return rows.filter(function (tr) {
        var s = state[tr.getAttribute('data-uid')];
        return s && s.tray === openTray;
      });
    }

    function paintTrayFooter() {
      var listed = trayRows().length;
      var sel = Object.keys(trayPicked).length;
      var all = document.getElementById('tray-all');
      all.checked = listed > 0 && sel === listed;
      all.indeterminate = sel > 0 && sel < listed;
      document.getElementById('tray-selcount').textContent =
        sel ? sel + ' selected' : 'Select all';
      var rm = document.getElementById('tray-remove-sel');
      rm.disabled = sel === 0;
      rm.textContent = sel ? 'Undo ' + sel : 'Undo';
      document.getElementById('tray-empty').disabled = listed === 0;

      // The list used to offer nothing but Undo and Close: a basket with no way to
      // check out. Saving is the one step that actually exists today, and it is the
      // step that makes this work survive the tab -- so it belongs here, not only in
      // the bar behind the overlay.
      var ts = document.getElementById('tray-save');
      var allPending = unsavedByLocale(), pending = 0;
      for (var pc in allPending) pending += allPending[pc].n;
      ts.hidden = pending === 0;
      ts.disabled = saving;
      ts.textContent = saving ? 'Saving…'
                              : 'Save ' + pending + (pending === 1 ? ' change' : ' changes');
      ts.title = 'Store your decisions so they survive this tab and reach anyone else reviewing';
    }

    function removeFromTray(uids) {
      uids.forEach(function (uid) { setTray(uid, null, 'take-back'); delete trayPicked[uid]; });
      persist();
      rows.forEach(paint);
      paintBar(); applyFilters(); paintTray();
      toast('Undone', { level: 'warn',
        detail: uids.length + (uids.length === 1 ? ' row is' : ' rows are') + ' back to Not reviewed.' });
    }

    function paintTray() {
      if (!openTray) return;
      var copy = TRAY_COPY[openTray];
      var listed = trayRows();
      var n = listed.length;
      document.getElementById('tray-title').textContent = copy.title;
      document.getElementById('tray-summary').textContent =
        n + ' ' + (n === 1 ? copy.one : copy.many);
      document.getElementById('tray-notice').textContent = copy.notice;

      trayList.textContent = '';
      listed.forEach(function (tr) {
        var uid = tr.getAttribute('data-uid');
        var li = document.createElement('li');
        li.className = 'desk-review-item';

        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'desk-pick';
        cb.checked = !!trayPicked[uid];
        cb.setAttribute('aria-label', 'Select this row');
        cb.addEventListener('change', function () {
          if (cb.checked) trayPicked[uid] = 1; else delete trayPicked[uid];
          paintTrayFooter();
        });

        var texts = document.createElement('div');
        texts.className = 'desk-review-texts';
        var src = document.createElement('p');
        src.className = 'desk-review-src';
        src.textContent = tr.querySelector('.desk-srctext').textContent;
        var tgt = document.createElement('p');
        tgt.className = 'desk-review-tgt';
        // Paragraph direction follows the text, as in the table (see `.desk-live`).
        tgt.setAttribute('dir', 'auto');
        var st = state[uid] || {};
        tgt.textContent = st.text != null ? st.text : liveText[uid];
        texts.appendChild(src); texts.appendChild(tgt);

        var rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'desk-btn desk-icon-btn';
        rm.title = 'Undo — back to Not reviewed';
        rm.setAttribute('aria-label', 'Undo this row');
        rm.appendChild(icon('undo'));
        rm.addEventListener('click', function () { removeFromTray([uid]); });

        li.appendChild(cb); li.appendChild(texts); li.appendChild(rm);
        trayList.appendChild(li);
      });

      paintTrayFooter();
      if (!n) closeOverlays();
    }

    document.getElementById('tray-all').addEventListener('change', function (ev) {
      trayPicked = Object.create(null);
      if (ev.target.checked) trayRows().forEach(function (tr) {
        trayPicked[tr.getAttribute('data-uid')] = 1;
      });
      Array.prototype.forEach.call(trayList.querySelectorAll('.desk-pick'), function (cb) {
        cb.checked = ev.target.checked;
      });
      paintTrayFooter();
    });

    document.getElementById('tray-remove-sel').addEventListener('click', function () {
      removeFromTray(Object.keys(trayPicked));
    });

    document.getElementById('tray-done').addEventListener('click', closeOverlays);
    document.getElementById('tray-save').addEventListener('click', function () {
      // Stay on the list while it saves -- the reviewer is looking at exactly the
      // rows being stored, and closing the overlay would hide the outcome.
      save().then(paintTrayFooter, paintTrayFooter);
      paintTrayFooter();
    });

    function showTray(which) {
      openTray = which;
      trayPicked = Object.create(null);   // a fresh visit starts with nothing selected
      paintTray();
      trayOverlay.hidden = false;
      document.getElementById('tray-done').focus();
    }

    document.getElementById('open-draft').addEventListener('click', function () { showTray('draft'); });
    document.getElementById('open-csv').addEventListener('click', function () { showTray('csv'); });
    document.getElementById('tray-empty').addEventListener('click', function () {
      if (!openTray) return;
      var listed = trayRows().length;
      if (!window.confirm('Undo all ' + listed + ' rows? They go back to Not reviewed.')) return;
      var n = 0;
      for (var k in state) {
        if (state[k] && state[k].tray === openTray) { setTray(k, null, 'empty-tray'); n++; }
      }
      note('empty-tray', null, openTray, String(n));
      persist(); rows.forEach(paint); paintBar(); applyFilters(); closeOverlays();
      toast('Undone', { level: 'warn',
        detail: n + (n === 1 ? ' row is back to Not reviewed.' : ' rows are back to Not reviewed.') });
    });

    // ── Export / import ────────────────────────────────────────────────
    // Decisions live in this browser, which means they do not survive a different
    // machine and cannot be read by the batch or CSV steps. This file is the handoff:
    // the reviewer exports it, it goes into the repo, and the pipeline consumes it.
    // A one-click save would need the dispatch Worker's workflow allowlist extended
    // and the Worker redeployed -- a security boundary, deliberately not touched here.
    // Still reachable from the console for support ("send me what you have"), but not
    // a button: asking the reviewer to take backups spends the time this project
    // exists to save, and durability is the system's job.
    window.deskExport = function () {
      var c = counts();
      return {
        schema: 'cel-localization-desk/1', locale: CODE,
        counts: { csv: c.csv, draft: c.draft, total_rows: rows.length },
        decisions: state, history: hist
      };
    };

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
      // Counted per KIND, because one number cannot honestly describe a document
      // that mixes arrivals, failures and reconciliation results -- the toast used
      // to announce "new translations arrived" over a batch of nothing but errors.
      var n = 0, nArrived = 0, nFailed = 0, nLive = 0;
      for (var uid in incoming) {
        if (!incoming[uid]) continue;
        var s = rec(uid);
        // Merge, never replace: a returning batch carries only the rows it was asked
        // about, and must not erase decisions made on every other row.
        //
        // These are exactly the fields the batch sets at each step of the lifecycle:
        // `sentAt` when a request goes to Gemini, then `arrivedAt` + `text` when the
        // new wording comes back, or `failed` when it does not. A row that has arrived
        // drops its tray, so it reads as a fresh translation waiting to be looked at
        // rather than something still queued.
        var inc = incoming[uid];
        if (inc.sentAt) { s.sentAt = inc.sentAt; delete s.arrivedAt; delete s.failed; n++; }
        if (inc.arrivedAt) {
          s.arrivedAt = inc.arrivedAt;
          delete s.tray; delete s.failed;
          if (typeof inc.text === 'string') s.text = inc.text;
          n++; nArrived++;
        }
        if (inc.failed) { s.failed = String(inc.failed); delete s.sentAt; n++; nFailed++; }
        if (inc.tray && !inc.arrivedAt) { s.tray = inc.tray; n++; }
        // Set by the CSV build and by reconciliation, respectively.
        if (inc.exportedAt) { s.exportedAt = inc.exportedAt; n++; }
        if (inc.liveAt) { s.liveAt = inc.liveAt; delete s.exportedAt; n++; nLive++; }
      }
      note('ingest', null, String(n), doc.exported_at || null);
      persist();
      rows.forEach(paint); paintBar(); applyFilters();
      if (n) {
        var said = [];
        if (nArrived) said.push(nArrived + (nArrived === 1 ? ' new translation to read.'
                                                          : ' new translations to read.'));
        if (nFailed) said.push(nFailed + (nFailed === 1 ? ' translation failed.'
                                                        : ' translations failed.'));
        if (nLive) said.push(nLive + (nLive === 1 ? ' is now on the website.'
                                                 : ' are now on the website.'));
        toast(n + (n === 1 ? ' row updated' : ' rows updated'),
              { level: nFailed ? 'warn' : 'ok', detail: said.join(' ') });
      }
      return { ok: true, rows: n };
    }
    window.deskIngest = ingest;


    // ── Saving ─────────────────────────────────────────────────────────
    // `saved` is what the repo is known to hold. Everything that differs from it is
    // unsaved work, and only the difference is sent -- a whole locale of approvals is
    // 61-66 KB base64 against a 65,536-byte workflow_dispatch ceiling (chunksFor splits
    // it), and sending deltas also means two people reviewing different pages of one
    // language merge instead of clobbering.
    var SAVEDKEY = 'cel-desk-saved-' + CODE;
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(SAVEDKEY) || '{}') || {}; } catch (e) { saved = {}; }

    var btnSave = document.getElementById('btn-save');
    var saveStatus = document.getElementById('save-status');
    var saving = false;

    // Every field `stage()` reads. Five of these used to be left behind by both the
    // comparison and the delta, so `sending`, `arrived`, `failed`, `exported` and
    // `live` existed only in the browser that produced them -- and `liveAt`, which
    // is what stops an already-published row being exported a second time, could
    // never reach the server that does the exporting.
    var SAVE_FIELDS = ['tray', 'text', 'rejected', 'by', 'at', 'approvedAgainst',
                       'sentAt', 'arrivedAt', 'failed', 'exportedAt', 'liveAt'];

    // A record is worth keeping if it carries a decision OR any lifecycle stamp.
    // Keying this on `tray` alone told the server to forget a row that was out for
    // translation.
    function hasContent(r) {
      if (!r) return false;
      for (var i = 0; i < SAVE_FIELDS.length; i++) {
        var v = r[SAVE_FIELDS[i]];
        if (v !== undefined && v !== null) return true;
      }
      return false;
    }

    function sameDecision(a, b) {
      if (!a && !b) return true;
      if (!a || !b) return false;
      for (var i = 0; i < SAVE_FIELDS.length; i++) {
        var k = SAVE_FIELDS[i];
        // `approvedAgainst` belongs here: without it, re-approving a row whose
        // wording had moved produced no delta, the server kept the stale snapshot,
        // and the export skipped the row as "changed since approval" for ever.
        if (JSON.stringify(a[k] === undefined ? null : a[k]) !==
            JSON.stringify(b[k] === undefined ? null : b[k])) return false;
      }
      return true;
    }

    function deltaBetween(now, was) {
      var out = {}, n = 0, ids = {};
      for (var k in now) ids[k] = 1;
      for (var k2 in was) ids[k2] = 1;
      for (var uid in ids) {
        var mine = hasContent(now[uid]) ? now[uid] : null;
        var theirs = was[uid] || null;
        if (sameDecision(mine, theirs)) continue;
        // null is how the server is told to forget a unit.
        if (mine) {
          var row = {};
          SAVE_FIELDS.forEach(function (f) {
            if (mine[f] !== undefined) row[f] = mine[f];
          });
          out[uid] = row;
        } else {
          out[uid] = null;
        }
        n++;
      }
      return { body: out, n: n };
    }

    function delta() { return deltaBetween(state, saved); }

    // Unsaved work is a fact about the REVIEWER, not about the page they happen to be
    // looking at. Making five changes in German, switching to French and finding an
    // empty bar reads as "nothing pending" -- and the tab gets closed. Every language
    // is counted, always.
    function readLocale(code) {
      try { return JSON.parse(localStorage.getItem('cel-desk-' + code) || '{}') || {}; }
      catch (e) { return {}; }
    }
    function readSaved(code) {
      try { return JSON.parse(localStorage.getItem('cel-desk-saved-' + code) || '{}') || {}; }
      catch (e) { return {}; }
    }

    function unsavedByLocale() {
      var out = {};
      LOCALES.forEach(function (code) {
        var d = code === CODE ? delta()
                              : deltaBetween(readLocale(code), readSaved(code));
        if (d.n) out[code] = d;
      });
      return out;
    }

    function paintSave() {
      var all = unsavedByLocale();
      var total = 0, others = 0;
      for (var c in all) { total += all[c].n; if (c !== CODE) others += all[c].n; }
      btnSave.hidden = total === 0 || saving;
      btnSave.textContent = 'Save ' + total + (total === 1 ? ' change' : ' changes');
      btnSave.disabled = saving;
      btnSave.title = others
        ? others + ' of them are in another language — Save stores every language at once'
        : '';
      var note = document.getElementById('save-elsewhere');
      if (note) {
        note.hidden = others === 0;
        note.textContent = others ? '· ' + others + ' unsaved in other languages' : '';
      }
    }

    // A reviewer has no model of a workflow run, an underscored status or an HTTP
    // code. The raw value still goes to note('save-failed'), where it can be read
    // when something needs diagnosing; it does not go on screen.
    var FAILURE_WORDS = {
      'startup_failure': 'the save could not be started',
      'cancelled': 'the save was cancelled',
      'timed_out': 'the save took too long',
      'failure': 'the server could not store it'
    };
    function humanFailure(msg) {
      msg = String(msg || '');
      for (var k in FAILURE_WORDS) if (msg.indexOf(k) !== -1) return FAILURE_WORDS[k];
      if (msg.indexOf('timed out') !== -1) return 'the save is taking longer than expected';
      if (msg.indexOf('HTTP 4') !== -1) return 'the server refused the save';
      if (msg.indexOf('HTTP 5') !== -1) return 'the server is having trouble';
      if (msg.indexOf('cannot confirm') !== -1) return msg;
      return 'the save did not complete';
    }

    var RUN_WORDS = {
      'queued': 'starting…', 'waiting': 'starting…', 'pending': 'starting…',
      'in_progress': 'saving…', 'requested': 'starting…'
    };

    function callProxy(payload) {
      var url = window.CEL_DISPATCH_URL;
      if (!url) return Promise.reject(new Error('Saving is not configured on this site yet.'));
      var m = document.cookie.match(/(?:^|; )cel_session=([^;]*)/);
      payload.token = m ? m[1] : '';
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (j) {
          return { status: resp.status, ok: resp.ok && j.ok !== false, body: j };
        });
      });
    }

    // The newest run of a workflow is NOT necessarily the run we just started.
    // Locales are saved one after another, so by the time the second one
    // dispatches, the newest run is the FIRST one -- already completed, already
    // successful. Polling without a baseline banked every locale after the first
    // against its predecessor's result and told the reviewer it was safe to close
    // the page. So: read the newest run id BEFORE dispatching, and accept only a
    // run that is not that one.
    function latestRunId(workflow) {
      return callProxy({ action: 'poll', workflow: workflow }).then(function (r) {
        // A failed poll is NOT "no runs yet": that answer means "any run is ours", and
        // on the fallback path it let another reviewer's run confirm this save.
        if (!r.ok) return undefined;
        var run = r.body && r.body.run ? r.body.run : null;
        if (!run) return null;                       // no runs yet; any run is ours
        return run.id != null ? run.id : undefined;  // undefined = worker too old
      }).catch(function () { return undefined; });
    }

    function awaitRun(workflow, baselineId) {
      var start = Date.now();
      function tick() {
        return callProxy({ action: 'poll', workflow: workflow }).then(function (r) {
          var run = r.ok && r.body && r.body.run ? r.body.run : null;
          if (run && run.id == null) {
            // Without a run id we cannot tell our run from the last one, and a
            // wrong "saved" is worse than an honest "unconfirmed".
            throw new Error('this site cannot confirm the save yet');
          }
          var isOurs = run && (baselineId === null || run.id !== baselineId);
          if (isOurs && run.status === 'completed') return run;
          if (Date.now() - start > 90000) return null;   // report a timeout, not a lie
          saveStatus.textContent = isOurs ? (RUN_WORDS[run.status] || 'saving…')
                                          : 'starting…';
          return new Promise(function (res) { setTimeout(function () { res(tick()); }, 3000); });
        });
      }
      if (baselineId === undefined) {
        return Promise.reject(new Error('this site cannot confirm the save yet'));
      }
      return tick();
    }

    function awaitRunId(workflow, runId) {
      var start = Date.now();
      function tick() {
        return callProxy({ action: 'poll', workflow: workflow, run_id: runId }).then(function (r) {
          var run = r.ok && r.body && r.body.run ? r.body.run : null;
          if (run && run.status === 'completed') return run;
          if (Date.now() - start > 90000) return null;   // report a timeout, not a lie
          saveStatus.textContent = run ? (RUN_WORDS[run.status] || 'saving…') : 'starting…';
          return new Promise(function (res) { setTimeout(function () { res(tick()); }, 3000); });
        });
      }
      return tick();
    }

    async function encodeFor(locale, body) {
      var doc = { schema: 'cel-localization-desk/1', locale: locale, decisions: body };
      var bytes = new TextEncoder().encode(JSON.stringify(doc));
      var gz = new Response(
        new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'))
      );
      var buf = new Uint8Array(await gz.arrayBuffer());
      var bin = '';
      for (var i = 0; i < buf.length; i++) bin += String.fromCharCode(buf[i]);
      return btoa(bin);
    }

    // A workflow_dispatch input is capped at 65,536 bytes. A whole locale of
    // approvals measures 61-66 KB base64 -- Arabic is OVER the limit and Japanese
    // clears it by 87 bytes -- and "select all, Approve, Save" is the ordinary way
    // to get there. So the payload is split until every piece fits. The workflow
    // MERGES rather than replaces, so several dispatches for one locale are safe.
    var MAX_B64 = 60000;

    async function chunksFor(locale, body) {
      var uids = Object.keys(body);
      if (!uids.length) return [];
      var out = [], queue = [uids];
      while (queue.length) {
        var part = queue.shift();
        var sub = {};
        part.forEach(function (u) { sub[u] = body[u]; });
        var enc = await encodeFor(locale, sub);
        if (enc.length <= MAX_B64) { out.push(enc); continue; }
        if (part.length === 1) {
          throw new Error('one row is too large to send (' + part[0] + ')');
        }
        var mid = Math.ceil(part.length / 2);
        queue.unshift(part.slice(mid));
        queue.unshift(part.slice(0, mid));
      }
      return out;
    }

    async function saveOne(locale, d) {
      var parts = await chunksFor(locale, d.body);
      for (var i = 0; i < parts.length; i++) {
        if (parts.length > 1) {
          saveStatus.textContent = 'saving ' + locale.toUpperCase() +
                                   ' (part ' + (i + 1) + ' of ' + parts.length + ')…';
        }
        // Probe BEFORE dispatching. A Worker that cannot name runs answers the poll
        // without an id; dispatching anyway let the save land in the repo and then
        // told the reviewer "Not saved -- try again", and every retry dispatched it
        // once more. Refusing here is the honest version of "cannot confirm".
        var baseline = await latestRunId('localization-save.yml');
        if (baseline === undefined) throw new Error('this site cannot confirm the save yet');
        var r = await callProxy({
          action: 'dispatch', workflow: 'localization-save.yml',
          inputs: { locale: locale, payload: parts[i] }
        });
        if (!r.ok) throw new Error('HTTP ' + r.status + (r.body && r.body.error ? ': ' + r.body.error : ''));
        // The dispatch names the run it created. Follow THAT run: "the newest run
        // that is not the baseline" is another reviewer's run whenever two people
        // save one language, and GitHub's concurrency group can cancel ours while
        // theirs succeeds. The baseline is only the fallback for a Worker that
        // cannot say which run it started.
        var runId = r.body && r.body.run_id != null ? r.body.run_id : null;
        var run = runId !== null ? await awaitRunId('localization-save.yml', runId)
                                 : await awaitRun('localization-save.yml', baseline);
        if (!run) throw new Error('timed out waiting for the run');
        if (run.conclusion !== 'success') throw new Error(run.conclusion || 'failed');
      }
    }

    async function save() {
      if (saving) return;                    // one save in flight, never two
      var all = unsavedByLocale();
      var codes = Object.keys(all);
      if (!codes.length) return;
      var total = 0;
      codes.forEach(function (c) { total += all[c].n; });

      saving = true; paintSave();
      saveStatus.textContent = 'saving…';
      saveStatus.className = 'desk-status';

      // Snapshot BEFORE sending. Anything decided while the run is in flight stays
      // unsaved rather than being marked clean without ever having been sent.
      var snaps = {};
      codes.forEach(function (c) {
        snaps[c] = JSON.parse(JSON.stringify(c === CODE ? state : readLocale(c)));
      });

      var done = [], failed = null;
      try {
        for (var i = 0; i < codes.length; i++) {
          var c = codes[i];
          if (codes.length > 1) {
            saveStatus.textContent = 'saving ' + c.toUpperCase() +
                                     ' (' + (i + 1) + ' of ' + codes.length + ')…';
          }
          await saveOne(c, all[c]);
          // Bank each language as it lands. A failure on the fourth must not throw
          // away the three that already succeeded.
          var next = {};
          for (var uid in snaps[c]) {
            if (hasContent(snaps[c][uid])) next[uid] = snaps[c][uid];
          }
          try { localStorage.setItem('cel-desk-saved-' + c, JSON.stringify(next)); } catch (e) {}
          if (c === CODE) saved = next;
          done.push(c);
        }
      } catch (err) {
        failed = err;
      }

      saving = false;
      paintSave(); paintBar();

      if (!failed) {
        note('save', null, String(total), codes.join(','));
        saveStatus.textContent = '';
        toast('Saved', { level: 'ok',
          detail: total + (total === 1 ? ' change is' : ' changes are') +
                  ' stored' + (codes.length > 1 ? ' across ' + codes.length + ' languages' : '') +
                  '. Safe to close this page or carry on from another computer.' });
      } else {
        saveStatus.textContent = 'not saved';
        saveStatus.className = 'desk-status is-error';
        note('save-failed', null, failed.message, done.join(','));
        toast(done.length ? 'Saved ' + done.length + ' of ' + codes.length + ' languages'
                          : 'Not saved',
              { level: 'err',
                detail: 'Nothing was lost — ' +
                        (done.length ? 'the rest is' : 'your work is') +
                        ' still on this page. Try Save again. (' +
                        humanFailure(failed.message) + ')' });
      }
    }

    btnSave.addEventListener('click', save);

    // ── Toasts ─────────────────────────────────────────────────────────
    // Confirmation for things that already happen and currently say nothing:
    // approving 48 rows in one click gave no feedback at all. Errors stay until
    // dismissed; everything else clears itself, and hovering holds it open so a
    // message cannot vanish while it is being read.
    var toastStack = document.getElementById('toast-stack');

    function toast(title, opts) {
      opts = opts || {};
      var el = document.createElement('div');
      el.className = 'toast' + (opts.level ? ' is-' + opts.level : '');
      var bodyEl = document.createElement('div');
      bodyEl.className = 'toast-body';
      var h = document.createElement('p');
      h.className = 'toast-title';
      h.textContent = title;
      bodyEl.appendChild(h);
      if (opts.detail) {
        var d = document.createElement('p');
        d.className = 'toast-detail';
        d.textContent = opts.detail;
        bodyEl.appendChild(d);
      }
      var x = document.createElement('button');
      x.type = 'button';
      x.className = 'toast-close';
      x.setAttribute('aria-label', 'Dismiss');
      x.textContent = '\u00d7';
      var timer = null;
      function close() {
        if (timer) clearTimeout(timer);
        if (el.parentNode) el.parentNode.removeChild(el);
      }
      x.addEventListener('click', close);
      el.appendChild(bodyEl);
      el.appendChild(x);
      toastStack.appendChild(el);

      // An error is a thing to act on, so it waits for the reader.
      if (opts.level !== 'err' && !opts.sticky) {
        var arm = function () { timer = setTimeout(close, opts.ms || 5000); };
        el.addEventListener('mouseenter', function () { if (timer) clearTimeout(timer); });
        el.addEventListener('mouseleave', arm);
        arm();
      }
      // Keep the stack short enough to stay readable.
      while (toastStack.children.length > 4) toastStack.removeChild(toastStack.firstChild);
      return close;
    }
    window.deskToast = toast;

    // ── URL state + language switching ─────────────────────────────────
    // The filters live in the query string so that switching language keeps you on
    // the same page and the same view. Before this, changing language meant going
    // back to the index and setting the filters up again.
    function syncUrl() {
      var q = new URLSearchParams();
      if (fPage.value) q.set('page', fPage.value);
      if (fState.value) q.set('show', fState.value);
      if (fQ.value.trim()) q.set('q', fQ.value.trim());
      var qs = q.toString();
      history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
      Array.prototype.forEach.call(document.querySelectorAll('[data-loc]'), function (a) {
        a.setAttribute('href', '/admin/localization/' + a.getAttribute('data-loc') + '/' + (qs ? '?' + qs : ''));
      });
    }

    // Each language tab carries its OUTSTANDING count -- rows worth a look that nobody
    // has decided yet -- so "where is there work left" is answerable without visiting
    // all eight. It used to count rows already DECIDED, the opposite: a tab you had
    // finished showed a number and a tab you had not started showed nothing.
    function paintLocaleCounts() {
      Array.prototype.forEach.call(document.querySelectorAll('[data-loc-count]'), function (el) {
        var lc = el.getAttribute('data-loc-count');
        var recs = lc === CODE ? state : readLocale(lc);
        var n = (WORTH[lc] || []).filter(function (uid) {
          return stageOf(recs[uid]) === 'todo';
        }).length;
        el.textContent = n ? String(n) : '';
        el.hidden = !n;
        var link = el.parentNode;
        var nm = link && link.querySelector('.desk-loc-name');
        // The name is visually hidden on inactive tabs; a hover says it, and the count.
        if (nm) link.title = nm.textContent + (n ? ' — ' + n + ' worth a look' : '');
      });
    }

    function resetView() {
      justActed = Object.create(null);   // changing the view is when rows may move
      applyFilters();
      syncUrl();
    }
    [fPage, fState].forEach(function (el) { el.addEventListener('change', resetView); });
    fQ.addEventListener('input', resetView);

    // ── Boot ───────────────────────────────────────────────────────────
    fetch('units.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(async function (units) {
        buildRows(units);
        // What the repo holds is the baseline. Anything decided in THIS browser and
        // not yet saved stays exactly as it is and still counts as unsaved -- the
        // server copy fills in only the units this browser has never touched, which
        // is what makes a second machine useful instead of blank.
        try {
          var dr = await fetch('decisions.json', { cache: 'no-cache' });
          if (dr.ok) {
            var ddoc = await dr.json();
            var server = (ddoc && ddoc.decisions) || {};
            var adopted = 0;
            for (var uid in server) {
              if (!hasContent(server[uid])) continue;
              saved[uid] = server[uid];
              // Adopt only where this browser holds NOTHING. The old test was
              // "no tray", which is not the same thing: a row that had come back
              // from Gemini, and a row the reviewer had deliberately un-approved
              // before saving, both have no tray -- and both were overwritten
              // wholesale. The first threw away a translation already paid for;
              // the second made the undo silently revert on reload.
              if (!hasContent(state[uid])) {
                state[uid] = JSON.parse(JSON.stringify(server[uid]));
                adopted++;
              }
            }
            try { localStorage.setItem(SAVEDKEY, JSON.stringify(saved)); } catch (e) {}
            persist();
            if (adopted) note('adopted', null, String(adopted), null);
          } else if (dr.status !== 404) {
            throw new Error('HTTP ' + dr.status);
          }
        } catch (e) {
          // A missing file is the normal first-run case. A 5xx, a CDN failure or
          // malformed JSON on a file that DOES exist is not: the desk would boot
          // showing none of a colleague's decisions, and the next save -- merged
          // last-writer-wins per unit -- would erase them.
          if (!(e instanceof TypeError && !navigator.onLine)) {
            note('decisions-load-failed', null, String(e && e.message || e), null);
          }
          toast('Could not read what is already saved', { level: 'warn',
            detail: 'This page may not be showing decisions made elsewhere. ' +
                    'Reload before you review, or your save could overwrite them.' });
        }
        // ?show= lets the locale index link straight into a tray.
        var qs = new URLSearchParams(location.search);
        var want = qs.get('show');
        var known = ['todo', 'csv', 'draft', 'edited', 'check', 'arrived',
                     'sending', 'failed', 'exported', 'live', ''];
        if (want !== null && known.indexOf(want) !== -1) {
          fState.value = want;
        } else if (rows.some(function (tr) { return stage(tr.getAttribute('data-uid')) === 'arrived'; })) {
          // Coming back after a batch, the question is "what came back", not "where
          // was I". Land on exactly those rows without being asked.
          fState.value = 'arrived';
        }
        if (qs.get('page')) fPage.value = qs.get('page');
        if (qs.get('q')) fQ.value = qs.get('q');
        rows.forEach(paint);
        paintBar();
        applyFilters();
        syncUrl();
        paintLocaleCounts();
        note('load', null, String(units.length), null);
      })
      .catch(function (err) {
        // Say so in the page. A desk that silently shows zero rows looks like
        // "nothing to review", which is the opposite of what has happened.
        countLine.textContent = 'Could not load the units (' + err.message + ').';
        countLine.className = 'subtle desk-status is-error';
        noRows.hidden = true;
        note('load-failed', null, err.message, null);
        toast('Could not load this language', {
          level: 'err',
          detail: err.message + ' — reload, and tell us if it keeps happening.'
        });
      });
  })();
  </script>
""".replace("__STAGE_JS__", _STAGE_JS).replace("__WORTH__", worth_js).replace(
    "__CODE__", code).replace("__RTL__", "true" if rtl else "false").replace(
    "__LOCALES__", json.dumps([c for c, *_ in LOCALES]))


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

    for code, name, endonym, direction, _flag in LOCALES:
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
