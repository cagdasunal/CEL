"""Back-compat shim — implementation moved to tools.core.web.page_fetcher (Plan B2).

Re-exports the full module namespace (public + private) so existing import paths
(`from tools.summary.page_fetcher import fetch_page, PageContent, _parse_html`) and
`monkeypatch.setattr(page_fetcher, "fetch_page", ...)` keep working with object
identity preserved. New code should import from tools.core.web.page_fetcher.
See docs/ARCHITECTURE.md.
"""
from tools.core.web import page_fetcher as _src
from tools.core.web.page_fetcher import *  # noqa: F401,F403

# Re-export every remaining top-level name (incl. private helpers used by tests/callers),
# preserving object identity for monkeypatch parity.
globals().update({_k: _v for _k, _v in vars(_src).items() if not _k.startswith("__")})
del _src
