# Arabic RTL CSS engine

Auto-generates `docs/scripts/cel-arabic.css` — a scoped (`html[lang="ar"]`) RTL
override for the Arabic version of englishcollege.com (Webflow + Weglot). Served at
`https://cel.englishcollege.com/scripts/cel-arabic.css`.

## What it does
1. Fetches `https://cel.englishcollege.com/sitemap.xml`, keeps the `/ar/` URLs.
2. Fetches those pages and collects the Webflow CDN CSS `<link>` URLs
   (`cdn.prod.website-files.com/*.css`). Vendor CSS (Swiper) is ignored — Swiper
   does its own RTL when `dir="rtl"` is set.
3. Fingerprints that URL set (the filenames are content-hashed, so the fingerprint
   changes only when the CSS actually changes). The fingerprint is stored in the
   output file's header comment — **there is no separate state file**.
4. If the fingerprint matches the deployed file → exits, no rewrite.
5. On change: downloads + combines the CSS, **de-duplicates identical rules** (per-page
   CSS repeats shared components across every page's opt file — dedup cut a recent run
   from 4.3 MB / 11k rules to 346 KB / 2k rules), mirrors it with `npx rtlcss`, then
   post-processes into a **diff + reset** override (see `generator.py`), prepends the
   hand-authored `arabic_static.css` (self-hosted Arabic font + `direction:rtl` +
   typography + component RTL corrections), and writes the single minified result with a
   fresh fingerprint header.

**One served file.** Everything above is concatenated into ONE `cel-arabic.css`; nothing
per-page is ever served.

## Why diff+reset (not the full rtlcss mirror)
rtlcss is built to *replace* the LTR stylesheet. We can only *add* CSS on `/ar/`
pages, so for a rule where rtlcss renames a one-sided property
(`margin-left` → `margin-right`) the override must also reset the old side
(`margin-left:0`), or the base rule's value still applies and you get margin on
both sides. `generator.diff_rule` handles this.

## Fonts (self-hosted)
The Arabic webfont (**Cairo**) is self-hosted, not loaded from Google Fonts — no
third-party request, no `@import`. The woff2 files live in `docs/assets/fonts/`
(`cairo-arabic.woff2`, `cairo-latin.woff2`, `cairo-latin-ext.woff2` — one variable file
per subset, `font-weight: 400 700`), served from
`https://cel.englishcollege.com/assets/fonts/`. The `@font-face` blocks (with Google's
`unicode-range` subsetting preserved) live in `arabic_static.css`. To refresh or change
the font, re-download the woff2 + update the `@font-face` blocks; the files are committed
to git and published via GitHub Pages like any other asset.

**Applying the Arabic font (auto):** the site's Latin-only display font (Cameraobscura)
would render Arabic as tofu. `generator.font_overrides()` scans the source CSS for every
selector that uses Cameraobscura — both directly (`font-family: Cameraobscura,…`) and via
CSS variables (`--*-font-family: Cameraobscura,…`, used by `h1–h6`) — and emits scoped
`html[lang="ar"] …{font-family:'Cairo',…;letter-spacing:normal;text-transform:none}`
overrides (and redefines the variables on `html[lang="ar"]`). This auto-covers current
*and* future Cameraobscura usage, so new display classes don't silently break Arabic.
font-family isn't directional, so rtlcss never touches it — this is where the Arabic font
gets applied. To target a different display font, change `DISPLAY_FONT_NEEDLE` in
`generator.py`.

## Component corrections (hand-authored, in `arabic_static.css`)
The mechanical flip + font swap gets the *bulk* right but can't infer from CSS alone what a
page actually LOOKS like in RTL — icon/glyph direction, JS-driven transforms, bidi-sensitive
numbers, and the few cases where a flipped value is semantically wrong. Those corrections are
authored **by hand** in `arabic_static.css` and verified by inspecting the live `/ar/` pages
locally (headless-browser computed-style + screenshot checks across the sitemap). Current set:
- breadcrumb & inline-link arrow glyphs mirrored (`scaleX(-1)`)
- slider arrows mirrored; slider progress-fill `transform-origin:right`
- numbers / prices / countdowns isolated LTR (`unicode-bidi:plaintext;direction:ltr`)
- star ratings kept LTR (international convention)
- typography: `letter-spacing:normal` + `text-transform:none` (Arabic is cursive; uppercase
  is meaningless) and a looser `line-height` (Cairo has tall glyphs/diacritics)
- nav: offers-dot mirrored to the top-left; dropdown-panel right-aligned and its links
  right-aligned via `justify-content:flex-start` (the links are `display:flex` — `text-align`
  is a no-op on flex-item position); `vs-toronto` comparison values right-aligned

Each is scoped `html[lang="ar"]` so it wins on specificity without `!important`. When rtlcss
flips a base rule that was **already RTL-correct** (e.g. `.navbar_dropdown-list` panel position,
`.navbar_dropdown-link` text-align, `.w-dropdown-toggle` framework padding), the wrong flip is
dropped via `exclusions.py` rather than overridden — see that file's docstring for each finding.

**Verification gotcha:** check the *rendered geometry* (element position / screenshot), not just
the computed property — `text-align:right` can compute "right" yet do nothing on a flex container,
and injecting test CSS as the last sheet hides cascade-order losses. Inspect the real page.

## Run
```bash
# from the repo root
python -m tools.arabic_rtl.build           # regenerate cel-arabic.css iff source changed
python -m tools.arabic_rtl.build --force   # always regenerate
python -m pytest tools/arabic_rtl/tests/   # unit tests
```
The engine is stdlib-only (`rtlcss` via `npx`, pinned `rtlcss@4.3.0`).

## Running it (manual — no auto-schedule)
Regenerate on demand, two ways:
- **Locally:** `python -m tools.arabic_rtl.build --force`, then commit + push
  `docs/scripts/cel-arabic.css`. GitHub Pages serves it within ~10 min.
- **GitHub Actions:** trigger `.github/workflows/arabic-css.yml` from the Actions tab
  (`workflow_dispatch`) — it regenerates + commits `cel-arabic.css` only when the source
  Webflow CSS changed (rebase-retry push, `push-to-main` group).

The hourly cron is **disabled** for now (commented out in the workflow). To restore
auto-refresh, re-add the `schedule:` trigger.

## Activating it on the live site (manual, one-time)
The engine only produces the file. To use it, add this to **Webflow → Site Settings
→ Custom Code → Head Code** — it loads the stylesheet and sets `dir="rtl"` only on
Arabic pages (zero bytes on the other 8 languages):
```html
<script>(function(){var a=document.documentElement.lang==='ar'||location.pathname==='/ar'||location.pathname.indexOf('/ar/')===0;if(!a)return;document.documentElement.setAttribute('dir','rtl');var l=document.createElement('link');l.rel='stylesheet';l.href='https://cel.englishcollege.com/scripts/cel-arabic.css?v=1';document.head.appendChild(l);})();</script>
```

**Also required (one-time, critical).** The site's global Head Code contained a legacy
scrollbar/transition snippet with `* { direction: ltr !important; }`. That `!important`
universal rule overrode the RTL `direction` on **every** element, so the layout never flipped
(only `text-align` did — the "half-flipped" look). It must be scoped to exclude Arabic:
```css
html:not([lang="ar"]) * { direction: ltr !important; }
```
With that scoped, `dir="rtl"` drives the full flip natively (navbar, grid columns, flex order,
Swiper). If another RTL language is added later, extend the exclusion (`:not([lang="he"])`, …).

## Known limitations
- **`@keyframes` are not auto-flipped** (they can't be scoped with a selector prefix).
  The build prints a WARNING with the count; handle directional slide animations by
  hand in `arabic_static.css`.
- **Cross-page cascade (low-impact, by design).** The override is built from *all* `/ar/`
  pages' CSS combined, but each page's base CSS is page-specific. If two pages' per-page
  opt files defined the *same selector* with *different* directional values, the override
  contains both and the one sorted last wins on every Arabic page. Rare in practice (opt
  files seldom redefine shared selectors with conflicting directional values); the proper
  fix (per-page override files) is intentionally out of scope for one combined file.
- **Each run fetches every `/ar/` page** (~46) to compute the fingerprint, even when
  nothing changed. Necessary to catch per-page CSS changes; load is negligible. (No longer
  hourly — runs only when invoked manually.)
- **Non-flip exclusions** (`exclusions.py`) start empty. rtlcss flips everything; if live
  validation shows a rule that shouldn't have flipped (a logo, a media-play control), add
  a substring of its selector to `EXCLUDE_SUBSTRINGS`.
- Deeper RTL polish (icon/carousel direction, spacing, bidi, alignment) is hand-authored in
  `arabic_static.css` and verified against the live `/ar/` pages (computed-style + screenshot
  checks across the sitemap). After any Webflow redesign, re-inspect the affected pages and
  update the static corrections. Corrections are component-level (scoped `html[lang="ar"]`),
  so one rule covers every Arabic page that uses that component.
