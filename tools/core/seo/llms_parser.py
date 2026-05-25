"""llms.txt parser — single deterministic graph of CEL's URL inventory.

Source format (https://cel.englishcollege.com/llms.txt):
    ## Section
    - [Title](URL): Description
    - [Title](URL): Description
    ## Other Section
    ...

Locale prefix is the only language signal — no explicit language tagging.
Cross-locale equivalents are found by slug-pattern substitution (insert/replace
the /<locale>/ path segment). If the slug differs across locales (e.g. native-
language blog post slugs), find_equivalent returns None — caller must handle.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable, Optional

# 9 CEL locales. The 8 non-EN locales have a `/<code>/` URL prefix; EN has no prefix.
_LOCALE_CODES = ("de", "fr", "es", "it", "pt", "ko", "ja", "ar")

# Line patterns.
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
_ENTRY_RE = re.compile(
    r"^-\s*\[(?P<title>[^\]]+)\]\((?P<url>https?://[^\)]+)\)(?::\s*(?P<description>.+))?\s*$"
)


@dataclass(frozen=True)
class LlmsEntry:
    url: str
    title: str
    description: str
    section: str
    locale: str  # "en" or one of the 8 locale codes


@dataclass
class LlmsIndex:
    """Parsed representation of llms.txt. Read-only after construction."""

    entries: list[LlmsEntry] = field(default_factory=list)
    _by_url: dict[str, LlmsEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._by_url:
            self._by_url = {e.url: e for e in self.entries}

    # ---- Lookup methods ----

    def get_entry(self, url: str) -> Optional[LlmsEntry]:
        return self._by_url.get(url)

    def urls_by_section(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for e in self.entries:
            out.setdefault(e.section, []).append(e.url)
        return out

    def urls_by_locale(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for e in self.entries:
            out.setdefault(e.locale, []).append(e.url)
        return out

    def find_equivalent(self, source_url: str, target_locale: str) -> Optional[str]:
        """Return the equivalent URL in target_locale, or None if no such URL exists.

        Algorithm: parse the source URL's path, replace the locale prefix with the
        target locale, and look up in the index. If the index has the resulting URL,
        return it; else None. NO fuzzy matching — if the slug differs across
        locales, the caller must decide what to do (REMOVE the link, per CEL rules).
        """
        candidate = _swap_locale_prefix(source_url, target_locale)
        if candidate and candidate in self._by_url:
            return candidate
        return None

    def find_equivalent_or_fallback(
        self, source_url: str, target_locale: str, url_map: Optional[dict] = None
    ) -> Optional[str]:
        """Same-locale link target with a SAFE, ordered fallback chain:

        0. **hreflang url_map** — authoritative EN→locale mapping that resolves
           TRANSLATED slugs the locale-prefix swap can't (e.g. /pathway-program-usa
           → /de/auslandsstudium-usa). Index-verified.
        1. **blog posts** — ORIGINAL per locale (no per-post translation; the
           same-slug /{locale}/post/<en-slug> redirects to the English original, a
           cross-locale leak), so link to the locale blog hub instead, or drop.
        2. exact slug-swap (locales that keep the EN slug).
        3. nearest in-index same-locale ancestor path.
        4. the locale root hub → else None.

        Every returned URL is index-verified AND carries the target locale's prefix,
        so a result can NEVER leak to another locale or to a nonexistent page.
        """
        # 0. Authoritative hreflang map (translated slugs).
        if url_map:
            mapped = (url_map.get(_norm_url(source_url)) or {}).get(target_locale)
            if mapped and self._url_in_index(mapped):
                return mapped

        candidate = _swap_locale_prefix(source_url, target_locale)
        if not candidate:
            return None
        parsed = urllib.parse.urlparse(candidate)

        # 1. Blog posts → locale blog hub (or drop). See docstring.
        if _is_post_path(candidate, target_locale):
            blog_paths = ((f"/{target_locale}/blog", f"/{target_locale}/blog/")
                          if target_locale != "en" else ("/blog", "/blog/"))
            for path in blog_paths:
                blog = urllib.parse.urlunparse(parsed._replace(path=path))
                if blog in self._by_url:
                    return blog
            return None

        # 2. exact slug-swap.
        exact = self.find_equivalent(source_url, target_locale)
        if exact:
            return exact

        # 3. nearest in-index same-locale ancestor (never drop below the locale prefix).
        segs = [s for s in parsed.path.strip("/").split("/") if s]
        floor = 1 if target_locale != "en" else 0
        while len(segs) > floor:
            segs = segs[:-1]
            for path in ("/" + "/".join(segs), "/" + "/".join(segs) + "/"):
                ancestor = urllib.parse.urlunparse(parsed._replace(path=path))
                if ancestor in self._by_url:
                    return ancestor

        # 4. locale root hub.
        root_paths = ((f"/{target_locale}/", f"/{target_locale}")
                      if target_locale != "en" else ("/",))
        for path in root_paths:
            root = urllib.parse.urlunparse(parsed._replace(path=path))
            if root in self._by_url:
                return root
        return None

    def _url_in_index(self, url: str) -> bool:
        """True if `url` (or its trailing-slash variant) is a known llms.txt URL."""
        return (url in self._by_url
                or _norm_url(url) in self._by_url
                or (_norm_url(url) + "/") in self._by_url)

    def urls_in_locale_excluding(
        self,
        locale: str,
        excluded_path_segments: Iterable[str] = (),
    ) -> list[str]:
        """All URLs for this locale whose path does NOT contain any excluded segment."""
        excluded = tuple(excluded_path_segments)
        out: list[str] = []
        for e in self.entries:
            if e.locale != locale:
                continue
            if any(_path_has_segment(e.url, seg) for seg in excluded):
                continue
            out.append(e.url)
        return out

    def urls_in_locale_section(self, locale: str, section_prefix: str) -> list[str]:
        """All URLs in a locale whose path begins with `/<locale>/<section_prefix>` (or
        `/<section_prefix>` for EN). Useful for picking blog-post candidates in DE etc."""
        out: list[str] = []
        target_root = f"/{section_prefix.strip('/')}/"
        for e in self.entries:
            if e.locale != locale:
                continue
            path = urllib.parse.urlparse(e.url).path
            if locale != "en":
                # path starts with /<locale>/...; we want /<locale>/<section_prefix>/...
                expected = f"/{locale}/{section_prefix.strip('/')}/"
                if path.startswith(expected):
                    out.append(e.url)
            else:
                if path.startswith(target_root):
                    out.append(e.url)
        return out


def parse_llms_txt(text: str) -> LlmsIndex:
    """Parse llms.txt text into an LlmsIndex. Pure function — no I/O."""
    entries: list[LlmsEntry] = []
    current_section = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        m_section = _SECTION_RE.match(line)
        if m_section:
            current_section = m_section.group(1).strip()
            continue
        m_entry = _ENTRY_RE.match(line)
        if m_entry:
            url = m_entry.group("url").strip()
            title = m_entry.group("title").strip()
            description = (m_entry.group("description") or "").strip()
            locale = _detect_locale(url)
            entries.append(
                LlmsEntry(
                    url=url,
                    title=title,
                    description=description,
                    section=current_section,
                    locale=locale,
                )
            )
    return LlmsIndex(entries=entries)


def fetch_and_parse(url: str, timeout: float = 15.0) -> LlmsIndex:
    """Fetch llms.txt over HTTPS and parse. Raises on network or HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": "cel-tools/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    return parse_llms_txt(text)


# ---- Internal helpers ----


def _detect_locale(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    parts = path.strip("/").split("/", 1)
    if parts and parts[0] in _LOCALE_CODES:
        return parts[0]
    return "en"


def _swap_locale_prefix(url: str, target_locale: str) -> Optional[str]:
    """Return the URL with its locale prefix swapped to target_locale.

    For source `/courses` (EN) and target `de` → `/de/courses`.
    For source `/de/kurse` and target `fr` → `/fr/kurse`.
    Returns None for malformed URLs.
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed.path:
        return None
    parts = parsed.path.strip("/").split("/")
    if not parts:
        return None
    # Strip existing locale prefix (if any).
    if parts[0] in _LOCALE_CODES:
        parts = parts[1:]
    # Prepend target locale prefix (none for EN).
    if target_locale != "en":
        new_path = "/" + "/".join([target_locale] + parts)
    else:
        new_path = "/" + "/".join(parts)
    # Trailing slash preservation — match the original style if any.
    if parsed.path.endswith("/") and not new_path.endswith("/"):
        new_path += "/"
    return urllib.parse.urlunparse(parsed._replace(path=new_path))


def _path_has_segment(url: str, segment: str) -> bool:
    parts = urllib.parse.urlparse(url).path.strip("/").split("/")
    return segment in parts


def _norm_url(url: str) -> str:
    """Drop query/fragment + trailing slash (match the hreflang url_map key form)."""
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/")


def _is_post_path(url: str, target_locale: str) -> bool:
    """True if `url`'s path is a blog post: `/post/...` (EN) or `/{locale}/post/...`."""
    segs = [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]
    if target_locale != "en":
        return len(segs) >= 2 and segs[1] == "post"
    return bool(segs) and segs[0] == "post"
