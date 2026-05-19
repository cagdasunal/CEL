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

# Batches API — sanity ceiling, well below the API max (~10,000).
BATCH_SIZE_TARGET = 500

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
)

# llms.txt — internal-linking source of truth (NOT sitemap.xml).
LLMS_TXT_URL = "https://cel.englishcollege.com/llms.txt"

# Filesystem layout.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEGLOT_IMPORTS_DIR = PROJECT_ROOT / "docs" / "admin" / "weglot-imports"
DRYRUN_DIR = PROJECT_ROOT / "data" / "seo-intel" / "summary-dryrun"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Field slug for the Summary field on each CMS collection. Webflow rich-text field
# slug — if it doesn't exist on a collection, the script auto-creates it (dry-run
# gated). The display name is "Summary".
SUMMARY_FIELD_SLUG = "summary"
SUMMARY_FIELD_DISPLAY_NAME = "Summary"

# Static page summary element CSS selector. The script targets the element with
# id="summary" via Webflow Designer API. If the element doesn't exist, dry-run
# reports it; the script does NOT auto-create.
STATIC_PAGE_SUMMARY_ELEMENT_ID = "summary"

# Audit thresholds. Score < 60 → REGENERATE; 60–80 → MANUAL_REVIEW; > 80 → KEEP.
AUDIT_REGENERATE_THRESHOLD = 60
AUDIT_MANUAL_REVIEW_THRESHOLD = 80

# Translation unit — paragraph (not sentence). Matches Weglot's natural unit.
TRANSLATION_UNIT = "paragraph"

# Extended thinking budget for content generation (translation passes disable thinking).
THINKING_BUDGET_TOKENS = 1500

# Webflow API base.
WEBFLOW_API_BASE = "https://api.webflow.com/v2"
