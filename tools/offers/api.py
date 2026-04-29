"""Webflow CMS HTTP wrappers for the Offers collection.

Exports:
  OFFERS_COLLECTION_ID  — canonical collection ID constant
  WEBFLOW_API_BASE      — Webflow v2 API base URL
  list_all_offers(token)                   → list[dict]
  patch_end_date(token, item_id, new_iso)  → dict
  publish_items(token, item_ids)           → dict

No module-level I/O.
"""
from __future__ import annotations

from tools.offers._token_helper import APIError, NetworkError, api_request  # noqa: F401

OFFERS_COLLECTION_ID = "691c26d07c581dbd27e75b64"
WEBFLOW_API_BASE = "https://api.webflow.com/v2"


def list_all_offers(token: str) -> list[dict]:
    """Paginate through all Offers collection items and return them as a list."""
    all_items: list[dict] = []
    limit = 100
    offset = 0

    while True:
        url = (
            f"{WEBFLOW_API_BASE}/collections/{OFFERS_COLLECTION_ID}/items"
            f"?limit={limit}&offset={offset}"
        )
        resp = api_request("GET", url, token)
        items = resp.get("items") or []
        all_items.extend(items)

        pagination = resp.get("pagination") or {}
        total = pagination.get("total", 0)
        if offset + limit >= total:
            break
        offset += limit

    return all_items


def patch_end_date(token: str, item_id: str, new_end_date_iso: str) -> dict:
    """PATCH a single Offer's end-date field. Returns parsed API response."""
    url = (
        f"{WEBFLOW_API_BASE}/collections/{OFFERS_COLLECTION_ID}"
        f"/items/{item_id}"
    )
    return api_request(
        "PATCH",
        url,
        token,
        data={"fieldData": {"end-date": new_end_date_iso}},
    )


def publish_items(token: str, item_ids: list[str]) -> dict:
    """Publish a list of Offer items so the live site sees the updated end-date.

    Empty list → skip the API call and return a no-op result.
    """
    if not item_ids:
        return {"publishedItemIds": [], "errors": []}

    url = (
        f"{WEBFLOW_API_BASE}/collections/{OFFERS_COLLECTION_ID}/items/publish"
    )
    return api_request("POST", url, token, data={"itemIds": item_ids})
