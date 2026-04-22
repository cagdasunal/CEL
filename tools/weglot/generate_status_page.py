#!/usr/bin/env python3
"""
Client-friendly HTML status page — admin/log/index.html.

Reads:
  data/log-state.json      — recent sync events (kind, ts, detail)
  data/weglot-exclusions.json  — roster of synced blog posts

Writes (into external repo):
  <EXTERNAL_REPO_ROOT>/admin/log/index.html
      — served at https://cel.englishcollege.com/admin/log/
  <EXTERNAL_REPO_ROOT>/assets/css/dashboard.css (via write_external_css)

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

from tools.dashboard import (
    AUTH_SCRIPT_TAG,
    EXTERNAL_REPO_ROOT,
    SHARED_CSS,
    render_favicon_tag,
    write_external_css,
    write_shell_html,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_STATE_FILE = DATA_DIR / "log-state.json"
EXCLUSIONS_FILE = DATA_DIR / "weglot-exclusions.json"
OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "log" / "index.html"

BG_COLOR = "#F1EAD8"
TEXT_COLOR = "#37332c"

MAX_RECENT_POSTS = 10
MAX_RECENT_EVENTS = 10

LANGUAGE_NAMES = {
    "ar": "Arabic", "de": "German", "en": "English", "es": "Spanish",
    "fr": "French", "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "pt": "Portuguese",
}

PUBLIC_SITEMAP_URL = "https://cel.englishcollege.com/sitemap.xml"
PUBLIC_LLMS_URL = "https://cel.englishcollege.com/llms.txt"


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


def file_mtime_iso(path: Path) -> str | None:
    """Return ISO-8601 timestamp of `path`'s last-modified time in San Diego
    local time, or None if the file doesn't exist.

    Replaces the previous git-log-based lookup — filesystem mtime is simpler,
    works locally and in CI without git context, and reflects when the file
    was actually last regenerated (which is what the page states).
    """
    try:
        if not path.exists():
            return None
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=SAN_DIEGO_TZ)
        return ts.isoformat()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def recent_posts(exclusions: dict, limit: int = MAX_RECENT_POSTS) -> list:
    items = []
    for slug, info in exclusions.items():
        added_at = info.get("added_at") or ""
        code = (info.get("language") or "").lower()
        items.append({
            "slug": slug,
            "language": LANGUAGE_NAMES.get(code, code.upper()),
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

def _css() -> str:
    """Return the shared dashboard CSS.

    Both BG_COLOR (#F9F1DF) and TEXT_COLOR (#37332c) must appear literally in
    the rendered HTML — enforced by test_generate_status_page.py::test_contains_required_colors.
    SHARED_CSS satisfies that invariant.
    """
    return SHARED_CSS


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

    posts = recent_posts(exclusions, MAX_RECENT_POSTS)
    recent_events = events[:MAX_RECENT_EVENTS]
    total_posts = len(exclusions)

    status_class = "status-ok" if is_ok else "status-error"
    status_modifier = "" if is_ok else " error"

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Blog Sync Status — English College</title>")
    parts.append('  <meta name="description" content="Live status of blog post syncing, sitemap, and AI reference file for englishcollege.com">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Status card
    parts.append(f'    <section class="status {status_class}{status_modifier}">')
    parts.append(f'      <p class="status-label">{escape(banner_label)}</p>')
    parts.append(f'      <p>Last checked on <strong>{escape(last_check)}</strong> (San Diego time).</p>')
    parts.append("    </section>")

    # Published files
    parts.append("    <h2>Published files</h2>")
    parts.append('    <ul class="files">')

    def _file_note(filename: str) -> str:
        ts = file_mtime_iso(EXTERNAL_REPO_ROOT / filename)
        if ts:
            return f"Last updated on {escape(iso_to_sd(ts))}"
        return "Not yet updated"

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">sitemap.xml</span>')
    parts.append(f'        <a href="{escape(PUBLIC_SITEMAP_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{_file_note("sitemap.xml")}</p>')
    parts.append("    </li>")

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">llms.txt</span>')
    parts.append(f'        <a href="{escape(PUBLIC_LLMS_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{_file_note("llms.txt")}</p>')
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
    parts.append("  </div>")  # close .dashboard-shell
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_status_page() -> None:
    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(), encoding="utf-8")


def main() -> int:
    write_status_page()
    print(f"[status_page] Wrote {OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
