"""Copywriter config — reuses the summary collections/locales + the shared Gemini model;
adds copywriter-specific paths + a prompt version. Pure constants, no business logic.
"""
from __future__ import annotations

from pathlib import Path

from tools.core.gemini import config as _gemini_config
from tools.summary import config as _summary_config

# Gemini 3.1 Pro for copy (human-first prose). Single source = the shared Gemini config.
MODEL_ID = _gemini_config.MODEL_ID

# 9 CEL locales (reuse summary's tuple). EN is the source for translated collections;
# all 9 are valid `improve` targets (locale-native).
LOCALES = _summary_config.LOCALES

# Per-locale prompt layers (register + AI-tell banlists) live in the summary tool
# (single source); the copywriter REUSES them rather than duplicating 9 files.
LOCALE_LAYERS_DIR = Path(_summary_config.PROMPTS_DIR) / "locales"

# The copywriter's own universal system prompt (human-voice + anti-AI + SEO).
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Bump when the prompt/QA contract changes materially (mirrors SUMMARY_PROMPT_VERSION).
COPYWRITER_PROMPT_VERSION = "2026-05-25-c001"

# Run artifacts: before/after preview, backup of prior CMS content, audit log.
RUN_DIR = _summary_config.PROJECT_ROOT / "data" / "seo-intel" / "copywriter-runs"

# Static-page improved-copy docs (for assisted Designer-MCP deploy / manual paste).
STATIC_DOC_DIR = _summary_config.PROJECT_ROOT / "docs" / "admin" / "copywriter"

# Reused from summary (internal linking + Webflow targets).
LLMS_TXT_URL = _summary_config.LLMS_TXT_URL
COLLECTIONS = _summary_config.COLLECTIONS
EXCLUDED_LINK_PATH_SEGMENTS = _summary_config.EXCLUDED_LINK_PATH_SEGMENTS
BLOG_LANGUAGE_ID_TO_LOCALE = _summary_config.BLOG_LANGUAGE_ID_TO_LOCALE
