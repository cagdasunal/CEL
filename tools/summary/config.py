"""Config — locale codes, collection IDs, model, exclusions, paths.

Single source of truth for IDs and rules. No business logic — pure constants.
Update MODEL_ID when a more capable Gemini production model ships.
"""
from __future__ import annotations

from pathlib import Path

# Google Gemini 3.1 Pro Preview — top-tier production model on Artificial
# Analysis Intelligence Index (tied with Opus 4.7 at 57) at ~7× lower Batch
# pricing. Migrated from claude-opus-4-7 in tracker-091 (2026-05-19 evening).
# Pricing reference: https://ai.google.dev/gemini-api/docs/pricing
MODEL_ID = "gemini-3.1-pro-preview"

# Defensive cost cap. Batch run aborts with an error if estimated cost exceeds this.
MAX_BATCH_COST_USD = 100

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
SUMMARY_PROMPT_VERSION = "2026-05-21-t096"
SUMMARY_STATE_FILE = PROJECT_ROOT / "data" / "seo-intel" / "summary-state.json"

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
SUMMARY_PARAGRAPH_FIELD_SLUG = "summary---paragraph"  # PlainText, singleLine

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

# Extended thinking budget for content generation (translation passes disable thinking).
THINKING_BUDGET_TOKENS = 1500

# Webflow API base.
WEBFLOW_API_BASE = "https://api.webflow.com/v2"
