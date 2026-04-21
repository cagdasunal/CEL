#!/usr/bin/env python3
"""
Update log.txt — event-based, client-facing, San Diego time.

Events:
  weglot_update   — new posts added to translation exclusions (--slugs required)
  no_change       — routine check, nothing changed
  sitemap_refreshed — sitemap regenerated
  llms_refreshed  — llms.txt regenerated
  error           — something went wrong (--error required)

Usage:
  python3 tools/weglot/update_log.py --event no_change
  python3 tools/weglot/update_log.py --event weglot_update --slugs slug1,slug2
  python3 tools/weglot/update_log.py --event error --error "post failed: HTTP 400"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = PROJECT_ROOT / "log.txt"
STATE_FILE = PROJECT_ROOT / "data" / "log-state.json"

MAX_RECENT_EVENTS = 10

PUBLIC_SITEMAP_URL = "https://sitemap.englishcollege.com/sitemap.xml"
PUBLIC_LLMS_URL = "https://sitemap.englishcollege.com/llms.txt"

VALID_EVENTS = {"weglot_update", "no_change", "sitemap_refreshed", "llms_refreshed", "error"}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_san_diego() -> datetime:
    return datetime.now(tz=SAN_DIEGO_TZ)


def fmt_sd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %I:%M %p %Z")


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"events": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def append_event(kind: str, detail: dict) -> None:
    state = load_state()
    events = state.get("events", [])
    events.insert(0, {
        "kind": kind,
        "ts": now_san_diego().isoformat(),
        "detail": detail,
    })
    state["events"] = events[:MAX_RECENT_EVENTS]
    save_state(state)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_event(event: dict) -> str:
    kind = event.get("kind", "")
    ts_raw = event.get("ts", "")
    detail = event.get("detail", {})

    try:
        dt = datetime.fromisoformat(ts_raw)
        ts_fmt = fmt_sd(dt)
    except (ValueError, TypeError):
        ts_fmt = ts_raw

    if kind == "weglot_update":
        slugs = detail.get("slugs", [])
        count = len(slugs)
        lines = [f"{ts_fmt}  — {count} post{'s' if count != 1 else ''} added to translation exclusions:"]
        for s in slugs:
            lines.append(f"    • {s}")
        lines.append("    Sitemap and LLMs reference refreshed.")
        return "\n".join(lines)

    if kind == "no_change":
        return f"{ts_fmt}  — No changes."

    if kind == "sitemap_refreshed":
        return f"{ts_fmt}  — Sitemap refreshed."

    if kind == "llms_refreshed":
        return f"{ts_fmt}  — LLMs reference refreshed."

    if kind == "error":
        msg = detail.get("message", "unknown error")
        return f"{ts_fmt}  — Error: {msg}"

    return f"{ts_fmt}  — {kind}"


def render() -> str:
    state = load_state()
    events = state.get("events", [])
    now = now_san_diego()

    if events:
        last_check = fmt_sd(datetime.fromisoformat(events[0]["ts"]))
        latest_kind = events[0].get("kind", "")
        if latest_kind == "error":
            status_line = "Status:      Check required — see recent activity below."
        elif latest_kind == "weglot_update":
            status_line = "Status:      Content updated and synced."
        else:
            status_line = "Status:      All content in sync."
    else:
        last_check = fmt_sd(now)
        status_line = "Status:      All content in sync."

    lines = [
        "English College Content Sync",
        "============================",
        "",
        f"Last check:  {last_check} (San Diego time)",
        status_line,
        "",
        "Recent activity",
        "---------------",
    ]

    if events:
        for event in events:
            lines.append(_render_event(event))
    else:
        lines.append("No activity recorded yet.")

    lines += [
        "",
        "Public files",
        "------------",
        f"  {PUBLIC_SITEMAP_URL}",
        f"  {PUBLIC_LLMS_URL}",
        "",
        "Next check: within 15 minutes.",
    ]

    return "\n".join(lines)


def write_log() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(render())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Update log.txt with an event.")
    parser.add_argument(
        "--event",
        required=True,
        choices=sorted(VALID_EVENTS),
        help="Event kind to record.",
    )
    parser.add_argument(
        "--slugs",
        default="",
        help="Comma-separated slugs (required for weglot_update).",
    )
    parser.add_argument(
        "--error",
        default="",
        help="Error message (required for error event).",
    )
    args = parser.parse_args()

    if args.event == "weglot_update":
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
        detail: dict = {"slugs": slugs}
    elif args.event == "error":
        if not args.error:
            print("ERROR: --error message required for error event", file=sys.stderr)
            return 1
        detail = {"message": args.error}
    else:
        detail = {}

    append_event(args.event, detail)
    write_log()
    print(f"[update_log] Logged event: {args.event}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
