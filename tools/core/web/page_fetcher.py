"""Fetch a live page and extract content needed for keyword derivation + audit.

Pure stdlib: urllib + html.parser. NO lxml dependency (despite CEL's requirements.txt
listing it for other tools, this module stays stdlib-only for resilience).

Public API: `fetch_page(url) -> PageContent`.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional


_USER_AGENT = "cel-tools/1.0"
_BODY_EXCERPT_MAX_CHARS = 8000
_FETCH_TIMEOUT = 20.0


@dataclass(frozen=True)
class PageContent:
    url: str
    final_url: str
    status: int
    html: str
    title: str
    h1: str
    headings: tuple[str, ...]
    canonical: Optional[str]
    hreflang_urls: tuple[str, ...]
    existing_summary_html: str
    body_text_excerpt: str  # ≤ 8000 chars, plain text
    description: str = ""  # <meta name="description"> content (tracker-092 Phase 3 meta caller)
    # tracker-096: inner HTML of the 4-part Summary elements, keyed by element id
    # (summary-tagline / summary-title / summary-paragraph / summary-content). Empty
    # when the page has none (e.g. the legacy single id="summary" → existing_summary_html).
    existing_summary_parts: dict = field(default_factory=dict)


def fetch_page(url: str, timeout: float = _FETCH_TIMEOUT) -> PageContent:
    """Fetch a URL with Googlebot UA and parse fields.

    URL scheme is restricted to http/https. file://, ftp://, gopher:// and other
    urllib-supported handlers are rejected to prevent SSRF (tracker-087 F-3).
    """
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme must be http or https; got {parsed_url.scheme!r} for {url!r}"
        )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        final_url = resp.geturl()
        body_bytes = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        html = body_bytes.decode(charset, errors="replace")
    return _parse_html(url, final_url, status, html)


def _parse_html(url: str, final_url: str, status: int, html: str) -> PageContent:
    """Parse HTML and return a PageContent. Pure function — no I/O."""
    parser = _ExtractParser()
    try:
        parser.feed(html)
    except Exception:
        # html.parser raises on some malformed inputs; degrade gracefully.
        pass
    body_text = _extract_body_text(html)
    return PageContent(
        url=url,
        final_url=final_url,
        status=status,
        html=html,
        title=parser.title.strip(),
        h1=parser.h1.strip(),
        headings=tuple(h.strip() for h in parser.headings if h.strip()),
        canonical=parser.canonical or None,
        hreflang_urls=tuple(parser.hreflang_urls),
        existing_summary_html=parser.existing_summary_html.strip(),
        body_text_excerpt=body_text[:_BODY_EXCERPT_MAX_CHARS],
        description=parser.description.strip(),
        existing_summary_parts={k: v.strip() for k, v in parser.existing_summary_parts.items()},
    )


# ---- Internal parser ----


_CAPTURE_IDS = (
    "summary",  # legacy single-block element → existing_summary_html
    "summary-tagline",  # tracker-096 4-part elements → existing_summary_parts
    "summary-title",
    "summary-paragraph",
    "summary-content",
)


class _ExtractParser(HTMLParser):
    """Single-pass HTML parser that extracts title, H1, headings, canonical, hreflang,
    the legacy `id="summary"` element, and (tracker-096) the four 4-part Summary
    elements (`summary-tagline` / `summary-title` / `summary-paragraph` /
    `summary-content`)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1 = ""
        self.description = ""
        self.headings: list[str] = []
        self.canonical = ""
        self.hreflang_urls: list[str] = []
        self.existing_summary_html = ""
        self.existing_summary_parts: dict[str, str] = {}
        # State
        self._in_title = False
        self._heading_tag: Optional[str] = None
        self._heading_buffer: list[str] = []
        # Generic single-element capture: the id currently being captured + nesting
        # depth + buffer. One element captured at a time (the 4 parts are siblings).
        self._capture_id: Optional[str] = None
        self._capture_depth = 0
        self._capture_buffer: list[str] = []
        # Skip script/style content entirely.
        self._skip_tag: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        if self._skip_tag:
            return
        if tag in ("script", "style"):
            self._skip_tag = tag
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self._heading_tag = tag
            self._heading_buffer = []
        if tag == "link":
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "")
            if rel == "canonical" and not self.canonical:
                self.canonical = href
            if "alternate" in rel and href:
                self.hreflang_urls.append(href)
        if tag == "meta" and not self.description:
            if attr_dict.get("name", "").lower() == "description":
                self.description = attr_dict.get("content", "")
        # Track entry into a captured Summary element (legacy #summary or one of the
        # four 4-part elements). Capture one element at a time; the depth counter
        # handles nested children within it.
        el_id = attr_dict.get("id")
        if self._capture_id is None and el_id in _CAPTURE_IDS:
            self._capture_id = el_id
            self._capture_depth = 1
        elif self._capture_id is not None:
            self._capture_depth += 1
        if self._capture_id is not None:
            self._capture_buffer.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_tag == tag:
            self._skip_tag = None
            return
        if self._skip_tag:
            return
        if self._capture_id is not None:
            self._capture_buffer.append(f"</{tag}>")
            self._capture_depth -= 1
            if self._capture_depth == 0:
                captured = "".join(self._capture_buffer)
                if self._capture_id == "summary":
                    self.existing_summary_html = captured
                else:
                    self.existing_summary_parts[self._capture_id] = captured
                self._capture_id = None
                self._capture_buffer = []
        if tag == "title":
            self._in_title = False
        if tag == self._heading_tag:
            text = "".join(self._heading_buffer).strip()
            if text:
                self.headings.append(text)
                if tag == "h1" and not self.h1:
                    self.h1 = text
            self._heading_tag = None
            self._heading_buffer = []

    def handle_data(self, data: str) -> None:
        if self._skip_tag:
            return
        if self._in_title:
            self.title += data
        if self._heading_tag:
            self._heading_buffer.append(data)
        if self._capture_id is not None:
            self._capture_buffer.append(data)


def _extract_body_text(html: str) -> str:
    """Best-effort plain-text extraction. Strips scripts/styles + all tags + collapses whitespace."""
    # Remove script/style blocks.
    cleaned = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE
    )
    # Strip tags.
    text = re.sub(r"<[^>]+>", " ", cleaned)
    # Decode common entities.
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text
