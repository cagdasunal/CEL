# Arabic visual corrections — https://www.englishcollege.com/ar/vancouver

_generated 2026-05-24T19:59:12Z · 4 rule(s) applied of 4 suggested_

- `.hero_title, .hero_sub, .section-title, .section-tagline, .small-title, .text-st` — English layouts frequently rely on letter-spacing for headings and uppercase UI elements, but applying letter-spacing to Arabic breaks the cursive connections between characters and makes text illegible.
- `p, .page_content, .hero_sub, .faq-question-text, .review-card_quote, .body-intro` — The Cairo font (and Arabic script generally) features taller ascenders and descenders than Latin fonts. Standard English line-heights cause the lines to look cramped or overlap in Arabic.
- `.breadcrumb-sep` — The breadcrumb separator chevron is pointing right (>), implying a left-to-right hierarchy. It needs to be mirrored to point left (<) to match the RTL reading flow.
- `.accred_accred-desc, .accred_regulatory-text, .photo-card_desc, .info-card-list_` — In the accreditations section, mixed LTR/RTL text like 'رقم: DLI...' causes the colon to hang on the far left edge instead of adjacent to the Arabic word. Plaintext bidi isolation fixes punctuation placement in mixed-direction strings.
