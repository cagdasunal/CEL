"""Headless-Chromium screenshot of a live /ar/ page, RTL-rendered.

Captures the page as an Arabic visitor sees it — Weglot translation + the head-loader's
`dir="rtl"` + cel-arabic.css + the Cairo font all applied — so Gemini can diagnose what
still looks wrong. Playwright is an optional dependency (only the weekly visual workflow
installs it); the import is lazy so the rest of the engine imports without it.
"""
from __future__ import annotations

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def capture(url: str, viewport_width: int = 1280, timeout_ms: int = 45000) -> bytes:
    """Return a full-page PNG of `url` after RTL + webfonts have applied.

    Raises on navigation failure (the caller skips that page). The dir=rtl and
    fonts-ready waits are best-effort — on timeout we screenshot anyway rather than
    drop the page, since a slightly-early shot still beats no data.
    """
    from playwright.sync_api import sync_playwright  # lazy — optional dep

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": 1024},
                user_agent=_UA,
                device_scale_factor=1,
            )
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            # The client head-loader sets dir=rtl after load; wait for it.
            try:
                page.wait_for_function(
                    "document.documentElement.getAttribute('dir')==='rtl'", timeout=15000
                )
            except Exception:
                pass
            # Wait for the Cairo webfont so Arabic isn't captured in a fallback face.
            try:
                page.evaluate("() => (document.fonts ? document.fonts.ready : null)")
            except Exception:
                pass
            page.wait_for_timeout(700)  # settle late layout / font swap
            return page.screenshot(full_page=True, type="png")
        finally:
            browser.close()
