"""Edit one geotargetly region's countries CSV — Settings tab editor backend.

Triggered by offers-edit-regions.yml workflow_dispatch from the dashboard
Settings tab. Writes to:
  data/cel-offers-regions.json     — staging file in CEL repo (workflow runner)
  docs/scripts/cel-offers-regions.json  — served file (same content, mirror)

The cel-offers.js bundle reads /scripts/cel-offers-regions.json at boot
(with the hardcoded CONFIG as fallback). Once a region is saved, future
page loads on the live offer pages pick up the new countries list.

Usage:
  python3 -m tools.offers.edit_regions --region <key> --countries <CSV>
  REGION=<key> COUNTRIES=<CSV> python3 -m tools.offers.edit_regions
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VALID_REGIONS = {"offers", "sandiego", "losangeles", "vancouver", "usa", "canada"}
VALID_CSV_RE = re.compile(r"^[A-Z]{2}(,[A-Z]{2})*$")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = REPO_ROOT / "data" / "cel-offers-regions.json"
PUBLIC_FILE = REPO_ROOT / "docs" / "scripts" / "cel-offers-regions.json"
LOG_FILE = REPO_ROOT / "data" / "offers-edit-log.json"
MAX_LOG_EVENTS = 500


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _append_log(event: dict) -> None:
    existing = _load(LOG_FILE)
    if not isinstance(existing, dict):
        existing = {}
    events = existing.get("events", [])
    events.append(event)
    if len(events) > MAX_LOG_EVENTS:
        events = events[-MAX_LOG_EVENTS:]
    existing["events"] = events
    _save(LOG_FILE, existing)


def main(argv: list[str] | None = None) -> int:
    global LOG_FILE
    parser = argparse.ArgumentParser(description="Edit one geotargetly region's countries CSV.")
    parser.add_argument("--region", default=os.environ.get("REGION") or os.environ.get("INPUT_REGION"))
    parser.add_argument("--countries", default=os.environ.get("COUNTRIES") or os.environ.get("INPUT_COUNTRIES"))
    parser.add_argument("--data-file", default=None, help="Override default data file path (for tests).")
    parser.add_argument("--public-file", default=None, help="Override default public file path (for tests).")
    parser.add_argument("--log-file", default=None, help="Override default log file path (for tests).")
    args = parser.parse_args(argv)

    if not args.region:
        print("[edit_regions] ERROR: --region required", file=sys.stderr)
        return 2
    region = args.region.strip()
    if region not in VALID_REGIONS:
        print(f"[edit_regions] ERROR: invalid region {region!r}; valid: {sorted(VALID_REGIONS)}", file=sys.stderr)
        return 2

    if not args.countries:
        print("[edit_regions] ERROR: --countries required", file=sys.stderr)
        return 2
    countries = (args.countries or "").strip().upper().replace(" ", "")
    if not VALID_CSV_RE.match(countries):
        print(f"[edit_regions] ERROR: invalid countries CSV; must match ^[A-Z]{{2}}(,[A-Z]{{2}})*$", file=sys.stderr)
        return 2

    data_file = Path(args.data_file) if args.data_file else DATA_FILE
    public_file = Path(args.public_file) if args.public_file else PUBLIC_FILE
    log_file = Path(args.log_file) if args.log_file else LOG_FILE

    # Load + mutate (preserve other regions, preserve unknown top-level keys)
    state = _load(data_file)
    if not isinstance(state, dict):
        state = {}
    regions = state.get("regions") or {}
    if not isinstance(regions, dict):
        regions = {}
    prev = (regions.get(region) or {}).get("countries", "")
    regions[region] = {"countries": countries, "action": (regions.get(region) or {}).get("action", "show")}
    state["regions"] = regions
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save(data_file, state)
    if public_file != data_file:
        _save(public_file, state)

    # Log the change (override LOG_FILE so test can verify)
    LOG_FILE = log_file
    _append_log({
        "ts": state["updated_at"],
        "kind": "region_edit",
        "region": region,
        "countries": countries,
        "previous": prev,
    })

    print(f"[edit_regions] OK region={region} countries={len(countries.split(','))} ISO codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
