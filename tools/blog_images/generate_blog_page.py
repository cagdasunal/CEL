#!/usr/bin/env python3
"""
generate_blog_page.py — Renders /admin/blog/index.html.

Reads:
  data/blog-optimization-log.jsonl  — one JSON object per image processed

Writes (into external repo):
  <EXTERNAL_REPO_ROOT>/admin/blog/index.html
      — served at https://cel.englishcollege.com/admin/blog/

Companion to scripts/optimize_blog_richtext_images.py — the optimizer
appends to the JSONL each night; this generator renders a stable status page
matching the styling of /admin/log/, /admin/offers/, /admin/housing/, etc.

No external dependencies. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.dashboard import (
    AUTH_SCRIPT_TAG,
    EXTERNAL_REPO_ROOT,
    render_favicon_tag,
    render_page_chrome,
    render_sync_status_card,
    write_external_css,
    write_shell_html,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_LOG_FILE = DATA_DIR / "blog-optimization-log.jsonl"
OUTPUT_FILE = EXTERNAL_REPO_ROOT / "admin" / "blog" / "index.html"

LAST_N_DAYS_ROLLUP = 7
MAX_DETAIL_ROWS = 200  # cap rendering on very long histories


# ---------------------------------------------------------------------------
# Time helpers (same pattern as tools/weglot/generate_status_page.py)
# ---------------------------------------------------------------------------

def _tz_abbr(dt: datetime) -> str:
    offset = dt.utcoffset()
    if offset is not None:
        secs = int(offset.total_seconds())
        if secs == -7 * 3600:
            return "PDT"
        if secs == -8 * 3600:
            return "PST"
    return dt.strftime("%Z") or ""


def fmt_sd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %I:%M %p ") + _tz_abbr(dt)


def now_san_diego() -> datetime:
    return datetime.now(tz=SAN_DIEGO_TZ)


def iso_to_dt(ts_iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def iso_to_sd(ts_iso: str) -> str:
    dt = iso_to_dt(ts_iso)
    if dt is None:
        return ts_iso or "—"
    return fmt_sd(dt.astimezone(SAN_DIEGO_TZ))


# ---------------------------------------------------------------------------
# Log loading
# ---------------------------------------------------------------------------

def load_log(log_file: Path) -> list[dict]:
    """Read JSONL. Skip blank lines + malformed entries silently — the file
    is append-only by an automated process; partial writes are not catastrophic."""
    if not log_file.exists():
        return []
    out: list[dict] = []
    try:
        text = log_file.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

def san_diego_date_of(entry: dict) -> str | None:
    dt = iso_to_dt(entry.get("ts", ""))
    if dt is None:
        return None
    return dt.astimezone(SAN_DIEGO_TZ).strftime("%Y-%m-%d")


def latest_run_id(entries: list[dict]) -> str | None:
    """Run_id of the most recent entry. None if no entries."""
    if not entries:
        return None
    sorted_entries = sorted(
        entries,
        key=lambda e: e.get("ts") or "",
        reverse=True,
    )
    for e in sorted_entries:
        rid = e.get("run_id")
        if rid:
            return rid
    return None


def filter_run(entries: list[dict], run_id: str) -> list[dict]:
    return [e for e in entries if e.get("run_id") == run_id]


def filter_last_n_days(entries: list[dict], n: int) -> list[dict]:
    cutoff = now_san_diego() - timedelta(days=n)
    out: list[dict] = []
    for e in entries:
        dt = iso_to_dt(e.get("ts", ""))
        if dt is None:
            continue
        if dt.astimezone(SAN_DIEGO_TZ) >= cutoff:
            out.append(e)
    return out


def filter_today_san_diego(entries: list[dict]) -> list[dict]:
    today_sd = now_san_diego().strftime("%Y-%m-%d")
    return [e for e in entries if san_diego_date_of(e) == today_sd]


def filter_current_week(entries: list[dict]) -> list[dict]:
    """ISO week (Mon 00:00 → now) in San Diego timezone."""
    now = now_san_diego()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    out: list[dict] = []
    for e in entries:
        dt = iso_to_dt(e.get("ts", ""))
        if dt is None:
            continue
        if dt.astimezone(SAN_DIEGO_TZ) >= monday:
            out.append(e)
    return out


def filter_current_month(entries: list[dict]) -> list[dict]:
    """Calendar month (1st 00:00 → now) in San Diego timezone."""
    now = now_san_diego()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out: list[dict] = []
    for e in entries:
        dt = iso_to_dt(e.get("ts", ""))
        if dt is None:
            continue
        if dt.astimezone(SAN_DIEGO_TZ) >= first:
            out.append(e)
    return out


def aggregate(entries: list[dict]) -> dict:
    """Sum stats + per-action counts."""
    actions: dict[str, int] = defaultdict(int)
    old_total = 0
    new_total = 0
    posts: set[str] = set()
    for e in entries:
        actions[e.get("action") or "unknown"] += 1
        try:
            old_total += int(e.get("old_bytes") or 0)
            new_total += int(e.get("new_bytes") or 0)
        except (TypeError, ValueError):
            pass
        if e.get("post_slug"):
            posts.add(e["post_slug"])
    saved = old_total - new_total
    pct = (saved / old_total * 100.0) if old_total > 0 else 0.0
    return {
        "image_total": len(entries),
        "replaced": actions.get("replaced", 0),
        "skipped_avif": actions.get("skipped_avif", 0),
        "skipped_small": actions.get("skipped_small", 0),
        "errors": actions.get("error", 0),
        "old_bytes": old_total,
        "new_bytes": new_total,
        "saved_bytes": saved,
        "saved_pct": pct,
        "post_count": len(posts),
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def fmt_pct(p: float) -> str:
    return f"{p:.1f}%"


def shorten_url(url: str, max_len: int = 60) -> str:
    if len(url) <= max_len:
        return url
    head = url[: max_len - 20]
    tail = url[-20:]
    return f"{head}…{tail}"


def filename_from_url(url: str) -> str:
    if not url:
        return "—"
    last = url.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    return last or url


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_kv(label: str, value: str, *, emphasize: bool = False) -> str:
    style = ' style="font-weight:600;font-size:var(--fs-lg);"' if emphasize else ""
    return (
        f'<tr><td class="k">{escape(label)}</td>'
        f'<td class="v"{style}>{escape(value)}</td></tr>'
    )


def render_stat_cards(entries: list[dict]) -> str:
    """Four cards: Today / This week / This month / All-time bytes saved."""
    periods = [
        ("Today",      filter_today_san_diego(entries)),
        ("This week",  filter_current_week(entries)),
        ("This month", filter_current_month(entries)),
        ("All-time",   entries),
    ]
    cards: list[str] = []
    for label, subset in periods:
        agg = aggregate(subset)
        saved = max(agg["saved_bytes"], 0)
        n_imgs = agg["replaced"]
        plural = "s" if n_imgs != 1 else ""
        cards.append(
            '<div class="stat-card">'
            f'<div class="stat-label">{escape(label)}</div>'
            f'<div class="stat-value">{escape(fmt_bytes(saved))}</div>'
            f'<div class="stat-sub">saved &middot; {n_imgs} image{plural}</div>'
            '</div>'
        )
    return (
        '<h2>Bytes saved</h2>'
        '<div class="stat-cards">' + "".join(cards) + '</div>'
    )


def render_tab_styles() -> str:
    """Inline CSS for the in-page tab nav + stat cards.

    Mirrors the offers viewer pattern (tools/offers/build_offers_viewer.py).
    Class names are scoped (.blog-tabs / .blog-tab-link / .stat-card) to avoid
    collision with the offers page's `.offers-tab-link`.
    """
    return (
        "<style>\n"
        "  [data-tab]{display:none}\n"
        "  [data-tab].is-active{display:block}\n"
        "  .blog-tabs{margin:16px 0 20px;display:flex;gap:8px}\n"
        "  .blog-tab-link{display:inline-block;padding:6px 14px;"
        "border-radius:4px;text-decoration:none;color:inherit;"
        "border:1px solid var(--border-strong);font-weight:500}\n"
        "  .blog-tab-link:hover{background:var(--stripe)}\n"
        "  .blog-tab-link.is-active{background:var(--stripe);"
        "border-color:var(--accent);color:var(--accent);font-weight:600}\n"
        "  .stat-cards{display:grid;grid-template-columns:repeat(4,1fr);"
        "gap:12px;margin:8px 0 32px}\n"
        "  .stat-card{padding:16px;border:1px solid var(--border);"
        "border-radius:var(--radius);background:var(--stripe)}\n"
        "  .stat-label{font-size:var(--fs-xs);font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.08em;"
        "color:var(--muted);margin-bottom:8px}\n"
        "  .stat-value{font-size:24px;font-weight:600;"
        "color:var(--fg);font-variant-numeric:tabular-nums}\n"
        "  .stat-sub{font-size:var(--fs-sm);color:var(--muted);"
        "margin-top:4px}\n"
        "  .latest-run-line{font-size:var(--fs-sm);color:var(--muted);"
        "margin:0 0 24px}\n"
        "  @media (max-width:820px){"
        ".stat-cards{grid-template-columns:repeat(2,1fr)}}\n"
        "  @media (max-width:480px){"
        ".stat-cards{grid-template-columns:1fr}}\n"
        "</style>"
    )


def render_tab_nav() -> str:
    return (
        '<nav class="blog-tabs">'
        '<a class="blog-tab-link" href="#status">Status</a>'
        '<a class="blog-tab-link" href="#history">History</a>'
        '</nav>'
    )


def render_tab_script() -> str:
    return (
        "<script>(function(){"
        "function apply(){"
        "var h=(location.hash||'#status').slice(1);"
        "if(h!=='status'&&h!=='history')h='status';"
        "document.querySelectorAll('[data-tab]').forEach(function(el){"
        "el.classList.toggle('is-active',el.getAttribute('data-tab')===h);});"
        "document.querySelectorAll('.blog-tab-link').forEach(function(a){"
        "a.classList.toggle('is-active',a.getAttribute('href')==='#'+h);});}"
        "window.addEventListener('hashchange',apply);apply();"
        "})();</script>"
    )


def render_latest_run_line(run_stats: dict, last_run_iso: str | None) -> str:
    lr = iso_to_sd(last_run_iso) if last_run_iso else "—"
    return (
        '<p class="latest-run-line">'
        f'Latest run: <strong>{escape(lr)}</strong> &middot; '
        f'{run_stats["post_count"]} post(s) touched &middot; '
        f'{run_stats["replaced"]} replaced &middot; '
        f'{run_stats["errors"]} error(s)'
        '</p>'
    )


def render_summary_card(today_stats: dict, today_label: str, last_run_iso: str | None) -> str:
    lr_str = iso_to_sd(last_run_iso) if last_run_iso else "—"
    rows = [
        render_kv("Last run", lr_str),
        render_kv("Today (San Diego)", today_label),
        render_kv("Posts touched today", str(today_stats["post_count"])),
        render_kv("Images replaced", str(today_stats["replaced"])),
        render_kv("Images skipped (already AVIF)", str(today_stats["skipped_avif"])),
        render_kv("Images skipped (savings <30%)", str(today_stats["skipped_small"])),
        render_kv("Errors", str(today_stats["errors"])),
        render_kv("Bytes before", fmt_bytes(today_stats["old_bytes"])),
        render_kv("Bytes after", fmt_bytes(today_stats["new_bytes"])),
        render_kv(
            "Total saved today",
            f"{fmt_bytes(today_stats['saved_bytes'])} ({fmt_pct(today_stats['saved_pct'])})",
            emphasize=True,
        ),
    ]
    return (
        '<h2>Today\'s run</h2>'
        '<table class="kv-table"><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_rollup_card(rollup_stats: dict) -> str:
    rows = [
        render_kv("Posts touched", str(rollup_stats["post_count"])),
        render_kv("Images replaced", str(rollup_stats["replaced"])),
        render_kv("Errors", str(rollup_stats["errors"])),
        render_kv("Bytes before", fmt_bytes(rollup_stats["old_bytes"])),
        render_kv("Bytes after", fmt_bytes(rollup_stats["new_bytes"])),
        render_kv(
            "Saved",
            f"{fmt_bytes(rollup_stats['saved_bytes'])} ({fmt_pct(rollup_stats['saved_pct'])})",
            emphasize=True,
        ),
    ]
    return (
        f'<h2>Last {LAST_N_DAYS_ROLLUP} days</h2>'
        '<table class="kv-table"><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_action_badge(action: str) -> str:
    classes = {
        "replaced": "badge-ok",
        "skipped_avif": "badge-partial",
        "skipped_small": "badge-partial",
        "error": "badge-failed",
    }
    label = {
        "replaced": "✓ Replaced",
        "skipped_avif": "↻ Skipped (AVIF)",
        "skipped_small": "↻ Skipped (small)",
        "error": "✗ Error",
    }
    cls = classes.get(action, "badge-partial")
    text = label.get(action, action or "—")
    return f'<span class="{cls}">{escape(text)}</span>'


def render_image_table(entries: list[dict]) -> str:
    """Per-image table — collapsible details rows for the URLs.

    Uses the existing dashboard table styling. Truncates to MAX_DETAIL_ROWS.
    """
    if not entries:
        return '<p class="empty">No image-level entries to show yet.</p>'

    # Newest first
    sorted_entries = sorted(entries, key=lambda e: e.get("ts") or "", reverse=True)[:MAX_DETAIL_ROWS]

    parts = ['<h2>Images processed today</h2>']
    parts.append("<table>")
    parts.append("<thead><tr>"
                 "<th>Post</th>"
                 "<th>Filename</th>"
                 "<th>Action</th>"
                 "<th>Old size</th>"
                 "<th>New size</th>"
                 "<th>Savings</th>"
                 "</tr></thead>")
    parts.append("<tbody>")
    for e in sorted_entries:
        slug = e.get("post_slug") or "—"
        old_url = e.get("old_url") or ""
        new_url = e.get("new_url") or ""
        old_b = int(e.get("old_bytes") or 0)
        new_b = int(e.get("new_bytes") or 0)
        pct = e.get("saving_pct")
        if pct is None and old_b > 0:
            pct = (old_b - new_b) / old_b * 100.0
        pct_disp = fmt_pct(float(pct)) if pct is not None else "—"

        parts.append(
            "<tr>"
            f'<td class="slug">{escape(slug)}</td>'
            f"<td>{escape(filename_from_url(old_url))}</td>"
            f"<td>{render_action_badge(e.get('action') or '')}</td>"
            f"<td>{fmt_bytes(old_b)}</td>"
            f"<td>{fmt_bytes(new_b)}</td>"
            f"<td>{escape(pct_disp)}</td>"
            "</tr>"
        )

        # Detail row — collapsible <details> below for URL inspection
        err = e.get("error")
        ts_disp = iso_to_sd(e.get("ts") or "")
        detail_html = (
            "<details><summary>Details</summary>"
            '<div class="tech-body">'
            f'<p class="subtle"><strong>Old URL:</strong> '
            f'<a href="{escape(old_url)}" target="_blank" rel="noopener">{escape(shorten_url(old_url, 90))}</a></p>'
        )
        if new_url:
            detail_html += (
                f'<p class="subtle"><strong>New URL:</strong> '
                f'<a href="{escape(new_url)}" target="_blank" rel="noopener">{escape(shorten_url(new_url, 90))}</a></p>'
            )
        detail_html += f'<p class="subtle"><strong>Timestamp:</strong> {escape(ts_disp)}</p>'
        if err:
            detail_html += f'<p class="subtle status-failed"><strong>Error:</strong> {escape(str(err))}</p>'
        detail_html += "</div></details>"

        parts.append(f'<tr><td colspan="6">{detail_html}</td></tr>')

    parts.append("</tbody></table>")
    if len(entries) > MAX_DETAIL_ROWS:
        parts.append(
            f'<p class="subtle">Showing newest {MAX_DETAIL_ROWS} of {len(entries)} entries.</p>'
        )
    return "".join(parts)


def render_empty_state() -> str:
    return (
        '<section class="status status-ok">'
        '<p class="status-label">No optimization runs yet.</p>'
        "<p>The first nightly run is scheduled for <strong>03:00 PT</strong> "
        "(11:00 UTC). You can also trigger it manually via the GitHub Actions "
        '<em>blog-image-optimization</em> workflow.</p>'
        "</section>"
    )


def render_html(entries: list[dict]) -> str:
    now_sd = now_san_diego()
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append(f"  {AUTH_SCRIPT_TAG}")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Blog images — English College</title>")
    parts.append('  <meta name="description" content="Nightly AVIF optimization for blog post rich-text images.">')
    parts.append('  <meta name="robots" content="noindex, nofollow">')
    parts.append(f'  {render_favicon_tag()}')
    parts.append('  <link rel="stylesheet" href="/assets/css/dashboard.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <div class="dashboard-shell">')

    parts.append(render_page_chrome("BLOG IMAGES", "Nightly AVIF optimization for rich-text content"))

    if not entries:
        parts.append("    " + render_empty_state())
    else:
        run_id = latest_run_id(entries)
        run_entries = filter_run(entries, run_id) if run_id else []
        last_run_ts = run_entries[0].get("ts") if run_entries else None
        run_stats = aggregate(run_entries)
        any_errors = run_stats["errors"] > 0
        is_ok = not any_errors
        last_run_label = iso_to_sd(last_run_ts) if last_run_ts else "—"

        # In-page tab nav + scoped CSS + toggle script (offers pattern)
        parts.append("    " + render_tab_styles())
        parts.append("    " + render_tab_nav())

        # ── Status tab (default) ───────────────────────────────────────────
        parts.append('    <section data-tab="status">')
        parts.append("      " + render_sync_status_card(
            "Latest run completed.",
            last_run_label,
            is_ok=is_ok,
        ))
        parts.append("      " + render_stat_cards(entries))
        parts.append("      " + render_latest_run_line(run_stats, last_run_ts))
        parts.append("    </section>")

        # ── History tab ────────────────────────────────────────────────────
        parts.append('    <section data-tab="history">')
        today_sd_label = now_sd.strftime("%Y-%m-%d")
        parts.append("      " + render_summary_card(run_stats, today_sd_label, last_run_ts))
        rollup_entries = filter_last_n_days(entries, LAST_N_DAYS_ROLLUP)
        rollup_stats = aggregate(rollup_entries)
        parts.append("      " + render_rollup_card(rollup_stats))
        parts.append("      " + render_image_table(run_entries))
        parts.append("    </section>")

        parts.append("    " + render_tab_script())

    parts.append("  <footer>")
    parts.append(
        f"    Page generated on {escape(fmt_sd(now_sd))}. "
        f"Optimizer runs nightly at 03:00 PT (11:00 UTC). "
        f"Manual trigger: GitHub Actions → blog-image-optimization → Run workflow."
    )
    parts.append("  </footer>")
    parts.append("  </div>")  # close .dashboard-shell
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_blog_page(log_file: Path) -> Path:
    write_external_css(EXTERNAL_REPO_ROOT)
    write_shell_html(EXTERNAL_REPO_ROOT)
    entries = load_log(log_file)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(entries), encoding="utf-8")
    return OUTPUT_FILE


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Render the /admin/blog/ dashboard page from the optimization log.",
    )
    p.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_FILE),
        help=f"Path to JSONL log (default: {DEFAULT_LOG_FILE.relative_to(PROJECT_ROOT)})",
    )
    args = p.parse_args(argv)

    # Allow override via env (mirrors patterns in other tools/* generators)
    log_path = Path(os.environ.get("BLOG_LOG_OVERRIDE", args.log_file))
    written = write_blog_page(log_path)
    print(f"[blog_images] Wrote {written}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
