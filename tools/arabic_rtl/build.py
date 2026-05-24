"""Arabic RTL CSS engine.

Fetches the live Webflow CSS used on /ar/ pages, mirrors it with rtlcss, and writes
a scoped diff+reset override to docs/scripts/cel-arabic.css.

Change detection: the source-CSS fingerprint is stored in the output file's header
comment, so a run regenerates ONLY when the Webflow CSS actually changed — no
separate state file. Pure stdlib (urllib + xml.etree + regex); rtlcss runs via npx.

Run from the repo root:
    python -m tools.arabic_rtl.build            # regenerate iff source CSS changed
    python -m tools.arabic_rtl.build --force    # always regenerate
    python -m tools.arabic_rtl.build --check     # report only; exit 1 if change detected
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from tools.arabic_rtl import generator

SITEMAP_URL = "https://cel.englishcollege.com/sitemap.xml"
WEBFLOW_CDN = "cdn.prod.website-files.com"
_REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = _REPO_ROOT / "docs" / "scripts" / "cel-arabic.css"
STATIC_PATH = Path(__file__).resolve().parent / "arabic_static.css"

_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# Browser UA — the /ar/ pages sit behind Weglot O2O / Cloudflare, which 1010-blocks
# non-browser user agents.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_FP_RE = re.compile(r"source-fp:([0-9a-f]{64})")
_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)


def fetch(url: str, tries: int = 3, timeout: float = 30.0) -> str:
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data.decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 — retry any transient fetch error
            last = e
            if k < tries - 1:
                time.sleep(2 * (k + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}: {last}")


def get_ar_urls(sitemap_xml: str) -> list[str]:
    root = ET.fromstring(sitemap_xml)
    locs = [e.text.strip() for e in root.iter(_SITEMAP_NS + "loc") if e.text]
    if not locs:
        locs = [e.text.strip() for e in root.iter("loc") if e.text]
    ar = [u for u in locs if "/ar/" in u or u.rstrip("/").endswith("/ar")]
    return sorted(set(ar))


def extract_css_urls(html: str) -> list[str]:
    out = []
    for tag in _LINK_RE.findall(html):
        if "stylesheet" not in tag.lower():
            continue
        m = _HREF_RE.search(tag)
        if m and WEBFLOW_CDN in m.group(1) and ".css" in m.group(1):
            out.append(m.group(1))
    return out


def fingerprint(urls) -> str:
    return hashlib.sha256("\n".join(sorted(urls)).encode("utf-8")).hexdigest()


def read_prior_fp(path: Path):
    if not path.exists():
        return None
    m = _FP_RE.search(path.read_text(encoding="utf-8")[:400])
    return m.group(1) if m else None


def dedupe_rules(css_text: str) -> str:
    """Collapse byte-identical top-level rules (prelude+body), preserving first
    occurrence + order. Per-page CSS repeats the same shared component rules across
    every page's opt file; removing exact duplicates is cascade-safe (a rule
    repeated verbatim is a no-op) and shrinks the override dramatically."""
    seen = set()
    out = []
    for prelude, body in generator.split_top(css_text):
        key = (prelude, body)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{prelude};" if body is None else f"{prelude}{{{body}}}")
    return "".join(out)


def run_rtlcss(src_text: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        ip, op = os.path.join(d, "in.css"), os.path.join(d, "out.css")
        Path(ip).write_text(src_text, encoding="utf-8")
        # Pinned exact version for reproducibility + supply-chain safety.
        try:
            subprocess.run(["npx", "--yes", "rtlcss@4.3.0", ip, op],
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"rtlcss failed (exit {e.returncode}): {(e.stderr or '').strip()[:500]}"
            ) from e
        return Path(op).read_text(encoding="utf-8")


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic UTF-8 write, LF newlines (pattern from tools/translator/weglot.py:87)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    p = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(p, path)
    except Exception:
        if p.exists():
            p.unlink(missing_ok=True)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate cel-arabic.css from live Webflow CSS.")
    ap.add_argument("--force", action="store_true", help="regenerate even if the fingerprint matches")
    ap.add_argument("--check", action="store_true", help="report change status only; exit 1 if a change is detected")
    args = ap.parse_args()

    try:
        sitemap_xml = fetch(SITEMAP_URL)
    except Exception as e:  # noqa: BLE001 — a network blip shouldn't crash with a traceback
        print(f"ERROR: could not fetch sitemap {SITEMAP_URL}: {e}", file=sys.stderr)
        return 1
    ar_urls = get_ar_urls(sitemap_xml)
    if not ar_urls:
        print("ERROR: sitemap yielded 0 /ar/ URLs — aborting without writing", file=sys.stderr)
        return 1
    print(f"found {len(ar_urls)} /ar/ URLs in sitemap")

    css_urls: set[str] = set()
    for page in ar_urls:
        try:
            css_urls.update(extract_css_urls(fetch(page)))
        except Exception as e:  # noqa: BLE001 — one flaky page must not block regeneration
            print(f"  WARN: skipping {page}: {e}", file=sys.stderr)
    css_urls = sorted(css_urls)
    if not css_urls:
        print("ERROR: no Webflow CDN CSS found on /ar/ pages — aborting", file=sys.stderr)
        return 1
    print(f"{len(css_urls)} unique Webflow CSS file(s)")

    fp = fingerprint(css_urls)
    prior = read_prior_fp(OUT_PATH)

    if args.check:
        changed = fp != prior
        print("CHANGE DETECTED" if changed else "no change")
        return 1 if changed else 0
    if fp == prior and not args.force:
        print("no change (fingerprint match) — skipping regeneration")
        return 0

    combined = []
    for u in css_urls:
        css = fetch(u)
        if not css.strip():
            print(f"ERROR: empty CSS from {u} — aborting (won't overwrite with partial output)", file=sys.stderr)
            return 1
        combined.append(css)
    raw_src = "\n".join(combined)
    combined_src = dedupe_rules(raw_src)
    print(f"combined CSS {len(raw_src)} bytes -> {len(combined_src)} bytes after de-duplicating "
          f"({len(generator.split_top(raw_src))} -> {len(generator.split_top(combined_src))} top-level rules)")

    combined_rtl = run_rtlcss(combined_src)
    src_rules = generator.split_top(combined_src)
    rtl_rules = generator.split_top(combined_rtl)
    override = generator.emit(src_rules, rtl_rules)
    fonts = generator.font_overrides(src_rules)

    warn = generator.changed_atrules(src_rules, rtl_rules)
    if warn:
        print(f"WARNING: {warn} @keyframes/@font-face block(s) change under RTL but are NOT "
              "auto-flipped — handle directional animations manually in arabic_static.css")

    static = STATIC_PATH.read_text(encoding="utf-8").strip()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (f"/*! cel-arabic.css | generated {ts} | source-fp:{fp} "
              f"| css-files:{len(css_urls)} | rtlcss-override+font-swap+static */")
    out = header + "\n" + static + "\n" + override + fonts + "\n"
    atomic_write_text(OUT_PATH, out)
    print(f"wrote {OUT_PATH} — {len(out)} bytes "
          f"(static {len(static)} + override {len(override)} + font-swap {len(fonts)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
