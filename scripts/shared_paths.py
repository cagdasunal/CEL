#!/usr/bin/env python3
"""Shared path constants used across multiple scripts.

Centralizes paths that were previously duplicated in design_learner.py
and system_inspector.py to prevent drift.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# PAGES_ROOT resolves to the repo root by default (parent of scripts/).
# The 2026-04-14 feedback pipeline audit flagged the previous behavior
# as "audit hostile" because there was no way to point scripts at a
# sandbox copy of the repo without modifying source. The WFO_PAGES_ROOT
# env var now provides that escape hatch: set it to an absolute path and
# every script that imports PAGES_ROOT will use the sandbox root instead.
# Empty or unset means "default to the real repo root", preserving the
# original behavior for normal runs.
_env_root = os.environ.get("WFO_PAGES_ROOT", "").strip()
if _env_root:
    PAGES_ROOT = Path(_env_root).resolve()
else:
    PAGES_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PAGES_ROOT / ".claude" / "improvement-data"
MEMORY_FILE = PAGES_ROOT / ".claude" / "memory" / "MEMORY.md"
LEARNED_RULES_FILE = DATA_DIR / "learned-rules.json"
EVENTS_FILE = DATA_DIR / "events.jsonl"
SESSIONS_FILE = DATA_DIR / "sessions.json"
CHECK_HISTORY_FILE = DATA_DIR / "check-history.json"

# Active data files (produced and consumed by multiple scripts)
GOLDEN_PATTERNS_FILE = DATA_DIR / "golden-patterns.json"
DESIGN_LEARNING_FILE = DATA_DIR / "design-learning.json"
DESIGN_VARIANTS_FILE = DATA_DIR / "design-variants.json"
DESIGN_REFERENCES_FILE = DATA_DIR / "design-references.json"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"
METRICS_FILE = DATA_DIR / "metrics.json"
PATTERNS_FILE = DATA_DIR / "patterns.json"
SESSION_CHECKLIST_FILE = DATA_DIR / "session-checklist.json"
INSPECTOR_BASELINES_FILE = DATA_DIR / "inspector-baselines.json"
LEARNED_RULES_ARCHIVE_FILE = DATA_DIR / "learned-rules-archive.json"
INSPIRATION_HISTORY_FILE = DATA_DIR / "inspiration-history.json"

# Infrastructure data files
HEARTBEAT_FILE = DATA_DIR / "heartbeat.json"
MCP_KEEPALIVE_FILE = DATA_DIR / "mcp-keepalive.json"
MCP_ERROR_PATTERNS_FILE = DATA_DIR / "mcp-error-patterns.json"

# Deprecated/phantom feature files (kept for backward compat, never created in practice)
DEPTH_CONFIG_FILE = DATA_DIR / "depth-config.json"
CONSENSUS_DATA_FILE = DATA_DIR / "consensus-history.json"
PREDICTOR_MODEL_FILE = DATA_DIR / "predictor-model.json"
TEST_HISTORY_FILE = DATA_DIR / "test-history.json"

# Staleness cascade thresholds (hours)
# watchdog shows STALE → inspector warns → hook_checker alerts
HEARTBEAT_STALE_DISPLAY = 24   # watchdog --status display
HEARTBEAT_STALE_WARNING = 48   # inspector check_watchdog_heartbeat
HEARTBEAT_STALE_ALERT = 72     # hook_checker PostToolUse warning


def safe_load_json(path, default=None):
    """Load JSON file with error handling. Returns default on missing/corrupt file."""
    path = Path(path)
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default if default is not None else {}


def safe_load_jsonl(path):
    """Load JSONL file with per-line error handling. Skips corrupt lines."""
    path = Path(path)
    if not path.exists():
        return []
    results = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return results


def utc_now_iso() -> str:
    """Return current UTC time as ISO string. Use this everywhere for consistent timestamps."""
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Show shared path constants used across scripts."
    )
    parser.parse_args()

    paths = {k: str(v) for k, v in sorted(globals().items())
             if k.isupper() and isinstance(v, (Path, int, str)) and not k.startswith("_")}
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
