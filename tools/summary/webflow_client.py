"""Adapter — Webflow client for the summary tool over tools.core.webflow.CmsClient (Plan B).

The generic HTTP/CMS plumbing (auth, retry, reads, the generic field PATCH, ensure_field)
moved to tools.core.webflow. This WebflowClient keeps the summary-specific Summary-field
writers (update_item_summary[_parts|_body], ensure_summary_field, find_summary_field) as
thin wrappers over the inherited generic methods + the config.SUMMARY_*_FIELD_SLUG values.

`import time` / `urllib.request` are retained so the retry tests can still
`mock.patch.object(webflow_client.urllib.request, "urlopen", ...)` /
`mock.patch.object(webflow_client.time, "sleep", ...)` — those patch the GLOBAL stdlib
modules the core request loop uses. WriteResult/CmsItem/CollectionField/WebflowApiError
are re-exported from core (single source). See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import time  # noqa: F401 — retained so retry tests can patch webflow_client.time.sleep
import urllib.error  # noqa: F401
import urllib.request  # noqa: F401 — retained so retry tests can patch webflow_client.urllib.request.urlopen
from typing import Optional

from tools.summary import config
from tools.core.webflow.cms import CmsClient, CmsItem, CollectionField, WriteResult  # noqa: F401
from tools.core.webflow.http import WebflowApiError  # noqa: F401


class WebflowClient(CmsClient):
    """Webflow Data API client for the summary tool — Summary-field writers over the
    shared core CmsClient. Construct with `dry_run=True` for safety."""

    def find_summary_field(self, collection_id: str) -> Optional[CollectionField]:
        """Return the Summary rich-text/plain field if it exists on this collection."""
        return self.find_field(collection_id, config.SUMMARY_FIELD_SLUG, types=("RichText", "PlainText"))

    def update_item_summary(self, collection_id: str, item_id: str, summary_html: str) -> WriteResult:
        """Patch the single Summary field (blog single-block). Staged; dry-run safe."""
        return self.patch_fields(collection_id, item_id, {config.SUMMARY_FIELD_SLUG: summary_html})

    def update_item_summary_parts(
        self, collection_id: str, item_id: str, tagline: str, title: str, paragraph: str, content_html: str
    ) -> WriteResult:
        """Patch all four Summary fields (tracker-096; back-compat). Staged; dry-run safe."""
        return self.patch_fields(collection_id, item_id, {
            config.SUMMARY_TAGLINE_FIELD_SLUG: tagline,
            config.SUMMARY_TITLE_FIELD_SLUG: title,
            config.SUMMARY_PARAGRAPH_FIELD_SLUG: paragraph,
            config.SUMMARY_CONTENT_FIELD_SLUG: content_html,
        })

    def update_item_summary_body(
        self, collection_id: str, item_id: str, paragraph_html: str, content_html: str
    ) -> WriteResult:
        """Patch ONLY the Paragraphs + Content RichText bodies (tracker-098 live 4-part
        path), preserving author-owned Tagline + Title. Staged; dry-run safe."""
        return self.patch_fields(collection_id, item_id, {
            config.SUMMARY_PARAGRAPH_FIELD_SLUG: paragraph_html,
            config.SUMMARY_CONTENT_FIELD_SLUG: content_html,
        })

    def ensure_summary_field(self, collection_id: str) -> dict:
        """Verify the Summary RichText field exists on the collection; create if missing."""
        return self.ensure_field(
            collection_id, slug=config.SUMMARY_FIELD_SLUG,
            display_name=config.SUMMARY_FIELD_DISPLAY_NAME, type="RichText",
        )
