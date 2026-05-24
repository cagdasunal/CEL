# Arabic visual corrections — https://www.englishcollege.com/ar/vancouver

_generated 2026-05-24T21:30:49Z · 8 rule(s) applied of 8 suggested_

- **[major]** `.breadcrumb-sep` — The breadcrumb chevron separator is pointing right. It needs to point left (<) to match the RTL reading order.
- **[critical]** [native-review] `h1, h2, h3, h4, h5, h6, p, li, a, .text-style-allcaps, .hero_title, .hero_sub, .` — Arabic is a cursive script; retaining English letter-spacing severs the joins between characters and makes the text appear broken and illegible. Uppercase styling is also invalid for Arabic.
- **[major]** `body, p, .hero_sub, .faq-question-text, .campus_bento-card-desc, .cm-textonly_de` — Arabic fonts (especially Cairo) have taller glyphs and prominent diacritics. Latin line-heights are too tight and will cause vertical clipping and visual overlap.
- **[critical]** `.course-slider_arrow, .card-slider_arrow, .accom-slider_arrow, .act-slider_arrow` — Directional navigation arrows for sliders were physically swapped to the correct sides by rtlcss, but the arrow graphics themselves must be horizontally mirrored to point in the correct RTL logical direction (left for 'next').
- **[major]** `.text-link svg, .course-card_link svg, .stoc_link svg, .stoc_link-blog svg, .inl` — Inline text link arrows (like 'Read More' or 'Go') currently point right and must point left to indicate forward progression in Arabic.
- **[major]** `.card-slider_progress-fill, .course-slider_progress-fill, .accom-slider_progress` — Slider progress bars animated via JavaScript 'scaleX' will fill backward (from the left) unless their CSS transform-origin is anchored to the right side.
- **[major]** [native-review] `.compare_number, .offer-bento_price-tag, .count_days, .count_hours, .count_minut` — Numeric ranges (e.g., 15-17) and mixed currency string formats (like C$3,604) easily scramble under global bidi algorithms. Isolating them preserves format integrity while flowing naturally inside the RTL layout.
- **[minor]** `.review-card_rating-stars, .reviews-hero_stars` — Star ratings should maintain a left-to-right fill direction internally to preserve standard international visual semantics.
