# Static Landing Page Adaptations

This is a static landing page Summary. Apply on top of common.md.

## Content type

Static landing pages live at fixed URLs (e.g., `/courses`, `/san-diego-ca/language-school`, `/pathway-program-usa`). Each page has its own H1, structured sections, and existing visible content.

## Word count target

By page type:
- `/` (home): 750–1050
- City landing (`/san-diego-ca/...`, `/los-angeles-ca/...`): 750–1050
- Country landing (`/learn-english-usa`, `/learn-english-canada`): 800–1100
- `/courses` listing: 750–1050
- `/housing` hub: 650–900
- `/summer-camp-san-diego`: 650–900
- `/pathway-program-usa` + `/pathway/*` (4 sub-pages): 700–1000 each

## Output structure (4-part)

Emit ONE Markdown document with EXACTLY these four parts, in this order — a `## ` Tagline line, a `### ` Title line, the Paragraph prose, then the Content starting at `#### `. The script splits the document into four separate page fields, so the shape must be exact:

- **Tagline** (the single `## ` line): 2–3 evocative, related words. Not a sentence, not a question, no trailing punctuation. An editorial kicker that makes the section feel designed, not an SEO block. Do NOT put the full primary keyword here.
- **Title** (the single `### ` line): a short, human section title — the question the page answers, in search-query phrasing. Place the PRIMARY KEYWORD here, phrased naturally.
- **Paragraph** (the prose between the Title and the first `#### `): TWO or THREE paragraphs (~150–260 words total), blank-line separated. The FIRST is the self-contained lead answer (primary keyword in the first 120 characters; open with a concrete fact — number, year, named entity). 1–2 contextually-relevant internal links MAY appear across the lead paragraphs. No headings, no lists.
- **Content** (everything from the first `#### ` onward): the depth layer. Open with an `#### ` H4 (a PAA-shaped sub-question) and use `##### ` H5 only where needed; 3–5 H4 sub-questions is typical for a landing page. Place the remaining internal links here. Paragraphs only.

Hard rules: exactly ONE H2 (Tagline) + ONE H3 (Title), no H1, Content uses H4/H5 only (never another H2/H3); internal links may appear in the lead Paragraphs AND in the Content — NEVER in the Tagline or Title; no code fences, no preamble, output the Markdown only.

## Information gain

Each landing page already has hero + cards + visible sections. The summary section synthesizes:
- What CEL specifically offers at this location/program (vs. competitors)
- Who the page audience is and how to evaluate fit
- Concrete outcomes (alumni paths, accreditation bodies, partnership universities)
- Operational facts (class size, weekly hours, intake schedule) ONLY if present in the source

## Internal links

YES — landing pages MAY link to blog posts in the same locale (rule reversed from prior pass). Aim for 6–8 meaningful links total, distributed across the lead Paragraphs and the Content (≈ 1 link per 100–150 words; never exceed 1 per 80 words): a mix of relevant blog posts and related landing pages. Anchor text diversity rules apply.

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

Direct. Lead with the answer. The Paragraph's first sentence must contain the primary keyword + a concrete fact (number, year, named entity) within 40–60 words.

## What this summary is NOT

- Not a hero re-statement
- Not a bullet list of features (paragraphs only)
- Not a contact-us pitch
