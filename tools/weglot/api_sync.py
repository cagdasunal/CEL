#!/usr/bin/env python3
"""
Weglot API Sync — posts new blog post exclusions directly to Weglot API.

Flow:
1. Fetch all published blog posts from Webflow CMS API
2. GET current Weglot excluded_paths
3. Compute which posts are new (not in Weglot yet)
4. POST full merged array (existing verbatim + new UPPERCASE entries)
5. Verify with second GET — exit 2 if any existing excluded_languages stripped
6. Emit GitHub Actions outputs

Environment variables:
  WEBFLOW_API_TOKEN   — Webflow Data API bearer token
  WEGLOT_PUBLIC_KEY   — Weglot public API key (read-only GET)
  WEGLOT_PRIVATE_KEY  — Weglot private API key (write POST)

UPPERCASE enum format required (title case returns HTTP 400 — confirmed 2026-04-21):
  type: "IS_EXACTLY"  (not "Is exactly")
  exclusion_behavior: "REDIRECT"  (not "Redirect")

Cloudflare 1010 bypass: USER_AGENT header required on all api.weglot.com requests.

URL: https://api.weglot.com/projects/settings
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEGLOT_SETTINGS_URL = "https://api.weglot.com/projects/settings"
WEBFLOW_API_BASE = "https://api.webflow.com/v2"
BLOG_COLLECTION_ID = "667453c576e8d35c454ccaae"

ALL_TRANSLATED_LANGS = frozenset({"ar", "de", "es", "fr", "it", "ja", "ko", "pt"})

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

HTTP_TIMEOUT = 60

# Required to bypass Cloudflare 1010 on api.weglot.com
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "weglot-exclusions.json"


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib urllib with manual retry)
# ---------------------------------------------------------------------------

def _http_request(
    url: str,
    *,
    method: str = "GET",
    extra_headers: dict | None = None,
    data: bytes | None = None,
    retries: int = 4,
) -> tuple[int, dict | str]:
    req_headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        req_headers.update(extra_headers)

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries + 1):
        try:
            req = Request(url, data=data, headers=req_headers, method=method)
            with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                status = resp.status
                try:
                    return status, json.loads(body)
                except json.JSONDecodeError:
                    return status, body
        except HTTPError as e:
            body_bytes = e.read()
            body_str = body_bytes.decode("utf-8", errors="replace")
            if e.code < 500:
                try:
                    return e.code, json.loads(body_str)
                except json.JSONDecodeError:
                    return e.code, body_str
            last_exc = e
        except URLError as e:
            last_exc = e

        if attempt < retries:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Request failed after {retries} retries: {last_exc}") from last_exc


def http_get(url: str, *, params: dict | None = None) -> tuple[int, dict | str]:
    full_url = url + ("?" + urlencode(params) if params else "")
    return _http_request(full_url, method="GET")


def http_post_json(url: str, body: dict, *, params: dict | None = None) -> tuple[int, dict | str]:
    full_url = url + ("?" + urlencode(params) if params else "")
    data = json.dumps(body).encode("utf-8")
    return _http_request(
        full_url,
        method="POST",
        extra_headers={"Content-Type": "application/json"},
        data=data,
    )


# ---------------------------------------------------------------------------
# Webflow CMS API
# ---------------------------------------------------------------------------

def fetch_all_blog_posts(token: str) -> list[dict]:
    all_items: list[dict] = []
    offset = 0
    limit = 100

    while True:
        url = (
            f"{WEBFLOW_API_BASE}/collections/{BLOG_COLLECTION_ID}/items"
            f"?limit={limit}&offset={offset}"
        )
        last_exc: Exception = RuntimeError("no attempts")
        data: dict = {}
        for attempt in range(5):
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json",
                    },
                )
                with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    break
            except HTTPError as e:
                if e.code < 500:
                    raise
                last_exc = e
            except URLError as e:
                last_exc = e
            if attempt < 4:
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Webflow CMS fetch failed: {last_exc}")

        items = data.get("items", [])
        all_items.extend(items)
        total = data.get("pagination", {}).get("total", len(all_items))
        print(f"[api_sync] Fetched {len(all_items)}/{total} blog posts", flush=True)
        if len(all_items) >= total:
            break
        offset += limit

    return all_items


def extract_post_data(items: list[dict]) -> list[dict]:
    posts = []
    for item in items:
        if item.get("isArchived", False):
            continue
        if not item.get("lastPublished"):
            continue

        field_data = item.get("fieldData", {})
        slug = field_data.get("slug", "")
        lang_ref = field_data.get("language", "")

        if not slug or not lang_ref:
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
# Language exclusion logic
# ---------------------------------------------------------------------------

def compute_excluded_languages(post_lang: str) -> list[str]:
    if post_lang == "en":
        return sorted(ALL_TRANSLATED_LANGS)
    return sorted(ALL_TRANSLATED_LANGS - {post_lang})


# ---------------------------------------------------------------------------
# Weglot API
# ---------------------------------------------------------------------------

def fetch_weglot_settings(public_key: str) -> dict:
    status, body = http_get(WEGLOT_SETTINGS_URL, params={"api_key": public_key})
    if status != 200:
        raise RuntimeError(f"GET Weglot settings failed: HTTP {status}: {body}")
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected response type from Weglot GET: {type(body)}")
    return body


def post_weglot_settings(private_key: str, body: dict) -> tuple[int, dict | str]:
    return http_post_json(
        WEGLOT_SETTINGS_URL,
        body,
        params={"api_key": private_key},
    )


# ---------------------------------------------------------------------------
# Entry building
# ---------------------------------------------------------------------------

def build_new_entries(new_posts: list[dict]) -> list[dict]:
    entries = []
    for post in new_posts:
        excluded = compute_excluded_languages(post["language"])
        entries.append({
            "type": "IS_EXACTLY",
            "value": post["url_path"],
            "language_button_displayed": True,
            "exclusion_behavior": "REDIRECT",
            "excluded_languages": sorted(excluded),
        })
    return entries


# ---------------------------------------------------------------------------
# State management
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


def generate_sitemap_exclusion_data(state: dict) -> None:
    exclusion_map = {}
    for slug, info in state.get("exclusions", {}).items():
        exclusion_map[f"/post/{slug}"] = info.get("excluded_from", [])
    out_path = DATA_DIR / "weglot-sitemap-exclusions.json"
    with open(out_path, "w") as f:
        json.dump(exclusion_map, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# GitHub Actions output
# ---------------------------------------------------------------------------

def emit_github_output(
    updated: bool, count: int, slugs: list[str], error: str = ""
) -> None:
    lines = [
        f"updated={'true' if updated else 'false'}",
        f"count={count}",
        f"slugs={','.join(slugs)}",
        f"error={error}",
    ]
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        for line in lines:
            print(f"[output] {line}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Sync new blog posts to Weglot API.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, no POST.")
    parser.add_argument("--status", action="store_true", help="Print current state and exit.")
    args = parser.parse_args()

    webflow_token = os.environ.get("WEBFLOW_API_TOKEN", "").strip()
    public_key = os.environ.get("WEGLOT_PUBLIC_KEY", "").strip()
    private_key = os.environ.get("WEGLOT_PRIVATE_KEY", "").strip()

    for name, val in [
        ("WEBFLOW_API_TOKEN", webflow_token),
        ("WEGLOT_PUBLIC_KEY", public_key),
        ("WEGLOT_PRIVATE_KEY", private_key),
    ]:
        if not val:
            print(f"ERROR: missing env var {name}", file=sys.stderr)
            return 1

    if args.status:
        state = load_state()
        print(json.dumps(state, indent=2))
        return 0

    # Fetch CMS posts
    print("[api_sync] Fetching Webflow CMS blog posts...", flush=True)
    try:
        raw_items = fetch_all_blog_posts(webflow_token)
    except Exception as e:
        emit_github_output(False, 0, [], error=f"CMS fetch failed: {e}")
        return 1

    posts = extract_post_data(raw_items)
    print(f"[api_sync] {len(posts)} published posts with language set", flush=True)

    # GET current Weglot state
    print("[api_sync] Fetching current Weglot settings...", flush=True)
    try:
        current = fetch_weglot_settings(public_key)
    except Exception as e:
        emit_github_output(False, 0, [], error=f"Weglot GET failed: {e}")
        return 1

    existing_entries = list(current.get("excluded_paths", []))
    existing_paths = {e["value"] for e in existing_entries}
    print(f"[api_sync] Weglot has {len(existing_paths)} existing exclusion rules", flush=True)

    # Compute new posts
    new_posts = [p for p in posts if p["url_path"] not in existing_paths]
    print(f"[api_sync] {len(new_posts)} new posts to add", flush=True)

    state = load_state()

    if not new_posts:
        for post in posts:
            slug = post["slug"]
            state.setdefault("exclusions", {}).setdefault(slug, {
                "language": post["language"],
                "excluded_from": compute_excluded_languages(post["language"]),
                "source": "api",
                "url_path": post["url_path"],
            })
        save_state(state)
        generate_sitemap_exclusion_data(state)
        emit_github_output(False, 0, [])
        return 0

    if args.dry_run:
        print(f"[dry-run] Would POST {len(new_posts)} new entries:", flush=True)
        for p in new_posts:
            print(f"  {p['url_path']} ({p['language']})", flush=True)
        emit_github_output(False, 0, [])
        return 0

    # Build mutated array: existing verbatim + new UPPERCASE entries
    new_entries = build_new_entries(new_posts)
    mutated = existing_entries + new_entries

    # POST
    print(f"[api_sync] POSTing {len(mutated)} total entries to Weglot...", flush=True)
    try:
        status, response = post_weglot_settings(private_key, {"excluded_paths": mutated})
    except Exception as e:
        emit_github_output(False, 0, [], error=f"POST failed: {e}")
        return 1

    if not (200 <= status < 300):
        msg = f"HTTP {status}: {response}"
        print(f"[api_sync] ERROR: POST failed: {msg}", file=sys.stderr)
        emit_github_output(False, 0, [], error=f"post_failed: {msg}")
        return 1

    print(f"[api_sync] POST succeeded (HTTP {status})", flush=True)

    # Verify with second GET
    print("[api_sync] Verifying with second GET...", flush=True)
    try:
        verify = fetch_weglot_settings(public_key)
    except Exception as e:
        emit_github_output(False, 0, [], error=f"verify_GET_failed: {e}")
        return 1

    pre_map = {
        e["value"]: sorted(e.get("excluded_languages") or [])
        for e in existing_entries
        if e.get("excluded_languages")
    }
    post_map = {
        e["value"]: sorted(e.get("excluded_languages") or [])
        for e in verify.get("excluded_paths", [])
    }
    stripped = [v for v, langs in pre_map.items() if langs and not post_map.get(v)]

    if stripped:
        count = len(stripped)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = DATA_DIR / f"weglot-backup-{ts}.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(backup_path, "w") as f:
            json.dump(
                {"pre_post": existing_entries, "post_get": verify.get("excluded_paths", [])},
                f,
                indent=2,
            )
        print(
            f"CRITICAL: Weglot regression — {count} entries lost excluded_languages. "
            f"Backup: {backup_path}",
            file=sys.stderr,
        )
        emit_github_output(False, 0, [], error=f"weglot_bug_regressed stripped={count}")
        return 2

    # Update state
    for post in new_posts:
        state.setdefault("exclusions", {})[post["slug"]] = {
            "language": post["language"],
            "excluded_from": compute_excluded_languages(post["language"]),
            "source": "api",
            "url_path": post["url_path"],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    save_state(state)
    generate_sitemap_exclusion_data(state)

    slugs = [p["slug"] for p in new_posts]
    emit_github_output(True, len(new_posts), slugs)
    print(f"[api_sync] Done. Added {len(new_posts)} entries: {', '.join(slugs)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
