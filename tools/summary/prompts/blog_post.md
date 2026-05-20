# Blog Post Adaptations

This is a blog post Summary. Apply on top of common.md.

## Content type — ORIGINAL per locale

Blog posts are **ORIGINAL per locale** (DE / FR / IT / KO / ES / PT / JA / AR / EN). Each post is original content authored in that locale, not a translation of an English original. **Write the summary in the SAME locale as the source post — do NOT translate from English.** The Summary you produce is the only summary that locale will have; there is no downstream translation pass for blog content (see `config.NATIVE_LANGUAGE_COLLECTIONS = ("blog",)`).

## Scope of this summary section

This summary is ADDED at the bottom of an existing blog post. The body of the post is the source content. Your summary:
- Synthesizes the post into 1–2 short paragraphs (200–300 words total)
- Adds a single H2 question + optional 1 H3
- Links to 2–3 sibling blog posts (same locale, same category) AND 1 relevant landing page (same locale)
- Adds genuine information-gain — a summary, an extra angle, a "what to do next" — not a duplicate of the post's opening

## Output structure (single-block)

Blog summaries use the SINGLE-BLOCK structure — NOT the 4-part Tagline/Title/Paragraph/Content layout (that one is for courses, housing, and landing pages). Emit one Markdown document:

- Exactly ONE `## H2` — the question the post answers, framed as a search query in the post's locale. Same lexical core as the post title but a different syntactic frame.
- 1–2 paragraphs immediately under the H2; the first leads with a direct answer.
- Optional: ONE `### H3` with a long-tail variant question + 1 short paragraph.
- **Primary keyword** in the H2 AND in the first 120 characters of the first paragraph AND in the H3 when present.

Return only the rendered Markdown (one `## H2`, optional `### H3`, plain paragraphs). No code fences, no preamble, no trailing commentary.

## Word count target

200–300 words. Shorter is acceptable when the post is short.

## Internal links allowed

YES — link to sibling blog posts in the SAME locale AND to landing pages in the same locale. Never cross-locale. Use the link inventory subset filtered by `locale=<post_locale>`.

## EEAT signals

Lower pressure than landing pages. Optional. If included, draw from the post body, not from CEL's institutional credentials.

## Voice

Native to the post's locale. Do not write English prose and "translate" — write directly in the locale's idiomatic register. (The locale rule file specifies tone.)

## What this summary is NOT

- Not a republishing of the post's intro
- Not a "thanks for reading" wrap-up
- Not a generic CTA ("contact us today")
- Not a keyword-stuffed paragraph aimed at a specific search term
