"""After GitHub Pages deploys a push: is the desk it serves the desk that was pushed?

    cd tools && python3 -m localize_desk.live_check --sha <commit> --repo <url>   # desk-live-check.yml

Monorepo runbook WO-33 (review round 2, lens L6): nothing checked the live desk after a
push. A Pages build that failed, a stale CDN copy or a file left out of the commit all
leave the reviewers on yesterday's desk -- or on a page whose script and data disagree --
while every test is green. This reads each served file twice and compares its bytes with
the checked-out file:
- past the edge, with the commit id as a cache-busting query, so a failed or partial
  deploy shows even while the CDN still holds a copy;
- at every URL a reviewer's browser asks for (`/de/`, and each `/de/?show=...` the desk
  links to), asking for gzip as a browser does -- each is its own cache key, and a stale
  copy there is what reviewers get (#5 review, 2026-09-28).
The files are the pages, their data, and every same-origin script and stylesheet the pages
load. Pages takes a minute or two after the deploy status and the CDN keeps a copy for up to
`max-age=600`, so a mismatch is retried for longer than that before it counts.

A check still running when a newer push deploys would compare the old commit with the new
files: when `--repo` shows main has moved on, the newer deploy's own check covers the desk,
and this one hands over instead of going red.

Exit 0: every file matches (or a newer push took over). Exit 1: the files that did not.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
BASE = "https://cel.englishcollege.com"
LOCALES = ("de", "fr", "es", "pt", "it", "ja", "ko", "ar")
_PAGES = ["admin/localization/index.html"] + [f"admin/localization/{c}/index.html" for c in LOCALES]
_ASSET = re.compile(r'(?:src|href)="/([^"?#]+[.](?:js|css))"')
_LINK = re.compile(r'href="/([^"#]+)"')


def served_files(docs: Path = DOCS) -> list[str]:
    """The desk's pages and data, and every same-origin script and stylesheet they load."""
    paths = _PAGES + [f"admin/localization/{c}/units.json" for c in LOCALES]
    for page in (docs / p for p in _PAGES if (docs / p).is_file()):
        paths += _ASSET.findall(page.read_text(encoding="utf-8"))
    return sorted({p for p in paths if (docs / p).is_file()})


def _plain(p: str) -> str:
    """The URL path a browser asks for: `/de/`, not `/de/index.html`."""
    return p[: -len("index.html")] if p.endswith("index.html") else p


def reviewer_urls(docs: Path = DOCS) -> dict[str, list[str]]:
    """Each served file -> the URL paths a reviewer's browser reads it through: its plain path,
    and every link in the desk's pages to that path with a query (`de/?show=check`)."""
    links: set[str] = set()
    for page in (docs / p for p in _PAGES if (docs / p).is_file()):
        links.update(_LINK.findall(page.read_text(encoding="utf-8")))
    out = {}
    for p in served_files(docs):
        plain = _plain(p)
        out[p] = [plain] + sorted(u for u in links if "?" in u and u.split("?", 1)[0] == plain)
    return out


def _fetch(url: str, timeout: float = 30.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "cel-desk-live-check/1",
                                               "Accept-Encoding": "gzip"})   # a browser's variant
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return gzip.decompress(body) if r.headers.get("Content-Encoding") == "gzip" else body
    except (urllib.error.URLError, TimeoutError, OSError, EOFError, gzip.BadGzipFile):
        return None


def _serves(url: str, digest: str) -> bool:
    body = _fetch(url)
    return body is not None and hashlib.sha256(body).hexdigest() == digest


def check(sha: str, *, base: str = BASE, docs: Path = DOCS, tries: int = 24,
          pause: float = 30.0) -> list[str]:
    """The served paths that still differ from the checkout after `tries` rounds."""
    want = {p: hashlib.sha256((docs / p).read_bytes()).hexdigest() for p in served_files(docs)}
    urls = reviewer_urls(docs)
    root = base.rstrip("/")
    left = sorted(want)
    for attempt in range(1, max(1, tries) + 1):
        still = []
        for p in left:
            reads = [f"{root}/{p}?v={sha}"] + [f"{root}/{u}" for u in urls[p]]
            if not all(_serves(u, want[p]) for u in reads):
                still.append(p)
        left = still
        if not left or attempt == tries:
            break
        time.sleep(pause)
    return left


def _main_head(repo: str) -> str | None:
    """main's commit on the remote now, or None when it cannot be read."""
    try:
        out = subprocess.run(["git", "ls-remote", repo, "refs/heads/main"], capture_output=True,
                             text=True, timeout=60, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[0] if out and re.fullmatch(r"[0-9a-f]{40}", out[0]) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sha", required=True, help="the pushed commit (the cache-busting query)")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--tries", type=int, default=24)      # 24 x 30 s: longer than max-age=600
    ap.add_argument("--pause", type=float, default=30.0)
    ap.add_argument("--repo", help="the repository's URL: a mismatch after main moved on hands over")
    args = ap.parse_args(argv)
    files = served_files(DOCS)
    if not files:
        print("LIVE CHECK: no desk files in this checkout -- nothing to compare", file=sys.stderr)
        return 1
    bad = check(args.sha, base=args.base, docs=DOCS, tries=args.tries, pause=args.pause)
    if not bad:
        print(f"LIVE CHECK: all {len(files)} served desk files match {args.sha[:8]}")
        return 0
    head = _main_head(args.repo) if args.repo else None
    if head and not head.startswith(args.sha) and not args.sha.startswith(head):
        print(f"LIVE CHECK: {len(bad)} of {len(files)} files differ from {args.sha[:8]}, but main "
              f"is now {head[:8]}: that push's deploy is checked by its own run")
        return 0
    print(f"LIVE CHECK: {len(bad)} of {len(files)} served files differ from {args.sha[:8]}:",
          file=sys.stderr)
    for p in bad:
        print(f"  {args.base.rstrip('/')}/{p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
