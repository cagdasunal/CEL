/*!
 * cel-offers.js — Consolidated offer JavaScript for englishcollege.com
 *
 * Source-of-truth: tools/cel-offers-js/cel-offers.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-offers.js        (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-offers.js
 *
 * Sections currently bundled:
 *   1. Section-level data-geo handler          (was inline_7606ee7d, since v1.0.0)
 *   2. Per-item .offer_item data-country filter (was inline_9d54ce87, since v1.1.0)
 *   3. Per-card .offer_date countdown          (was inline_6c6f5f54, since v1.2.0)
 *
 * Each section is wrapped in its own IIFE — they run independently and only
 * cooperate via DOM mutation. Section 1 toggles wrapping [data-geo] blocks by
 * visitor country; Section 2 removes individual .offer_item cards inside them
 * whose per-item data-country list excludes the visitor.
 *
 * Both sections require a global window.geotargetly_country_code() function,
 * provided by the Geotargetly install snippet in Webflow Site Settings → Head
 * Code (NOT bundled here).
 *
 * Section 1 caches the resolved country code in localStorage["cel_geo_cc"] for
 * 7 days to prevent nav "popping". Adds the class `geo-ready` to <html> once
 * filtering completes — the FOUC-prevention CSS in Webflow Site Settings →
 * Head Code keys off this class.
 *
 * v1.1.0 (2026-04-29): Section 2 added (per-item country filter). Surgical
 * fixes vs the inline original:
 *   - F6 (audit): 3x console.log + 1x console.warn debug noise removed.
 *   - F3 (audit): forever-retry on missing .offers_list wrapper bounded to
 *     ~10s (20 retries x 500ms), then gives up cleanly. The wrapper observer
 *     was a "what if items are added later" safety net that never engages on
 *     the current 6 offer pages anyway; runFilter() works without it.
 *   - Init runs immediately inside the IIFE (CDN-safe), same pattern as
 *     Section 1 (per project no-domcontentloaded rule for CDN-loaded scripts).
 *
 * v1.0.0 (2026-04-29): Section 1 added (data-geo handler).
 *
 * Future versions will fold in one more script that currently lives as an
 * inline copy elsewhere on the site:
 *   v1.2.0 — per-card .offer_date countdown (was inline_6c6f5f54). Replaces
 *            both the clean version and the verbose inline_0bd2cf04 duplicate
 *            that ships only on /offers.
 *
 * NOT in this file (intentional):
 *   - Geotargetly install snippet — stays in Webflow Site Settings → Head.
 *   - dayjs + dayjs/utc + dayjs/duration — only needed by v1.2.0.
 *
 * Version: 1.5.0
 * Last update: 2026-07-08
 *
 * v1.5.0 (2026-07-08): Section 0 added — consent-free geo resolver — plus a
 *                      Section 2 cache-parity fix. Three defects addressed:
 *
 *                      (1) FAIL-CLOSED CONSENT GATE. Geotargetly is gated as
 *                          `type="text/plain" data-category="functional"`, so for
 *                          any visitor who has not accepted cookies it never runs,
 *                          `geotargetly_country_code()` stays undefined, Section 1's
 *                          poll times out, `markGeoReady()` — which lives INSIDE
 *                          `runFilter()`, after the `!userGeo` early-return — never
 *                          fires, and the FOUC CSS keeps every `[data-geo]` block at
 *                          `visibility:hidden` forever. All 34 offer cards rendered
 *                          into the DOM and stayed permanently invisible, along with
 *                          the navbar "Offers" link. Section 0 now resolves the
 *                          country without consent, so offers show.
 *
 *                      (2) DEAD POLL. The 5s `clearInterval` had no re-arm and no
 *                          `cc:onConsent` listener, while the consent config sets no
 *                          `reloadPage`. Accepting the banner after ~5s (i.e. anyone
 *                          who reads it) loaded Geotargetly with nothing left
 *                          listening — offers stayed hidden for the rest of that
 *                          pageview, appearing only on the next navigation. Section 0
 *                          resolves in ~50ms regardless, and re-resolves on
 *                          `cc:onConsent` / `cc:onChange` if the first attempt failed.
 *
 *                      (3) CACHE/FILTER ASYMMETRY (over-exposure). Section 1 read the
 *                          `cel_geo_cc` cache at init; Section 2 did NOT — it learned
 *                          geo only from the live poll. On the cached path (or with
 *                          `g792337341.co` ad-blocked) Section 1 revealed the wrapper
 *                          while Section 2 had nothing to filter with, rendering EVERY
 *                          market's card — CN-only, JP-only, KR-only, 10%..40% — to
 *                          EVERY visitor. Section 2 now reads the same cache and the
 *                          same `cel:geo` event.
 *
 *                      Targeting rules are UNCHANGED: the region→country map and the
 *                      per-item `data-country` lists are untouched. Visitors in
 *                      countries outside a region's list still see nothing, as before.
 *
 * v1.4.1 (2026-05-01): Section 1 — `action: 'show'` matched branch now
 *                      sets `el.style.display = ''` (revert to CSS) instead
 *                      of `'block'`. Forcing 'block' broke flex/grid
 *                      children (e.g. `.stoc_link` TOC sidebar item) whose
 *                      computed display comes from CSS, not the default
 *                      `<a>` user-agent rule. Mismatch branch still sets
 *                      'none' (unchanged). The 'hide' and 'remove' branches
 *                      already used '' for matches — now consistent.
 *
 * v1.4.0 (2026-05-01): Sections 2, 3, 4 now also recognize the new
 *                      offer-bento card markup used on /vancouver/adults-16
 *                      and /vancouver/costs:
 *                        - Item selector widened to `.offer_item, .offer-item`
 *                          (legacy CMS cards on /offers etc. unchanged; new
 *                          offer-bento cards now filtered + ticked).
 *                        - Date element detection falls back to any
 *                          `[data-wg-notranslate]` descendant whose trimmed
 *                          text matches `YYYY-MM-DD` when no `.offer_date`
 *                          element is present (offer-bento cards omit the
 *                          legacy `.offer_date` class).
 *                        - Section 3 rewritten to use vanilla `Date` instead
 *                          of dayjs. Behavior identical (UTC end-of-day
 *                          expiry, per-second tick, isConnected guard) but
 *                          the dayjs guard early-return is gone — Section 3
 *                          now also runs on the previously nav-only pages
 *                          (adults-16, how-long-to-learn-english, costs, vs-toronto)
 *                          which don't ship dayjs. Pages without offer cards
 *                          remain a no-op (querySelectorAll returns empty).
 *
 * v1.3.2 (2026-04-30): Section 1 — fix relative regions-fetch URL that
 *                      404'd on www.englishcollege.com. The script is
 *                      hosted at cel.englishcollege.com but loaded into
 *                      pages on www.englishcollege.com; the relative
 *                      path /scripts/cel-offers-regions.json resolved
 *                      against the page origin (www) and 404'd, so the
 *                      runtime regions JSON was never applied (silent
 *                      fallback to the hardcoded baseline). Now
 *                      hardcoded to the absolute cel.englishcollege.com
 *                      URL — GitHub Pages already sends ACAO:* so the
 *                      cross-origin fetch works.
 * v1.3.1 (2026-04-30): Section 4 — fix latent Temporal Dead Zone in
 *                      tick()'s clearInterval(loop) reference. The first
 *                      synchronous tick() runs before `const loop = setInterval(...)`
 *                      is evaluated; on nav-only pages (where pickSoonest()
 *                      returns null on the first call) this threw a
 *                      ReferenceError that was masked by the IIFE's try/catch.
 *                      Now `let loop = null` is declared before tick(), and
 *                      the early-exit branch guards `if (loop !== null)`.
 *                      Behavior on offer pages is identical.
 * v1.3.0 (2026-04-30): Section 4 added — navbar .offers_counter now ticks
 *                      against soonest-expiring .offer_item .offer_date
 *                      (audit F5). Section 2 dead .offers_list retry replaced
 *                      with document.body observer (matches Section 1 pattern).
 *                      Section 3 guarded against missing dayjs on nav-only
 *                      pages. build.sh now passes --comments false to terser
 *                      so cel-offers.min.js no longer carries the source's
 *                      banner comment.
 * v1.2.0 (2026-04-29): Section 3 added (per-card countdown, was inline_6c6f5f54).
 *                      Verbose duplicate (was inline_0bd2cf04) dropped — cleaner
 *                      version now covers all 6 pages. F4 fix: per-tick
 *                      isConnected check clears orphan intervals when Section 2
 *                      removes country-mismatched items.
 * v1.1.1 (2026-04-29): Minification workflow added (cel-offers.min.js).
 *                      Removed dead visibleCount variable from Section 2.
 *
 * Maintenance rules: rules/cel-offers-deploy.md
 */

/* ============================================================
 * Section 0 — consent-free geo resolver (v1.5.0)
 * ============================================================
 * THE SOURCE
 *   www.englishcollege.com is proxied by Cloudflare, which serves
 *   `/cdn-cgi/trace` on every proxied hostname. It is same-origin, sets no
 *   cookie, reads no storage, is on no blocklist, and returns `loc=<ISO2>` in
 *   ~50ms. It needs no consent because it stores nothing — it is an ordinary
 *   same-origin request whose response the visitor's own browser reads.
 *
 *   Root-relative `/cdn-cgi/trace` is REQUIRED. A bare relative `cdn-cgi/trace`
 *   would resolve to `/tr/cdn-cgi/trace` on Weglot locale paths, which 404s
 *   (verified 2026-07-08).
 *
 * STORAGE / CONSENT BOUNDARY
 *   The resolved country is persisted to localStorage ONLY when functional
 *   consent is granted. A 7-day country cache is itself ePrivacy "storage";
 *   without consent we simply re-resolve each pageview (one ~50ms same-origin
 *   fetch). Section 1 keeps writing the cache on its own Geotargetly path,
 *   which by definition already implies consent.
 *
 * HANDOFF
 *   Announces the result on a `cel:geo` CustomEvent; Sections 1 and 2 listen.
 *   It only ever fires asynchronously (after the synchronous IIFE parse below),
 *   so those listeners are always attached in time. First source to resolve
 *   wins — a country already read from cache or Geotargetly is never
 *   overridden, and `publish()` is idempotent.
 *
 * FALLBACK
 *   Non-Cloudflare origins (englishcollege.webflow.io staging) 404 → silent
 *   no-op, and the pre-existing Geotargetly poll remains the fallback. If geo
 *   cannot be resolved by ANY source, behavior is exactly as before this
 *   version: `geo-ready` is not set and [data-geo] blocks stay hidden. We do
 *   not blind-reveal, because with no country there is no correct subset of
 *   offers to show — none of the 34 cards is tagged `ALL`.
 * ============================================================ */

(function() {
  const TRACE_URL = '/cdn-cgi/trace';
  const GEO_CACHE_KEY = 'cel_geo_cc';
  // Cloudflare returns loc=XX when the country is unknown and loc=T1 for Tor
  // exit nodes. Both are non-countries — treating them as ISO2 would match no
  // region and silently filter every offer away.
  const NOT_A_COUNTRY = ['XX', 'T1'];

  let published = false;

  function functionalConsentGranted() {
    try {
      return !!(window.CookieConsent &&
                typeof CookieConsent.acceptedCategory === 'function' &&
                CookieConsent.acceptedCategory('functional'));
    } catch (e) {
      return false;
    }
  }

  function cacheIfConsented(cc) {
    if (!functionalConsentGranted()) return;
    try {
      localStorage.setItem(GEO_CACHE_KEY, JSON.stringify({ cc: cc, t: Date.now() }));
    } catch (e) {}
  }

  function publish(raw) {
    if (published) return;
    const cc = String(raw || '').trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return;
    if (NOT_A_COUNTRY.indexOf(cc) !== -1) return;
    published = true;
    cacheIfConsented(cc);
    try {
      window.dispatchEvent(new CustomEvent('cel:geo', { detail: { cc: cc } }));
    } catch (e) {}
  }

  function resolve() {
    try {
      fetch(TRACE_URL, { cache: 'no-store' })
        .then(function(r) { return r && r.ok ? r.text() : null; })
        .then(function(txt) {
          if (!txt) return;
          const m = txt.match(/^loc=([A-Z0-9]{2})$/m);
          if (m) publish(m[1]);
        })
        .catch(function() { /* staging/offline → Geotargetly poll remains */ });
    } catch (e) { /* no fetch() → Geotargetly poll remains */ }
  }

  resolve();

  // If the trace call failed but the visitor later accepts cookies, Geotargetly
  // executes in place (CookieConsent sets no `reloadPage`). Re-resolve then, so
  // the offers are not stranded behind an already-expired 5s poll (defect 2).
  function retry() { if (!published) resolve(); }
  window.addEventListener('cc:onConsent', retry);
  window.addEventListener('cc:onChange', retry);

})();

/* ============================================================
 * Section 1 — data-geo handler (was inline_7606ee7d)
 * ============================================================ */

(function() {
  /* CONFIG is the active region → countries map. Initial value is the
   * hardcoded fallback (preserves v1.2.0 behavior if the runtime JSON
   * fetch fails or hasn't resolved yet). At boot we attempt to fetch
   * https://cel.englishcollege.com/scripts/cel-offers-regions.json — if
   * it returns a valid shape, CONFIG is overwritten and runFilter() runs
   * again so the fresh values take effect on the next paint.
   *
   * The URL must be ABSOLUTE (cross-origin to cel.englishcollege.com)
   * because this script is loaded onto www.englishcollege.com pages —
   * a relative path resolves to www.englishcollege.com and 404s. The
   * GitHub Pages CDN already sends `Access-Control-Allow-Origin: *`
   * for all assets under /scripts/, so the cross-origin fetch works.
   *
   * The JSON file is written by the admin dashboard's Settings tab via
   * .github/workflows/offers-edit-regions.yml — see rules/cel-offers-deploy.md.
   */
  const REGIONS_URL = 'https://cel.englishcollege.com/scripts/cel-offers-regions.json';
  const FALLBACK_CONFIG = {
    'offers': {
      countries: "ES,IT,NL,SE,FI,AT,BE,PT,AD,DK,DE,GR,IS,LI,LU,NO,SM,TR,AZ,BY,GE,KZ,KG,AM,MD,RU,TJ,UA,AL,BA,BG,HR,CY,CZ,EE,LV,LT,ME,MK,PL,RO,RS,SK,SI,TW,CN,KR,VN,TH,BD,KH,ID,MY,MN,BH,EG,IR,IQ,AE,JO,KW,SA,LB,OM,QA,YE,DZ,AR,BZ,BO,CL,CO,CR,CU,DO,EC,SV,GT,HT,HN,JM,MX,NI,PA,PY,PE,UY,VE,BR,JP",
      action: 'show'
    },
    'sandiego': {
      countries: "AE,AL,AM,AR,AZ,BA,BD,BE,BG,BH,BO,BR,BZ,CL,CN,CO,CR,CU,CY,CZ,DO,DZ,EC,EE,EG,ES,FR,GE,GT,HN,HR,HT,ID,IQ,IR,IT,JM,JO,JP,KG,KH,KR,KW,KZ,LB,LT,LV,MD,ME,MK,MN,MX,MY,NI,OM,PA,PE,PL,PY,QA,RO,RS,RU,SA,SI,SK,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
      action: 'show'
    },
    'losangeles': {
      countries: "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KU,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
      action: 'show'
    },
    'usa': {
      countries: "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CL,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,FR,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KU,KW,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
      action: 'show'
    },
    'vancouver': {
      countries: "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
      action: 'show'
    },
    'canada': {
      countries: "AD,AE,AL,AM,AR,AT,AZ,BA,BD,BE,BG,BH,BO,BR,BY,BZ,CN,CO,CR,CU,CY,CZ,DE,DK,DO,DZ,EC,EE,EG,ES,FI,GE,GR,GT,HN,HR,HT,ID,IQ,IR,IS,IT,JM,JO,JP,KG,KH,KR,KZ,LB,LI,LT,LU,LV,MD,ME,MK,MN,MX,MY,NI,NL,NO,OM,PA,PE,PL,PT,PY,QA,RO,RS,RU,SA,SE,SI,SK,SM,SV,TH,TJ,TR,TW,UA,UY,VE,VN,YE",
      action: 'show'
    }
  };

  // Mutable active config — starts as fallback, may be replaced by fetched JSON.
  let CONFIG = FALLBACK_CONFIG;

  function applyFetchedRegions(json) {
    if (!json || !json.regions || typeof json.regions !== 'object') return false;
    const next = {};
    let any = false;
    Object.keys(FALLBACK_CONFIG).forEach(function(k) {
      const fetched = json.regions[k];
      if (fetched && typeof fetched.countries === 'string' && /^[A-Z]{2}(,[A-Z]{2})*$/.test(fetched.countries)) {
        next[k] = { countries: fetched.countries, action: fetched.action || 'show' };
        any = true;
      } else {
        next[k] = FALLBACK_CONFIG[k];
      }
    });
    if (!any) return false;
    CONFIG = next;
    return true;
  }

  // Try to load latest regions JSON. Failure is silent — fallback is already in place.
  try {
    fetch(REGIONS_URL, { cache: 'no-cache' })
      .then(function(r) { return r && r.ok ? r.json() : null; })
      .then(function(json) {
        if (applyFetchedRegions(json)) {
          // Re-run the filter so saved Settings take effect immediately
          if (typeof runFilter === 'function') runFilter();
        }
      })
      .catch(function() { /* fallback in place; nothing to do */ });
  } catch (e) { /* very old browsers without fetch — silent fallback */ }

  // ---- Cache (prevents nav "popping" after refresh) ----
  const GEO_CACHE_KEY = "cel_geo_cc";
  const GEO_CACHE_TTL_MS = 1000 * 60 * 60 * 24 * 7; // 7 days

  function readCachedGeo() {
    try {
      const raw = localStorage.getItem(GEO_CACHE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !data.cc || !data.t) return null;
      if (Date.now() - data.t > GEO_CACHE_TTL_MS) return null;
      return String(data.cc).toUpperCase();
    } catch (e) {
      return null;
    }
  }

  function writeCachedGeo(cc) {
    try {
      localStorage.setItem(GEO_CACHE_KEY, JSON.stringify({ cc: String(cc).toUpperCase(), t: Date.now() }));
    } catch (e) {}
  }

  // Mark when geo is resolved so CSS can stop treating items as "pending"
  function markGeoReady() {
    document.documentElement.classList.add("geo-ready");
  }

  let userGeo = readCachedGeo(); // <- immediate if available

  function runFilter() {
    if (!userGeo) return;

    const components = document.querySelectorAll('[data-geo]');

    components.forEach(el => {
      const key = el.getAttribute('data-geo');
      const settings = CONFIG[key];

      if (!settings) return;

      let allowedList = [];

      if (settings.useAttribute) {
        const rawAttr = el.getAttribute(settings.attrName);
        if (rawAttr) {
          allowedList = rawAttr.split(',').map(s => s.trim().toUpperCase());
        }
      } else if (settings.countries) {
        allowedList = settings.countries.split(',').map(s => s.trim().toUpperCase());
      }

      const isMatch = allowedList.includes(userGeo) || allowedList.includes('ALL');

      if (settings.action === 'show') {
        // v1.4.1: empty string (revert to CSS-defined display) instead of
        // 'block' — forcing 'block' breaks flex/grid children like
        // .stoc_link (TOC sidebar) whose layout depends on inherited
        // display. Empty string lets the stylesheet decide.
        el.style.display = isMatch ? '' : 'none';
      }
      else if (settings.action === 'remove') {
        if (!isMatch) el.remove();
        else el.style.display = '';
      }
      else if (settings.action === 'hide') {
        el.style.display = isMatch ? '' : 'none';
      }
    });

    markGeoReady();
  }

  function initGeo() {
    // If we already have cached geo, apply immediately
    if (userGeo) runFilter();

    const interval = setInterval(() => {
      if (typeof geotargetly_country_code === 'function') {
        const code = geotargetly_country_code();
        if (code && code.length > 0) {
          userGeo = code.trim().toUpperCase();
          writeCachedGeo(userGeo);
          clearInterval(interval);
          runFilter();
        }
      }
    }, 100);

    setTimeout(() => {
      if (!userGeo) clearInterval(interval);
    }, 5000);
  }

  function initObserver() {
    const observer = new MutationObserver((mutations) => {
      let shouldRefilter = false;
      mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) shouldRefilter = true;
      });
      if (shouldRefilter) runFilter();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // v1.5.0: Section 0 resolves the country without consent and announces it
  // here. Whichever source lands first wins; a country already resolved from
  // cache or Geotargetly is never overridden.
  window.addEventListener('cel:geo', function(e) {
    const cc = e && e.detail && e.detail.cc;
    if (!cc || userGeo === cc) return;
    userGeo = cc;
    runFilter();
  });

  // Run init immediately (CDN-safe). The MutationObserver catches any items
  // added after this point.
  initObserver();
  initGeo();

})();

/* ============================================================
 * Section 2 — per-item .offer_item data-country filter (was inline_9d54ce87)
 * Surgical fixes since v1.1.0:
 *   F6: 4 debug console lines removed.
 *   F3: forever-retry on missing .offers_list bounded to ~10s.
 * ============================================================ */

(function() {
  const CONF = {
    listWrapper: '.offers_list',
    // Legacy CMS cards use `.offer_item` (underscore); new offer-bento
    // cards on /vancouver/adults-16 + /vancouver/costs use `.offer-item`
    // (hyphen). Match both.
    item: '.offer_item, .offer-item',
    attrName: 'data-country'
  };

  // v1.5.0 (defect 3): Section 1 has always read the shared `cel_geo_cc` cache
  // at init, but Section 2 did not — it learned geo ONLY from the Geotargetly
  // poll. On the cached path (or when Geotargetly is ad-blocked) Section 1
  // revealed the wrapper while Section 2 still had `userGeo === null`, so
  // `runFilter()` early-returned and EVERY market's offer card rendered to
  // EVERY visitor. Read the same cache, with the same key and TTL as Section 1.
  const GEO_CACHE_KEY = 'cel_geo_cc';
  const GEO_CACHE_TTL_MS = 1000 * 60 * 60 * 24 * 7; // 7 days — matches Section 1

  function readCachedGeo() {
    try {
      const raw = localStorage.getItem(GEO_CACHE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !data.cc || !data.t) return null;
      if (Date.now() - data.t > GEO_CACHE_TTL_MS) return null;
      return String(data.cc).toUpperCase();
    } catch (e) {
      return null;
    }
  }

  let userGeo = readCachedGeo();

  function runFilter() {
    if (!userGeo) return;

    const items = document.querySelectorAll(CONF.item);

    items.forEach(item => {
      const rawAttr = item.getAttribute(CONF.attrName);

      if (!rawAttr) {
        item.remove();
        return;
      }

      const allowedList = rawAttr.split(',').map(s => s.trim().toUpperCase());

      if (allowedList.includes(userGeo) || allowedList.includes('ALL')) {
        item.style.display = '';
      } else {
        item.remove();
      }
    });

    const list = document.querySelector(CONF.listWrapper);
    if (list) list.style.opacity = '1';
  }

  // v1.3.0: drop the .offers_list wrapper retry (the wrapper has never existed
  // on any of the 6 offer pages — verified by audit). Watch document.body instead,
  // matching Section 1's pattern. Same defensive behavior, no dead retry timer.
  function initObserver() {
    const observer = new MutationObserver((mutations) => {
      let shouldRefilter = false;
      mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) shouldRefilter = true;
      });
      if (shouldRefilter) runFilter();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function initGeo() {
    const interval = setInterval(() => {
      if (typeof geotargetly_country_code === 'function') {
        const code = geotargetly_country_code();

        if (code && code.length > 0) {
          userGeo = code.trim().toUpperCase();
          clearInterval(interval);
          runFilter();
        }
      }
    }, 100);

    setTimeout(() => {
        if (!userGeo) {
            clearInterval(interval);
        }
    }, 5000);
  }

  // v1.5.0: same `cel:geo` handoff as Section 1.
  window.addEventListener('cel:geo', function(e) {
    const cc = e && e.detail && e.detail.cc;
    if (!cc || userGeo === cc) return;
    userGeo = cc;
    runFilter();
  });

  // Run init immediately (CDN-safe). The MutationObserver (when its wrapper
  // exists) catches any .offer_item elements added after this point.
  initObserver();
  if (userGeo) runFilter();   // v1.5.0: cached path — filter before first paint
  initGeo();

})();

/* ============================================================
 * Section 3 — per-card countdown (was inline_6c6f5f54)
 * Surgical fixes since v1.2.0:
 *   F4: per-tick isConnected check clears the interval when Section 2
 *       removes country-mismatched items (no more orphan setIntervals).
 *   Init runs immediately inside the IIFE (CDN-safe), same pattern as
 *       Sections 1 and 2.
 *   v1.4.0: vanilla Date instead of dayjs (no dayjs guard needed → runs
 *       on adults-16/how-long-to-learn-english/costs/vs-toronto), and dual
 *       item/date selectors covering legacy `.offer_item`+`.offer_date`
 *       and new offer-bento `.offer-item` + `[data-wg-notranslate]`
 *       date markup. UTC end-of-day expiry semantics preserved.
 * ============================================================ */

(function() {
  function pad(num) {
    return String(num).padStart(2, '0');
  }

  // Find the date element inside an offer card. Legacy: explicit
  // `.offer_date` class. New offer-bento: any `[data-wg-notranslate]`
  // descendant whose trimmed text matches `YYYY-MM-DD`.
  function findDateEl(item) {
    const explicit = item.querySelector('.offer_date');
    if (explicit) return explicit;
    const candidates = item.querySelectorAll('[data-wg-notranslate]');
    for (let i = 0; i < candidates.length; i++) {
      if (/^\d{4}-\d{2}-\d{2}$/.test((candidates[i].textContent || '').trim())) {
        return candidates[i];
      }
    }
    return null;
  }

  // YYYY-MM-DD → UTC end-of-day epoch ms (matches the previous
  // dayjs.utc(dateStr).endOf('day') semantics exactly).
  function parseExpiry(dateStr) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return NaN;
    return new Date(dateStr + 'T23:59:59.999Z').getTime();
  }

  const items = document.querySelectorAll('.offer_item, .offer-item');
  const now = Date.now();

  items.forEach(function (item) {
    const dateEl = findDateEl(item);
    if (!dateEl) return;

    const dateStr = (dateEl.textContent || '').trim();
    const expiry = parseExpiry(dateStr);
    if (!isFinite(expiry)) return;

    if (now > expiry) {
      item.remove();
      return;
    }

    const dEl = item.querySelector('.count_days');
    const hEl = item.querySelector('.count_hours');
    const mEl = item.querySelector('.count_minutes');
    const sEl = item.querySelector('.count_seconds');

    if (!dEl || !hEl || !mEl || !sEl) return;

    let loop = null;

    function tick() {
      // F4 fix: if Section 2's filter removed this item, stop ticking.
      if (!item.isConnected) {
        if (loop !== null) clearInterval(loop);
        return;
      }

      const diff = expiry - Date.now();

      if (diff <= 0) {
        item.remove();
        if (loop !== null) clearInterval(loop);
        return;
      }

      const totalSec = Math.floor(diff / 1000);
      dEl.textContent = pad(Math.floor(totalSec / 86400));
      hEl.textContent = pad(Math.floor((totalSec % 86400) / 3600));
      mEl.textContent = pad(Math.floor((totalSec % 3600) / 60));
      sEl.textContent = pad(totalSec % 60);
    }

    tick();
    loop = setInterval(tick, 1000);
  });

})();

/* ============================================================
 * Section 4 — navbar .offers_counter ticker (v1.3.0, audit F5)
 * Ticks the standalone navbar countdown against the soonest-expiring
 * .offer_item .offer_date on the page. Vanilla Date — no dayjs needed.
 * Exits cleanly when there's no .offer_item on the page (the 4 nav-only
 * pages /adults-16, /how-long-to-learn-english, /costs, /vs-toronto — navbar counter
 * stays at its CMS-rendered "00" placeholder, current behavior unchanged).
 * Whole section is try/catch wrapped — any error → leave navbar alone.
 * ============================================================ */

(function() {
  try {
    function pad(n) { return String(n).padStart(2, '0'); }

    // Find the navbar counter (decorative element outside any .offer_item).
    // The selectors target the navbar instance only — not per-card counters.
    const counter = document.querySelector('.navbar_buttons .offers_counter, .navbar_button-wrapper .offers_counter');
    if (!counter) return;

    const dEl = counter.querySelector('.count_days');
    const hEl = counter.querySelector('.count_hours');
    const mEl = counter.querySelector('.count_minutes');
    const sEl = counter.querySelector('.count_seconds');
    if (!dEl || !hEl || !mEl || !sEl) return;

    let loop = null;

    // Find date element on legacy `.offer_item` (.offer_date) AND new
    // offer-bento `.offer-item` ([data-wg-notranslate] with YYYY-MM-DD text).
    function findDateEl(item) {
      const explicit = item.querySelector('.offer_date');
      if (explicit) return explicit;
      const candidates = item.querySelectorAll('[data-wg-notranslate]');
      for (let i = 0; i < candidates.length; i++) {
        if (/^\d{4}-\d{2}-\d{2}$/.test((candidates[i].textContent || '').trim())) {
          return candidates[i];
        }
      }
      return null;
    }

    function pickSoonest() {
      const items = document.querySelectorAll('.offer_item, .offer-item');
      let soonest = null;
      items.forEach(function(item) {
        if (!item.isConnected) return;
        const dateEl = findDateEl(item);
        if (!dateEl) return;
        const dateStr = (dateEl.textContent || '').trim();
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return;
        // End-of-day UTC (matches Section 3's UTC end-of-day semantics).
        const expiry = new Date(dateStr + 'T23:59:59.999Z').getTime();
        if (!isFinite(expiry)) return;
        if (expiry <= Date.now()) return;
        if (soonest === null || expiry < soonest) soonest = expiry;
      });
      return soonest;
    }

    function tick() {
      const target = pickSoonest();
      if (target === null) {
        // No live offers on this page → leave counter at its CMS placeholder.
        // Don't write anything; don't keep ticking.
        if (loop !== null) clearInterval(loop);
        return;
      }
      const diff = target - Date.now();
      if (diff <= 0) {
        // Soonest just expired — recompute next tick. Fast path.
        return;
      }
      const totalSec = Math.floor(diff / 1000);
      const days = Math.floor(totalSec / 86400);
      const hours = Math.floor((totalSec % 86400) / 3600);
      const mins = Math.floor((totalSec % 3600) / 60);
      const secs = totalSec % 60;
      dEl.textContent = pad(days);
      hEl.textContent = pad(hours);
      mEl.textContent = pad(mins);
      sEl.textContent = pad(secs);
    }

    tick();
    loop = setInterval(tick, 1000);
  } catch (e) {
    /* Any error → navbar counter stays at its CMS placeholder. Current behavior. */
  }
})();
