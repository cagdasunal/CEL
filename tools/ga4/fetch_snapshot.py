#!/usr/bin/env python3
"""
Fetch a curated, CLIENT-READY GA4 snapshot -> <CEL repo>/docs/admin/analytics/data.json.

The dashboard's Analytics tab renders this JSON (see tools/weglot/generate_status_page.py
render_analytics_html). All curation — friendly labels, locale badges, trend arrow,
zero-row suppression, one plain-English insight — happens HERE (server-side) so the client
never sees jargon, "(not set)", or a bare "0".

Scope: STANDARD GA4 dimensions only. (All 20 custom dimensions still return "(not set)";
several custom events return 0 over 28 days — both deliberately excluded from the client view.)

Credentials (read-only, analytics.readonly):
  - CI / explicit:  env GA4_OAUTH_CREDENTIALS = a JSON blob (authorized_user OR service_account).
  - Local default:  Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS / well-known ADC),
                    the same file the read-only google-analytics MCP uses.
Never logs the credential. Google libs are lazy-imported (rules/quality.md §12).

Runs both locally (off ADC) and in CI (off the secret) with the same code.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.dashboard import EXTERNAL_REPO_ROOT  # CEL docs root (same resolver generate_status_page uses)

SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_JSON = PROJECT_ROOT / "sites" / "cel" / "site.json"
OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "analytics" / "data.json"

GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

# GA4 channel name -> plain-English label a non-technical owner understands.
CHANNEL_LABELS = {
    "Direct": "Came to you directly",
    "Organic Search": "Found you on a search engine",
    "Organic Social": "Came from social media",
    "Paid Search": "Came from a paid ad",
    "Paid Social": "Came from a paid social ad",
    "Referral": "Followed a link from another site",
    "Organic Video": "Came from a video",
    "Email": "Came from an email",
    "Display": "Came from a display ad",
}
# URL locale prefix -> language name (for the "market" badge on localized pages).
LOCALE_NAMES = {
    "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ko": "Korean", "ja": "Japanese", "ar": "Arabic",
}


# --------------------------------------------------------------------------
# Pure curation helpers (unit-tested in test_fetch_snapshot.py; no network)
# --------------------------------------------------------------------------
def resolve_property_id() -> str:
    """Property id from env override, else site.json, else the known CEL property."""
    pid = os.environ.get("GA4_PROPERTY_ID")
    if pid:
        return pid.strip()
    try:
        return str(json.loads(SITE_JSON.read_text(encoding="utf-8")).get("ga4_property_id") or "459514528")
    except (OSError, json.JSONDecodeError, ValueError):
        return "459514528"


def visitors_phrase(n: int) -> str:
    """Warm, rounded headline. Rounds DOWN to a clean figure so it never overstates."""
    if n >= 1000:
        rounded = (n // 500) * 500
        return f"Over {rounded:,} people visited your website in the last 28 days"
    return f"{n:,} people visited your website in the last 28 days"


def momentum(curr: int, prev: int) -> dict:
    """Last-14 vs prior-14 trend, as a direction + plain phrase (never a bare percent)."""
    if not prev:
        return {"direction": "flat", "pct": 0, "phrase": ""}
    pct = round((curr - prev) / prev * 100)
    if pct >= 2:
        return {"direction": "up", "pct": pct, "phrase": f"up about {pct}% vs the two weeks before"}
    if pct <= -2:
        return {"direction": "down", "pct": abs(pct), "phrase": f"down about {abs(pct)}% vs the two weeks before"}
    return {"direction": "flat", "pct": 0, "phrase": "holding steady vs the two weeks before"}


def friendly_page_title(path: str) -> dict:
    """Raw slug path -> {title, badge (language for localized paths), path}."""
    parts = [p for p in (path or "").split("/") if p]
    badge = None
    if parts and parts[0] in LOCALE_NAMES:
        badge = LOCALE_NAMES[parts[0]]
        parts = parts[1:]
    if not parts:
        title = "Home page"
    else:
        title = parts[-1].replace("-", " ").replace("_", " ").strip().title() or "Home page"
    return {"title": title, "badge": badge, "path": path}


def channel_label(name: str) -> str:
    return CHANNEL_LABELS.get(name, name)


def curate_channels(rows: list) -> list:
    """rows: [(name, users)] -> top-3 friendly channels with %, zero/(not set) dropped."""
    rows = [(n, u) for n, u in rows if u > 0 and n and n != "(not set)"]
    total = sum(u for _, u in rows) or 1
    rows.sort(key=lambda x: -x[1])
    return [{"raw": n, "label": channel_label(n), "users": u, "pct": round(u / total * 100)}
            for n, u in rows[:3]]


def curate_pages(rows: list, limit: int = 5) -> list:
    """rows: [(path, views)] (pre-sorted desc) -> top friendly pages, empties dropped."""
    out = []
    for path, views in rows:
        if views <= 0 or not path:
            continue
        out.append({**friendly_page_title(path), "views": views})
        if len(out) >= limit:
            break
    return out


def curate_countries(rows: list, limit: int = 5) -> list:
    """rows: [(name, users)] -> top countries by name with %, zero/(not set) dropped."""
    rows = [(n, u) for n, u in rows if u > 0 and n and n != "(not set)"]
    total = sum(u for _, u in rows) or 1
    rows.sort(key=lambda x: -x[1])
    return [{"name": n, "users": u, "pct": round(u / total * 100)} for n, u in rows[:limit]]


def build_insight(channels: list) -> str:
    """One plain-English takeaway, picked from the curated channels."""
    if not channels:
        return ""
    top = channels[0]["raw"]
    if top == "Organic Search":
        return "Search engines are your strongest source of new visitors — a good sign your SEO is working."
    if top == "Direct":
        return "Most visitors come straight to you — a sign your brand is well recognised."
    if top in ("Organic Social", "Paid Social"):
        return "Social media is your biggest source of visitors right now."
    return f"Your biggest source of visitors right now: {channels[0]['label'].lower()}."


def assemble(total_28d: int, last14: int, prior14: int,
             channel_rows: list, page_rows: list, country_rows: list,
             generated_at: str) -> dict:
    """Pure assembly of the client-ready snapshot from raw (name/value) row tuples."""
    channels = curate_channels(channel_rows)
    return {
        "generated_at": generated_at,
        "visitors_28d": total_28d,
        "visitors_phrase": visitors_phrase(total_28d),
        "momentum": momentum(last14, prior14),
        "insight": build_insight(channels),
        "channels": channels,
        "top_pages": curate_pages(page_rows),
        "countries": curate_countries(country_rows),
    }


# --------------------------------------------------------------------------
# GA4 Data API access (lazy imports; reads env blob or ADC)
# --------------------------------------------------------------------------
def _credentials():
    blob = os.environ.get("GA4_OAUTH_CREDENTIALS")
    if blob:
        info = json.loads(blob)
        if info.get("type") == "service_account":
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_info(info, scopes=[GA4_READONLY_SCOPE])
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_info(info, scopes=[GA4_READONLY_SCOPE])
    import google.auth
    creds, _ = google.auth.default(scopes=[GA4_READONLY_SCOPE])
    return creds


def _client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    return BetaAnalyticsDataClient(credentials=_credentials())


def _run(client, pid, start, end, dim=None, metric="totalUsers", limit=10000, order_desc=True):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Metric, Dimension, OrderBy,
    )
    kwargs = dict(
        property=f"properties/{pid}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        metrics=[Metric(name=metric)],
        limit=limit,
    )
    if dim:
        kwargs["dimensions"] = [Dimension(name=dim)]
        if order_desc:
            kwargs["order_bys"] = [OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metric), desc=True)]
    return client.run_report(RunReportRequest(**kwargs))


def _total(resp) -> int:
    return int(resp.rows[0].metric_values[0].value) if resp.rows else 0


def _pairs(resp) -> list:
    return [(r.dimension_values[0].value, int(r.metric_values[0].value)) for r in resp.rows]


def fetch(pid: str | None = None) -> dict:
    pid = pid or resolve_property_id()
    c = _client()
    total_28d = _total(_run(c, pid, "28daysAgo", "yesterday"))
    last14 = _total(_run(c, pid, "14daysAgo", "yesterday"))
    prior14 = _total(_run(c, pid, "28daysAgo", "15daysAgo"))
    channels = _pairs(_run(c, pid, "28daysAgo", "yesterday", dim="sessionDefaultChannelGroup", limit=15))
    pages = _pairs(_run(c, pid, "28daysAgo", "yesterday", dim="pagePath", metric="screenPageViews", limit=20))
    countries = _pairs(_run(c, pid, "28daysAgo", "yesterday", dim="country", limit=15))
    generated_at = datetime.now(tz=SAN_DIEGO_TZ).strftime("%Y-%m-%d %I:%M %p ") + (
        datetime.now(tz=SAN_DIEGO_TZ).strftime("%Z"))
    return assemble(total_28d, last14, prior14, channels, pages, countries, generated_at)


def main(argv=None) -> int:
    snap = fetch()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ga4] wrote {OUTPUT_FILE} (visitors_28d={snap['visitors_28d']}, "
          f"channels={len(snap['channels'])}, pages={len(snap['top_pages'])}, "
          f"countries={len(snap['countries'])})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
