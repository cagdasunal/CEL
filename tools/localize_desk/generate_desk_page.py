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
Taking something back out is deliberate, from the review list (ruling 18), where the
reviewer can see what they are removing.

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

from localize_desk.copy_text import JS_HELPERS, block_html, js_table, t, tn  # noqa: E402
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

# code, endonym, direction, flag. The English NAME is copy and lives in COPY.md
# (`lang.<code>`), like every other word on screen. Codes are the ones the unit files
# carry (`pt`, not `pt-BR`) so the desk and the data cannot drift apart. `pt` is
# Brazilian Portuguese for CEL, hence Brazil rather than Portugal. Arabic has no
# country, so it takes the one the client's own locale list implies; the language name
# is always available beside the flag precisely because a flag is not a language.
LOCALES = [
    ("de", "Deutsch", "ltr", "\U0001F1E9\U0001F1EA"),
    ("fr", "Français", "ltr", "\U0001F1EB\U0001F1F7"),
    ("es", "Español", "ltr", "\U0001F1EA\U0001F1F8"),
    ("pt", "Português", "ltr", "\U0001F1E7\U0001F1F7"),
    ("it", "Italiano", "ltr", "\U0001F1EE\U0001F1F9"),
    ("ja", "日本語", "ltr", "\U0001F1EF\U0001F1F5"),
    ("ko", "한국어", "ltr", "\U0001F1F0\U0001F1F7"),
    ("ar", "العربية", "rtl", "\U0001F1F8\U0001F1E6"),
]
_LOCALE = {code: (endonym, direction, flag) for code, endonym, direction, flag in LOCALES}

# The four pages, by the key the unit files carry; their labels are copy (`page.<key>`).
PAGE_KEYS = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]


def lang_name(code: str) -> str:
    return t(f"lang.{code}")


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


def _how_modal() -> str:
    """The help window. Its body is the `how.body` block in COPY.md."""
    return (
        '  <div class="cpw-overlay" id="how-overlay" hidden>\n'
        '    <div class="cpw-modal desk-modal-wide" role="dialog" aria-modal="true" aria-labelledby="how-title">\n'
        f'      <h2 class="cpw-title" id="how-title">{escape(t("how.title"))}</h2>\n'
        f'      <div class="desk-modal-body">\n{block_html("how.body")}\n      </div>\n'
        '      <div class="cpw-actions">\n'
        f'        <button type="button" class="cpw-btn cpw-save" id="how-close">{escape(t("how.close"))}</button>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
    )


def _review_modal() -> str:
    """The approved / requested list window. Its moving parts are filled in by the page."""
    close = escape(t("list.close"))
    return f"""\
  <div class="cpw-overlay" id="tray-overlay" hidden>
    <div class="desk-review" role="dialog" aria-modal="true" aria-labelledby="tray-title">
      <header class="desk-review-head">
        <div>
          <h2 class="desk-review-title" id="tray-title"></h2>
          <p class="desk-review-sub" id="tray-summary"></p>
        </div>
        <button type="button" class="desk-icon-btn desk-review-x" id="tray-close"
                data-tip="{close}" aria-label="{close}">&#215;</button>
      </header>
      <div class="desk-review-toolbar">
        <label class="desk-review-all">
          <input type="checkbox" class="desk-pick" id="tray-all"
                 aria-label="{escape(t("list.select_all.label"))}">
          <span id="tray-all-label">{escape(t("list.select_all"))}</span>
        </label>
        <span class="desk-savebar-spacer"></span>
        <button type="button" class="desk-btn" id="tray-remove-sel" disabled>{escape(t("list.undo"))}</button>
        <button type="button" class="desk-btn" id="tray-empty">{escape(t("list.undo_all"))}</button>
      </div>
      <ul class="desk-review-list" id="tray-list"></ul>
      <footer class="desk-review-foot">
        <p class="desk-notice" id="tray-notice"></p>
        <div class="desk-review-actions">
          <button type="button" class="desk-btn" id="tray-done">{close}</button>
          <button type="button" class="desk-btn is-primary" id="tray-save" hidden></button>
        </div>
      </footer>
    </div>
  </div>
"""


def render_index(units: list[dict]) -> str:
    total = len(units)
    parts = _head(t("meta.index.title"), t("meta.index.description"))
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    parts.append(render_page_chrome(escape(t("index.eyebrow")), escape(t("index.subtitle"))))
    parts.append('    <main class="dashboard-main">')
    parts.append('      <section class="status status-ok">')
    parts.append(f'        <p class="status-label">{escape(t("index.intro.title"))}</p>')
    parts.append(f'        <p>{escape(t("index.intro.text", total=total, pages=len(PAGE_KEYS)))}</p>')
    parts.append("      </section>")

    # The WHOLE card opens the language. It used to be a card of plain-looking text with
    # one link hidden in the heading, and nothing on it looked clickable (operator,
    # 2026-09-23). The heading link is stretched over the card (`.desk-locale-open::after`)
    # and a real button says what the click does; the chips stay separately clickable.
    parts.append('      <div class="desk-locales">')
    for code, endonym, _dir, flag in LOCALES:
        name = lang_name(code)
        have = sum(1 for u in units if (u.get("current") or {}).get(code))
        # The flagged count is the only number that is useful on a FIRST visit:
        # decisions all start at zero, so without it every card said the same thing.
        flagged = len(worth_a_look(code, units))
        start = f"/admin/localization/{code}/?show={'check' if flagged else 'todo'}"
        stat = (tn("index.card.flagged", flagged) if flagged else t("index.card.flagged.none"))
        parts.append(
            f'        <div class="desk-locale-card" data-locale="{code}" '
            f'data-name="{escape(name)}" '
            f'data-total="{have}" data-flagged="{flagged}">'
        )
        parts.append(
            f'          <a class="desk-locale-open" href="{start}" '
            f'aria-label="{escape(t("index.card.open", language=name))}">'
            f'<span class="desk-loc-flag" aria-hidden="true">{flag}</span> '
            f'<span class="desk-locale-name">{escape(name)}</span></a>'
        )
        parts.append(
            f'          <p class="desk-locale-sub"><bdi>{escape(endonym)}</bdi> '
            f'&middot; {escape(t("index.card.texts", total=have))}</p>'
        )
        parts.append('          <div class="desk-meter" role="presentation">')
        parts.append('            <div class="desk-meter-fill"></div>')
        parts.append("          </div>")
        parts.append(f'          <p class="desk-locale-stat">{escape(stat)}</p>')
        parts.append('          <div class="desk-trays"></div>')
        parts.append(
            f'          <span class="desk-btn desk-locale-cta" aria-hidden="true">'
            f'{escape(t("index.card.start"))}</span>'
        )
        parts.append("        </div>")
    parts.append("      </div>")

    parts.append(f'      <p class="subtle">{escape(t("index.footnote"))}</p>')
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
# Runbook WO-34 (decision A15): saving is switched off until WO-17 stores decisions
# privately. One constant for the desk AND the index, so the two cannot disagree about it.
SAVE_OFF = True

# Why a save can stop -- each a COPY.md `save.reason.<name>` line. The page's failureReason()
# returns exactly these (tests/test_copy.py holds the two together).
SAVE_REASONS = ("offline", "reload", "signed_out", "cap", "daily", "unavailable", "refused", "trouble")

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


# What counts as unsaved, for the desk AND the index card, from this one string. The card
# kept its own whole-record JSON comparison, which disagreed with the desk whenever a
# record's keys came back in another order, or a record was empty (review round 2).
_DELTA_JS = """\
    // What the storage keeps of a decision: the reviewer's own fields -- the Worker's
    // deskRecord() (runbook WO-17). `by` and `at` are stamped by the server, and the
    // engine's stamps (sent, arrived, failed, exported, live) live in its own tables, so
    // none of them is sent, and none of them makes a row unsaved.
    var STORED_FIELDS = ['tray', 'text', 'approvedAgainst', 'rejected'];

    // A record is worth keeping if it carries a decision.
    function hasContent(r) {
      if (!r) return false;
      for (var i = 0; i < STORED_FIELDS.length; i++) {
        var v = r[STORED_FIELDS[i]];
        if (v !== undefined && v !== null) return true;
      }
      return false;
    }
    function storedOnly(r) {
      var out = {};
      if (!r) return out;
      STORED_FIELDS.forEach(function (f) { if (r[f] !== undefined && r[f] !== null) out[f] = r[f]; });
      return out;
    }

    // Strings compare directly; only `rejected` (a list) needs serialising. Serialising
    // every field of every record made each click on a decided desk pay for ~18,000
    // JSON.stringify calls.
    function sameValue(x, y) {
      if (x === undefined) x = null;
      if (y === undefined) y = null;
      if (x === y) return true;
      if (x === null || y === null || typeof x !== 'object' || typeof y !== 'object') return false;
      return JSON.stringify(x) === JSON.stringify(y);
    }

    function sameDecision(a, b) {
      if (!a && !b) return true;
      if (!a || !b) return false;
      for (var i = 0; i < STORED_FIELDS.length; i++) {
        // `approvedAgainst` belongs here: without it, re-approving a row whose
        // wording had moved produced no delta, the server kept the stale snapshot,
        // and the export skipped the row as "changed since approval" for ever.
        if (!sameValue(a[STORED_FIELDS[i]], b[STORED_FIELDS[i]])) return false;
      }
      return true;
    }

    function deltaBetween(now, was) {
      var out = {}, n = 0, ids = {};
      for (var k in now) ids[k] = 1;
      for (var k2 in was) ids[k2] = 1;
      for (var uid in ids) {
        var mine = hasContent(now[uid]) ? now[uid] : null;
        var theirs = hasContent(was[uid]) ? was[uid] : null;
        if (sameDecision(mine, theirs)) continue;
        // null is how the storage is told the decision was undone.
        out[uid] = mine ? storedOnly(mine) : null;
        n++;
      }
      return { body: out, n: n };
    }
"""


# One tooltip for every control on the desk and the index (ruling #51, runbook WO-08).
# The browser's own `title` tooltip waited about a second, never showed on keyboard focus
# or touch, and could not say a control's state promptly. This one: about 0.1 s after
# hover, at once on keyboard focus, on a long press on touch; Esc closes it; it flips
# below near the top of the screen and never runs off an edge. The text is the control's
# `data-tip`, which comes from COPY.md; `aria-label` still carries it for screen readers.
_TIP_JS = """
    (function () {
      var tip = document.createElement('div');
      tip.className = 'desk-tip';
      tip.setAttribute('role', 'tooltip');
      tip.hidden = true;
      document.body.appendChild(tip);
      var owner = null, timer = null;
      function hide() { clearTimeout(timer); timer = null; owner = null; tip.hidden = true; }
      function show(el) {
        var text = el.getAttribute('data-tip');
        if (!text) { hide(); return; }
        owner = el;
        tip.textContent = text;
        tip.hidden = false;
        var r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight, gap = 8;
        var top = r.top - h - gap;
        if (top < gap) top = r.bottom + gap;
        var left = Math.min(Math.max(gap, r.left + r.width / 2 - w / 2), window.innerWidth - w - gap);
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
      }
      function later(el, ms) { clearTimeout(timer); timer = setTimeout(function () { show(el); }, ms); }
      document.addEventListener('pointerover', function (ev) {
        if (ev.pointerType === 'touch') return;
        var el = ev.target.closest && ev.target.closest('[data-tip]');
        if (el && el !== owner) later(el, 100);
      });
      document.addEventListener('pointerout', function (ev) {
        var el = ev.target.closest && ev.target.closest('[data-tip]');
        if (el && (!ev.relatedTarget || !el.contains(ev.relatedTarget))) hide();
      });
      document.addEventListener('focusin', function (ev) {
        var el = ev.target.closest && ev.target.closest('[data-tip]');
        if (el && el.matches(':focus-visible')) show(el);
      });
      document.addEventListener('focusout', hide);
      document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') hide(); });
      window.addEventListener('scroll', hide, true);
      document.addEventListener('pointerdown', function (ev) {
        var el = ev.target.closest && ev.target.closest('[data-tip]');
        if (ev.pointerType === 'touch' && el) later(el, 500);
      });
      ['pointerup', 'pointercancel'].forEach(function (type) {
        document.addEventListener(type, function (ev) {
          if (ev.pointerType === 'touch') { clearTimeout(timer); if (!tip.hidden) setTimeout(hide, 1500); }
        });
      });
      // A click changes what the control says ("Approved -- click to undo"): say it now.
      document.addEventListener('click', function () {
        var el = owner;
        if (el) setTimeout(function () { if (owner === el) show(el); }, 0);
      });
    })();
"""


def _worth_js(units: list[dict]) -> str:
    """`{locale: [unit ids worth a look]}` for every locale, as a JS literal."""
    return json.dumps({c: worth_a_look(c, units) for c, *_ in LOCALES},
                      separators=(",", ":"))


def _index_js(worth_js: str = "{}") -> str:
    """Fill each card's progress and links from that locale's saved decisions.

    The server cannot know any of this -- decisions live in the reviewer's browser --
    so the card ships with the honest static number and this upgrades it in place.
    Every word comes from COPY.md through `t()` / `tn()`.
    """
    return """\
  <script>
  (function () {
    'use strict';
    var COPY = __COPY__;
__HELPERS__
    var WORTH = __WORTH__;
    var SAVE_OFF = __SAVE_OFF__;
__STAGE_JS__
__DELTA_JS__
    function read(code) {
      try { return JSON.parse(localStorage.getItem('cel-desk-' + code) || '{}') || {}; }
      catch (e) { return {}; }
    }
    function chip(cls, label, href) {
      var a = document.createElement('a');
      a.className = 'desk-tray ' + cls;
      a.href = href;
      a.textContent = label;
      return a;
    }
    function paintCard(card) {
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
      card.classList.toggle('is-started', done > 0);
      // Before anything is decided, the number of flagged texts is the useful one;
      // after, progress is.
      card.querySelector('.desk-locale-stat').textContent = done
        ? t('index.card.progress', { done: done, total: total })
        : (flagged ? tn('index.card.flagged', flagged) : t('index.card.flagged.none'));
      card.querySelector('.desk-locale-cta').textContent =
        t(done ? 'index.card.continue' : 'index.card.start');
      // Continue lands where there is work: once the flagged texts were decided, the
      // card still opened "Flagged" -- an empty list (review round 2, L5).
      var left = total - done;
      card.querySelector('.desk-locale-open').setAttribute('href', '/admin/localization/' + code +
        '/?show=' + (arrived ? 'arrived' : flagged ? 'check' : left > 0 ? 'todo' : 'all'));

      // Only what is waiting on the reviewer or already decided, each a real link into
      // that filter. The old "nothing decided yet" pill said nothing and led nowhere.
      var trays = card.querySelector('.desk-trays');
      trays.textContent = '';
      var base = '/admin/localization/' + code + '/';
      if (arrived) trays.appendChild(chip('desk-tray-arrived', tn('index.chip.arrived', arrived), base + '?show=arrived'));
      if (failed) trays.appendChild(chip('desk-tray-failed', tn('index.chip.failed', failed), base + '?show=failed'));
      if (sending) trays.appendChild(chip('desk-tray-sending', t('index.chip.sending', { n: sending }), base + '?show=sending'));
      if (csv) trays.appendChild(chip('desk-tray-csv', t('index.chip.approved', { n: csv }), base + '?show=approved'));
      if (draft) trays.appendChild(chip('desk-tray-draft', tn('index.chip.requested', draft), base + '?show=requested'));
      trays.hidden = !trays.firstChild;

      // It can honestly offer only one thing: throwing away what this browser has not
      // sent yet. Anything saved comes back from the server on the next visit.
      // The desk's own delta, emitted from the same string: comparing whole records as
      // JSON counted saved work as unsaved whenever its keys came back in another order
      // (review round 2, L1 P2-3).
      var unsaved = deltaBetween(st, read('saved-' + code)).n;
      // While saving is off nothing is on a server, so "discard what is unsaved" would wipe
      // a whole language with one click (round 3). WO-17 brings it back.
      if (unsaved && !SAVE_OFF) {
        var undo = document.createElement('button');
        undo.type = 'button';
        undo.className = 'desk-btn desk-locale-discard';
        undo.textContent = t('index.discard.button', { n: unsaved });
        undo.setAttribute('data-tip', t('index.discard.hint'));
        undo.addEventListener('click', function () {
          var nm = card.getAttribute('data-name') || code;
          if (!window.confirm(tn('index.discard.confirm', unsaved, { language: nm }))) return;
          try {
            localStorage.setItem('cel-desk-' + code,
                                 localStorage.getItem('cel-desk-saved-' + code) || '{}');
          } catch (e) {}
          paintAll();
        });
        trays.hidden = false;
        trays.appendChild(undo);
      }
    }
    function paintAll() {
      Array.prototype.forEach.call(document.querySelectorAll('[data-locale]'), paintCard);
    }
    paintAll();
    // A desk open in another tab changes these numbers; so does Back to a cached page.
    window.addEventListener('storage', function (ev) {
      if (ev.key === null || (ev.key.indexOf('cel-desk-') === 0 && ev.key.indexOf('cel-desk-log-') !== 0)) paintAll();
    });
    window.addEventListener('pageshow', function (ev) { if (ev.persisted) paintAll(); });
  })();
  </script>
""".replace("__STAGE_JS__", _STAGE_JS).replace("__DELTA_JS__", _DELTA_JS).replace(
        "__WORTH__", worth_js).replace("__HELPERS__", JS_HELPERS + _TIP_JS).replace(
        "__SAVE_OFF__", "true" if SAVE_OFF else "false").replace("__COPY__", js_table())


def render_locale(code: str, units: list[dict]) -> str:
    endonym, direction, _flag = _LOCALE[code]
    name = lang_name(code)
    rows = [u for u in units if (u.get("current") or {}).get(code)]
    parts = _head(t("meta.locale.title", language=name),
                  t("meta.locale.description", language=name))
    parts.append(render_admin_open("localization"))
    parts.append('  <div class="dashboard-shell">')
    # Same markup and classes as render_page_chrome(), written out here so the help
    # control can live IN the header rather than down among the filters.
    parts.append('    <header class="dashboard-header">')
    parts.append('      <div class="brand-text">')
    parts.append(f'        <p class="eyebrow" id="desk-eyebrow">{escape(t("locale.eyebrow", LANGUAGE=name.upper()))}</p>')
    parts.append(
        f'        <p class="subtitle" id="desk-subtitle"><bdi>{escape(endonym)}</bdi> &middot; '
        f'{escape(t("locale.subtitle", total=len(rows)))}</p>'
    )
    parts.append("      </div>")
    parts.append('      <button type="button" class="desk-btn desk-header-btn" id="how-open">'
                 f'{escape(t("locale.help"))}</button>')
    parts.append("    </header>")

    # Toolbar. The locale strip comes FIRST because switching language while staying
    # on the same page and filter is the move the reviewer makes most.
    parts.append('    <div class="controls">')
    parts.append(f'      <nav class="desk-locales-strip" aria-label="{escape(t("locale.langs.label"))}">')
    for lcode, _endo, _dir, lflag in LOCALES:
        lname = lang_name(lcode)
        cls = "desk-loc is-active" if lcode == code else "desk-loc"
        aria = ' aria-current="page"' if lcode == code else ""
        parts.append(
            f'        <a class="{cls}" href="/admin/localization/{lcode}/" '
            f'data-loc="{lcode}" data-tip="{escape(t("locale.langs.hover", language=lname))}"{aria}>'
            f'<span class="desk-loc-flag" aria-hidden="true">{lflag}</span>'
            f'<span class="desk-loc-name">{escape(lname)}</span>'
            f'<span class="desk-loc-count" data-loc-count="{lcode}" hidden></span></a>'
        )
    parts.append("      </nav>")
    parts.append('      <div class="desk-toolbar">')
    parts.append(f'        <label class="desk-field">{escape(t("filter.page"))}')
    parts.append('          <select class="desk-select" id="f-page">')
    parts.append(f'            <option value="">{escape(t("filter.page.all"))}</option>')
    for slug in PAGE_KEYS:
        parts.append(f'            <option value="{slug}">{escape(t("page." + slug))}</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append(f'        <label class="desk-field">{escape(t("filter.show"))}')
    parts.append('          <select class="desk-select" id="f-state">')
    # Ordered by what the reviewer should do next. The labels (with their live counts)
    # are written by the page from COPY.md `show.*`, so they are never two copies.
    for value, key in [("check", "check"), ("arrived", "arrived"), ("todo", "todo"),
                       ("", "all"), ("csv", "csv"), ("edited", "edited"), ("draft", "draft"),
                       ("sending", "sending"), ("failed", "failed"), ("exported", "exported"),
                       ("live", "live")]:
        parts.append(f'            <option value="{value}" data-copy="show.{key}">'
                     f'{escape(t("show." + key, n="…"))}</option>')
    parts.append("          </select>")
    parts.append("        </label>")
    parts.append(f'        <label class="desk-field">{escape(t("filter.search"))}')
    parts.append('          <input class="desk-select desk-search" id="f-q" type="search" '
                 f'placeholder="{escape(t("filter.search.placeholder", language=name))}" '
                 'autocomplete="off">')
    parts.append("        </label>")
    parts.append("      </div>")
    parts.append('      <p class="subtle" id="count-line" aria-live="polite"></p>')
    parts.append("    </div>")

    parts.append('    <main class="dashboard-main">')
    parts.append('      <div class="scroll-x">')
    parts.append('        <table class="doc-table desk-table">')
    # Explicit columns, because the table is `table-layout: fixed`.
    parts.append("          <colgroup>")
    parts.append('            <col class="col-pick"><col class="col-src"><col class="col-tgt">')
    parts.append('            <col class="col-state"><col class="col-act">')
    parts.append("          </colgroup>")
    parts.append("          <thead><tr>")
    parts.append('            <th scope="col" class="desk-col-pick">'
                 '<input type="checkbox" class="desk-pick" id="pick-all" '
                 f'aria-label="{escape(t("table.pick_all"))}"></th>')
    parts.append(f'            <th scope="col">{escape(t("table.col.source"))}</th>')
    parts.append(f'            <th scope="col" id="col-target">{escape(t("table.col.target", language=name))}</th>')
    parts.append(f'            <th scope="col" class="desk-col-state">{escape(t("table.col.status"))}</th>')
    parts.append(f'            <th scope="col" class="desk-col-act">{escape(t("table.col.actions"))}</th>')
    parts.append("          </tr></thead>")
    # Rows are built in the browser from units.json, not baked in here.
    parts.append('          <tbody id="desk-body"></tbody>')
    parts.append("        </table>")
    parts.append('        <div class="empty" id="no-rows" hidden>')
    parts.append(f'          <p>{escape(t("table.empty"))}</p>')
    parts.append(f'          <button type="button" class="desk-btn" id="no-rows-reset">{escape(t("table.empty.reset"))}</button>')
    parts.append('        </div>')
    parts.append("      </div>")
    parts.append("    </main>")

    # Sticky two-zone action bar
    parts.append('    <div class="desk-savebar" id="savebar" hidden>')
    parts.append('      <div class="desk-bar-row" id="bar-select" hidden>')
    parts.append('        <p class="desk-savebar-text" id="sel-count"></p>')
    parts.append('        <span class="desk-savebar-spacer"></span>')
    parts.append(f'        <button type="button" class="desk-btn" id="bulk-clear">{escape(t("bar.clear"))}</button>')
    parts.append(f'        <button type="button" class="desk-btn" id="bulk-draft">{escape(t("bar.queue"))}</button>')
    parts.append(f'        <button type="button" class="desk-btn is-strong" id="bulk-approve">{escape(t("bar.approve"))}</button>')
    parts.append("      </div>")
    parts.append('      <div class="desk-bar-row" id="bar-trays" hidden>')
    parts.append('        <p class="desk-savebar-text" id="tray-line"></p>')
    parts.append('        <span class="desk-savebar-spacer"></span>')
    # These OPEN a list; the two in the row above ACT on the selection.
    parts.append(f'        <button type="button" class="desk-btn" id="open-draft">{escape(t("bar.view.requested"))}</button>')
    parts.append(f'        <button type="button" class="desk-btn" id="open-csv">{escape(t("bar.view.approved"))}</button>')
    parts.append('        <button type="button" class="desk-btn is-primary" id="btn-save" hidden></button>')
    parts.append('        <span class="desk-status" id="save-elsewhere" hidden></span>')
    parts.append('        <span class="desk-status" id="save-status" role="status"></span>')
    parts.append("      </div>")
    parts.append("    </div>")

    parts.append("  </div>")
    parts.append('  <div class="toast-stack" id="toast-stack" role="status" aria-live="polite"></div>')
    parts.append(_how_modal())
    parts.append(_review_modal())
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
    // Every word on this page comes from COPY.md (operator, 2026-09-23: all text lives in
    // one document and the code pulls it from there). t() / tn() read it.
    var COPY = __COPY__;
__HELPERS__
    // Weglot keeps each link inside a text as <a wg-N="">words</a>. Showing that raw made
    // the reviewer read markup; the linked words are shown underlined instead. DOM only.
    var MARK = new RegExp('(<a wg-[0-9]+="">|</a>)');
    function renderMarked(el, text) {
      el.textContent = '';
      var inLink = null;
      String(text).split(MARK).forEach(function (part) {
        if (!part) return;
        if (part.indexOf('<a wg-') === 0) {
          inLink = document.createElement('span');
          inLink.className = 'desk-linktext';
          el.appendChild(inLink);
          return;
        }
        if (part === '</a>') { inLink = null; return; }
        (inLink || el).appendChild(document.createTextNode(part));
      });
    }
    // Per locale, the ids "Worth a look first" starts from -- the same list the index
    // card counts, so a tab badge, the filter and the index say one number.
    var WORTH = __WORTH__;
    // Every language's endonym and direction, so this one page can show any of them.
    // Switching language swaps the data, not the page (ruling #52, runbook WO-09).
    var LOCALE_INFO = __LOCALE_INFO__;
    var CODE, KEY, LOGKEY, SAVEDKEY, RTL;
    var LOG_CAP = 1000;
    function setLocale(code) {
      CODE = code;
      KEY = 'cel-desk-' + code;
      LOGKEY = 'cel-desk-log-' + code;
      SAVEDKEY = 'cel-desk-saved-' + code;
      RTL = !!LOCALE_INFO[code].rtl;
    }
    setLocale('__CODE__');

    var state = {};
    // What the website serves for each row, as loaded -- never what is on screen. The
    // `.desk-live` span shows the reviewer's edit when there is one, and reading the
    // wording back from it recorded a DISCARDED edit as the text an approval was given
    // to (audit 2026-09-23): export then refused the row as "moved since approval".
    var liveText = Object.create(null);
    var sourceText = Object.create(null);   // the English, markers included
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
    // Eight languages' decisions and logs share one origin's ~5 MB. When it is full, the
    // logs are the one thing that may give way: they exist for diagnosis, the decisions
    // are the reviewer's work (review round 2, L1 P2-5).
    function trimLogs() {
      LOCALES.forEach(function (c) {
        if (c !== CODE) { try { localStorage.removeItem('cel-desk-log-' + c); } catch (e) {} }
      });
      hist = hist.slice(Math.floor(hist.length / 2));
      try { localStorage.setItem(LOGKEY, JSON.stringify(hist)); } catch (e) {}
    }
    function persist() {
      var raw = JSON.stringify(state);
      try {
        try { localStorage.setItem(KEY, raw); }
        catch (full) { trimLogs(); localStorage.setItem(KEY, raw); }
        storageBroken = false;
        return true;
      } catch (e) {
        // Swallowing this silently let every caller toast "saved" while nothing had
        // been written -- the screen stayed right and a reload lost the lot. Say so
        // once, then stop repeating it.
        if (!storageBroken) {
          storageBroken = true;
          toast(t('toast.storage.title'), { level: 'err', detail: t('toast.storage.detail') });
        }
        return false;
      }
    }
    function note(action, uid, from, to) {
      // Capped so a long session cannot fill the origin's storage quota and start
      // throwing on the writes that actually matter.
      hist.push({ t: new Date().toISOString(), a: action, u: uid || null, f: from || null, x: to || null });
      if (hist.length > LOG_CAP) hist = hist.slice(hist.length - LOG_CAP);
      try { localStorage.setItem(LOGKEY, JSON.stringify(hist)); }
      catch (e) {
        hist = hist.slice(Math.floor(hist.length / 2));
        try { localStorage.setItem(LOGKEY, JSON.stringify(hist)); } catch (e2) {}
      }
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
      rows = [];
      units.forEach(function (u) {
        var tr = document.createElement('tr');
        tr.className = 'desk-row';
        tr.setAttribute('data-uid', u.id);
        liveText[u.id] = u.tgt;
        sourceText[u.id] = u.src;
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
        cb.setAttribute('aria-label', t('row.pick'));
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
        renderMarked(srcText, u.src);
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
        // The text's own language, so a screen reader speaks it as that language and
        // Japanese and Korean get their own glyphs, not the English page's (review round 2).
        live.setAttribute('lang', CODE);
        renderMarked(live, u.tgt);
        live.setAttribute('data-shown', u.tgt);
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
          var eg = u.sharedEg === '/' ? t('row.shared.home') : u.sharedEg;
          shared.textContent = tn('row.shared', u.shared, { example: eg });
        }
        tdTgt.appendChild(live);
        if (why) tdTgt.appendChild(why);
        if (shared) tdTgt.appendChild(shared);

        var tdState = document.createElement('td');
        tdState.className = 'desk-col-state';
        var badge = document.createElement('span');
        badge.className = 'desk-state desk-badge-todo';
        badge.textContent = t('status.todo');
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
        [['approve', t('action.approve'), 'tick'],
         ['edit', t('action.edit'), 'pencil'],
         ['queue', t('action.queue'), 'spark']]
          .forEach(function (spec) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'desk-btn desk-icon-btn';
            b.setAttribute('data-act', spec[0]);
            b.setAttribute('data-tip', spec[1]);
            b.setAttribute('aria-label', spec[1]);
            b.appendChild(icon(spec[2]));
            acts.appendChild(b);
          });
        tdAct.appendChild(acts);

        tr.appendChild(tdPick); tr.appendChild(tdSrc); tr.appendChild(tdTgt);
        tr.appendChild(tdState); tr.appendChild(tdAct);
        rows.push(tr);
      });
    }

    // Rows go onto the page in slices (runbook WO-09). Every row is built and painted,
    // and filters, counts and selection read `rows`, never the page -- but the browser
    // lays out only what is attached. So the first screen (down past the reader's place)
    // goes up at once and the rest follows a slice per task, instead of one long freeze
    // laying out 823 rows nobody can see yet.
    var attachGen = 0;
    var FIRST_SCREEN = 40, SLICE = 150;
    function attachRows(anchorUid) {
      var gen = ++attachGen;
      var i = 0, shown = 0, reached = !anchorUid;
      var frag = document.createDocumentFragment();
      while (i < rows.length && !(reached && shown >= FIRST_SCREEN)) {
        var tr = rows[i++];
        frag.appendChild(tr);
        if (!reached && tr.getAttribute('data-uid') === anchorUid) { reached = true; shown = 0; }
        if (!tr.hidden) shown++;
      }
      body.appendChild(frag);
      var more = function () {
        if (gen !== attachGen) return;     // a switch has replaced these rows
        var f = document.createDocumentFragment();
        for (var n = 0; n < SLICE && i < rows.length; n++) f.appendChild(rows[i++]);
        body.appendChild(f);
        if (i < rows.length) setTimeout(more, 0);
      };
      if (i < rows.length) setTimeout(more, 0);
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
      // One colour per meaning (role table, process contract §8 U1): not reviewed =
      // neutral outline, waiting on the machine = grey, look at this = warm, settled =
      // green, went wrong = red. Indigo is never a state (ruling #53).
      todo:     [t('status.todo'), 'desk-badge-todo'],
      arrived:  [t('status.arrived'), 'desk-badge-look'],
      approved: [t('status.approved'), 'badge-ok'],
      edited:   [t('status.edited'), 'badge-ok'],
      queued:   [t('status.queued'), 'desk-badge-wait'],
      sending:  [t('status.sending'), 'desk-badge-wait'],
      failed:   [t('status.failed'), 'badge-failed'],
      exported: [t('status.exported'), 'badge-ok'],
      live:     [t('status.live'), 'badge-ok']
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
      if (st === 'failed' && s.failed) badge.setAttribute('data-tip', String(s.failed));
      else badge.removeAttribute('data-tip');
      // Someone else saved this text first (WO-17): said on the row, with a way to take
      // their version; deciding again yourself keeps yours.
      var theirs = conflicts[uid];
      tr.classList.toggle('is-conflict', !!theirs);
      var take = tr.querySelector('[data-conflict]');
      if (theirs) {
        badge.className = 'desk-state desk-badge-look';
        badge.textContent = t('status.conflict');
        badge.setAttribute('data-tip', theirs.gone ? t('status.conflict.gone')
          : t('status.conflict.tip', { who: theirs.by || '', text: theirs.text != null ? theirs.text : liveText[uid] }));
        if (!take) {
          take = document.createElement('button');
          take.type = 'button';
          take.className = 'desk-btn desk-take-theirs';
          take.setAttribute('data-conflict', 'theirs');
          take.textContent = t('conflict.take_theirs');
          take.setAttribute('data-tip', t('conflict.take_theirs.hint'));
          badge.parentNode.appendChild(take);
        }
      } else if (take) {
        take.parentNode.removeChild(take);
      }
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
      // with no text has nowhere else to say what it currently means. The active one IS
      // the undo, so neither is disabled -- except while Gemini has the row (above):
      // re-enabling them here left a sending row with two buttons that did nothing.
      bApprove.classList.toggle('is-on', s.tray === 'csv');
      var tipA = t(s.tray === 'csv' ? 'action.approve.on' : 'action.approve');
      bApprove.setAttribute('data-tip', tipA);
      bApprove.setAttribute('aria-label', tipA);
      bQueue.classList.toggle('is-on', s.tray === 'draft');
      var tipQ = t(s.tray === 'draft' ? 'action.queue.on' : 'action.queue');
      bQueue.setAttribute('data-tip', tipQ);
      bQueue.setAttribute('aria-label', tipQ);

      var cb = tr.querySelector('[data-pick]');
      if (cb) cb.checked = !!picked[uid];

      // The reviewer's wording while there is one; the website's again once it is cleared.
      var live = tr.querySelector('.desk-live');
      var shown = s.text != null ? s.text : liveText[uid];
      if (live.getAttribute('data-shown') !== shown) {
        renderMarked(live, shown);
        live.setAttribute('data-shown', shown);
      }
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
      selCount.textContent = t('bar.selected', { n: n });
      barSelect.hidden = n === 0;
      // The bar stays while ANY language has unsaved work, so switching language can
      // never make pending work disappear from view.
      barTrays.hidden = (c.csv + c.draft) === 0 && unsaved === 0;
      savebar.hidden = barSelect.hidden && barTrays.hidden;
      var bits = [];
      if (c.csv) bits.push(t('bar.summary.approved', { n: c.csv }));
      if (c.draft) bits.push(tn('bar.summary.requested', c.draft));
      trayLine.textContent = bits.join('  ·  ');
      var oc = document.getElementById('open-csv');
      var od = document.getElementById('open-draft');
      oc.disabled = !c.csv;
      od.disabled = !c.draft;
      oc.textContent = c.csv ? t('bar.view.approved_n', { n: c.csv }) : t('bar.view.approved');
      od.textContent = c.draft ? t('bar.view.requested_n', { n: c.draft }) : t('bar.view.requested');
      paintSave();
      // After the frame: reading the bar's position inside a click forced a layout per click
      // (round 3 measured 3.2 -> 10.4 ms with a toast up).
      requestAnimationFrame(placeToasts);
    }

    // ── Filters ────────────────────────────────────────────────────────
    // A row you have just acted on stays where it is. Without this, approving under
    // "Worth a look first" made the row vanish mid-click: the list shifted, the next
    // click landed on a different row, and there was no way to undo the thing you had
    // just done. Cleared whenever you change the view yourself.
    var justActed = Object.create(null);

    // The Page and Search filters: what the Show counts are counted over, too.
    function inScope(tr) {
      var p = fPage.value;
      if (p && (' ' + tr.getAttribute('data-pages') + ' ').indexOf(' ' + p + ' ') === -1) return false;
      var q = fQ.value.trim().toLowerCase();
      if (q && tr.getAttribute('data-q').indexOf(q) === -1) return false;
      return true;
    }

    function matches(tr) {
      if (justActed[tr.getAttribute('data-uid')]) return true;
      if (!inScope(tr)) return false;
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
      return true;
    }

    function shown() { return rows.filter(function (tr) { return !tr.hidden; }); }

    // Live counts on every option, over the rows the Page and Search filters leave --
    // an option once promised 38 rows and showed none (audit P1-9b). An empty group is
    // disabled rather than hidden, so the list does not reshuffle under the cursor.
    var LATE_STAGES = { arrived: 1, sending: 1, failed: 1, exported: 1, live: 1 };
    function paintFilterCounts() {
      var tally = { arrived: 0, check: 0, todo: 0, csv: 0, edited: 0,
                    draft: 0, sending: 0, failed: 0, exported: 0, live: 0 };
      var scoped = rows.filter(inScope);
      scoped.forEach(function (tr) {
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
        var key = opt.getAttribute('data-copy');
        if (opt.value === '') { opt.textContent = t(key, { n: scoped.length }); return; }
        var n = tally[opt.value] || 0;
        opt.textContent = t(key, { n: n });
        // Never disable the option currently selected, or the select goes blank.
        opt.disabled = n === 0 && opt.value !== fState.value;
        // Stages nothing has reached yet (nothing is sent, exported or live before the
        // steps that do those exist) are left out, not offered as five dead options.
        opt.hidden = opt.disabled && LATE_STAGES[opt.value] === 1;
      });
    }

    function applyFilters() {
      rows.forEach(function (tr) { var h = !matches(tr); if (tr.hidden !== h) tr.hidden = h; });
      paintFilterCounts();
      var vis = shown();
      noRows.hidden = vis.length !== 0;
      // aria-live: rewriting an unchanged line made screen readers repeat it on every key.
      var line = t('count.line', { shown: vis.length, total: rows.length });
      if (countLine.textContent !== line) countLine.textContent = line;
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
    // Every decision goes through here -- a click, a key, a bulk action -- so the row
    // state table (process doc §1) holds for all of them. Three rules the table needed:
    //  * A decision that replaces another remembers it (`was`), so clicking the active
    //    choice again returns EXACTLY there: ✦ then ✦ on an approved row is approved
    //    again, not "not reviewed" with the reviewer's edit hidden inside it.
    //  * ✦ on an arrived draft records that draft as `rejected` -- the batch sends it to
    //    Gemini as what not to repeat; without it a re-request paid twice for the same
    //    prompt (R56). Undoing puts the draft back.
    //  * `was` stays in this browser (it is not in STORED_FIELDS): undo is a convenience of
    //    the session that made the change, not a fact the engine needs.
    function decide(uid, tr, tray, why, restoring) {
      clearConflict(uid);                  // deciding again is choosing yours over theirs
      var s = rec(uid);
      var from = s.tray || null;
      if (from === tray) return false;
      // A LIST, newest last, the last five: what the Worker's storage and the batch
      // all read. A string was refused by the Worker, taking the whole save with it
      // (review round 2, L7 P1-1).
      if (tray === 'draft' && stage(uid) === 'arrived' && s.text != null) {
        var turnedDown = Array.isArray(s.rejected) ? s.rejected.slice()
          : (typeof s.rejected === 'string' && s.rejected ? [s.rejected] : []);   // the pre-list shape
        turnedDown.push(s.text);
        s.rejected = turnedDown.slice(-5);
        delete s.text;
      }
      if (restoring && from === 'draft' && Array.isArray(s.rejected) && s.rejected.length &&
          s.arrivedAt && s.text == null) {
        s.rejected = s.rejected.slice();
        s.text = s.rejected.pop();
        if (!s.rejected.length) delete s.rejected;
      }
      if (!restoring && from && tray) s.was = from; else delete s.was;
      setTray(uid, tray, why);
      if (from === 'csv') stampApproval(uid, tr, false);
      if (tray === 'csv') stampApproval(uid, tr, true);
      return true;
    }

    function apply(tr, what) {
      var uid = tr.getAttribute('data-uid');
      // A row being sent to Gemini is not the reviewer's to change until it comes back.
      // The buttons were already disabled; the keyboard reached it anyway (audit P1-4),
      // and `E` still did -- it was checked after the editor (review round 2).
      if (stage(uid) === 'sending') return;
      if (what === 'edit') {
        var ed = tr.querySelector('.desk-editor');
        toggleEditor(tr, !ed || ed.hidden);
        return;
      }
      var tray = what === 'approve' ? 'csv' : what === 'queue' ? 'draft' : null;
      if (!tray) return;
      // Clicking the decision a row already carries undoes it -- back to what it was
      // before, never further (ruling #16).
      justActed[uid] = 1;
      var s = rec(uid);
      var undoing = (s.tray || null) === tray;
      var target = undoing ? (s.was || null) : tray;
      var why = undoing ? (what === 'approve' ? 'un-approve' : 'un-queue') : what;
      if (decide(uid, tr, target, why, undoing)) { persist(); paint(tr); }
    }

    body.addEventListener('click', function (ev) {
      var take = ev.target.closest('[data-conflict]');
      if (take) {
        var trc = take.closest('.desk-row'), uidc = trc.getAttribute('data-uid');
        var theirs = conflicts[uidc] || {};
        // Their decision, as the storage holds it: nothing of yours left to send. The
        // engine's stamps on the row are not a decision and stay.
        var keep = {};
        ['sentAt', 'arrivedAt', 'failed', 'exportedAt', 'liveAt'].forEach(function (f) {
          if (state[uidc] && state[uidc][f] != null) keep[f] = state[uidc][f];
        });
        state[uidc] = Object.assign(keep, storedOnly(theirs), theirs.by ? { by: theirs.by, at: theirs.at } : {});
        clearConflict(uidc);
        note('take-theirs', uidc, null, null);
        persist(); paint(trc); paintBar(); applyFilters();
        return;
      }
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
    // The editor is built the first time a row is edited. Building all of them up front
    // made every load create ~10,000 hidden elements nobody had asked for (runbook WO-09).
    function ensureEditor(tr) {
      var have = tr.querySelector('.desk-editor');
      if (have) return have;
      var uid = tr.getAttribute('data-uid');
      var editWrap = document.createElement('div');
      editWrap.className = 'desk-editor';
      editWrap.hidden = true;
      var ta = document.createElement('textarea');
      ta.className = 'desk-edit';
      ta.setAttribute('aria-label', t('editor.label'));
      ta.setAttribute('dir', 'auto');
      ta.setAttribute('lang', CODE);
      ta.value = liveText[uid];
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
      bCancel.textContent = t('editor.cancel');
      var bSave = document.createElement('button');
      bSave.type = 'button';
      // Ghost, not filled. Save in the bottom bar is the page's one primary, and a
      // second filled pill inline in a table row competes with it for the same job.
      bSave.className = 'desk-btn is-strong';
      bSave.setAttribute('data-edit', 'save');
      bSave.textContent = t('editor.save');
      editBar.appendChild(editHint);
      editBar.appendChild(bCancel);
      editBar.appendChild(bSave);
      editWrap.appendChild(ta);
      // A text with a link carries its markers into the edit box; say what they are
      // for, once, where the reviewer meets them.
      if (liveText[uid].indexOf('<a wg-') !== -1 || sourceText[uid].indexOf('<a wg-') !== -1) {
        var linkNote = document.createElement('p');
        linkNote.className = 'desk-editor-note';
        linkNote.setAttribute('dir', 'auto');
        linkNote.textContent = t('editor.links');
        editWrap.appendChild(linkNote);
      }
      editWrap.appendChild(editBar);
      tr.querySelector('.desk-tgt').appendChild(editWrap);
      return editWrap;
    }

    function toggleEditor(tr, open) {
      var wrap = open ? ensureEditor(tr) : tr.querySelector('.desk-editor');
      if (!wrap) return;
      var live = tr.querySelector('.desk-live');
      var ta = wrap.querySelector('.desk-edit');
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
      if (!ta) return false;
      return ta.value.trim() !== (ta.getAttribute('data-opened-with') || '').trim();
    }

    function paintEditor(tr) {
      if (!tr.querySelector('.desk-editor')) return;
      var dirty = editorDirty(tr);
      tr.querySelector('.desk-editor-hint').textContent = dirty ? t('editor.unsaved') : '';
      var sv = tr.querySelector('[data-edit="save"]');
      sv.disabled = !dirty;
      // A disabled control says why (the dead-control robot, runbook WO-33).
      if (dirty) sv.removeAttribute('data-tip'); else sv.setAttribute('data-tip', t('editor.save.hint'));
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
      // What is in the box is now the decision, so Cancel has nothing to throw away.
      ta.setAttribute('data-opened-with', ta.value);
      // Typing your own wording is deciding again -- over someone else's save, too (WO-17).
      if (changed) clearConflict(uid);
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
          toast(t('toast.edited.title'), { level: 'ok', detail: t('toast.edited.detail') });
        }
        toggleEditor(tr, false);
      } else {
        // Closing with changes is allowed, but never silently.
        if (editorDirty(tr) &&
            !window.confirm(t('editor.discard'))) return;
        toggleEditor(tr, false);
      }
    });

    // Both doors out of this page.
    window.addEventListener('beforeunload', flushEditors);
    // A language tab switches the data in place (ruling #52): no reload, no blank page, no
    // second sign-in check; filters and the reviewer's place carry over. Open editors are
    // committed first (ruling #12). A modified click still opens the page itself.
    document.addEventListener('click', function (ev) {
      var link = ev.target.closest('a[data-loc]');
      if (!link) return;
      // Editors are committed by switchTo(), and only when the language really changes:
      // committing here, first, meant clicking the language already open approved a
      // half-typed edit behind the reviewer's back (review round 2, L1 P2-2).
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      var code = link.getAttribute('data-loc');
      if (!LOCALE_INFO[code]) return;
      ev.preventDefault();
      switchTo(code, true);
    }, true);
    var PATH_LOCALE = new RegExp('/localization/([a-z][a-z])/');
    // The desk keeps the reader's place itself (the same English text in view); the
    // browser's own restore on Back would put them wherever they last were instead.
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    window.addEventListener('popstate', function () {
      var m = location.pathname.match(PATH_LOCALE);
      if (m && m[1] !== CODE && LOCALE_INFO[m[1]]) switchTo(m[1], false);
    });
    // Hovering a tab starts loading that language, so the click has nothing to wait for.
    document.addEventListener('pointerover', function (ev) {
      var a = ev.target.closest && ev.target.closest('a[data-loc]');
      if (a && LOCALE_INFO[a.getAttribute('data-loc')]) fetchUnits(a.getAttribute('data-loc')).catch(function () {});
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
      var inFlight = ids.filter(function (uid) { return stage(uid) === 'sending'; });
      ids = ids.filter(function (uid) { return stage(uid) !== 'sending'; });
      if (!ids.length) {
        toast(t('toast.inflight.title'), { level: 'warn', detail: tn('toast.inflight', inFlight.length) });
        return;
      }
      var changed = 0;
      ids.forEach(function (uid) {
        var row = rows.find(function (r) { return r.getAttribute('data-uid') === uid; });
        if (!decide(uid, row, tray, why, false)) return;
        changed++;
        // Rows acted on hold their place until the reviewer changes the view (ruling
        // #17) -- a bulk action is an action, not a change of view. Clearing the view
        // here emptied "Flagged" on a select-all + Approve (audit P1-5).
        justActed[uid] = 1;
      });
      note(why + ':bulk', null, String(ids.length), String(changed));
      picked = Object.create(null);
      lastPicked = -1;
      persist();
      rows.forEach(paint);
      paintBar(); applyFilters();
      var extra = changed !== ids.length ? tn('toast.already', ids.length - changed) + ' ' : '';
      toast(tn(tray === 'csv' ? 'toast.approved' : 'toast.requested', changed), {
        level: 'ok',
        detail: extra + t(tray === 'csv' ? 'toast.approved.detail' : 'toast.requested.detail')
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
      // With any dialog open -- the help, a list, the shell's account dialog -- J/K/A/E/R/X
      // acted on the table behind it.
      if (document.querySelector('.cpw-overlay:not([hidden])')) return;
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

    function closeOverlays() { howOverlay.hidden = true; trayOverlay.hidden = true; openTray = null; }
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
    // COPY.md `list.<draft|csv>.*`: what each list IS, not what is planned.

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
      document.getElementById('tray-all-label').textContent =
        sel ? t('list.selected', { n: sel }) : t('list.select_all');
      var rm = document.getElementById('tray-remove-sel');
      rm.disabled = sel === 0;
      rm.textContent = sel ? t('list.undo_n', { n: sel }) : t('list.undo');
      // A disabled control says why (the dead-control robot, runbook WO-33).
      if (sel) rm.removeAttribute('data-tip'); else rm.setAttribute('data-tip', t('list.undo.hint'));
      document.getElementById('tray-empty').disabled = listed === 0;

      // The list used to offer nothing but Undo and Close: a basket with no way to
      // check out. Saving is the one step that actually exists today, and it is the
      // step that makes this work survive the tab -- so it belongs here, not only in
      // the bar behind the overlay.
      var ts = document.getElementById('tray-save');
      var allPending = unsavedByLocale(), pending = 0;
      for (var pc in allPending) pending += allPending[pc].n;
      ts.hidden = pending === 0 || SAVE_OFF;
      ts.disabled = saving;
      ts.textContent = saving ? t('save.status.saving') : tn('save.button', pending);
      ts.setAttribute('data-tip', t('save.button.hint'));
    }

    // Through decide(), like every other decision, so an undone approval also drops its
    // who/when/against stamps. A row Gemini has is skipped, as the table and the bulk
    // bar already did; Undo all took them out anyway (review round 2, L5 #7).
    function takeBack(uids, why) {
      var n = 0, busy = 0;
      uids.forEach(function (uid) {
        delete trayPicked[uid];
        if (stage(uid) === 'sending') { busy++; return; }
        var row = rows.find(function (r) { return r.getAttribute('data-uid') === uid; });
        // Exactly the table's Undo: back to what the row was before (`was`), and a draft
        // turned down by the request comes back (round 3 -- a list Undo left it rejected).
        if (decide(uid, row, (state[uid] && state[uid].was) || null, why, true)) n++;
      });
      persist();
      rows.forEach(paint);
      paintBar(); applyFilters(); paintTray();
      toast(t('toast.undone.title'), { level: 'warn',
        detail: tn('toast.undone', n) + (busy ? ' ' + tn('toast.inflight', busy) : '') });
      return n;
    }
    function removeFromTray(uids) { takeBack(uids, 'take-back'); }

    function paintTray() {
      if (!openTray) return;
      var listed = trayRows();
      // A row another tab moved out of this list is not selected any more: its Undo would
      // act on a row the list no longer shows (round 3).
      var onList = Object.create(null);
      listed.forEach(function (tr) { onList[tr.getAttribute('data-uid')] = 1; });
      Object.keys(trayPicked).forEach(function (uid) { if (!onList[uid]) delete trayPicked[uid]; });
      var n = listed.length;
      document.getElementById('tray-title').textContent = t('list.' + openTray + '.title');
      document.getElementById('tray-summary').textContent = tn('list.' + openTray + '.summary', n);
      document.getElementById('tray-notice').textContent = t('list.' + openTray + '.notice');

      trayList.textContent = '';
      listed.forEach(function (tr) {
        var uid = tr.getAttribute('data-uid');
        var li = document.createElement('li');
        li.className = 'desk-review-item';

        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'desk-pick';
        cb.checked = !!trayPicked[uid];
        cb.setAttribute('aria-label', t('row.pick'));
        cb.addEventListener('change', function () {
          if (cb.checked) trayPicked[uid] = 1; else delete trayPicked[uid];
          paintTrayFooter();
        });

        var texts = document.createElement('div');
        texts.className = 'desk-review-texts';
        var src = document.createElement('p');
        src.className = 'desk-review-src';
        renderMarked(src, sourceText[uid]);
        var tgt = document.createElement('p');
        tgt.className = 'desk-review-tgt';
        // Paragraph direction follows the text, as in the table (see `.desk-live`).
        tgt.setAttribute('dir', 'auto');
        tgt.setAttribute('lang', CODE);
        var st = state[uid] || {};
        renderMarked(tgt, st.text != null ? st.text : liveText[uid]);
        texts.appendChild(src); texts.appendChild(tgt);

        var rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'desk-btn desk-icon-btn';
        rm.setAttribute('data-tip', t('list.row.undo'));
        rm.setAttribute('aria-label', t('list.row.undo.label'));
        rm.appendChild(icon('undo'));
        rm.addEventListener('click', function () { removeFromTray([uid]); });
        rm.disabled = stage(uid) === 'sending';

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
      var which = openTray;
      var ids = trayRows().map(function (tr) { return tr.getAttribute('data-uid'); });
      var movable = ids.filter(function (uid) { return stage(uid) !== 'sending'; }).length;
      if (!window.confirm(t('list.undo_all.confirm', { n: movable }))) return;
      var n = takeBack(ids, 'empty-tray');
      note('empty-tray', null, which, String(n));
      closeOverlays();
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
        if (nArrived) said.push(tn('toast.updated.arrived', nArrived));
        if (nFailed) said.push(tn('toast.updated.failed', nFailed));
        if (nLive) said.push(tn('toast.updated.live', nLive));
        toast(tn('toast.updated', n), { level: nFailed ? 'warn' : 'ok', detail: said.join(' ') });
      }
      return { ok: true, rows: n };
    }
    window.deskIngest = ingest;


    // ── Saving ─────────────────────────────────────────────────────────
    // `saved` is what the storage is known to hold. Everything that differs from it is
    // unsaved work, and only the difference is sent -- which also means two people
    // reviewing different pages of one language merge instead of clobbering.
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(SAVEDKEY) || '{}') || {}; } catch (e) { saved = {}; }

    var btnSave = document.getElementById('btn-save');
    var saveStatus = document.getElementById('save-status');
    var saving = false;
    // Runbook WO-34 (decision A15): Save committed the reviewer's email address into a
    // public repository. It is switched off until WO-17 moves the decisions to private
    // storage; the button stays, says so, and explains itself on hover and on click.
    var SAVE_OFF = __SAVE_OFF__;

__DELTA_JS__
    function delta() { return deltaBetween(state, saved); }

    // Unsaved work is a fact about the REVIEWER, not about the page they happen to be
    // looking at. Making five changes in German, switching to French and finding an
    // empty bar reads as "nothing pending" -- and the tab gets closed. Every language
    // is counted, always.
    //
    // Every click repaints the bar, and the bar read and parsed all eight languages twice
    // and diffed seven of them: 88 ms a click on a fully decided desk at 4x CPU (review
    // round 2, L1 P3). A stored value is parsed once and its delta computed once, until
    // it changes. What these return is SHARED -- read it, never change it; readFresh()
    // is for a copy that will be changed.
    var parsedCache = Object.create(null);
    function readStored(key) {
      var raw;
      try { raw = localStorage.getItem(key) || '{}'; } catch (e) { return {}; }
      var hit = parsedCache[key];
      if (hit && hit.raw === raw) return hit.val;
      var val;
      try { val = JSON.parse(raw) || {}; } catch (e) { val = {}; }
      parsedCache[key] = { raw: raw, val: val };
      return val;
    }
    function readFresh(key) {
      try { return JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { return {}; }
    }
    function readLocale(code) { return readStored('cel-desk-' + code); }
    function readSaved(code) { return readStored('cel-desk-saved-' + code); }
    var deltaMemo = Object.create(null);
    function storedDelta(code) {
      var now = readLocale(code), was = readSaved(code), m = deltaMemo[code];
      if (m && m.now === now && m.was === was) return m.d;
      var d = deltaBetween(now, was);
      deltaMemo[code] = { now: now, was: was, d: d };
      return d;
    }

    function unsavedByLocale() {
      var out = {};
      LOCALES.forEach(function (code) {
        var d = code === CODE ? delta() : storedDelta(code);
        if (d.n) out[code] = d;
      });
      return out;
    }

    function paintSave() {
      var all = unsavedByLocale();
      var total = 0, others = 0;
      for (var c in all) { total += all[c].n; if (c !== CODE) others += all[c].n; }
      var elsewhere = document.getElementById('save-elsewhere');
      if (elsewhere) {
        elsewhere.hidden = others === 0;
        elsewhere.textContent = others ? t(SAVE_OFF ? 'save.off.elsewhere' : 'save.elsewhere', { n: others }) : '';
      }
      if (SAVE_OFF) {
        // aria-disabled, not disabled: a disabled button takes no hover, so it could
        // never say why it is off.
        btnSave.hidden = total === 0;
        btnSave.textContent = t('save.off.button');
        btnSave.classList.remove('is-primary');
        btnSave.setAttribute('aria-disabled', 'true');
        btnSave.setAttribute('data-tip', t('save.off.hint'));
        return;
      }
      btnSave.hidden = total === 0 || saving;
      btnSave.textContent = tn('save.button', total);
      btnSave.disabled = saving;
      btnSave.setAttribute('data-tip', others ? t('save.button.hint_elsewhere', { n: others }) : t('save.button.hint'));
    }

    // ── Saving: the sign-in Worker's desk storage (runbook WO-17) ─────────────────
    // A change names the version it was based on; the Worker applies it only on that
    // version and stamps who and when itself. At most 200 changes a request, one request
    // at a time. `saved` is the storage's copy, each with its `version`; the difference is
    // what is sent. The old path -- a GitHub workflow committing to the public repo -- is
    // gone (S2). Nothing leaves the browser while SAVE_OFF (WO-34).
    var DESK_CLIENT = 1;      // the Worker's DESK_MIN_CLIENT: below it, it says reload
    var CHUNK = 200;          // the Worker's most changes in one request

    function callProxy(payload) {
      var url = window.CEL_DISPATCH_URL;
      if (!url) return Promise.reject(new Error('not configured'));
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

    // Why a save stopped, as a COPY.md `save.reason.*` key. The raw answer goes to the log
    // for diagnosis, never on screen.
    function failureReason(r) {
      if (!r) return 'offline';
      if (r.status === 409) return 'reload';
      if (r.status === 401 || r.status === 403) return 'signed_out';
      if (r.status === 429) return /daily/.test((r.body && r.body.error) || '') ? 'daily' : 'cap';
      if (r.status === 503) return 'unavailable';
      if (r.status === 400) return 'refused';
      return 'trouble';
    }

    // Texts someone else saved first, per language, until the reviewer decides: stored,
    // so a reload cannot turn "decide first" into a silent overwrite.
    function conflictsOf(code) { return readFresh('cel-desk-conflicts-' + code); }
    var conflicts = conflictsOf(CODE);
    function persistConflicts(code, map) {
      try {
        if (Object.keys(map).length) localStorage.setItem('cel-desk-conflicts-' + code, JSON.stringify(map));
        else localStorage.removeItem('cel-desk-conflicts-' + code);
      } catch (e) {}
    }
    function clearConflict(uid) {
      if (!conflicts[uid]) return;
      delete conflicts[uid];
      persistConflicts(CODE, conflicts);
    }

    // The page a change names: the Page filter's when the text is on it, else its first
    // (the Worker's page map allows any page the text is on).
    function pageFor(pages) {
      if (!pages || !pages.length) return '';
      return fPage.value && pages.indexOf(fPage.value) !== -1 ? fPage.value : pages[0];
    }

    async function saveLanguage(code, d) {
      var units = await fetchUnits(code);
      var pages = Object.create(null);
      units.forEach(function (u) { pages[u.id] = u.pages; });
      var base = code === CODE ? saved : readFresh('cel-desk-saved-' + code);
      var waiting = code === CODE ? conflicts : conflictsOf(code);
      // A text waiting on a conflict decision is not sent again until it is decided.
      var uids = Object.keys(d.body).filter(function (uid) { return !waiting[uid]; });
      var out = { applied: 0, conflicts: 0, refused: 0, waiting: Object.keys(d.body).length - uids.length };
      for (var i = 0; i < uids.length; i += CHUNK) {
        var changes = uids.slice(i, i + CHUNK).map(function (uid) {
          return { unit: uid, page: pageFor(pages[uid]), base: (base[uid] && base[uid].version) || 0,
                   record: d.body[uid] };                // null: the decision was undone
        });
        var r = null;
        try {
          r = await callProxy({ action: 'desk-write', locale: code, client: DESK_CLIENT, changes: changes });
        } catch (e) { r = null; }
        if (!r || !r.ok) {
          var err = new Error(failureReason(r));
          err.detail = r ? r.status + ' ' + ((r.body && r.body.error) || '') : 'no answer';
          throw err;
        }
        (r.body.applied || []).forEach(function (a) {
          base[a.unit] = Object.assign(storedOnly(d.body[a.unit]), { version: a.version });
          out.applied++;
        });
        (r.body.conflicts || []).forEach(function (c) {
          // Their version becomes the base, so a later save of yours is a deliberate choice
          // over theirs -- and it waits until the reviewer makes it (the row says so).
          base[c.unit] = c.current ? Object.assign(storedOnly(c.current), { version: c.current.version }) : {};
          waiting[c.unit] = c.current || { gone: true };
          out.conflicts++;
        });
        out.refused += (r.body.refused || []).length;
        // Bank each request as it lands: a failure on the next must not undo this one.
        try { localStorage.setItem('cel-desk-saved-' + code, JSON.stringify(base)); } catch (e) {}
        persistConflicts(code, waiting);
        if (code === CODE) saved = base;
      }
      return out;
    }

    async function save() {
      if (SAVE_OFF) {
        toast(t('save.off.title'), { level: 'warn', detail: t('save.off.hint') });
        return;
      }
      if (saving) return;                    // one save in flight, never two
      var all = unsavedByLocale();
      var codes = Object.keys(all);
      if (!codes.length) return;

      saving = true; paintSave();
      saveStatus.textContent = t('save.status.saving');
      saveStatus.className = 'desk-status';

      var got = { applied: 0, conflicts: 0, refused: 0, waiting: 0 }, done = [], failed = null;
      try {
        for (var i = 0; i < codes.length; i++) {
          var c = codes[i];
          if (codes.length > 1) {
            saveStatus.textContent = t('save.status.language',
              { language: t('lang.' + c), i: i + 1, count: codes.length });
          }
          var res = await saveLanguage(c, all[c]);
          for (var k in got) got[k] += res[k];
          done.push(c);
        }
      } catch (err) {
        failed = err;
      }

      saving = false;
      rows.forEach(paint);
      paintSave(); paintBar(); applyFilters();

      if (failed) {
        saveStatus.textContent = t('save.status.failed');
        saveStatus.className = 'desk-status is-error';
        note('save-failed', null, failed.message + ': ' + (failed.detail || ''), done.join(','));
        var reason = t('save.reason.' + failed.message);
        toast(done.length ? t('save.partial.title', { done: done.length, count: codes.length })
                          : t('save.failed.title'),
              { level: 'err',
                detail: t(done.length ? 'save.partial.detail' : 'save.failed.detail', { reason: reason }) });
        return;
      }
      note('save', null, String(got.applied), codes.join(','));
      saveStatus.textContent = '';
      if (got.applied) {
        toast(t('save.done.title'), { level: 'ok',
          detail: codes.length > 1 ? t('save.done.detail_langs', { n: got.applied, count: codes.length })
                                   : tn('save.done.detail', got.applied) });
      }
      if (got.conflicts || got.waiting) {
        toast(t('save.conflicts.title'), { level: 'warn', sticky: true,
                                           detail: tn('save.conflicts.detail', got.conflicts + got.waiting) });
      }
      if (got.refused) {
        toast(t('save.refused.title'), { level: 'warn', detail: tn('save.refused.detail', got.refused) });
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
      x.setAttribute('aria-label', t('toast.close'));
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
      placeToasts();
      return close;
    }
    window.deskToast = toast;

    // Messages sit above the bar at the bottom, never on it: in the corner they covered
    // View approved and Save, and hovering one to read it kept it there (review round 2,
    // L5 #2). The bar is sticky, so where it is depends on the scroll.
    function placeToasts() {
      if (!toastStack.firstChild) return;
      var r = savebar.hidden ? null : savebar.getBoundingClientRect();
      var lift = r && r.top < window.innerHeight ? Math.ceil(window.innerHeight - r.top) + 10 : 0;
      toastStack.style.bottom = lift ? lift + 'px' : '';
    }
    var placing = false;
    window.addEventListener('scroll', function () {
      if (placing) return;
      placing = true;
      requestAnimationFrame(function () { placing = false; placeToasts(); });
    }, { passive: true });
    window.addEventListener('resize', placeToasts);

    // ── URL state + language switching ─────────────────────────────────
    // The filters live in the query string so that switching language keeps you on
    // the same page and the same view. Before this, changing language meant going
    // back to the index and setting the filters up again.
    // Reviewers share these addresses, so they say what a reviewer would (desk audit §6
    // #2, runbook WO-09): ?show=approved, ?show=requested. The list values underneath are
    // unchanged, and a link carrying the old value still opens the same list.
    // "All texts" is `all`: it wrote nothing, so a reload fell back to Flagged (review
    // round 2, L5 #5).
    var SHOW_WORD = { csv: 'approved', draft: 'requested', '': 'all' };
    var SHOW_ALIAS = { approved: 'csv', requested: 'draft', all: '' };
    function showFromUrl(v) {
      return Object.prototype.hasOwnProperty.call(SHOW_ALIAS, v) ? SHOW_ALIAS[v] : v;
    }

    function syncUrl() {
      var q = new URLSearchParams();
      if (fPage.value) q.set('page', fPage.value);
      q.set('show', Object.prototype.hasOwnProperty.call(SHOW_WORD, fState.value) ? SHOW_WORD[fState.value] : fState.value);
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
    function outstanding(lc, recs) {
      return (WORTH[lc] || []).filter(function (uid) { return stageOf(recs[uid]) === 'todo'; }).length;
    }
    var outstandingMemo = Object.create(null);
    function storedOutstanding(lc) {
      var recs = readLocale(lc), m = outstandingMemo[lc];
      if (m && m.recs === recs) return m.n;
      var n = outstanding(lc, recs);
      outstandingMemo[lc] = { recs: recs, n: n };
      return n;
    }
    function paintLocaleCounts() {
      Array.prototype.forEach.call(document.querySelectorAll('[data-loc-count]'), function (el) {
        var lc = el.getAttribute('data-loc-count');
        var n = lc === CODE ? outstanding(lc, state) : storedOutstanding(lc);
        el.textContent = n ? String(n) : '';
        el.hidden = !n;
        var link = el.parentNode;
        var nm = link && link.querySelector('.desk-loc-name');
        // The name is visually hidden on inactive tabs; a hover says it, and the count.
        if (nm) link.setAttribute('data-tip', n ? tn('locale.langs.hover_flagged', n, { language: nm.textContent })
                                                 : t('locale.langs.hover', { language: nm.textContent }));
      });
    }

    function resetView() {
      justActed = Object.create(null);   // changing the view is when rows may move
      applyFilters();
      syncUrl();
    }
    [fPage, fState].forEach(function (el) { el.addEventListener('change', resetView); });
    fQ.addEventListener('input', resetView);
    // An emptied view offers the way back instead of a dead end.
    document.getElementById('no-rows-reset').addEventListener('click', function () {
      fPage.value = ''; fState.value = ''; fQ.value = '';
      resetView();
    });

    // ── Loading a language ─────────────────────────────────────────────
    // One path for the first load and for every switch: the texts and the saved decisions
    // are fetched TOGETHER (the decisions used to wait until 823 rows were built), and a
    // language already fetched in the background costs nothing to open.
    // The desk's own folder, whatever the site mounts it under, so every language's
    // files resolve the same way before and after the address changes.
    var BASE = new URL('../', location.href).pathname;
    var unitCache = Object.create(null);
    function fetchUnits(code) {
      if (!unitCache[code]) {
        unitCache[code] = fetch(BASE + code + '/units.json', { cache: 'no-cache' })
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          })
          .catch(function (e) { delete unitCache[code]; throw e; });
      }
      return unitCache[code];
    }

    function paintLocaleChrome(code, total) {
      var name = t('lang.' + code);
      document.title = t('meta.locale.title', { language: name });
      document.getElementById('desk-eyebrow').textContent = t('locale.eyebrow', { LANGUAGE: name.toUpperCase() });
      document.getElementById('col-target').textContent = t('table.col.target', { language: name });
      fQ.setAttribute('placeholder', t('filter.search.placeholder', { language: name }));
      if (total != null) {
        var sub = document.getElementById('desk-subtitle');
        sub.textContent = '';
        var bdi = document.createElement('bdi');
        bdi.textContent = LOCALE_INFO[code].endonym;
        sub.appendChild(bdi);
        sub.appendChild(document.createTextNode(' \u00b7 ' + t('locale.subtitle', { total: total })));
      }
      Array.prototype.forEach.call(document.querySelectorAll('.desk-loc'), function (a) {
        var on = a.getAttribute('data-loc') === code;
        a.classList.toggle('is-active', on);
        if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
      });
    }

    // Only the newest load may build. Checking the language alone was not enough: de
    // (still loading) -> fr -> de left two live loads for de, and both built their 823
    // rows into one table (review round 2, L1 P1-1).
    var loadSeq = 0, booted = false, loadFailedFor = null;
    async function loadLocale(anchor) {
      var seq = ++loadSeq;
      var code = CODE;
      var unitsP = fetchUnits(code);
      // The storage's copy, fetched with the texts (runbook WO-17). While saving is off the
      // desk asks nothing of the storage: every decision is this browser's.
      var serverP = SAVE_OFF ? Promise.resolve(null)
        : callProxy({ action: 'desk-read', locale: code }).catch(function (e) { return e; });
      var units;
      try { units = await unitsP; }
      catch (e) { if (seq !== loadSeq) return; throw e; }   // a stale failure is not news
      if (seq !== loadSeq) return;          // a newer switch has taken over
      // What the storage holds is the baseline, with each text's version. Anything decided
      // in THIS browser and not yet saved stays exactly as it is and still counts as
      // unsaved -- the server copy fills in only the texts this browser has never touched,
      // which is what makes a second machine useful instead of blank.
      try {
        var sr = await serverP;
        if (seq !== loadSeq) return;        // switched away while this was loading
        if (sr instanceof Error) throw sr;
        if (sr && !sr.ok) throw new Error('HTTP ' + sr.status);
        if (sr) {
          var server = (sr.body && sr.body.decisions) || {};
          var adopted = 0;
          saved = {};
          for (var uid in server) {
            saved[uid] = Object.assign(storedOnly(server[uid]), { version: server[uid].version });
            // Adopt only where this browser holds NOTHING -- an undone decision and a draft
            // that came back both have no tray, and neither may be overwritten.
            if (!hasContent(state[uid]) && hasContent(server[uid])) {
              state[uid] = Object.assign(storedOnly(server[uid]), { by: server[uid].by, at: server[uid].at });
              adopted++;
            }
          }
          try { localStorage.setItem(SAVEDKEY, JSON.stringify(saved)); } catch (e) {}
          persist();
          if (adopted) note('adopted', null, String(adopted), null);
        }
      } catch (e) {
        // Unreadable storage is not "nothing saved": a desk that booted without a
        // colleague's decisions, then saved, would present its own as the newer ones.
        note('decisions-load-failed', null, String(e && e.message || e), null);
        toast(t('toast.saved_load.title'), { level: 'warn', detail: t('toast.saved_load.detail') });
      }
      if (seq !== loadSeq) return;
      // Built only now, with the decisions in hand: a row never shows undecided for a
      // frame and then flips.
      buildRows(units);
      paintLocaleChrome(code, units.length);
      loadFailedFor = null;
      countLine.className = 'subtle';     // an earlier failure's styling goes with it
      // The address's filters apply to whichever load lands first -- the page's own, or
      // a switch made before it finished.
      var first = !booted;
      booted = true;
      if (first) {
        // ?show= lets the locale index link straight into a tray.
        var qs = new URLSearchParams(location.search);
        var want = qs.get('show');
        if (want !== null) want = showFromUrl(want);
        var known = ['todo', 'csv', 'draft', 'edited', 'check', 'arrived',
                     'sending', 'failed', 'exported', 'live', ''];
        if (want !== null && known.indexOf(want) !== -1) {
          fState.value = want;
        } else if (rows.some(function (tr) { return stage(tr.getAttribute('data-uid')) === 'arrived'; })) {
          // Coming back after a batch, the question is "what came back", not "where
          // was I". Land on exactly those rows without being asked.
          fState.value = 'arrived';
        }
        // Only a page the desk has: an unknown one blanked the select and showed everything.
        var pg = qs.get('page');
        if (pg && Array.prototype.some.call(fPage.options, function (o) { return o.value === pg; })) fPage.value = pg;
        if (qs.get('q')) fQ.value = qs.get('q');
      }
      rows.forEach(paint);
      paintBar();
      applyFilters();
      syncUrl();
      paintLocaleCounts();
      attachRows(anchor && anchor.uid);
      if (anchor) {
        var at = rows.find(function (tr) { return tr.getAttribute('data-uid') === anchor.uid; });
        if (at && !at.hidden) window.scrollBy(0, at.getBoundingClientRect().top - anchor.top);
      }
      // Once per page, not per switch: sixteen switches were sixteen log entries in each
      // language, and the eight capped logs nearly filled the origin (review round 2).
      if (first) note('load', null, String(units.length), null);
      // What the browser tests time (runbook WO-09, G9 budgets): from the switch, or the
      // page opening, to the new rows painted on screen.
      if (window.performance && performance.mark) {
        requestAnimationFrame(function () {
          setTimeout(function () { if (seq === loadSeq) performance.mark('desk-ready:' + code); }, 0);
        });
      }
    }

    function loadFailed(err) {
      // Say so in the page. A desk that silently shows zero rows looks like
      // "nothing to review", which is the opposite of what has happened.
      countLine.textContent = t('count.failed', { error: err.message });
      countLine.className = 'subtle desk-status is-error';
      loadFailedFor = CODE;                // its own tab now tries again
      noRows.hidden = true;
      note('load-failed', null, err.message, null);
      toast(t('toast.load.title'), { level: 'err', detail: t('toast.load.detail', { error: err.message }) });
    }

    // The row at the top of the reader's view, and where it sat, so a switch can put the
    // same English text back in the same place.
    function viewAnchor() {
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].hidden) continue;
        var r = rows[i].getBoundingClientRect();
        if (r.bottom > 0) return { uid: rows[i].getAttribute('data-uid'), top: r.top };
      }
      return null;
    }

    function switchTo(code, push) {
      // The open language is not a switch -- unless it failed to load, when its own tab
      // is the way to try again. It did nothing (review round 2, L1 P2-4).
      var again = code === CODE;
      if (again && loadFailedFor !== code) return;
      flushEditors();
      // A list belongs to its language: left open over the next one, its Undo changed
      // the language on screen, not the one it listed (review round 2, L1 P0).
      closeOverlays();
      if (window.performance && performance.mark) performance.mark('desk-switch:' + code);
      var anchor = viewAnchor();
      setLocale(code);
      state = readFresh(KEY);
      saved = readFresh(SAVEDKEY);
      conflicts = conflictsOf(code);
      try { hist = JSON.parse(localStorage.getItem(LOGKEY) || '[]') || []; } catch (e) { hist = []; }
      picked = Object.create(null);
      lastPicked = -1;
      cursor = -1;
      justActed = Object.create(null);
      liveText = Object.create(null);
      sourceText = Object.create(null);
      attachGen++;                         // stop the old language's remaining slices
      body.textContent = '';
      rows = [];
      paintLocaleChrome(code, null);
      if (push && !again) history.pushState(null, '', BASE + code + '/' + location.search);
      return loadLocale(anchor).catch(loadFailed);
    }

    // Another tab of this browser -- a second desk, or the index's Discard -- wrote this
    // language. Adopt it: each tab wrote its whole copy, so the second tab's next click
    // erased the first tab's work, and a Discard on the index came back after one more
    // click here (review round 2, L1 P1-2).
    function adoptStored() {
      state = readFresh(KEY);
      saved = readFresh(SAVEDKEY);
      conflicts = conflictsOf(CODE);
      // Nothing built yet -- loading, or failed to load: the load paints from `state`, and a
      // failure's message must stay on screen (round 3: it became "Showing 0 of 0").
      if (!rows.length) return;
      rows.forEach(paint); paintBar(); applyFilters();
      if (openTray) paintTray();
    }
    window.addEventListener('storage', function (ev) {
      if (ev.key === KEY || ev.key === SAVEDKEY || ev.key === 'cel-desk-conflicts-' + CODE || ev.key === null) adoptStored();
      else if (ev.key.indexOf('cel-desk-') === 0 && ev.key.indexOf('cel-desk-log-') !== 0) paintBar();
    });
    window.addEventListener('pageshow', function (ev) { if (ev.persisted) adoptStored(); });

    // ── Boot ───────────────────────────────────────────────────────────
    loadLocale(null).then(function () {
      // With the first language on screen, fetch the rest while the reviewer reads.
      var rest = function () {
        Object.keys(LOCALE_INFO).forEach(function (c) { if (c !== CODE) fetchUnits(c).catch(function () {}); });
      };
      if (window.requestIdleCallback) window.requestIdleCallback(rest, { timeout: 3000 });
      else setTimeout(rest, 1500);
    }).catch(loadFailed);
  })();
  </script>
""".replace("__STAGE_JS__", _STAGE_JS).replace("__WORTH__", worth_js).replace(
    "__CODE__", code).replace("__LOCALE_INFO__", json.dumps(
        {c: {"endonym": e, "rtl": d == "rtl"} for c, e, d, _f in LOCALES}, ensure_ascii=False)).replace(
    "__LOCALES__", json.dumps([c for c, *_ in LOCALES])).replace(
    "__HELPERS__", JS_HELPERS + _TIP_JS).replace("__DELTA_JS__", _DELTA_JS).replace(
    "__SAVE_OFF__", "true" if SAVE_OFF else "false").replace("__COPY__", js_table())


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

    for code, _endonym, _direction, _flag in LOCALES:
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
        target.write_text(render_locale(code, units), encoding="utf-8")
        written.append(target)

    print(f"{len(units)} reviewable units")
    for p in written:
        print(f"  wrote {p} ({p.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
