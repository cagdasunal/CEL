"""Static landing page #summary element reader/writer (via Webflow Designer API).

Different paradigm than the Data API: pages have an element tree, not a flat
record. Elements are addressed by ID within a page. We need to find the
element with `id="summary"` (or DOM-id attr) on each static page.

The Designer API endpoint shape is documented at:
https://developers.webflow.com/v2.0.0/data/reference/pages-and-collections/designer-engine

This module exposes:
  find_summary_element(page_id) -> ElementRef | None
  write_summary_element(page_id, ref, html, dry_run) -> WriteResult

If the element doesn't exist, find_summary_element returns None and the CLI
surfaces the page as a "missing element" warning. The script does NOT auto-create.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.summary import config
from tools.summary.webflow_client import WebflowApiError, WriteResult


@dataclass(frozen=True)
class ElementRef:
    page_id: str
    element_id: str
    dom_id: str  # the HTML id="..." attribute, e.g. "summary"


class WebflowDesignerClient:
    """Webflow Designer Engine API client. Construct with dry_run=True for safety."""

    def __init__(self, dry_run: bool = True, token_env: str = "WEBFLOW_API_TOKEN") -> None:
        self.dry_run = dry_run
        self._token_env = token_env
        self._token: Optional[str] = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        token = os.environ.get(self._token_env, "").strip()
        if not token:
            raise RuntimeError(
                f"Environment variable {self._token_env} is not set. "
                "Required for live Webflow Designer API calls."
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

    # ---- Page lookup ----

    def find_page_id_by_url(self, page_url: str) -> Optional[str]:
        """Best-effort match: list site pages, find one whose publishedPath matches.

        Returns None if no match. Caller should fall back to a static map of
        URL → page_id baked into config.STATIC_PAGE_IDS (TODO: populate after
        first live read).
        """
        parsed = urllib.parse.urlparse(page_url)
        path = parsed.path.rstrip("/") or "/"
        url = f"{config.WEBFLOW_API_BASE}/sites/{config.WEBFLOW_SITE_ID}/pages"
        data = self._request("GET", url, headers=self._headers(content_type_json=False))
        for p in data.get("pages", []):
            pub = (p.get("publishedPath") or p.get("slug") or "").rstrip("/") or "/"
            if pub == path:
                return p.get("id")
        return None

    def find_summary_element(self, page_id: str) -> Optional[ElementRef]:
        """Find the element with `id="summary"` (or `data-summary-target`) on the page.

        Returns None if not found.
        """
        url = (
            f"{config.WEBFLOW_API_BASE}/pages/{page_id}/dom"
        )
        try:
            data = self._request("GET", url, headers=self._headers(content_type_json=False))
        except WebflowApiError:
            # Endpoint may not exist on all sites or may require Designer auth — surface as "not found"
            return None
        # Walk nodes/elements looking for `id="summary"`.
        elements = data.get("nodes", []) or data.get("elements", [])
        for el in _walk_elements(elements):
            attrs = el.get("attributes", {}) or {}
            if attrs.get("id") == config.STATIC_PAGE_SUMMARY_ELEMENT_ID:
                return ElementRef(
                    page_id=page_id,
                    element_id=el.get("id", "") or el.get("nodeId", ""),
                    dom_id=config.STATIC_PAGE_SUMMARY_ELEMENT_ID,
                )
        return None

    def write_summary_element(
        self,
        ref: ElementRef,
        summary_html: str,
    ) -> WriteResult:
        """Write rich-text HTML to the #summary element on a static page.

        Dry-run safe. The exact endpoint shape depends on the Webflow Designer API
        version; this is the safe form: PATCH /pages/{page_id}/elements/{element_id}.
        """
        url = (
            f"{config.WEBFLOW_API_BASE}/pages/{ref.page_id}/elements/{ref.element_id}"
        )
        payload = {
            "richText": summary_html,
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


def _walk_elements(items: list[dict[str, Any]]):
    """Recursive generator over an element tree."""
    for el in items:
        yield el
        children = el.get("children") or el.get("nodes") or []
        if children:
            yield from _walk_elements(children)
