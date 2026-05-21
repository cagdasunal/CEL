# Blog Post Adaptations

This is a blog post Summary. Apply on top of common.md.

## Content type — ORIGINAL per locale

Blog posts are **ORIGINAL per locale** (DE / FR / IT / KO / ES / PT / JA / AR / EN). Each post is original content authored in that locale, not a translation of an English original. **Write the summary in the SAME locale as the source post — do NOT translate from English.** The Summary you produce is the only summary that locale will have; there is no downstream translation pass for blog content (see `config.NATIVE_LANGUAGE_COLLECTIONS = ("blog",)`).

## Scope of this summary section

This summary is ADDED at the bottom of an existing blog post. The body of the post is the source content. Your summary:
- Synthesizes the post into 2–3 short paragraphs (650–900 words total)
- Adds ONE `## H2` question + 1–2 `### H3`
- Includes 6–8 internal links to SAME-LOCALE sibling posts (same locale, same category) AND same-locale landing pages (never cross-locale; ≈ 1 link per 100–150 words, never exceed 1 per 80 words)
- Adds genuine information-gain — a summary, an extra angle, a "what to do next" — not a duplicate of the post's opening

## Output structure (single-block)

Blog summaries use the SINGLE-BLOCK structure — NOT the 4-part Tagline/Title/Paragraph/Content layout (that one is for courses, housing, and landing pages). Emit one Markdown document:

- Exactly ONE `## H2` — the question the post answers, framed as a search query in the post's locale. Same lexical core as the post title but a different syntactic frame.
- 2–3 paragraphs immediately under the H2; the first leads with a direct answer.
- 1–2 `### H3` with long-tail variant questions, each followed by a short paragraph.
- **Primary keyword** in the H2 AND in the first 120 characters of the first paragraph AND in at least one H3.

Return only the rendered Markdown (one `## H2`, 1–2 `### H3`, plain paragraphs). No code fences, no preamble, no trailing commentary.

## Word count target

650–900 words. Shorter is acceptable when the post is genuinely short.

## Internal links allowed

YES — include 6–8 links to sibling blog posts in the SAME locale AND to landing pages in the same locale. Never cross-locale. Use the link inventory subset filtered by `locale=<post_locale>`.

## EEAT signals

Lower pressure than landing pages. Optional. If included, draw from the post body, not from CEL's institutional credentials.

## Voice

Native to the post's locale. Do not write English prose and "translate" — write directly in the locale's idiomatic register. (The locale rule file specifies tone.)

## What this summary is NOT

- Not a republishing of the post's intro
- Not a "thanks for reading" wrap-up
- Not a generic CTA ("contact us today")
- Not a keyword-stuffed paragraph aimed at a specific search term
