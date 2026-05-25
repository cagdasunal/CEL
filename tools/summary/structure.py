"""Back-compat shim — implementation moved to tools.core.content.structure (Plan B2).

Re-exports the full module namespace (public + private) so existing import paths
(`from tools.summary.structure import FourPartSummary, parse_four_part,
summary_markdown_to_html, summary_page_blocks, ...`) keep working with object
identity preserved. New code should import from tools.core.content.structure.
See docs/ARCHITECTURE.md.
"""
from tools.core.content import structure as _src
from tools.core.content.structure import *  # noqa: F401,F403

globals().update({_k: _v for _k, _v in vars(_src).items() if not _k.startswith("__")})
del _src
