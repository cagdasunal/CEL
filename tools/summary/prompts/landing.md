# Static Landing Page Adaptations

This is a static landing page Summary. Apply on top of common.md.

## Content type

Static landing pages live at fixed URLs (e.g., `/courses`, `/san-diego-ca/language-school`, `/pathway-program-usa`). Each page has its own H1, structured sections, and existing visible content.

## Word count target

By page type:
- `/` (home): 400–600
- City landing (`/san-diego-ca/...`, `/los-angeles-ca/...`): 400–600
- Country landing (`/learn-english-usa`, `/learn-english-canada`): 400–700
- `/courses` listing: 400–600
- `/housing` hub: 350–500
- `/summer-camp-san-diego`: 350–500
- `/pathway-program-usa` + `/pathway/*` (4 sub-pages): 400–600 each

## Structure

- 1 H2 (the question the page answers, in the search-query phrasing)
- 3–5 H3s answering PAA-shaped sub-questions
- Paragraphs only

## Information gain

Each landing page already has hero + cards + visible sections. The summary section synthesizes:
- What CEL specifically offers at this location/program (vs. competitors)
- Who the page audience is and how to evaluate fit
- Concrete outcomes (alumni paths, accreditation bodies, partnership universities)
- Operational facts (class size, weekly hours, intake schedule) ONLY if present in the source

## Internal links

YES — landing pages MAY link to blog posts in the same locale (rule reversed from prior pass). Pick 1–2 relevant blog posts plus 2–3 related landing pages. Anchor text diversity rules apply.

Excluded targets:
- `/vc/*`, `/sd/*`, `/sm/*` housing slugs (unpublished collections)
- The page itself (no self-links)

## Translation

This summary WILL be translated into 8 locales. Translation will:
- Look up equivalent URLs in the target locale via llms.txt
- If a linked blog post has no target-locale equivalent: REMOVE the link entirely (do not link cross-language)
- Translate prose with locale-native conventions (per the locale rule file)

## EEAT

Landing pages carry the highest indexing pressure when in `crawled_not_indexed`. Pack at least 2 EEAT signals into the first 150 words: years operating + accreditation, OR alumni count + university partnerships, OR certified teachers + class size differentiator.

## Voice

Direct. Lead with the answer. The first sentence under the H2 must contain the primary keyword + a concrete fact (number, year, named entity) within 40–60 words.

## What this summary is NOT

- Not a hero re-statement
- Not a bullet list of features (paragraphs only)
- Not a contact-us pitch
