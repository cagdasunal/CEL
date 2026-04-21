#!/usr/bin/env python3
"""
Client-friendly HTML status page — log.html.

Reads:
  data/log-state.json      — recent sync events (kind, ts, detail)
  data/weglot-exclusions.json  — roster of synced blog posts

Writes:
  log.html  — static HTML page served at https://sitemap.englishcollege.com/log.html

Design constants locked by user:
  BG_COLOR   = #F9F1DF  (cream)
  TEXT_COLOR = #37332c  (dark brown)

No external dependencies. Stdlib only.
"""

import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_STATE_FILE = DATA_DIR / "log-state.json"
EXCLUSIONS_FILE = DATA_DIR / "weglot-exclusions.json"
OUTPUT_FILE = PROJECT_ROOT / "log.html"

BG_COLOR = "#F9F1DF"
TEXT_COLOR = "#37332c"

MAX_RECENT_POSTS = 10
MAX_RECENT_EVENTS = 10

PUBLIC_SITEMAP_URL = "https://sitemap.englishcollege.com/sitemap.xml"
PUBLIC_LLMS_URL = "https://sitemap.englishcollege.com/llms.txt"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _tz_abbr(dt: datetime) -> str:
    offset = dt.utcoffset()
    if offset is not None:
        secs = int(offset.total_seconds())
        if secs == -7 * 3600:
            return "PDT"
        if secs == -8 * 3600:
            return "PST"
    return dt.strftime("%Z")


def fmt_sd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %I:%M %p ") + _tz_abbr(dt)


def now_san_diego() -> datetime:
    return datetime.now(tz=SAN_DIEGO_TZ)


def iso_to_sd(ts_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_iso)
        return fmt_sd(dt.astimezone(SAN_DIEGO_TZ))
    except (ValueError, TypeError):
        return ts_iso or "—"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_events() -> list:
    if LOG_STATE_FILE.exists():
        with open(LOG_STATE_FILE) as f:
            data = json.load(f)
        return data.get("events", [])
    return []


def load_exclusions() -> dict:
    if EXCLUSIONS_FILE.exists():
        with open(EXCLUSIONS_FILE) as f:
            data = json.load(f)
        return data.get("exclusions", {})
    return {}


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def recent_posts(exclusions: dict, limit: int = MAX_RECENT_POSTS) -> list:
    items = []
    for slug, info in exclusions.items():
        added_at = info.get("added_at") or ""
        items.append({
            "slug": slug,
            "language": (info.get("language") or "").upper(),
            "added_at": added_at,
            "source": info.get("source") or "",
        })
    items.sort(key=lambda x: x["added_at"], reverse=True)
    return items[:limit]


def last_weglot_update_ts(events: list):
    for event in events:
        if event.get("kind") == "weglot_update":
            return event.get("ts")
    return None


def status_banner(events: list):
    if not events:
        return ("All blog posts in sync.", True)
    kind = events[0].get("kind", "")
    if kind == "error":
        return ("Attention required — see recent activity.", False)
    if kind == "weglot_update":
        return ("New posts synced successfully.", True)
    return ("All blog posts in sync.", True)


def describe_event(event: dict):
    kind = event.get("kind", "")
    ts_sd = iso_to_sd(event.get("ts", ""))
    detail = event.get("detail") or {}

    if kind == "weglot_update":
        slugs = detail.get("slugs") or []
        n = len(slugs)
        return (ts_sd, f"{n} post{'s' if n != 1 else ''} added to translation exclusions. Sitemap and LLMs reference refreshed.")
    if kind == "no_change":
        return (ts_sd, "Checked for new blog posts — nothing to sync.")
    if kind == "sitemap_refreshed":
        return (ts_sd, "Sitemap refreshed.")
    if kind == "llms_refreshed":
        return (ts_sd, "LLMs reference refreshed.")
    if kind == "error":
        msg = detail.get("message", "unknown error")
        return (ts_sd, f"Error: {msg}")
    return (ts_sd, kind or "unknown event")


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

CSS_TEMPLATE = """
  * { box-sizing: border-box; }
  body {
    background: BG_COLOR_PLACEHOLDER;
    color: TEXT_COLOR_PLACEHOLDER;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    max-width: 780px;
    margin: 0 auto;
    padding: 48px 20px;
    line-height: 1.5;
  }
  h1 { font-size: 28px; margin: 0 0 8px; font-weight: 600; }
  h2 {
    font-size: 18px;
    margin: 40px 0 12px;
    border-bottom: 1px solid rgba(55,51,44,0.15);
    padding-bottom: 6px;
    font-weight: 600;
  }
  p.lede { margin: 0 0 24px; color: rgba(55,51,44,0.8); }
  .status {
    background: rgba(55,51,44,0.04);
    border: 1px solid rgba(55,51,44,0.12);
    border-radius: 8px;
    padding: 20px;
    margin: 24px 0;
  }
  .status.error { background: rgba(192,57,43,0.08); border-color: rgba(192,57,43,0.3); }
  .status-label { font-size: 20px; font-weight: 600; margin: 0 0 6px; }
  .status-ok .status-label { color: #1d6b3a; }
  .status-error .status-label { color: #a02624; }
  .subtle { color: rgba(55,51,44,0.7); font-size: 14px; margin: 6px 0 0; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 14px; }
  th, td {
    text-align: left;
    padding: 10px 10px;
    border-bottom: 1px solid rgba(55,51,44,0.12);
    vertical-align: top;
  }
  th {
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: rgba(55,51,44,0.6);
  }
  td.slug {
    font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 13px;
    word-break: break-word;
  }
  td.lang {
    font-variant: all-small-caps;
    letter-spacing: 0.05em;
    color: rgba(55,51,44,0.8);
    white-space: nowrap;
  }
  td.when { color: rgba(55,51,44,0.7); white-space: nowrap; font-size: 13px; }
  ul.files, ul.activity { list-style: none; padding: 0; margin: 8px 0; }
  ul.files li, ul.activity li {
    padding: 10px 0;
    border-bottom: 1px solid rgba(55,51,44,0.1);
  }
  ul.files li:last-child, ul.activity li:last-child { border-bottom: 0; }
  ul.files .file-row { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
  ul.files .file-name { font-weight: 600; }
  ul.activity .when { color: rgba(55,51,44,0.6); font-size: 13px; margin-right: 10px; }
  .empty { color: rgba(55,51,44,0.6); font-style: italic; padding: 16px 0; }
  a { color: TEXT_COLOR_PLACEHOLDER; text-decoration: underline; }
  a:hover { color: #5f5950; }
  footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid rgba(55,51,44,0.15);
    font-size: 13px;
    color: rgba(55,51,44,0.7);
  }
  @media (max-width: 500px) {
    body { padding: 24px 16px; }
    h1 { font-size: 22px; }
    table { font-size: 13px; }
    td.slug { font-size: 12px; }
  }
"""


def _css() -> str:
    return CSS_TEMPLATE.replace("BG_COLOR_PLACEHOLDER", BG_COLOR).replace(
        "TEXT_COLOR_PLACEHOLDER", TEXT_COLOR
    )


def render_html(events=None, exclusions=None) -> str:
    if events is None:
        events = load_events()
    if exclusions is None:
        exclusions = load_exclusions()

    now = now_san_diego()
    banner_label, is_ok = status_banner(events)

    if events:
        last_check = iso_to_sd(events[0].get("ts", ""))
    else:
        last_check = fmt_sd(now)

    last_artifact = last_weglot_update_ts(events)
    if last_artifact:
        last_artifact_sd = iso_to_sd(last_artifact)
    else:
        last_artifact_sd = None

    posts = recent_posts(exclusions, MAX_RECENT_POSTS)
    recent_events = events[:MAX_RECENT_EVENTS]
    total_posts = len(exclusions)

    status_class = "status-ok" if is_ok else "status-error"
    status_modifier = "" if is_ok else " error"

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Blog Sync Status — English College</title>")
    parts.append('  <meta name="description" content="Live status of blog post syncing, sitemap, and AI reference file for englishcollege.com">')
    parts.append('  <meta name="robots" content="noindex">')
    parts.append("  <style>")
    parts.append(_css())
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")

    # Status card
    parts.append(f'  <section class="status {status_class}{status_modifier}">')
    parts.append(f'    <p class="status-label">{escape(banner_label)}</p>')
    parts.append(f'    <p>Last checked on <strong>{escape(last_check)}</strong> (San Diego time).</p>')
    parts.append("  </section>")

    # Published files
    parts.append("  <h2>Published files</h2>")
    parts.append('  <ul class="files">')

    if last_artifact_sd:
        refresh_note = f"Last refreshed on {escape(last_artifact_sd)}"
    else:
        refresh_note = "Refreshed whenever a new post is added"

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">sitemap.xml</span>')
    parts.append(f'        <a href="{escape(PUBLIC_SITEMAP_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{refresh_note}</p>')
    parts.append("    </li>")

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">llms.txt</span>')
    parts.append(f'        <a href="{escape(PUBLIC_LLMS_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{refresh_note}</p>')
    parts.append("    </li>")
    parts.append("  </ul>")

    # Recent posts
    parts.append("  <h2>Recent blog posts synced</h2>")
    if posts:
        parts.append("  <table>")
        parts.append("    <thead>")
        parts.append("      <tr><th>Slug</th><th>Language</th><th>Synced on</th></tr>")
        parts.append("    </thead>")
        parts.append("    <tbody>")
        for p in posts:
            ts_display = iso_to_sd(p["added_at"]) if p["added_at"] else "—"
            parts.append(
                f'      <tr><td class="slug">{escape(p["slug"])}</td>'
                f'<td class="lang">{escape(p["language"] or "—")}</td>'
                f'<td class="when">{escape(ts_display)}</td></tr>'
            )
        parts.append("    </tbody>")
        parts.append("  </table>")
    else:
        parts.append('  <p class="empty">No posts synced yet.</p>')

    # Recent activity
    parts.append("  <h2>Recent activity</h2>")
    if recent_events:
        parts.append('  <ul class="activity">')
        for event in recent_events:
            ts_sd, description = describe_event(event)
            parts.append(
                f"    <li><span class=\"when\">{escape(ts_sd)}</span>"
                f"<span>{escape(description)}</span></li>"
            )
        parts.append("  </ul>")
    else:
        parts.append('  <p class="empty">No activity recorded yet.</p>')

    # Footer
    parts.append("  <footer>")
    parts.append(
        f'    Total blog posts being tracked: <strong>{total_posts}</strong>. '
        f'This page was generated on {escape(fmt_sd(now))}. '
        f'Next check within 15 minutes.'
    )
    parts.append("  </footer>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_status_page() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(), encoding="utf-8")


def main() -> int:
    write_status_page()
    print(f"[status_page] Wrote {OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
