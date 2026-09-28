"""After GitHub Pages deploys a push: is the desk it serves the desk that was pushed?

    cd tools && python3 -m localize_desk.live_check --sha <commit>      # desk-live-check.yml

Monorepo runbook WO-33 (review round 2, lens L6): nothing checked the live desk after a
push. A Pages build that failed, a stale CDN copy or a file left out of the commit all
leave the reviewers on yesterday's desk -- or on a page whose script and data disagree --
while every test is green. This fetches each served file with a cache-busting query (the
commit id, so the CDN cannot answer with an older copy) and compares its bytes with the
checked-out file. Pages takes a minute or two after the deploy status, so a mismatch is
retried before it counts.

Exit 0: every file matches. Exit 1: the files that did not, after the retries.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
BASE = "https://cel.englishcollege.com"
LOCALES = ("de", "fr", "es", "pt", "it", "ja", "ko", "ar")


def served_files(docs: Path = DOCS) -> list[str]:
    """The desk's pages and data, and the two stylesheets they load, as served paths."""
    paths = ["admin/localization/index.html", "assets/css/dashboard.css", "scripts/cel-arabic.css"]
    for code in LOCALES:
        paths += [f"admin/localization/{code}/index.html", f"admin/localization/{code}/units.json"]
    return [p for p in paths if (docs / p).is_file()]


def _fetch(url: str, timeout: float = 30.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "cel-desk-live-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def check(sha: str, *, base: str = BASE, docs: Path = DOCS, tries: int = 10,
          pause: float = 30.0) -> list[str]:
    """The served paths that still differ from the checkout after `tries` rounds."""
    want = {p: hashlib.sha256((docs / p).read_bytes()).hexdigest() for p in served_files(docs)}
    left = sorted(want)
    for attempt in range(1, max(1, tries) + 1):
        still = []
        for p in left:
            got = _fetch(f"{base.rstrip('/')}/{p}?v={sha}")
            if got is None or hashlib.sha256(got).hexdigest() != want[p]:
                still.append(p)
        left = still
        if not left or attempt == tries:
            break
        time.sleep(pause)
    return left


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sha", required=True, help="the pushed commit (the cache-busting query)")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--tries", type=int, default=10)
    ap.add_argument("--pause", type=float, default=30.0)
    args = ap.parse_args(argv)
    files = served_files()
    if not files:
        print("LIVE CHECK: no desk files in this checkout -- nothing to compare", file=sys.stderr)
        return 1
    bad = check(args.sha, base=args.base, tries=args.tries, pause=args.pause)
    if bad:
        print(f"LIVE CHECK: {len(bad)} of {len(files)} served files differ from {args.sha[:8]}:",
              file=sys.stderr)
        for p in bad:
            print(f"  {args.base.rstrip('/')}/{p}", file=sys.stderr)
        return 1
    print(f"LIVE CHECK: all {len(files)} served desk files match {args.sha[:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
