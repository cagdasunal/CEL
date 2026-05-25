"""tracker-114 poison gate — fail if any per-locale Weglot CSV has a source<->target
mis-pairing.

Run before importing CSVs into Weglot (and in CI after CSV generation). Uses the canonical
detector (`tools.weglot.csv_engine.detect_poison_rows`) with the Fidelo on-page-label
allowlist (`data/weglot/fidelo-word-from.json`) so legitimate short labels (e.g. "Sleeping
pods") are not flagged. Exit 0 = clean, 2 = poison found. Import-safe (no module-level I/O).

The 2026-05-25 incident: an ad-hoc text-node regeneration mis-zipped source nodes with
their translations, so short source strings mapped to long unrelated targets; imported into
Weglot, each overwrites every occurrence of that string site-wide and broke all non-English
pages. The block-level pipeline cannot produce these; this gate blocks any CSV that did.
See rules/weglot-csv-integrity.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CSV_DIR = _REPO / "docs" / "admin" / "weglot-imports"
_DEFAULT_ALLOWLIST = _REPO / "data" / "weglot" / "fidelo-word-from.json"


def _load_allowlist(path: Path) -> set[str]:
    """Fidelo word_from allowlist (poison-gate exemption set). {} if absent/unreadable."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {w for w in data.get("word_from", []) if isinstance(w, str)}
    except (json.JSONDecodeError, OSError):
        return set()


def scan(csv_dir: Path, allowlist: set[str]) -> dict:
    """Scan every per-locale <lang>.csv for poison rows. Returns {by_file, total}."""
    from tools.weglot.csv_engine import detect_poison_rows, read_existing_csv

    by_file: dict[str, int] = {}
    total = 0
    csv_dir = Path(csv_dir)
    if csv_dir.is_dir():
        for csvp in sorted(csv_dir.glob("*.csv")):
            if csvp.name == "all-languages.csv":
                continue
            poison = detect_poison_rows(read_existing_csv(csvp), fidelo_word_from=allowlist or None)
            if poison:
                by_file[csvp.name] = len(poison)
                total += len(poison)
    return {"by_file": by_file, "total": total}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dir", type=Path, default=_DEFAULT_CSV_DIR,
                   help=f"per-locale Weglot CSV dir (default: {_DEFAULT_CSV_DIR})")
    p.add_argument("--allowlist", type=Path, default=_DEFAULT_ALLOWLIST,
                   help="Fidelo word_from allowlist JSON (exemption set)")
    args = p.parse_args(argv)

    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    rep = scan(args.dir, _load_allowlist(args.allowlist))
    if rep["total"]:
        per = ", ".join(f"{k}:{v}" for k, v in rep["by_file"].items())
        print(
            f"POISON GATE FAILED: {rep['total']} source<->target mis-paired row(s) ({per}). "
            "Do NOT import — regenerate via the block-level pipeline. See rules/weglot-csv-integrity.md.",
            file=sys.stderr,
        )
        return 2
    print("poison gate: clean (0 mis-paired rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
