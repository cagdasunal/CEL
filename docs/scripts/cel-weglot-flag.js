/*!
 * cel-weglot-flag.js — Geo-targeted Weglot flag swap for englishcollege.com
 *
 * WHAT IT DOES
 *   For visitors located in Brazil, replace the Weglot-injected Portuguese
 *   (Portugal) flag in the language switcher with a Brazilian flag. Brazilian
 *   visitors recognise the Brazil flag — not Portugal's — as "their" Portuguese.
 *   The language link is UNCHANGED ("pt" still points at /pt/contato); only the
 *   small flag icon is swapped, and ONLY for BR-located visitors.
 *
 * TOPOLOGY (matches cel-offers.js — see rules/cel-offers-deploy.md)
 *   Source-of-truth: tools/cel-weglot-flag-js/cel-weglot-flag.js (cagdasunal/webflow monorepo)
 *   Mirrored to:     docs/scripts/cel-weglot-flag.js (cagdasunal/CEL repo)
 *   Public URL:      https://cel.englishcollege.com/scripts/cel-weglot-flag.min.js
 *   Webflow:         <script src="…/cel-weglot-flag.min.js" defer> in
 *                    Site Settings → Custom Code → Footer Code
 *
 * GEO SOURCE
 *   window.geotargetly_country_code() — provided by the Geotargetly install
 *   snippet already in Webflow Site Settings → Head Code (the same global the
 *   offers bundle uses). NOT bundled here. We also read the shared
 *   localStorage["cel_geo_cc"] cache that cel-offers.js writes, so on a repeat
 *   visit the flag swaps on the first paint with no Geotargetly round-trip.
 *
 * GRACEFUL DEGRADATION
 *   If geo never resolves (e.g. the visitor declined functional cookies, so
 *   Geotargetly never loads), nothing happens — the Portugal flag stays. No
 *   errors, no layout shift. Non-BR visitors are never touched.
 *
 * Version: 1.0.0
 */
(function () {
  'use strict';

  // Run-once guard (every CEL bundle needs a unique guard name).
  if (window.__celWeglotFlagBR) return;
  window.__celWeglotFlagBR = true;

  /* ── Config ─────────────────────────────────────────────────────────────
   * Brazil flag shown to BR visitors in place of the Portugal flag.
   * DEFAULT = Weglot's own circular Brazil flag (512×512 SVG — identical
   * format to every other flag in the switcher, so the dimensions match
   * pixel-for-pixel with no distortion).
   *
   * >>> Replace this single value with the Webflow-hosted asset URL once it
   *     is uploaded. Use a SQUARE / circular image (ideally 512×512) so it
   *     fills the 21.6×21.6 slot without stretching — the Brazil flag's true
   *     10:7 rectangle would distort if hosted flat.
   */
  const BRAZIL_FLAG_URL = 'https://cdn.weglot.com/flags/circle/br.svg';

  /* The Portuguese flag(s) Weglot renders. Targets BOTH the dropdown list item
   * and the "current" flag (shown when a BR visitor is already browsing /pt/…),
   * across every switcher instance on the page (header, footer, mobile). The
   * src fallback catches any instance where the data-l attribute is absent. */
  const PT_SELECTOR = '[data-l="pt"] img.wg-flag, img.wg-flag[src*="/pt.svg"]';

  // Shared geo cache written by cel-offers.js. We mirror that script's
  // readCachedGeo() exactly — require the timestamp and honour the same 7-day
  // TTL — so a stale BR entry can't keep swapping the flag past the window.
  const GEO_CACHE_KEY = 'cel_geo_cc';
  const GEO_CACHE_TTL_MS = 1000 * 60 * 60 * 24 * 7; // 7 days

  function cachedCountry() {
    try {
      const raw = localStorage.getItem(GEO_CACHE_KEY);
      if (!raw) return null;
      const d = JSON.parse(raw);
      if (!d || !d.cc || !d.t) return null;
      if (Date.now() - d.t > GEO_CACHE_TTL_MS) return null;
      return String(d.cc).trim().toUpperCase();
    } catch (e) {
      return null;
    }
  }

  let isBrazil = cachedCountry() === 'BR';

  /* ── Swap ───────────────────────────────────────────────────────────────
   * Idempotent: skips any flag already showing the Brazil URL, so re-runs
   * (triggered by the observer below) never loop or thrash. Only the `src`
   * attribute changes — width/height stay put, so render size is identical. */
  function swap() {
    if (!isBrazil) return;
    const flags = document.querySelectorAll(PT_SELECTOR);
    for (let i = 0; i < flags.length; i++) {
      const img = flags[i];
      if (img.getAttribute('src') === BRAZIL_FLAG_URL) continue; // already swapped
      img.setAttribute('src', BRAZIL_FLAG_URL);
      img.setAttribute('data-cel-flag', 'br');
    }
  }

  /* Weglot injects and re-renders its switcher asynchronously (initial inject,
   * dropdown open, language change). Watch for added nodes and re-apply. We
   * only mutate the `src` ATTRIBUTE — which this childList observer ignores —
   * so swap() cannot retrigger itself. */
  function observe() {
    const obs = new MutationObserver(function (muts) {
      for (let i = 0; i < muts.length; i++) {
        if (muts[i].addedNodes && muts[i].addedNodes.length) {
          swap();
          return;
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  /* ── Geo resolution ─────────────────────────────────────────────────────
   * Cache hit → swap now. Otherwise poll the Geotargetly global (same cadence
   * as cel-offers.js: 100ms, give up after 5s). swap() is called directly on
   * resolution so we don't depend on a subsequent Weglot re-render. */
  function resolveGeo() {
    if (isBrazil) {
      swap();
      return;
    }
    const t = setInterval(function () {
      if (typeof geotargetly_country_code === 'function') {
        const code = geotargetly_country_code();
        if (code && code.length) {
          clearInterval(t);
          if (code.trim().toUpperCase() === 'BR') {
            isBrazil = true;
            swap();
          }
        }
      }
    }, 100);
    setTimeout(function () { clearInterval(t); }, 5000);
  }

  observe();    // catch Weglot's switcher injection (can happen any time)
  resolveGeo(); // resolve country and swap when it is BR
})();
