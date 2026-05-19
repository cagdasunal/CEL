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
TRANSLATIONS_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "translations" / "index.html"
FILES_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "files" / "index.html"
SUMMARIES_OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "summaries" / "index.html"

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
    """Find the most recent timestamped subdir under SUMMARY_DRYRUN_DIR.

    Directory names are 'YYYYMMDDTHHMMSSZ' so lexical sort = chronological.
    Returns None if SUMMARY_DRYRUN_DIR doesn't exist or has no subdirs.
    """
    if not SUMMARY_DRYRUN_DIR.exists():
        return None
    subdirs = sorted(
        (p for p in SUMMARY_DRYRUN_DIR.iterdir() if p.is_dir()),
        reverse=True,
    )
    return subdirs[0] if subdirs else None


def _count_words_in_markdown(md: str) -> int:
    """Strip Markdown syntax + count whitespace-separated words. Best-effort."""
    if not md:
        return 0
    import re as _re
    stripped = _re.sub(r"```.*?```", "", md, flags=_re.DOTALL)
    stripped = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = _re.sub(r"[#*`>_~|\[\](){}<>]", " ", stripped)
    return len(_re.findall(r"\b\w+\b", stripped, flags=_re.UNICODE))


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
    cls = mapping.get(content_type, "badge-when")
    return f'<span class="{cls}">{escape(content_type or "—")}</span>'


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
    audit_scores: dict[str, dict] = {}
    manual_review: dict = {}
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
    try:
        audit_path = latest / "audit-scores.json"
        if audit_path.exists():
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            for row in audit_data.get("scores", []):
                if isinstance(row, dict) and "url" in row:
                    audit_scores[row["url"]] = row
    except (json.JSONDecodeError, OSError):
        audit_scores = {}
    try:
        review_path = latest / "manual-review.json"
        if review_path.exists():
            manual_review = json.loads(review_path.read_text(encoding="utf-8"))
            if not isinstance(manual_review, dict):
                manual_review = {}
    except (json.JSONDecodeError, OSError):
        manual_review = {}

    # Derive aggregate stats.
    total = len(en_summaries)
    total_words = sum(_count_words_in_markdown(e.get("markdown", "")) for e in en_summaries.values())
    avg_words = (total_words // total) if total else 0
    by_locale: dict[str, int] = {}
    for entry in en_summaries.values():
        loc = entry.get("locale", "—")
        by_locale[loc] = by_locale.get(loc, 0) + 1
    started_at = report.get("started_at", "")
    started_human = iso_to_sd(started_at) if started_at else "—"
    is_dry = bool(report.get("dry_run"))
    subcommand = report.get("subcommand", "—")
    gen_phase = report.get("phases", {}).get("generate_english", {}) if isinstance(report.get("phases"), dict) else {}
    cost_estimate = gen_phase.get("cost_estimate_usd")
    batch_id = gen_phase.get("batch_id", "—")
    succeeded = gen_phase.get("succeeded")
    failed = gen_phase.get("failed")

    # Status banner.
    status_class = "status-ok"
    dry_label = " (dry-run)" if is_dry else ""
    parts.append(f'    <section class="status {status_class}">')
    parts.append(f'      <p class="status-label">Latest run: {escape(subcommand)}{dry_label}</p>')
    parts.append(f'      <p>Generated on <strong>{escape(started_human)}</strong>. Run directory: <code>{escape(latest.name)}</code>.</p>')
    parts.append("    </section>")

    # Manual-review banner (if applicable).
    if manual_review.get("custom_ids"):
        n_review = len(manual_review["custom_ids"])
        parts.append('    <section class="status error">')
        parts.append(f'      <p class="status-label">{n_review} item{"s" if n_review != 1 else ""} need manual review.</p>')
        parts.append('      <p>The summary script retried these once and they still failed. Open <code>manual-review.json</code> for details.</p>')
        parts.append("    </section>")

    # Aggregate KPIs.
    parts.append("    <h2>Run overview</h2>")
    parts.append('    <table class="kv-table">')
    parts.append('      <tbody>')
    parts.append(f'        <tr><td class="k">Total summaries</td><td class="v"><strong>{total}</strong></td></tr>')
    parts.append(f'        <tr><td class="k">Total words</td><td class="v"><strong>{total_words:,}</strong></td></tr>')
    parts.append(f'        <tr><td class="k">Average words per summary</td><td class="v">{avg_words:,}</td></tr>')
    if by_locale:
        loc_pairs = ", ".join(f"{escape(k)}: {v}" for k, v in sorted(by_locale.items()))
        parts.append(f'        <tr><td class="k">By locale</td><td class="v">{loc_pairs}</td></tr>')
    if cost_estimate is not None:
        parts.append(f'        <tr><td class="k">Estimated cost</td><td class="v">${cost_estimate:.2f}</td></tr>')
    if succeeded is not None:
        parts.append(f'        <tr><td class="k">Succeeded</td><td class="v">{succeeded}</td></tr>')
    if failed is not None:
        parts.append(f'        <tr><td class="k">Failed</td><td class="v">{failed}</td></tr>')
    if batch_id and batch_id != "—":
        parts.append(f'        <tr><td class="k">Batch ID</td><td class="v"><code>{escape(batch_id)}</code></td></tr>')
    parts.append('      </tbody>')
    parts.append('    </table>')

    # Per-item table.
    parts.append("    <h2>Summaries</h2>")
    if en_summaries:
        parts.append("    <table>")
        parts.append("      <thead>")
        parts.append("        <tr><th>Page</th><th>Type</th><th>Locale</th><th>Words</th><th>Keywords</th><th>Audit</th><th>Status</th></tr>")
        parts.append("      </thead>")
        parts.append("      <tbody>")
        for cid, entry in en_summaries.items():
            url = entry.get("url", "")
            md = entry.get("markdown", "") or ""
            content_type = entry.get("content_type", "")
            locale = entry.get("locale", "—")
            kw_plan = entry.get("keyword_plan") or {}
            word_count = _count_words_in_markdown(md)
            if kw_plan:
                primary = 1 if kw_plan.get("primary") else 0
                secondaries = len(kw_plan.get("secondaries") or [])
                entities = len(kw_plan.get("entities") or [])
                kw_count = primary + secondaries + entities
                kw_display = (
                    f'{kw_count} '
                    f'<span class="subtle">'
                    f'({primary}p, {secondaries}s, {entities}e)'
                    f'</span>'
                )
            else:
                kw_display = '—'
            if url.startswith("http://") or url.startswith("https://"):
                page_html = f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(url)}</a>'
            else:
                page_html = f'<span class="subtle">{escape(url)}</span>'
            paste_html = ""
            if content_type == "landing":
                slug = _slug_from_url(url)
                paste_file = STATIC_SUMMARIES_DIR / f"{slug}.summary.md"
                if paste_file.exists():
                    paste_html = ' <span class="badge-partial">Paste pending</span>'
            audit_row = audit_scores.get(url)
            audit_action = audit_row.get("action") if isinstance(audit_row, dict) else None
            parts.append(
                f"        <tr>"
                f"<td>{page_html}</td>"
                f"<td>{_content_type_badge(content_type)}</td>"
                f"<td class=\"lang\">{escape(locale)}</td>"
                f"<td>{word_count}</td>"
                f"<td>{kw_display}</td>"
                f"<td>{_audit_action_badge(audit_action)}</td>"
                f"<td>{paste_html.strip() or '—'}</td>"
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
    """Render /admin/translations/ — Fidelo translation downloads only.

    Contains the 10 Weglot CSV download rows (1 ZIP bundle + 1 all-languages
    matrix + 8 per-language CSVs) extracted from the previous /admin/log/ page.
    Sitemap, llms.txt, blog post sync, and recent activity remain on /admin/log/.
    """
    now = now_san_diego()
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Fidelo Translations — English College</title>")
    parts.append('  <meta name="description" content="Download Fidelo translation overrides as Weglot CSVs.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    # Intro
    parts.append('    <section class="status status-ok">')
    parts.append('      <p class="status-label">Fidelo translation downloads.</p>')
    parts.append('      <p>One ZIP bundle and one CSV per non-English locale. Each CSV covers both course and housing on-page text (titles, bullets, USP facts, accordion sections). Import each per-language CSV into the Weglot Dashboard to override machine translations with Fidelo\'s authoritative copy.</p>')
    parts.append("    </section>")

    parts.append("    <h2>Weglot import files</h2>")
    parts.append('    <ul class="files">')

    # ZIP bundle
    parts.append("    <li>")
    parts.append('      <div class="file-row">')
    parts.append('        <span class="file-name">Weglot translations — Download all (ZIP, all 8 languages)</span>')
    parts.append(f'        <a href="{escape(PUBLIC_WEGLOT_ZIP_URL)}" download>Download ZIP</a>')
    parts.append("      </div>")
    ts_zip = file_mtime_iso(WEGLOT_ZIP_FILE)
    note_zip = f"Last updated on {escape(iso_to_sd(ts_zip))}" if ts_zip else "Not yet generated"
    parts.append(f'      <p class="subtle">{note_zip} — unzip locally, then import each <code>&lt;lang&gt;.csv</code> in the Weglot Dashboard.</p>')
    parts.append("    </li>")

    # Per-language CSVs (with import-status badges)
    import_status_by_lang = load_import_status()
    for lang in WEGLOT_CSV_LANGUAGES:
        lang_name = LANGUAGE_NAMES.get(lang, lang.upper())
        csv_url = PUBLIC_WEGLOT_CSV_URL_TEMPLATE.format(lang=lang)
        csv_path = WEGLOT_CSV_DIR / f"{lang}.csv"
        ts = file_mtime_iso(csv_path)
        note = f"Last updated on {escape(iso_to_sd(ts))}" if ts else "Not yet generated"
        badge = render_import_badge(import_status_by_lang.get(lang))
        parts.append("    <li>")
        parts.append('      <div class="file-row">')
        parts.append(f'        <span class="file-name">Weglot translations — {escape(lang_name)} ({lang}.csv)</span>')
        parts.append(f'        <a href="{escape(csv_url)}" download>Download</a>')
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_status_page() -> None:
    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(), encoding="utf-8")
    TRANSLATIONS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATIONS_OUTPUT_FILE.write_text(render_translations_html(), encoding="utf-8")
    FILES_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FILES_OUTPUT_FILE.write_text(render_files_html(), encoding="utf-8")
    SUMMARIES_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARIES_OUTPUT_FILE.write_text(render_summaries_html(), encoding="utf-8")


def main() -> int:
    write_status_page()
    print(f"[status_page] Wrote {OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {TRANSLATIONS_OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {FILES_OUTPUT_FILE}", flush=True)
    print(f"[status_page] Wrote {SUMMARIES_OUTPUT_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
