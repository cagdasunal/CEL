#!/usr/bin/env python3
"""
Weglot Exclusion Sync — Detects new blog posts and manages translation exclusions.

Flow:
1. Fetch all published blog posts from Webflow CMS API
2. Read current Weglot excluded_paths via API
3. Compute which posts need new exclusion rules
4. Attempt to push to Weglot API (POST /projects/settings)
5. If Weglot write fails → generate CSV for manual import
6. Update local state file (data/weglot-exclusions.json)
7. Signal GitHub Actions to regenerate sitemap + llms.txt if changes found

Environment variables:
  WEBFLOW_API_TOKEN  — Webflow Data API bearer token
  WEGLOT_API_KEY     — Weglot project API key (wg_...)

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

# Optional: requests is needed for API calls (installed in CI via pip)
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
CSV_OUTPUT = DATA_DIR / "weglot-import.csv"

WEBFLOW_API_BASE = "https://api.webflow.com/v2"
BLOG_COLLECTION_ID = "667453c576e8d35c454ccaae"

WEGLOT_API_BASE = "https://api.weglot.com"

# All Weglot translated languages (everything except the English base)
ALL_TRANSLATED_LANGS = {"ar", "de", "es", "fr", "it", "ja", "ko", "pt"}

# Webflow CMS Language item ID → Weglot language code
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

# Logging
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
    """Get required environment variable or exit."""
    val = os.environ.get(name, "").strip()
    if not val:
        log.error(f"Missing required env var: {name}")
        sys.exit(1)
    return val


def compute_excluded_languages(post_lang: str) -> list[str]:
    """Given a post's language code, return the sorted list of languages to exclude.

    - English posts: exclude ALL translated languages (ar,de,es,fr,it,ja,ko,pt)
    - Non-English posts: exclude all EXCEPT the post's own language
      (English/base is never in the exclusion list since it's Weglot's original)
    """
    if post_lang == "en":
        return sorted(ALL_TRANSLATED_LANGS)
    else:
        return sorted(ALL_TRANSLATED_LANGS - {post_lang})


# ---------------------------------------------------------------------------
# Webflow CMS API
# ---------------------------------------------------------------------------

def fetch_all_blog_posts(token: str) -> list[dict]:
    """Fetch all published blog posts from Webflow CMS, handling pagination."""
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
    }
    all_items = []
    offset = 0
    limit = 100

    while True:
        url = f"{WEBFLOW_API_BASE}/collections/{BLOG_COLLECTION_ID}/items"
        params = {"limit": limit, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        all_items.extend(items)

        pagination = data.get("pagination", {})
        total = pagination.get("total", len(items))

        log.info(f"Fetched {len(all_items)}/{total} blog posts")

        if len(all_items) >= total:
            break
        offset += limit

    return all_items


def extract_post_data(items: list[dict]) -> list[dict]:
    """Extract slug and language from blog post items. Skip drafts and posts without language."""
    posts = []
    for item in items:
        if item.get("isDraft", False) or item.get("isArchived", False):
            continue

        # Skip scheduled posts that haven't been published yet
        if not item.get("lastPublished"):
            continue

        field_data = item.get("fieldData", {})
        slug = field_data.get("slug", "")
        lang_ref = field_data.get("language", "")

        if not slug:
            log.warning(f"Post {item.get('id', '?')} has no slug, skipping")
            continue

        if not lang_ref:
            log.warning(f"Post '{slug}' has no language set, skipping")
            continue

        lang_code = LANGUAGE_ID_MAP.get(lang_ref)
        if not lang_code:
            log.warning(f"Post '{slug}' has unknown language ref '{lang_ref}', skipping")
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
# Weglot API
# ---------------------------------------------------------------------------

def fetch_weglot_exclusions(api_key: str) -> list[dict]:
    """Fetch current excluded_paths from Weglot settings API."""
    url = f"{WEGLOT_API_BASE}/projects/settings"
    params = {"api_key": api_key}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("excluded_paths", [])


def try_push_weglot_exclusion(api_key: str, exclusion: dict) -> bool:
    """Attempt to push a new exclusion to Weglot API.

    Returns True if successful, False if the API key lacks write permissions.
    """
    url = f"{WEGLOT_API_BASE}/projects/settings"
    params = {"api_key": api_key}
    try:
        resp = requests.post(
            url,
            params=params,
            json={"excluded_paths": [exclusion]},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
        elif resp.status_code == 401:
            return False
        else:
            log.warning(f"Weglot POST returned {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"Weglot POST failed: {e}")
        return False


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load exclusion state from JSON file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_sync": None, "exclusions": {}}


def save_state(state: dict) -> None:
    """Save exclusion state to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=False)
    log.info(f"State saved to {STATE_FILE}")


# ---------------------------------------------------------------------------
# CSV Export (for manual Weglot import)
# ---------------------------------------------------------------------------

def generate_csv(new_exclusions: list[dict]) -> None:
    """Generate a Weglot-compatible CSV for manual import of pending exclusions."""
    if not new_exclusions:
        # Remove pending CSV if no new exclusions
        if CSV_OUTPUT.exists():
            CSV_OUTPUT.unlink()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CSV_OUTPUT, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "id", "type", "value", "languages",
            "language_button_displayed", "exclusion_behavior",
        ])
        for i, exc in enumerate(new_exclusions, start=1):
            writer.writerow([
                "",  # id (auto-assigned by Weglot)
                "Is exactly",
                exc["url_path"],
                ",".join(exc["excluded_languages"]),
                1,  # language_button_displayed
                "Redirect",
            ])
    log.info(f"CSV with {len(new_exclusions)} pending exclusions written to {CSV_OUTPUT}")


# ---------------------------------------------------------------------------
# Sitemap Exclusion Data (for sitemap generator)
# ---------------------------------------------------------------------------

def generate_sitemap_exclusion_data(state: dict) -> None:
    """Write a simplified exclusion map for the sitemap generator to consume.

    Output: data/weglot-sitemap-exclusions.json
    Format: { "/post/slug": ["ar", "de", ...], ... }
    """
    exclusion_map = {}
    for slug, info in state.get("exclusions", {}).items():
        url_path = f"/post/{slug}"
        exclusion_map[url_path] = info["excluded_from"]

    out_path = DATA_DIR / "weglot-sitemap-exclusions.json"
    with open(out_path, "w") as f:
        json.dump(exclusion_map, f, indent=2, sort_keys=True)
    log.info(f"Sitemap exclusion map written to {out_path} ({len(exclusion_map)} entries)")


# ---------------------------------------------------------------------------
# Main Sync Logic
# ---------------------------------------------------------------------------

def sync(dry_run: bool = False) -> bool:
    """Run the full sync. Returns True if changes were made."""
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

    # 3. Load local state
    state = load_state()

    # 4. Find posts that need new exclusion rules
    new_exclusions = []
    for post in posts:
        url_path = post["url_path"]

        # Already in Weglot → skip
        if url_path in weglot_paths:
            # Ensure it's in local state too
            if post["slug"] not in state["exclusions"]:
                state["exclusions"][post["slug"]] = {
                    "language": post["language"],
                    "excluded_from": compute_excluded_languages(post["language"]),
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "source": "weglot_existing",
                }
            continue

        # Already in local state (added in previous run, pending Weglot import)
        if post["slug"] in state["exclusions"]:
            continue

        # New post — needs exclusion
        excluded_langs = compute_excluded_languages(post["language"])
        log.info(
            f"NEW: {url_path} (lang={post['language']}) → exclude {','.join(excluded_langs)}"
        )
        new_exclusions.append({
            "slug": post["slug"],
            "name": post["name"],
            "url_path": url_path,
            "language": post["language"],
            "excluded_languages": excluded_langs,
        })

    if not new_exclusions:
        log.info("No new exclusions needed. Everything is in sync.")
        # Still update state to capture any Weglot-existing entries we synced
        if not dry_run:
            save_state(state)
            generate_sitemap_exclusion_data(state)
        return False

    log.info(f"Found {len(new_exclusions)} posts needing exclusion rules")

    if dry_run:
        log.info("DRY RUN — no changes will be made")
        for exc in new_exclusions:
            print(f"  {exc['url_path']} ({exc['language']}) → exclude: {','.join(exc['excluded_languages'])}")
        return True

    # 5. Try pushing to Weglot API
    weglot_push_success = False
    if new_exclusions:
        log.info("Attempting to push exclusions to Weglot API...")
        # Try first one as a test
        test_exc = {
            "type": "IS_EXACTLY",
            "value": new_exclusions[0]["url_path"],
            "language_button_displayed": True,
            "exclusion_behavior": "REDIRECT",
            "excluded_languages": new_exclusions[0]["excluded_languages"],
        }
        weglot_push_success = try_push_weglot_exclusion(weglot_key, test_exc)
        if weglot_push_success:
            log.info("Weglot API write succeeded! Pushing all exclusions...")
            for exc in new_exclusions[1:]:
                weglot_exc = {
                    "type": "IS_EXACTLY",
                    "value": exc["url_path"],
                    "language_button_displayed": True,
                    "exclusion_behavior": "REDIRECT",
                    "excluded_languages": exc["excluded_languages"],
                }
                try_push_weglot_exclusion(weglot_key, weglot_exc)
        else:
            log.warning(
                "Weglot API write not available (key lacks write permission). "
                "Generating CSV for manual import."
            )

    # 6. Update local state
    for exc in new_exclusions:
        state["exclusions"][exc["slug"]] = {
            "language": exc["language"],
            "excluded_from": exc["excluded_languages"],
            "added_at": datetime.now(timezone.utc).isoformat(),
            "source": "weglot_api" if weglot_push_success else "pending_csv",
        }

    save_state(state)

    # 7. Generate CSV for manual import (if Weglot write failed)
    if not weglot_push_success:
        generate_csv(new_exclusions)

    # 8. Generate sitemap exclusion data
    generate_sitemap_exclusion_data(state)

    # 9. Set GitHub Actions output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write("changes_made=true\n")
            f.write(f"new_exclusions={len(new_exclusions)}\n")
            f.write(f"weglot_push={'success' if weglot_push_success else 'csv_fallback'}\n")

    log.info(
        f"Sync complete: {len(new_exclusions)} new exclusions "
        f"({'pushed to Weglot' if weglot_push_success else 'CSV generated for import'})"
    )
    return True


def show_status():
    """Show current sync status."""
    state = load_state()
    total = len(state.get("exclusions", {}))
    pending = sum(
        1 for v in state.get("exclusions", {}).values()
        if v.get("source") == "pending_csv"
    )
    print(f"Last sync: {state.get('last_sync', 'never')}")
    print(f"Total tracked exclusions: {total}")
    print(f"Pending CSV import: {pending}")
    if CSV_OUTPUT.exists():
        print(f"Pending CSV file: {CSV_OUTPUT}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        sys.exit(0)

    dry_run = "--dry-run" in args

    try:
        changes = sync(dry_run=dry_run)
        sys.exit(0 if not changes else 0)
    except requests.HTTPError as e:
        log.error(f"HTTP error: {e}")
        log.error(f"Response: {e.response.text[:500] if e.response else 'no response'}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)
