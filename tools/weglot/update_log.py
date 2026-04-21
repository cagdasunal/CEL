#!/usr/bin/env python3
"""
Append event to data/log-state.json — consumed by generate_status_page.py for log.html.

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
STATE_FILE = PROJECT_ROOT / "data" / "log-state.json"

MAX_RECENT_EVENTS = 10

VALID_EVENTS = {"weglot_update", "no_change", "sitemap_refreshed", "llms_refreshed", "error"}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_san_diego() -> datetime:
    return datetime.now(tz=SAN_DIEGO_TZ)


def _tz_abbr(dt: datetime) -> str:
    # On Ubuntu without tzdata, zoneinfo returns "UTC-07:00" instead of "PDT".
    # Resolve manually from UTC offset so the output is consistent across platforms.
    offset = dt.utcoffset()
    if offset is not None:
        secs = int(offset.total_seconds())
        if secs == -7 * 3600:
            return "PDT"
        if secs == -8 * 3600:
            return "PST"
    return dt.strftime("%Z")  # fallback for unexpected offsets


def fmt_sd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %I:%M %p ") + _tz_abbr(dt)


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
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Append event to data/log-state.json.")
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
    print(f"[update_log] Logged event: {args.event}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
