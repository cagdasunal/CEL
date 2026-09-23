#!/usr/bin/env python3
"""Apply a batch of reviewer decisions to the repo. Run by the save workflow.

Basecamp #451. Decisions are made in the reviewer's browser and, until this existed,
lived nowhere else — so an afternoon's work survived only as long as one browser
profile, and nothing downstream (reconciliation, the CSV builder, the batch) could read
them at all.

THE INPUT IS UNTRUSTED AND ARRIVES THROUGH THE ENVIRONMENT
-----------------------------------------------------------
The payload is translated website copy typed by a human. It must never be interpolated
into a shell command, so the workflow binds it with `env:` and this script reads
`os.environ` — never `${{ inputs.payload }}` inside a `run:` string, which is the
injection GitHub's own guidance warns about. It is additionally base64 of gzip of JSON,
so the value the Worker forwards cannot contain a shell metacharacter at all, and the
Worker's input schema rejects anything that is not base64.

Everything below validates rather than trusts: the locale must be one we know, the
JSON must decode to the exact shape expected, unknown keys are dropped, and any single
malformed entry fails the whole apply rather than being silently skipped. A partial
save that reports success is worse than a failed one.

MERGE, NEVER REPLACE
--------------------
The browser sends only what changed since its last successful save, and this merges
into what is already committed. Two consequences, both wanted: the payload stays small
(a typical save is a handful of rows, against ~40 KB for a whole locale — close enough
to the 65 KB workflow_dispatch ceiling to matter), and two people reviewing different
pages of the same locale do not overwrite each other. Per unit it is last-writer-wins,
which the history log makes traceable.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Beside units.json, because the desk has to READ this back and GitHub Pages only
# serves docs/. A first version wrote to data/localize/decisions/, which the browser
# could never have fetched -- the save would have worked and the desk would still have
# come up empty on another machine, which is the whole failure this is meant to fix.
# These files are as public as units.json already is: /admin/* is gated by auth.js in
# the browser, not at the file level (rules/dashboard-deploy.md), and the contents are
# website copy either way.
OUT_ROOT = REPO_ROOT / "docs" / "admin" / "localization"


def decisions_path(locale: str, out_root: Path | None = None) -> Path:
    return (out_root or OUT_ROOT) / locale / "decisions.json"

LOCALES = {"de", "fr", "es", "pt", "it", "ja", "ko", "ar"}
TRAYS = {"csv", "draft"}
# A decision is exactly these keys. Anything else is dropped rather than stored: the
# file is read by the CSV builder and the batch, and neither should meet a field that
# arrived because a future desk version sent it.
ALLOWED_KEYS = {"tray", "text", "rejected", "at", "by", "approvedAgainst",
                "sentAt", "arrivedAt", "failed", "exportedAt", "liveAt"}
MAX_TEXT = 8000          # a translation unit, generously. Guards against a paste bomb.
MAX_UNITS = 5000         # one locale has ~990; 5x that is a clear error, not a batch.


class Invalid(ValueError):
    """The payload is not something we are willing to write."""


def decode(payload_b64: str) -> dict:
    """base64(gzip(json)) -> dict, with every failure named."""
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Invalid(f"payload is not valid base64: {exc}") from exc
    try:
        text = gzip.decompress(raw)
    except (OSError, EOFError) as exc:
        raise Invalid(f"payload is not gzip: {exc}") from exc
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise Invalid(f"payload is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise Invalid("payload must be a JSON object")
    return doc


def clean_decision(uid: str, value: object) -> dict | None:
    """Validate one decision. None means 'delete this unit's decision'."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise Invalid(f"{uid}: decision must be an object or null")

    out: dict = {}
    tray = value.get("tray")
    if tray is not None:
        if tray not in TRAYS:
            raise Invalid(f"{uid}: tray must be one of {sorted(TRAYS)}, got {tray!r}")
        out["tray"] = tray

    text = value.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise Invalid(f"{uid}: text must be a string")
        if len(text) > MAX_TEXT:
            raise Invalid(f"{uid}: text is {len(text)} chars, over the {MAX_TEXT} limit")
        out["text"] = text

    rejected = value.get("rejected")
    if rejected is not None:
        if not isinstance(rejected, list) or not all(isinstance(r, str) for r in rejected):
            raise Invalid(f"{uid}: rejected must be a list of strings")
        # Only the last few matter to a re-draft; keeping every attempt forever would
        # grow this file without bound.
        out["rejected"] = [r[:MAX_TEXT] for r in rejected[-5:]]

    at = value.get("at")
    if at is not None:
        if not isinstance(at, str) or len(at) > 40:
            raise Invalid(f"{uid}: at must be a short ISO string")
        out["at"] = at

    # Who approved it, and what wording they were looking at. The second is what lets
    # the export refuse a row whose translation moved AFTER the approval -- otherwise
    # a later Weglot re-translation ships under a signature given to different text.
    by = value.get("by")
    if by is not None:
        if not isinstance(by, str) or len(by) > 200:
            raise Invalid(f"{uid}: by must be a short string")
        out["by"] = by

    against = value.get("approvedAgainst")
    if against is not None:
        if not isinstance(against, str):
            raise Invalid(f"{uid}: approvedAgainst must be a string")
        if len(against) > MAX_TEXT:
            raise Invalid(f"{uid}: approvedAgainst is over the {MAX_TEXT} limit")
        out["approvedAgainst"] = against

    # The lifecycle stamps. These used to be dropped here, so five of the desk's nine
    # stages -- sending, arrived, failed, exported, live -- never left the browser
    # that produced them. The one that matters most is `liveAt`: the exporter skips
    # rows already on the website, and it reads this file, so without it that
    # exclusion could never fire and an older wording would be re-imported over a
    # newer one.
    for stamp in ("sentAt", "arrivedAt", "exportedAt", "liveAt"):
        v = value.get(stamp)
        if v is not None:
            if not isinstance(v, str) or len(v) > 40:
                raise Invalid(f"{uid}: {stamp} must be a short ISO string")
            out[stamp] = v

    failed = value.get("failed")
    if failed is not None:
        if not isinstance(failed, str) or len(failed) > 400:
            raise Invalid(f"{uid}: failed must be a short string")
        out["failed"] = failed

    if not out:
        # An empty object is ambiguous -- it could mean "clear" or "nothing". Null is
        # how the desk says clear, so this is a bug in the sender.
        raise Invalid(f"{uid}: decision has no recognised fields")
    return out


def merge(existing: dict, delta: dict) -> tuple[dict, dict]:
    """Apply `delta` onto `existing`. Returns (merged, counts)."""
    merged = dict(existing)
    counts = {"set": 0, "cleared": 0, "unchanged": 0}
    for uid, value in delta.items():
        if not isinstance(uid, str) or not uid:
            raise Invalid(f"unit id must be a non-empty string, got {uid!r}")
        cleaned = clean_decision(uid, value)
        if cleaned is None:
            if merged.pop(uid, None) is not None:
                counts["cleared"] += 1
            continue
        if merged.get(uid) == cleaned:
            counts["unchanged"] += 1
            continue
        merged[uid] = cleaned
        counts["set"] += 1
    return merged, counts


def apply(locale: str, payload_b64: str, out_dir: Path | None = None) -> dict:
    if locale not in LOCALES:
        raise Invalid(f"unknown locale {locale!r}")
    doc = decode(payload_b64)

    if doc.get("schema") != "cel-localization-desk/1":
        raise Invalid(f"unexpected schema {doc.get('schema')!r}")
    if doc.get("locale") != locale:
        # The locale is asserted twice on purpose: once by the caller (which the Worker
        # schema constrains) and once inside the signed-for payload. A mismatch means
        # the two disagree about what is being written, which is never benign.
        raise Invalid(f"payload is for {doc.get('locale')!r}, dispatch said {locale!r}")

    delta = doc.get("decisions")
    if not isinstance(delta, dict):
        raise Invalid("decisions must be an object")
    if len(delta) > MAX_UNITS:
        raise Invalid(f"{len(delta)} units in one save, over the {MAX_UNITS} limit")

    target = decisions_path(locale, out_dir)
    existing = {}
    if target.is_file():
        try:
            prev = json.loads(target.read_text(encoding="utf-8"))
            existing = prev.get("decisions", {}) if isinstance(prev, dict) else {}
        except ValueError:
            # A corrupt file is not a reason to throw away this save, but it IS a
            # reason to say so loudly rather than quietly starting from empty.
            print(f"WARNING: {target} was unreadable; starting from an empty set",
                  file=sys.stderr)

    merged, counts = merge(existing, delta)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"schema": "cel-localization-desk/1", "locale": locale,
                    "decisions": merged},
                   ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"locale": locale, "total": len(merged), **counts}


def main() -> int:
    locale = os.environ.get("LOCALE", "").strip()
    payload = os.environ.get("PAYLOAD", "").strip()
    if not locale or not payload:
        print("ERROR: LOCALE and PAYLOAD must both be set in the environment",
              file=sys.stderr)
        return 2
    try:
        result = apply(locale, payload)
    except Invalid as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
