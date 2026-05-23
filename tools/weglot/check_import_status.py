#!/usr/bin/env python3
"""
Check whether each Weglot CSV has been imported into the live site.

For each of the 8 target locales:
  1. Read sentinel pairs from data/weglot-imports/<lang>.csv (longest, most
     distinctive multi-word source strings — see pick_sentinels()).
  2. GET https://www.englishcollege.com/<lang>/courses with the same UA +
     retry helper used by tools.weglot.api_sync.
  3. Substring-search each sentinel's word_to in the normalized response.
  4. Emit a verdict per language (imported / partial / pending /
     no_sentinels / no_csv / check_failed) into
     data/weglot-imports/import-status.json.

The dashboard (tools.weglot.generate_status_page) reads that JSON and
renders a colored badge per language alongside each CSV download link.

CLI:
  python3 -m tools.weglot.check_import_status \\
      [--csv-dir data/weglot-imports] \\
      [--out data/weglot-imports/import-status.json] \\
      [--check] [--only-locale CODE]

`--check` is dry-run: print summary, exit 0 only if every language is
"imported", exit 1 otherwise. Used by tests and CI smoke gates.
"""

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.weglot.api_sync import _http_request


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LANGUAGES = ("de", "fr", "es", "it", "ja", "ko", "pt", "ar")
SITE_BASE_URL = "https://www.englishcollege.com"
SCHEMA = "weglot.import-status.v1"
SAN_DIEGO_TZ = ZoneInfo("America/Los_Angeles")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_DIR = PROJECT_ROOT / "data" / "weglot-imports"
DEFAULT_OUT_FILE = DEFAULT_CSV_DIR / "import-status.json"

_WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------

def language_url(base: str, lang: str) -> str:
    """Return the live courses URL for a language."""
    return f"{base.rstrip('/')}/{lang}/courses"


def normalize_for_search(text: str) -> str:
    """HTML-unescape and collapse whitespace runs to single spaces.

    Lowercasing is NOT applied — translation case carries meaning.
    """
    if not text:
        return ""
    unescaped = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", unescaped)


def pick_sentinels(rows, n: int = 3):
    """Pick distinctive (word_from, word_to) pairs for live-page substring check.

    Rules (locked):
    - len(word_from) >= 25  (longer = lower MT-collision risk)
    - word_from != word_to  (skip identity rows)
    - word_from has >= 2 spaces  (multi-word — single tokens collide too easily)
    - word_to.strip() != ""  (defensive)
    - Sort: len(word_from) desc, then word_from asc (stable, deterministic)
    - Take first n
    """
    candidates = []
    for row in rows:
        word_from = (row.get("word_from") or "").strip()
        word_to = (row.get("word_to") or "").strip()
        if len(word_from) < 25:
            continue
        if word_from == word_to:
            continue
        if word_from.count(" ") < 2:
            continue
        if not word_to:
            continue
        candidates.append({"word_from": word_from, "word_to": word_to})
    candidates.sort(key=lambda r: (-len(r["word_from"]), r["word_from"]))
    return candidates[:n]


def verify_sentinels(body: str, sentinels) -> dict:
    """Check each sentinel's word_to for substring presence in the body.

    Returns:
      {
        "found":   [list of {word_from, word_to} that DID match],
        "missing": [list of {word_from, word_to} that did NOT match],
        "verdict": "imported" | "partial" | "pending" | "no_sentinels",
        "sentinels_total": int,
        "sentinels_found": int,
      }

    Verdict rules (matches plan §1 verdict table):
      - 0 total → "no_sentinels"
      - all found → "imported"
      - none found → "pending"
      - some found → "partial"
    """
    total = len(sentinels)
    if total == 0:
        return {
            "found": [],
            "missing": [],
            "verdict": "no_sentinels",
            "sentinels_total": 0,
            "sentinels_found": 0,
        }
    normalized_body = normalize_for_search(body)
    found = []
    missing = []
    for s in sentinels:
        target = normalize_for_search(s["word_to"])
        if target and target in normalized_body:
            found.append({"word_from": s["word_from"], "word_to": s["word_to"]})
        else:
            missing.append({"word_from": s["word_from"], "word_to": s["word_to"]})
    if not missing:
        verdict = "imported"
    elif not found:
        verdict = "pending"
    else:
        verdict = "partial"
    return {
        "found": found,
        "missing": missing,
        "verdict": verdict,
        "sentinels_total": total,
        "sentinels_found": len(found),
    }


def load_sentinel_pool(csv_dir: Path, lang: str) -> list | None:
    """Read <lang>.sentinels.json if present; return ordered candidate list.

    Returns None if missing/unparseable so caller can fall back to CSV-based
    pick_sentinels() for backwards compat with older builds without sidecar.
    """
    path = csv_dir / f"{lang}.sentinels.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return None
    cleaned = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        wf = (c.get("word_from") or "").strip()
        wt = (c.get("word_to") or "").strip()
        if wf and wt:
            cleaned.append({"word_from": wf, "word_to": wt})
    return cleaned


# ---------------------------------------------------------------------------
# Time / I/O helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(tz=SAN_DIEGO_TZ).isoformat()


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _read_csv(csv_path: Path):
    # Weglot CSVs are semicolon-delimited (per their example file).
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


# ---------------------------------------------------------------------------
# Per-language check
# ---------------------------------------------------------------------------

def check_language(lang: str, csv_dir: Path) -> dict:
    """Run the full check for one language; never raises."""
    url = language_url(SITE_BASE_URL, lang)
    csv_path = csv_dir / f"{lang}.csv"

    # CSV missing → no_csv
    if not csv_path.exists():
        return {
            "verdict": "no_csv",
            "url": url,
            "checked_at": now_iso(),
            "sentinels_total": 0,
            "sentinels_found": 0,
            "missing": [],
            "http_status": None,
        }

    pool = load_sentinel_pool(csv_dir, lang)
    if pool is not None:
        sentinels = pool[:3]
    else:
        # Backwards-compat: fall back to CSV-based selection when sidecar
        # hasn't been generated yet (older builds / first run before csv_export).
        rows = _read_csv(csv_path)
        sentinels = pick_sentinels(rows, n=3)

    # No usable sentinels → no_sentinels (don't bother fetching)
    if not sentinels:
        return {
            "verdict": "no_sentinels",
            "url": url,
            "checked_at": now_iso(),
            "sentinels_total": 0,
            "sentinels_found": 0,
            "missing": [],
            "http_status": None,
        }

    # Fetch live page; HTTP issues → check_failed (do not raise)
    http_status = None
    try:
        status, body = _http_request(url)
        http_status = status
        if status >= 400 or not isinstance(body, str):
            return {
                "verdict": "check_failed",
                "url": url,
                "checked_at": now_iso(),
                "sentinels_total": len(sentinels),
                "sentinels_found": 0,
                "missing": sentinels,
                "http_status": status,
            }
    except RuntimeError as e:
        print(f"[check_import_status] {lang}: HTTP failed: {e}", file=sys.stderr)
        return {
            "verdict": "check_failed",
            "url": url,
            "checked_at": now_iso(),
            "sentinels_total": len(sentinels),
            "sentinels_found": 0,
            "missing": sentinels,
            "http_status": None,
        }

    result = verify_sentinels(body, sentinels)
    return {
        "verdict": result["verdict"],
        "url": url,
        "checked_at": now_iso(),
        "sentinels_total": result["sentinels_total"],
        "sentinels_found": result["sentinels_found"],
        "missing": result["missing"],
        "http_status": http_status,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Weglot CSV import status against live site."
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help="Directory containing <lang>.csv files (default: data/weglot-imports/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_FILE,
        help="Output JSON path (default: data/weglot-imports/import-status.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: print summary, exit 0 if all imported, 1 otherwise. No file written.",
    )
    parser.add_argument(
        "--only-locale",
        metavar="CODE",
        help="Restrict to a single language code (testing aid).",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help=(
            "Stress test: fetch each live page, print per-sentinel FOUND/MISS "
            "with snippet context. Exits 0. Does NOT write the state file."
        ),
    )
    args = parser.parse_args(argv)

    target_langs = [args.only_locale] if args.only_locale else list(LANGUAGES)

    if args.diagnose:
        for lang in target_langs:
            url = language_url(SITE_BASE_URL, lang)
            csv_path = args.csv_dir / f"{lang}.csv"
            print(f"\n=== {lang} — {url} ===", flush=True)
            if not csv_path.exists():
                print(f"  [no CSV at {csv_path}]")
                continue
            pool = load_sentinel_pool(args.csv_dir, lang)
            if pool is None:
                rows = _read_csv(csv_path)
                sentinels = pick_sentinels(rows, n=3)
                print("  [sentinel source: CSV fallback]")
            else:
                sentinels = pool[:5]
                print(f"  [sentinel source: sidecar pool ({len(pool)} candidates total)]")
            try:
                status, body = _http_request(url)
            except RuntimeError as e:
                print(f"  HTTP FAILED: {e}")
                continue
            if not isinstance(body, str):
                print(f"  HTTP {status} non-text body")
                continue
            print(f"  HTTP {status}, body {len(body)} bytes")
            normalized_body = normalize_for_search(body)
            for s in sentinels:
                target = normalize_for_search(s["word_to"])
                if target and target in normalized_body:
                    idx = normalized_body.find(target)
                    snippet = normalized_body[max(0, idx - 40):idx + len(target) + 40]
                    print(f"  FOUND: {s['word_to'][:60]}")
                    print(f"    near: …{snippet[:140]}…")
                else:
                    print(f"  MISS:  {s['word_to'][:80]}")
                    print(f"    src:  {s['word_from'][:80]}")
        return 0

    state = {
        "schema": SCHEMA,
        "checked_at": now_iso(),
        "site_base_url": SITE_BASE_URL,
        "languages": {},
    }
    for lang in target_langs:
        result = check_language(lang, args.csv_dir)
        state["languages"][lang] = result
        print(
            f"[check_import_status] {lang}: {result['verdict']} "
            f"({result['sentinels_found']}/{result['sentinels_total']})",
            flush=True,
        )

    if args.check:
        verdicts = {c: i["verdict"] for c, i in state["languages"].items()}
        print(f"[check_import_status] verdicts: {verdicts}", flush=True)
        all_imported = all(v == "imported" for v in verdicts.values())
        return 0 if all_imported else 1

    _atomic_write_json(args.out, state)
    print(f"[check_import_status] wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
