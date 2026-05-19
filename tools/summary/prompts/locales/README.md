# Locale Layer Files — Canonical Dimensions

Each `<locale>.md` file in this directory contains the locale-specific tone/idiom/conventions layer for the summary generation prompt. To prevent asymmetric coverage, every locale file should address the following dimensions (skip a dimension only if it does not apply to that locale, e.g., RTL doesn't apply to LTR scripts).

## Canonical dimensions

1. **Direction (LTR / RTL)** — for non-Latin scripts especially
2. **Tone + register** — formal, casual, professional; "Sie/Lei/usted" vs "du/tu/tú"
3. **Text expansion factor** — % longer or shorter than English (DE +25%, JA −10%, etc.)
4. **Punctuation conventions** — French space-before-colon, Spanish inverted marks, Japanese full-width
5. **Number formatting** — thousand separator, decimal separator
6. **Currency formatting** — symbol placement, "USD" vs "$" usage
7. **Date format** — DD.MM.YYYY (DE), JJ/MM/AAAA (FR), 2026年3月15日 (JA)
8. **Entity terminology** — locale-native terms for "English course", "language school", "student housing", "study abroad"
9. **Geography on first mention** — locale-native form of city + state/province
10. **Accents/diacritics or script notes** — critical for FR, ES, IT, PT, AR, KO, JA
11. **Anti-patterns** — common machine-translation tells to avoid (anglicisms, missing accents, wrong gender agreement)
12. **Char-limit applicability** — note "no Latin char limit" for KO, JA, AR (Google measures pixel width on non-Latin scripts)
13. **AI-tell banlist** *(new 2026-05-19, tracker-087)* — per-language list of 15-35 words/phrases that are AI-generated tells in that language. Sourced from 2026 detector word-lists (Walter Writes, HumanizeThisAI, ContentConsultants, Digitad, Hastewire, Rebrandb, AI総合研究所, Harmash, etc.).
14. **Syntactic AI-tells** *(new 2026-05-19)* — 5-7 grammar/structure patterns that mark machine-generated text in this locale (e.g. tri-adjective + em-dash; uniform sentence length; English-influenced word order).
15. **ESL industry glossary** *(new 2026-05-19, tracker-087)* — per-language list of 18-25 native ESL / study-abroad industry terms that an English-school summary should naturally use. Sourced from native-language ESL marketing sites (ESL.de, Mundo Joven, EF Italia, EF Brasil, Studydestiny, 留学ジャーナル, Language International).
16. **Native-voice examples** *(new 2026-05-19)* — one paragraph "❌ AI-feeling" + one paragraph "✅ human-feeling" example per locale, anchored in CEL Vancouver context for consistency.

## Coverage status (updated 2026-05-19, tracker-087 F-7)

| Locale | Direction | Tone | Expansion | Punctuation | Numbers | Currency | Date | Entities | Geo | Accents/Script | Anti-patterns | Char-limit | **AI-tells** | **ESL glossary** |
|--------|-----------|------|-----------|-------------|---------|----------|------|----------|-----|----------------|---------------|------------|--------------|------------------|
| en | LTR | ✓ | (baseline) | ✓ | ✓ | ✓ | ✓ | (n/a) | (n/a) | (n/a) | ✓ | (n/a) | 35 items | 22 terms |
| de | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (Latin) | ✓ | (n/a) | 19 items | 24 terms |
| fr | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) | 19 items | 21 terms |
| es | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) | 25 items | 21 terms |
| it | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) | 23 items | 21 terms |
| pt | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) | 22 items | 21 terms |
| ko | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 19 items* | 20 terms |
| ja | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 19 items* | 22 terms |
| ar | **RTL** | ✓ | ✓ | (Arabic) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 21 items* | 21 terms |

\* Coverage caveats noted in individual locale files: KO/JA AI-tell research is moderate; AR is the weakest of the nine. Banlists should be expanded post-2026 as native-language detector research accumulates.

All 9 locales cover all 16 applicable dimensions. Audit-086 M-3 (locale asymmetry) verified closed; tracker-087 F-7 (locale prompts thin) closed by 2026-05-19 expansion from 10-15 lines → 54-69 lines per locale with AI-tell banlist + ESL glossary added.

## Adding a new locale

1. Create `<code>.md` following the structure of an existing locale file (e.g. `de.md` for Latin/LTR or `ja.md` for non-Latin).
2. Add the code to `config.LOCALES` in `tools/summary/config.py`.
3. Add the code to `tools.weglot.csv_export.TARGET_LANGUAGES` if translation is intended.
4. Add a column to this README's coverage table.
5. Run a dry-run to confirm the prompt builder loads the new file.
