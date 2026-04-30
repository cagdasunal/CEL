"""Shared log-event utility for offers workflows.

Writes are JSONL: one JSON object per line. Append-only writes are
conflict-free during git rebase, which prevents push races when multiple
workflow runs write to the same log file in parallel (tracker 077, M1).

Reads are backward-compatible: handles both JSONL (preferred) and the
legacy JSON-object format (`{"events": [...]}`). Existing data files are
migrated lazily by the writers — once a JSONL append happens against a
legacy file, the next read will still work because `read_events()`
detects the format from content. A one-shot migration script lives at
`tools/offers/migrate_log_to_jsonl.py`.

Truncation is NOT done here — workflows truncate via `tail -n 500` after
every commit, which is race-free (cron-style). See
`.github/workflows/offers-edit-item.yml` "Truncate log" step.

Module-level: side-effect-free (rules/quality.md §12). No I/O at import.
"""
from __future__ import annotations

import json
from pathlib import Path


def append_event(path: Path, event: dict) -> None:
    """Append one event as a single JSONL line.

    Pure-append writes are conflict-free during git rebase: every parallel
    runner adds a distinct new line. The 3-way merge sees no overlapping
    edits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_events(path: Path) -> list[dict]:
    """Read all events from a log file. Backward-compatible.

    Detects format by content:
    - JSONL: each non-empty line is a JSON object
    - Legacy JSON-object: `{"events": [...]}` produced by the pre-tracker-077
      `_append_log()` writers. Detected by leading `{` followed by `"events"`
      somewhere in the first 200 bytes.

    Bad lines (corrupt JSON in JSONL, parse failure on legacy) are skipped
    silently — log readers are best-effort, never fatal.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    stripped = text.lstrip()
    # Legacy detection: JSON-object with "events" key in the prologue
    if stripped.startswith("{") and '"events"' in stripped[:200]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        events = data.get("events") if isinstance(data, dict) else None
        return list(events) if isinstance(events, list) else []
    # JSONL
    out: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
