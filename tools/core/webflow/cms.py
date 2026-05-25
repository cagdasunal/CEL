"""Webflow Data API v2 CMS client (shared, leaf).

Generic reads + a generic STAGED field PATCH (`patch_fields`) + field-ensure, all
dry-run safe. Tools (the summary adapter, copywriter, future) build on this instead
of reimplementing Webflow writes. Plan B. See docs/ARCHITECTURE.md.

create_item / bulk_create / publish_items are intentionally NOT here yet — no current
caller needs them (Script Creation Gate). Add when a tool does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from tools.core.webflow.http import (
    WEBFLOW_API_BASE,
    WebflowApiError,
    request as _http_request,
    resolve_token,
)


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


class CmsClient:
    """Webflow Data API v2 client. Construct with `dry_run=True` for safety."""

    def __init__(self, dry_run: bool = True, token_env: str = "WEBFLOW_API_TOKEN") -> None:
        self.dry_run = dry_run
        self._token_env = token_env
        # Token fetched lazily so dry-run doesn't require the secret to be set.
        self._token: Optional[str] = None

    # ---- Auth ----

    def _get_token(self) -> str:
        if self._token:
            return self._token
        self._token = resolve_token(self._token_env)
        return self._token

    def _headers(self, content_type_json: bool = True) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "User-Agent": "cel-summary-script/1.0",
        }
        if content_type_json:
            h["Content-Type"] = "application/json"
        return h

    def _request(self, method, url, headers, payload=None, timeout=30.0, max_attempts=3):
        return _http_request(method, url, headers, payload=payload, timeout=timeout, max_attempts=max_attempts)

    # ---- Reads (always real) ----

    def get_collection_details(self, collection_id: str) -> dict[str, Any]:
        url = f"{WEBFLOW_API_BASE}/collections/{collection_id}"
        return self._request("GET", url, headers=self._headers(content_type_json=False))

    def list_collection_fields(self, collection_id: str) -> list[CollectionField]:
        data = self.get_collection_details(collection_id)
        out: list[CollectionField] = []
        for f in data.get("fields", []):
            out.append(CollectionField(
                slug=f.get("slug", ""), display_name=f.get("displayName", ""),
                type=f.get("type", ""), id=f.get("id"), required=bool(f.get("isRequired", False)),
            ))
        return out

    def find_field(
        self, collection_id: str, slug: str, types: tuple[str, ...] = ("RichText", "PlainText")
    ) -> Optional[CollectionField]:
        """Return the field with this slug + an allowed type, or None."""
        for f in self.list_collection_fields(collection_id):
            if f.slug == slug and f.type in types:
                return f
        return None

    def list_items(self, collection_id: str, page_size: int = 100) -> Iterator[CmsItem]:
        """Yield all items in a collection (paginated via pagination.total, with a
        len(items) < page_size fallback for older responses)."""
        offset = 0
        while True:
            url = (
                f"{WEBFLOW_API_BASE}/collections/{collection_id}/items"
                f"?limit={page_size}&offset={offset}"
            )
            data = self._request("GET", url, headers=self._headers(content_type_json=False))
            items = data.get("items", [])
            for raw in items:
                yield CmsItem(
                    id=raw.get("id", ""), collection_id=collection_id,
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
                if len(items) < page_size:
                    break

    # ---- Writes (dry-run safe) ----

    def patch_fields(self, collection_id: str, item_id: str, field_data: dict[str, Any]) -> WriteResult:
        """Generic STAGED field PATCH (/items/{id} — no /live, succeeds on drafts). The
        reusable write primitive; the caller publishes via Webflow Designer."""
        url = f"{WEBFLOW_API_BASE}/collections/{collection_id}/items/{item_id}"
        payload = {"fieldData": field_data}
        if self.dry_run:
            return WriteResult(
                dry_run=True, success=True, method="PATCH", url=url, payload=payload,
                response={"_dry_run": True, "would_patch": payload},
            )
        try:
            response = self._request("PATCH", url, headers=self._headers(), payload=payload)
            return WriteResult(dry_run=False, success=True, method="PATCH", url=url, payload=payload, response=response)
        except WebflowApiError as e:
            return WriteResult(dry_run=False, success=False, method="PATCH", url=url, payload=payload, error=str(e))

    def ensure_field(self, collection_id: str, *, slug: str, display_name: str, type: str = "RichText") -> dict[str, Any]:
        """Verify a field exists on the collection; create it if missing. Dry-run safe.
        Returns {existed, created, field, dry_run[, _would_create]}."""
        existing = self.find_field(collection_id, slug)
        if existing:
            return {"existed": True, "created": False, "field": existing, "dry_run": self.dry_run}
        if self.dry_run:
            return {
                "existed": False, "created": False, "field": None, "dry_run": True,
                "_would_create": {"displayName": display_name, "slug": slug, "type": type},
            }
        url = f"{WEBFLOW_API_BASE}/collections/{collection_id}/fields"
        payload = {"displayName": display_name, "slug": slug, "type": type, "isRequired": False}
        response = self._request("POST", url, headers=self._headers(), payload=payload)
        return {
            "existed": False, "created": True,
            "field": CollectionField(
                slug=response.get("slug", slug), display_name=response.get("displayName", display_name),
                type=response.get("type", type), id=response.get("id"),
            ),
            "dry_run": False,
        }
