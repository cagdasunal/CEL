"""Thin Webflow Data API v2 wrapper for the summary script.

Dry-run safety baked in: every write method accepts `dry_run: bool` and returns
a mock response without firing an HTTP request when True. Reads are real
either way (they don't mutate state).

Uses stdlib `urllib.request` — no `requests` dependency. Auth via
`os.environ["WEBFLOW_API_TOKEN"]`.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from tools.summary import config


# ---- Errors ----


class WebflowApiError(RuntimeError):
    """Raised on HTTP error from the Webflow API."""


# ---- Data types ----


@dataclass(frozen=True)
class CmsItem:
    id: str
    collection_id: str
    field_data: dict[str, Any]
    is_archived: bool = False
    is_draft: bool = False


@dataclass(frozen=True)
class CollectionField:
    slug: str
    display_name: str
    type: str  # e.g. "RichText", "PlainText", "Image"
    id: Optional[str] = None
    required: bool = False


@dataclass
class WriteResult:
    """Result of a write operation (real or dry-run)."""

    dry_run: bool
    success: bool
    method: str
    url: str
    payload: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ---- Client ----


class WebflowClient:
    """Webflow Data API v2 client. Construct with `dry_run=True` for safety."""

    def __init__(self, dry_run: bool = True, token_env: str = "WEBFLOW_API_TOKEN") -> None:
        self.dry_run = dry_run
        self._token_env = token_env
        # Token is fetched lazily so dry-run doesn't require the secret to be set.
        self._token: Optional[str] = None

    # ---- Authentication ----

    def _get_token(self) -> str:
        if self._token:
            return self._token
        token = os.environ.get(self._token_env, "").strip()
        if not token:
            raise RuntimeError(
                f"Environment variable {self._token_env} is not set or empty. "
                f"Required for live Webflow API calls."
            )
        self._token = token
        return token

    def _headers(self, content_type_json: bool = True) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "User-Agent": "cel-summary-script/1.0",
        }
        if content_type_json:
            h["Content-Type"] = "application/json"
        return h

    # ---- Read methods (always real) ----

    def get_collection_details(self, collection_id: str) -> dict[str, Any]:
        """Fetch the live collection schema (fields list)."""
        url = f"{config.WEBFLOW_API_BASE}/collections/{collection_id}"
        return self._request("GET", url, headers=self._headers(content_type_json=False))

    def list_collection_fields(self, collection_id: str) -> list[CollectionField]:
        """Return the collection's fields as typed objects."""
        data = self.get_collection_details(collection_id)
        out: list[CollectionField] = []
        for f in data.get("fields", []):
            out.append(
                CollectionField(
                    slug=f.get("slug", ""),
                    display_name=f.get("displayName", ""),
                    type=f.get("type", ""),
                    id=f.get("id"),
                    required=bool(f.get("isRequired", False)),
                )
            )
        return out

    def find_summary_field(self, collection_id: str) -> Optional[CollectionField]:
        """Return the Summary rich-text field if it exists on this collection."""
        for f in self.list_collection_fields(collection_id):
            if f.slug == config.SUMMARY_FIELD_SLUG and f.type in ("RichText", "PlainText"):
                return f
        return None

    def list_items(
        self, collection_id: str, page_size: int = 100
    ) -> Iterator[CmsItem]:
        """Yield all items in a collection (paginated).

        Uses Webflow v2 pagination metadata (`pagination.total`) when present;
        falls back to the `len(items) < page_size` terminator for older responses.
        """
        offset = 0
        while True:
            url = (
                f"{config.WEBFLOW_API_BASE}/collections/{collection_id}/items"
                f"?limit={page_size}&offset={offset}"
            )
            data = self._request("GET", url, headers=self._headers(content_type_json=False))
            items = data.get("items", [])
            for raw in items:
                yield CmsItem(
                    id=raw.get("id", ""),
                    collection_id=collection_id,
                    field_data=raw.get("fieldData", {}),
                    is_archived=bool(raw.get("isArchived", False)),
                    is_draft=bool(raw.get("isDraft", False)),
                )
            pagination = data.get("pagination") or {}
            total = pagination.get("total")
            offset += page_size
            if total is not None:
                if offset >= total:
                    break
            else:
                # Fallback: older API responses without pagination metadata.
                if len(items) < page_size:
                    break

    # ---- Write methods (dry-run safe) ----

    def update_item_summary(
        self,
        collection_id: str,
        item_id: str,
        summary_html: str,
    ) -> WriteResult:
        """Patch the Summary field on a CMS item via the STAGED endpoint. Dry-run safe.

        Writes to `/items/{id}` (no `/live` suffix) so the call succeeds on draft items.
        The user publishes the Webflow site to push staged changes live. Per
        rules/workflow.md §7.1, Claude never publishes. This matches the pattern
        used by tools/fidelo/cms_writer.py + cms_writer_courses.py in the monorepo.
        """
        url = (
            f"{config.WEBFLOW_API_BASE}/collections/{collection_id}/items/{item_id}"
        )
        payload = {
            "fieldData": {
                config.SUMMARY_FIELD_SLUG: summary_html,
            }
        }
        if self.dry_run:
            return WriteResult(
                dry_run=True,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response={"_dry_run": True, "would_patch": payload},
            )
        try:
            response = self._request(
                "PATCH",
                url,
                headers=self._headers(),
                payload=payload,
            )
            return WriteResult(
                dry_run=False,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response=response,
            )
        except WebflowApiError as e:
            return WriteResult(
                dry_run=False,
                success=False,
                method="PATCH",
                url=url,
                payload=payload,
                error=str(e),
            )

    def update_item_summary_parts(
        self,
        collection_id: str,
        item_id: str,
        tagline: str,
        title: str,
        paragraph: str,
        content_html: str,
    ) -> WriteResult:
        """Patch all four Summary fields on a CMS item (tracker-096). Dry-run safe.

        tracker-098: NO LONGER the 4-part write path — `update_item_summary_body` is,
        because it preserves the author-owned Tagline + Title (this method overwrites
        them). Retained for back-compat + tests. Writes Tagline / Title / Paragraph(s)
        + the RichText Content on the Courses/Housing collections via the same STAGED
        `/items/{id}` endpoint as `update_item_summary`. The Content part reuses the
        `summary` slug; the other parts use the `summary---*` triple-hyphen slugs (the
        Paragraphs slug is now RichText). Claude never publishes (rules/workflow.md §7.1).
        """
        url = f"{config.WEBFLOW_API_BASE}/collections/{collection_id}/items/{item_id}"
        payload = {
            "fieldData": {
                config.SUMMARY_TAGLINE_FIELD_SLUG: tagline,
                config.SUMMARY_TITLE_FIELD_SLUG: title,
                config.SUMMARY_PARAGRAPH_FIELD_SLUG: paragraph,
                config.SUMMARY_CONTENT_FIELD_SLUG: content_html,
            }
        }
        if self.dry_run:
            return WriteResult(
                dry_run=True,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response={"_dry_run": True, "would_patch": payload},
            )
        try:
            response = self._request(
                "PATCH",
                url,
                headers=self._headers(),
                payload=payload,
            )
            return WriteResult(
                dry_run=False,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response=response,
            )
        except WebflowApiError as e:
            return WriteResult(
                dry_run=False,
                success=False,
                method="PATCH",
                url=url,
                payload=payload,
                error=str(e),
            )

    def update_item_summary_body(
        self,
        collection_id: str,
        item_id: str,
        paragraph_html: str,
        content_html: str,
    ) -> WriteResult:
        """Patch ONLY the Paragraphs + Content RichText fields on a CMS item (tracker-098).

        The model still emits the full 4-part document, but the Tagline and Title are
        author-owned section furniture — regenerating them on every run would clobber
        hand-tuned headings. So the 4-part write path now PATCHes only the two RichText
        bodies: `summary---paragraphs` (the 1-2 lead paragraphs, as HTML) and `summary`
        (the Content, as HTML). Both carry HTML (not Markdown) so links/headings render
        rather than showing literal `##`/`[](url)`. Same STAGED `/items/{id}` endpoint
        as the other writers; Claude never publishes (rules/workflow.md §7.1). Dry-run
        safe. `update_item_summary_parts` is retained for back-compat/tests but is no
        longer the 4-part write path.
        """
        url = f"{config.WEBFLOW_API_BASE}/collections/{collection_id}/items/{item_id}"
        payload = {
            "fieldData": {
                config.SUMMARY_PARAGRAPH_FIELD_SLUG: paragraph_html,
                config.SUMMARY_CONTENT_FIELD_SLUG: content_html,
            }
        }
        if self.dry_run:
            return WriteResult(
                dry_run=True,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response={"_dry_run": True, "would_patch": payload},
            )
        try:
            response = self._request(
                "PATCH",
                url,
                headers=self._headers(),
                payload=payload,
            )
            return WriteResult(
                dry_run=False,
                success=True,
                method="PATCH",
                url=url,
                payload=payload,
                response=response,
            )
        except WebflowApiError as e:
            return WriteResult(
                dry_run=False,
                success=False,
                method="PATCH",
                url=url,
                payload=payload,
                error=str(e),
            )

    def ensure_summary_field(self, collection_id: str) -> dict[str, Any]:
        """Verify the Summary rich-text field exists on the collection; create if missing.

        Returns {"existed": bool, "created": bool, "field": CollectionField | None,
        "dry_run": bool}.
        """
        existing = self.find_summary_field(collection_id)
        if existing:
            return {
                "existed": True,
                "created": False,
                "field": existing,
                "dry_run": self.dry_run,
            }
        if self.dry_run:
            return {
                "existed": False,
                "created": False,
                "field": None,
                "dry_run": True,
                "_would_create": {
                    "displayName": config.SUMMARY_FIELD_DISPLAY_NAME,
                    "slug": config.SUMMARY_FIELD_SLUG,
                    "type": "RichText",
                },
            }
        url = f"{config.WEBFLOW_API_BASE}/collections/{collection_id}/fields"
        payload = {
            "displayName": config.SUMMARY_FIELD_DISPLAY_NAME,
            "slug": config.SUMMARY_FIELD_SLUG,
            "type": "RichText",
            "isRequired": False,
        }
        response = self._request("POST", url, headers=self._headers(), payload=payload)
        return {
            "existed": False,
            "created": True,
            "field": CollectionField(
                slug=response.get("slug", config.SUMMARY_FIELD_SLUG),
                display_name=response.get("displayName", config.SUMMARY_FIELD_DISPLAY_NAME),
                type=response.get("type", "RichText"),
                id=response.get("id"),
            ),
            "dry_run": False,
        }

    # ---- HTTP plumbing ----

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: Optional[dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise WebflowApiError(f"HTTP {e.code} {method} {url}: {body[:500]}") from e
        except urllib.error.URLError as e:
            raise WebflowApiError(f"Network error {method} {url}: {e.reason}") from e
