"""Auto-extend offer end-dates that would otherwise expire within 24h.

Cron entry point. Reads Offers CMS, computes which items need extension,
PATCHes end-date, then publishes the patched items so the live site
sees the new date without a manual Webflow Publish.

Usage:
  python3 -m tools.offers.auto_extend --dry-run     # report only
  python3 -m tools.offers.auto_extend               # PATCH + publish
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.offers._token_helper import APIError, NetworkError, get_api_token
from tools.offers.api import list_all_offers, patch_end_date, publish_items

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXTEND_DAYS = 14
DEFAULT_THRESHOLD_HOURS = 24
LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "offers-extend-log.json"
MAX_LOG_EVENTS = 200


# ---------------------------------------------------------------------------
# Core logic (pure, testable)
# ---------------------------------------------------------------------------

def _should_extend(
    item: dict,
    now_utc: datetime,
    threshold_hours: int,
) -> tuple[bool, str | None, int]:
    """Decide whether an item should be extended.

    Returns (should_extend, new_end_iso_or_None, extend_days).
    """
    if item.get("isArchived") or item.get("isDraft"):
        return False, None, DEFAULT_EXTEND_DAYS

    fd = item.get("fieldData") or {}
    end_raw = fd.get("end-date")
    if not end_raw:
        return False, None, DEFAULT_EXTEND_DAYS

    # Read auto-extend-days field
    raw_extend = fd.get("auto-extend-days")
    if raw_extend is None:
        extend_days = DEFAULT_EXTEND_DAYS
    else:
        try:
            extend_days = int(raw_extend)
        except (TypeError, ValueError):
            print(
                f"[auto_extend] WARN: skipping {item.get('id')}: "
                f"bad auto-extend-days value {raw_extend!r}",
                file=sys.stderr,
            )
            extend_days = DEFAULT_EXTEND_DAYS

    if extend_days == 0:
        return False, None, 0

    # Parse end-date
    try:
        end_date = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        print(
            f"[auto_extend] WARN: skipping {item.get('id')}: "
            f"bad end-date {end_raw!r}",
            file=sys.stderr,
        )
        return False, None, extend_days

    # Mirror cel-offers.js endOf('day') UTC semantics
    effective_end = end_date.replace(hour=23, minute=59, second=59, microsecond=999000)

    remaining = (effective_end - now_utc).total_seconds()
    if remaining > threshold_hours * 3600:
        return False, None, extend_days

    # Compute new end-date
    new_date = end_date + timedelta(days=extend_days)
    new_end_iso = new_date.strftime("%Y-%m-%dT00:00:00.000Z")
    return True, new_end_iso, extend_days


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _append_log(log_path: Path, event: dict) -> None:
    """Load existing log, append event, cap at MAX_LOG_EVENTS, write back."""
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {"events": []}
    else:
        existing = {"events": []}

    events = existing.get("events", [])
    events.append(event)
    # Cap oldest first
    if len(events) > MAX_LOG_EVENTS:
        events = events[-MAX_LOG_EVENTS:]
    existing["events"] = events

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-extend Offer end-dates approaching expiry.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report items that would be extended without patching.",
    )
    parser.add_argument(
        "--threshold-hours",
        type=int,
        default=DEFAULT_THRESHOLD_HOURS,
        metavar="N",
        help=f"Extend items whose end-date is within N hours (default {DEFAULT_THRESHOLD_HOURS}).",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        metavar="PATH",
        help="Override the default log file path (for tests).",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log_path) if args.log_path else LOG_FILE

    token = get_api_token()
    if not token:
        print("[auto_extend] WEBFLOW_API_TOKEN unset", file=sys.stderr)
        return 2

    # Fetch all offers
    try:
        items = list_all_offers(token)
    except (APIError, NetworkError) as exc:
        print(f"[auto_extend] ERROR fetching offers: {exc}", file=sys.stderr)
        _append_log(log_path, {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "error",
            "patched": [],
            "errors": [{"id": "fetch", "message": str(exc)}],
            "publish_errors": [],
        })
        return 1

    now_utc = datetime.now(timezone.utc)
    scheduled: list[tuple[dict, str, int]] = []

    for item in items:
        should, new_end, extend_days = _should_extend(item, now_utc, args.threshold_hours)
        if should and new_end:
            scheduled.append((item, new_end, extend_days))

    print(f"PLAN: {len(scheduled)} items")

    if args.dry_run:
        for item, new_end, extend_days in scheduled:
            fd = item.get("fieldData") or {}
            title = fd.get("internal-title") or fd.get("name") or item.get("id")
            old_end = fd.get("end-date", "")
            print(f"  {item['id']} | {title} | {old_end} → {new_end} | +{extend_days} days")
        return 0

    # Patch each scheduled item
    patched: list[dict] = []
    errors: list[dict] = []

    for item, new_end, extend_days in scheduled:
        item_id = item["id"]
        fd = item.get("fieldData") or {}
        title = fd.get("internal-title") or fd.get("name") or item_id
        old_end = fd.get("end-date", "")
        try:
            patch_end_date(token, item_id, new_end)
            patched.append({
                "id": item_id,
                "internal_title": title,
                "old_end": old_end,
                "new_end": new_end,
                "extend_days": extend_days,
            })
        except APIError as exc:
            print(
                f"[auto_extend] ERROR patching {item_id}: {exc}",
                file=sys.stderr,
            )
            errors.append({"id": item_id, "message": str(exc)})
            # Abort immediately on OAuth scope error — retrying remaining items
            # would produce the same 403 and needlessly inflate the error count.
            if exc.status_code == 403 and "missing_scopes" in exc.body:
                print(
                    "[auto_extend] ABORT: WEBFLOW_API_TOKEN lacks 'cms:write' scope. "
                    "Regenerate the token in Webflow → Account → API Access with "
                    "'CMS: Read & Write' enabled, then update the WEBFLOW_API_TOKEN "
                    "secret in the GitHub repo settings.",
                    file=sys.stderr,
                )
                break
        except NetworkError as exc:
            print(
                f"[auto_extend] ERROR patching {item_id}: {exc}",
                file=sys.stderr,
            )
            errors.append({"id": item_id, "message": str(exc)})

    # Publish successfully patched items
    publish_errors: list[dict] = []
    if patched:
        patched_ids = [p["id"] for p in patched]
        try:
            pub_resp = publish_items(token, patched_ids)
            pub_errs = pub_resp.get("errors") or []
            if pub_errs:
                publish_errors.extend(
                    {"id": str(e), "message": str(e)} for e in pub_errs
                )
        except (APIError, NetworkError) as exc:
            print(
                f"[auto_extend] ERROR publishing: {exc}",
                file=sys.stderr,
            )
            publish_errors.append({"id": "publish", "message": str(exc)})

    # Log event
    kind = "extend_run" if (patched or errors) else "no_change"
    _append_log(log_path, {
        "ts": now_utc.isoformat(),
        "kind": kind,
        "patched": patched,
        "errors": errors,
        "publish_errors": publish_errors,
    })

    n_patched = len(patched)
    n_errors = len(errors)
    n_pub = len(patched) - len(publish_errors)
    n_pub_err = len(publish_errors)
    print(
        f"[auto_extend] {n_patched} items patched, {n_errors} errors, "
        f"{n_pub} published, {n_pub_err} publish_errors"
    )

    return 1 if (n_errors > 0 or n_pub_err > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
