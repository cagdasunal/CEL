"""copywriter — multilingual, brief-driven copy improvement on Gemini 3.1 Pro.

Public API:
    from tools.copywriter import improve_copy, improve_copy_batch, CopyRequest, CopyResult

Built on the shared cores (tools.core.gemini, tools.core.webflow,
tools.core.{web,content,seo}) + the translator. Korean-first but locale-native across
all 9 CEL locales: `improve_copy(req)` rewrites natively in `req.locale` and NEVER
translates; translation to other locales is a separate, opt-in step. The human-voice /
anti-AI contract is enforced in BOTH the prompt and the QA gate. See README.md.
"""
from __future__ import annotations

from tools.copywriter.brief import CopyRequest, CopyResult
from tools.copywriter.engine import improve_copy, improve_copy_batch

__all__ = ["improve_copy", "improve_copy_batch", "CopyRequest", "CopyResult"]
