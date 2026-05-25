"""Back-compat shim — implementation moved to tools.core.gemini.client (Plan A).

Re-exports the full module namespace (public + private, incl. _PENDING_BATCHES,
_parse_inline_response, _retry_transient, _build_generation_config,
_flatten_system_blocks, _result_from_response, …) so existing import paths
(`from tools.summary import batch_runner`) and `monkeypatch.setattr(batch_runner, ...)`
keep working with object identity preserved. New code should import from
tools.core.gemini.client. See docs/ARCHITECTURE.md.
"""
from tools.core.gemini import client as _src
from tools.core.gemini.client import *  # noqa: F401,F403

globals().update({_k: _v for _k, _v in vars(_src).items() if not _k.startswith("__")})
del _src
