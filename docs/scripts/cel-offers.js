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
 * Version: 1.1.1
 * Last update: 2026-04-29
 *
 * v1.1.1 (2026-04-29): Minification workflow added (cel-offers.min.js).
 *                      Removed dead visibleCount variable from Section 2.
 *
 * Maintenance rules: rules/cel-offers-deploy.md
 */

/* ============================================================
 * Section 1 — data-geo handler (was inline_7606ee7d)
 * ============================================================ */

(function() {
  const CONFIG = {
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
        el.style.display = isMatch ? 'block' : 'none';
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
    item: '.offer_item',
    attrName: 'data-country'
  };

  let userGeo = null;

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

  // F3 fix: bound the missing-wrapper retry loop. Closure-scoped counter.
  let observerTries = 0;
  const OBSERVER_MAX_TRIES = 20;  // 20 x 500ms = 10s ceiling

  function initObserver() {
    const listWrapper = document.querySelector(CONF.listWrapper);

    if (!listWrapper) {
        if (++observerTries < OBSERVER_MAX_TRIES) {
          setTimeout(initObserver, 500);
        }
        return;
    }

    const observer = new MutationObserver((mutations) => {
      let shouldRefilter = false;
      mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) shouldRefilter = true;
      });

      if (shouldRefilter) {
        runFilter();
      }
    });

    observer.observe(listWrapper, { childList: true, subtree: true });
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

  // Run init immediately (CDN-safe). The MutationObserver (when its wrapper
  // exists) catches any .offer_item elements added after this point.
  initObserver();
  initGeo();

})();
