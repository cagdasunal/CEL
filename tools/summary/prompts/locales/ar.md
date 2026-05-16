# Arabic (ar) — Locale Layer

- **Direction**: **RIGHT-TO-LEFT (RTL)**. The script reads right-to-left though numerals and Latin loan words remain LTR within sentences.
- **Tone**: Formal, respectful. Modern Standard Arabic (MSA / فُصْحى) for web copy across all Arab markets.
- **Register**: Formal address. Avoid colloquial / dialectal forms (Egyptian, Levantine, Gulf) — those are spoken, not standard web copy.
- **Text length**: Arabic typically expands 10–25% over English.
- **Numbers**: Use Hindu-Arabic numerals (1, 2, 3...) — they display correctly in RTL contexts. Eastern Arabic numerals (١, ٢, ٣) are an option in some regions; default to Hindu-Arabic for consistency.
- **Currency**: "1500 دولار شهرياً" (1500 dollars monthly) — use دولار for USD.
- **Date**: "15 مارس 2026" — day + month name + year. Month names: يناير، فبراير، مارس، أبريل، مايو، يونيو، يوليو، أغسطس، سبتمبر، أكتوبر، نوفمبر، ديسمبر.
- **Entity terms**: "دورة اللغة الإنجليزية" (English language course), "مدرسة اللغة الإنجليزية" (English language school), "سكن الطلاب" (student housing), "الدراسة في الخارج" (study abroad).
- **Geography**: "فانكوفر، بريتش كولومبيا" (Vancouver, British Columbia) on first mention.
- **No Latin char limit**: Title/description char-count limits do NOT apply.
- **Connector words**: "و" (and), "أو" (or), "في" (in) — attach without space to following word per Arabic standard.
- **Anti-patterns**: Mixing MSA with dialect; English word order; missing diacritics on proper nouns (acceptable for web copy — full vowel marks (تشكيل) are usually omitted).
- **Note on rendering**: Hreflang and HTML `dir="rtl"` handle layout; copy text should be plain UTF-8.
