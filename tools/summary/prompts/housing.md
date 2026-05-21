# Housing Adaptations

This is a Housing CMS item Summary (the new Housing collection, ID `69e8ab603e1e04f22496dd3c`). Apply on top of common.md.

## Content type

Housing detail pages list student accommodation options near CEL campuses. The CMS item has fields like title, description, included features, location proximity to the school.

## Word count target

650–900 words.

## Output structure (4-part)

Emit ONE Markdown document with EXACTLY these four parts, in this order — a `## ` Tagline line, a `### ` Title line, the Paragraph prose, then the Content starting at `#### `. The script splits the document into four separate page fields, so the shape must be exact:

- **Tagline** (the single `## ` line): 2–3 evocative, related words. Not a sentence, not a question, no trailing punctuation. An editorial kicker that makes the section feel designed, not an SEO block. Do NOT put the full primary keyword here.
- **Title** (the single `### ` line): a short, human section title — e.g. "What kind of student is this housing best for?". Place the PRIMARY KEYWORD here, phrased naturally.
- **Paragraph** (the prose between the Title and the first `#### `): TWO or THREE paragraphs (~150–260 words total), blank-line separated. The FIRST is the self-contained lead answer (primary keyword in the first 120 characters, open with a concrete fact). 1–2 contextually-relevant internal links MAY appear across the lead paragraphs (subject to the no-legacy-housing rule below). No headings, no lists.
- **Content** (everything from the first `#### ` onward): the depth layer. Open with an `#### ` H4 (a PAA-shaped sub-question: who it suits, daily-life context, transit/distance, what's included) and use `##### ` H5 only where needed. Place the remaining internal links here (subject to the no-legacy-housing rule below). Paragraphs only.

Hard rules: exactly ONE H2 (Tagline) + ONE H3 (Title), no H1, Content uses H4/H5 only (never another H2/H3); internal links may appear in the lead Paragraphs AND in the Content — NEVER in the Tagline or Title; no code fences, no preamble, output the Markdown only.

## CRITICAL — no outbound links to legacy housing

This housing Summary MUST NOT link to ANY URL whose path contains `/vc/`, `/sd/`, or `/sm/`. Those are the legacy per-city housing collections (Vancouver / San Diego / Los Angeles slugs), currently unpublished.

Acceptable link targets:
- Same locale's main `/housing` page (the housing hub)
- Same locale's main `/courses` or `/<course-slug>` page when the housing complements a specific course
- City landing pages (e.g., `/san-diego-ca/language-school`)

NO links to other housing items within this collection.

## Translation

This collection's Summary is NOT translated by the script. The English Summary lives on the item and Weglot's fallback serves it on locale URLs.

## EEAT

Less applicable than landing pages. Focus on facts from the CMS item: walking distance to campus, neighborhood character (only if in the source), what's included in the price.

## What this summary is NOT

- Not a marketing pitch
- Not a comparison of every available housing option
- Not a price list (the page already shows pricing)
