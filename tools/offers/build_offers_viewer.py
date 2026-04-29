"""Generate the Offers dashboard page.

Writes:
  <EXTERNAL_REPO_ROOT>/admin/offers/index.html
    — served at https://cel.englishcollege.com/admin/offers/

Reads:
  data/offers-extend-log.json  — most recent auto-extend run timestamp

No external dependencies beyond stdlib + tools.dashboard + tools.offers.
No module-level I/O.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from tools.dashboard import (
    AUTH_SCRIPT_TAG,
    EXTERNAL_REPO_ROOT,
    render_favicon_tag,
    render_page_chrome,
    render_sync_status_card,
    write_external_css,
    write_shell_html,
)
from tools.offers._token_helper import APIError, NetworkError, get_api_token
from tools.offers.api import list_all_offers
from tools.offers.regions import REGIONS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_FILE = DATA_DIR / "offers-extend-log.json"
OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "offers" / "index.html"

DEFAULT_EXTEND_DAYS = 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_to_display(ts_iso: str | None) -> str:
    if not ts_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ts_iso or "—"


def _relative_phrase(end_iso: str | None, now: datetime) -> str:
    if not end_iso:
        return ""
    try:
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        # endOf(day) UTC semantics
        effective_end = end.replace(hour=23, minute=59, second=59)
        diff = (effective_end - now).total_seconds()
        days = int(diff / 86400)
        if diff < 0:
            return "expired"
        if days == 0:
            return "expires today"
        if days == 1:
            return "expires in 1 day"
        return f"expires in {days} days"
    except (ValueError, TypeError):
        return ""


def _load_last_extend_ts() -> str | None:
    if not LOG_FILE.exists():
        return None
    try:
        data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        events = data.get("events", [])
        if events:
            return events[-1].get("ts")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _render_item_row(item: dict, now: datetime) -> str:
    fd = item.get("fieldData") or {}
    title = escape(fd.get("internal-title") or fd.get("name") or item.get("id", ""))
    end_date = fd.get("end-date", "")
    end_display = escape(_iso_to_display(end_date))
    rel = escape(_relative_phrase(end_date, now))

    raw_days = fd.get("auto-extend-days")
    if raw_days is None:
        days_value = DEFAULT_EXTEND_DAYS
        days_is_default = True
    else:
        days_value = int(raw_days)
        days_is_default = False
    default_marker = ' <span class="subtle">(default)</span>' if days_is_default else ''
    days_cell = (
        f'<div class="extend-edit" data-item-id="{escape(item.get("id", ""))}">'
        f'<input type="number" min="0" max="365" step="1" '
        f'class="extend-input" value="{days_value}" '
        f'data-original="{days_value}" '
        f'aria-label="Auto-extend days">'
        f'<button class="extend-save" type="button" disabled>Save</button>'
        f'<span class="extend-status" role="status"></span>'
        f'{default_marker}'
        f'</div>'
    )

    # Build details panel
    detail_rows: list[str] = []
    for field_key, label in [
        ("internal-title", "Internal Title"),
        ("end-date", "End Date"),
        ("auto-extend-days", "Auto-extend days"),
        ("targeted-countriess", "Targeted Countries (ISO)"),
        ("campus-3", "Campus"),
        ("most-popular-this-month", "Most Popular This Month"),
        ("slug", "Slug"),
    ]:
        val = fd.get(field_key)
        if val is None:
            continue
        detail_rows.append(
            f'        <dt>{escape(label)}</dt>'
            f'<dd>{escape(str(val))}</dd>'
        )
    if item.get("lastPublished"):
        detail_rows.append(
            f'        <dt>Last Published</dt>'
            f'<dd>{escape(str(item["lastPublished"]))}</dd>'
        )
    if item.get("isDraft"):
        detail_rows.append('        <dt>Status</dt><dd>Draft</dd>')

    details_html = "\n".join(detail_rows)

    return (
        f'      <tr>'
        f'<td>{title}</td>'
        f'<td><span class="date-primary">{end_display}</span>'
        f' <span class="subtle">({rel})</span></td>'
        f'<td>{days_cell}</td>'
        f'<td><details class="item-details"><summary>View</summary>'
        f'<dl>\n{details_html}\n        </dl>'
        f'</details></td>'
        f'</tr>'
    )


def _render_region_block(key: str, val: dict) -> str:
    countries_csv = val.get("countries", "")
    country_list = [c for c in countries_csv.split(",") if c]
    n = len(country_list)
    return (
        f'    <div class="region-block" data-region="{escape(key)}">'
        f'<h3>{escape(key)} '
        f'<span class="subtle region-count" data-count>({n} countr{"y" if n == 1 else "ies"})</span>'
        f'</h3>'
        f'<p class="subtle">action: {escape(val.get("action", "show"))}</p>'
        f'<label class="region-label">'
        f'ISO country codes (comma-separated, no spaces):'
        f'<textarea class="region-input" rows="3" '
        f'data-original="{escape(countries_csv)}" '
        f'aria-label="Country codes for {escape(key)}">{escape(countries_csv)}</textarea>'
        f'</label>'
        f'<div class="region-actions">'
        f'<button class="region-save" type="button" disabled>Save</button>'
        f'<span class="region-status" role="status"></span>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# HTML renderer (pure — tests cover this)
# ---------------------------------------------------------------------------

def render_html(items: list[dict] | None = None, log_events: list | None = None) -> str:
    now = datetime.now(timezone.utc)
    if items is None:
        items = []
    if log_events is None:
        log_events = []

    # Status banner
    last_ts = log_events[-1].get("ts") if log_events else None
    if last_ts:
        last_display = _iso_to_display(last_ts)
        status_label = f"Auto-extend last ran: {last_display}."
        is_ok = True
    else:
        status_label = "Auto-extend has not yet run."
        is_ok = True

    subtitle = f"{len(items)} active offer{'s' if len(items) != 1 else ''} · auto-extend cron daily 02:17 UTC"

    # Tab-toggle + GitHub dispatch controller
    tab_script = """\
  <script>
  (function () {
    var GH_OWNER = 'cagdasunal';
    var GH_REPO  = 'CEL';
    var PAT_KEY  = 'cel_admin_gh_pat';
    var ADMIN_KEY = 'cel_admin_mode';
    var ITEM_WORKFLOW    = 'offers-edit-item.yml';
    var REGIONS_WORKFLOW = 'offers-edit-regions.yml';

    // ── Admin mode detection ─────────────────────────────────────────
    // Admin mode unlocks: PAT banner, editor inputs (writeable), Save buttons.
    // Activate by visiting the page with ?admin=1 — then it's persisted in
    // localStorage (top-window only; iframe inherits via the same origin).
    // Clear with ?admin=0.
    try {
      var qs = new URLSearchParams(location.search);
      if (qs.get('admin') === '1') localStorage.setItem(ADMIN_KEY, '1');
      if (qs.get('admin') === '0') localStorage.removeItem(ADMIN_KEY);
    } catch (_) {}
    var isAdmin = false;
    try { isAdmin = localStorage.getItem(ADMIN_KEY) === '1'; } catch (_) {}
    if (isAdmin) document.body.classList.add('is-admin');

    function applyTab() {
      var hash = (location.hash || '#list').slice(1);
      if (hash !== 'list' && hash !== 'settings') hash = 'list';
      document.querySelectorAll('[data-tab]').forEach(function(el) {
        el.classList.toggle('is-active', el.getAttribute('data-tab') === hash);
      });
      document.querySelectorAll('.offers-tab-link').forEach(function(a) {
        a.classList.toggle('is-active', a.getAttribute('href') === '#' + hash);
      });
    }
    window.addEventListener('hashchange', applyTab);
    applyTab();

    // ── GitHub PAT helpers ────────────────────────────────────────────
    function getPat() { try { return localStorage.getItem(PAT_KEY) || ''; } catch (_) { return ''; } }
    function setPat(v) { try { localStorage.setItem(PAT_KEY, v); } catch (_) {} }
    function clearPat() { try { localStorage.removeItem(PAT_KEY); } catch (_) {} }

    function refreshBanner() {
      var banner = document.getElementById('pat-banner');
      if (!banner) return;
      banner.classList.toggle('hidden', !!getPat());
    }

    function dispatchWorkflow(workflow, inputs) {
      var pat = getPat();
      if (!pat) return Promise.reject(new Error('GitHub PAT not set. Open the banner above to add it.'));
      var url = 'https://api.github.com/repos/' + GH_OWNER + '/' + GH_REPO +
                '/actions/workflows/' + workflow + '/dispatches';
      return fetch(url, {
        method: 'POST',
        headers: {
          'Accept': 'application/vnd.github+json',
          'Authorization': 'Bearer ' + pat,
          'X-GitHub-Api-Version': '2022-11-28',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ref: 'main', inputs: inputs })
      }).then(function(resp) {
        if (resp.status === 204) return { ok: true };
        return resp.text().then(function(txt) {
          var msg = 'HTTP ' + resp.status;
          try { var j = JSON.parse(txt); if (j.message) msg += ': ' + j.message; }
          catch (_) { msg += ': ' + txt.slice(0, 120); }
          throw new Error(msg);
        });
      });
    }

    function pollLatestRun(workflow) {
      var pat = getPat();
      if (!pat) return Promise.reject(new Error('PAT missing'));
      var url = 'https://api.github.com/repos/' + GH_OWNER + '/' + GH_REPO +
                '/actions/workflows/' + workflow + '/runs?per_page=1';
      return fetch(url, {
        headers: { 'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + pat }
      }).then(function(r) { return r.json(); })
        .then(function(j) {
          var run = (j.workflow_runs || [])[0];
          if (!run) return null;
          return { status: run.status, conclusion: run.conclusion, html_url: run.html_url };
        });
    }

    // Wait until a run finishes (max 90 s, 3 s polling)
    function awaitRun(workflow, statusEl) {
      var start = Date.now();
      function tick() {
        return pollLatestRun(workflow).then(function(run) {
          if (!run) {
            statusEl.textContent = 'queueing…';
            statusEl.className = statusEl.className.replace(/\\bis-(ok|error)\\b/g, '').trim();
          } else if (run.status !== 'completed') {
            statusEl.textContent = run.status + '…';
            statusEl.className = statusEl.className.replace(/\\bis-(ok|error)\\b/g, '').trim();
          } else {
            if (run.conclusion === 'success') {
              statusEl.textContent = '✓ saved';
              statusEl.className += ' is-ok';
            } else {
              statusEl.textContent = '✗ ' + (run.conclusion || 'failed');
              statusEl.className += ' is-error';
            }
            return run;
          }
          if (Date.now() - start > 90000) {
            statusEl.textContent = 'timeout (check Actions tab)';
            statusEl.className += ' is-error';
            return null;
          }
          return new Promise(function(resolve) {
            setTimeout(function() { resolve(tick()); }, 3000);
          });
        });
      }
      return tick();
    }

    // ── PAT banner controller ─────────────────────────────────────────
    document.addEventListener('click', function(ev) {
      if (ev.target.id === 'pat-save') {
        var input = document.getElementById('pat-input');
        var v = (input.value || '').trim();
        if (v) { setPat(v); refreshBanner(); input.value = ''; }
      } else if (ev.target.id === 'pat-clear') {
        clearPat(); refreshBanner();
      } else if (ev.target.id === 'pat-toggle') {
        var b = document.getElementById('pat-banner');
        if (b) b.classList.toggle('hidden');
      }
    });

    // ── Auto-extend-days inline edit ───────────────────────────────────
    document.addEventListener('input', function(ev) {
      if (!ev.target.classList || !ev.target.classList.contains('extend-input')) return;
      var wrap = ev.target.closest('.extend-edit');
      var btn = wrap.querySelector('.extend-save');
      btn.disabled = (ev.target.value === ev.target.dataset.original) ||
                     (ev.target.value === '' || isNaN(parseInt(ev.target.value, 10)));
    });

    document.addEventListener('click', function(ev) {
      if (!ev.target.classList || !ev.target.classList.contains('extend-save')) return;
      var wrap = ev.target.closest('.extend-edit');
      var input = wrap.querySelector('.extend-input');
      var status = wrap.querySelector('.extend-status');
      var itemId = wrap.dataset.itemId;
      var days = parseInt(input.value, 10);
      if (isNaN(days) || days < 0) { status.textContent = 'invalid'; status.className = 'extend-status is-error'; return; }
      ev.target.disabled = true;
      input.disabled = true;
      status.textContent = 'dispatching…';
      status.className = 'extend-status';
      dispatchWorkflow(ITEM_WORKFLOW, { item_id: itemId, days: String(days) })
        .then(function() {
          // Give GitHub ~2s to register the run
          return new Promise(function(r) { setTimeout(r, 2000); });
        })
        .then(function() { return awaitRun(ITEM_WORKFLOW, status); })
        .then(function(run) {
          if (run && run.conclusion === 'success') {
            input.dataset.original = String(days);
          }
        })
        .catch(function(err) {
          status.textContent = '✗ ' + err.message;
          status.className = 'extend-status is-error';
        })
        .finally(function() {
          input.disabled = false;
          ev.target.disabled = (input.value === input.dataset.original);
        });
    });

    // ── Regions Settings inline edit ───────────────────────────────────
    document.addEventListener('input', function(ev) {
      if (!ev.target.classList || !ev.target.classList.contains('region-input')) return;
      var block = ev.target.closest('.region-block');
      var btn = block.querySelector('.region-save');
      var v = (ev.target.value || '').trim().toUpperCase().replace(/\\s+/g, '');
      var validCsv = /^[A-Z]{2}(,[A-Z]{2})*$/.test(v);
      btn.disabled = !validCsv || (v === ev.target.dataset.original);
      // Update count display
      var n = v ? v.split(',').length : 0;
      var counter = block.querySelector('[data-count]');
      if (counter) counter.textContent = '(' + n + ' countr' + (n === 1 ? 'y' : 'ies') + ')';
    });

    document.addEventListener('click', function(ev) {
      if (!ev.target.classList || !ev.target.classList.contains('region-save')) return;
      var block = ev.target.closest('.region-block');
      var input = block.querySelector('.region-input');
      var status = block.querySelector('.region-status');
      var region = block.dataset.region;
      var v = (input.value || '').trim().toUpperCase().replace(/\\s+/g, '');
      if (!/^[A-Z]{2}(,[A-Z]{2})*$/.test(v)) { status.textContent = 'invalid CSV'; status.className = 'region-status is-error'; return; }
      ev.target.disabled = true;
      input.disabled = true;
      status.textContent = 'dispatching…';
      status.className = 'region-status';
      dispatchWorkflow(REGIONS_WORKFLOW, { region: region, countries: v })
        .then(function() { return new Promise(function(r) { setTimeout(r, 2000); }); })
        .then(function() { return awaitRun(REGIONS_WORKFLOW, status); })
        .then(function(run) {
          if (run && run.conclusion === 'success') {
            input.dataset.original = v;
            input.value = v;
          }
        })
        .catch(function(err) {
          status.textContent = '✗ ' + err.message;
          status.className = 'region-status is-error';
        })
        .finally(function() {
          input.disabled = false;
          ev.target.disabled = (input.value === input.dataset.original);
        });
    });

    refreshBanner();
  })();
  </script>"""

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Offers — English College Admin</title>")
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f"  {render_favicon_tag()}")
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("  <style>")
    parts.append("    [data-tab]{display:none}")
    parts.append("    [data-tab].is-active{display:block}")
    parts.append("    .offers-tab-link{display:inline-block;padding:6px 14px;margin-right:8px;border-radius:4px;text-decoration:none;color:inherit;border:1px solid #ccc}")
    parts.append("    .offers-tab-link.is-active{background:#f0e8d4;border-color:#9b8c7d;font-weight:600}")
    parts.append("    .item-details summary{cursor:pointer;color:#6b5f52}")
    parts.append("    .item-details dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin-top:8px}")
    parts.append("    .item-details dt{font-weight:600;white-space:nowrap}")
    parts.append("    .country-list{display:block;word-break:break-all;font-size:0.85em}")
    parts.append("    .region-block{margin-bottom:32px;padding:16px;border:1px solid #d9cfb9;border-radius:8px;background:#fbf6e9}")
    parts.append("    .region-block h3{margin:0 0 8px 0;text-transform:uppercase;letter-spacing:0.04em}")
    parts.append("    .region-label{display:block;margin:8px 0;font-weight:500}")
    parts.append("    .region-input{display:block;width:100%;margin-top:6px;padding:8px;font-family:ui-monospace,monospace;font-size:0.85em;border:1px solid #b8a98c;border-radius:4px;background:#fff;resize:vertical}")
    parts.append("    .region-actions{margin-top:8px;display:flex;align-items:center;gap:12px}")
    parts.append("    .region-save,.extend-save{padding:6px 14px;border:1px solid #6b5f52;border-radius:4px;background:#f0e8d4;color:#3a342b;cursor:pointer;font-weight:600}")
    parts.append("    .region-save:disabled,.extend-save:disabled{opacity:0.4;cursor:not-allowed}")
    parts.append("    .region-save:hover:not(:disabled),.extend-save:hover:not(:disabled){background:#e7daa8}")
    parts.append("    .region-status,.extend-status{font-size:0.85em;color:#6b5f52}")
    parts.append("    .region-status.is-ok,.extend-status.is-ok{color:#3a7a3a}")
    parts.append("    .region-status.is-error,.extend-status.is-error{color:#a54040}")
    parts.append("    .extend-edit{display:flex;align-items:center;gap:8px;flex-wrap:wrap}")
    parts.append("    .extend-input{width:80px;padding:6px;font-family:inherit;font-size:0.95em;border:1px solid #b8a98c;border-radius:4px;background:#fff}")
    parts.append("    .date-primary{font-variant-numeric:tabular-nums}")
    parts.append("    .pat-banner{margin:16px 0;padding:12px 16px;background:#F9F1DF;border:1px solid #d9cfb9;border-radius:6px}")
    parts.append("    .pat-banner.hidden{display:none}")
    parts.append("    .pat-input{width:100%;max-width:520px;padding:8px;font-family:ui-monospace,monospace;font-size:0.85em;border:1px solid #b8a98c;border-radius:4px;margin-top:6px;background:#fff}")
    parts.append("    .pat-actions{margin-top:8px;display:flex;gap:8px}")
    parts.append("    /* Admin-only: hidden by default; shown when ?admin=1 or localStorage cel_admin=1 */")
    parts.append("    .admin-only{display:none}")
    parts.append("    body.is-admin .admin-only{display:initial}")
    parts.append("    body.is-admin .admin-only.pat-banner{display:block}")
    parts.append("    /* Inputs: read-only by default; become editable when admin */")
    parts.append("    body:not(.is-admin) .extend-input,body:not(.is-admin) .region-input{pointer-events:none;background:transparent;border-color:transparent;color:#3a342b;font-weight:500}")
    parts.append("    body:not(.is-admin) .extend-save,body:not(.is-admin) .region-save{display:none}")
    parts.append("    body:not(.is-admin) .region-input{resize:none}")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Page chrome
    parts.append(f'    {render_page_chrome(eyebrow="OFFERS", subtitle=subtitle)}')

    # Status card
    last_sync_display = _iso_to_display(last_ts) if last_ts else "Never"
    parts.append(f'    {render_sync_status_card(status_label, last_sync_display, is_ok=is_ok)}')

    # GitHub PAT banner — admin-only (hidden unless body.is-admin)
    parts.append('    <button id="pat-toggle" type="button" class="admin-only" style="margin:8px 0;font-size:0.85em;background:none;border:1px dashed #b8a98c;border-radius:4px;padding:4px 10px;cursor:pointer">⚙ GitHub credentials</button>')
    parts.append('    <section id="pat-banner" class="pat-banner admin-only">')
    parts.append('      <p style="margin:0 0 4px 0;font-weight:600">GitHub PAT required for editing</p>')
    parts.append('      <p class="subtle" style="margin:0">')
    parts.append('        Inline edits dispatch to a GitHub Action. Generate a fine-grained PAT at ')
    parts.append('        <a href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noopener">github.com/settings/personal-access-tokens</a>')
    parts.append('        with <strong>Actions: Read &amp; Write</strong> on the <code>cagdasunal/CEL</code> repo.')
    parts.append('        Stored locally in your browser only.')
    parts.append('      </p>')
    parts.append('      <input id="pat-input" class="pat-input" type="password" placeholder="github_pat_…" autocomplete="off">')
    parts.append('      <div class="pat-actions">')
    parts.append('        <button id="pat-save" type="button" class="region-save">Save token</button>')
    parts.append('        <button id="pat-clear" type="button" class="region-save" style="background:#f0d4d4;border-color:#a54040">Forget token</button>')
    parts.append('      </div>')
    parts.append('    </section>')

    # In-page tab nav
    parts.append('    <nav class="offers-tabs" style="margin-bottom:16px">')
    parts.append('      <a class="offers-tab-link" href="#list">Offers List</a>')
    parts.append('      <a class="offers-tab-link" href="#settings">Settings</a>')
    parts.append("    </nav>")

    # ── Tab: List ──────────────────────────────────────────────────────────
    parts.append('    <section data-tab="list">')
    if items:
        parts.append("      <table>")
        parts.append("        <thead>")
        parts.append("          <tr>")
        parts.append("            <th>Internal Title</th>")
        parts.append("            <th>End Date</th>")
        parts.append("            <th>Auto-extend days</th>")
        parts.append("            <th>Details</th>")
        parts.append("          </tr>")
        parts.append("        </thead>")
        parts.append("        <tbody>")
        for item in items:
            parts.append(_render_item_row(item, now))
        parts.append("        </tbody>")
        parts.append("      </table>")
    else:
        parts.append('      <p class="empty">No offers yet.</p>')
    parts.append("    </section>")

    # ── Tab: Settings ──────────────────────────────────────────────────────
    parts.append('    <section data-tab="settings">')
    parts.append(
        '      <p>Geotargetly region → ISO country mappings. Read-only. '
        'To change, edit <code>tools/cel-offers-js/cel-offers.js</code> '
        "in the monorepo and rebuild the bundle.</p>"
    )
    for key, val in REGIONS.items():
        parts.append(_render_region_block(key, val))
    parts.append("    </section>")

    # Footer
    gen_ts = now.strftime("%Y-%m-%d %H:%M UTC")
    parts.append("    <footer>")
    parts.append(
        f'      Total offers tracked: <strong>{len(items)}</strong>. '
        f"This page was generated on {escape(gen_ts)}. "
        "Auto-extend runs daily at 02:17 UTC."
    )
    parts.append("    </footer>")
    parts.append("  </div>")  # .dashboard-shell
    parts.append(tab_script)
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_offers_page(items: list[dict] | None = None) -> None:
    """Fetch data and write the offers viewer HTML to the CEL repo."""
    token = get_api_token()
    if items is None:
        if not token:
            raise RuntimeError("WEBFLOW_API_TOKEN unset")
        items = list_all_offers(token)

    log_events: list = []
    if LOG_FILE.exists():
        try:
            log_events = json.loads(LOG_FILE.read_text(encoding="utf-8")).get("events", [])
        except (json.JSONDecodeError, OSError):
            pass

    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(items, log_events), encoding="utf-8")


def main() -> int:
    token = get_api_token()
    if not token:
        print("[offers_viewer] WEBFLOW_API_TOKEN unset", file=sys.stderr)
        # Write fallback page so the file exists
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        fallback = (
            "<!DOCTYPE html><html lang='en'><head>"
            f"  {AUTH_SCRIPT_TAG}"
            '<meta charset=\"utf-8\"><title>Offers — English College Admin</title>'
            '<link rel="stylesheet" href="/assets/css/dashboard.css"></head>'
            "<body><div class='dashboard-shell'>"
            "<section class='status status-error error'>"
            "<p class='status-label'>Offers data temporarily unavailable.</p>"
            "<p>WEBFLOW_API_TOKEN is not set in this environment. "
            "The offers dashboard will populate on the next scheduled run.</p>"
            "</section></div></body></html>\n"
        )
        try:
            write_external_css(EXTERNAL_REPO_ROOT)
            write_shell_html(EXTERNAL_REPO_ROOT)
        except Exception:
            pass
        OUTPUT_FILE.write_text(fallback, encoding="utf-8")
        print(f"[offers_viewer] Wrote fallback page to {OUTPUT_FILE}", flush=True)
        return 2

    try:
        items = list_all_offers(token)
    except (APIError, NetworkError, Exception) as exc:
        print(f"[offers_viewer] ERROR fetching offers: {exc}", file=sys.stderr)
        # Write error fallback
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        fallback = (
            "<!DOCTYPE html><html lang='en'><head>"
            f"  {AUTH_SCRIPT_TAG}"
            '<meta charset=\"utf-8\"><title>Offers — English College Admin</title>'
            '<link rel="stylesheet" href="/assets/css/dashboard.css"></head>'
            "<body><div class='dashboard-shell'>"
            "<section class='status status-error error'>"
            "<p class='status-label'>Offers data temporarily unavailable.</p>"
            f"<p>{escape(str(exc))}</p>"
            "</section></div></body></html>\n"
        )
        try:
            write_external_css(EXTERNAL_REPO_ROOT)
            write_shell_html(EXTERNAL_REPO_ROOT)
        except Exception:
            pass
        OUTPUT_FILE.write_text(fallback, encoding="utf-8")
        return 1

    log_events: list = []
    if LOG_FILE.exists():
        try:
            log_events = json.loads(LOG_FILE.read_text(encoding="utf-8")).get("events", [])
        except (json.JSONDecodeError, OSError):
            pass

    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(items, log_events), encoding="utf-8")
    print(f"[offers_viewer] Wrote {OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
