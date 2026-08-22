#!/usr/bin/env python3
"""
avif_optimizer.py — Reusable AVIF encode + Webflow asset upload utilities
==========================================================================

Extracted from optimize_blog_richtext_images.py so multiple callers can share
the same AVIF encode + 2-step S3 upload + rate-limited Webflow Data API
plumbing. The functions here are deliberately pure-ish: they take bytes /
strings, return bytes / dicts, and have no module-level side effects.

Callers (as of 2026-05-12):
  - scripts/optimize_blog_richtext_images.py — blog post body images
  - tools/fidelo/fetch_course_heroes.py      — Fidelo course hero images

Public API
----------
  head_image(url, timeout=DOWNLOAD_TIMEOUT_SEC)            -> (length, ctype)
  download_image(url, timeout=DOWNLOAD_TIMEOUT_SEC)        -> bytes
  is_avif(url, ctype)                                      -> bool
  encode_avif(image_bytes, max_width, quality)             -> bytes  (AVIF)
  upload_avif(image_bytes, file_name, site_id, token)      -> dict
  rate_limited_request(method, url, token, data=None)      -> dict   (JSON)

Pillow + pillow_avif are imported lazily inside encode_avif so that callers
which only need head_image / download_image / rate_limited_request can run
on hosts without Pillow installed.
"""
from __future__ import annotations

import io
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# --- repo path bootstrap --------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse asset_upload.py for HTTP client + auth + S3 multipart helpers.
from asset_upload import (  # noqa: E402  (path-bootstrapped import)
    APIError,
    MAX_FILE_SIZE,
    NetworkError,
    WEBFLOW_API_BASE,
    api_request,
    build_multipart_body,
)

# --- constants ------------------------------------------------------------
USER_AGENT = "avif-optimizer/1.0"
DOWNLOAD_TIMEOUT_SEC = 30
ALREADY_AVIF_SKIP_SIZE = 200 * 1024  # 200 KB — already-small AVIFs are skipped
RATE_LIMIT_SLEEP_SEC = 0.6           # ~100 req/min, under CMS 120/min ceiling
HOSTED_URL_POLL_TRIES = 5
HOSTED_URL_POLL_SLEEP_SEC = 2.0


# =========================================================================
# Image I/O
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


# =========================================================================
# AVIF encode
# =========================================================================
def encode_avif(image_bytes: bytes, max_width: int, quality: int) -> bytes:
    """Decode → resize (downscale only) → re-encode AVIF.

    Aspect-preserving; uses ``thumbnail((max_width, max_width*100))`` so a
    very tall portrait (height >> width) does not get height-capped before
    its width hits max_width.

    Pillow + pillow_avif are imported here, not at module level, so the
    module imports cleanly on hosts without Pillow.
    """
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
# Webflow API helpers
# =========================================================================
def rate_limited_request(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """Wrap api_request with sleep + 429 exponential backoff (2/4/8 then give up).

    CMS plan rate limit is 120/min; 600 ms post-sleep keeps us at ~100/min.
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


def upload_avif(image_bytes: bytes, file_name: str, site_id: str, token: str) -> dict:
    """Upload image bytes via Webflow's 2-step S3 presigned flow.

    Receives bytes in-memory rather than reading from disk, so the image
    flows download → encode → upload without staging. Returns
    ``{'asset_id', 'hostedUrl', 'md5', 'size'}``.

    Despite the name (kept for the two existing callers) this is format-agnostic:
    the multipart Content-Type is derived from ``file_name``'s extension, not
    hard-coded. It used to stage every upload through a ``.avif`` temp file, so
    a PNG uploaded through here was announced to S3 as ``image/avif``. Callers
    passing a non-AVIF ``file_name`` — watermark_cleaner.py does, for lossless
    strips that must preserve the original format — now get the right MIME.
    """
    import hashlib
    import tempfile

    md5 = hashlib.md5(image_bytes).hexdigest()
    size = len(image_bytes)

    if size > MAX_FILE_SIZE:
        raise ValueError(f"image too large for Webflow: {size} bytes (max {MAX_FILE_SIZE})")

    suffix = Path(file_name).suffix.lower() or ".avif"

    # Step 1: register asset
    register_body = {"fileName": file_name, "fileHash": md5}
    register_url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    register_resp = rate_limited_request("POST", register_url, token, data=register_body)
    asset_id = register_resp.get("id")
    upload_url = register_resp.get("uploadUrl")
    upload_details = register_resp.get("uploadDetails", {})
    if not asset_id or not upload_url:
        raise RuntimeError(f"Webflow register response missing fields: {register_resp}")

    # Step 2: S3 multipart POST. build_multipart_body wants a Path on disk.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
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
            asset_resp = rate_limited_request("GET", asset_get_url, token)
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


# Re-export APIError / NetworkError for callers that want to catch them
# without importing asset_upload directly.
__all__ = [
    "APIError",
    "NetworkError",
    "USER_AGENT",
    "DOWNLOAD_TIMEOUT_SEC",
    "ALREADY_AVIF_SKIP_SIZE",
    "RATE_LIMIT_SLEEP_SEC",
    "HOSTED_URL_POLL_TRIES",
    "HOSTED_URL_POLL_SLEEP_SEC",
    "head_image",
    "download_image",
    "is_avif",
    "encode_avif",
    "upload_avif",
    "rate_limited_request",
]
