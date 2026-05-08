#!/usr/bin/env python3
"""
asset_upload.py — Webflow Asset Upload for Multi-Site Platform
==============================================================

Uploads local image files to Webflow via the Data API, tracks uploaded
assets, and optionally assigns them to elements via MCP.

USAGE:
  # Plan (dry-run) — show what would be uploaded, no API calls needed
  python3 scripts/asset_upload.py --site cel --plan path/to/images/
  python3 scripts/asset_upload.py --site cel --plan hero.png

  # Upload files (requires API token)
  python3 scripts/asset_upload.py --site cel --upload hero.png --token <token>
  python3 scripts/asset_upload.py --site cel --upload images/ --token <token>
  python3 scripts/asset_upload.py --site cel --upload hero.png  # uses WEBFLOW_API_TOKEN env

  # Upload into a specific folder
  python3 scripts/asset_upload.py --site cel --upload hero.png --folder "Page Images"

  # List existing assets on site
  python3 scripts/asset_upload.py --site cel --list
  python3 scripts/asset_upload.py --site cel --list --json

API FLOW:
  1. POST /v2/sites/{site_id}/assets with {fileName, fileHash} → get uploadUrl + uploadDetails
  2. Multipart POST to uploadUrl with uploadDetails fields + file binary
  3. Asset is available in Webflow

TOKEN:
  Provide via --token flag or WEBFLOW_API_TOKEN environment variable.
  If neither provided, --plan and --list without token show what they can.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared_paths import safe_load_json

# ── Constants ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif'}

MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB

MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
}

WEBFLOW_API_BASE = "https://api.webflow.com/v2"


# ── Site Config Loading ──────────────────────────────────────────────────────

def load_site_config(site_nickname=None):
    """Load site config from registry. If no site given, use default."""
    registry_path = REPO_ROOT / "sites" / "registry.json"
    if not registry_path.exists():
        print(f"Error: No registry at {registry_path}", file=sys.stderr)
        sys.exit(1)

    with open(registry_path) as f:
        registry = json.load(f)

    if not site_nickname:
        site_nickname = registry.get("default_site")
    if not site_nickname or site_nickname not in registry.get("sites", {}):
        print(f"Error: Site '{site_nickname}' not in registry", file=sys.stderr)
        sys.exit(1)

    site_entry = registry["sites"][site_nickname]
    site_path = REPO_ROOT / site_entry["path"]
    config_path = site_path / "site.json"

    if not config_path.exists():
        print(f"Error: No site config at {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    config["_site_path"] = site_path
    config["_nickname"] = site_nickname
    return config


# ── File Utilities ───────────────────────────────────────────────────────────

def validate_file(filepath):
    """
    Validate a file for upload. Returns (ok, error_message).
    ok=True means file is valid for upload.
    """
    path = Path(filepath)

    if not path.exists():
        return False, f"File not found: {filepath}"

    if not path.is_file():
        return False, f"Not a file: {filepath}"

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        size_mb = size / (1024 * 1024)
        return False, f"File too large: {size_mb:.1f}MB (max 4MB)"

    if size == 0:
        return False, f"File is empty: {filepath}"

    return True, None


def compute_md5(filepath):
    """Compute MD5 hex digest of a file."""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def get_mime_type(filepath):
    """Get MIME type from file extension."""
    ext = Path(filepath).suffix.lower()
    return MIME_TYPES.get(ext, 'application/octet-stream')


def generate_alt_text(filepath):
    """Generate alt text suggestion from filename.

    Strips extension, replaces hyphens/underscores with spaces, title cases.
    Examples:
        hero-image.png → "Hero Image"
        campus_photo_01.jpg → "Campus Photo 01"
        logo.svg → "Logo"
    """
    stem = Path(filepath).stem
    # Replace hyphens and underscores with spaces
    text = stem.replace('-', ' ').replace('_', ' ')
    # Collapse multiple spaces
    text = ' '.join(text.split())
    # Title case
    return text.title()


def auto_alt_text(filename):
    """Generate descriptive alt text from an asset filename.

    Strips the page slug prefix (e.g. "adults-16-"), converts separators
    to spaces, removes the file extension, and capitalizes words.

    Args:
        filename: Filename like "adults-16-hero-classroom.jpg"

    Returns:
        Descriptive alt text like "Hero Classroom"

    Examples:
        >>> auto_alt_text("adults-16-hero-classroom.jpg")
        'Hero Classroom'
        >>> auto_alt_text("how-long-to-study-campus-photo.png")
        'Campus Photo'
        >>> auto_alt_text("hero.jpg")
        'Hero'
        >>> auto_alt_text("logo_dark.svg")
        'Logo Dark'
    """
    stem = Path(filename).stem

    # Try to strip page slug prefix.
    # Page slugs follow the pattern: word(-word)*-  where last segment
    # before the descriptor is typically a page identifier.
    # Known pattern: slug like "adults-16-" or "how-long-to-study-"
    # Strategy: look for common page slug patterns (word-number- or word-word-)
    # and strip the longest matching prefix that leaves a non-empty remainder.
    # Match page-slug prefix: one or more groups of (word or number) followed by hyphen,
    # where total prefix is at least 2 segments (e.g., "adults-16-", "how-long-to-study-")
    match = re.match(r'^((?:[a-zA-Z]+[-_]\d+|[a-zA-Z]+[-_][a-zA-Z]+)[-_])', stem)
    if match:
        remainder = stem[match.end():]
        if remainder:  # Only strip if something remains
            stem = remainder

    # Replace hyphens and underscores with spaces
    text = stem.replace('-', ' ').replace('_', ' ')
    # Collapse multiple spaces
    text = ' '.join(text.split())
    # Capitalize words
    return text.title() if text else Path(filename).stem.title()


def suggest_alt_texts(directory):
    """Scan a directory and return suggested alt text for each image file.

    Args:
        directory: Path to directory containing image files

    Returns:
        List of dicts with 'filename', 'alt_text', and 'filepath' keys.
        Returns empty list if directory doesn't exist or has no images.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    suggestions = []
    files = collect_files(directory)
    for f in files:
        suggestions.append({
            'filename': f.name,
            'alt_text': auto_alt_text(f.name),
            'filepath': str(f),
        })
    return suggestions


def collect_files(path_arg):
    """Collect image files from a path (file or directory).

    Returns list of Path objects for valid image files.
    """
    path = Path(path_arg)

    if path.is_file():
        return [path]

    if path.is_dir():
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(path.glob(f"*{ext}"))
            # Also match uppercase extensions
            files.extend(path.glob(f"*{ext.upper()}"))
        # Deduplicate and sort
        seen = set()
        unique = []
        for f in sorted(files, key=lambda x: x.name.lower()):
            if f.resolve() not in seen:
                seen.add(f.resolve())
                unique.append(f)
        return unique

    return []


def format_size(size_bytes):
    """Format byte size into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f}MB"


# ── Asset Tracking ───────────────────────────────────────────────────────────

def get_tracking_path(config, page_name=None):
    """Get path to uploaded_assets.json tracking file.

    If page_name is provided, stores in page's sync_data dir.
    Otherwise stores in site's shared/ dir.
    """
    if page_name:
        return config["_site_path"] / "pages" / page_name / "sync_data" / "uploaded_assets.json"
    return config["_site_path"] / "shared" / "uploaded_assets.json"


def load_tracking(tracking_path):
    """Load uploaded asset tracking data."""
    return safe_load_json(tracking_path, default={})


def save_tracking(tracking_path, data):
    """Save uploaded asset tracking data."""
    tracking_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tracking_path, 'w') as f:
        json.dump(data, f, indent=2)


# ── API Helpers ──────────────────────────────────────────────────────────────

def get_api_token(args_token=None):
    """Get API token from args, environment, or .env file."""
    token = args_token or os.environ.get("WEBFLOW_API_TOKEN")
    if not token:
        # Fall back to .env file (same pattern as element_registry.py)
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            try:
                text = env_path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("WEBFLOW_API_TOKEN="):
                        val = line.split("=", 1)[1].strip()
                        if val and val[0] in ('"', "'") and val[-1] == val[0]:
                            val = val[1:-1]
                        if val:
                            return val
            except IOError:
                pass
        return None
    return token


def api_request(method, url, token, data=None, content_type="application/json"):
    """Make an authenticated API request to Webflow.

    Returns parsed JSON response or raises on error.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        if content_type == "application/json":
            body = json.dumps(data).encode('utf-8')
            headers["Content-Type"] = "application/json"
        else:
            body = data
            headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode('utf-8')
            if resp_body:
                return json.loads(resp_body)
            return {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        raise APIError(e.code, error_body, url)
    except urllib.error.URLError as e:
        raise NetworkError(str(e.reason), url)


class APIError(Exception):
    """Webflow API error with status code and body."""
    def __init__(self, status_code, body, url):
        self.status_code = status_code
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status_code} from {url}: {body}")


class NetworkError(Exception):
    """Network connectivity error."""
    def __init__(self, reason, url):
        self.reason = reason
        self.url = url
        super().__init__(f"Network error for {url}: {reason}")


# ── Multipart Form Upload ───────────────────────────────────────────────────

def build_multipart_body(fields, file_path, file_field_name="file"):
    """Build a multipart/form-data body for S3 upload.

    Args:
        fields: dict of form field name → value (from uploadDetails)
        file_path: Path to the file to upload
        file_field_name: Form field name for the file

    Returns:
        (body_bytes, content_type) tuple
    """
    boundary = "----WebflowAssetUploadBoundary"
    lines = []

    # Add form fields
    for key, value in fields.items():
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{key}"')
        lines.append("")
        lines.append(str(value))

    # Add file field
    path = Path(file_path)
    mime = get_mime_type(file_path)
    lines.append(f"--{boundary}")
    lines.append(f'Content-Disposition: form-data; name="{file_field_name}"; filename="{path.name}"')
    lines.append(f"Content-Type: {mime}")
    lines.append("")

    # Build the preamble (everything before file content)
    preamble = "\r\n".join(lines) + "\r\n"

    # Build the epilogue (after file content)
    epilogue = f"\r\n--{boundary}--\r\n"

    # Read file content
    with open(file_path, 'rb') as f:
        file_data = f.read()

    body = preamble.encode('utf-8') + file_data + epilogue.encode('utf-8')
    content_type = f"multipart/form-data; boundary={boundary}"

    return body, content_type


def upload_to_s3(upload_url, upload_details, file_path):
    """Upload file to S3 using the presigned URL and form fields.

    Args:
        upload_url: S3 presigned URL from Webflow API
        upload_details: dict of form fields from Webflow API
        file_path: local file to upload

    Returns:
        True on success, raises on error.
    """
    body, content_type = build_multipart_body(upload_details, file_path)

    req = urllib.request.Request(
        upload_url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            # S3 returns 200-204 on success
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        raise APIError(e.code, error_body, upload_url)
    except urllib.error.URLError as e:
        raise NetworkError(str(e.reason), upload_url)


# ── Core Commands ────────────────────────────────────────────────────────────

def cmd_plan(files_arg, config, page=None):
    """Dry-run: show what would be uploaded with sizes, hashes, MIME types."""
    files = collect_files(files_arg)

    if not files:
        print(f"No supported image files found in: {files_arg}")
        print(f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return {"files": [], "valid": 0, "invalid": 0, "total_size": 0}

    # Load tracking to detect already-uploaded
    tracking_path = get_tracking_path(config, page)
    tracking = load_tracking(tracking_path)

    valid = []
    invalid = []
    total_size = 0

    print(f"\n{'='*60}")
    print(f"  UPLOAD PLAN — {config.get('name', config.get('_nickname', 'unknown'))}")
    print(f"{'='*60}\n")

    for f in files:
        ok, error = validate_file(f)
        if not ok:
            invalid.append({"file": str(f), "error": error})
            print(f"  SKIP  {f.name}")
            print(f"        {error}")
            continue

        size = f.stat().st_size
        md5 = compute_md5(f)
        mime = get_mime_type(f)
        alt = generate_alt_text(f)
        already = f.name in tracking

        total_size += size
        entry = {
            "file": str(f),
            "name": f.name,
            "size": size,
            "size_human": format_size(size),
            "md5": md5,
            "mime": mime,
            "alt_text": alt,
            "already_uploaded": already,
        }
        if already:
            entry["existing_asset_id"] = tracking[f.name].get("asset_id")
        valid.append(entry)

        status = "SKIP (already uploaded)" if already else "READY"
        print(f"  {status}  {f.name}")
        print(f"        Size: {format_size(size)}  |  MD5: {md5}")
        print(f"        MIME: {mime}  |  Alt: \"{alt}\"")
        if already:
            print(f"        Asset ID: {tracking[f.name].get('asset_id', 'N/A')}")
        print()

    # Summary
    new_count = sum(1 for v in valid if not v["already_uploaded"])
    skip_count = sum(1 for v in valid if v["already_uploaded"])

    print(f"{'─'*60}")
    print(f"  Total files: {len(valid) + len(invalid)}")
    print(f"  Valid: {len(valid)} ({format_size(total_size)})")
    print(f"    New (will upload): {new_count}")
    print(f"    Already uploaded:  {skip_count}")
    print(f"  Invalid: {len(invalid)}")
    if not get_api_token():
        print("\n  Note: Set WEBFLOW_API_TOKEN or use --token to upload.")
    print()

    return {
        "files": valid,
        "invalid": invalid,
        "valid": len(valid),
        "new": new_count,
        "skipped": skip_count,
        "invalid_count": len(invalid),
        "total_size": total_size,
    }


def cmd_upload(files_arg, config, token, page=None, folder_name=None):
    """Upload files to Webflow assets."""
    site_id = config.get("webflow_site_id")
    if not site_id:
        print("Error: No webflow_site_id in site config", file=sys.stderr)
        sys.exit(1)

    files = collect_files(files_arg)
    if not files:
        print(f"No supported image files found in: {files_arg}")
        return {"uploaded": 0, "skipped": 0, "failed": 0}

    tracking_path = get_tracking_path(config, page)
    tracking = load_tracking(tracking_path)

    # Resolve folder ID if specified
    folder_id = None
    if folder_name:
        folder_id = resolve_folder_id(site_id, token, folder_name)

    results = {"uploaded": 0, "skipped": 0, "failed": 0, "total_size": 0, "details": []}

    print(f"\nUploading to {config.get('name', config.get('_nickname'))}...")
    print(f"Site ID: {site_id}")
    if folder_name:
        print(f"Folder: {folder_name} (ID: {folder_id or 'root'})")
    print()

    for f in files:
        ok, error = validate_file(f)
        if not ok:
            print(f"  FAIL  {f.name}: {error}")
            results["failed"] += 1
            results["details"].append({"file": f.name, "status": "invalid", "error": error})
            continue

        # Check if already uploaded
        if f.name in tracking:
            print(f"  SKIP  {f.name} (already uploaded as {tracking[f.name].get('asset_id', 'N/A')})")
            results["skipped"] += 1
            results["details"].append({"file": f.name, "status": "skipped", "asset_id": tracking[f.name].get("asset_id")})
            continue

        # Step 1: Register asset with Webflow API
        md5 = compute_md5(f)
        size = f.stat().st_size

        register_body = {
            "fileName": f.name,
            "fileHash": md5,
        }
        if folder_id:
            register_body["parentFolder"] = folder_id

        try:
            url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
            resp = api_request("POST", url, token, register_body)
        except APIError as e:
            print(f"  FAIL  {f.name}: API error {e.status_code}")
            results["failed"] += 1
            results["details"].append({"file": f.name, "status": "api_error", "error": str(e)})
            continue
        except NetworkError as e:
            print(f"  FAIL  {f.name}: Network error: {e.reason}")
            results["failed"] += 1
            results["details"].append({"file": f.name, "status": "network_error", "error": str(e)})
            continue

        asset_id = resp.get("id")
        upload_url = resp.get("uploadUrl")
        upload_details = resp.get("uploadDetails", {})

        if not upload_url:
            print(f"  FAIL  {f.name}: No uploadUrl in response")
            results["failed"] += 1
            results["details"].append({"file": f.name, "status": "no_upload_url", "error": "Missing uploadUrl"})
            continue

        # Step 2: Upload to S3
        try:
            upload_to_s3(upload_url, upload_details, f)
        except (APIError, NetworkError) as e:
            print(f"  FAIL  {f.name}: S3 upload failed: {e}")
            results["failed"] += 1
            results["details"].append({"file": f.name, "status": "s3_error", "error": str(e)})
            continue

        # Success — track it
        alt = generate_alt_text(f)
        tracking[f.name] = {
            "asset_id": asset_id,
            "md5": md5,
            "size": size,
            "alt_text": alt,
        }
        save_tracking(tracking_path, tracking)

        results["uploaded"] += 1
        results["total_size"] += size
        results["details"].append({
            "file": f.name,
            "status": "uploaded",
            "asset_id": asset_id,
            "size": size,
        })
        print(f"  OK    {f.name} → {asset_id} ({format_size(size)})")

    # Summary
    print(f"\n{'─'*60}")
    print(f"  Uploaded: {results['uploaded']}")
    print(f"  Skipped:  {results['skipped']} (already uploaded)")
    print(f"  Failed:   {results['failed']}")
    if results['uploaded'] > 0:
        print(f"  Total uploaded size: {format_size(results['total_size'])}")
    print()

    return results


def cmd_list(config, token, as_json=False):
    """List existing assets on the site."""
    site_id = config.get("webflow_site_id")
    if not site_id:
        print("Error: No webflow_site_id in site config", file=sys.stderr)
        sys.exit(1)

    url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    try:
        resp = api_request("GET", url, token)
    except APIError as e:
        print(f"Error listing assets: HTTP {e.status_code}", file=sys.stderr)
        print(f"  {e.body}", file=sys.stderr)
        sys.exit(1)
    except NetworkError as e:
        print(f"Error listing assets: {e.reason}", file=sys.stderr)
        sys.exit(1)

    assets = resp.get("assets", [])

    if as_json:
        print(json.dumps(assets, indent=2))
        return assets

    print(f"\n{'='*60}")
    print(f"  ASSETS — {config.get('name', config.get('_nickname', 'unknown'))}")
    print(f"{'='*60}\n")

    if not assets:
        print("  No assets found.")
        return assets

    for a in assets:
        name = a.get("fileName", "unknown")
        aid = a.get("id", "N/A")
        size = a.get("fileSize", 0)
        url = a.get("url", "")
        alt = a.get("altText", "")
        print(f"  {name}")
        print(f"    ID: {aid}  |  Size: {format_size(size)}")
        if alt:
            print(f"    Alt: {alt}")
        if url:
            print(f"    URL: {url}")
        print()

    print(f"  Total: {len(assets)} assets\n")
    return assets


def resolve_folder_id(site_id, token, folder_name):
    """Resolve a folder name to its ID. Returns None if not found."""
    url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    try:
        resp = api_request("GET", url, token)
    except (APIError, NetworkError):
        return None

    # Look through assets response for folder info
    # The Webflow API returns folders separately; check for folders
    folders = resp.get("folders", [])
    for folder in folders:
        if folder.get("displayName") == folder_name or folder.get("name") == folder_name:
            return folder.get("id")
    return None


# ── API Request Building (exposed for testing) ──────────────────────────────

def build_register_request(site_id, filename, file_hash, folder_id=None):
    """Build the asset registration API request details.

    Returns (url, headers, body) tuple.
    """
    url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "fileName": filename,
        "fileHash": file_hash,
    }
    if folder_id:
        body["parentFolder"] = folder_id
    return url, headers, body


def build_list_request(site_id):
    """Build the asset list API request details.

    Returns (url, headers) tuple.
    """
    url = f"{WEBFLOW_API_BASE}/sites/{site_id}/assets"
    headers = {
        "Accept": "application/json",
    }
    return url, headers


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Upload image assets to Webflow via Data API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run plan
  python3 scripts/asset_upload.py --site cel --plan images/

  # Upload files
  python3 scripts/asset_upload.py --site cel --upload hero.png --token <token>

  # List existing assets
  python3 scripts/asset_upload.py --site cel --list --token <token>

Supported formats: PNG, JPG, JPEG, GIF, SVG, WebP, AVIF (max 4MB)
""",
    )

    parser.add_argument("--site", help="Site nickname (from registry.json)")
    parser.add_argument("--page", help="Page name (for tracking assets per page)")

    # Commands (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--upload", metavar="PATH", help="Upload file(s) to Webflow assets")
    group.add_argument("--list", action="store_true", help="List existing assets on site")
    group.add_argument("--plan", metavar="PATH", help="Dry-run: show what would be uploaded")
    group.add_argument("--suggest-alt", metavar="PATH", help="Suggest alt text for images in a directory or file")

    # Options
    parser.add_argument("--token", help="Webflow API token (or set WEBFLOW_API_TOKEN env)")
    parser.add_argument("--folder", help="Upload into a specific asset folder")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # suggest-alt doesn't need site config
    if args.suggest_alt:
        path = Path(args.suggest_alt)
        if path.is_dir():
            suggestions = suggest_alt_texts(args.suggest_alt)
        elif path.is_file():
            suggestions = [{'filename': path.name, 'alt_text': auto_alt_text(path.name), 'filepath': str(path)}]
        else:
            print(f"Error: Path not found: {args.suggest_alt}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(suggestions, indent=2))
        else:
            if not suggestions:
                print("No image files found.")
            else:
                print(f"\n{'='*60}")
                print(f"  ALT TEXT SUGGESTIONS")
                print(f"{'='*60}\n")
                for s in suggestions:
                    print(f"  {s['filename']}")
                    print(f"    Alt: \"{s['alt_text']}\"")
                    print()
                print(f"  Total: {len(suggestions)} files\n")
        return

    # Load site config for commands that need it
    config = load_site_config(args.site)

    if args.plan:
        result = cmd_plan(args.plan, config, args.page)
        if args.json:
            print(json.dumps(result, indent=2))
        return

    # Commands that need a token
    token = get_api_token(args.token)

    if args.list:
        if not token:
            print("Error: --list requires API token. Use --token or set WEBFLOW_API_TOKEN.", file=sys.stderr)
            sys.exit(1)
        cmd_list(config, token, as_json=args.json)
        return

    if args.upload:
        if not token:
            print("Error: --upload requires API token. Use --token or set WEBFLOW_API_TOKEN.", file=sys.stderr)
            print("Tip: Use --plan for a dry-run without a token.", file=sys.stderr)
            sys.exit(1)
        cmd_upload(args.upload, config, token, args.page, args.folder)
        return


if __name__ == "__main__":
    main()
