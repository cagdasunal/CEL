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

## Coverage status (2026-05-16)

| Locale | Direction | Tone | Expansion | Punctuation | Numbers | Currency | Date | Entities | Geo | Accents/Script | Anti-patterns | Char-limit |
|--------|-----------|------|-----------|-------------|---------|----------|------|----------|-----|----------------|---------------|------------|
| en | LTR | ✓ | (baseline) | ✓ | ✓ | ✓ | ✓ | (n/a) | (n/a) | (n/a) | ✓ | (n/a) |
| de | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (Latin) | ✓ | (n/a) |
| fr | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) |
| es | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) |
| it | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) |
| pt | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (n/a) |
| ko | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (implicit) | ✓ | ✓ | ✓ |
| ja | LTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | (implicit) | ✓ | ✓ | ✓ |
| ar | **RTL** | ✓ | ✓ | (Arabic) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

All 9 locales cover all applicable dimensions. Asymmetry confirmed minimal as of 2026-05-16; audit-086 M-3 finding verified closed.

## Adding a new locale

1. Create `<code>.md` following the structure of an existing locale file (e.g. `de.md` for Latin/LTR or `ja.md` for non-Latin).
2. Add the code to `config.LOCALES` in `tools/summary/config.py`.
3. Add the code to `tools.weglot.csv_export.TARGET_LANGUAGES` if translation is intended.
4. Add a column to this README's coverage table.
5. Run a dry-run to confirm the prompt builder loads the new file.
