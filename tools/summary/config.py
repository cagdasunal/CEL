"""Config — locale codes, collection IDs, model, exclusions, paths.

Single source of truth for IDs and rules. No business logic — pure constants.
Update MODEL_ID when a more capable Gemini production model ships.
"""
from __future__ import annotations

from pathlib import Path

# Google Gemini 3.1 Pro Preview — top-tier production model on Artificial
# Analysis Intelligence Index (tied with Opus 4.7 at 57). Migrated from
# claude-opus-4-7 in tracker-091 (2026-05-19 evening).
# Pricing reference (verified 2026-05-21 — tracker-097): interactive
# $2.00 in / $12.00 out per 1M (≤200k ctx); Batch $1.00 / $6.00; cached read $0.20.
# https://ai.google.dev/gemini-api/docs/pricing
MODEL_ID = "gemini-3.1-pro-preview"

# tracker-097: model tiering. The bulk blog catalog (415 posts × locales) is the
# single-block, lower-stakes path — generate it on Gemini 2.5 Flash (~6.7× cheaper
# input / ~4.8× cheaper output than Pro, and supports thinking_budget=0). The
# high-value designed pages (static landing + courses + housing 4-part) stay on Pro.
# QA gate is the quality backstop: a weak Flash summary is demoted to MANUAL_REVIEW,
# never shipped. Reversible — change this map and bump SUMMARY_PROMPT_VERSION.
MODEL_BLOG = "gemini-2.5-flash"
MODEL_BY_CONTENT_TYPE = {
    "blog_post": MODEL_BLOG,
    # course / housing / landing default to MODEL_ID (Pro) via model_for_content_type.
}


def model_for_content_type(content_type: str) -> str:
    """Resolve the Gemini model for a content type (tracker-097 tiering)."""
    return MODEL_BY_CONTENT_TYPE.get(content_type, MODEL_ID)


# Defensive cost cap (tracker-097: 100 → 15). A run aborts if estimated cost
# exceeds this — a real guardrail, not the old ~$100 no-op. Tunable.
MAX_BATCH_COST_USD = 15

# tracker-097: a LIVE run whose projected cost exceeds this refuses to submit
# unless --confirm-cost is passed (operationalizes pilot-first: you always see
# the projection before any spend). Tiny pilot runs (a few items, well under $1)
# proceed without the flag. The standing rule "no paid run without explicit
# go-ahead" is the human layer; this is the code-level backstop.
COST_CONFIRM_THRESHOLD_USD = 1.00

# Locales. EN is the source language; the other 8 are translation targets.
LOCALES = ("en", "de", "fr", "es", "it", "pt", "ko", "ja", "ar")
TARGET_TRANSLATION_LOCALES = LOCALES[1:]

# Webflow site + collections.
WEBFLOW_SITE_ID = "667453c576e8d35c454cc9ae"

COLLECTIONS = {
    "blog": "667453c576e8d35c454ccaae",
    "courses": "667453c576e8d35c454cca49",
    "housing_new": "69e8ab603e1e04f22496dd3c",
}

# Collections whose URLs must NEVER appear as internal-link targets in any locale
# (legacy per-city housing — currently unpublished). The script filters link
# candidates by URL path-segment match against these slugs.
EXCLUDED_LINK_COLLECTION_IDS = (
    "66bb665a060d43bf40f9d37c",  # Housing — Vancouver (slug: vc)
    "667453c576e8d35c454cca6b",  # Housing — San Diego (slug: sd)
    "667453c576e8d35c454ccaf2",  # Housing — Los Angeles (slug: sm)
)
EXCLUDED_LINK_PATH_SEGMENTS = ("vc", "sd", "sm")

# Housing link policy (2026-05-22): there is NO cap on `/housing` link candidates — the
# site has many new accommodation pages (hub + per-city detail pages, every locale) that
# need inbound internal links. `_build_link_candidate_pool` offers ALL housing candidates,
# ordered first so they survive the prompt cap; the model links them where contextually
# relevant (city-matched) and the link-stuffing + 6–8-link QA caps the total.

# Which collections get translated (English source → 8 target languages via CSV).
TRANSLATE_COLLECTIONS = ("courses",)

# Which collections have native-language summaries (one summary per item in the item's
# authored language; no translation).
NATIVE_LANGUAGE_COLLECTIONS = ("blog",)

# Blog posts are ORIGINAL per locale but carry their language as a Reference (the
# `language` field → the Languages collection 687658de56f115eff1e02e18), NOT a shortcode
# string. Map each Languages item id → locale shortcode so a blog summary is generated
# in the post's actual language (e.g. a French post gets a French summary), not English.
# Verified live via the Languages collection 2026-05-20 (tracker-096 follow-up).
BLOG_LANGUAGE_ID_TO_LOCALE = {
    "6876590744e1f69b128ef245": "en",
    "6876596a3a4d6e078bebe528": "de",
    "6876591fab42b61d6b9e5d68": "es",
    "687659b3281d98a9803a86ae": "fr",
    "687659cca45f80dbea92430c": "it",
    "6876599de124298a6bd8cb8d": "pt",
    "6876597d1d2fe4f1a294fd77": "ko",
    "687659e4ab42b61d6b9f6a96": "ja",
    "687659fe11c147ceed4f09cd": "ar",
}

# Which collections are summarized in English but never translated. Their items still
# get a Summary field populated; Weglot fallback handles display on locale URLs.
NO_TRANSLATE_COLLECTIONS = ("housing_new",)

# Static landing pages — write to the element with id="summary" via Webflow Designer API.
STATIC_PAGES = (
    "https://www.englishcollege.com/",
    "https://www.englishcollege.com/courses",  # tracker-098 follow-up: course catalogue index (→ 17 total)
    "https://www.englishcollege.com/san-diego-ca/language-school",
    "https://www.englishcollege.com/los-angeles-ca/language-courses",
    "https://www.englishcollege.com/summer-camp-san-diego",
    "https://www.englishcollege.com/learn-english-usa",
    "https://www.englishcollege.com/learn-english-canada",
    "https://www.englishcollege.com/housing",
    "https://www.englishcollege.com/pathway-program-usa",
    "https://www.englishcollege.com/pathway/semester-abroad",
    "https://www.englishcollege.com/pathway/certificate-programs",
    "https://www.englishcollege.com/pathway/undergraduate-programs",
    "https://www.englishcollege.com/pathway/graduate-programs",
    # tracker-096: Vancouver landing pages (added to the existing 12 → 16 total).
    "https://www.englishcollege.com/vancouver",
    "https://www.englishcollege.com/vancouver/cost-of-studying-english",
    "https://www.englishcollege.com/vancouver/how-long-to-learn-english",
    "https://www.englishcollege.com/vancouver/vs-toronto",
)

# llms.txt — internal-linking source of truth (NOT sitemap.xml).
LLMS_TXT_URL = "https://cel.englishcollege.com/llms.txt"

# Filesystem layout.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEGLOT_IMPORTS_DIR = PROJECT_ROOT / "docs" / "admin" / "weglot-imports"
DRYRUN_DIR = PROJECT_ROOT / "data" / "seo-intel" / "summary-dryrun"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# tracker-092 Phase 2: idempotency. summary-state.json maps a content id
# (cms_item_id for CMS items, or the static-page URL) → a hash of its source
# content + prompt version. generate-english skips items whose hash is unchanged
# since the last successful run (unless --force) so re-runs don't re-submit
# unchanged items to Gemini. Bump SUMMARY_PROMPT_VERSION whenever the prompts or
# keyword logic change materially, to force a full regeneration.
# tracker-097: bumped 2026-05-21-t096 → -t097 (provenance trimmed from common.md +
# per-content-type model tiering). The model is also folded into _source_hash, so a
# future model change regenerates without a version bump; this bump forces a one-time
# full regeneration under the new cheaper (tiered + cached) pipeline.
SUMMARY_PROMPT_VERSION = "2026-05-21-t098"
SUMMARY_STATE_FILE = PROJECT_ROOT / "data" / "seo-intel" / "summary-state.json"

# tracker-097: the last submitted Batch job's id + metadata, persisted on submit so a
# cancelled/failed GHA run can `cancel-batch`/`retrieve-batch` it (a submitted Gemini
# batch keeps billing even after the GHA run is cancelled — see RC5). Committed by the
# workflow alongside summary-state.json so it survives across runs.
LAST_BATCH_FILE = PROJECT_ROOT / "data" / "seo-intel" / "summary-last-batch.json"

# tracker-097: explicit context-cache lifecycle. The ~6,500-token system prefix is
# identical across every (content_type, locale, model) group; caching it drops the
# prefix from full input rate to the cache-read rate ($0.20/M Pro, $0.03/M Flash).
# Only groups with >= CACHE_MIN_GROUP_SIZE items are cached (a 1-item cache adds a
# create/delete round-trip for negligible saving).
#
# TTL note: a Batch job runs ASYNCHRONOUSLY (1-4h typical, capped by the GHA job's
# 6h timeout) and the cache is looked up at PROCESSING time — so the TTL must cover
# the whole in-job batch run, NOT just submit. Caches are deleted in wait_for_batch
# once the batch reaches a terminal state (storage is billed for actual lifetime,
# usually << TTL); the TTL is the backstop if the run is cancelled/crashes.
CACHE_TTL_SECONDS = 6 * 3600  # 6h — matches the GHA job timeout (covers in-job batch processing)
CACHE_MIN_GROUP_SIZE = 2

# Safety valve: the live explicit-cache path is exercised on real Gemini Batch infra
# only (no offline test can hit it). If a run shows cache misbehaviour, set this False
# to fall back to full-price generation without a code change. The submit path is also
# fallback-safe per-request (a cache create/reference failure degrades to full price).
ENABLE_EXPLICIT_CACHE = True

# tracker-092 Phase 3: dedicated translator memory. Persists
# source→translation across runs so unchanged strings are never re-translated.
TRANSLATION_MEMORY_FILE = PROJECT_ROOT / "data" / "seo-intel" / "translation-memory.json"

# Field slug for the Summary field on each CMS collection. Webflow rich-text field
# slug — if it doesn't exist on a collection, the script auto-creates it (dry-run
# gated). The display name is "Summary". Used for the single-block blog summary AND
# (tracker-096) as the Content part of the 4-part structure on Courses/Housing.
SUMMARY_FIELD_SLUG = "summary"
SUMMARY_FIELD_DISPLAY_NAME = "Summary"

# tracker-096: 4-part Summary section (Tagline / Title / Paragraph / Content) on the
# Courses + Housing collections. CMS field slugs use TRIPLE hyphens — Webflow
# slugifies the display name "Summary - Tagline" → "summary---tagline" (verified
# live via get_collection_details 2026-05-20). The Content part reuses the existing
# RichText `summary` slug (renamed display → "Summary - Content"), so only the three
# plain-text parts are genuinely new field slugs.
SUMMARY_CONTENT_FIELD_SLUG = SUMMARY_FIELD_SLUG  # "summary" (RichText)
SUMMARY_TAGLINE_FIELD_SLUG = "summary---tagline"  # PlainText, singleLine
SUMMARY_TITLE_FIELD_SLUG = "summary---title"  # PlainText, singleLine
# tracker-098: the Paragraph field is now RichText holding TWO paragraphs that may
# carry inline internal links, and the CMS slug was renamed "summary---paragraph" →
# "summary---paragraphs" (display "Summary - Paragraphs"). RichText writes get HTML
# (<p>…</p> with inline <a>), not plain text.
SUMMARY_PARAGRAPH_FIELD_SLUG = "summary---paragraphs"  # RichText (two paragraphs + links)

# Static page summary element CSS selector. The single-block legacy element is
# id="summary". tracker-096: static landing pages now use FOUR elements whose ids use
# SINGLE hyphens (distinct from the CMS triple-hyphen slugs above — do not cross-wire).
STATIC_PAGE_SUMMARY_ELEMENT_ID = "summary"
STATIC_SUMMARY_TAGLINE_ID = "summary-tagline"
STATIC_SUMMARY_TITLE_ID = "summary-title"
STATIC_SUMMARY_PARAGRAPH_ID = "summary-paragraph"
STATIC_SUMMARY_CONTENT_ID = "summary-content"

# Audit thresholds. Score < 60 → REGENERATE; 60–80 → MANUAL_REVIEW; > 80 → KEEP.
AUDIT_REGENERATE_THRESHOLD = 60
AUDIT_MANUAL_REVIEW_THRESHOLD = 80

# Translation unit — paragraph (not sentence). Matches Weglot's natural unit.
TRANSLATION_UNIT = "paragraph"

# Per-request OUTPUT-token allowance for cost estimation (2026-05-23, audit C1 fix).
# Gemini bills THINKING tokens AS output; a Pro 4-part request spends ~3000-5000 thinking
# + ~1500-2500 visible (the BatchRequest.max_tokens ceiling is 16000 for this reason), so
# the old flat 800-token assumption under-projected Pro by ~6x — the root cause of the
# ~806 TRY billing burst. Keyed by (model_family, enable_thinking). CONSERVATIVE by design:
# over-estimating is the safe direction (it makes the cost gate stricter, not looser).
# Flash forces thinking_budget=0, so both flash keys are visible-output only.
OUTPUT_TOKEN_ESTIMATE = {
    ("pro", True): 5500,    # thinking-heavy 4-part landing / courses / housing generation
    ("pro", False): 1000,   # translation (thinking disabled) + any no-think Pro path
    ("flash", True): 1300,  # blog single-block (Flash thinking_budget=0; margin for visible)
    ("flash", False): 1300,
}
DEFAULT_OUTPUT_TOKEN_ESTIMATE = 1500

# Extended thinking budget for content generation (translation passes disable thinking).
THINKING_BUDGET_TOKENS = 1500

# Webflow API base.
WEBFLOW_API_BASE = "https://api.webflow.com/v2"
