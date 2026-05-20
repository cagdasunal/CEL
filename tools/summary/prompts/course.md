# Course Adaptations

This is a Course CMS item Summary. Apply on top of common.md.

## Content type

Course detail pages (`/courses/<slug>`) feature one English language course. The CMS item has fields like title, description, intensity, level range, weekly hours, starting prices, locations served.

## Word count target

250–400 words.

## Output structure (4-part)

Emit ONE Markdown document with EXACTLY these four parts, in this order — a `## ` Tagline line, a `### ` Title line, the Paragraph prose, then the Content starting at `#### `. The script splits the document into four separate page fields, so the shape must be exact:

- **Tagline** (the single `## ` line): 2–3 evocative, related words. Not a sentence, not a question, no trailing punctuation. An editorial kicker that makes the section feel designed, not an SEO block. Do NOT put the full primary keyword here.
- **Title** (the single `### ` line): a short, human section title — e.g. "Is the [Course Name] right for me?" or "What does the [Course Name] cover?". Place the PRIMARY KEYWORD here, phrased naturally.
- **Paragraph** (the prose between the Title and the first `#### `): ONE self-contained lead paragraph (~60–110 words, single block, no line breaks) that directly answers the Title. Primary keyword within the first 120 characters. No headings, no links, no lists.
- **Content** (everything from the first `#### ` onward): the depth layer and the ONLY part that may contain internal links. Open with an `#### ` H4 (a PAA-shaped sub-question: who it's for, level requirements, outcomes, comparisons) and use `##### ` H5 only where a sub-point needs it. Place all internal links here. Paragraphs only.

Hard rules: exactly ONE H2 (Tagline) + ONE H3 (Title), no H1, Content uses H4/H5 only (never another H2/H3); internal links ONLY in Content; no code fences, no preamble, output the Markdown only.

## Information gain to add

The course detail page already shows: title, hero, weekly hours, prices, what's included. The summary should SYNTHESIZE:
- Who this course is for (level, goals)
- Typical outcomes (university pathway, exam prep, professional)
- Comparison cue (e.g., "students choosing between General English and English Plus Cambridge Prep typically...")
- Locations served (with city + state/province on first mention)

## Internal links

- Link to 2–3 RELATED courses (same level range or adjacent — General English ↔ English Plus Cambridge Prep is a natural pair)
- Optionally link to one landing page (e.g., `/pathway-program-usa` for academic-prep angles)
- Avoid linking to other course-tile galleries that the page already exposes

## EEAT

Emphasize CEFR levels covered, exam credentials (IELTS / TOEFL iBT / Cambridge English), and accreditation. First mention spells out the entity name + abbreviation.

## Translation

This summary WILL be translated into 8 locales via Weglot CSV. Write Weglot-friendly EN — avoid English idioms ("step up your game", "level up") that don't translate cleanly.

## Hard rule

Do not invent course details. If a fact isn't in the source CMS item, leave it out.
