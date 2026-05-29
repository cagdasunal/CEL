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
    write_dashboard_config,
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

# Weglot translation CSVs — published to CEL repo and served by GitHub Pages
PUBLIC_WEGLOT_CSV_URL_TEMPLATE = "https://cel.englishcollege.com/admin/weglot-imports/{lang}.csv"
PUBLIC_WEGLOT_MANIFEST_URL = "https://cel.englishcollege.com/admin/weglot-imports/manifest.json"
WEGLOT_CSV_LANGUAGES = ("de", "fr", "es", "it", "ja", "ko", "pt", "ar")
WEGLOT_CSV_DIR = EXTERNAL_REPO_ROOT / "admin" / "weglot-imports"
WEGLOT_IMPORT_STATUS_FILE = WEGLOT_CSV_DIR / "import-status.json"
PUBLIC_WEGLOT_ZIP_URL = "https://cel.englishcollege.com/admin/weglot-imports/weglot-imports.zip"
PUBLIC_WEGLOT_MATRIX_URL = "https://cel.englishcollege.com/admin/weglot-imports/all-languages.csv"
WEGLOT_ZIP_FILE = WEGLOT_CSV_DIR / "weglot-imports.zip"
WEGLOT_MATRIX_FILE = WEGLOT_CSV_DIR / "all-languages.csv"
# Written by the summary tool's translate phase (tools/summary, CEL-only) next to
# the CSVs; surfaces per-locale + per-item translation coverage on /admin/#summaries.
WEGLOT_TRANSLATION_STATUS_FILE = WEGLOT_CSV_DIR / "translation-status.json"
TRANSLATIONS_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "translations" / "index.html"
FILES_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "files" / "index.html"
SUMMARIES_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "summaries" / "index.html"
# Analytics tab — a client-facing, jargon-free showcase of everything we track + a LIVE
# embedded Google Analytics (Looker Studio) report that shows the real numbers in-page.
# The report is owned by the client's own Google account (GA4 property 459514528), shared
# "anyone with the link" + embedding enabled, so it renders for any viewer without a Google
# login (no multi-account / wrong-account problem) and refreshes on its own.
ANALYTICS_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "analytics" / "index.html"
LOOKER_EMBED_URL = (
    "https://datastudio.google.com/embed/reporting/"
    "1a0081b3-6631-46f2-84ed-25b6209200e9/page/kIV1C"
)

# Summary-script artifact locations (tracker-090 — SEO Summaries page)
SUMMARY_DRYRUN_DIR = PROJECT_ROOT / "data" / "seo-intel" / "summary-dryrun"
STATIC_SUMMARIES_DIR = WEGLOT_CSV_DIR / "static-summaries"


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


def _mtime_note(path: Path) -> str:
    """Render the "Last updated on ..." / "Not yet updated" subtle paragraph for a file.

    Shared by the log page's now-removed Published-files section (tracker-090 B1)
    and the new Files page. Module-level so both renderers can call it.
    """
    ts = file_mtime_iso(path)
    if ts:
        return f"Last updated on {escape(iso_to_sd(ts))}"
    return "Not yet updated"


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


def load_import_status() -> dict:
    """Read import-status.json if present.

    Returns: {language_code: status_dict, ...} (the inner "languages" dict),
    or {} when the file is missing or unparseable. Never raises — the badge
    is non-essential UI; missing status must not break dashboard regen.
    """
    if not WEGLOT_IMPORT_STATUS_FILE.exists():
        return {}
    try:
        data = json.loads(WEGLOT_IMPORT_STATUS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    langs = data.get("languages")
    if not isinstance(langs, dict):
        return {}
    return langs


def render_import_badge(status: dict | None) -> str:
    """Render an inline HTML badge for one language's import status.

    Returns an empty string (no badge) when status is None or verdict is
    "no_csv". All other verdicts render a <span class="badge-..."> with a
    prefixed glyph. When checked_at is present, an adjacent muted timestamp
    span is appended so users can see how fresh the verdict is.
    """
    if not status:
        return ""
    verdict = status.get("verdict")
    if verdict == "imported":
        badge = '<span class="badge-ok">✓ Imported</span>'
    elif verdict == "partial":
        found = int(status.get("sentinels_found", 0))
        total = int(status.get("sentinels_total", 0))
        badge = f'<span class="badge-partial">⚠ Partial ({found}/{total})</span>'
    elif verdict == "pending":
        badge = '<span class="badge-failed">⚠ Pending import</span>'
    elif verdict == "no_sentinels":
        badge = '<span class="badge-partial">⚠ Cannot verify</span>'
    elif verdict == "check_failed":
        code = status.get("http_status")
        suffix = f" (HTTP {int(code)})" if isinstance(code, int) else ""
        badge = f'<span class="badge-failed">⚠ Check failed{escape(suffix)}</span>'
    elif verdict == "no_csv":
        return ""
    else:
        return ""
    ts_iso = status.get("checked_at")
    if ts_iso:
        ts_pretty = iso_to_sd(ts_iso)
        badge += f' <span class="badge-when">(checked {escape(ts_pretty)})</span>'
    return badge


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

    # (Published files block moved to /admin/files/ in tracker-090 — was here previously.)

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


def render_files_html() -> str:
    """Render /admin/files/ — SEO files (sitemap.xml, llms.txt) + manual-paste summaries.

    Tracker-090 B1: extracted the Published-files block out of /admin/log/ so the
    log page is strictly the Synced Posts surface. This page is the SEO-files
    surface — sitemap, llms.txt, and the static-page Markdown files awaiting
    manual paste into Webflow Designer.
    """
    now = now_san_diego()
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>SEO Files — English College</title>")
    parts.append('  <meta name="description" content="Published SEO files (sitemap, llms.txt) and pending manual-paste summary files.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Intro
    parts.append('    <section class="status status-ok">')
    parts.append('      <p class="status-label">SEO file manifest.</p>')
    parts.append('      <p>Published files that Google + AI crawlers consume, plus any per-page summary Markdown awaiting manual paste into Webflow Designer.</p>')
    parts.append("    </section>")

    # Published files
    parts.append("    <h2>Published files</h2>")
    parts.append('    <ul class="files">')

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">sitemap.xml</span>')
    parts.append(f'        <a href="{escape(PUBLIC_SITEMAP_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{_mtime_note(EXTERNAL_REPO_ROOT / "sitemap.xml")}</p>')
    parts.append("    </li>")

    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">llms.txt</span>')
    parts.append(f'        <a href="{escape(PUBLIC_LLMS_URL)}">View</a>')
    parts.append("      </div>")
    parts.append(f'      <p class="subtle">{_mtime_note(EXTERNAL_REPO_ROOT / "llms.txt")}</p>')
    parts.append("    </li>")

    parts.append("  </ul>")

    # Manual paste files (per-page summary Markdown awaiting paste)
    parts.append("    <h2>Manual paste files</h2>")
    paste_files = []
    if STATIC_SUMMARIES_DIR.exists():
        paste_files = sorted(STATIC_SUMMARIES_DIR.glob("*.summary.md"))
    if paste_files:
        parts.append('    <p class="subtle">Static-page summaries waiting to be pasted into Webflow Designer. Open each file, copy the Markdown, paste into the page\'s Rich Text element below the hero, and publish.</p>')
        parts.append('    <ul class="files">')
        for path in paste_files:
            public_url = f"https://cel.englishcollege.com/admin/weglot-imports/static-summaries/{path.name}"
            parts.append("    <li>")
            parts.append('      <div class="file-row">')
            parts.append(f'        <span class="file-name">{escape(path.name)}</span>')
            parts.append(f'        <a href="{escape(public_url)}" download>Download</a>')
            parts.append("      </div>")
            parts.append(f'      <p class="subtle">{_mtime_note(path)}</p>')
            parts.append("    </li>")
        parts.append("  </ul>")
    else:
        parts.append('    <p class="empty">No manual-paste files yet. They will appear here after a live summary-script run touches static landing pages.</p>')

    # Footer
    parts.append("  <footer>")
    parts.append(
        f'    This page was generated on {escape(fmt_sd(now))}. '
        f'Next check within 15 minutes.'
    )
    parts.append("  </footer>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


def _latest_summary_run_dir() -> Path | None:
    """Find the most recent timestamped subdir under SUMMARY_DRYRUN_DIR that
    contains en-summaries.json.

    Directory names are 'YYYYMMDDTHHMMSSZ' so lexical sort = chronological.
    Skips partial-run dirs (e.g. retrieve-batch dirs that have only
    retrieved-batch.json). Returns None when no qualifying dir exists.
    """
    if not SUMMARY_DRYRUN_DIR.exists():
        return None
    subdirs = sorted(
        (p for p in SUMMARY_DRYRUN_DIR.iterdir() if p.is_dir()),
        reverse=True,
    )
    for d in subdirs:
        if (d / "en-summaries.json").exists():
            return d
    return None


def _format_run_dir_stamp(name: str) -> str:
    """Parse a summary-dryrun dir name ('YYYYMMDDTHHMMSSZ') into a readable UTC
    string for display, or '' if the name isn't a recognized timestamp.

    Lets the summaries page state WHEN its data is from (the source run),
    independent of report.json — which is not committed, so the run-dir name is
    the only always-present date source.
    """
    try:
        dt = datetime.strptime(name, "%Y%m%dT%H%M%SZ")
    except (ValueError, TypeError):
        return ""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _count_words_in_markdown(md: str) -> int:
    """Strip Markdown syntax + count whitespace-separated words. Best-effort."""
    if not md:
        return 0
    import re as _re
    stripped = _re.sub(r"```.*?```", "", md, flags=_re.DOTALL)
    stripped = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = _re.sub(r"[#*`>_~|\[\](){}<>]", " ", stripped)
    return len(_re.findall(r"\b\w+\b", stripped, flags=_re.UNICODE))


def _count_internal_links(md: str) -> int:
    """Count internal links in the summary Markdown (englishcollege.com or root-relative)."""
    if not md:
        return 0
    import re as _re
    return len(_re.findall(r"\]\(\s*(?:https?://(?:www\.)?englishcollege\.com|/)", md))


def _slug_from_url(url: str) -> str:
    """Mirror webflow_designer.py:write_static_summary's slug derivation."""
    import urllib.parse as _urlparse
    parsed = _urlparse.urlparse(url)
    return parsed.path.strip("/").replace("/", "-") or "home"


def _content_type_badge(content_type: str) -> str:
    """Existing .badge-* class per content type (no new colors)."""
    mapping = {
        "landing": "badge-ok",
        "blog_post": "badge-partial",
        "course": "badge-when",
        "housing": "badge-when",
    }
    labels = {
        "landing": "Landing Page",
        "blog_post": "Blog Post",
        "course": "Course",
        "housing": "Housing",
    }
    cls = mapping.get(content_type, "badge-when")
    label = labels.get(content_type) or (content_type or "—").replace("_", " ").title()
    return f'<span class="{cls}">{escape(label)}</span>'


def _audit_action_badge(action: str | None) -> str:
    """Map audit verdict to existing badge class."""
    if not action:
        return '<span class="badge-when">Not audited</span>'
    mapping = {
        "KEEP": "badge-ok",
        "REGENERATE": "badge-partial",
        "MANUAL_REVIEW": "badge-failed",
    }
    cls = mapping.get(action, "badge-when")
    return f'<span class="{cls}">{escape(action)}</span>'


def _load_translation_status() -> dict:
    """Load the translate phase's coverage artifact (per_locale + per_item), or {}.

    Written by `tools/summary` (CEL-only) next to the Weglot CSVs and committed by
    summary.yml's live step. Absent until the first live translate run — callers
    must treat {} as 'no translations yet'."""
    try:
        data = json.loads(WEGLOT_TRANSLATION_STATUS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def render_summaries_html() -> str:
    """Render /admin/summaries/ — SEO summary-script output surface.

    Tracker-090 B2: reads the most recent timestamped subdir under
    `data/seo-intel/summary-dryrun/`. Surfaces aggregate KPIs + per-item rows
    (URL, content type, locale, word count, keyword count, audit verdict,
    manual-paste status). Empty-state when no run dirs exist.

    NO API calls. Read-only against existing on-disk artifacts.
    """
    now = now_san_diego()
    latest = _latest_summary_run_dir()

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>SEO Summaries — English College</title>")
    parts.append('  <meta name="description" content="Per-page SEO summaries generated by the summary script.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    if latest is None:
        parts.append('    <section class="status status-ok">')
        parts.append('      <p class="status-label">No summaries generated yet.</p>')
        parts.append('      <p>This page surfaces per-page SEO summaries once the summary script has been run. Trigger the <strong>Summary script</strong> workflow on GitHub Actions to populate it.</p>')
        parts.append('      <p>What you will see here once a run completes: per-page URL, content type, locale, word count, keyword count, generation date, batch / run metadata, and audit verdict (KEEP / REGENERATE / MANUAL_REVIEW).</p>')
        parts.append("    </section>")
        parts.append("  <footer>")
        parts.append(
            f'    This page was generated on {escape(fmt_sd(now))}. '
            f'Next check within 15 minutes.'
        )
        parts.append("  </footer>")
        parts.append("  </div>")
        parts.append("</body>")
        parts.append("</html>")
        return "\n".join(parts) + "\n"

    # Load artifacts.
    report = {}
    en_summaries: dict[str, dict] = {}
    try:
        report_path = latest / "report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        report = {}
    try:
        man_path = latest / "en-summaries.json"
        if man_path.exists():
            en_summaries = json.loads(man_path.read_text(encoding="utf-8"))
            if not isinstance(en_summaries, dict):
                en_summaries = {}
    except (json.JSONDecodeError, OSError):
        en_summaries = {}
    # Derive aggregate stats.
    total = len(en_summaries)
    total_words = sum(_count_words_in_markdown(e.get("markdown", "")) for e in en_summaries.values())
    avg_words = (total_words // total) if total else 0
    by_locale: dict[str, int] = {}
    total_keywords = 0
    total_links = 0
    for entry in en_summaries.values():
        loc = entry.get("locale", "—")
        by_locale[loc] = by_locale.get(loc, 0) + 1
        kp = entry.get("keyword_plan") or {}
        if kp:
            total_keywords += (1 if kp.get("primary") else 0) + len(kp.get("secondaries") or []) + len(kp.get("entities") or [])
        total_links += _count_internal_links(entry.get("markdown", "") or "")
    started_at = report.get("started_at", "")
    started_human = iso_to_sd(started_at) if started_at else "—"
    is_dry = bool(report.get("dry_run"))
    dry_label = " (dry-run)" if is_dry else ""

    # Translation coverage (per-locale + per-item), written by the translate phase.
    tstatus = _load_translation_status()
    tper_locale = tstatus.get("per_locale") or {}
    tper_item = tstatus.get("per_item") or {}
    tn_targets = len(tstatus.get("target_locales") or [])
    tshow = bool(tstatus)

    # tracker-107: fold translated summaries/words/links into the Overview totals + the
    # By-language breakdown so the dashboard reflects the FULL multilingual volume (the
    # client showcase), not just the EN/native source. `per_locale` carries `words` +
    # `internal_links` recorded by the translate phase. The separate "Translations" row
    # below keeps the source-vs-translated split visible.
    src_total = total
    tr_summaries = tr_words = tr_links = 0
    for _loc, _info in tper_locale.items():
        _n = _info.get("translated", 0) or 0
        tr_summaries += _n
        tr_words += _info.get("words", 0) or 0
        tr_links += _info.get("internal_links", 0) or 0
        by_locale[_loc] = by_locale.get(_loc, 0) + _n
    total += tr_summaries
    total_words += tr_words
    total_links += tr_links
    avg_words = (total_words // total) if total else 0

    # Status banner.
    parts.append('    <section class="status status-ok">')
    if started_human != "—":
        parts.append(f'      <p class="status-label">Last updated {escape(started_human)}{dry_label}.</p>')
    else:
        parts.append(f'      <p class="status-label">{total} page summaries ready{dry_label}.</p>')
    run_stamp = _format_run_dir_stamp(latest.name)
    if run_stamp:
        parts.append(
            f'      <p>Summary data is from the run on <strong>{escape(run_stamp)}</strong>. '
            f'This page refreshes every 15 minutes, but the summaries themselves change only '
            f'when a new Summary-script run is committed.</p>'
        )
    parts.append("    </section>")

    # Aggregate KPIs.
    parts.append("    <h2>Overview</h2>")
    parts.append('    <table class="kv-table">')
    parts.append('      <tbody>')
    _src_note = (
        f' <span class="subtle">({src_total:,} source + {tr_summaries:,} translated)</span>'
        if tr_summaries else ""
    )
    parts.append(f'        <tr><td class="k">Total summaries</td><td class="v"><strong>{total:,}</strong>{_src_note}</td></tr>')
    parts.append(f'        <tr><td class="k">Total words</td><td class="v"><strong>{total_words:,}</strong></td></tr>')
    parts.append(f'        <tr><td class="k">Average words per summary</td><td class="v">{avg_words:,}</td></tr>')
    parts.append(f'        <tr><td class="k">Total keywords</td><td class="v">{total_keywords:,}</td></tr>')
    parts.append(f'        <tr><td class="k">Total internal links</td><td class="v">{total_links:,}</td></tr>')
    if by_locale:
        loc_pairs = ", ".join(
            f"{escape(LANGUAGE_NAMES.get(k, k.upper()))}: {v}"
            for k, v in sorted(by_locale.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        parts.append(f'        <tr><td class="k">By language</td><td class="v">{loc_pairs}</td></tr>')
    if tper_locale:
        tloc_pairs = " · ".join(
            f"{escape(LANGUAGE_NAMES.get(loc, loc.upper()))} {info.get('translated', 0)}"
            for loc, info in sorted(tper_locale.items())
        )
        tasof = iso_to_sd(tstatus.get("generated_at", "")) if tstatus.get("generated_at") else "—"
        parts.append(
            f'        <tr><td class="k">Translations</td><td class="v">{tloc_pairs} '
            f'<span class="subtle">(as of {escape(tasof)}; courses + landing — blog stays native per locale)</span></td></tr>'
        )
    parts.append('      </tbody>')
    parts.append('    </table>')

    # Per-item table.
    parts.append("    <h2>Latest summaries</h2>")
    if en_summaries:
        parts.append("    <table>")
        parts.append("      <thead>")
        _thead = "<th>Page</th><th>Type</th><th>Language</th><th>Words</th><th>Keywords</th><th>Links</th>"
        if tshow:
            _thead += "<th>Translated</th>"
        parts.append(f"        <tr>{_thead}</tr>")
        parts.append("      </thead>")
        parts.append("      <tbody>")
        for cid, entry in en_summaries.items():
            url = entry.get("url", "")
            md = entry.get("markdown", "") or ""
            content_type = entry.get("content_type", "")
            locale = entry.get("locale", "—")
            kw_plan = entry.get("keyword_plan") or {}
            word_count = _count_words_in_markdown(md)
            link_count = _count_internal_links(md)
            if kw_plan:
                kw_count = (1 if kw_plan.get("primary") else 0) + len(kw_plan.get("secondaries") or []) + len(kw_plan.get("entities") or [])
                kw_display = str(kw_count)
            else:
                kw_display = "—"
            if url.startswith("http://") or url.startswith("https://"):
                page_html = f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(url)}</a>'
            else:
                page_html = f'<span class="subtle">{escape(url)}</span>'
            lang_label = LANGUAGE_NAMES.get(locale, locale.upper()) if locale and locale != "—" else "—"
            tr_cell = ""
            if tshow:
                _n = len(tper_item.get(cid, []))
                if not _n:
                    tr_cell = '<td class="subtle">—</td>'
                elif tn_targets:
                    tr_cell = f"<td>{_n}/{tn_targets}</td>"
                else:  # status present but target_locales empty — avoid "N/0"
                    tr_cell = f"<td>{_n}</td>"
            parts.append(
                f"        <tr>"
                f"<td>{page_html}</td>"
                f"<td>{_content_type_badge(content_type)}</td>"
                f"<td class=\"lang\">{escape(lang_label)}</td>"
                f"<td>{word_count}</td>"
                f"<td>{kw_display}</td>"
                f"<td>{link_count}</td>"
                f"{tr_cell}"
                f"</tr>"
            )
        parts.append("      </tbody>")
        parts.append("    </table>")
    else:
        parts.append('    <p class="empty">The latest run produced no summary entries.</p>')

    # Footer
    parts.append("  <footer>")
    parts.append(
        f'    This page was generated on {escape(fmt_sd(now))}. '
        f'Next check within 15 minutes.'
    )
    parts.append("  </footer>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


def render_translations_html() -> str:
    """Render /admin/translations/ — Weglot CSV downloads, FIDELO SYNC FILES ONLY.

    The download is a single ZIP of `Fidelo/<lang>.csv` (course & housing on-page
    text — titles, bullets, USP facts, accordion sections), one per non-English
    locale, straight from the Fidelo exporter.

    Summary paragraphs + page meta are NO LONGER offered here (2026-05-26): they are
    produced and imported via the summary block-reuse pipeline (`tools/summary`), not
    this dashboard. Keep this page Fidelo-only — do not re-add a Summaries download.
    """
    now = now_san_diego()
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Weglot Translations — English College</title>")
    parts.append('  <meta name="description" content="Download Weglot import CSVs: Fidelo on-page text (course & housing titles, bullets, USP facts) for all 8 non-English locales.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Intro
    parts.append('    <section class="status status-ok">')
    parts.append('      <p class="status-label">Weglot CSV downloads — Fidelo sync files.</p>')
    parts.append('      <p>Download the single ZIP below. It unzips into a <strong>Fidelo/</strong> folder with one <code>&lt;lang&gt;.csv</code> per non-English locale — course &amp; housing on-page text (titles, bullets, USP facts, accordion sections). Import each into the Weglot Dashboard (with “Overwrite existing translations” on) to replace machine translations with authoritative copy. <em>Summary paragraphs &amp; page meta are handled by the summary pipeline and are not listed here.</em></p>')
    parts.append("    </section>")

    parts.append("    <h2>Weglot import files</h2>")
    parts.append('    <ul class="files">')

    # The ONE download — a ZIP with the Fidelo/ folder (Fidelo sync files only).
    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">Fidelo translations — Download all (ZIP: Fidelo/&lt;lang&gt;.csv, all 8 languages)</span>')
    parts.append(f'        <a href="{escape(PUBLIC_WEGLOT_ZIP_URL)}" download>Download ZIP</a>')
    parts.append("      </div>")
    ts_zip = file_mtime_iso(WEGLOT_ZIP_FILE)
    note_zip = f"Last updated on {escape(iso_to_sd(ts_zip))}" if ts_zip else "Not yet generated"
    parts.append(f'      <p class="subtle">{note_zip} — unzip, then import each <code>Fidelo/&lt;lang&gt;.csv</code> in the Weglot Dashboard.</p>')
    parts.append("    </li>")

    parts.append("  </ul>")

    # Per-language import status — INFO ONLY (no per-file download; everything
    # ships in the ZIP above). Kept so the operator still sees what's imported.
    parts.append("    <h2>Per-language import status</h2>")
    import_status_by_lang = load_import_status()
    parts.append('    <ul class="files">')
    for lang in WEGLOT_CSV_LANGUAGES:
        lang_name = LANGUAGE_NAMES.get(lang, lang.upper())
        csv_path = WEGLOT_CSV_DIR / f"{lang}.csv"
        ts = file_mtime_iso(csv_path)
        note = f"Last updated on {escape(iso_to_sd(ts))}" if ts else "Not yet generated"
        badge = render_import_badge(import_status_by_lang.get(lang))
        parts.append("    <li>")
        parts.append('      <div class="file-row">')
        parts.append(f'        <span class="file-name">{escape(lang_name)} ({lang})</span>')
        parts.append("      </div>")
        if badge:
            parts.append(f'      <p class="subtle">{note} {badge}</p>')
        else:
            parts.append(f'      <p class="subtle">{note}</p>')
        parts.append("    </li>")

    parts.append("  </ul>")

    # Footer
    parts.append("  <footer>")
    parts.append(
        f'    This page was generated on {escape(fmt_sd(now))}. '
        f'Next check within 15 minutes.'
    )
    parts.append("  </footer>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


# The tracking we built, as business OUTCOMES (curated; never names a tag/event; never a count).
# Each line maps to one of the live tags but the client copy stays jargon-free.
TRACKING_SHOWCASE = [
    "People clicking your buttons and calls-to-action",
    "People sending an enquiry (your leads)",
    "People viewing your courses",
    "People choosing a specific course",
    "People searching and browsing your course lists",
    "How far people read down each page",
    "People switching language",
    "People opening your FAQs",
    "People using your menus and navigation",
    "People jumping between sections of a page",
    "Where each visitor came from when they arrive",
    "Privacy choices respected on every visit",
]


def render_analytics_html() -> str:
    """Render /admin/analytics/ — a client-facing, jargon-free Analytics tab: a showcase
    of everything we track + a LIVE embedded Google Analytics (Looker Studio) report that
    shows the real numbers in-page. No links to click out (so the multi-Google-account
    problem can't happen); the report is owned by the client's Google account and refreshes
    automatically. Embed URL = LOOKER_EMBED_URL (shared 'anyone with the link' + embedding
    enabled by the account owner)."""
    now = now_san_diego()

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Your Website Analytics &mdash; English College</title>")
    parts.append('  <meta name="description" content="A plain-English overview of how your website is doing.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f"  {render_favicon_tag()}")
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Intro
    parts.append('    <section class="status status-ok">')
    parts.append('      <p class="status-label">Your website analytics &mdash; live</p>')
    parts.append('      <p>Everything we track for you is listed below, with your real, always-up-to-date numbers shown right on this page. The figures come straight from Google Analytics and refresh on their own.</p>')
    parts.append("    </section>")

    # What we track (the showcase) — listed first, per the client's request
    parts.append("  <h2>What we keep an eye on for you</h2>")
    parts.append("  <p>We&rsquo;ve set up detailed, always-on tracking across your whole site &mdash; in every language &mdash; so we can see what&rsquo;s working and where to grow your enquiries:</p>")
    parts.append('  <ul class="activity">')
    for item in TRACKING_SHOWCASE:
        parts.append(f'    <li><span>&#10003;</span><span>{escape(item)}</span></li>')
    parts.append("  </ul>")

    # The live statistics — embedded Google Analytics report (real numbers, no click-out)
    parts.append("  <h2>Your live statistics</h2>")
    parts.append("  <p>Visitors, where they come from, your most-visited pages and which countries they&rsquo;re in &mdash; updated automatically. Use the tabs on the left inside the report to explore.</p>")
    parts.append(
        f'  <iframe title="College of English Language &mdash; website analytics" '
        f'src="{LOOKER_EMBED_URL}" width="100%" height="2125" frameborder="0" '
        f'style="border:0;display:block;width:100%" allowfullscreen '
        f'sandbox="allow-storage-access-by-user-activation allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>'
    )

    parts.append("  <footer>")
    parts.append(f"    Page last built {escape(fmt_sd(now))}. The statistics above update live from Google Analytics.")
    parts.append("  </footer>")
    parts.append("  </div>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_status_page() -> None:
    write_external_css(EXTERNAL_REPO_ROOT)
    write_dashboard_config(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(), encoding="utf-8")
    TRANSLATIONS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATIONS_OUTPUT_FILE.write_text(render_translations_html(), encoding="utf-8")
    FILES_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FILES_OUTPUT_FILE.write_text(render_files_html(), encoding="utf-8")
    SUMMARIES_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARIES_OUTPUT_FILE.write_text(render_summaries_html(), encoding="utf-8")
    ANALYTICS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANALYTICS_OUTPUT_FILE.write_text(render_analytics_html(), encoding="utf-8")


def main() -> int:
    write_status_page()
    print(f"[status_page] Wrote {OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {TRANSLATIONS_OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {FILES_OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {SUMMARIES_OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {ANALYTICS_OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
