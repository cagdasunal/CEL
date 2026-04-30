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
import os
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
from tools.offers._log import read_events
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

# Campus collection ID → display name (sites/cel/docs/offers/cms.md)
CAMPUS_NAMES: dict[str, str] = {
    "69284a1fdd88ce50865499ee": "San Diego",
    "69284a3658a8a030e4124ff6": "Vancouver",
    "69284a28e38a8c5f736359cb": "Los Angeles",
}

def _load_country_names() -> dict[str, str]:
    """Load ISO 3166-1 alpha-2 → English name mapping from the JSON file."""
    f = Path(__file__).parent / "iso-3166-1.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

COUNTRY_NAMES: dict[str, str] = _load_country_names()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_to_display(ts_iso: str | None) -> str:
    """Format an ISO timestamp as a friendly date (e.g. 'Apr 30, 2026')."""
    if not ts_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return dt.strftime("%b %-d, %Y")
    except (ValueError, TypeError):
        return ts_iso or "—"


def _format_countries(csv: str | None) -> str:
    """Convert 'AZ,BY,GE' → 'Azerbaijan, Belarus, Georgia'. Unknown codes pass through."""
    if not csv:
        return "—"
    codes = [c.strip().upper() for c in csv.split(",") if c.strip()]
    return ", ".join(COUNTRY_NAMES.get(code, code) for code in codes)


def _format_campus(value: str | dict | None) -> str:
    """Resolve a campus reference (ID string or dict) to a display name."""
    if not value:
        return "—"
    cid = value if isinstance(value, str) else (value.get("id") or "")
    return CAMPUS_NAMES.get(cid, cid or "—")


def _format_bool(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value)


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
    """Return the most recent event timestamp from the auto-extend log.

    Reader is backward-compatible (handles both JSONL and legacy JSON-object
    formats). Tracker 077 M1.
    """
    events = read_events(LOG_FILE)
    if events:
        return events[-1].get("ts")
    return None


def _load_current_regions() -> dict[str, dict[str, str]]:
    """Return the current region→{countries,action} map.

    Priority: data/cel-offers-regions.json (live, written by edit_regions.py)
    > REGIONS (FALLBACK_CONFIG mirror in regions.py).
    """
    json_file = PROJECT_ROOT / "data" / "cel-offers-regions.json"
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            regions = data.get("regions") if isinstance(data, dict) else None
            if isinstance(regions, dict) and regions:
                return regions
        except (json.JSONDecodeError, OSError):
            pass
    return dict(REGIONS)


def _render_item_row(item: dict, now: datetime) -> str:
    fd = item.get("fieldData") or {}
    item_id = item.get("id", "")
    title = escape(fd.get("internal-title") or fd.get("name") or item_id)
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
        f'<div class="extend-edit" data-item-id="{escape(item_id)}">'
        f'<input type="number" min="0" max="365" step="1" '
        f'class="extend-input" value="{days_value}" '
        f'data-original="{days_value}" '
        f'aria-label="Auto-extend days">'
        f'<button class="extend-save" type="button" disabled>Save</button>'
        f'<span class="extend-status" role="status"></span>'
        f'{default_marker}'
        f'</div>'
    )

    # Detail panel: only fields NOT already in the data row.
    detail_rows: list[str] = []

    def _row(label: str, value: str) -> None:
        detail_rows.append(
            f'        <dt>{escape(label)}</dt><dd>{escape(value)}</dd>'
        )

    if (v := fd.get("internal-title")) is not None:
        _row("Internal Title", str(v))
    if (v := fd.get("targeted-countriess")) is not None:
        _row("Targeted Countries", _format_countries(str(v)))
    if (v := fd.get("campus-3")) is not None:
        _row("Campus", _format_campus(v))
    if (v := fd.get("most-popular-this-month")) is not None:
        _row("Most Popular This Month", _format_bool(v))
    if item.get("lastPublished"):
        _row("Last Published", _iso_to_display(str(item["lastPublished"])))

    details_html = "\n".join(detail_rows)
    safe_id = escape(item_id)

    return (
        f'      <tbody class="item-tbody" data-item-id="{safe_id}">'
        f'<tr class="item-row">'
        f'<td>{title}</td>'
        f'<td><span class="date-primary">{end_display}</span>'
        f' <span class="subtle">({rel})</span></td>'
        f'<td>{days_cell}</td>'
        f'<td><button type="button" class="view-toggle" '
        f'aria-expanded="false" aria-controls="detail-{safe_id}">View</button></td>'
        f'</tr>'
        f'<tr class="item-detail-row" id="detail-{safe_id}" hidden>'
        f'<td colspan="4"><dl class="item-details">\n{details_html}\n        </dl></td>'
        f'</tr>'
        f'</tbody>'
    )


def _render_region_block(key: str, val: dict) -> str:
    countries_csv = val.get("countries", "")
    iso_list = [c.strip().upper() for c in countries_csv.split(",") if c.strip()]
    n = len(iso_list)

    chips = []
    for code in iso_list:
        name = COUNTRY_NAMES.get(code, code)
        chips.append(
            f'<span class="country-chip" data-iso="{escape(code)}">'
            f'<span class="chip-flag">{escape(code)}</span>'
            f'<span class="chip-name">{escape(name)}</span>'
            f'<button type="button" class="chip-remove" '
            f'aria-label="Remove {escape(name)}">×</button>'
            f'</span>'
        )
    chips_html = "".join(chips)

    return (
        f'    <div class="region-block" data-region="{escape(key)}" '
        f'data-original="{escape(",".join(iso_list))}">'
        f'<h3>{escape(key)} '
        f'<span class="subtle region-count" data-count>'
        f'({n} countr{"y" if n == 1 else "ies"})</span>'
        f'</h3>'
        f'<p class="subtle">action: {escape(val.get("action", "show"))}</p>'
        f'<div class="country-chips" role="list" '
        f'aria-label="{escape(key)} countries">{chips_html}</div>'
        f'<div class="country-add">'
        f'<input type="text" class="country-input" '
        f'list="country-options" '
        f'placeholder="Type a country name to add…" '
        f'autocomplete="off" '
        f'aria-label="Add country to {escape(key)}">'
        f'<button type="button" class="country-add-btn">Add</button>'
        f'</div>'
        f'<div class="region-actions">'
        f'<button class="region-save" type="button" disabled>Save changes</button>'
        f'<button class="region-revert" type="button" disabled>Revert</button>'
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
    var ITEM_WORKFLOW    = 'offers-edit-item.yml';
    var REGIONS_WORKFLOW = 'offers-edit-regions.yml';
    var COUNTRY_NAME_MAP = __COUNTRY_NAME_MAP_JSON__;
    var DISPATCH_URL     = __DISPATCH_PROXY_URL__;

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

    // ── Dispatch proxy helpers ────────────────────────────────────────
    // The Cloudflare Worker holds the GitHub PAT; the browser never has one.
    function callProxy(payload) {
      if (!DISPATCH_URL) {
        return Promise.reject(new Error('Editor not configured — contact the site administrator.'));
      }
      return fetch(DISPATCH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(resp) {
        return resp.json().catch(function() { return {}; }).then(function(j) {
          return { status: resp.status, ok: resp.ok && j.ok !== false, body: j };
        });
      });
    }

    function dispatchWorkflow(workflow, inputs) {
      return callProxy({ action: 'dispatch', workflow: workflow, inputs: inputs })
        .then(function(r) {
          if (r.ok) return { ok: true };
          var msg = 'HTTP ' + r.status;
          if (r.body && r.body.error) msg += ': ' + r.body.error;
          else if (r.body && r.body.body) msg += ': ' + String(r.body.body).slice(0, 120);
          throw new Error(msg);
        });
    }

    function pollLatestRun(workflow) {
      return callProxy({ action: 'poll', workflow: workflow })
        .then(function(r) {
          if (!r.ok) return null;
          return r.body && r.body.run ? r.body.run : null;
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

    // ── View toggle (per-row details) ─────────────────────────────────
    document.addEventListener('click', function(ev) {
      var btn = ev.target.closest && ev.target.closest('.view-toggle');
      if (!btn) return;
      var tbody = btn.closest('.item-tbody');
      if (!tbody) return;
      var detailRow = tbody.querySelector('.item-detail-row');
      if (!detailRow) return;
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      if (open) detailRow.setAttribute('hidden', '');
      else detailRow.removeAttribute('hidden');
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

    // ── Regions Settings: chip editor ─────────────────────────────────
    function getRegionState(block) {
      var chips = block.querySelectorAll('.country-chip');
      var out = [];
      for (var i = 0; i < chips.length; i++) {
        out.push(chips[i].getAttribute('data-iso'));
      }
      return out;
    }

    function syncRegionUI(block) {
      var current = getRegionState(block).join(',');
      var original = block.getAttribute('data-original') || '';
      var saveBtn = block.querySelector('.region-save');
      var revertBtn = block.querySelector('.region-revert');
      var status = block.querySelector('.region-status');
      var dirty = current !== original;
      var empty = getRegionState(block).length === 0;
      if (revertBtn) revertBtn.disabled = !dirty;
      if (saveBtn) saveBtn.disabled = !dirty || empty;
      if (status) {
        if (empty) {
          status.textContent = 'Region cannot be empty — add at least one country or click Revert';
          status.className = 'region-status is-error';
        } else if (dirty) {
          status.textContent = 'Unsaved changes';
          status.className = 'region-status';
        } else {
          if (!status.classList.contains('is-ok')) {
            status.textContent = '';
            status.className = 'region-status';
          }
        }
      }
      var counter = block.querySelector('[data-count]');
      if (counter) {
        var n = getRegionState(block).length;
        counter.textContent = '(' + n + ' countr' + (n === 1 ? 'y' : 'ies') + ')';
      }
    }

    function resolveCountryInput(text) {
      if (!text) return null;
      var t = text.trim();
      if (!t) return null;
      var asIso = t.toUpperCase();
      if (/^[A-Z]{2}$/.test(asIso) && COUNTRY_NAME_MAP[asIso]) return asIso;
      var m = t.match(/^(.+?)\\s*\\(([A-Z]{2})\\)\\s*$/i);
      if (m && COUNTRY_NAME_MAP[m[2].toUpperCase()]) return m[2].toUpperCase();
      var lc = t.toLowerCase();
      for (var code in COUNTRY_NAME_MAP) {
        if (COUNTRY_NAME_MAP[code].toLowerCase() === lc) return code;
      }
      return null;
    }

    document.addEventListener('click', function(ev) {
      var btn = ev.target.closest && ev.target.closest('.chip-remove');
      if (!btn) return;
      var chip = btn.closest('.country-chip');
      var block = btn.closest('.region-block');
      if (!chip || !block) return;
      chip.parentNode.removeChild(chip);
      syncRegionUI(block);
    });

    function tryAddCountry(block) {
      var input = block.querySelector('.country-input');
      var status = block.querySelector('.region-status');
      if (!input) return;
      var code = resolveCountryInput(input.value);
      if (!code) {
        status.textContent = 'Unknown country — pick from the autocomplete list';
        status.className = 'region-status is-error';
        return;
      }
      if (block.querySelector('.country-chip[data-iso="' + code + '"]')) {
        status.textContent = COUNTRY_NAME_MAP[code] + ' is already in this region';
        status.className = 'region-status is-error';
        input.value = '';
        return;
      }
      var name = COUNTRY_NAME_MAP[code] || code;
      var chips = block.querySelector('.country-chips');
      var span = document.createElement('span');
      span.className = 'country-chip';
      span.setAttribute('data-iso', code);
      span.innerHTML =
        '<span class="chip-flag">' + code + '</span>' +
        '<span class="chip-name">' + name + '</span>' +
        '<button type="button" class="chip-remove" aria-label="Remove ' + name + '">×</button>';
      chips.appendChild(span);
      input.value = '';
      input.focus();
      syncRegionUI(block);
    }

    document.addEventListener('click', function(ev) {
      var btn = ev.target;
      if (!btn.classList || !btn.classList.contains('country-add-btn')) return;
      var block = btn.closest('.region-block');
      if (block) tryAddCountry(block);
    });

    document.addEventListener('keydown', function(ev) {
      if (ev.key !== 'Enter') return;
      var input = ev.target;
      if (!input.classList || !input.classList.contains('country-input')) return;
      ev.preventDefault();
      var block = input.closest('.region-block');
      if (block) tryAddCountry(block);
    });

    document.addEventListener('click', function(ev) {
      var btn = ev.target;
      if (!btn.classList || !btn.classList.contains('region-revert')) return;
      var block = btn.closest('.region-block');
      if (!block) return;
      var original = (block.getAttribute('data-original') || '').split(',').filter(Boolean);
      var chips = block.querySelector('.country-chips');
      chips.innerHTML = '';
      for (var i = 0; i < original.length; i++) {
        var code = original[i];
        var name = COUNTRY_NAME_MAP[code] || code;
        var span = document.createElement('span');
        span.className = 'country-chip';
        span.setAttribute('data-iso', code);
        span.innerHTML =
          '<span class="chip-flag">' + code + '</span>' +
          '<span class="chip-name">' + name + '</span>' +
          '<button type="button" class="chip-remove" aria-label="Remove ' + name + '">×</button>';
        chips.appendChild(span);
      }
      syncRegionUI(block);
    });

    document.addEventListener('click', function(ev) {
      var btn = ev.target;
      if (!btn.classList || !btn.classList.contains('region-save')) return;
      var block = btn.closest('.region-block');
      if (!block) return;
      var status = block.querySelector('.region-status');
      var revertBtn = block.querySelector('.region-revert');
      var region = block.getAttribute('data-region');
      var v = getRegionState(block).join(',');
      if (v === '') { return; }
      if (!/^[A-Z]{2}(,[A-Z]{2})*$/.test(v) && v !== '') {
        status.textContent = 'invalid';
        status.className = 'region-status is-error';
        return;
      }
      btn.disabled = true;
      if (revertBtn) revertBtn.disabled = true;
      status.textContent = 'dispatching…';
      status.className = 'region-status';
      dispatchWorkflow(REGIONS_WORKFLOW, { region: region, countries: v })
        .then(function() { return new Promise(function(r) { setTimeout(r, 2000); }); })
        .then(function() { return awaitRun(REGIONS_WORKFLOW, status); })
        .then(function(run) {
          if (run && run.conclusion === 'success') {
            block.setAttribute('data-original', v);
          }
        })
        .catch(function(err) {
          status.textContent = '✗ ' + err.message;
          status.className = 'region-status is-error';
        })
        .finally(function() { syncRegionUI(block); });
    });

    document.querySelectorAll('.region-block').forEach(function(b) { syncRegionUI(b); });

  })();
  </script>"""
    tab_script = tab_script.replace(
        "__COUNTRY_NAME_MAP_JSON__",
        json.dumps(COUNTRY_NAMES, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029"),
    )
    # Cloudflare Worker URL (PAT-holding proxy). Read at build time from env.
    # Empty when unset \u2192 Save buttons fail with a clear "not configured" message.
    dispatch_proxy_url = os.environ.get("OFFERS_DISPATCH_PROXY_URL", "").strip()
    tab_script = tab_script.replace("__DISPATCH_PROXY_URL__", json.dumps(dispatch_proxy_url))
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
    parts.append("    .item-row td{vertical-align:middle}")
    parts.append("    .item-detail-row td{padding:12px 16px;background:#F6EEDA;border-top:none}")
    parts.append("    .item-details{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;margin:0}")
    parts.append("    .item-details dt{font-weight:600;white-space:nowrap}")
    parts.append("    .view-toggle{padding:4px 12px;border:1px solid #6b5f52;border-radius:4px;background:#f0e8d4;color:#3a342b;cursor:pointer;font-weight:500}")
    parts.append("    .view-toggle:hover{background:#e7daa8}")
    parts.append("    .view-toggle[aria-expanded='true']::after{content:' ▾'}")
    parts.append("    .view-toggle[aria-expanded='false']::after{content:' ▸'}")
    parts.append("    .region-block{margin-bottom:32px;padding:16px;border:1px solid #d9cfb9;border-radius:8px;background:#F6EEDA}")
    parts.append("    .region-block h3{margin:0 0 8px 0;text-transform:uppercase;letter-spacing:0.04em}")
    parts.append("    .region-actions{margin-top:8px;display:flex;align-items:center;gap:12px}")
    parts.append("    .region-save,.extend-save{padding:6px 14px;border:1px solid #6b5f52;border-radius:4px;background:#f0e8d4;color:#3a342b;cursor:pointer;font-weight:600}")
    parts.append("    .region-save:disabled,.extend-save:disabled{opacity:0.4;cursor:not-allowed}")
    parts.append("    .region-save:hover:not(:disabled),.extend-save:hover:not(:disabled){background:#e7daa8}")
    parts.append("    .region-revert{padding:6px 14px;border:1px solid #b8a98c;border-radius:4px;background:#fff;color:#6b5f52;cursor:pointer}")
    parts.append("    .region-revert:disabled{opacity:0.4;cursor:not-allowed}")
    parts.append("    .region-status,.extend-status{font-size:0.85em;color:#6b5f52}")
    parts.append("    .region-status.is-ok,.extend-status.is-ok{color:#3a7a3a}")
    parts.append("    .region-status.is-error,.extend-status.is-error{color:#a54040}")
    parts.append("    .extend-edit{display:flex;align-items:center;gap:8px;flex-wrap:wrap}")
    parts.append("    .extend-input{width:80px;padding:6px;font-family:inherit;font-size:0.95em;border:1px solid #b8a98c;border-radius:4px;background:#fff}")
    parts.append("    .date-primary{font-variant-numeric:tabular-nums}")

    parts.append("    .country-chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;min-height:32px}")
    parts.append("    .country-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 4px 4px 10px;background:#fff;border:1px solid #b8a98c;border-radius:16px;font-size:0.9em}")
    parts.append("    .chip-flag{font-family:ui-monospace,monospace;font-size:0.78em;color:#6b5f52;font-weight:600}")
    parts.append("    .chip-remove{width:20px;height:20px;border:none;border-radius:50%;background:#e7daa8;color:#3a342b;cursor:pointer;font-size:0.9em;line-height:1;padding:0;display:inline-flex;align-items:center;justify-content:center}")
    parts.append("    .chip-remove:hover{background:#a54040;color:#fff}")
    parts.append("    .country-add{display:flex;gap:8px;align-items:center;margin:8px 0}")
    parts.append("    .country-input{padding:6px 10px;font-family:inherit;font-size:0.95em;border:1px solid #b8a98c;border-radius:4px;background:#fff;min-width:280px}")
    parts.append("    .country-add-btn{padding:6px 14px;border:1px solid #6b5f52;border-radius:4px;background:#fff;color:#3a342b;cursor:pointer;font-weight:500}")
    parts.append("    .country-add-btn:hover{background:#f0e8d4}")
    parts.append("    .offers-tabs{margin-bottom:16px}")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    datalist_options = "\n".join(
        f'    <option value="{escape(name)}" data-iso="{escape(code)}">'
        f'{escape(name)} ({escape(code)})</option>'
        for code, name in sorted(COUNTRY_NAMES.items(), key=lambda x: x[1])
    )
    parts.append('  <datalist id="country-options">')
    parts.append(datalist_options)
    parts.append('  </datalist>')
    parts.append('  <div class="dashboard-shell">')

    # Page chrome
    parts.append(f'    {render_page_chrome(eyebrow="OFFERS", subtitle=subtitle)}')

    # Status card
    last_sync_display = _iso_to_display(last_ts) if last_ts else "Never"
    parts.append(f'    {render_sync_status_card(status_label, last_sync_display, is_ok=is_ok)}')

    # In-page tab nav
    parts.append('    <nav class="offers-tabs">')
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
        for item in items:
            parts.append(_render_item_row(item, now))
        parts.append("      </table>")
    else:
        parts.append('      <p class="empty">No offers yet.</p>')
    parts.append("    </section>")

    # ── Tab: Settings ──────────────────────────────────────────────────────
    parts.append('    <section data-tab="settings">')
    parts.append(
        '      <p>Geotargetly region → country mappings. '
        'Click <strong>×</strong> on any chip to remove a country. '
        'Use the dropdown to add countries. '
        'Save changes to dispatch a workflow that updates '
        '<code>cel-offers-regions.json</code> (consumed by '
        '<code>cel-offers.js</code>).</p>'
    )
    current_regions = _load_current_regions()
    for key, val in current_regions.items():
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

    log_events: list = read_events(LOG_FILE)

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

    log_events: list = read_events(LOG_FILE)

    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(items, log_events), encoding="utf-8")
    print(f"[offers_viewer] Wrote {OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
