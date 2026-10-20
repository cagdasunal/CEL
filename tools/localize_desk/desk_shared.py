#!/usr/bin/env python3
"""What every desk page shares: the four pages, the eight locales, where the unit files and the output
live, the save switch, the page head, and the three scripts (the stage rules, the sign-in proxy, the
tooltip) that more than one page inlines.

Basecamp #451, cleanup C2 and C4 (monorepo CEL-051, CEL-050). These were defined in `generate_desk_page.py`,
the first desk's generator, which the document page and the rules page read them from; it is deleted. They
are defined once, here.

THE THREE SCRIPTS ARE NON-RAW PYTHON STRINGS. A backslash escape inside them is a SyntaxWarning or is
quietly turned into another character; the runbook's section 1.7 has the trap. Text changed inside them
changes every page that inlines it: regenerate `docs/admin/localization/**` with
`python3 -m localize_desk.generate_document_page` and `generate_rules_page`.
"""
from __future__ import annotations

import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from localize_desk.copy_text import t  # noqa: E402

from dashboard import (  # noqa: E402
    AUTH_SCRIPT_TAG,
    DASHBOARD_CSS_LINK,
    EXTERNAL_REPO_ROOT,
    render_favicon_tag,
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

# The four pages, by the key the unit files carry; their labels are copy (`page.<key>`).
PAGE_KEYS = ["vancouver", "vs-toronto", "cost-of-studying-english", "how-long-to-learn-english"]

def lang_name(code: str) -> str:
    return t(f"lang.{code}")

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
        f"  {DASHBOARD_CSS_LINK}",   # the stylesheet, with its content's hash (U3)
        "</head>",
        "<body>",
    ]

INDEX_REDIRECT_TO = "/admin/localization/document/"


def render_index_redirect() -> str:
    """The index page since CEL-045 (2026-10-20): the desk is the document page, so /admin/localization/ is
    only a redirect to it, in the shape /admin/ already uses. The dashboard's Localization tabs point here.
    `generate_document_page.main` writes it, beside its own folder (cleanup C4, CEL-050)."""
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">\n'
        '  <meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet, noimageindex">\n'
        f'  <meta http-equiv="refresh" content="0; url={INDEX_REDIRECT_TO}">\n'
        f'  <title>{escape(t("meta.index.title"))}</title>\n'
        '  <link rel="icon" type="image/png" href="/assets/img/favicon.png">\n'
        f"  <script>location.replace('{INDEX_REDIRECT_TO}');</script>\n"
        '</head>\n<body></body>\n</html>\n'
    )

# Why a save can stop -- each a COPY.md `save.reason.<name>` line. The page's failureReason()
# returns exactly these (tests/test_copy.py holds the two together).
SAVE_REASONS = ("offline", "reload", "signed_out", "cap", "daily", "unavailable", "refused", "trouble")

# Runbook WO-34 (decision A15): saving was switched off until WO-17 stored decisions
# privately; M1 switches it on. It stays as the one switch back (the harness's --save-off
# serves it off). One constant for the desk AND the index, so the two cannot disagree about it.
SAVE_OFF = False

# The ONE decider of what a row is (process doc §1). It is emitted into the locale
# pages AND the index from this single string: the index used to carry its own copy
# that knew nothing about `liveAt`/`exportedAt`, so the two pages could disagree about
# the same record.
_STAGE_JS = """\
    // The engine's rules for the stamps, line for line (monorepo tools/localize/storage.py:
    // instant(), failed_now(), in_flight() -- the parity test runs both on shared cases).
    // Two writers stamp rows, so stamps are compared as instants, never as text: "10:00:00Z"
    // sorts after "10:00:00.500Z" and is the earlier of the two. A stamp with no offset is UTC,
    // as the engine reads it -- Date.parse would take it as this browser's local time.
    var STAMP_OFFSET = new RegExp('(Z|z|[+-][0-9][0-9](:?[0-9][0-9])?)$');
    function instant(v) {
      if (!v || typeof v !== 'string') return null;
      var ms = Date.parse(v.indexOf(':') !== -1 && !STAMP_OFFSET.test(v) ? v + 'Z' : v);
      return isNaN(ms) ? null : ms;
    }
    // Why the last attempt failed, while nothing has happened since: `failed` is never cleared
    // by the storage, so a later send, arrival or decision ends it (review of WO-17, P2-4; U3's
    // B3-1). A failure whose time cannot be read stands.
    function failedNow(s) {
      if (!s.failed) return false;
      var at = instant(s.failedAt);
      if (at === null) return true;
      // A decision saved after the failure ends it too (the U3 review's B3-1): the reviewer's own
      // wording, a new ask, an undo. storage.failed_now and desk-summary's SQL read it the same.
      return ![s.sentAt, s.arrivedAt, s.decidedAt].some(function (v) { var t = instant(v); return t !== null && t > at; });
    }
    // Sent, and neither back nor failed since. A send whose time cannot be read is still out.
    function inFlight(s) {
      if (!s.sentAt) return false;
      var sent = instant(s.sentAt);
      if (sent === null) return true;
      return ![s.arrivedAt, s.failedAt].some(function (v) { var t = instant(v); return t !== null && t >= sent; });
    }
    function stageOf(s) {
      s = s || {};
      // A live row the reviewer has decided about again is NOT live any more from
      // their point of view -- the new decision is what is outstanding. So anything
      // in flight or freshly decided outranks where the text currently sits.
      if (failedNow(s)) return 'failed';
      if (inFlight(s)) return 'sending';
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
    // One text from the storage's three tables (runbook WO-25c): storage.merged, line for line.
    // The decision's fields, and its `at` as decidedAt; the engine's stamps as they are; then
    // Gemini's draft, when it arrived later than the decision was saved -- or there is no decision,
    // or no time to read -- whose text replaces the decision's, and the tray clears.
    var DECISION_FIELDS = ['tray', 'text', 'approvedAgainst', 'rejected'];
    var STAMP_KEYS = ['sentAt', 'arrivedAt', 'failed', 'failedAt', 'exportedAt', 'importedAt', 'liveAt', 'runId'];
    function merged(decision, stamps, draft) {
      var d = decision || {}, out = {};
      DECISION_FIELDS.forEach(function (k) { if (k in d) out[k] = d[k]; });
      if (d.at) out.decidedAt = d.at;
      if (stamps) STAMP_KEYS.forEach(function (k) { if (stamps[k] !== undefined && stamps[k] !== null) out[k] = stamps[k]; });
      var arrived = draft ? instant(draft.arrivedAt) : null;
      if (draft && draft.text !== undefined && draft.text !== null && arrived !== null) {
        var asked = instant(d.at);
        if (!decision || asked === null || arrived > asked) {
          out.text = draft.text;
          delete out.tray;
          var piped = instant(out.arrivedAt);
          if (piped === null || arrived > piped) out.arrivedAt = draft.arrivedAt;
        }
      }
      return out;
    }
    // desk-summary's answer for one text (monorepo stage_vectors.shape): what stageOf reads, the
    // times already compared -- an arrival only after the decision (ruling q3), and in the csv
    // tray a stamp only for the wording it was stamped for (exportedAt at or after decidedAt,
    // liveAt at or after that exportedAt). data/localize/stage-vectors.json holds the engine,
    // desk-summary's SQL and these two to one rule (stage_vectors.py runs them on every case).
    function arrivedSince(m) {
      if (!m.arrivedAt || m.tray) return false;
      var decided = instant(m.decidedAt), at = instant(m.arrivedAt);
      return decided === null || (at !== null && at > decided);
    }
    function exportCounts(m) {
      if (!m.exportedAt) return false;
      var decided = instant(m.decidedAt), exported = instant(m.exportedAt);
      return decided === null || (exported !== null && exported >= decided);
    }
    function liveCounts(m) {
      if (!m.liveAt || !exportCounts(m)) return false;
      var live = instant(m.liveAt), exported = instant(m.exportedAt);
      return live !== null && exported !== null && live >= exported;
    }
    function shapeOf(m) {
      var out = {};
      if (m.tray) out.tray = m.tray;
      if (m.text !== undefined && m.text !== null) out.text = true;
      if (failedNow(m)) out.failed = true;
      else if (inFlight(m)) out.sentAt = true;
      else if (arrivedSince(m)) out.arrivedAt = true;
      if (m.tray === 'csv' ? exportCounts(m) : m.exportedAt) out.exportedAt = true;
      if (m.tray === 'csv' ? liveCounts(m) : m.liveAt) out.liveAt = true;
      return out;
    }
"""

# The sign-in Worker, for the desk AND the index, from this one string: the session the
# dashboard's sign-in left in its cookie goes with every request. A request with no answer
# by `ms` is abandoned (runbook WO-18), so a hung request cannot hold the one slot for ever.
_PROXY_JS = """\
    function callProxy(payload, ms) {
      var url = window.CEL_DISPATCH_URL;
      if (!url) return Promise.reject(new Error('not configured'));
      var m = document.cookie.match(/(?:^|; )cel_session=([^;]*)/);
      payload.token = m ? m[1] : '';
      var ctl = ms && window.AbortController ? new AbortController() : null;
      var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms) : null;
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ctl ? ctl.signal : undefined
      }).then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (j) {
          return { status: resp.status, ok: resp.ok && j.ok !== false, body: j };
        });
      }).finally(function () { if (timer) clearTimeout(timer); });
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
