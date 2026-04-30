"""Edit a single Offer item — set auto-extend-days field + publish.

Triggered by the offers-edit-item.yml workflow_dispatch from the admin
dashboard. Reads inputs from CLI args or env vars (workflow inputs become
INPUT_<NAME> env vars).

Usage:
  python3 -m tools.offers.edit_item --item-id <id> --days <n>
  ITEM_ID=<id> DAYS=<n> python3 -m tools.offers.edit_item

Behavior:
  1. PATCH the item's auto-extend-days field
  2. Publish the item so the live site sees no change
     (auto-extend-days isn't user-visible, but publishing keeps the
     item's lastPublished in sync with the latest field state).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.offers._log import append_event
from tools.offers._token_helper import APIError, NetworkError, api_request, get_api_token
from tools.offers.api import (
    OFFERS_COLLECTION_ID,
    WEBFLOW_API_BASE,
    publish_items,
)

LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "offers-edit-log.json"


def _patch_auto_extend(token: str, item_id: str, days: int) -> dict:
    url = f"{WEBFLOW_API_BASE}/collections/{OFFERS_COLLECTION_ID}/items/{item_id}"
    return api_request(
        "PATCH",
        url,
        token,
        data={"fieldData": {"auto-extend-days": days}},
    )


def _append_log(event: dict) -> None:
    """Append one event to LOG_FILE in JSONL format.

    Truncation (MAX_LOG_EVENTS cap) is no longer done here — workflows
    truncate via `tail -n 500` after every commit. Pure-append writes are
    conflict-free during git rebase, which prevents push races. See
    tracker 077 M1.
    """
    append_event(LOG_FILE, event)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Edit one Offer item's auto-extend-days field.")
    parser.add_argument("--item-id", default=os.environ.get("ITEM_ID") or os.environ.get("INPUT_ITEM_ID"))
    parser.add_argument("--days", default=os.environ.get("DAYS") or os.environ.get("INPUT_DAYS"))
    args = parser.parse_args(argv)

    if not args.item_id:
        print("[edit_item] ERROR: --item-id (or ITEM_ID env) required", file=sys.stderr)
        return 2
    if args.days is None or args.days == "":
        print("[edit_item] ERROR: --days (or DAYS env) required", file=sys.stderr)
        return 2

    try:
        days = int(args.days)
    except (TypeError, ValueError):
        print(f"[edit_item] ERROR: --days must be an integer, got {args.days!r}", file=sys.stderr)
        return 2

    if days < 0:
        print(f"[edit_item] ERROR: --days must be >= 0, got {days}", file=sys.stderr)
        return 2

    token = get_api_token()
    if not token:
        print("[edit_item] ERROR: WEBFLOW_API_TOKEN unset", file=sys.stderr)
        return 2

    item_id = args.item_id.strip()
    now = datetime.now(timezone.utc).isoformat()

    # PATCH
    try:
        _patch_auto_extend(token, item_id, days)
    except (APIError, NetworkError) as exc:
        print(f"[edit_item] ERROR PATCH {item_id}: {exc}", file=sys.stderr)
        _append_log({
            "ts": now,
            "kind": "edit_error",
            "item_id": item_id,
            "field": "auto-extend-days",
            "value": days,
            "error": str(exc),
        })
        return 1

    # Publish
    publish_errors: list = []
    try:
        pub_resp = publish_items(token, [item_id])
        publish_errors = pub_resp.get("errors") or []
    except (APIError, NetworkError) as exc:
        publish_errors = [{"id": item_id, "message": str(exc)}]

    _append_log({
        "ts": now,
        "kind": "edit_ok" if not publish_errors else "edit_partial",
        "item_id": item_id,
        "field": "auto-extend-days",
        "value": days,
        "publish_errors": publish_errors,
    })

    if publish_errors:
        print(f"[edit_item] PATCHED but publish had errors: {publish_errors}", file=sys.stderr)
        return 1

    print(f"[edit_item] OK item={item_id} auto-extend-days={days}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
