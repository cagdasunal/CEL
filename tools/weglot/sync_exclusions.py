#!/usr/bin/env python3
"""
Weglot Exclusion Sync — Detects new blog posts and generates CSV for Weglot import.

Flow:
1. Fetch all published blog posts from Webflow CMS API
2. Read current Weglot excluded_paths via API (public key, read-only)
3. Compute which posts need new exclusion rules
4. Generate CSV for manual Weglot dashboard import
5. Update local state + sitemap exclusion data
6. Signal GitHub Actions to regenerate sitemap if changes found

Note: Weglot POST API cannot set per-language exclusions (excluded_languages
field is silently stripped). CSV import via dashboard is the only way to set
per-language exclusions correctly.

Environment variables:
  WEBFLOW_API_TOKEN  — Webflow Data API bearer token
  WEGLOT_API_KEY     — Weglot public API key (read access)

Usage:
  python3 tools/weglot/sync_exclusions.py          # full sync
  python3 tools/weglot/sync_exclusions.py --dry-run # show what would change
  python3 tools/weglot/sync_exclusions.py --status  # show current state
"""

import json
import os
import sys
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "weglot-exclusions.json"
CSV_OUTPUT = DATA_DIR / "weglot.csv"

WEBFLOW_API_BASE = "https://api.webflow.com/v2"
BLOG_COLLECTION_ID = "667453c576e8d35c454ccaae"

WEGLOT_API_BASE = "https://api.weglot.com"

ALL_TRANSLATED_LANGS = {"ar", "de", "es", "fr", "it", "ja", "ko", "pt"}

LANGUAGE_ID_MAP = {
    "6876590744e1f69b128ef245": "en",
    "6876596a3a4d6e078bebe528": "de",
    "687659b3281d98a9803a86ae": "fr",
    "6876591fab42b61d6b9f6a96": "es",
    "6876597d1d2fe4f1a294fd77": "ko",
    "687659cca45f80dbea92430c": "it",
    "6876599de124298a6bd8cb8d": "pt",
    "687659e4ab42b61d6b9f6a96": "ja",
    "687659fe11c147ceed4f09cd": "ar",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("weglot-sync")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        log.error(f"Missing required env var: {name}")
        sys.exit(1)
    return val


def compute_excluded_languages(post_lang: str) -> list[str]:
    """Given a post's language code, return sorted list of languages to exclude."""
    if post_lang == "en":
        return sorted(ALL_TRANSLATED_LANGS)
    else:
        return sorted(ALL_TRANSLATED_LANGS - {post_lang})


# ---------------------------------------------------------------------------
# Webflow CMS API
# ---------------------------------------------------------------------------

def fetch_all_blog_posts(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    all_items = []
    offset = 0
    limit = 100

    while True:
        url = f"{WEBFLOW_API_BASE}/collections/{BLOG_COLLECTION_ID}/items"
        resp = requests.get(url, headers=headers, params={"limit": limit, "offset": offset}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_items.extend(items)
        total = data.get("pagination", {}).get("total", len(items))
        log.info(f"Fetched {len(all_items)}/{total} blog posts")
        if len(all_items) >= total:
            break
        offset += limit

    return all_items


def extract_post_data(items: list[dict]) -> list[dict]:
    posts = []
    for item in items:
        if item.get("isArchived", False):
            continue
        # isDraft=True + lastPublished set = published with unsaved edits (still live)
        if not item.get("lastPublished"):
            continue

        field_data = item.get("fieldData", {})
        slug = field_data.get("slug", "")
        lang_ref = field_data.get("language", "")

        if not slug:
            continue
        if not lang_ref:
            continue

        lang_code = LANGUAGE_ID_MAP.get(lang_ref)
        if not lang_code:
            continue

        posts.append({
            "id": item["id"],
            "slug": slug,
            "name": field_data.get("name", slug),
            "language": lang_code,
            "url_path": f"/post/{slug}",
            "last_published": item.get("lastPublished", ""),
        })

    return posts


# ---------------------------------------------------------------------------
# Weglot API (read-only)
# ---------------------------------------------------------------------------

def fetch_weglot_exclusions(api_key: str) -> list[dict]:
    url = f"{WEGLOT_API_BASE}/projects/settings"
    resp = requests.get(url, params={"api_key": api_key}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("excluded_paths", [])


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_sync": None, "exclusions": {}}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=False)
    log.info(f"State saved to {STATE_FILE}")


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

def generate_csv(new_exclusions: list[dict]) -> None:
    """Generate Weglot-compatible CSV for dashboard import."""
    if not new_exclusions:
        if CSV_OUTPUT.exists():
            CSV_OUTPUT.unlink()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CSV_OUTPUT, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["id", "type", "value", "languages", "language_button_displayed", "exclusion_behavior"])
        for exc in new_exclusions:
            writer.writerow([
                "",
                "Is exactly",
                exc["url_path"],
                ",".join(exc["excluded_languages"]),
                1,
                "Redirect",
            ])
    log.info(f"CSV with {len(new_exclusions)} exclusions written to {CSV_OUTPUT}")


# ---------------------------------------------------------------------------
# Sitemap Exclusion Data
# ---------------------------------------------------------------------------

def generate_sitemap_exclusion_data(state: dict) -> None:
    exclusion_map = {}
    for slug, info in state.get("exclusions", {}).items():
        exclusion_map[f"/post/{slug}"] = info["excluded_from"]

    out_path = DATA_DIR / "weglot-sitemap-exclusions.json"
    with open(out_path, "w") as f:
        json.dump(exclusion_map, f, indent=2, sort_keys=True)
    log.info(f"Sitemap exclusion map written to {out_path} ({len(exclusion_map)} entries)")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_exclusions(weglot_exclusions: list[dict], posts: list[dict]) -> int:
    """Validate Weglot exclusions match expected patterns. Returns count of issues."""
    post_lang_map = {post["url_path"]: post["language"] for post in posts}
    issues = 0

    for ex in weglot_exclusions:
        value = ex.get("value", "")
        if not value.startswith("/post/"):
            continue

        excluded = ex.get("excluded_languages", [])
        if not excluded:
            continue  # empty = exclude ALL, acceptable for English posts

        post_lang = post_lang_map.get(value)
        if not post_lang:
            continue  # post not in CMS (orphan or draft) — skip

        # Check: post's own language should NOT be in excluded list
        if post_lang != "en" and post_lang in excluded:
            log.warning(
                f"SELF-EXCLUSION: {value} is {post_lang.upper()} but excludes {post_lang}! "
                f"This post is invisible to {post_lang} visitors. Fix in Weglot dashboard."
            )
            issues += 1

        # Check: expected excluded languages
        expected = compute_excluded_languages(post_lang)
        if sorted(excluded) != expected:
            log.warning(
                f"MISMATCH: {value} ({post_lang}) excludes {','.join(sorted(excluded))} "
                f"but expected {','.join(expected)}"
            )
            issues += 1

    if issues:
        log.warning(f"Validation found {issues} exclusion issues — check Weglot dashboard")
    else:
        log.info("Validation: all exclusions match expected patterns")

    return issues


# ---------------------------------------------------------------------------
# Main Sync Logic
# ---------------------------------------------------------------------------

def sync(dry_run: bool = False) -> bool:
    webflow_token = get_env("WEBFLOW_API_TOKEN")
    weglot_key = get_env("WEGLOT_API_KEY")

    # 1. Fetch blog posts from Webflow
    log.info("Fetching blog posts from Webflow CMS...")
    raw_items = fetch_all_blog_posts(webflow_token)
    posts = extract_post_data(raw_items)
    log.info(f"Found {len(posts)} published posts with language set")

    # 2. Fetch current Weglot exclusions
    log.info("Fetching current Weglot exclusions...")
    weglot_exclusions = fetch_weglot_exclusions(weglot_key)
    weglot_paths = {ex["value"] for ex in weglot_exclusions}
    log.info(f"Weglot has {len(weglot_exclusions)} exclusion rules")

    # 2.5 Validate existing exclusions
    validate_exclusions(weglot_exclusions, posts)

    # 3. Load local state
    state = load_state()

    # 4. Auto-confirm imported entries: if a post was "csv" or "needs_import"
    #    in state but now appears in Weglot, update source to "weglot_existing"
    imported_count = 0
    for slug, info in state.get("exclusions", {}).items():
        if info.get("source") in ("csv", "needs_import"):
            if f"/post/{slug}" in weglot_paths:
                info["source"] = "weglot_existing"
                imported_count += 1
    if imported_count:
        log.info(f"Confirmed {imported_count} previously pending entries now in Weglot")

    # 5. Find posts not yet in Weglot
    new_exclusions = []
    for post in posts:
        url_path = post["url_path"]

        if url_path in weglot_paths:
            if post["slug"] not in state["exclusions"]:
                state["exclusions"][post["slug"]] = {
                    "language": post["language"],
                    "excluded_from": compute_excluded_languages(post["language"]),
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "source": "weglot_existing",
                }
            continue

        excluded_langs = compute_excluded_languages(post["language"])
        log.info(f"NEW: {url_path} (lang={post['language']}) → exclude {','.join(excluded_langs)}")
        new_exclusions.append({
            "slug": post["slug"],
            "name": post["name"],
            "url_path": url_path,
            "language": post["language"],
            "excluded_languages": excluded_langs,
        })

    if not new_exclusions:
        log.info("No new exclusions needed. Everything is in sync.")
        if not dry_run:
            save_state(state)
            generate_sitemap_exclusion_data(state)
            # Clear CSV if all pending entries are now confirmed in Weglot
            if imported_count > 0:
                generate_csv([])  # clears the file
                return True  # signal changes so workflow commits the cleared CSV
        return False

    log.info(f"Found {len(new_exclusions)} posts needing exclusion rules")

    if dry_run:
        log.info("DRY RUN — no changes will be made")
        for exc in new_exclusions:
            print(f"  {exc['url_path']} ({exc['language']}) → exclude: {','.join(exc['excluded_languages'])}")
        return True

    # 5. Generate CSV for Weglot dashboard import
    generate_csv(new_exclusions)

    # 6. Update local state
    for exc in new_exclusions:
        state["exclusions"][exc["slug"]] = {
            "language": exc["language"],
            "excluded_from": exc["excluded_languages"],
            "added_at": datetime.now(timezone.utc).isoformat(),
            "source": "csv",
        }

    save_state(state)

    # 7. Generate sitemap exclusion data
    generate_sitemap_exclusion_data(state)

    # 8. Set GitHub Actions output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write("changes_made=true\n")
            f.write(f"new_exclusions={len(new_exclusions)}\n")

    log.info(f"Sync complete: {len(new_exclusions)} new exclusions → CSV generated for Weglot import")
    return True


def show_status():
    state = load_state()
    total = len(state.get("exclusions", {}))
    sources = {}
    for v in state.get("exclusions", {}).values():
        s = v.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    print(f"Last sync: {state.get('last_sync', 'never')}")
    print(f"Total tracked exclusions: {total}")
    print(f"Sources: {sources}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--status" in args:
        show_status()
        sys.exit(0)

    dry_run = "--dry-run" in args
    try:
        sync(dry_run=dry_run)
    except requests.HTTPError as e:
        log.error(f"HTTP error: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)
