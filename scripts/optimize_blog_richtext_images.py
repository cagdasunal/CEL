#!/usr/bin/env python3
"""
optimize_blog_richtext_images.py — Batch-optimize Blog Post rich-text images
=============================================================================

Walks every Blog Post item via Webflow Data API, finds <img> tags inside the
``post-body`` RichText field, downloads each image, re-encodes to AVIF
(quality 50 by default, max-width 700px), uploads the AVIF back to Webflow,
and (with --apply) PATCHes the post-body HTML so the new URLs go live.

Designed to run nightly via GitHub Actions cron + ad-hoc via workflow_dispatch.

CLI
---
  python3 scripts/optimize_blog_richtext_images.py --site cel --dry-run
  python3 scripts/optimize_blog_richtext_images.py --site cel --limit 5 --dry-run
  python3 scripts/optimize_blog_richtext_images.py --site cel --posts SLUG1,SLUG2 --apply
  python3 scripts/optimize_blog_richtext_images.py --site cel --apply

Default mode is --dry-run. --apply is required to perform CMS PATCHes.
See ~/.claude/plans/i-have-performance-issues-polished-bengio.md for the full plan.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

# --- repo path bootstrap --------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse asset_upload.py's HTTP client + auth + tracking — DO NOT duplicate.
from asset_upload import (  # noqa: E402  (path-bootstrapped import)
    APIError,
    MAX_FILE_SIZE,
    NetworkError,
    WEBFLOW_API_BASE,
    api_request,
    build_multipart_body,
    get_api_token,
    get_tracking_path,
    load_site_config,
    load_tracking,
    save_tracking,
)

# --- constants ------------------------------------------------------------
COLLECTION_ID = "667453c576e8d35c454ccaae"  # Blog Posts collection (cel site)
RICHTEXT_FIELD_SLUG = "post-body"

DEFAULT_QUALITY = 50              # AVIF q=50 — locked decision §5.2
DEFAULT_MAX_WIDTH = 700           # Blog wrapper width — locked decision §5.3
DEFAULT_MIN_SAVING_PCT = 30.0     # Skip if savings <30% — locked §5.12

DEFAULT_LOG_PATH = ROOT / "data" / "blog-optimization-log.jsonl"
DEFAULT_BACKUP_DIR = ROOT / "data" / "blog-richtext-backup"

RATE_LIMIT_SLEEP_SEC = 0.6        # 100 req/min — under CMS plan's 120/min ceiling
HOSTED_URL_POLL_TRIES = 5
HOSTED_URL_POLL_SLEEP_SEC = 2.0
ALREADY_AVIF_SKIP_SIZE = 200 * 1024  # 200 KB — locked §6 ambiguity #1
DOWNLOAD_TIMEOUT_SEC = 30
USER_AGENT = "blog-richtext-optimizer/1.0"


# =========================================================================
# HTML parsing — find <img src>; rewriting via str.replace (URLs are unique)
# =========================================================================
class ImageSrcCollector(HTMLParser):
    """Walk HTML and collect <img src='...'> URLs, skipping data: URIs.

    Stdlib only per locked decision §5.6. Used only for FINDING images; the
    rewrite path is plain str.replace because Webflow CDN URLs are uniquely
    identifying within a post body (no risk of accidental hit elsewhere).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.srcs: list[str] = []  # ordered, may contain duplicates

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        for k, v in attrs:
            if k.lower() == "src" and v and not v.startswith("data:"):
                self.srcs.append(v)
                return

    # Webflow rich text always emits <img> as a void start tag; treat
    # self-closing form identically.
    handle_startendtag = handle_starttag


def find_image_srcs(html: str) -> list[str]:
    """Return ordered list of image src URLs. De-duplicates while preserving order."""
    p = ImageSrcCollector()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # html.parser raises rarely on truly broken input
        pass
    seen: set[str] = set()
    out: list[str] = []
    for u in p.srcs:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def rewrite_image_srcs(html: str, src_map: dict[str, str]) -> str:
    """Replace ``<img src="OLD">`` with ``<img src="NEW">`` in html.

    Webflow rich-text uses double-quoted attributes; we handle single quotes
    too as belt-and-braces. URLs are unique enough that direct str.replace is
    safe (no risk of clobbering some other attribute that happens to contain
    the URL substring).
    """
    out = html
    for old, new in src_map.items():
        if not old or old == new:
            continue
        out = out.replace(f'src="{old}"', f'src="{new}"')
        out = out.replace(f"src='{old}'", f"src='{new}'")
    return out


# =========================================================================
# Image I/O + AVIF encode
# =========================================================================
def head_image(url: str, timeout: int = DOWNLOAD_TIMEOUT_SEC) -> tuple[int, str]:
    """HEAD an image URL. Returns (content_length_bytes, content_type_lc).

    On any failure returns (0, "") — caller decides what to do next.
    """
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            length = int(resp.headers.get("content-length") or 0)
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            return length, ctype
    except Exception:
        return 0, ""


def download_image(url: str, timeout: int = DOWNLOAD_TIMEOUT_SEC) -> bytes:
    """Download image bytes with one retry on 503/timeout."""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt == 0:
                time.sleep(2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 0:
                time.sleep(2)
                continue
            raise
    return b""  # unreachable; kept for type checker


def is_avif(url: str, ctype: str) -> bool:
    """Treat as AVIF when content-type matches OR URL path ends in .avif."""
    if ctype == "image/avif":
        return True
    return url.lower().rsplit("?", 1)[0].rsplit("#", 1)[0].endswith(".avif")


def encode_avif(image_bytes: bytes, max_width: int, quality: int) -> bytes:
    """Decode → resize (downscale only) → re-encode AVIF.

    Aspect-preserving; uses ``thumbnail((max_width, max_width*100))`` so a
    very tall portrait (height >> width) does not get height-capped before
    its width hits max_width — matches plan review-hotspot §8.2.
    """
    # Imports are local so the module imports cleanly when Pillow is missing
    # (e.g., the pure-Python dashboard generator never needs Pillow).
    from PIL import Image  # type: ignore[import-not-found]
    import pillow_avif  # noqa: F401  (registers AVIF plugin with Pillow)

    img = Image.open(io.BytesIO(image_bytes))

    # Color-space coercion for AVIF safety (palette and 1-bit modes can lose
    # transparency or fidelity through libavif). RGB / RGBA is always safe.
    if img.mode in ("P", "1"):
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode == "CMYK":
        img = img.convert("RGB")

    # Downscale only — never upscale.
    if img.width > max_width:
        img.thumbnail((max_width, max_width * 100), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="AVIF", quality=quality)
    return out.getvalue()


# =========================================================================
# Webflow Data API helpers
# =========================================================================
def list_blog_posts(
    token: str,
    slugs_filter: set[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Paginate /v2/collections/{id}/items. Returns list of CMS items.

    When ``slugs_filter`` is given, only items whose slug is in the set are
    returned. ``limit`` (post-filter) caps total returned.
    """
    items: list[dict] = []
    offset = 0
    page_size = 100
    while True:
        url = f"{WEBFLOW_API_BASE}/collections/{COLLECTION_ID}/items?limit={page_size}&offset={offset}"
        resp = _rate_limited_request("GET", url, token)
        page = resp.get("items", []) if isinstance(resp, dict) else []
        if not page:
            break
        for it in page:
            slug = it.get("fieldData", {}).get("slug", "")
            if slugs_filter is not None and slug not in slugs_filter:
                continue
            items.append(it)
            if limit and len(items) >= limit:
                return items
        if len(page) < page_size:
            break
        offset += page_size
    return items


def patch_blog_post(token: str, item_id: str, post_body: str, is_draft: bool, is_archived: bool) -> dict:
    """PATCH /v2/collections/{id}/items/{item_id} — update post-body only."""
    url = f"{WEBFLOW_API_BASE}/collections/{COLLECTION_ID}/items/{item_id}"
    payload = {
        "fieldData": {RICHTEXT_FIELD_SLUG: post_body},
        "isDraft": is_draft,
        "isArchived": is_archived,
    }
    return _rate_limited_request("PATCH", url, token, data=payload)


def publish_collection_items(token: str, item_ids: list[str]) -> dict:
    """POST /v2/collections/{id}/items/publish — make staged content live for
    SPECIFIC item IDs.

    SAFETY: only call this on item IDs that were already published before our
    PATCH. Caller MUST verify ``was_published_before == True`` (i.e. the item
    had a non-null ``lastPublished`` AND ``isDraft=False`` PRIOR to PATCH).
    Publishing a draft item via this endpoint would make it live — exactly the
    behavior we are guarding against.

    This is item-level publishing, NOT site-wide publishing. ``publish_site``
    is BANNED by ``rules/workflow.md §7.1``; this endpoint is permitted because
    its scope is bounded to specific items the user already chose to publish.
    """
    if not item_ids:
        return {}
    url = f"{WEBFLOW_API_BASE}/collections/{COLLECTION_ID}/items/publish"
    payload = {"itemIds": item_ids}
    return _rate_limited_request("POST", url, token, data=payload)


def upload_avif(image_bytes: bytes, file_name: str, site_id: str, token: str) -> dict:
    """Upload AVIF bytes via Webflow's 2-step S3 presigned flow.

    Mirrors scripts/asset_upload.py:cmd_upload step 1+2 — but receives bytes
    in-memory rather than reading from disk, so the image flows
    download → encode → upload without staging. Returns
    ``{'asset_id', 'hostedUrl', 'md5', 'size'}``.
    """
    import hashlib
    import tempfile

    md5 = hashlib.md5(image_bytes).hexdigest()
    size = len(image_bytes)

    if size > MAX_FILE_SIZE:
        raise ValueError(f"AVIF too large after encode: {size} bytes (max {MAX_FILE_SIZE})")

    # Step 1: register asset
    register_body = {"fileName": file_name, "fileHash": md5}
    register_url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    register_resp = _rate_limited_request("POST", register_url, token, data=register_body)
    asset_id = register_resp.get("id")
    upload_url = register_resp.get("uploadUrl")
    upload_details = register_resp.get("uploadDetails", {})
    if not asset_id or not upload_url:
        raise RuntimeError(f"Webflow register response missing fields: {register_resp}")

    # Step 2: S3 multipart POST. build_multipart_body wants a Path on disk.
    with tempfile.NamedTemporaryFile(suffix=".avif", delete=False) as tf:
        tf.write(image_bytes)
        tmp_path = Path(tf.name)
    try:
        body, content_type = build_multipart_body(upload_details, tmp_path)
        s3_req = urllib.request.Request(
            upload_url,
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with urllib.request.urlopen(s3_req) as s3_resp:
            if s3_resp.status not in (200, 201, 204):
                raise RuntimeError(f"S3 upload failed: HTTP {s3_resp.status}")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Step 3: poll asset endpoint for hostedUrl (Webflow indexes lazily)
    hosted_url = ""
    asset_get_url = f"{WEBFLOW_API_BASE}/assets/{asset_id}"
    last_err: Exception | None = None
    for attempt in range(HOSTED_URL_POLL_TRIES):
        try:
            asset_resp = _rate_limited_request("GET", asset_get_url, token)
            hosted_url = asset_resp.get("hostedUrl") or ""
            if hosted_url:
                break
        except APIError as e:
            last_err = e
            # 404 right after upload is normal — keep polling.
            if e.status_code != 404:
                raise
        time.sleep(HOSTED_URL_POLL_SLEEP_SEC)
    if not hosted_url:
        raise RuntimeError(f"Asset {asset_id} uploaded but hostedUrl never appeared (last_err={last_err})")

    return {"asset_id": asset_id, "hostedUrl": hosted_url, "md5": md5, "size": size}


def _rate_limited_request(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """Wrap api_request with sleep + 429 exponential backoff (2/4/8 then give up).

    Locked §5.7 — CMS plan rate limit is 120/min; 600 ms → 100/min safe margin.
    """
    last_err: APIError | None = None
    for backoff in (0.0, 2.0, 4.0, 8.0):
        if backoff:
            time.sleep(backoff)
        try:
            resp = api_request(method, url, token, data=data)
            time.sleep(RATE_LIMIT_SLEEP_SEC)
            return resp
        except APIError as e:
            if e.status_code == 429:
                last_err = e
                continue
            raise
    assert last_err is not None
    raise last_err


# =========================================================================
# Filename derivation
# =========================================================================
def derive_avif_filename(slug: str, idx: int, src_url: str) -> str:
    """Construct a stable AVIF filename from (post slug, image index, original).

    Example:
        slug='6-tips-...-correctly', idx=1, src='....pexels-thirdman-6503000.jpg'
        → '6-tips-...-correctly-1-pexels-thirdman-6503000.avif'

    The original stem is kept (sans extension) so editors can recognize the
    image in Webflow's Asset Manager. Filename is filesystem-safe (no spaces,
    no slashes — Webflow CDN replaces unsupported chars anyway).

    Length budget: Webflow's asset registration endpoint rejects fileName
    fields >~100 chars with HTTP 400 ``"File name is too long"``. Discovered
    on 2026-05-09 against Italian/German slugs that exceeded the original
    plan's ``slug[:80] + stem[:60]`` ceiling. Total cap now ~80 chars to
    leave headroom for URL-encoded percent sequences (e.g. ``%20`` for
    space) that Webflow stores literally on disk.
    """
    # Original stem: last path segment, drop query/hash, drop extension
    last_seg = src_url.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    stem = last_seg.rsplit(".", 1)[0] if "." in last_seg else last_seg
    # Strip any leading hex-prefix Webflow tacks on (24 hex + underscore).
    if len(stem) > 25 and "_" in stem[:30] and all(c in "0123456789abcdef" for c in stem[:24]):
        stem = stem.split("_", 1)[1]
    safe_slug = slug[:40]
    safe_stem = stem[:30]
    return f"{safe_slug}-{idx}-{safe_stem}.avif"


# =========================================================================
# Per-post processor
# =========================================================================
def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_iso_compact() -> str:
    """Filesystem-safe UTC stamp: 20260509T110000Z (no colons)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def process_post(
    *,
    item: dict,
    site_id: str,
    token: str,
    quality: int,
    max_width: int,
    min_saving_pct: float,
    apply: bool,
    auto_publish: bool,
    backup_dir: Path,
    log_path: Path,
    run_id: str,
    tracking_path: Path,
    tracking: dict,
) -> dict:
    """Process one Blog Post item. Returns a per-post summary dict.

    On --dry-run: downloads + encodes + decides; no Webflow writes, no upload.
    On --apply: uploads + PATCHes if all images succeeded.

    Atomicity (review hotspot §8.4): if any image upload fails in --apply
    mode, the post's PATCH is skipped — partial state never lands in CMS.
    """
    post_id = item.get("id", "?")
    field_data = item.get("fieldData", {}) or {}
    slug = field_data.get("slug", "?")
    post_body = field_data.get(RICHTEXT_FIELD_SLUG, "") or ""
    is_draft = bool(item.get("isDraft", False))
    is_archived = bool(item.get("isArchived", False))
    last_published = item.get("lastPublished")

    # SAFEGUARD for auto-publish: only items that were ALREADY published
    # before this run (non-empty lastPublished AND not currently a draft) are
    # eligible for ``publish_collection_items``. Drafts stay drafts no matter
    # what — the user explicitly required this guard. See
    # publish_collection_items() docstring for context.
    was_published_before = (
        bool(last_published)
        and is_draft is False
        and is_archived is False
    )

    summary = {
        "post_slug": slug,
        "post_id": post_id,
        "image_count": 0,
        "replaced": 0,
        "skipped_avif": 0,
        "skipped_small": 0,
        "errors": 0,
        "old_bytes_total": 0,
        "new_bytes_total": 0,
        "patched": False,
        "published": False,
        "publish_skipped_reason": "",
        "post_dirty": False,
        "was_published_before": was_published_before,
    }

    srcs = find_image_srcs(post_body)
    summary["image_count"] = len(srcs)
    if not srcs:
        return summary

    src_map: dict[str, str] = {}        # old_url → new_hosted_url (only for replaced)
    per_image_logs: list[dict] = []     # one entry per image, written to JSONL at end
    any_error = False

    for idx, src in enumerate(srcs, start=1):
        log: dict = {
            "ts": utc_iso(),
            "run_id": run_id,
            "post_slug": slug,
            "post_id": post_id,
            "old_url": src,
            "new_url": "",
            "old_bytes": 0,
            "new_bytes": 0,
            "saving_pct": 0.0,
            "action": "error",
            "error": None,
        }

        try:
            # HEAD → decide quickly whether to skip already-AVIF small images
            head_len, head_ctype = head_image(src)
            log["old_bytes"] = head_len
            if is_avif(src, head_ctype) and 0 < head_len <= ALREADY_AVIF_SKIP_SIZE:
                log["action"] = "skipped_avif"
                summary["skipped_avif"] += 1
                per_image_logs.append(log)
                continue

            # Download → encode
            orig_bytes = download_image(src)
            old_size = len(orig_bytes)
            log["old_bytes"] = old_size

            avif_bytes = encode_avif(orig_bytes, max_width=max_width, quality=quality)
            new_size = len(avif_bytes)
            log["new_bytes"] = new_size
            saving_pct = ((old_size - new_size) / old_size * 100.0) if old_size > 0 else 0.0
            log["saving_pct"] = round(saving_pct, 2)

            if old_size > 0 and saving_pct < min_saving_pct:
                log["action"] = "skipped_small"
                summary["skipped_small"] += 1
                per_image_logs.append(log)
                continue

            file_name = derive_avif_filename(slug, idx, src)
            summary["old_bytes_total"] += old_size
            summary["new_bytes_total"] += new_size

            if apply:
                # Real upload + record in tracking
                upload_resp = upload_avif(avif_bytes, file_name, site_id, token)
                new_url = upload_resp["hostedUrl"]
                tracking[file_name] = {
                    "asset_id": upload_resp["asset_id"],
                    "md5": upload_resp["md5"],
                    "size": new_size,
                    "alt_text": file_name.rsplit(".", 1)[0].replace("-", " ").title(),
                }
                log["new_url"] = new_url
                src_map[src] = new_url
            else:
                # Dry-run — predict the URL but do nothing destructive
                log["new_url"] = f"<would-upload>{file_name}"

            log["action"] = "replaced"
            summary["replaced"] += 1
        except (APIError, NetworkError, ValueError, RuntimeError, urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            log["action"] = "error"
            log["error"] = f"{type(e).__name__}: {e}"
            summary["errors"] += 1
            any_error = True

        per_image_logs.append(log)

    # Atomic per-post: in --apply mode, abort PATCH on any image error
    if apply and any_error:
        # Roll back by NOT patching — CMS stays clean.
        summary["patched"] = False
        summary["publish_skipped_reason"] = "image_errors_in_post"
    elif apply and src_map:
        # Backup body before mutation
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"{slug}__{utc_iso_compact()}.html"
        backup_file.write_text(post_body, encoding="utf-8")

        new_body = rewrite_image_srcs(post_body, src_map)
        if new_body != post_body:
            patch_blog_post(token, post_id, new_body, is_draft, is_archived)
            summary["patched"] = True
            summary["post_dirty"] = True
            # Persist tracking after a successful PATCH
            save_tracking(tracking_path, tracking)

            # Auto-publish (item-level, NOT site-level) — gated by the
            # was_published_before safeguard. Drafts NEVER get published here.
            if auto_publish and was_published_before:
                try:
                    publish_collection_items(token, [post_id])
                    summary["published"] = True
                except (APIError, NetworkError) as e:
                    # PATCH succeeded; publish failed. Log + continue. The
                    # user can manually publish via Webflow Designer later.
                    summary["publish_skipped_reason"] = (
                        f"publish_api_error: {type(e).__name__}: {e}"[:200]
                    )
            elif auto_publish and not was_published_before:
                summary["publish_skipped_reason"] = (
                    "post_was_draft_or_never_published"
                )
            elif not auto_publish:
                summary["publish_skipped_reason"] = "auto_publish_disabled"
    else:
        # Dry-run with image changes — note we WOULD patch
        summary["post_dirty"] = bool(src_map) or any(
            log["action"] == "replaced" for log in per_image_logs
        )

    # Append per-image logs to JSONL log file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        for entry in per_image_logs:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return summary


# =========================================================================
# CLI
# =========================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Optimize blog post rich-text images to AVIF and update Webflow CMS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--site", required=True, help="Site nickname (registry.json key, e.g., 'cel')")
    p.add_argument("--quality", type=int, default=DEFAULT_QUALITY,
                   help=f"AVIF quality 1-100 (default: {DEFAULT_QUALITY})")
    p.add_argument("--max-width", type=int, default=DEFAULT_MAX_WIDTH,
                   help=f"Max image width in px (default: {DEFAULT_MAX_WIDTH})")
    p.add_argument("--min-saving-pct", type=float, default=DEFAULT_MIN_SAVING_PCT,
                   help=f"Skip if AVIF saves <N%% (default: {DEFAULT_MIN_SAVING_PCT})")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N posts (default: all)")
    p.add_argument("--posts", default="",
                   help="Comma-separated slugs to filter to (default: all)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Default. List what would change, no Webflow writes.")
    mode.add_argument("--apply", action="store_true",
                      help="Actually upload + PATCH. Required for writes.")

    publish_group = p.add_mutually_exclusive_group()
    publish_group.add_argument("--auto-publish", dest="auto_publish",
                               action="store_true", default=True,
                               help=("Default. After successful PATCH, item-publish "
                                     "ONLY items that were already published before "
                                     "the run (lastPublished != null AND isDraft=False). "
                                     "Drafts are never published. NEVER calls "
                                     "data_sites_tool.publish_site (per workflow.md §7.1)."))
    publish_group.add_argument("--no-auto-publish", dest="auto_publish",
                               action="store_false",
                               help="Disable auto-publish. Posts are PATCHed only; staged "
                                    "content stays staged until you manually publish.")

    p.add_argument("--log-jsonl", default=str(DEFAULT_LOG_PATH),
                   help=f"JSONL log path (default: {DEFAULT_LOG_PATH.relative_to(ROOT)})")
    p.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR),
                   help=f"Backup dir for original post-body HTML (default: {DEFAULT_BACKUP_DIR.relative_to(ROOT)})")
    p.add_argument("--token", default=None, help="Webflow API token (else WEBFLOW_API_TOKEN env / .env)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # --apply wins over the default --dry-run when both flag-name properties
    # are reachable on argparse output (mutually exclusive ensures only one
    # is True at a time, but the default-True dry_run flag stays True until
    # --apply is given).
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
        print("ERROR: Webflow API token missing (use --token, WEBFLOW_API_TOKEN env, or .env)", file=sys.stderr)
        return 1

    slugs_filter: set[str] | None = None
    if args.posts:
        slugs_filter = {s.strip() for s in args.posts.split(",") if s.strip()}

    log_path = Path(args.log_jsonl)
    backup_dir = Path(args.backup_dir)
    tracking_path = get_tracking_path(site_config)
    tracking = load_tracking(tracking_path)
    run_id = uuid.uuid4().hex[:12]

    print(f"\n{'=' * 70}")
    print(f"  BLOG IMAGE OPTIMIZER — site={args.site}  mode={'APPLY' if apply else 'DRY-RUN'}")
    print(f"  quality={args.quality}  max-width={args.max_width}  min-saving-pct={args.min_saving_pct}")
    print(f"  auto-publish={'ON' if args.auto_publish else 'OFF'}"
          + (" (only published items, never drafts)" if args.auto_publish else ""))
    if args.limit:
        print(f"  limit={args.limit}")
    if slugs_filter:
        print(f"  posts={sorted(slugs_filter)}")
    print(f"  run_id={run_id}")
    print(f"{'=' * 70}\n")

    # List target posts
    print("Listing Blog Posts...", flush=True)
    items = list_blog_posts(token, slugs_filter=slugs_filter, limit=args.limit)
    print(f"  Found {len(items)} post(s) to process.\n")

    if not items:
        print("No posts matched. Done.")
        return 0

    # Per-post processing
    totals = {
        "posts": len(items),
        "patched": 0,
        "published": 0,
        "publish_skipped_drafts": 0,
        "would_patch": 0,
        "image_count": 0,
        "replaced": 0,
        "skipped_avif": 0,
        "skipped_small": 0,
        "errors": 0,
        "old_bytes_total": 0,
        "new_bytes_total": 0,
    }
    any_error = False

    for n, item in enumerate(items, start=1):
        slug = item.get("fieldData", {}).get("slug", "?")
        print(f"[{n}/{len(items)}] {slug}", flush=True)
        summary = process_post(
            item=item,
            site_id=site_id,
            token=token,
            quality=args.quality,
            max_width=args.max_width,
            min_saving_pct=args.min_saving_pct,
            apply=apply,
            auto_publish=args.auto_publish,
            backup_dir=backup_dir,
            log_path=log_path,
            run_id=run_id,
            tracking_path=tracking_path,
            tracking=tracking,
        )

        totals["image_count"] += summary["image_count"]
        totals["replaced"] += summary["replaced"]
        totals["skipped_avif"] += summary["skipped_avif"]
        totals["skipped_small"] += summary["skipped_small"]
        totals["errors"] += summary["errors"]
        totals["old_bytes_total"] += summary["old_bytes_total"]
        totals["new_bytes_total"] += summary["new_bytes_total"]
        if summary["patched"]:
            totals["patched"] += 1
        elif summary["post_dirty"] and not apply:
            totals["would_patch"] += 1
        if summary["published"]:
            totals["published"] += 1
        elif (
            summary["patched"]
            and args.auto_publish
            and summary["publish_skipped_reason"] == "post_was_draft_or_never_published"
        ):
            totals["publish_skipped_drafts"] += 1

        if summary["errors"]:
            any_error = True

        # Per-post line
        if summary["image_count"] == 0:
            print(f"     no images in post-body")
        else:
            saved = summary["old_bytes_total"] - summary["new_bytes_total"]
            pct = (saved / summary["old_bytes_total"] * 100.0) if summary["old_bytes_total"] > 0 else 0.0
            verb = "patched" if summary["patched"] else (
                "would patch" if summary["post_dirty"] and not apply else "no change"
            )
            pub_note = ""
            if summary["patched"]:
                if summary["published"]:
                    pub_note = " + PUBLISHED"
                elif args.auto_publish and summary["publish_skipped_reason"] == "post_was_draft_or_never_published":
                    pub_note = " (kept as draft — was never published)"
                elif not args.auto_publish:
                    pub_note = " (auto-publish disabled)"
                elif summary["publish_skipped_reason"].startswith("publish_api_error"):
                    pub_note = f" (publish FAILED: {summary['publish_skipped_reason'][:80]})"
            print(
                f"     {summary['image_count']} image(s): "
                f"replaced={summary['replaced']} "
                f"skipped_avif={summary['skipped_avif']} "
                f"skipped_small={summary['skipped_small']} "
                f"errors={summary['errors']} "
                f"saved={saved}B ({pct:.1f}%) {verb}{pub_note}"
            )

    # Final totals
    saved = totals["old_bytes_total"] - totals["new_bytes_total"]
    pct = (saved / totals["old_bytes_total"] * 100.0) if totals["old_bytes_total"] > 0 else 0.0
    print(f"\n{'-' * 70}")
    print(f"  TOTAL — posts={totals['posts']}  images={totals['image_count']}")
    print(f"    replaced={totals['replaced']}  skipped_avif={totals['skipped_avif']}  "
          f"skipped_small={totals['skipped_small']}  errors={totals['errors']}")
    print(f"    bytes:  {totals['old_bytes_total']:,} → {totals['new_bytes_total']:,}  "
          f"saved {saved:,} ({pct:.1f}%)")
    if apply:
        print(f"    posts patched:    {totals['patched']}/{totals['posts']}")
        if args.auto_publish:
            print(f"    posts published:  {totals['published']}/{totals['patched'] or 1}"
                  f"  (drafts preserved as drafts: {totals['publish_skipped_drafts']})")
    else:
        print(f"    posts that would be patched: {totals['would_patch']}/{totals['posts']}")
    print(f"  log: {log_path}")
    if not apply:
        print(f"  mode: DRY-RUN — to actually write, re-run with --apply")

    return 2 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
