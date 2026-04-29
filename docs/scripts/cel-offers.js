/*!
 * cel-offers.js — Section-level data-geo handler for englishcollege.com
 *
 * Source-of-truth: tools/cel-offers-js/cel-offers.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-offers.js        (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-offers.js
 *
 * Toggles whole sections (e.g. the navbar /offers link) by visitor country
 * using a hardcoded region->country map for 6 named regions:
 *   offers, sandiego, losangeles, usa, vancouver, canada.
 *
 * Reads a global window.geotargetly_country_code() function (provided by
 * the Geotargetly install snippet in Webflow Site Settings -> Head Code,
 * NOT bundled here) and applies CONFIG[key].action ('show' / 'hide' /
 * 'remove') to every element with a matching `data-geo` attribute.
 *
 * Caches the resolved country code in localStorage["cel_geo_cc"] for 7
 * days to prevent nav "popping" after refresh. Adds the class
 * `geo-ready` to <html> once filtering completes — the FOUC-prevention
 * CSS in Webflow Site Settings -> Head Code keys off this class.
 *
 * v1.0.0 (2026-04-29): originally was inline_7606ee7d in Webflow Site
 * Settings -> Footer Code; consolidated here for git tracking. Adapted
 * for CDN delivery: init runs immediately inside the IIFE rather than
 * waiting on a dom-ready event (per project no-domcontentloaded rule).
 *
 * Future versions will fold in two more scripts that currently live as
 * inline copies elsewhere on the site:
 *   v1.1.0 — per-item .offer_item data-country filter (was inline_9d54ce87)
 *   v1.2.0 — per-card .offer_date countdown (was inline_6c6f5f54)
 *
 * NOT in this file (intentional):
 *   - Geotargetly install snippet — stays in Webflow Site Settings -> Head.
 *   - dayjs + dayjs/utc + dayjs/duration — only needed by v1.2.0.
 *
 * Maintenance rules: rules/cel-offers-deploy.md
 */

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

  // Run init immediately (CDN-safe). MutationObserver catches any
  // [data-geo] elements added to the DOM after this point.
  initObserver();
  initGeo();

})();
