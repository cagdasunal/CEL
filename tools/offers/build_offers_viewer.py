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
        days_display = f"{DEFAULT_EXTEND_DAYS} (default)"
    else:
        days_display = str(int(raw_days))

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
        f'<td>{escape(days_display)}</td>'
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
        f'    <div class="region-block">'
        f'<h3>{escape(key)}</h3>'
        f'<p class="subtle">action: {escape(val.get("action", "show"))}</p>'
        f'<details><summary>{n} countr{"y" if n == 1 else "ies"}</summary>'
        f'<code class="country-list">{escape(countries_csv)}</code>'
        f'</details>'
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

    # Tab-toggle JS + CSS
    tab_script = """\
  <script>
  (function () {
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
    parts.append("    .region-block{margin-bottom:24px}")
    parts.append("    .date-primary{font-variant-numeric:tabular-nums}")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Page chrome
    parts.append(f'    {render_page_chrome(eyebrow="OFFERS", subtitle=subtitle)}')

    # Status card
    last_sync_display = _iso_to_display(last_ts) if last_ts else "Never"
    parts.append(f'    {render_sync_status_card(status_label, last_sync_display, is_ok=is_ok)}')

    # In-page tab nav
    parts.append('    <nav class="offers-tabs" style="margin-bottom:16px">')
    parts.append('      <a class="offers-tab-link" href="#list">Offers List</a>')
    parts.append('      <a class="offers-tab-link" href="#settings">Settings</a>')
    parts.append("    </nav>")

    # ── Tab: List ──────────────────────────────────────────────────────────
    parts.append('    <section data-tab="list">')
    if items:
        parts.append('      <div class="page-grid">')
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
        parts.append("      </div>")
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
