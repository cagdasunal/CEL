"""Shared Webflow Data API v2 client (leaf): HTTP plumbing + CMS reads/writes.

The canonical Webflow integration for CEL tools — import
`from tools.core.webflow.cms import CmsClient, WriteResult` (or
`from tools.core.webflow.http import request, WebflowApiError`). Tools build on this
instead of reimplementing Webflow writes. See docs/ARCHITECTURE.md.
"""
