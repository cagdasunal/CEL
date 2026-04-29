/*!
 * cel-offers.js — Consolidated offer JavaScript for englishcollege.com
 *
 * Source-of-truth: tools/cel-offers-js/cel-offers.js (cagdasunal/webflow monorepo)
 * Mirrored to:     js/cel-offers.js                 (cagdasunal/CEL repo)
 * Public URL:      https://cdn.jsdelivr.net/gh/cagdasunal/CEL@main/js/cel-offers.js
 *
 * Bundles three scripts that previously lived as inline <script> blocks in
 * Webflow Site Settings → Custom Code (Footer) and per-page Custom Code:
 *
 *   1. Section-level data-geo handler          (was inline_7606ee7d, all 6 pages)
 *   2. Per-item .offer_item data-country filter (was inline_9d54ce87, all 6 pages)
 *   3. Per-card .offer_date countdown          (was inline_6c6f5f54, 5 of 6 pages)
 *
 * The verbose duplicate countdown that previously shipped only on /offers
 * (was inline_0bd2cf04) is dropped — section 3 below now covers /offers too.
 *
 * Behavior parity v1.0.0: identical to the previous inline versions, with two
 * adaptations for CDN delivery:
 *   - 5 debug log lines removed (4 console.log + 1 console.warn in section 2).
 *   - DOMContentLoaded listeners replaced with direct init calls inside IIFEs
 *     (per project rule no-domcontentloaded: CDN scripts may load after the
 *     event fires, so init code must run immediately. Sections 1 and 2 already
 *     install MutationObservers that catch any DOM items added after init.)
 *
 * Future fix-ups (forever-retry on missing wrapper, orphan setIntervals,
 * dead navbar counter, hardcoded country lists, dual-poll loop) are tracked
 * in sites/cel/docs/offers/javascript-and-geotargetly.md §8 and applied in
 * subsequent versions.
 *
 * NOT in this file (intentional):
 *   - Geotargetly install snippet — stays in Webflow Site Settings → Head.
 *   - dayjs + dayjs/utc + dayjs/duration — stay as <script src> in Webflow Head.
 *
 * Version: 1.0.0
 * Last update: 2026-04-29
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

  // CDN-loaded: run init immediately. The MutationObserver catches any items
  // added after this point. (Replaces the original readyState/DOMContentLoaded
  // branching from the inline version.)
  initObserver();
  initGeo();

})();

/* ============================================================
 * Section 2 — per-item data-country filter (was inline_9d54ce87)
 * Debug logs removed: 3 x console.log + 1 x console.warn
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
    let visibleCount = 0;

    items.forEach(item => {
      const rawAttr = item.getAttribute(CONF.attrName);

      if (!rawAttr) {
        item.remove();
        return;
      }

      const allowedList = rawAttr.split(',').map(s => s.trim().toUpperCase());

      if (allowedList.includes(userGeo) || allowedList.includes('ALL')) {
        item.style.display = '';
        visibleCount++;
      } else {
        item.remove();
      }
    });

    const list = document.querySelector(CONF.listWrapper);
    if (list) list.style.opacity = '1';
  }

  function initObserver() {
    const listWrapper = document.querySelector(CONF.listWrapper);

    if (!listWrapper) {
        setTimeout(initObserver, 500);
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

  // CDN-loaded: run init immediately. (Replaces the original
  // readyState/DOMContentLoaded branching from the inline version.)
  initObserver();
  initGeo();

})();

/* ============================================================
 * Section 3 — per-card .offer_date countdown (was inline_6c6f5f54)
 * Wrapped in IIFE for CDN safety; pad() helper now scoped privately
 * (was global in inline version — no other script depended on it).
 * ============================================================ */

(function() {
  dayjs.extend(dayjs_plugin_duration);
  dayjs.extend(dayjs_plugin_utc);

  function pad(num) {
    return num.toString().padStart(2, "0");
  }

  const items = document.querySelectorAll(".offer_item");
  const now = dayjs.utc();

  items.forEach(function (item) {
    const dateEl = item.querySelector(".offer_date");
    if (!dateEl) return;

    const dateStr = dateEl.textContent.trim();
    if (!dateStr) return;

    const expiryDate = dayjs.utc(dateStr).endOf('day');

    if (now.isAfter(expiryDate)) {
      item.remove();
      return;
    }

    const dEl = item.querySelector(".count_days");
    const hEl = item.querySelector(".count_hours");
    const mEl = item.querySelector(".count_minutes");
    const sEl = item.querySelector(".count_seconds");

    if (!dEl || !hEl || !mEl || !sEl) return;

    function tick() {
      const currentTime = dayjs.utc();
      const diff = expiryDate.diff(currentTime);

      if (diff <= 0) {
        item.remove();
        clearInterval(loop);
        return;
      }

      const dur = dayjs.duration(diff);
      dEl.textContent = pad(Math.floor(dur.asDays()));
      hEl.textContent = pad(dur.hours());
      mEl.textContent = pad(dur.minutes());
      sEl.textContent = pad(dur.seconds());
    }

    tick();
    const loop = setInterval(tick, 1000);
  });
})();
