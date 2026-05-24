"""Back-compat shim — implementation moved to tools.core.seo.llms_parser (Plan B2).

Re-exports the full module namespace (public + private) so existing import paths
(`from tools.summary.llms_parser import LlmsIndex, fetch_and_parse, ...`) and
`monkeypatch.setattr(llms_parser, "fetch_and_parse", ...)` keep working with object
identity preserved. New code should import from tools.core.seo.llms_parser.
See docs/ARCHITECTURE.md.
"""
from tools.core.seo import llms_parser as _src
from tools.core.seo.llms_parser import *  # noqa: F401,F403

globals().update({_k: _v for _k, _v in vars(_src).items() if not _k.startswith("__")})
del _src
