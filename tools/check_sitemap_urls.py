#!/usr/bin/env python3
"""
Sitemap URL Checker — Validates all URLs in sitemap.xml are healthy.

Checks:
- HTTP status (expects 200, flags 301/302/404/5xx)
- Page loads (response within timeout)
- No redirect chains

Usage:
  python3 tools/check_sitemap_urls.py                    # check all URLs
  python3 tools/check_sitemap_urls.py --posts-only       # check only /post/ URLs
  python3 tools/check_sitemap_urls.py --limit 50         # check first 50 URLs
  python3 tools/check_sitemap_urls.py --sitemap URL      # use a specific sitemap URL
"""

import sys
import json
import logging
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from lxml import etree
except ImportError:
    print("ERROR: requires 'requests' and 'lxml'. Install: pip install requests lxml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_SITEMAP = PROJECT_ROOT / "docs" / "sitemap.xml"
REMOTE_SITEMAP = "https://raw.githubusercontent.com/cagdasunal/CEL/main/docs/sitemap.xml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("url-check")


def load_sitemap_urls(source: str) -> list[str]:
    """Load URLs from a local file or remote URL."""
    if source.startswith("http"):
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()
        root = etree.fromstring(resp.content)
    else:
        tree = etree.parse(source)
        root = tree.getroot()

    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = root.xpath("//ns:loc", namespaces=ns)
    if not locs:
        locs = root.xpath("//loc")
    return [el.text.strip() for el in locs if el.text]


def check_url(url: str, timeout: int = 10) -> dict:
    """Check a single URL with GET (no redirect follow). Fast — doesn't load full page."""
    try:
        # Use GET with allow_redirects=False and stream=True to avoid downloading body
        resp = requests.get(url, timeout=timeout, allow_redirects=False, stream=True)
        resp.close()  # Don't download body

        result = {
            "url": url,
            "status": resp.status_code,
            "ok": resp.status_code == 200,
        }

        if resp.status_code in (301, 302, 307, 308):
            location = resp.headers.get("Location", "")
            result["redirect_to"] = location
            result["issue"] = f"redirect {resp.status_code} → {location}"

        elif resp.status_code == 404:
            result["issue"] = "not found"

        elif resp.status_code >= 500:
            result["issue"] = f"server error {resp.status_code}"

        return result

    except requests.Timeout:
        return {"url": url, "status": 0, "ok": False, "issue": "timeout"}
    except requests.ConnectionError as e:
        return {"url": url, "status": 0, "ok": False, "issue": f"connection error: {e}"}
    except Exception as e:
        return {"url": url, "status": 0, "ok": False, "issue": str(e)}


def main():
    args = sys.argv[1:]
    posts_only = "--posts-only" in args
    limit = None
    sitemap_source = str(DEFAULT_SITEMAP) if DEFAULT_SITEMAP.exists() else REMOTE_SITEMAP

    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if arg == "--sitemap" and i + 1 < len(args):
            sitemap_source = args[i + 1]

    log.info(f"Loading sitemap from: {sitemap_source}")
    urls = load_sitemap_urls(sitemap_source)
    log.info(f"Loaded {len(urls)} URLs")

    if posts_only:
        urls = [u for u in urls if "/post/" in urlparse(u).path]
        log.info(f"Filtered to {len(urls)} post URLs")

    if limit:
        urls = urls[:limit]
        log.info(f"Limited to {limit} URLs")

    # Check URLs in parallel
    log.info(f"Checking {len(urls)} URLs (10 concurrent)...")
    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(check_url, url): url for url in urls}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done += 1
            if not result["ok"]:
                log.warning(f"[{done}/{len(urls)}] {result['status']} {result['url']} — {result.get('issue','')}")
            elif done % 100 == 0:
                log.info(f"[{done}/{len(urls)}] checked...")

    # Summary
    ok = [r for r in results if r["ok"]]
    redirects = [r for r in results if r["status"] in (301, 302, 307, 308)]
    not_found = [r for r in results if r["status"] == 404]
    errors = [r for r in results if r["status"] >= 500 or r["status"] == 0]

    print(f"\n{'='*60}")
    print(f"SITEMAP URL CHECK RESULTS")
    print(f"{'='*60}")
    print(f"Total checked:  {len(results)}")
    print(f"OK (200):       {len(ok)}")
    print(f"Redirects:      {len(redirects)}")
    print(f"Not found (404):{len(not_found)}")
    print(f"Errors:         {len(errors)}")

    if redirects:
        print(f"\n--- REDIRECTS ({len(redirects)}) ---")
        for r in redirects:
            print(f"  {r['status']} {r['url']}")
            print(f"    → {r.get('redirect_to', '?')}")

    if not_found:
        print(f"\n--- NOT FOUND ({len(not_found)}) ---")
        for r in not_found:
            print(f"  {r['url']}")

    if errors:
        print(f"\n--- ERRORS ({len(errors)}) ---")
        for r in errors:
            print(f"  {r['url']} — {r.get('issue', '?')}")

    # Save full report
    report_path = PROJECT_ROOT / "data" / "sitemap-check-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "total": len(results),
            "ok": len(ok),
            "redirects": len(redirects),
            "not_found": len(not_found),
            "errors": len(errors),
            "issues": [r for r in results if not r["ok"]],
        }, f, indent=2)
    print(f"\nFull report: {report_path}")

    # Exit code: 1 if any 404s or errors
    if not_found or errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
