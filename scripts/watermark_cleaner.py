#!/usr/bin/env python3
"""
watermark_cleaner.py — scan and strip AI-provenance metadata, locally and on Webflow
====================================================================================

The operator front-end for ``image_provenance.py``. That module does the byte
surgery; this one finds the images, decides what to touch, talks to Webflow, and
proves afterwards that the live file is actually clean.

    scan     inventory provenance signals (local paths, Webflow assets, CMS)
    clean    strip local files
    replace  strip images already on Webflow and re-point every reference
    verify   fetch a live URL and report what a crawler would see

The honesty boundary
--------------------
This tool removes **metadata**: C2PA manifests, IPTC ``digitalSourceType``, XMP,
EXIF, vendor breadcrumbs. Those are what Google Images, Bing and the social
platforms actually read to label an image "AI-generated".

It does **not** remove pixel-domain watermarks (Google SynthID, the watermark
OpenAI declares via ``c2pa.watermarked``). Those are in the image samples, not
the metadata, and no lossless operation touches them. When ``scan`` finds a
declaration, it says so under "NOT REMOVABLE" and the exit summary repeats it.
Do not describe an image cleaned by this tool as "watermark-free".

Writing to Webflow
------------------
``replace --apply`` is an external write and therefore a task boundary: present
the dry-run diff and wait for the user's explicit approval before running it
(CLAUDE.md → Deploy Approval Boundary; ``hooks/deploy-gate.py`` enforces it).
This tool never publishes — ``data_sites_tool.publish_site`` is the user's call.

Asset-identity safety
---------------------
Webflow's CDN URL embeds the asset id (``…/{site_id}/{asset_id}_{name}``). If a
re-upload mints a *new* asset id, every reference to the old URL — CMS fields,
and Designer elements this tool cannot reach — still points at the original,
un-stripped bytes. ``replace`` therefore checks the returned id and, when it
changed, re-points what it can and **refuses** any asset with references it
cannot fix, unless ``--allow-new-asset-id`` is passed. It never leaves a page
pointing at a broken URL to make a number look better.

Called by
---------
  CLI (operator, on request)
  .github/workflows/blog-image-optimization.yml   nightly CEL sweep (scan mode)
  scripts/tests/test_watermark_cleaner.py
"""
from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import image_provenance as ip  # noqa: E402
from image_provenance import Policy, ProvenanceError  # noqa: E402

# asset_upload owns auth + the S3 multipart plumbing; avif_optimizer owns the
# 2-step register/upload dance and the rate limiter. Neither is re-implemented.
from asset_upload import (  # noqa: E402
    APIError,
    NetworkError,
    WEBFLOW_API_BASE,
    get_api_token,
    load_site_config,
)
from avif_optimizer import (  # noqa: E402
    download_image,
    rate_limited_request,
    upload_avif as upload_bytes,   # format-agnostic since the suffix fix
)

DEFAULT_LOG_PATH = ROOT / "data" / "watermark-clean-log.jsonl"
DEFAULT_BACKUP_DIR = ROOT / "data" / "watermark-backup"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".heic", ".heif"}
CDN_HOSTS = ("cdn.prod.website-files.com", "uploads-ssl.webflow.com",
             "assets-global.website-files.com", "s3.amazonaws.com")

IMAGE_FIELD_TYPE = "Image"
MULTI_IMAGE_FIELD_TYPE = "MultiImage"
RICHTEXT_FIELD_TYPE = "RichText"


# ── small helpers ────────────────────────────────────────────────────────────
def utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}".replace(".0 ", " ")
        n /= 1024.0
    return f"{n} B"


def _fmt_bytes(n: int) -> str:
    if abs(n) < 1024:
        return f"{n} B"
    if abs(n) < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def asset_basename(original_file_name: str, display_name: str = "") -> str:
    """Recover the upload filename from Webflow's ``{asset_id}_{name}`` form.

    Webflow prefixes ``originalFileName`` with the asset id and an underscore.
    The id is 24 lowercase hex characters, so the split is unambiguous — a
    filename that merely *contains* an underscore is not mistaken for one.
    """
    name = original_file_name or display_name or ""
    head, sep, tail = name.partition("_")
    if sep and len(head) == 24 and all(c in "0123456789abcdef" for c in head.lower()):
        name = tail
    return urllib.parse.unquote(name)


def iter_local_images(paths: list[str], *, recursive: bool = True) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            out += [q for q in sorted(it) if q.is_file() and q.suffix.lower() in IMAGE_EXTS]
        elif p.is_file():
            out.append(p)
        else:
            matched = [Path(m) for m in sorted(__import__("glob").glob(raw, recursive=True))]
            out += [m for m in matched if m.is_file() and m.suffix.lower() in IMAGE_EXTS]
    seen: dict[Path, None] = {}
    for p in out:
        seen.setdefault(p.resolve(), None)
    return list(seen)


def resolve_site_token(site_nickname: str, override: str | None = None) -> str | None:
    """Resolve the Webflow REST token for a specific site.

    ``asset_upload.get_api_token`` only knows the single ``WEBFLOW_API_TOKEN``,
    which is the CEL grant. Every other site has its own token named in
    ``sites/registry.json`` under ``webflow_connection.rest_token_env`` — that
    registry field is the SSOT for multi-site routing (rules/webflow-elements.md
    §13 Rule 8). Without this, pointing the tool at brightvalley would silently
    authenticate as CEL and 404 on every asset.

    Resolution order: explicit override -> the site's own env var -> that name in
    .env -> the generic token. Returns None when nothing resolves, so the caller
    can fail loudly rather than firing unauthenticated requests.
    """
    if override:
        return override

    env_name = ""
    try:
        registry = json.loads((ROOT / "sites" / "registry.json").read_text(encoding="utf-8"))
        entry = (registry.get("sites") or {}).get(site_nickname) or {}
        env_name = ((entry.get("webflow_connection") or {}).get("rest_token_env") or "").strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        env_name = ""

    if env_name:
        val = os.environ.get(env_name)
        if val:
            return val
        env_file = ROOT / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith(f"{env_name}="):
                    val = line.split("=", 1)[1].strip()
                    if val and val[0] in ("\"", "'") and val[-1] == val[0]:
                        val = val[1:-1]
                    if val:
                        return val
    return get_api_token()


def render_markdown_summary(summary: dict) -> str:
    """Render a scan summary as GitHub-flavoured markdown for a job summary.

    Lives here rather than as a heredoc in the workflow YAML: a Python block
    embedded in a YAML block scalar inside a shell heredoc depends on three
    layers of indentation agreeing, and breaks silently when any of them is
    reflowed. Here it is one function with a test.
    """
    lines = ["## AI-provenance scan", ""]
    if not summary:
        lines += ["> Summary unavailable — the scan did not complete.",
                  "> Status is **UNKNOWN**, which is not the same as clean."]
        return "\n".join(lines) + "\n"

    lines += [
        "| checked at | scanned | carry metadata | AI-flagged | removable | pixel watermark declared |",
        "|---|---|---|---|---|---|",
        f"| {summary.get('ts', '?')} | {summary.get('scanned', 0)} | "
        f"{summary.get('with_metadata', 0)} | **{summary.get('ai_flagged', 0)}** | "
        f"{summary.get('removable_bytes', 0):,} B | {summary.get('pixel_watermark_declared', 0)} |",
    ]
    if summary.get("unreadable"):
        lines += ["", f"> **Coverage: {summary.get('coverage', '?')}.** "
                      f"{summary['unreadable']} file(s) could not be parsed."]
    flagged = summary.get("flagged_names") or []
    if flagged:
        lines += ["", "Images a crawler would read as AI-generated:", ""]
        lines += [f"- `{n}`" for n in flagged]
        lines += ["", "To strip these, run this workflow manually with **scrub_provenance** "
                      "checked and **scrub_confirm = REPLACE**."]
    else:
        scanned = summary.get("scanned", 0)
        unreadable = summary.get("unreadable", 0)
        readable = scanned - unreadable
        if scanned == 0:
            lines += ["", "> **Nothing was scanned.** This is not an all-clear — it means the run "
                          "produced no result at all. Treat as UNKNOWN."]
        elif unreadable:
            lines += ["", f"No image carries a C2PA manifest or an IPTC AI marker — "
                          f"**among the {readable} of {scanned} we could read**. "
                          f"{unreadable} could not be parsed; their status is UNKNOWN, not clean."]
        else:
            lines += ["", "No image carries a C2PA manifest or an IPTC AI marker."]
    if summary.get("pixel_watermark_declared"):
        lines += ["",
                  f"> **{summary['pixel_watermark_declared']} image(s) declare a pixel-domain "
                  "watermark** (SynthID / `c2pa.watermarked`). That lives in the pixel data, not "
                  "in metadata. It is **not** removed by this tool and cannot be removed by any "
                  "lossless operation. Do not describe these images as watermark-free."]
    return "\n".join(lines) + "\n"


def load_known_clean(path: Path) -> set[str]:
    """Asset ids a previous run proved carry no removable metadata.

    Safe to trust because a Webflow asset is immutable: changing an image's
    bytes produces a new asset with a new id and a new CDN URL, it never mutates
    one in place (the URL embeds the id). So "asset 6a7d… was clean" cannot go
    stale — only "the site no longer uses it" can, which does not matter here.
    Anything not positively recorded as clean is re-checked, so a corrupt or
    truncated log costs time, never correctness.
    """
    known: set[str] = set()
    if not path.is_file():
        return known
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        action = row.get("action")
        aid = row.get("asset_id")
        # A `replaced` row's asset_id is the ORIGINAL — and replace never touches
        # the original, it uploads a clean COPY. Treating that id as proven-clean
        # made every later scan skip the still-dirty source forever. The clean
        # asset is the new one.
        if action == "replaced":
            new_id = row.get("new_asset_id")
            if new_id and row.get("verify", {}).get("clean") is not False:
                known.add(new_id)
            continue
        # incomplete_repoint / verify_failed / refused_* / error prove nothing.
        if action == "already_clean" and aid:
            known.add(aid)
        elif row.get("mode") == "scan-asset" and aid and not row.get("signals"):
            # Zero signals means "clean" ONLY if the walk actually completed.
            # A parse_error on a container we recognised means it ABORTED — and
            # crediting that made the alarm self-clearing: night 1 exits 2 with
            # the UNKNOWN warning, night 2 filters the asset out before the fetch
            # so unreadable == 0 and the warning vanishes, manifest still there.
            #
            # But "unsupported container" is a statement about the file TYPE, not
            # a failure. Excluding those too would evict every font and PDF from
            # the cache and re-download them every night forever.
            aborted = bool(row.get("parse_error")) and row.get("container") != "unknown"
            if not aborted:
                known.add(aid)
    return known


def load_superseded(path: Path) -> dict[str, str]:
    """Original asset id -> the clean asset that replaced it.

    A SECOND set, deliberately kept apart from ``load_known_clean``. The two
    answer different questions and must never be merged:

    * *clean* means "these bytes carry no removable metadata". A superseded
      original is NOT clean — its bytes are untouched and still served at its
      own CDN URL — so crediting it there would make ``scan`` report a site
      clean while a dirty orphan is still public.
    * *superseded* means "replacing this again would only mint another orphan".

    Without this set ``replace --apply`` was not idempotent: a Webflow asset is
    immutable, so a successful replace uploads a COPY and leaves the original in
    the asset list. The next run found it, still dirty, and uploaded another
    one — a fresh orphan on the client's site every single night.

    Only a fully successful replace supersedes. ``incomplete_repoint`` means the
    CMS still points at the original, and ``verify_failed`` means the copy was
    never proven — in both cases the original still needs work.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("action") != "replaced":
            continue
        old, new = row.get("asset_id"), row.get("new_asset_id")
        # An `--allow-new-asset-id` run can record old == new when Webflow
        # de-duplicated the upload; that is not a supersession, and treating it
        # as one would skip an asset that genuinely still needs replacing.
        if old and new and old != new:
            out[old] = new          # last successful replace wins
    return out


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── Webflow read helpers ─────────────────────────────────────────────────────
PAGE_SIZE = 100
RETRY_BACKOFF = 0.75      # seconds; doubled per attempt (build_live_page_index._get)
PAGE_HARD_CAP = 1000          # 100k records; a runaway-loop backstop, not a real bound


def _paginate(token: str, url_for: "callable", key: str, *,
              limit: int | None = None) -> list[dict]:
    """Page through a Webflow list endpoint until it is genuinely exhausted.

    The stop condition is **a short batch**, not ``offset >= pagination.total``.
    Defaulting the total to ``len(out)`` when the block is missing makes the
    first full page look like the whole collection: measured, a 250-asset site
    returned 100 and reported it as complete, after which every downstream
    command — scan, replace, lineage, purge — silently operated on a partial
    site and could report "0 AI-flagged" on one full of them. ``total`` is now
    only ever used as an additional early exit, never as the sole one.
    """
    out: list[dict] = []
    offset = 0
    for _page in range(PAGE_HARD_CAP):
        resp = rate_limited_request("GET", url_for(offset, PAGE_SIZE), token)
        batch = resp.get(key, []) or []
        out += batch
        if limit and len(out) >= limit:
            return out[:limit]
        if len(batch) < PAGE_SIZE:
            return out                       # a short page is the last page
        offset += PAGE_SIZE
        total = (resp.get("pagination") or {}).get("total")
        if isinstance(total, int) and offset >= total:
            return out
    raise RuntimeError(
        f"pagination exceeded {PAGE_HARD_CAP} pages for {key} — refusing to loop forever")


def list_assets(token: str, site_id: str, *, limit: int | None = None) -> list[dict]:
    """Page through every asset on the site."""
    return _paginate(
        token,
        lambda off, lim: f"{WEBFLOW_API_BASE}/sites/{site_id}/assets?limit={lim}&offset={off}",
        "assets", limit=limit)


def list_collections(token: str, site_id: str) -> list[dict]:
    resp = rate_limited_request("GET", f"{WEBFLOW_API_BASE}/sites/{site_id}/collections", token)
    return resp.get("collections", []) or []


def get_collection_fields(token: str, collection_id: str) -> list[dict]:
    resp = rate_limited_request("GET", f"{WEBFLOW_API_BASE}/collections/{collection_id}", token)
    return resp.get("fields", []) or []


def classify_image_fields(fields: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"image": [], "multi": [], "richtext": []}
    for f in fields:
        slug, ftype = f.get("slug"), f.get("type")
        if not slug:
            continue
        if ftype == IMAGE_FIELD_TYPE:
            out["image"].append(slug)
        elif ftype == MULTI_IMAGE_FIELD_TYPE:
            out["multi"].append(slug)
        elif ftype == RICHTEXT_FIELD_TYPE:
            out["richtext"].append(slug)
    return out


def list_items(token: str, collection_id: str) -> list[dict]:
    """Page through every item in a collection. See _paginate for the stop rule."""
    return _paginate(
        token,
        lambda off, lim: (f"{WEBFLOW_API_BASE}/collections/{collection_id}"
                          f"/items?limit={lim}&offset={off}"),
        "items")


def patch_item(token: str, collection_id: str, item_id: str, field_data: dict,
               *, is_draft: bool, is_archived: bool) -> dict:
    url = f"{WEBFLOW_API_BASE}/collections/{collection_id}/items/{item_id}"
    body = {"isDraft": is_draft, "isArchived": is_archived, "fieldData": field_data}
    return rate_limited_request("PATCH", url, token, data=body)


def publish_items(token: str, collection_id: str, item_ids: list[str]) -> dict:
    if not item_ids:
        return {}
    url = f"{WEBFLOW_API_BASE}/collections/{collection_id}/items/publish"
    return rate_limited_request("POST", url, token, data={"itemIds": item_ids})


# ── reference index ──────────────────────────────────────────────────────────
@dataclasses.dataclass
class Reference:
    """One place a Webflow asset URL appears."""

    kind: str                 # "image" | "multi" | "richtext"
    collection_id: str
    collection_slug: str
    item_id: str
    item_slug: str
    field_slug: str
    index: int = -1           # position within a MultiImage array
    source_url: str = ""      # the URL as stored in the field
    is_draft: bool = False
    is_archived: bool = False
    was_published: bool = False


def _url_key(url: str) -> str:
    """Normalise a CDN URL so the same asset matches across host/encoding variants."""
    if not url:
        return ""
    u = urllib.parse.urlsplit(urllib.parse.unquote(url))
    tail = u.path.rsplit("/", 1)[-1]
    return tail.lower()


def _strip_id_prefixes(key: str) -> str:
    """Remove leading ``{24-hex}_`` prefixes from a URL key, repeatedly.

    Webflow stamps an id onto the stored filename, so the last URL segment is
    ``{id}_{name}``. Re-uploading a file that already carried a prefix stacks
    another one — brightvalley's team photos really are
    ``{id}_{id}_team-13-danny-v2.webp``.
    """
    s = key
    while True:
        head, sep, tail = s.partition("_")
        if sep and len(head) == 24 and all(c in "0123456789abcdef" for c in head):
            s = tail
            continue
        return s


def asset_id_from_url_key(key: str) -> str:
    """The Webflow asset id stamped on a URL key, or "" if there is none.

    ``_url_key`` yields ``{24-hex}_{name}`` while ``load_known_clean`` and
    ``load_superseded`` are keyed by the bare asset id. ``cmd_cms`` compared the
    two directly, so ``--skip-known-clean`` could never match a single entry:
    the flag was accepted, complained about nothing, reported ``skipped 0`` and
    re-downloaded the whole site on every run. A no-op that looks like a
    working feature is worse than an unimplemented one.

    Only the OUTERMOST prefix is the current id — re-uploading a prefixed file
    stacks another (``{new}_{old}_name.webp``), and the inner one names the
    superseded asset.
    """
    head, sep, _tail = key.partition("_")
    if sep and len(head) == 24 and all(c in "0123456789abcdef" for c in head.lower()):
        return head.lower()
    return ""


def _basename_key(url: str) -> str:
    """Identity of an image independent of which id happens to be stamped on it.

    Needed because the id in a CMS field's URL is NOT always the site-asset id.
    On brightvalley (a WordPress import) the two populations are completely
    disjoint: 214 site assets and 164 CMS-referenced images with **zero**
    overlap under ``_url_key``. Joining on the exact key there reports every
    flagged image as "referenced nowhere", which is the most dangerous possible
    wrong answer — it is the input to the refuse-or-proceed decision, and it
    reads as "safe to replace".
    """
    return _strip_id_prefixes(_url_key(url))


def _iter_richtext_srcs(html: str) -> list[str]:
    from html.parser import HTMLParser

    class C(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.srcs: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "img":
                for k, v in attrs:
                    if k == "src" and v:
                        self.srcs.append(v)

    c = C()
    try:
        c.feed(html)
    except Exception:
        return []
    return c.srcs


def build_reference_index(token: str, site_id: str, *,
                          collections_filter: str = "all",
                          progress: bool = True) -> tuple[dict[str, list[Reference]], list[dict]]:
    """Map ``_url_key(url) -> [Reference, …]`` across every CMS collection.

    Returns (index, collection_summaries). This is what makes a safe replace
    possible: before touching an asset we know exactly which CMS fields point at
    it, and can tell "referenced nowhere" apart from "referenced somewhere I
    cannot reach".
    """
    index: dict[str, list[Reference]] = {}
    summaries: list[dict] = []
    cols = list_collections(token, site_id)
    if collections_filter not in ("all", ""):
        wanted = {c.strip() for c in collections_filter.split(",") if c.strip()}
        cols = [c for c in cols if c.get("slug") in wanted or c.get("id") in wanted]

    for col in cols:
        cid, cslug = col.get("id"), col.get("slug", "")
        if not cid:
            continue
        fields = classify_image_fields(get_collection_fields(token, cid))
        if not any(fields.values()):
            summaries.append({"collection": cslug, "items": 0, "refs": 0, "skipped": "no image fields"})
            continue
        items = list_items(token, cid)
        n_refs = 0
        for item in items:
            fd = item.get("fieldData", {}) or {}
            base = dict(
                collection_id=cid, collection_slug=cslug,
                item_id=item.get("id", ""), item_slug=fd.get("slug", ""),
                is_draft=bool(item.get("isDraft")), is_archived=bool(item.get("isArchived")),
                was_published=bool(item.get("lastPublished")),
            )
            for slug in fields["image"]:
                val = fd.get(slug)
                url = (val or {}).get("url", "") if isinstance(val, dict) else ""
                if url:
                    index.setdefault(_url_key(url), []).append(
                        Reference(kind="image", field_slug=slug, source_url=url, **base))
                    n_refs += 1
            for slug in fields["multi"]:
                val = fd.get(slug)
                if isinstance(val, list):
                    for i, entry in enumerate(val):
                        url = (entry or {}).get("url", "") if isinstance(entry, dict) else ""
                        if url:
                            index.setdefault(_url_key(url), []).append(
                                Reference(kind="multi", field_slug=slug, index=i, source_url=url, **base))
                            n_refs += 1
            for slug in fields["richtext"]:
                html = fd.get(slug)
                if isinstance(html, str) and "<img" in html:
                    for src in _iter_richtext_srcs(html):
                        index.setdefault(_url_key(src), []).append(
                            Reference(kind="richtext", field_slug=slug, source_url=src, **base))
                        n_refs += 1
        summaries.append({"collection": cslug, "items": len(items), "refs": n_refs})
        if progress:
            print(f"    indexed {cslug:32} {len(items):>4} items  {n_refs:>4} image refs", flush=True)
    return index, summaries


def lookup_refs(index: dict[str, list], url: str) -> tuple[list, str]:
    """Find the references to ``url``. Returns (refs, how) where how is
    ``"exact"``, ``"basename"``, ``"ambiguous"`` or ``"none"``.

    Exact key wins. Falling back to basename is what makes a WordPress-imported
    site joinable at all, but it is a weaker claim: two genuinely different
    pictures can share a filename. When the basename resolves to more than one
    distinct exact key, this returns ``"ambiguous"`` and the caller must refuse
    rather than re-point a reference to the wrong image.
    """
    exact = index.get(_url_key(url))
    if exact:
        return exact, "exact"
    want = _basename_key(url)
    if not want:
        return [], "none"
    matches = {k: v for k, v in index.items() if _strip_id_prefixes(k) == want}
    if not matches:
        return [], "none"
    if len(matches) > 1:
        return [r for refs in matches.values() for r in refs], "ambiguous"
    return next(iter(matches.values())), "basename"


def build_live_page_index(site_url: str, *, limit: int = 0, progress: bool = True,
                          timeout: int = 20) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Map ``_url_key(url) -> [page_url, …]`` by reading the *published* site.

    The CMS index covers what the Data API can see. It cannot see an image
    placed directly on a page in the Designer — and that is exactly the
    reference that breaks silently when an asset id changes. Rather than
    guessing, this fetches the sitemap, reads each page's HTML, and records
    every Webflow-CDN image URL it actually finds. The result turns "might be
    referenced elsewhere" into a measured fact.

    Returns (index, pages_fetched, pages_failed). The failure list is RETURNED,
    not merely printed: a caller deciding whether it is safe to delete an asset
    must be able to tell "checked 200 pages, none reference it" from "managed to
    read 3 of 200". Previously only a totally empty result was treated as
    unusable, so a partial fetch silently satisfied the "no page references it"
    precondition of an irreversible delete.
    """
    import re as _re

    base = site_url.rstrip("/")
    index: dict[str, list[str]] = {}
    fetched: list[str] = []
    failures: list[str] = []

    def _get(u: str, *, tries: int = 3) -> str:
        """Fetch with a short retry on TRANSIENT failures only.

        Every failure here poisons `live_known`, which is the evidence gate in
        front of an irreversible delete and of `replace`'s id-change refusal. So
        one dropped connection out of 200 pages used to void the whole run's
        evidence and make the tool refuse work it could have done correctly.

        Retry only what can succeed on a second try. A 404 or 410 is a fact
        about the URL: retrying it wastes time and, worse, would let a genuinely
        missing page look like a flake.
        """
        req = urllib.request.Request(u, headers={"User-Agent": "watermark-cleaner/1.0"})
        last: Exception | None = None
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code in (408, 425, 429, 500, 502, 503, 504) and attempt < tries - 1:
                    last = e
                    time.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                if attempt < tries - 1:
                    last = e
                    time.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise
        raise last if last else RuntimeError("unreachable")

    try:
        sitemap = _get(f"{base}/sitemap.xml")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"    sitemap unreachable ({e}) — live-page index unavailable")
        return {}, [], ["<sitemap>"]

    page_urls = _re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap)
    # A sitemap index points at more sitemaps; follow one level.
    if page_urls and all(u.endswith(".xml") for u in page_urls[:3]):
        nested: list[str] = []
        if len(page_urls) > 20:
            # Dropping child sitemaps silently would let "read 3 of 40 pages"
            # satisfy live_known, which gates an irreversible delete.
            failures.append(f"<sitemap-index-truncated:{len(page_urls) - 20}>")
        for sm in page_urls[:20]:
            try:
                nested += _re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", _get(sm))
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                failures.append(sm)
        page_urls = nested
    if limit and len(page_urls) > limit:
        failures.append(f"<page-limit-truncated:{len(page_urls) - limit}>")
        page_urls = page_urls[:limit]

    img_re = _re.compile(r"https?://(?:" + "|".join(h.replace(".", r"\.") for h in CDN_HOSTS)
                         + r")/[^\s\"'<>\\)]+", _re.I)
    # Webflow compiles a Designer-set background-image into the SITE STYLESHEET
    # (/css/<site>.webflow.<hash>.css), never into the page markup. Reading only
    # HTML therefore reports an AI hero background as referenced nowhere — and
    # "referenced nowhere" is what lets purge delete it irreversibly. Each
    # same-origin stylesheet is fetched once and attributed to every page that
    # links it; a stylesheet we cannot read is a coverage failure, not a pass.
    css_re = _re.compile(r'<link[^>]+rel=["\']?stylesheet["\']?[^>]*>', _re.I)
    href_re = _re.compile(r'href=["\']([^"\']+)["\']', _re.I)
    css_cache: dict[str, list[str]] = {}

    for i, pu in enumerate(page_urls, 1):
        try:
            html = _get(pu)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            failures.append(pu)
            continue
        fetched.append(pu)
        for m in set(img_re.findall(html)):
            index.setdefault(_url_key(m), []).append(pu)

        for tag in css_re.findall(html):
            href = href_re.search(tag)
            if not href:
                continue
            css_url = urllib.parse.urljoin(pu, href.group(1))
            if urllib.parse.urlsplit(css_url).netloc != urllib.parse.urlsplit(base).netloc:
                continue                       # third-party CSS cannot hold our assets
            if css_url not in css_cache:
                try:
                    css_cache[css_url] = list(set(img_re.findall(_get(css_url))))
                except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                    css_cache[css_url] = []
                    failures.append(css_url)
            for m in css_cache[css_url]:
                index.setdefault(_url_key(m), []).append(pu)

        if progress and i % 25 == 0:
            print(f"    scanned {i}/{len(page_urls)} pages…", flush=True)

    if failures:
        print(f"    ! {len(failures)} page(s) could not be fetched — their references are UNKNOWN")
    return index, fetched, failures


def repoint_reference(token: str, ref: Reference, *, old_url: str, new_url: str,
                      new_file_id: str, apply: bool) -> dict:
    """Update one CMS field so it points at the replacement asset."""
    if not apply:
        return {"status": "would-repoint", "ref": dataclasses.asdict(ref)}
    url = f"{WEBFLOW_API_BASE}/collections/{ref.collection_id}/items/{ref.item_id}"
    item = rate_limited_request("GET", url, token)
    fd = dict(item.get("fieldData", {}) or {})
    changed = False

    def _same(candidate: str) -> bool:
        """Match the field's current URL against the asset we are replacing.

        Exact key first; basename when the ids differ (WordPress-imported sites
        stamp a different id into CMS URLs than the site-asset id). Comparing
        only on the exact key made every re-point on brightvalley report
        "ref-stale" and silently do nothing — the upload succeeded, the CMS kept
        pointing at the un-stripped file, and the run still printed a success
        line. That is the half-replaced state this tool exists to avoid.
        """
        if not candidate:
            return False
        if _url_key(candidate) == _url_key(old_url):
            return True
        return _basename_key(candidate) == _basename_key(old_url)

    def _exact(candidate: str) -> bool:
        return bool(candidate) and _url_key(candidate) == _url_key(old_url)

    if ref.kind == "image":
        val = dict(fd.get(ref.field_slug) or {})
        if _same(val.get("url", "")):
            val["url"] = new_url
            if new_file_id:
                val["fileId"] = new_file_id
            fd[ref.field_slug] = val
            changed = True
    elif ref.kind == "multi":
        arr = list(fd.get(ref.field_slug) or [])

        # Rewrite exactly the entry this Reference points at. The previous loop
        # rewrote EVERY entry whose url satisfied _same(), and _same() falls back
        # to basename — so re-pointing gallery[0] of
        #   [{aaa_hero.png}, {bbb_hero.png}, {ccc_other.png}]
        # replaced gallery[1] as well. Those are two distinct uploads that merely
        # share a filename, and the sibling was silently swapped for a different
        # picture. Reference.index was already recorded; it was just ignored.
        targets: list[int] = []
        if 0 <= ref.index < len(arr):
            entry = arr[ref.index]
            if isinstance(entry, dict) and _same(entry.get("url", "")):
                targets = [ref.index]
        else:
            exact = [i for i, e in enumerate(arr)
                     if isinstance(e, dict) and _exact(e.get("url", ""))]
            loose = [i for i, e in enumerate(arr)
                     if isinstance(e, dict) and _same(e.get("url", ""))]
            if exact:
                targets = exact
            elif len(loose) == 1:
                targets = loose
            elif len(loose) > 1:
                # Ambiguous by basename with no index to disambiguate: refuse
                # rather than pick. Rewriting the wrong gallery entry is not
                # recoverable from the log.
                return {"status": "ref-ambiguous", "ref": dataclasses.asdict(ref),
                        "candidates": loose}

        for i in targets:
            e = dict(arr[i])
            e["url"] = new_url
            if new_file_id:
                e["fileId"] = new_file_id
            arr[i] = e
            changed = True
        if changed:
            fd[ref.field_slug] = arr
    elif ref.kind == "richtext":
        html = fd.get(ref.field_slug) or ""
        if isinstance(html, str):
            srcs = _iter_richtext_srcs(html)
            exact = {s for s in srcs if _exact(s)}
            loose = {s for s in srcs if _same(s)}
            # Prefer exact; only fall back to basename when it is unambiguous.
            # Replacing every basename match would swap two DIFFERENT body images
            # that happen to share a filename — the same defect as the gallery
            # path, and just as unrecoverable.
            chosen = exact or (loose if len(loose) == 1 else set())
            if not chosen and len(loose) > 1:
                return {"status": "ref-ambiguous", "ref": dataclasses.asdict(ref),
                        "candidates": sorted(loose)}
            out = html
            for src in chosen:
                out = out.replace(src, new_url)
                changed = True
            if changed:
                fd[ref.field_slug] = out

    if not changed:
        return {"status": "ref-stale", "ref": dataclasses.asdict(ref)}
    patch_item(token, ref.collection_id, ref.item_id, fd,
               is_draft=ref.is_draft, is_archived=ref.is_archived)
    return {"status": "repointed", "ref": dataclasses.asdict(ref)}


# ── verification ─────────────────────────────────────────────────────────────
def fetch_and_scan(url: str, *, timeout: int = 30) -> tuple[ip.Report, int]:
    """Download a URL and report what a crawler fetching it would find."""
    data = download_image(url, timeout=timeout)
    return ip.scan(data), len(data)


def verify_live(url: str, *, tries: int = 4, sleep: float = 2.0,
                policy: Policy | None = None) -> dict:
    """Poll a CDN URL until it serves bytes, then assert the policy's intent held.

    ``policy`` MUST be the same policy the bytes were stripped with — see
    ``verdict``. Passing None asks the strict question instead.
    """
    last: dict = {}
    for attempt in range(tries):
        try:
            # One download, scanned two ways. Fetching twice doubled the network
            # cost of every verify AND compared two possibly-different responses
            # (a CDN mid-propagation can serve old bytes to one and new to the
            # other), so a mixed verdict was possible on bytes that were never
            # simultaneously live.
            # One download, scanned every way — see verdict(). An unparseable
            # response is UNKNOWN, never clean: replace/cms print this verdict
            # as their proof that an upload landed clean, so "could not read it"
            # must never render as "verified clean".
            data = download_image(url)
            v, rep, residue = verdict(data, policy=policy)
            last = {
                "url": url, "size": len(data), "container": rep.container,
                "verdict": v, "clean": v == "CLEAN",
                "signals": [s.as_dict() for s in rep.signals],
                "residue": residue[:5],
                "parse_error": rep.parse_error,
                "undetectable_watermarks": rep.undetectable_watermarks,
            }
            if last["clean"] or attempt == tries - 1:
                return last
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            last = {"url": url, "error": f"{type(e).__name__}: {e}"}
        time.sleep(sleep)
    return last


# ── commands ─────────────────────────────────────────────────────────────────
def _policy_from_args(args: argparse.Namespace) -> Policy:
    return Policy(
        strip_c2pa=not args.keep_c2pa,
        strip_exif=not args.keep_exif,
        strip_xmp=True,
        strip_iptc=True,
        strip_comments=True,
        strip_generator_tags=True,
        keep_icc=not args.strip_icc,
        keep_orientation=not args.drop_orientation,
    )


def _is_concerning_parse_error(rep: ip.Report) -> bool:
    """Distinguish "not an image I handle" from "an image I could not read".

    A Webflow site holds fonts, PDFs and other non-images; those sniff as
    ``unknown`` and report "unsupported container", which is a statement about
    the file TYPE, not a failure. Counting them as unreadable made a healthy
    site exit non-zero on every nightly run — an alarm that fires every night is
    an alarm nobody reads.

    A parse error on a container we DID recognise is the real concern: that is
    exactly the shape in which a manifest hides behind zero signals.
    """
    if not rep.parse_error:
        return False
    # Key on the MESSAGE, not on our sniffer's vocabulary. `sniff` recognises
    # containers it has no scanner for (TIFF), so `container != "unknown"` called
    # a perfectly benign TIFF unreadable and reddened the nightly run. What we
    # actually mean is "we could not read a format we claim to handle".
    return not rep.parse_error.startswith("unsupported container")


def _print_report(label: str, rep: ip.Report, *, verbose: bool) -> None:
    # "clean" requires that the structure was actually READ. A parse error means
    # zero signals were found because the walk aborted, not because there is
    # nothing there — printing "clean" for that contradicted the UNKNOWN verdict
    # on the line above it.
    if rep.parse_error:
        flag = "UNKNOWN"
    elif rep.is_ai_flagged:
        flag = "AI-FLAGGED"
    elif rep.signals:
        flag = "metadata"
    else:
        flag = "clean"
    gens = f"  [{', '.join(rep.generators)}]" if rep.generators else ""
    print(f"  {flag:<11} {label}{gens}")
    if rep.parse_error:
        print(f"              ! {rep.parse_error}")
    if verbose:
        for s in rep.signals:
            mark = "-" if s.removable else "X"
            print(f"                {mark} {s.kind:<20} {s.where:<22} {_fmt_bytes(s.length):>9}  {s.detail[:64]}")
    if rep.undetectable_watermarks:
        for w in rep.undetectable_watermarks:
            print(f"                X NOT REMOVABLE: {w}")


def cmd_scan(args: argparse.Namespace) -> int:
    rows: list[dict] = []
    totals = {"files": 0, "flagged": 0, "with_metadata": 0, "removable_bytes": 0,
              "undetectable": 0, "unreadable": 0}

    if args.local:
        files = iter_local_images(args.local)
        print(f"\nScanning {len(files)} local image(s)…\n")
        for p in files:
            try:
                rep = ip.scan(p.read_bytes())
            except OSError as e:
                print(f"  ERROR       {p}: {e}")
                totals["unreadable"] += 1
                continue
            totals["files"] += 1
            if _is_concerning_parse_error(rep):
                totals["unreadable"] += 1
            if rep.is_ai_flagged:
                totals["flagged"] += 1
            if any(s.removable for s in rep.signals):
                totals["with_metadata"] += 1
            totals["removable_bytes"] += rep.removable_bytes
            if rep.undetectable_watermarks:
                totals["undetectable"] += 1
            if rep.signals or args.all:
                _print_report(str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p),
                              rep, verbose=args.verbose)
            rows.append({"ts": utc_iso(), "mode": "scan-local", "path": str(p), **rep.as_dict()})

    if args.site:
        cfg = load_site_config(args.site)
        token = resolve_site_token(args.site, getattr(args, "token", None))
        site_id = cfg["webflow_site_id"]
        assets = list_assets(token, site_id, limit=args.limit)
        known = load_known_clean(Path(args.skip_known_clean)) if args.skip_known_clean else set()
        if known:
            before_n = len(assets)
            assets = [a for a in assets if a.get("id") not in known]
            print(f"\n  {before_n - len(assets)} asset(s) already proven clean — skipping them.")
        print(f"\nScanning {len(assets)} Webflow asset(s) on '{args.site}'…\n")
        for a in assets:
            url = a.get("hostedUrl") or ""
            name = asset_basename(a.get("originalFileName", ""), a.get("displayName", ""))
            if args.pattern and not fnmatch.fnmatch(name, args.pattern):
                continue
            if not url:
                continue
            try:
                rep, size = fetch_and_scan(url)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
                print(f"  ERROR       {name}: {type(e).__name__}: {e}")
                totals["unreadable"] += 1
                continue
            totals["files"] += 1
            if _is_concerning_parse_error(rep):
                totals["unreadable"] += 1
            if rep.is_ai_flagged:
                totals["flagged"] += 1
            if any(s.removable for s in rep.signals):
                totals["with_metadata"] += 1
            totals["removable_bytes"] += rep.removable_bytes
            if rep.undetectable_watermarks:
                totals["undetectable"] += 1
            if rep.signals or args.all:
                _print_report(f"{name}  ({a.get('id')})", rep, verbose=args.verbose)
            rows.append({"ts": utc_iso(), "mode": "scan-asset", "asset_id": a.get("id"),
                         "name": name, "url": url, **rep.as_dict()})

    # The WARNING above scrolls; this block is what gets read. "AI-flagged 0" is
    # a clean bill of health, and printing it after reading 0 of 5 assets states
    # something the run did not establish — so the count is qualified by the
    # coverage it was measured over, and an all-unreadable run does not get to
    # print a number at all.
    read = totals["files"]
    unread = totals["unreadable"]
    print(f"\n{'─' * 70}")
    print(f"  scanned              {read}"
          + (f"   ({unread} unreadable — status UNKNOWN, not clean)" if unread else ""))
    print(f"  carry metadata       {totals['with_metadata']}")
    if read == 0 and unread:
        print("  AI-flagged (C2PA/IPTC)  n/a   <- NOTHING was read; this is not a clean result")
    else:
        cov = f"   of {read} read" + (f", {unread} NOT read" if unread else "")
        print(f"  AI-flagged (C2PA/IPTC){totals['flagged']:>4}   <- what a crawler reads as "
              f"'AI-generated'{cov}")
    print(f"  removable            {_fmt_bytes(totals['removable_bytes'])}")
    if totals["undetectable"]:
        print(f"  pixel watermark declared on {totals['undetectable']} image(s) — NOT removable by any lossless tool")
    print(f"{'─' * 70}\n")

    if args.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
    if args.log_jsonl:
        append_jsonl(Path(args.log_jsonl), rows)

    # CI surfaces. `--summary-out` is written even when nothing was found: a
    # health surface that only appears on failure reads as "green" during an
    # outage, which is exactly the stale-state trap in rules/.
    if getattr(args, "summary_out", ""):
        flagged_names = [r.get("name") or r.get("path", "") for r in rows
                         if r.get("is_ai_flagged")]
        summary = {
            "ts": utc_iso(),
            "scanned": totals["files"],
            "with_metadata": totals["with_metadata"],
            "ai_flagged": totals["flagged"],
            "removable_bytes": totals["removable_bytes"],
            "pixel_watermark_declared": totals["undetectable"],
            "unreadable": totals["unreadable"],
            "coverage": f"{totals['files'] - totals['unreadable']}/{totals['files']}",
            "flagged_names": flagged_names[:50],
        }
        out_path = Path(args.summary_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
        if getattr(args, "markdown_out", ""):
            md = Path(args.markdown_out)
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(render_markdown_summary(summary), encoding="utf-8")

    if getattr(args, "fail_on_flagged", False) and totals["flagged"]:
        print(f"  FAIL: {totals['flagged']} image(s) carry an AI-provenance signal.", file=sys.stderr)
        return 1
    if totals.get("unreadable"):
        # A scan that could not read part of its input must not exit 0. The CEL
        # cron reads this exit code, and a green run on a scan that saw nothing
        # is indistinguishable from a green run on a clean site.
        print(f"  WARNING: {totals['unreadable']} file(s)/asset(s) could not be read or parsed — "
              "their status is UNKNOWN, not clean.", file=sys.stderr)
        return 2
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    policy = _policy_from_args(args)
    files = iter_local_images(args.local)
    if not files:
        print("No image files matched.")
        return 1
    out_dir = Path(args.out).expanduser() if args.out else None
    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else None
    rows: list[dict] = []
    n_changed = n_skipped = n_error = n_unreadable = n_notimage = 0
    saved = 0

    print(f"\n{'Cleaning' if args.apply else 'DRY RUN — would clean'} {len(files)} file(s)\n")
    for p in files:
        rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
        try:
            data = p.read_bytes()
            rep = ip.scan(data)
            if rep.parse_error:
                # NOT n_skipped: "could not read it" is not "already clean".
                # The summary printed `already clean N` with these folded in.
                if _is_concerning_parse_error(rep):
                    print(f"  UNKNOWN {rel}  ({rep.parse_error})")
                    n_unreadable += 1
                else:
                    print(f"  SKIP   {rel}  (not an image format this tool handles)")
                    n_notimage += 1
                continue
            if not any(s.removable and policy.wants(s.kind) for s in rep.signals):
                n_skipped += 1
                if args.all:
                    print(f"  CLEAN  {rel}")
                continue
            res = ip.strip(data, policy=policy)
        except (ProvenanceError, OSError) as e:
            print(f"  ERROR  {rel}: {e}")
            n_error += 1
            rows.append({"ts": utc_iso(), "mode": "clean", "path": str(p), "error": str(e)})
            continue

        kinds = ",".join(sorted({s.kind for s in res.removed}))
        wm = "  ⚠ pixel watermark declared (NOT removed)" if res.before.undetectable_watermarks else ""
        print(f"  {'STRIP ' if args.apply else 'WOULD '} {rel}  -{_fmt_bytes(res.bytes_removed)}  [{kinds}]{wm}")
        saved += res.bytes_removed
        n_changed += 1
        rows.append({"ts": utc_iso(), "mode": "clean", "path": str(p),
                     "applied": bool(args.apply), **res.as_dict()})

        if args.apply:
            if backup_dir:
                # `rel` is absolute for anything outside the repo, and
                # `backup_dir / <absolute>` silently DISCARDS backup_dir — the
                # "backup" then overwrote the original in place and the backup
                # directory stayed empty. Always mirror a relative path.
                mirror = rel if not rel.is_absolute() else Path(*p.parts[1:])
                dest = backup_dir / mirror
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            target = (out_dir / p.name) if out_dir else p
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(res.data)

    print(f"\n{'─' * 70}")
    print(f"  {'stripped' if args.apply else 'would strip'}  {n_changed}   "
          f"already clean {n_skipped}   errors {n_error}")
    if n_notimage:
        print(f"  not an image format   {n_notimage}")
    if n_unreadable:
        print(f"  UNREADABLE            {n_unreadable}   <- status UNKNOWN, NOT clean")
    print(f"  bytes removed        {_fmt_bytes(saved)}")
    if not args.apply and n_changed:
        print("\n  Re-run with --apply to write the changes.")
    print(f"{'─' * 70}\n")
    if args.log_jsonl:
        append_jsonl(Path(args.log_jsonl), rows)
    return 0 if (n_error == 0 and n_unreadable == 0) else 2


def cmd_replace(args: argparse.Namespace) -> int:
    """Strip images already on Webflow, re-upload, and re-point CMS references."""
    policy = _policy_from_args(args)
    cfg = load_site_config(args.site)
    token = resolve_site_token(args.site, getattr(args, "token", None))
    site_id = cfg["webflow_site_id"]
    backup_dir = Path(args.backup_dir).expanduser()
    log_path = Path(args.log_jsonl) if args.log_jsonl else DEFAULT_LOG_PATH

    print(f"\n{'REPLACE' if args.apply else 'DRY RUN — replace'} on site '{args.site}' ({site_id})")
    if not args.apply:
        print("  No writes will be made. Re-run with --apply after approval.\n")

    print("  Building CMS reference index…")
    index, summaries = build_reference_index(token, site_id,
                                             collections_filter=args.collections,
                                             progress=not args.quiet)
    total_refs = sum(len(v) for v in index.values())
    print(f"  {len(index)} distinct image URLs referenced, {total_refs} references total")

    # The published-site index answers the question the Data API cannot: is this
    # asset also placed directly on a page in the Designer? If it is, a change of
    # asset id silently breaks that page, because nothing here can rewrite it.
    live_index: dict[str, list[str]] = {}
    live_known = False
    site_domains = evidence_domains(args.site, cfg, args.site_url)
    site_url = site_domains[0] if site_domains else ""
    if args.check_live_pages and site_domains:
        live_index, fetched, live_failed = crawl_evidence_domains(
            args.site, cfg, args.site_url,
            limit=args.live_page_limit, progress=not args.quiet)
        # "known" requires COMPLETE coverage: a partial crawl cannot prove absence.
        live_known = bool(fetched) and not live_failed
        print(f"  {len(live_index)} distinct image URLs across {len(fetched)} published page(s)\n")
    elif args.check_live_pages:
        print("  ! --check-live-pages given but no domain on record for this site "
              "(pass --site-url, or add `live_url`/`staging_url` to site.json)\n")
    else:
        print("  (live-page index skipped — pass --check-live-pages to enable)\n")

    assets = list_assets(token, site_id, limit=args.limit)
    if getattr(args, "only_referenced", False):
        # `--collections` alone only narrows the REFERENCE index; without this the
        # tool would still walk every asset on the site and merely re-point fewer
        # of them. Combined with --collections it means "just this collection's
        # images", which is what "start with Team Members" asks for.
        before_n = len(assets)
        assets = [a for a in assets if lookup_refs(index, a.get("hostedUrl", ""))[0]]
        print(f"  --only-referenced: {before_n} asset(s) on the site -> "
              f"{len(assets)} referenced by the selected collection(s).")
    known = load_known_clean(Path(args.skip_known_clean)) if args.skip_known_clean else set()
    if known:
        before_n = len(assets)
        assets = [a for a in assets if a.get("id") not in known]
        print(f"  {before_n - len(assets)} asset(s) already proven clean — skipping them.")
    # Idempotence. A Webflow asset is immutable, so a successful replace leaves
    # the dirty original in the asset list; without this the next run replaces
    # it AGAIN, minting a fresh orphan every night. Deliberately NOT folded into
    # `known`: the original is superseded, not clean, and `scan` must keep
    # reporting it so the site's true state stays visible.
    superseded: dict[str, str] = {}
    if args.skip_known_clean and not args.no_skip_superseded:
        superseded = load_superseded(Path(args.skip_known_clean))
        hit = [a for a in assets if a.get("id") in superseded]
        if hit:
            assets = [a for a in assets if a.get("id") not in superseded]
            print(f"  {len(hit)} asset(s) already replaced by a clean copy — skipping "
                  "(they are orphans now; `purge` removes them, `replace` would "
                  "only mint more).")
            for a in hit[:5]:
                print(f"      {asset_basename(a.get('originalFileName', ''), a.get('displayName', ''))}"
                      f"  {a.get('id')} -> {superseded[a['id']]}")
            if len(hit) > 5:
                print(f"      … and {len(hit) - 5} more")
    if args.asset_id:
        wanted = {a.strip() for a in args.asset_id.split(",") if a.strip()}
        assets = [a for a in assets if a.get("id") in wanted]
    print(f"  Examining {len(assets)} asset(s)…\n")

    rows: list[dict] = []
    stats = {"examined": 0, "clean": 0, "stripped": 0, "repointed": 0,
             "refused": 0, "errors": 0, "bytes": 0, "undetectable": 0, "unreadable": 0}
    to_publish: dict[str, set[str]] = {}

    for a in assets:
        asset_id = a.get("id", "")
        url = a.get("hostedUrl") or ""
        name = asset_basename(a.get("originalFileName", ""), a.get("displayName", ""))
        if not url or not name:
            continue
        if args.pattern and not fnmatch.fnmatch(name, args.pattern):
            continue
        stats["examined"] += 1

        row: dict = {"ts": utc_iso(), "mode": "replace", "site": args.site,
                     "asset_id": asset_id, "name": name, "old_url": url,
                     "applied": bool(args.apply)}
        try:
            data = download_image(url)
            rep = ip.scan(data)
            if rep.parse_error:
                # cmd_scan already treats this as a coverage failure. The
                # commands that exist to FIX such an asset printed one SKIP
                # line, touched no counter and exited 0 — so the same corrupt,
                # manifest-bearing file reddened the nightly and was silently
                # passed over by every repair run.
                if _is_concerning_parse_error(rep):
                    stats["unreadable"] += 1
                    print(f"  UNKNOWN {name}  ({rep.parse_error}) — status UNKNOWN, not clean")
                else:
                    print(f"  SKIP    {name}  (not an image format this tool handles)")
                row["action"] = "skip_unparseable"
                rows.append(row)
                continue
            if not any(s.removable and policy.wants(s.kind) for s in rep.signals):
                stats["clean"] += 1
                row["action"] = "already_clean"
                rows.append(row)
                if args.all:
                    print(f"  CLEAN   {name}")
                continue
            res = ip.strip(data, policy=policy)
        except (ProvenanceError, APIError, NetworkError, urllib.error.HTTPError,
                urllib.error.URLError, OSError, ValueError) as e:
            stats["errors"] += 1
            print(f"  ERROR   {name}: {type(e).__name__}: {e}")
            row["action"] = "error"
            row["error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            continue

        refs, ref_how = lookup_refs(index, url)
        if ref_how == "ambiguous":
            stats["refused"] += 1
            print(f"  AMBIG   {name}: filename resolves to several distinct images — refusing.")
            row["action"] = "refused_ambiguous_basename"
            rows.append(row)
            continue
        kinds = ",".join(sorted({s.kind for s in res.removed}))
        wm = res.before.undetectable_watermarks
        if wm:
            stats["undetectable"] += 1
        row.update({"removed_kinds": kinds, "bytes_removed": res.bytes_removed,
                    "cms_refs": len(refs), "ref_match": ref_how,
                    "undetectable_watermarks": wm})

        page_refs_preview, _ = lookup_refs(live_index, url)
        row["page_refs_count"] = len(page_refs_preview)
        note = f"  ⚠ {wm[0]}" if wm else ""
        pg = f" pages={len(page_refs_preview)}" if live_known else ""
        print(f"  {'STRIP  ' if args.apply else 'WOULD  '} {name}  -{_fmt_bytes(res.bytes_removed)}"
              f"  [{kinds}]  cms={len(refs)}{pg}{note}")

        if not args.apply:
            stats["stripped"] += 1
            stats["bytes"] += res.bytes_removed
            row["action"] = "would_replace"
            rows.append(row)
            continue

        # ---- decide BEFORE writing ---------------------------------------
        # This refusal used to sit AFTER upload_bytes, because the id change it
        # reacts to is only knowable once the upload returns. But both REASONS
        # for refusing are knowable beforehand — they depend on live_index and
        # live_known, which are fixed for the whole run. So the old order paid a
        # permanent orphan on the client's site for information it already had:
        # every refusal left an unreferenced copy behind that only `purge` could
        # remove, on a site the tool is supposed to leave tidier than it found.
        #
        # Webflow mints a new asset id on every upload (the CDN URL embeds it),
        # so "the id might come back the same" is not a bet worth an orphan.
        if not args.allow_new_asset_id:
            page_refs, _ = lookup_refs(live_index, url)
            if page_refs:
                reason = (f"still referenced on {len(page_refs)} published page(s), "
                          f"e.g. {page_refs[0]}")
            elif not live_known:
                reason = ("cannot prove no Designer page references it "
                          "(live-page index unavailable)")
            else:
                reason = ""
            if reason:
                stats["refused"] += 1
                print(f"          ! REFUSED before upload: replacing {name} would mint a new "
                      f"asset id and {reason}.")
                print("            Fix those in the Designer via /webflow-implement, "
                      "or re-run with --allow-new-asset-id to accept the risk.")
                row["action"] = "refused_id_change"
                row["refusal_reason"] = reason
                row["page_refs"] = page_refs[:10]
                row["orphan_created"] = False
                rows.append(row)
                continue

        # ---- writes begin here -------------------------------------------
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"{asset_id}_{name}").write_bytes(data)

        try:
            up = upload_bytes(res.data, name, site_id, token)
        except (APIError, NetworkError, RuntimeError, ValueError,
                urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            stats["errors"] += 1
            print(f"          ! upload failed: {type(e).__name__}: {e}")
            row["action"] = "upload_error"
            row["error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            continue

        new_id, new_url = up["asset_id"], up["hostedUrl"]
        same_identity = (new_id == asset_id)
        row.update({"new_asset_id": new_id, "new_url": new_url, "same_asset_id": same_identity})

        if not same_identity and not args.allow_new_asset_id:
            # Backstop. The pre-upload gate above already refuses on both known
            # reasons, so reaching here means live_index disagreed with itself
            # mid-run. Keep it — but say plainly that an orphan now exists and
            # name the id, because a refusal that hides its own side effect is
            # how the client's asset list silently grew.
            page_refs, _ = lookup_refs(live_index, url)
            if page_refs or not live_known:
                reason = (f"still referenced on {len(page_refs)} published page(s)"
                          if page_refs else "cannot prove no Designer page references it")
                stats["refused"] += 1
                stats["errors"] += 1
                print(f"          ! REFUSED after upload: asset id changed "
                      f"{asset_id} -> {new_id}; {reason}.")
                print(f"            An unreferenced copy now exists as {new_id} — "
                      f"remove it with: watermark_cleaner.py purge --site {args.site} "
                      f"--asset-id {new_id} --apply")
                row.update({"action": "refused_id_change", "refusal_reason": reason,
                            "page_refs": page_refs[:10], "orphan_created": True,
                            "orphan_asset_id": new_id})
                rows.append(row)
                continue

        n_ok = 0
        staged: dict[str, set[str]] = {}
        for ref in refs:
            try:
                out = repoint_reference(token, ref, old_url=url, new_url=new_url,
                                        new_file_id=new_id, apply=True)
                if out["status"] == "repointed":
                    n_ok += 1
                    # Queue for publish ONLY on success. A careless string patch
                    # once moved this line into the ambiguous branch, so
                    # successful re-points were never published while UNWRITTEN
                    # ones were queued — the precise inverse of correct.
                    if ref.was_published and not ref.is_draft and not ref.is_archived:
                        # Staged, NOT queued. Publishing is the irreversible half
                        # of this command; doing it before the verify decision
                        # pushed bytes live that the very next line reported as
                        # unverifiable. Promoted below, only on success.
                        staged.setdefault(ref.collection_id, set()).add(ref.item_id)
                elif out["status"] == "ref-ambiguous":
                    # The reference could not be resolved to ONE entry. Surfaced,
                    # not guessed — n_ok stays short, which makes the run
                    # incomplete and therefore an error.
                    print(f"          ! AMBIGUOUS ref in {ref.collection_slug}/{ref.item_slug}"
                          f".{ref.field_slug}: {len(out.get('candidates', []))} candidates share "
                          "this filename — not rewritten.")
            except (APIError, NetworkError, urllib.error.HTTPError,
                    urllib.error.URLError, OSError) as e:
                print(f"          ! repoint failed on {ref.collection_slug}/{ref.item_slug}: {e}")

        # The outcome is decided ONCE, from what actually happened. Setting
        # action="incomplete_repoint" and then unconditionally row.update(
        # {"action": "replaced"}) one line later meant the log always said
        # "replaced" — and load_known_clean reads that as proof, so a
        # half-completed replace marked the still-dirty original clean forever.
        verify = verify_live(new_url, policy=policy) if args.verify else {}
        incomplete = bool(refs) and n_ok < len(refs)
        verify_failed = bool(args.verify) and not verify.get("clean")
        if verify_failed:
            print(f"          ! not queuing {len(staged)} collection(s) for publish — "
                  "the replacement bytes did not verify.")
        else:
            for cid, ids in staged.items():
                to_publish.setdefault(cid, set()).update(ids)

        if incomplete:
            stats["errors"] += 1
            print(f"          ! INCOMPLETE: re-pointed {n_ok}/{len(refs)} reference(s) — "
                  f"the CMS still points at the un-stripped file.")
        if verify_failed:
            # A verifier whose failure changes nothing is decorative. It must
            # move the action, the error count and therefore the exit code.
            stats["errors"] += 1
            print(f"          ! VERIFY FAILED on {new_url.rsplit('/', 1)[-1]} — "
                  f"{verify.get('verdict', 'not clean')}; treating this asset as NOT done.")

        action = ("incomplete_repoint" if incomplete
                  else "verify_failed" if verify_failed
                  else "replaced")
        row.update({"action": action, "repointed": n_ok, "verify": verify})
        if action == "replaced":
            # The forward link load_superseded() reads. Written only on the
            # fully-successful branch, so an incomplete or unverified run
            # leaves the original eligible for another attempt.
            row["superseded_by"] = new_id
        stats["stripped"] += 1
        stats["repointed"] += n_ok
        stats["bytes"] += res.bytes_removed
        status = ("verified clean" if verify.get("clean")
                  else "VERIFY FAILED" if args.verify else "not verified")
        print(f"          -> {new_url.rsplit('/', 1)[-1]}  repointed {n_ok}/{len(refs)}  [{status}]")
        rows.append(row)

    if args.apply and args.auto_publish and to_publish:
        print("\n  Publishing touched CMS items…")
        for cid, ids in to_publish.items():
            try:
                publish_items(token, cid, sorted(ids))
                print(f"    published {len(ids)} item(s) in {cid}")
            except (APIError, NetworkError) as e:
                # A publish failure left the CMS holding the correct, stripped
                # reference in DRAFT while the live page kept serving the old
                # one — and the run still exited 0. It is an error like any other.
                stats["errors"] += 1
                print(f"    ! PUBLISH FAILED for {cid}: {e}")
                print(f"      {len(ids)} item(s) were re-pointed but are NOT live; "
                      "the published page still serves the un-stripped image.")

    print(f"\n{'─' * 70}")
    print(f"  examined {stats['examined']}   already clean {stats['clean']}   "
          f"{'replaced' if args.apply else 'would replace'} {stats['stripped']}")
    print(f"  CMS refs re-pointed  {stats['repointed']}")
    if stats["refused"]:
        print(f"  REFUSED (asset id changed, refs unreachable)  {stats['refused']}")
    if stats["unreadable"]:
        print(f"  UNREADABLE           {stats['unreadable']}   <- status UNKNOWN, NOT clean")
    if stats["errors"]:
        print(f"  errors               {stats['errors']}")
    print(f"  bytes removed        {_fmt_bytes(stats['bytes'])}")
    if stats["undetectable"]:
        print(f"\n  {stats['undetectable']} image(s) declare a pixel watermark (SynthID / c2pa.watermarked).")
        print("  That is in the pixels, not the metadata. It is NOT removed and cannot be")
        print("  removed losslessly. Do not describe these images as watermark-free.")
    if not args.apply and stats["stripped"]:
        print("\n  This was a dry run. Get explicit approval, then re-run with --apply.")
    print(f"{'─' * 70}\n")

    if args.apply or args.log_jsonl:
        # Same rule as cmd_cms: a dry run must not append to the DEFAULT log,
        # because load_known_clean() reads it — a preview would otherwise seed
        # the known-clean cache and make a later real run skip that asset.
        append_jsonl(log_path, rows)
    return 0 if (stats["errors"] == 0 and stats["unreadable"] == 0) else 2


# ── perceptual lineage ───────────────────────────────────────────────────────
# Metadata detection has one structural blind spot: an AI image that has been
# resized or converted carries no metadata at all, so it reads as clean. That is
# not a detection failure to fix — the metadata really is gone — but it does mean
# "how many of these were AI-generated?" cannot be answered from metadata.
#
# It CAN be answered from lineage. We hold the originals (in the repo, and in
# data/watermark-backup with their markers intact). A difference hash survives
# resize and re-encode, so an uploaded derivative can be matched back to the
# marked original it came from. That is positive evidence of AI origin for a file
# that carries no trace of it.
PHASH_BITS = 512
PHASH_MATCH_MAX = 40      # measured: same image after resize+WebP = 1-4; different images = 228-270


def _px(img):
    """Pillow 14 renames getdata() to get_flattened_data(); prefer the new name."""
    getter = getattr(img, "get_flattened_data", None) or img.getdata
    return list(getter())


def _autotrim(im, tol: int = 12):
    """Remove a uniform border, so that padding does not change the hash.

    Measured on the real team-headshot pipeline (`iod-report.json` scale+pad
    parameters, then a 700px WebP): padding of 92-284px moved the plain hash by
    99-205 bits — far past the match threshold, so a padded derivative of a
    known AI original scored as unrelated. Trimming first brings the same cases
    to 3-8 bits. Unrelated images stay 228-270 apart either way, so this costs
    nothing in false positives.

    The bbox must keep >30% of each dimension, otherwise a near-uniform image
    (a flat colour block, a dark frame) would trim to almost nothing and every
    such image would collide with every other.
    """
    from PIL import Image, ImageChops
    g = im.convert("RGB")
    for corner in ((0, 0), (g.width - 1, 0), (0, g.height - 1), (g.width - 1, g.height - 1)):
        bg = Image.new("RGB", g.size, g.getpixel(corner))
        mask = ImageChops.difference(g, bg).convert("L").point(lambda v: 255 if v > tol else 0)
        bb = mask.getbbox()
        if bb and (bb[2] - bb[0]) > g.width * 0.3 and (bb[3] - bb[1]) > g.height * 0.3:
            return g.crop(bb)
    return g


def perceptual_hash(data: bytes, size: int = 16, *, trim: bool = False) -> int:
    """512-bit row+column difference hash. Robust to resize and re-encode.

    With ``trim=True`` a uniform border is removed first, which additionally
    makes the hash robust to padding. Pillow is imported lazily so the rest of
    this module keeps working on hosts without it (same pattern as
    avif_optimizer.encode_avif).
    """
    from PIL import Image
    try:
        import pillow_avif  # noqa: F401  (registers the AVIF plugin)
    except ImportError:
        pass

    im = Image.open(io.BytesIO(data))
    im = (_autotrim(im) if trim else im).convert("L")
    rows = _px(im.resize((size + 1, size), Image.LANCZOS))
    cols = _px(im.resize((size, size + 1), Image.LANCZOS))
    value = 0
    for y in range(size):
        for x in range(size):
            value = (value << 1) | int(rows[y * (size + 1) + x] < rows[y * (size + 1) + x + 1])
    for y in range(size):
        for x in range(size):
            value = (value << 1) | int(cols[y * size + x] < cols[(y + 1) * size + x])
    return value


# A difference hash compares adjacent pixels. On a flat or near-flat image every
# comparison is a tie, so the hash is all-zeros — and ALL such images are then
# identical to each other at distance 0. Measured: five different solid colours
# all matched each other at 0, while 25 real photographs from the corpus scored
# 189-241 bits of 512 (median 241). 64 sits in that gap with enormous margin.
#
# Without this guard, lineage would report a client's plain-colour tile or a
# blank placeholder as a derivative of an AI original — the worst possible false
# positive, because it labels real work as machine-made.
MIN_FINGERPRINT_BITS = 64


def fingerprint_is_degenerate(fp: tuple[int, int]) -> bool:
    """True when a fingerprint carries too little signal to identify anything."""
    return max(bin(fp[0]).count("1"), bin(fp[1]).count("1")) < MIN_FINGERPRINT_BITS


def perceptual_fingerprint(data: bytes) -> tuple[int, int]:
    """(plain, trimmed) hashes. Matching takes the better of the two.

    Two hashes rather than only the trimmed one: trimming is a heuristic, and on
    an image whose real content reaches the edge it is a no-op, while on one with
    a legitimate uniform frame as part of the composition it removes real signal.
    Keeping both means neither failure mode can hide a true match.
    """
    return perceptual_hash(data), perceptual_hash(data, trim=True)


def fingerprint_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return min(hamming(a[0], b[0]), hamming(a[1], b[1]))


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def build_lineage_corpus(paths: list[str], *, progress: bool = True
                        ) -> tuple[list[dict], list[str]]:
    """Hash every local image that carries an AI-generation marker.

    Reads both the working tree and ``data/watermark-backup`` — the backup is
    what still holds the markers for files this tool has already stripped, so
    cleaning the sources does not destroy the ability to identify their
    derivatives later.

    Returns ``(corpus, sources_that_contributed_nothing)``. The second value is
    not decoration: ``iter_local_images`` yields nothing for a directory that
    does not exist rather than raising, so a wrong ``--source`` produced a
    silently smaller corpus and every query against it answered a confident
    "not AI-descended".
    """
    corpus: list[dict] = []
    seen_hashes: set[tuple[int, int]] = set()
    empty: list[str] = []
    for one in paths:
        if not iter_local_images([one]):
            empty.append(one)
    for p in iter_local_images(paths):
        try:
            data = p.read_bytes()
        except OSError:
            continue
        rep = ip.scan(data)
        if not rep.is_ai_flagged:
            continue
        try:
            fp = perceptual_fingerprint(data)
        except Exception:
            continue
        if fingerprint_is_degenerate(fp):
            # A flat original identifies nothing — admitting it would make every
            # flat asset on the site "match" it.
            continue
        if fp in seen_hashes:
            continue
        seen_hashes.add(fp)
        corpus.append({"path": str(p), "fp": fp, "generators": rep.ai_generators})
        if progress and len(corpus) % 25 == 0:
            print(f"    hashed {len(corpus)} AI-marked originals…", flush=True)
    return corpus, empty


def cmd_lineage(args: argparse.Namespace) -> int:
    """Identify remote assets that are derivatives of known AI-generated sources."""
    cfg = load_site_config(args.site)
    token = resolve_site_token(args.site, getattr(args, "token", None))
    site_id = cfg["webflow_site_id"]

    # `cmd_clean` mirrors the source tree under the backup dir; `cmd_replace` and
    # `cmd_cms` write FLAT into the backup ROOT ({asset_id}_{name} and
    # {site}_{url_key}). Defaulting to the mirrored path alone excluded every
    # backup the scrub itself made — precisely the population lineage exists to
    # identify — and reported a smaller corpus without saying anything was missing.
    sources = args.source or [f"sites/{args.site}",
                              f"data/watermark-backup/sites/{args.site}",
                              "data/watermark-backup"]
    print(f"\nBuilding AI-lineage corpus from: {', '.join(sources)}")
    corpus, empty_sources = build_lineage_corpus(sources, progress=not args.quiet)
    print(f"  {len(corpus)} distinct AI-marked original(s) hashed")
    if empty_sources:
        # A source that yielded nothing is reported, never silently dropped: a
        # corpus that quietly shrank still answers every query with a confident
        # "not AI-descended".
        print(f"  ! {len(empty_sources)} source(s) contributed nothing: "
              f"{', '.join(empty_sources)}")
        print("    (a missing or already-stripped directory narrows the corpus — "
              "matches below are only as complete as what was read)")
    print()
    if not corpus:
        print("  No AI-marked originals found — nothing to match against.")
        print("  (If the sources were already stripped, point --source at data/watermark-backup.)")
        return 1

    assets = list_assets(token, site_id, limit=args.limit)
    print(f"Matching {len(assets)} Webflow asset(s) against the corpus…\n")
    rows: list[dict] = []
    matched = clean_derivative = still_dirty = skipped_flat = 0
    fetch_errors = 0

    for a in assets:
        url = a.get("hostedUrl") or ""
        name = asset_basename(a.get("originalFileName", ""), a.get("displayName", ""))
        if not url or not name:
            continue
        if args.pattern and not fnmatch.fnmatch(name, args.pattern):
            continue
        try:
            data = download_image(url)
            rep = ip.scan(data)
            fp = perceptual_fingerprint(data)
        except Exception as e:  # noqa: BLE001 — fonts/SVG/unsupported all land here
            fetch_errors += 1
            rows.append({"name": name, "asset_id": a.get("id"), "action": "error",
                         "error": f"{type(e).__name__}: {e}"})
            continue

        if fingerprint_is_degenerate(fp):
            # Too little signal to identify. Reported, not silently matched or
            # silently dropped.
            skipped_flat += 1
            rows.append({"ts": utc_iso(), "mode": "lineage", "site": args.site,
                         "asset_id": a.get("id"), "name": name,
                         "action": "skipped_low_detail"})
            continue
        best = min(corpus, key=lambda c: fingerprint_distance(c["fp"], fp))
        dist = fingerprint_distance(best["fp"], fp)
        if dist > PHASH_MATCH_MAX:
            continue

        matched += 1
        has_meta = any(s.removable for s in rep.signals)
        if has_meta:
            still_dirty += 1
        else:
            clean_derivative += 1
        rows.append({
            "ts": utc_iso(), "mode": "lineage", "site": args.site,
            "asset_id": a.get("id"), "name": name, "url": url,
            "distance": dist, "source": best["path"], "generators": best["generators"],
            "carries_metadata": has_meta,
            "signals": [s.kind for s in rep.signals],
        })
        flag = "HAS METADATA" if has_meta else "already clean"
        print(f"  AI-DERIVED  {name[:46]:46} d={dist:>3}  {flag:13} "
              f"<- {pathlib_name(best['path'])}  [{','.join(best['generators'])}]")

    print(f"\n{'─' * 78}")
    print(f"  assets checked            {len(assets)}")
    print(f"  could not be read         {fetch_errors}")
    print(f"  too flat to identify      {skipped_flat}")
    print(f"  matched an AI original    {matched}")
    print(f"    of those, still carry removable metadata  {still_dirty}")
    print(f"    of those, already metadata-clean          {clean_derivative}")
    print()
    print("  A clean derivative has nothing left to strip — the resize/convert that")
    print("  produced it already destroyed the metadata. It is still an AI-generated")
    print("  image, and any pixel-domain watermark it carries is untouched and")
    print("  undetectable from here. This command answers 'which are AI?', which is")
    print("  a different question from 'which can be cleaned?'.")
    print(f"{'─' * 78}\n")
    if args.log_jsonl:
        append_jsonl(Path(args.log_jsonl), rows)
    if args.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
    if fetch_errors:
        # A lineage run where every fetch failed used to print a confident
        # "matched 0" and exit 0 — indistinguishable from a site with no AI.
        print(f"  WARNING: {fetch_errors} asset(s) could not be read; "
              "their status is UNKNOWN, not 'not AI'.", file=sys.stderr)
        return 2
    return 0


def pathlib_name(p: str) -> str:
    return Path(p).name


def _registry_production_url(site_nickname: str) -> str:
    """The site's production host from sites/registry.json, if it names one."""
    try:
        reg = json.loads((ROOT / "sites" / "registry.json").read_text(encoding="utf-8"))
        entry = (reg.get("sites") or {}).get(site_nickname) or {}
        prod = (entry.get("production_url") or "").strip()
        stg = (entry.get("staging_url") or "").strip()
        return prod if prod and prod != stg else ""
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def evidence_domains(site_nickname: str, cfg: dict, override: str) -> list[str]:
    """EVERY domain that could serve this Webflow site.

    "Production or staging?" is the wrong question. brightvalley's Webflow build
    lives on the .webflow.io staging host while its production domain still runs
    WordPress; CEL is the other way round. Picking one and hoping proves nothing
    — crawling staging to justify deleting an asset production serves is wrong,
    and so is crawling a WordPress production host to justify deleting a Webflow
    staging asset (it would find nothing, "proving" absence trivially).

    So use all of them. Absence has to hold on every domain that could serve the
    asset, and cmd_purge holds when any of them is unreadable.
    """
    if override:
        return [override.rstrip("/")]
    out: list[str] = []
    for u in (cfg.get("live_url"), cfg.get("staging_url"), cfg.get("url"),
              _registry_production_url(site_nickname)):
        u = (u or "").strip().rstrip("/")
        if u and u not in out:
            out.append(u)
    return out


def crawl_evidence_domains(site_nickname: str, cfg: dict, override: str, *,
                           limit: int = 0, progress: bool = True
                           ) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Index every domain that could serve this site, merged.

    `evidence_domains` was the file's most careful piece of domain resolution
    and exactly ONE of the three commands that need it used it. `replace` and
    `cms` each rolled their own `cfg.get("live_url")` lookup, which misses
    `staging_url` — and brightvalley's Webflow build lives on the staging host
    while its production domain still runs WordPress. On the site the tool was
    written for, both commands silently found no URL to crawl and reported
    nothing, which is the failure mode this whole audit keeps finding.

    Returns (index, pages_fetched, failures) with the same contract as
    `build_live_page_index`, so `bool(pages) and not failures` remains the
    single honest definition of "coverage is complete".
    """
    index: dict[str, list[str]] = {}
    pages: list[str] = []
    failures: list[str] = []
    domains = evidence_domains(site_nickname, cfg, override)
    if not domains:
        return index, pages, ["<no-domain>"]
    for dom in domains:
        print(f"  Evidence domain: {dom}")
        idx, got, failed = build_live_page_index(dom, limit=limit, progress=progress)
        for k, v in idx.items():
            index.setdefault(k, []).extend(v)
        pages += got
        failures += failed
    return index, pages, failures


def delete_asset(token: str, asset_id: str) -> dict:
    return rate_limited_request("DELETE", f"{WEBFLOW_API_BASE}/assets/{asset_id}", token)


def asset_id_appears_in_cms(token: str, site_id: str, asset_ids: set[str]) -> dict[str, list[str]]:
    """Search every CMS field for the LITERAL asset id.

    This is deliberately not ``lookup_refs``: the basename fallback reports a
    false positive here, because a replacement asset shares its filename with
    the original it replaced. For a delete decision only the exact id will do —
    a wrong answer costs an image that nothing can restore.
    """
    hits: dict[str, list[str]] = {a: [] for a in asset_ids}
    for col in list_collections(token, site_id):
        cid = col.get("id")
        if not cid:
            continue
        for item in list_items(token, cid):
            blob = json.dumps(item.get("fieldData", {}) or {})
            for aid in asset_ids:
                if aid in blob:
                    hits[aid].append(f"{col.get('slug')}/{(item.get('fieldData') or {}).get('slug')}")
    return hits


def cmd_purge(args: argparse.Namespace) -> int:
    """Delete AI-flagged assets that nothing references any more.

    Four independent conditions, ALL required, checked immediately before the
    delete rather than trusted from an earlier run:
      1. the asset still carries an AI-provenance signal (there is a reason);
      2. its literal id appears in no CMS field in any collection;
      3. it appears on no published page;
      4. a byte-identical backup exists on disk.
    Anything failing any check is held, not deleted. Deletion is irreversible;
    this refuses far more readily than it acts.
    """
    cfg = load_site_config(args.site)
    token = resolve_site_token(args.site, getattr(args, "token", None))
    site_id = cfg["webflow_site_id"]
    backup_dir = Path(args.backup_dir).expanduser()

    print(f"\n{'PURGE' if args.apply else 'DRY RUN — purge'} on '{args.site}' ({site_id})")
    if not args.apply:
        print("  No deletions will be made.\n")

    assets = list_assets(token, site_id, limit=args.limit)
    candidates = []
    print(f"  Scanning {len(assets)} asset(s) for AI-flagged, unreferenced originals…")
    for a in assets:
        url, aid = a.get("hostedUrl") or "", a.get("id", "")
        name = asset_basename(a.get("originalFileName", ""), a.get("displayName", ""))
        if not url or not aid:
            continue
        if args.asset_id and aid not in {x.strip() for x in args.asset_id.split(",")}:
            continue
        try:
            data = download_image(url)
        except Exception:
            continue
        rep = ip.scan(data)
        if not rep.is_ai_flagged:
            continue
        candidates.append({"id": aid, "name": name, "url": url, "bytes": data,
                           "generators": rep.ai_generators, "kinds": rep.kinds})
    print(f"  {len(candidates)} AI-flagged asset(s) found\n")
    if not candidates:
        print("  Nothing to purge.\n")
        return 0

    cms_hits = asset_id_appears_in_cms(token, site_id, {c["id"] for c in candidates})
    # WHICH domain proves "no published page uses this"? Crawling staging to
    # justify deleting an asset that production serves proves the wrong thing.
    # brightvalley has no live_url, so this silently fell back to the .webflow.io
    # staging domain while the registry named a separate production host.
    live_index: dict[str, list[str]] = {}
    pages: list[str] = []
    page_failures: list[str] = []
    if args.check_live_pages:
        live_index, pages, page_failures = crawl_evidence_domains(
            args.site, cfg, args.site_url, progress=not args.quiet)
        if page_failures == ["<no-domain>"]:
            print("  ! No domain on record for this site — cannot prove any page is free of it.")

    deleted = held = 0
    for c in candidates:
        cms = cms_hits.get(c["id"], [])
        page = [p for k, v in live_index.items() if c["id"] in k for p in v]
        bk = list(backup_dir.rglob(f"*{c['id']}*")) or list(backup_dir.rglob(c["name"]))
        bk_ok = any(b.is_file() and b.read_bytes() == c["bytes"] for b in bk)
        reasons = []
        if cms:
            reasons.append(f"referenced by CMS {cms[:2]}")
        if page:
            reasons.append(f"on published page {page[:1]}")
        if not bk_ok:
            reasons.append("no byte-identical backup on disk")
        if args.check_live_pages and not pages:
            reasons.append("could not read the published site to prove no page uses it")
        elif args.check_live_pages and page_failures:
            # Partial coverage is not proof. One unreadable page is enough to
            # make "no page references this asset" an unsupported claim, and the
            # delete is irreversible.
            reasons.append(f"{len(page_failures)} published page(s) unreadable — "
                           "cannot prove no page uses it")

        if reasons:
            held += 1
            print(f"  HOLD    {c['name'][:46]:46} — {'; '.join(reasons)}")
            continue
        if not args.apply:
            print(f"  WOULD   {c['name'][:46]:46} delete {c['id']}  [{','.join(c['generators'])}]")
            deleted += 1
            continue
        try:
            delete_asset(token, c["id"])
            deleted += 1
            print(f"  DELETED {c['name'][:46]:46} {c['id']}")
        except (APIError, NetworkError) as e:
            held += 1
            print(f"  FAILED  {c['name'][:46]:46} {type(e).__name__}: {e}")

    print(f"\n{'─' * 70}")
    print(f"  {'deleted' if args.apply else 'would delete'} {deleted}   held {held}")
    if held:
        print("  Held assets were NOT touched. Resolve the reason above and re-run.")
    if not args.apply and deleted:
        print("\n  This was a dry run. Deletion is irreversible — re-run with --apply.")
    print(f"{'─' * 70}\n")
    return 0


def cmd_cms(args: argparse.Namespace) -> int:
    """Walk CMS image references directly, rather than the site's asset list.

    Why this exists: ``GET /sites/{id}/assets`` does not return images uploaded
    straight into a CMS item. On brightvalley — a WordPress import — that is
    **every** CMS image: 214 assets listed, 164 CMS-referenced images, zero
    overlap. An asset-driven replace simply cannot see them, and reports
    "nothing to do" rather than "cannot reach". This walks the collections
    instead, so the unit of work is a *reference*, not an asset.

    Each distinct image URL is downloaded once, stripped once, uploaded once,
    and then every reference pointing at it is re-pointed — so an image reused
    across ten items costs one upload, not ten.
    """
    policy = _policy_from_args(args)
    cfg = load_site_config(args.site)
    token = resolve_site_token(args.site, getattr(args, "token", None))
    site_id = cfg["webflow_site_id"]
    backup_dir = Path(args.backup_dir).expanduser()
    log_path = Path(args.log_jsonl) if args.log_jsonl else DEFAULT_LOG_PATH

    print(f"\n{'CMS REPLACE' if args.apply else 'DRY RUN — CMS replace'} on '{args.site}' ({site_id})")
    if not args.apply:
        print("  No writes will be made. Re-run with --apply after approval.\n")

    print("  Building CMS reference index…")
    index, _summaries = build_reference_index(token, site_id,
                                              collections_filter=args.collections,
                                              progress=not args.quiet)
    print(f"  {len(index)} distinct image URLs, "
          f"{sum(len(v) for v in index.values())} reference(s)")

    # An image can live in a CMS field AND be placed directly on a page in the
    # Designer. This command rewrites the CMS reference and mints a new asset id
    # — which leaves the Designer reference pointing at the ORIGINAL, still
    # serving the un-stripped bytes, while the run reports success.
    #
    # Unlike `replace` this does not refuse: the CMS half is genuinely fixable
    # and refusing would leave everything dirty. It does the work, then names
    # the Designer references as remaining work and counts them, so the run
    # cannot exit 0 while a dirty image is still published.
    live_index: dict[str, list[str]] = {}
    live_known = False
    site_domains = evidence_domains(args.site, cfg, args.site_url)
    site_url = site_domains[0] if site_domains else ""
    if args.check_live_pages and site_domains:
        live_index, fetched, live_failed = crawl_evidence_domains(
            args.site, cfg, args.site_url,
            limit=args.live_page_limit, progress=not args.quiet)
        live_known = bool(fetched) and not live_failed
        print(f"  {len(live_index)} distinct image URLs across {len(fetched)} published page(s)")
    elif args.check_live_pages:
        print("  ! --check-live-pages given but no domain on record for this site "
              "(pass --site-url, or add `live_url`/`staging_url` to site.json)")
    print()

    known: set[str] = set()
    superseded: dict[str, str] = {}
    if args.skip_known_clean:
        known = load_known_clean(Path(args.skip_known_clean))
        if not args.no_skip_superseded:
            superseded = load_superseded(Path(args.skip_known_clean))
    rows: list[dict] = []
    stats = {"examined": 0, "clean": 0, "not_ai": 0, "stripped": 0, "repointed": 0,
             "errors": 0, "bytes": 0, "undetectable": 0, "skipped": 0,
             "unreadable": 0, "superseded": 0, "designer_refs": 0}
    to_publish: dict[str, set[str]] = {}

    for key in sorted(index):
        refs = index[key]
        url = refs[0].source_url if refs and refs[0].source_url else ""
        if not url:
            continue
        name = _strip_id_prefixes(_url_key(url)) or "image"
        if args.pattern and not fnmatch.fnmatch(name, args.pattern):
            continue
        # Both sets are keyed by ASSET ID; `key` is `{id}_{name}`. Comparing them
        # directly made the skip unreachable — see asset_id_from_url_key.
        aid = asset_id_from_url_key(key)
        if aid and aid in known:
            stats["skipped"] += 1
            continue
        if aid and aid in superseded:
            # Same immutability argument as cmd_replace: a successful CMS
            # replace uploads a COPY, so without this the next run replaces the
            # already-replaced image again, every night.
            stats["superseded"] += 1
            continue
        stats["examined"] += 1

        row: dict = {"ts": utc_iso(), "mode": "cms-replace", "site": args.site,
                     "name": name, "old_url": url, "refs": len(refs),
                     "applied": bool(args.apply)}
        try:
            data = download_image(url)
            rep = ip.scan(data)
            if rep.parse_error:
                # cmd_scan already treats this as a coverage failure. The
                # commands that exist to FIX such an asset printed one SKIP
                # line, touched no counter and exited 0 — so the same corrupt,
                # manifest-bearing file reddened the nightly and was silently
                # passed over by every repair run.
                if _is_concerning_parse_error(rep):
                    stats["unreadable"] += 1
                    print(f"  UNKNOWN {name[:52]}  ({rep.parse_error}) — status UNKNOWN, not clean")
                else:
                    print(f"  SKIP    {name[:52]}  (not an image format this tool handles)")
                row["action"] = "skip_unparseable"
                rows.append(row)
                continue
            wants = [s for s in rep.signals if s.removable and policy.wants(s.kind)]
            if args.only_ai and not rep.is_ai_flagged:
                # NOT stats["clean"]: an image skipped for carrying no AI signal
                # may still be carrying camera EXIF. Folding the two together
                # printed "already clean 164" when the truth was "164 had no AI
                # signal, 38 of which are not clean at all".
                stats["not_ai"] += 1
                row["action"] = "skip_not_ai"
                rows.append(row)
                continue
            if not wants:
                stats["clean"] += 1
                row["action"] = "already_clean"
                rows.append(row)
                if args.all:
                    print(f"  CLEAN   {name[:52]}")
                continue
            res = ip.strip(data, policy=policy)
        except (ProvenanceError, APIError, NetworkError, urllib.error.HTTPError,
                urllib.error.URLError, OSError, ValueError) as e:
            stats["errors"] += 1
            print(f"  ERROR   {name[:52]}: {type(e).__name__}: {e}")
            row["action"] = "error"
            row["error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            continue

        kinds = ",".join(sorted({s.kind for s in res.removed}))
        gens = ",".join(res.before.ai_generators)
        wm = res.before.undetectable_watermarks
        if wm:
            stats["undetectable"] += 1
        row.update({"removed_kinds": kinds, "ai_generators": res.before.ai_generators,
                    "bytes_removed": res.bytes_removed, "undetectable_watermarks": wm})
        print(f"  {'STRIP  ' if args.apply else 'WOULD  '} {name[:52]:52} "
              f"-{_fmt_bytes(res.bytes_removed):>9}  [{kinds}]  refs={len(refs)}"
              f"{'  ' + gens if gens else ''}{'  ⚠ pixel watermark' if wm else ''}")

        if not args.apply:
            stats["stripped"] += 1
            stats["bytes"] += res.bytes_removed
            row["action"] = "would_replace"
            rows.append(row)
            continue

        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"{args.site}_{_url_key(url)}").write_bytes(data)
        try:
            up = upload_bytes(res.data, name, site_id, token)
        except (APIError, NetworkError, RuntimeError, ValueError,
                urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            stats["errors"] += 1
            print(f"          ! upload failed: {type(e).__name__}: {e}")
            row.update({"action": "upload_error", "error": f"{type(e).__name__}: {e}"})
            rows.append(row)
            continue

        n_ok = 0
        staged: dict[str, set[str]] = {}
        for ref in refs:
            try:
                out = repoint_reference(token, ref, old_url=url, new_url=up["hostedUrl"],
                                        new_file_id=up["asset_id"], apply=True)
                if out["status"] == "repointed":
                    n_ok += 1
                    # Queue for publish ONLY on success. A careless string patch
                    # once moved this line into the ambiguous branch, so
                    # successful re-points were never published while UNWRITTEN
                    # ones were queued — the precise inverse of correct.
                    if ref.was_published and not ref.is_draft and not ref.is_archived:
                        # Staged, NOT queued. Publishing is the irreversible half
                        # of this command; doing it before the verify decision
                        # pushed bytes live that the very next line reported as
                        # unverifiable. Promoted below, only on success.
                        staged.setdefault(ref.collection_id, set()).add(ref.item_id)
                elif out["status"] == "ref-ambiguous":
                    # The reference could not be resolved to ONE entry. Surfaced,
                    # not guessed — n_ok stays short, which makes the run
                    # incomplete and therefore an error.
                    print(f"          ! AMBIGUOUS ref in {ref.collection_slug}/{ref.item_slug}"
                          f".{ref.field_slug}: {len(out.get('candidates', []))} candidates share "
                          "this filename — not rewritten.")
            except (APIError, NetworkError, urllib.error.HTTPError,
                    urllib.error.URLError, OSError) as e:
                print(f"          ! repoint failed on {ref.collection_slug}/{ref.item_slug}: {e}")

        verify = verify_live(up["hostedUrl"], policy=policy) if args.verify else {}
        incomplete = n_ok < len(refs)
        verify_failed = bool(args.verify) and not verify.get("clean")
        if verify_failed:
            print(f"          ! not queuing {len(staged)} collection(s) for publish — "
                  "the replacement bytes did not verify.")
        else:
            for cid, ids in staged.items():
                to_publish.setdefault(cid, set()).update(ids)
        if incomplete:
            stats["errors"] += 1
            print(f"          ! INCOMPLETE: re-pointed {n_ok}/{len(refs)} — "
                  "the CMS still points at the un-stripped file.")
        if verify_failed:
            stats["errors"] += 1
            print(f"          ! VERIFY FAILED — {verify.get('verdict', 'not clean')}; "
                  "treating this image as NOT done.")
        row["action"] = ("incomplete_repoint" if incomplete
                         else "verify_failed" if verify_failed else "replaced")
        row.update({"new_asset_id": up["asset_id"], "new_url": up["hostedUrl"],
                    "repointed": n_ok, "verify": verify})
        if row["action"] == "replaced":
            # `load_superseded` keys on the ORIGINAL asset id; cmd_cms works
            # from URLs, so recover it here or the row records a supersession
            # nothing can look up.
            row["asset_id"] = asset_id_from_url_key(_url_key(url))
            row["superseded_by"] = up["asset_id"]
        stats["stripped"] += 1
        stats["repointed"] += n_ok
        stats["bytes"] += res.bytes_removed
        print(f"          -> repointed {n_ok}/{len(refs)}  "
              f"[{'verified clean' if verify.get('clean') else ('VERIFY FAILED' if args.verify else 'not verified')}]")

        page_refs, _ = lookup_refs(live_index, url)
        if page_refs:
            stats["designer_refs"] += len(page_refs)
            stats["errors"] += 1
            row["designer_page_refs"] = page_refs[:10]
            print(f"          ! STILL DIRTY on {len(page_refs)} published page(s): "
                  f"{page_refs[0]}")
            print("            Those references are set in the Designer, not the CMS, "
                  "and cannot be rewritten from here — fix them via /webflow-implement.")
        elif args.check_live_pages and not live_known:
            row["designer_refs_unknown"] = True
        rows.append(row)

    if args.apply and args.auto_publish and to_publish:
        print("\n  Publishing touched CMS items…")
        for cid, ids in to_publish.items():
            try:
                publish_items(token, cid, sorted(ids))
                print(f"    published {len(ids)} item(s) in {cid}")
            except (APIError, NetworkError) as e:
                # A publish failure left the CMS holding the correct, stripped
                # reference in DRAFT while the live page kept serving the old
                # one — and the run still exited 0. It is an error like any other.
                stats["errors"] += 1
                print(f"    ! PUBLISH FAILED for {cid}: {e}")
                print(f"      {len(ids)} item(s) were re-pointed but are NOT live; "
                      "the published page still serves the un-stripped image.")

    print(f"\n{'─' * 70}")
    print(f"  examined {stats['examined']}   carried no removable metadata {stats['clean']}   "
          f"{'replaced' if args.apply else 'would replace'} {stats['stripped']}")
    if stats["not_ai"]:
        print(f"  skipped by --only-ai (no AI signal) {stats['not_ai']}"
              "   <- NOT a statement that they are metadata-clean")
    print(f"  references re-pointed {stats['repointed']}")
    if stats["skipped"]:
        print(f"  skipped (known clean)  {stats['skipped']}")
    if stats["superseded"]:
        print(f"  skipped (already replaced) {stats['superseded']}"
              "   <- orphans; `purge` removes them")
    if stats["unreadable"]:
        print(f"  UNREADABLE             {stats['unreadable']}   <- status UNKNOWN, NOT clean")
    if stats["errors"]:
        print(f"  errors                 {stats['errors']}")
    print(f"  bytes removed          {_fmt_bytes(stats['bytes'])}")
    if stats["designer_refs"]:
        print(f"\n  {stats['designer_refs']} Designer-set reference(s) still point at un-stripped")
        print("  images. The CMS half is done; those are set on the page itself and")
        print("  need /webflow-implement. This run is NOT complete.")
    elif not live_known:
        # Key on whether the crawl PRODUCED COVERAGE, never on whether the flag
        # was passed. `--check-live-pages` with no site URL, or a crawl that
        # failed halfway, both leave live_index empty — and keying on the flag
        # made those runs print nothing at all, which reads as "checked, found
        # none". Caught on the first live brightvalley run after this was added.
        why = ("no domain is on record — pass --site-url, or add `live_url` or "
               "`staging_url` to site.json" if not site_url else
               "the published-page crawl did not complete")
        print(f"\n  Published pages were NOT fully checked ({why}).")
        print("  An image placed on a page in the Designer keeps serving the original,")
        print("  so this run cannot claim the site is done.")
    if stats["undetectable"]:
        print(f"\n  {stats['undetectable']} image(s) declare a pixel watermark. That is in the pixels,")
        print("  not the metadata. It is NOT removed. Do not call these watermark-free.")
    if not args.apply and stats["stripped"]:
        print("\n  This was a dry run. Get explicit approval, then re-run with --apply.")
    print(f"{'─' * 70}\n")
    if args.apply or args.log_jsonl:
        # A dry run must not append to the DEFAULT log: load_known_clean() reads
        # that file, so a preview could seed the known-clean cache and cause a
        # later real run to skip an asset it never actually processed. An
        # explicit --log-jsonl is the caller asking for the write, so honour it.
        append_jsonl(log_path, rows)
    return 0 if (stats["errors"] == 0 and stats["unreadable"] == 0) else 2


def verdict(data: bytes, *, policy: Policy | None = None) -> tuple[str, ip.Report, list]:
    """Three-way verdict on a blob: CLEAN / DIRTY / UNKNOWN.

    ``clean`` is a CONJUNCTION, not merely "the structural scan found nothing":

      1. the container parsed  — an unparseable file is UNKNOWN, never clean;
      2. no removable signal survived;
      3. the byte-level backstop finds no provenance string either.

    Condition 1 is the one that mattered. Corrupting a single chunk header on a
    C2PA-bearing PNG makes the structural walk abort with zero signals, and
    "zero signals" was being reported as CLEAN — on a file whose bytes still
    contained a signed manifest and 44 matching provenance strings. ``verify``
    is the command whose entire purpose is answering "is this clean?", so it is
    the last place that may guess.

    ``policy`` asks a DIFFERENT question. Without it the question is "is this
    file free of all removable provenance?" — right for ``verify`` on an
    arbitrary file. With it the question is "did this policy's intent get
    achieved?" — right for the post-write check inside ``replace``/``cms``,
    where ``--keep-exif`` means the surviving EXIF is the *requested* outcome.
    Being policy-blind there turned a fully correct run all-red: every upload
    verified DIRTY, counted as verify_failed, and the run exited 2.
    """
    rep = ip.scan(data)
    # High-confidence needles only. The 4-byte ones ("c2pa", "jumb") are right
    # for a post-strip assertion, where a false positive costs a re-check — but
    # as evidence about an arbitrary file they fire on compressed pixel data,
    # and here that becomes verify_failed -> exit 2 -> reprocessed forever.
    residue = ip.raw_residue(data, high_confidence_only=True)
    if policy is not None:
        residue = [r for r in residue if policy.wants(r[0])]
    if rep.parse_error:
        return "UNKNOWN", rep, residue
    live = [s for s in rep.signals
            if s.removable and (policy is None or policy.wants(s.kind))]
    if live or residue:
        # DIRTY means "carries removable metadata", which is NOT the same as
        # "is AI-generated" — a scanned photograph with 204 bytes of camera EXIF
        # is DIRTY and not AI. Saying which avoids the reader collapsing the two.
        #
        # An AI marker found only by the byte backstop still counts: is_ai_flagged
        # reads structural signals, so a `trainedAlgorithmicMedia` string sitting
        # outside any declared record produced a bare "DIRTY" and read as ordinary
        # camera metadata.
        ai_residue = any(kind == "iptc_ai" for kind, _needle, _at in residue)
        return ("DIRTY-AI" if (rep.is_ai_flagged or ai_residue) else "DIRTY"), rep, residue
    return "CLEAN", rep, residue


def cmd_verify(args: argparse.Namespace) -> int:
    results = []
    for url in args.url or []:
        r = verify_live(url, tries=1)
        results.append(r)
        print(f"  {r.get('verdict', 'UNKNOWN')}  {url}")
        for s in r.get("signals", []):
            print(f"          - {s['kind']:<20} {s['where']:<22} {s['detail'][:60]}")
        for w in r.get("undetectable_watermarks", []):
            print(f"          X NOT REMOVABLE: {w}")
        if r.get("parse_error"):
            print(f"          ! could not parse: {r['parse_error']}")
        if r.get("residue"):
            print(f"          ! raw residue: {[x[1] for x in r['residue'][:4]]}")
        if r.get("error"):
            print(f"          ! {r['error']}")
    for path in args.file or []:
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError as e:
            print(f"  UNKNOWN  {p}  ! {e}")
            results.append({"path": str(p), "verdict": "UNKNOWN", "error": str(e)})
            continue
        v, rep, residue = verdict(data)
        results.append({"path": str(p), "verdict": v, "clean": v == "CLEAN",
                        "residue": residue[:5], **rep.as_dict()})
        print(f"  {v}  {p}")
        if rep.parse_error:
            print(f"          ! could not parse: {rep.parse_error}")
            print("          ! UNKNOWN is not CLEAN — the structure could not be read, so"
                  " a manifest may still be present.")
        if residue:
            print(f"          ! raw residue: {[x[1] for x in residue[:4]]}")
        _print_report(str(p), rep, verbose=True)
    if args.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    # UNKNOWN must not exit 0: a caller scripting this needs "could not tell"
    # to be as loud as "found something".
    if any(str(r.get("verdict", "")).startswith("DIRTY") for r in results):
        return 1
    if any(r.get("verdict") != "CLEAN" for r in results):
        return 2
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="watermark_cleaner.py",
        description="Scan and losslessly strip AI-provenance metadata, locally and on Webflow.",
        epilog="Removes METADATA (C2PA/IPTC/XMP/EXIF). Does NOT remove pixel watermarks "
               "such as SynthID — see `scan` output under 'NOT REMOVABLE'.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--keep-c2pa", action="store_true", help="leave C2PA manifests in place")
        sp.add_argument("--keep-exif", action="store_true", help="leave the EXIF IFD in place")
        sp.add_argument("--strip-icc", action="store_true",
                        help="also drop the ICC colour profile (default: keep — dropping shifts colour)")
        sp.add_argument("--drop-orientation", action="store_true",
                        help="do not re-emit EXIF Orientation (default: keep — dropping rotates photos)")
        sp.add_argument("--log-jsonl", default="", help="append structured results here")
        sp.add_argument("--verbose", "-v", action="store_true", help="list every signal")
        sp.add_argument("--all", action="store_true", help="also report images that are already clean")
        sp.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    sc = sub.add_parser("scan", help="inventory provenance signals")
    sc.add_argument("--local", nargs="*", default=[], help="files, dirs or globs")
    sc.add_argument("--site", help="site nickname — scan its Webflow assets")
    sc.add_argument("--pattern", default="", help="fnmatch filter on asset filename")
    sc.add_argument("--limit", type=int, default=0, help="stop after N assets")
    sc.add_argument("--token", default=None, help="Webflow API token override")
    sc.add_argument("--skip-known-clean", default="",
                    help="a prior --log-jsonl file; assets it proved clean are not re-fetched")
    sc.add_argument("--fail-on-flagged", action="store_true",
                    help="exit 1 when any AI-provenance signal is found (for CI gating)")
    sc.add_argument("--summary-out", default="",
                    help="write a machine-readable JSON summary here")
    sc.add_argument("--markdown-out", default="",
                    help="write a markdown summary here (append to $GITHUB_STEP_SUMMARY)")
    common(sc)
    sc.set_defaults(func=cmd_scan)

    cl = sub.add_parser("clean", help="strip local image files")
    cl.add_argument("--local", nargs="+", required=True, help="files, dirs or globs")
    cl.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    cl.add_argument("--out", default="", help="write cleaned files here instead of in place")
    cl.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR),
                    help="copy originals here before overwriting")
    common(cl)
    cl.set_defaults(func=cmd_clean)

    rp = sub.add_parser("replace", help="strip images on Webflow and re-point CMS references")
    rp.add_argument("--site", required=True, help="site nickname")
    rp.add_argument("--apply", action="store_true",
                    help="perform the writes — REQUIRES explicit user approval first")
    rp.add_argument("--asset-id", default="", help="comma-separated asset ids to limit to")
    rp.add_argument("--pattern", default="", help="fnmatch filter on asset filename")
    rp.add_argument("--collections", default="all",
                    help="'all', or comma-separated collection slugs/IDs, to scope the reference index")
    rp.add_argument("--only-referenced", action="store_true",
                    help="process ONLY assets referenced by --collections (not the whole site)")
    rp.add_argument("--limit", type=int, default=0, help="stop after N assets")
    rp.add_argument("--allow-new-asset-id", action="store_true",
                    help="proceed even when the re-upload mints a new asset id (URL changes)")
    rp.add_argument("--check-live-pages", action="store_true", default=True,
                    help="index the published site to find Designer-placed references (default on)")
    rp.add_argument("--no-check-live-pages", dest="check_live_pages", action="store_false")
    rp.add_argument("--site-url", default="", help="published site URL (defaults to site.json live_url)")
    rp.add_argument("--live-page-limit", type=int, default=0, help="stop after N published pages")
    rp.add_argument("--auto-publish", action="store_true",
                    help="publish CMS items that were already published before the edit")
    rp.add_argument("--verify", action="store_true", default=True,
                    help="re-fetch each replaced URL and confirm it is clean (default on)")
    rp.add_argument("--no-verify", dest="verify", action="store_false")
    rp.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    rp.add_argument("--quiet", action="store_true", help="suppress per-collection index progress")
    rp.add_argument("--token", default=None, help="Webflow API token override")
    rp.add_argument("--skip-known-clean", default="",
                    help="a prior --log-jsonl file; assets it proved clean are not re-fetched")
    rp.add_argument("--no-skip-superseded", action="store_true",
                    help="also re-process assets a prior run already replaced. Off by "
                         "default: a Webflow asset is immutable, so replacing one twice "
                         "just leaves two orphans. Use `purge` to remove the originals.")
    common(rp)
    rp.set_defaults(func=cmd_replace)

    pg = sub.add_parser("purge",
                        help="delete AI-flagged assets that nothing references (irreversible)")
    pg.add_argument("--site", required=True)
    pg.add_argument("--apply", action="store_true", help="actually delete — IRREVERSIBLE")
    pg.add_argument("--asset-id", default="", help="comma-separated asset ids to limit to")
    pg.add_argument("--limit", type=int, default=0)
    pg.add_argument("--check-live-pages", action="store_true", default=True)
    pg.add_argument("--no-check-live-pages", dest="check_live_pages", action="store_false")
    pg.add_argument("--site-url", default="",
                    help="the domain whose pages count as evidence (defaults to the site's production host)")
    pg.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    pg.add_argument("--quiet", action="store_true")
    pg.add_argument("--token", default=None)
    common(pg)
    pg.set_defaults(func=cmd_purge)

    ln = sub.add_parser("lineage",
                        help="identify remote assets that are derivatives of known AI-generated sources")
    ln.add_argument("--site", required=True)
    ln.add_argument("--source", nargs="*", default=[],
                    help="local dirs holding AI-marked originals "
                         "(default: sites/<site> + data/watermark-backup/sites/<site> "
                         "+ data/watermark-backup, where replace/cms write flat)")
    ln.add_argument("--pattern", default="", help="fnmatch filter on asset filename")
    ln.add_argument("--limit", type=int, default=0)
    ln.add_argument("--quiet", action="store_true")
    ln.add_argument("--token", default=None)
    common(ln)
    ln.set_defaults(func=cmd_lineage)

    cm = sub.add_parser("cms", help="walk CMS image references directly (reaches CMS-uploaded images)")
    cm.add_argument("--site", required=True)
    cm.add_argument("--apply", action="store_true",
                    help="perform the writes — REQUIRES explicit user approval first")
    cm.add_argument("--collections", default="all", help="'all' or comma-separated collection slugs/IDs")
    cm.add_argument("--pattern", default="", help="fnmatch filter on the image filename")
    cm.add_argument("--only-ai", action="store_true",
                    help="only touch images carrying an AI-generation signal (C2PA/IPTC/AI generator tag)")
    cm.add_argument("--auto-publish", action="store_true",
                    help="publish CMS items that were already published before the edit")
    cm.add_argument("--verify", action="store_true", default=True)
    cm.add_argument("--no-verify", dest="verify", action="store_false")
    cm.add_argument("--check-live-pages", action="store_true", default=True,
                    help="index the published site to find Designer-placed references "
                         "this command cannot rewrite (default on)")
    cm.add_argument("--no-check-live-pages", dest="check_live_pages", action="store_false")
    cm.add_argument("--site-url", default="", help="published site URL (defaults to site.json live_url)")
    cm.add_argument("--live-page-limit", type=int, default=0, help="stop after N published pages")
    cm.add_argument("--skip-known-clean", default="",
                    help="a prior --log-jsonl file; images it proved clean are not re-fetched")
    cm.add_argument("--no-skip-superseded", action="store_true",
                    help="also re-process images a prior run already replaced")
    cm.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    cm.add_argument("--quiet", action="store_true")
    cm.add_argument("--token", default=None)
    common(cm)
    cm.set_defaults(func=cmd_cms)

    vf = sub.add_parser("verify", help="report what a crawler would see at a URL or path")
    vf.add_argument("--url", action="append", default=[], help="live URL (repeatable)")
    vf.add_argument("--file", action="append", default=[], help="local path (repeatable)")
    vf.add_argument("--json", action="store_true")
    vf.set_defaults(func=cmd_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan" and not args.local and not args.site:
        print("scan needs --local and/or --site", file=sys.stderr)
        return 2
    if args.command in ("replace", "cms", "purge") and getattr(args, "apply", False) \
            and os.environ.get("WATERMARK_CLEANER_CONFIRM") != "1":
        # A second, deliberate gate on top of the repo's deploy-gate hook: an
        # --apply typed by muscle memory should not reach Webflow.
        print("\n  refusing --apply without WATERMARK_CLEANER_CONFIRM=1 in the environment.")
        print("  This writes to a live Webflow site. Show the dry run, get approval, then:")
        print(f"      WATERMARK_CLEANER_CONFIRM=1 python3 scripts/watermark_cleaner.py "
              f"{args.command} --site {args.site} --apply\n", file=sys.stderr)
        return 3
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
