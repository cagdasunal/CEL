"""EN↔locale URL map from hreflang alternates (tracker-106).

llms.txt and the sitemap use TRANSLATED slugs per locale — e.g. the EN
`/pathway-program-usa` is `/de/auslandsstudium-usa`, `/es/programa-pathway-usa`,
`/fr/programme-preparation-universitaire-etas-unis` (de/es/fr translate; ko/pt/it/
ja/ar keep the EN slug). So the naive `/{locale}/{en-slug}` swap in
`llms_parser._swap_locale_prefix` only resolves the EN-slug locales and misses
de/es/fr, collapsing those links to the locale hub.

The AUTHORITATIVE EN→locale mapping lives in each EN page's
`<link rel="alternate" hreflang="...">` tags (Weglot-injected). This module
fetches those once and caches `{en_url: {locale: localized_url}}` so the translate
phase links same-locale to the CORRECT translated URL.

Pure-stdlib. Import-safe (no module-level I/O). `build_url_map` takes an injectable
`fetch` so tests never hit the network.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Optional

# Target locales (en is the source, excluded from the per-page mapping).
TARGET_LOCALES = ("de", "es", "fr", "it", "pt", "ko", "ja", "ar")
_ALL_LOCALES = TARGET_LOCALES + ("en",)

_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_HREFLANG_RE = re.compile(r'hreflang=["\']([A-Za-z-]{2,5})["\']', re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_REL_ALT_RE = re.compile(r'rel=["\']alternate["\']', re.IGNORECASE)
_LOC_RE = re.compile(r"https://www\.englishcollege\.com/[^\s)\"']+")
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(https://www\.englishcollege\.com/[^<\s]+)\s*</loc>", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Drop query/fragment + trailing slash; lowercase host stays as-is (already www)."""
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/")


def _path_first_segment(url: str) -> str:
    path = url[len("https://www.englishcollege.com"):] if url.startswith("https://www.englishcollege.com") else url
    segs = [s for s in path.split("/") if s]
    return segs[0] if segs else ""


def is_en_page(url: str) -> bool:
    """True for an EN canonical page to map: englishcollege.com, NOT locale-prefixed
    (those are the targets we resolve to), NOT the sitemap/llms file.

    Blog posts (`/post/...`) ARE included: although their summaries are never
    translated (blog is native-per-locale), a translated course/landing summary
    still LINKS to blog posts, so we need EN-post → locale-post mappings for
    same-locale linking (e.g. /post/x → /de/post/<german-slug>)."""
    if not url.startswith("https://www.englishcollege.com/"):
        return False
    first = _path_first_segment(url)
    if first in _ALL_LOCALES:   # locale-prefixed → a target, not a source
        return False
    if url.endswith(".xml") or url.endswith(".txt"):
        return False
    return True


def en_pages_from_sources(llms_text: str, sitemap_xml: str) -> list[str]:
    """Union the EN canonical pages from llms.txt + sitemap.xml (deduped, sorted)."""
    urls: set[str] = set()
    for m in _LOC_RE.findall(llms_text or ""):
        urls.add(normalize_url(m))
    for m in _SITEMAP_LOC_RE.findall(sitemap_xml or ""):
        urls.add(normalize_url(m))
    return sorted(u for u in urls if is_en_page(u))


def extract_hreflang(html: str) -> dict[str, str]:
    """Return {locale: normalized_url} from a page's hreflang alternate <link> tags.

    Robust to attribute order: each `<link>` tag must carry rel="alternate",
    hreflang, and href. Regional codes (e.g. en-US) collapse to the base locale.
    """
    out: dict[str, str] = {}
    for tag in _LINK_TAG_RE.findall(html or ""):
        if not _REL_ALT_RE.search(tag):
            continue
        hl = _HREFLANG_RE.search(tag)
        hr = _HREF_RE.search(tag)
        if not (hl and hr):
            continue
        loc = hl.group(1).lower().split("-", 1)[0]
        if loc in _ALL_LOCALES:
            out[loc] = normalize_url(hr.group(1))
    return out


def build_url_map(
    en_urls: Iterable[str],
    fetch: Callable[[str], Optional[str]],
    locales: Iterable[str] = TARGET_LOCALES,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Build `{en_url: {locale: localized_url}}` by fetching each EN page's hreflang.

    `fetch(url) -> html | None` (None on any fetch failure — injectable for tests).
    Returns (map, skipped_urls). A page is skipped if the fetch fails or it has no
    usable alternate for any target locale.
    """
    locales = tuple(locales)
    out: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for u in en_urls:
        html = fetch(u)
        if not html:
            skipped.append(u)
            continue
        alts = extract_hreflang(html)
        mapping = {loc: alts[loc] for loc in locales if loc in alts}
        if mapping:
            out[normalize_url(u)] = mapping
        else:
            skipped.append(u)
    return out, skipped


def load_url_map(path: Path) -> dict[str, dict[str, str]]:
    """Load the cached `{en_url: {locale: url}}` map, or {} if absent/corrupt.

    Accepts both the wrapped artifact ({"map": {...}, "generated_at": ...}) and a
    bare map. Graceful (pre-build state → {})."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    inner = data.get("map")
    return inner if isinstance(inner, dict) else data


def localized_url(url_map: dict, source_url: str, target_locale: str) -> Optional[str]:
    """Look up the authoritative same-locale URL for `source_url`, or None."""
    if not url_map:
        return None
    return (url_map.get(normalize_url(source_url)) or {}).get(target_locale)


def _http_fetch(url: str, timeout: float = 20.0, retries: int = 3) -> Optional[str]:
    """Fetch with retry + backoff — rides out transient failures / brief rate-limits.
    Returns HTML or None after exhausting retries."""
    import time

    req = urllib.request.Request(url, headers={"User-Agent": "cel-url-map/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception:
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))  # 2s, 4s backoff
    return None


def _main() -> int:
    """Live build: fetch llms.txt + sitemap, enumerate EN pages, fetch each page's
    hreflang, write the map JSON. Run when pages/slugs change."""
    import sys
    from tools.summary import config

    llms = _http_fetch(config.LLMS_TXT_URL) or ""
    sitemap = _http_fetch("https://cel.englishcollege.com/sitemap.xml") or ""
    en = en_pages_from_sources(llms, sitemap)
    print(f"[url-map] {len(en)} EN pages from llms.txt + sitemap (incl. blog as link targets)", file=sys.stderr)

    # Throttle: ~2 req/s so a 200-page sweep doesn't trip Cloudflare/Webflow rate
    # limits (which return connection resets → skipped pages). Retry+backoff in
    # _http_fetch rides out brief limits; the delay prevents triggering them.
    import time

    def _polite(u: str) -> Optional[str]:
        html = _http_fetch(u)
        time.sleep(0.5)
        return html

    url_map, skipped = build_url_map(en, _polite)
    out_path = config.URL_MAP_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "source_count": len(en),
        "mapped_count": len(url_map),
        "skipped": skipped,
        "map": url_map,
    }
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_path)
    print(f"[url-map] mapped {len(url_map)}/{len(en)} pages → {out_path} ({len(skipped)} skipped)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
