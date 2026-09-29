"""Gemini client config (shared) — model tiering, thinking, caching, output-token
estimates, and the dry-run / last-batch paths the shared client reads.

Canonical home (Plan A) for the Gemini knobs that `tools.core.gemini.client` reads.
`tools.summary.config` re-exports these for back-compat. Pure constants, no I/O.
The cost-gate caps (MAX_BATCH_COST_USD / COST_CONFIRM_THRESHOLD_USD) intentionally
stay in tools/summary/config.py — the client doesn't read them; cli.py does.
See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from pathlib import Path

# Repo root: this file is tools/core/gemini/config.py → parents[3] == repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Google Gemini 3.1 Pro Preview (tracker-091 migration from Claude). Pricing ref
# (2026-05-21, tracker-097): interactive $2/$12 per 1M; Batch $1/$6; cached read $0.20.
MODEL_ID = "gemini-3.1-pro-preview"

# U3-S (2026-09-29): every content type runs on MODEL_ID. The blog tier (tracker-097) sat on
# gemini-2.5-flash, which now answers 404 "no longer available to new users" for this key, so
# every blog request failed. The blog generator takes the localization engine's decision
# (monorepo sites/cel/docs/localize-gemini-models-2026-09-29.md): 3.1 Pro, thinking pinned at
# BLOG_THINKING_LEVEL. MODEL_BLOG now serves only `link-blogs`, which rewrites summaries that
# already exist; it is left on the dead model on purpose (the operator: "Never rewrite ...").
MODEL_BLOG = "gemini-2.5-flash"
MODEL_BY_CONTENT_TYPE: dict[str, str] = {}
# G-1 (2026-09-29): models the project's key cannot use -- each answers 404 "no longer available to new
# users" (Google limits 2.5 to past users), though models.list still lists them. client.usable_model()
# refuses them before any call; MODEL_BLOG (link-blogs, kept dead) is one of them. The same list as the
# localization engine's (monorepo tools/localize/draft.GONE_MODELS).
GONE_MODELS = frozenset({"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"})
BLOG_THINKING_LEVEL = "high"


def model_for_content_type(content_type: str) -> str:
    """Resolve the Gemini model for a content type (tracker-097 tiering)."""
    return MODEL_BY_CONTENT_TYPE.get(content_type, MODEL_ID)


# tracker-097 explicit context-cache lifecycle. Caching the ~6,500-token system prefix
# drops it to the cache-read rate. Only groups >= CACHE_MIN_GROUP_SIZE are cached.
# TTL must cover the whole async in-job batch run (caches deleted in wait_for_batch).
CACHE_TTL_SECONDS = 6 * 3600  # 6h — matches the GHA job timeout
CACHE_MIN_GROUP_SIZE = 2
# Safety valve: set False to fall back to full-price generation without a code change.
ENABLE_EXPLICIT_CACHE = True

# Per-request OUTPUT-token allowance for cost estimation (2026-05-23, audit C1 fix).
# Gemini bills THINKING tokens AS output; keyed by (model_family, enable_thinking).
# Conservative by design — over-estimating makes the cost gate stricter, not looser.
OUTPUT_TOKEN_ESTIMATE = {
    ("pro", True): 5500,    # thinking-heavy 4-part landing / courses / housing generation
    ("pro", False): 1000,   # translation (thinking disabled) + any no-think Pro path
    ("flash", True): 1300,  # blog single-block (Flash thinking_budget=0)
    ("flash", False): 1300,
}
DEFAULT_OUTPUT_TOKEN_ESTIMATE = 1500
# U3-S: a request pinned at thinking "high" (the blog generator): the answer (~1,300, the old
# blog allowance) plus the engine doc's 8,000-token thinking floor.
OUTPUT_TOKEN_ESTIMATE_THINKING_HIGH = 9_300
# G-1 (2026-09-29): the level a Pro request with thinking OFF is sent at. 3.1 Pro cannot switch thinking
# off; omitting it meant its default -- high, billed as output -- unpinned. Pinned to the same level, so
# nothing changes today and a change of Google's default cannot move spend or quality unseen. The same
# level the localization engine translates at (monorepo draft.THINKING_LEVEL).
PRO_THINKING_OFF_LEVEL = "high"

# Extended thinking budget for content generation (translation passes disable thinking).
THINKING_BUDGET_TOKENS = 1500

# Dry-run artifact dir + the last submitted Batch job's recovery pointer. Path values
# kept identical to the summary-era constants for back-compat (the GHA workflow commits
# summary-last-batch.json; cancel-batch/retrieve-batch read it).
DRYRUN_DIR = PROJECT_ROOT / "data" / "seo-intel" / "summary-dryrun"
LAST_BATCH_FILE = PROJECT_ROOT / "data" / "seo-intel" / "summary-last-batch.json"
