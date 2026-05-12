#!/usr/bin/env python3
"""
strip_placeholder_images.py — Remove `image-placeholder.svg` references from
every Blog Post's `post-body` RichText field.

Reuses scripts/optimize_blog_richtext_images.py helpers for: site config,
Webflow Data API client, rate-limited pagination, item-level publish guard.

CLI
---
  # Dry-run (default). Shows what would change, no Webflow writes.
  python3 scripts/strip_placeholder_images.py --site cel

  # Apply for real.
  python3 scripts/strip_placeholder_images.py --site cel --apply

  # Filter to specific posts.
  python3 scripts/strip_placeholder_images.py --site cel --posts SLUG1,SLUG2

Auto-publish guard mirrors optimize_blog_richtext_images.py exactly:
ONLY items with `lastPublished != null AND isDraft=False AND isArchived=False`
are item-published after a successful PATCH. Drafts are NEVER published.

NEVER calls `data_sites_tool.publish_site` (banned by rules/workflow.md §7.1).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import uuid
from pathlib import Path

# --- repo path bootstrap --------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the optimizer's HTTP client, auth, pagination, and publish helpers.
from optimize_blog_richtext_images import (  # noqa: E402
    COLLECTION_ID,
    RICHTEXT_FIELD_SLUG,
    list_blog_posts,
    patch_blog_post,
    publish_collection_items,
    utc_iso,
    utc_iso_compact,
)
from asset_upload import (  # noqa: E402
    APIError,
    NetworkError,
    get_api_token,
    load_site_config,
)

# --- constants ------------------------------------------------------------
PLACEHOLDER_URL_FRAGMENT = "image-placeholder.svg"

DEFAULT_LOG_PATH = ROOT / "data" / "blog-placeholder-removal-log.jsonl"
DEFAULT_BACKUP_DIR = ROOT / "data" / "blog-placeholder-removal-backup"

# 1) Webflow rich-text figure wrapper around an <img> with placeholder src.
#    Tempered greedy match so adjacent <figure>s don't get fused.
_FIGURE_RE = re.compile(
    r"<figure\b[^>]*?>(?:(?!</figure>).)*?<img\b[^>]*?"
    + re.escape(PLACEHOLDER_URL_FRAGMENT)
    + r"[^>]*?>(?:(?!</figure>).)*?</figure>",
    flags=re.IGNORECASE | re.DOTALL,
)
# 2) Any leftover standalone <img ...image-placeholder.svg...>.
_IMG_RE = re.compile(
    r"<img\b[^>]*?"
    + re.escape(PLACEHOLDER_URL_FRAGMENT)
    + r"[^>]*?/?>",
    flags=re.IGNORECASE,
)


def strip_placeholders(html: str) -> tuple[str, int]:
    """Return (new_html, count_removed)."""
    if not html:
        return html, 0
    new_html, fig_n = _FIGURE_RE.subn("", html)
    new_html, img_n = _IMG_RE.subn("", new_html)
    return new_html, fig_n + img_n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Remove image-placeholder.svg from every Blog Post's post-body.",
    )
    p.add_argument("--site", required=True, help="Site nickname (registry.json key)")
    p.add_argument("--limit", type=int, default=None, help="Process at most N posts")
    p.add_argument("--posts", default="", help="Comma-separated slugs to filter to")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Default. List what would change, no Webflow writes.")
    mode.add_argument("--apply", action="store_true",
                      help="Actually PATCH posts. Required for writes.")

    pub = p.add_mutually_exclusive_group()
    pub.add_argument("--auto-publish", dest="auto_publish",
                     action="store_true", default=True,
                     help="After PATCH, item-publish ONLY previously-published items.")
    pub.add_argument("--no-auto-publish", dest="auto_publish",
                     action="store_false",
                     help="PATCH only; staged content stays staged.")

    p.add_argument("--log-jsonl", default=str(DEFAULT_LOG_PATH),
                   help=f"JSONL log path (default: {DEFAULT_LOG_PATH.relative_to(ROOT)})")
    p.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR),
                   help=f"Backup dir (default: {DEFAULT_BACKUP_DIR.relative_to(ROOT)})")
    p.add_argument("--token", default=None, help="Webflow API token (else WEBFLOW_API_TOKEN env / .env)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    apply = bool(args.apply)
    if apply:
        args.dry_run = False

    site_config = load_site_config(args.site)
    site_id = site_config.get("webflow_site_id")
    if not site_id:
        print(f"ERROR: site '{args.site}' has no webflow_site_id", file=sys.stderr)
        return 1

    token = get_api_token(args.token)
    if not token:
        print("ERROR: Webflow API token missing (use --token, WEBFLOW_API_TOKEN env, or .env)",
              file=sys.stderr)
        return 1

    slugs_filter: set[str] | None = None
    if args.posts:
        slugs_filter = {s.strip() for s in args.posts.split(",") if s.strip()}

    log_path = Path(args.log_jsonl)
    backup_dir = Path(args.backup_dir)
    run_id = uuid.uuid4().hex[:12]

    print(f"\n{'=' * 70}")
    print(f"  PLACEHOLDER STRIP — site={args.site}  mode={'APPLY' if apply else 'DRY-RUN'}")
    print(f"  auto-publish={'ON' if args.auto_publish else 'OFF'}"
          + (" (only previously-published items)" if args.auto_publish else ""))
    if args.limit:
        print(f"  limit={args.limit}")
    if slugs_filter:
        print(f"  posts={sorted(slugs_filter)}")
    print(f"  run_id={run_id}")
    print(f"{'=' * 70}\n")

    print("Listing Blog Posts...", flush=True)
    items = list_blog_posts(token, slugs_filter=slugs_filter, limit=args.limit)
    print(f"  Found {len(items)} post(s) to scan.\n")

    totals = {
        "posts_scanned": len(items),
        "posts_modified": 0,
        "total_removed": 0,
        "published": 0,
        "errors": 0,
    }
    any_error = False
    log_lines: list[str] = []

    for n, item in enumerate(items, start=1):
        post_id = item.get("id", "?")
        fd = item.get("fieldData", {}) or {}
        slug = fd.get("slug", "?")
        post_body = fd.get(RICHTEXT_FIELD_SLUG, "") or ""
        is_draft = bool(item.get("isDraft", False))
        is_archived = bool(item.get("isArchived", False))
        last_published = item.get("lastPublished")
        was_published_before = (
            bool(last_published) and is_draft is False and is_archived is False
        )

        new_body, removed = strip_placeholders(post_body)
        if removed == 0:
            continue

        totals["posts_modified"] += 1
        totals["total_removed"] += removed

        log_entry = {
            "ts": utc_iso(),
            "run_id": run_id,
            "post_slug": slug,
            "post_id": post_id,
            "removed_count": removed,
            "was_published_before": was_published_before,
            "action": "would_strip" if not apply else "stripped",
            "published": False,
            "error": None,
        }

        if apply:
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_file = backup_dir / f"{slug}__{utc_iso_compact()}.html"
                backup_file.write_text(post_body, encoding="utf-8")

                patch_blog_post(token, post_id, new_body, is_draft, is_archived)

                if args.auto_publish and was_published_before:
                    try:
                        publish_collection_items(token, [post_id])
                        log_entry["published"] = True
                        totals["published"] += 1
                    except (APIError, NetworkError) as e:
                        log_entry["error"] = (
                            f"publish_failed: {type(e).__name__}: {e}"[:200]
                        )
            except (APIError, NetworkError, urllib.error.HTTPError,
                    urllib.error.URLError, OSError, ValueError) as e:
                log_entry["action"] = "error"
                log_entry["error"] = f"{type(e).__name__}: {e}"
                totals["errors"] += 1
                any_error = True

        log_lines.append(json.dumps(log_entry, ensure_ascii=False))

        verb = "would strip" if not apply else "stripped"
        pub_note = ""
        if apply and log_entry["published"]:
            pub_note = " + PUBLISHED"
        elif apply and was_published_before and args.auto_publish and log_entry.get("error"):
            pub_note = f" (publish FAILED: {log_entry['error'][:80]})"
        elif apply and not was_published_before:
            pub_note = " (kept as draft — was never published)"
        print(f"[{n}/{len(items)}] {slug}: {verb} {removed} placeholder(s){pub_note}")

    if log_lines:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for line in log_lines:
                fh.write(line + "\n")

    print(f"\n{'-' * 70}")
    print(f"  posts_scanned={totals['posts_scanned']}  "
          f"posts_modified={totals['posts_modified']}  "
          f"total_removed={totals['total_removed']}  "
          f"errors={totals['errors']}")
    if apply:
        print(f"  posts published: {totals['published']}/{totals['posts_modified']}")
    print(f"  mode: {'APPLY' if apply else 'DRY-RUN — re-run with --apply to write'}")
    print(f"  log: {log_path}")

    return 2 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
