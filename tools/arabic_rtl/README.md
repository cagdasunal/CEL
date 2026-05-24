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
   typography incl. headings), appends the **Gemini visual-correction layer** (see "Visual
   pass" below), and writes the single minified result with a fresh fingerprint header.

**One served file.** Everything above is concatenated into ONE `cel-arabic.css`. The
per-page `data/arabic-visual/*.css` files are intermediate Gemini output — they are merged
into `cel-arabic.css`; nothing per-page is ever served.

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

## Visual pass (Gemini 3.1 Pro vision)
The mechanical flip + font swap gets the *bulk* right but can't judge how a page actually
LOOKS in RTL. `tools/arabic_rtl/visual.py` adds a vision layer: it screenshots the live
`/ar/` page (Playwright headless Chromium — RTL + Cairo already applied), sends the
screenshot + the page's real CSS class names to **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`)
with an Arabic-UX prompt (`prompts/visual_system.md`), and gets back corrective CSS.

Every returned rule is **validated** before use: it must target a real class on the page,
it gets `html[lang="ar"]`-scoped, and it's rejected if it contains `@import` / an external
`url()` / `javascript:` / a `{}<>` breakout. Validated corrections are written to
`data/arabic-visual/<slug>.css` (+ a `<slug>.report.md` explaining each); `build.py` folds
them all into the one `cel-arabic.css`.

**Smart cadence (cost control).** A page is screenshotted + sent to Gemini only when it has
**never been analyzed, OR its CSS changed AND it hasn't been analyzed in ≥ 7 days**
(`data/arabic-visual/state.json` tracks each page's `css_hash` + `analyzed_at`). First run
covers all pages once; thereafter only changed pages, at most weekly. Needs `GEMINI_API_KEY`
(env / `.env` / GitHub secret) and the `google-genai` + `playwright` deps.

## Run
```bash
# from the repo root
python -m tools.arabic_rtl.build           # regenerate cel-arabic.css iff source changed
python -m tools.arabic_rtl.build --force   # always regenerate
python -m tools.arabic_rtl.visual          # Gemini visual pass on all ELIGIBLE /ar/ pages
python -m tools.arabic_rtl.visual --only /ar/vancouver --force --limit 1  # one page (smoke)
python -m tools.arabic_rtl.visual --dry-run   # show eligibility only; no screenshots/Gemini
python -m pytest tools/arabic_rtl/tests/   # unit tests
```
The build engine is stdlib-only (`rtlcss` via `npx`, pinned `rtlcss@4.3.0`); the visual pass
adds `google-genai` + `playwright` (lazy-imported, so the build engine still runs without them).

## Automation
- `.github/workflows/arabic-css.yml` — **hourly** (`23 * * * *`): regenerates + commits
  `cel-arabic.css` only when the source CSS or the gemini layer changed (rebase-retry push,
  `push-to-main` group). GitHub Pages serves it within ~10 min.
- `.github/workflows/arabic-visual.yml` — **weekly** (Mon 05:00 UTC) + manual dispatch: runs
  the Gemini visual pass on eligible pages, reassembles, commits the corrections + state, and
  uploads the screenshots as a CI artifact for review.

## Activating it on the live site (manual, one-time)
The engine only produces the file. To use it, add this to **Webflow → Site Settings
→ Custom Code → Head Code** — it loads the stylesheet and sets `dir="rtl"` only on
Arabic pages (zero bytes on the other 8 languages):
```html
<script>(function(){var a=document.documentElement.lang==='ar'||location.pathname==='/ar'||location.pathname.indexOf('/ar/')===0;if(!a)return;document.documentElement.setAttribute('dir','rtl');var l=document.createElement('link');l.rel='stylesheet';l.href='https://cel.englishcollege.com/scripts/cel-arabic.css?v=1';document.head.appendChild(l);})();</script>
```

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
- **Hourly run fetches every `/ar/` page** (~46) to compute the fingerprint, even when
  nothing changed (~1,100 lightweight GETs/day). Necessary to catch per-page CSS changes;
  load is negligible. Could be lightened later by short-circuiting on the shared file's hash.
- **Non-flip exclusions** (`exclusions.py`) start empty. rtlcss flips everything; if live
  validation shows a rule that shouldn't have flipped (a logo, a media-play control), add
  a substring of its selector to `EXCLUDE_SUBSTRINGS`.
- Deeper RTL polish (icon/carousel direction, spacing, bidi, alignment) is handled by the
  **Gemini visual pass** above, refreshed weekly. LLM-authored CSS isn't infallible — review
  the live `/ar/` pages after publishing and tune `prompts/visual_system.md` (or add a
  selector substring to `exclusions.py`) if a correction looks wrong.
- The visual pass produces one combined layer scoped `html[lang="ar"]`, so a correction made
  for one page applies to all Arabic pages (fine for shared components; the prompt steers
  Gemini toward component-level selectors).
