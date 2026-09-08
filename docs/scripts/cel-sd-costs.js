/*!
 * CEL — cel-sd-costs.js
 * Page bundle for /san-diego-ca/costs (Claude Design build, 2026-09-01).
 *
 * Concatenated VERBATIM from the design project, in load order:
 *   1. pages/san-diego/currency.js                 — publishes window.CELFxRates
 *   2. pages/san-diego/calculator-sandiego-costs.js — §4 planner rates/copy; reads
 *                                                     CELFxRates, queues onto CELCalculator
 *   3. pages/san-diego/costs.js                    — all-price-tables bar reveal,
 *                                                     sticky CTA, TOC close-on-jump
 *
 * The design's own deploy note asks for ONE bundle slot shared with currency.js.
 *
 * REQUIRES, as separate <script> tags on the page (both already deployed):
 *   cel-cost-of-studying-english.min.js — TOC spy, FAQ accordion, Swiper loader and
 *     the card sliders. It already targets #livingSlider/#livingSliderNav, which are
 *     this page's ids; its #accomSlider block no-ops (that section is excluded here).
 *   cel-calculator.min.js — the shared planner engine. Order-independent: the config
 *     above queues onto window.CELCalculator when the engine has not landed yet.
 *
 * Guard flags are disjoint from the Vancouver bundle's (__celToc/__celFq/__costsPriceBarDone
 * vs __celFxDone/__costsAllPriceBarsDone/__costsStickyCtaDone),
 * so nothing double-binds.
 */
/* ═══════════════════════════════════════════════════════════
   CEL San Diego — currency.js · the §3 currency converter, standalone
   Page: pages/san-diego/costs.html (§3 "All Prices in USD" card).
   Loaded BEFORE costs.js; owns nothing else on the page and shares no state with
   it. Same conventions as costs.js: one IIFE, one unique window guard flag, no
   DOMContentLoaded, no globals beyond the flag.

   DEPLOY: folds into the CEL page-script bundle under tools/cel-page-scripts/src/
   and ships minified via /deploy-page-scripts — NOT a Webflow inline script. It
   shares this page's single bundle slot with costs.js, so no extra slot is used.
   ═══════════════════════════════════════════════════════════ */

/* ── FAST FIRST, THEN FRESH ───────────────────────────────────
   1. The baked table renders instantly — the converted figure is on screen in the
      first frame, with no request and no spinner, ever.
   2. Rates are then refreshed from the ECB (frankfurter.app: free, no key, CORS,
      one small JSON) and cached in localStorage for one hour, so at most ONE
      request per visitor per hour, and repeat views are instant from cache.
   3. The refresh only fires once the widget is in view, so a visitor who never
      reaches §3 makes no third-party call at all.
   4. If the fetch fails, is blocked, or times out (4s), the baked table simply
      stays and the note reads "indicative rate" instead of "live mid-market rate".
      The figure never disappears and there is no error state to design around.
   MAINTENANCE: refresh RATES + RATE_DATE together (source: ECB reference rates) so
   the offline path stays close to reality. The picker list is built from RATES, so
   a currency can never be offered without a rate behind it.
   ── */
(function () {
  if (window.__celFxDone) return;
  window.__celFxDone = true;

  /* Baked ECB reference rates, 1 US$ = X — the instant, offline path.
     Order here is the order in the picker: CEL's biggest markets first. */
  var RATE_DATE = '3 August 2026';
  var RATES = {
    AED: 3.6725, ARS: 1452, AUD: 1.518, BRL: 5.0675, CAD: 1.4028,
    CHF: 0.808, CLP: 942, CNY: 6.7526, COP: 3985, CZK: 21.3,
    DKK: 6.468, EGP: 48.5, EUR: 0.8669, GBP: 0.7424, HKD: 7.795,
    HUF: 345, IDR: 17977, ILS: 3.0511, INR: 95.34, JPY: 156.68,
    KRW: 1427.05, KWD: 0.3062, MAD: 9.15, MXN: 17.3207, MYR: 4.21,
    NOK: 10.24, NZD: 1.665, PEN: 3.63, PHP: 57.4, PLN: 3.7306,
    QAR: 3.64, RON: 4.315, RUB: 82, SAR: 3.75, SEK: 9.58,
    SGD: 1.285, THB: 33.335, TRY: 47.536, TWD: 31.2, UAH: 42.5,
    USD: 1, VND: 26100, ZAR: 17.6
  };

  /* Codes the ECB feed publishes. Everything else is a POPULAR market currency the ECB does
     not quote (Gulf, LATAM, RUB, TWD, UAH, VND): its baked rate is correct as of RATE_DATE and
     is labelled "indicative" per currency, so a refreshed ECB code never lends its "live" wording
     to one that was not refreshed. */
  var ECB = {AUD:1,BRL:1,CAD:1,CHF:1,CNY:1,CZK:1,DKK:1,EUR:1,GBP:1,HKD:1,HUF:1,IDR:1,ILS:1,INR:1,JPY:1,KRW:1,MXN:1,MYR:1,NOK:1,NZD:1,PHP:1,PLN:1,RON:1,SEK:1,SGD:1,THB:1,TRY:1,ZAR:1};

  var ENDPOINT = 'https://api.frankfurter.app/latest?from=USD';
  var CACHE_KEY = 'celFxUsd';      /* the only key this page writes */
  var TTL = 60 * 60 * 1000;        /* one hour */
  var TIMEOUT = 4000;

  var amountEl = document.getElementById('fxAmount');
  var pickEl = document.getElementById('fxPick');
  var pickCodeEl = document.getElementById('fxPickCode');
  var pickFlagEl = document.getElementById('fxPickFlag');
  var menuEl = document.getElementById('fxMenu');
  var resultEl = document.getElementById('fxResult');
  var noteEl = document.getElementById('fxNote');
  var widgetEl = document.getElementById('fxWidget');
  if (!amountEl || !pickEl || !menuEl || !resultEl) return;

  var code = 'EUR';
  var rates = RATES;
  var rateDate = RATE_DATE;
  var isLive = false;
  var liveSet = {};   /* per-code: was THIS rate refreshed from the feed? */

  function setText(el, text) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(text));
  }

  function format(value, cur) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency', currency: cur,
        minimumFractionDigits: 0, maximumFractionDigits: 0
      }).format(value);
    } catch (e) {
      return Math.round(value).toLocaleString() + ' ' + cur;
    }
  }

  function render() {
    var rate = rates[code] || RATES[code];
    var usd = parseFloat(amountEl.value);
    if (!rate) { setText(resultEl, ''); return; }
    if (!isFinite(usd) || usd < 0) {
      setText(resultEl, '');
      setText(noteEl, 'Enter an amount in US dollars.');
      return;
    }
    setText(resultEl, format(usd * rate, code));
    setText(noteEl, '1 US$ = ' + rate.toLocaleString(undefined, { maximumFractionDigits: 4 }) +
      ' ' + code + ' \u00b7 ' + (isLive && liveSet[code] ? 'live mid-market rate, ' : 'indicative rate, ') +
      rateDate + '. CEL bills in US$.');
  }

  function publish() {
    /* ONE rate source per page. The §4 calculator reads this instead of carrying its own
       copy of the table, so a rate can never disagree between the two tools. */
    window.CELFxRates = {
      date: rateDate,
      live: isLive,
      codes: Object.keys(RATES),
      liveFor: function (c) { return !!(isLive && liveSet[c]); },
      get: function (code) { return rates[code] || RATES[code] || null; }
    };
    var tool = document.getElementById('calcTool');
    if (tool && tool.__celCalc) tool.__celCalc.render();
  }

  function adopt(payload, live) {
    if (!payload || !payload.rates) return;
    var merged = {};
    for (var k in RATES) if (RATES.hasOwnProperty(k)) {
      if (payload.rates[k]) { merged[k] = payload.rates[k]; liveSet[k] = true; }
      else { merged[k] = RATES[k]; }               /* never drop a listed currency */
    }
    rates = merged;
    rateDate = payload.date || rateDate;
    isLive = !!live;
    publish();
    render();
  }

  /* ── hourly cache (localStorage; this page writes ONLY celFxUsd) ── */
  function readCache() {
    try {
      var raw = window.localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var c = JSON.parse(raw);
      if (!c || !c.rates || !c.ts) return null;
      if (Date.now() - c.ts > TTL) return null;
      return c;
    } catch (e) { return null; }
  }

  function writeCache(payload) {
    try {
      window.localStorage.setItem(CACHE_KEY, JSON.stringify({
        rates: payload.rates, date: payload.date, ts: Date.now()
      }));
    } catch (e) { /* private mode / quota — the baked table still works */ }
  }

  var refreshed = false;
  function refresh() {
    if (refreshed) return;
    refreshed = true;

    var cached = readCache();
    if (cached) { adopt(cached, true); return; }   /* instant, no request */
    if (typeof fetch !== 'function') return;

    var settled = false;
    var timer = setTimeout(function () { settled = true; }, TIMEOUT);

    fetch(ENDPOINT, { mode: 'cors', credentials: 'omit', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        clearTimeout(timer);
        if (settled || !data || !data.rates) return;
        adopt(data, true);
        writeCache(data);
      })
      .catch(function () { clearTimeout(timer); /* baked table stays */ });
  }

  /* ── picker: one column, code + name, full keyboard control ── */
  function options() { return menuEl.querySelectorAll('.fx_option'); }

  function setOpen(open) {
    menuEl.hidden = !open;
    pickEl.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      document.addEventListener('click', onDocClick, true);
    } else {
      document.removeEventListener('click', onDocClick, true);
    }
  }

  function onDocClick(ev) {
    if (menuEl.contains(ev.target) || pickEl.contains(ev.target)) return;
    setOpen(false);
  }

  function choose(btn) {
    if (!btn) return;
    code = btn.getAttribute('data-code');
    var all = options();
    for (var i = 0; i < all.length; i++) {
      var on = all[i] === btn;
      all[i].classList.toggle('is-active', on);
      all[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    setText(pickCodeEl, code);
    /* PUBLISHING: copy the option's OWN <img> rather than rebuilding a flagcdn URL. Every option
       already carries its flag in the markup, so a bundler has inlined those bytes; a URL built in
       JS is invisible to it and unreachable from a published artifact (no CDN fetches). The CDN
       build stays as the fallback for markup that ships an option without an image. */
    var srcImg = btn.querySelector('img');
    var cc = btn.getAttribute('data-flag');
    if (pickFlagEl && srcImg && srcImg.getAttribute('src')) {
      pickFlagEl.src = srcImg.getAttribute('src');
      var ss = srcImg.getAttribute('srcset');
      if (ss) pickFlagEl.srcset = ss; else pickFlagEl.removeAttribute('srcset');
    } else if (pickFlagEl && cc) {
      pickFlagEl.src = 'https://flagcdn.com/w40/' + cc + '.png';
      pickFlagEl.srcset = 'https://flagcdn.com/w80/' + cc + '.png 2x';
    }
    pickEl.setAttribute('aria-label', 'Change currency, currently ' + code);
    setOpen(false);
    pickEl.focus();
    render();
  }

  function focusActive() {
    var target = menuEl.querySelector('.fx_option.is-active') || options()[0];
    if (target) target.focus();
  }

  pickEl.addEventListener('click', function () {
    var open = pickEl.getAttribute('aria-expanded') === 'true';
    setOpen(!open);
    refresh();
    if (!open) focusActive();
  });

  menuEl.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.fx_option') : null;
    if (btn) choose(btn);
  });

  /* ↑/↓ walk the list, Enter picks, Escape closes, a letter jumps to that code */
  menuEl.addEventListener('keydown', function (ev) {
    var all = options();
    var i = Array.prototype.indexOf.call(all, document.activeElement);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      var next = ev.key === 'ArrowDown' ? i + 1 : i - 1;
      if (next < 0) next = all.length - 1;
      if (next >= all.length) next = 0;
      all[next].focus();
      return;
    }
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choose(all[i]); return; }
    if (ev.key === 'Escape') { ev.preventDefault(); setOpen(false); pickEl.focus(); return; }
    if (ev.key && ev.key.length === 1 && /[a-z]/i.test(ev.key)) {
      var letter = ev.key.toUpperCase();
      for (var n = 1; n <= all.length; n++) {
        var cand = all[(Math.max(i, 0) + n) % all.length];
        if (cand.getAttribute('data-code').charAt(0) === letter) { cand.focus(); return; }
      }
    }
  });

  pickEl.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); setOpen(true); refresh(); focusActive(); }
  });

  amountEl.addEventListener('input', function () { render(); refresh(); });

  publish();
  render();   /* instant, from the baked table */

  /* refresh when the card comes into view — a rect check, not IntersectionObserver:
     when IO does not fire, nothing would ever refresh (see costs.js §11) */
  function inView() {
    if (!widgetEl) return true;
    var r = widgetEl.getBoundingClientRect();
    var h = window.innerHeight || document.documentElement.clientHeight;
    return r.top < h + 200 && r.bottom > -200;
  }

  function maybeRefresh() {
    if (!inView()) return;
    window.removeEventListener('scroll', maybeRefresh);
    window.removeEventListener('resize', maybeRefresh);
    refresh();
  }

  window.addEventListener('scroll', maybeRefresh, { passive: true });
  window.addEventListener('resize', maybeRefresh);
  maybeRefresh();
})();
/* ═══════════════════════════════════════════════════════════════════════════
   CEL San Diego — calculator-sandiego-costs.js
   The §4 cost calculator on pages/san-diego/costs.html.
   Engine: shared/calculator.js (load that FIRST — see its header for the API).

   This file is ONLY rates + arithmetic + copy. No DOM, no events, no styling:
   the engine reads the data-calc-* hooks in the markup and writes the results.

   EVERY figure below is published on the page itself (copy SSOT
   pages/san-diego/costs.md §4/§6/§7/§9). Nothing is interpolated — where the
   copy does not publish a short-stay housing rate per residence, the nearest
   PUBLISHED bracket is used and the total is labelled "from" in the markup, with
   the note telling the reader the written quote confirms it. Never invent a
   figure here (DESIGN-RULES.md §1: "never widen or trim a figure").

   MAINTENANCE: when a rate changes, change it here and in costs.md together.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  /* ── published rates ──────────────────────────────────────────────────────
     Tuition US$/week by duration bracket, as [[maxWeeks, rate], …] (§6 tiers).
     GE24 also prices GE23 — §6: "priced the same as General English 24". */
  /* CEL Prices 2026 (agents), San Diego / Courses. Seventeen San Diego courses are
     published there and they collapse to exactly FOUR per-week ladders, because the
     price is set by lessons per week and nothing else:

       20 lessons, no elective          GE20                                    370/360
       23 lessons, 1 elective           GE23 · CD3 · AE3 · TOEFL3 · CAE3        410/400
       24 lessons, 1 elective           GE24 · CD4 · AE4 · TOEFL4 · CAE4        410/400/380/340/320
       28 lessons, 2 electives          GE28 · CD8 · AE8 · TOEFL28 · CAE28      460/450/430/390/370

     So the four options below ARE the whole San Diego course list, not a subset —
     each label names the specialisations that share its ladder. Listing the tracks
     separately would add twelve entries that all compute the same number.

     `visa` is the price list's own VISA TYPE column, not an inference: the 20- and
     23-lesson courses are sold on ESTA/Tourist, the 24- and 28-lesson courses are
     F-1 Student Visa. That column is why GE23 and GE24 could not stay merged behind
     one option — they carry the same 410/400 short-stay rate but different routes,
     so the merged option sent an ESTA student down the F-1 path.

     The list marks the ESTA ladders n/a past 12 weeks (they are not sold that long).
     Per this file's standing convention the nearest PUBLISHED bracket is held rather
     than a rate being invented, and note() says the stay has left ESTA's 90 days.
     GE20's 13+ week brackets are the ones this page's own §6 tuition table publishes.

     NOT modelled here, and deliberately: Global Pathway 28 is a flat US$6,880 for a
     fixed 16 weeks with two start dates a year — a weeks-slider cannot price it
     without lying. Private lessons (US$85/lesson) and the optional Cambridge exam fee
     (US$425) need a quantity input this tool does not have. */
  var COURSES = {
    ge20: { name: 'General English 20', visa: 'esta',
            option: 'General English 20',
            tiers: [[6, 370], [12, 360], [19, 340], [999, 300]] },
    ge23: { name: 'General English 23', visa: 'esta',
            option: 'General English 23 \u00b7 or Career / Academic / Exam 23',
            tiers: [[6, 410], [999, 400]] },
    ge24: { name: 'General English 24', visa: 'f1',
            option: 'General English 24 \u00b7 or Career / Academic / Exam 24',
            tiers: [[6, 410], [12, 400], [19, 380], [29, 340], [999, 320]] },
    ge28: { name: 'General English 28', visa: 'f1',
            option: 'General English 28 \u00b7 or Career / Academic / Exam 28',
            tiers: [[6, 460], [12, 450], [19, 430], [29, 390], [999, 370]] }
  };
  var COURSE_ORDER = ['ge20', 'ge23', 'ge24', 'ge28'];

  /* True when the course is sold on ESTA/Tourist rather than F-1 — the one question
     three separate call sites used to answer by testing for the string 'ge20'. */
  function isEsta(key) {
    var c = COURSES[key] || COURSES.ge20;
    return c.visa === 'esta';
  }

  /* Accommodation US$/week by bracket + the one-time placement fee (§4, §7).
     Standard-season (low-season) rates from CEL Prices 2026 (agents), San Diego /
     Accommodation. Shared-apartment rows are the TWIN room — the rate the page quotes;
     the single-room rate is a different product and is not offered by this tool.
     Homestay rows are the shared-bathroom tiers the page publishes: hss/hsd breakfast,
     hpr breakfast and dinner. Shared apartments bracket at 1-11 / 12-23 / 24+, homestay
     at 1-4 / 5-11 / 12+ — the two are NOT the same ladder, which is why each carries its
     own tier list rather than a shared one.
     2026 update: every short-stay bracket is now PUBLISHED, so the old flat homestay
     rates (which quoted the 12+ figure at every length and under-quoted short stays) and
     the old prm/sup ladders are gone. No figure here is interpolated. */
  var ROOMS = {
    std:  { label: 'Shared apt Standard', fee: 100, tiers: [[11, 290], [23, 280], [999, 270]] },
    prm:  { label: 'Shared apt Premium',  fee: 100, tiers: [[11, 360], [23, 350], [999, 340]] },
    sup:  { label: 'Shared apt Superior', fee: 100, tiers: [[11, 410], [23, 400], [999, 390]] },
    hss:  { label: 'Homestay single',     fee: 200, tiers: [[4, 360], [11, 340], [999, 320]] },
    hsd:  { label: 'Homestay double',     fee: 200, tiers: [[4, 330], [11, 310], [999, 290]] },
    hpr:  { label: 'Premium homestay',    fee: 200, tiers: [[4, 490], [11, 470], [999, 450]] },
    none: { label: 'Own accommodation',   fee: 0,   tiers: [[999, 0]] }
  };

  /* Which residences are homestays — drives the meal/diet caveat in note() and nothing else.
     Kept as a set beside ROOMS so adding a residence cannot leave the caveat behind. */
  var HOMESTAY = { hss: true, hsd: true, hpr: true };

  /* Resolve a flag from the DOM first: the currency menu ships one <img> per currency, so those
     bytes survive bundling. Falls back to the CDN URL when the menu is absent. */
  function flagSrc(cc, size) {
    var sel = 'img[src*="' + size + '/' + cc + '.png"], img[srcset*="' + size + '/' + cc + '.png"]';
    var el = document.querySelector(sel);
    if (el) {
      var attr = size === 'w80' ? (el.getAttribute('srcset') || '') : '';
      if (attr) return attr.split(' ')[0];
      if (size === 'w40') return el.getAttribute('src');
    }
    return 'https://flagcdn.com/' + size + '/' + cc + '.png';
  }

  /* flagcdn country code per currency — real flag artwork, never a hand-drawn SVG */
  var FLAG = {
    AED:'ae', ARS:'ar', AUD:'au', BRL:'br', CAD:'ca', CHF:'ch', CLP:'cl', CNY:'cn',
    COP:'co', CZK:'cz', DKK:'dk', EGP:'eg', EUR:'eu', GBP:'gb', HKD:'hk', HUF:'hu',
    IDR:'id', ILS:'il', INR:'in', JPY:'jp', KRW:'kr', KWD:'kw', MAD:'ma', MXN:'mx',
    MYR:'my', NOK:'no', NZD:'nz', PEN:'pe', PHP:'ph', PLN:'pl', QAR:'qa', RON:'ro',
    RUB:'ru', SAR:'sa', SEK:'se', SGD:'sg', THB:'th', TRY:'tr', TWD:'tw', UAH:'ua',
    USD:'us', VND:'vn', ZAR:'za'
  };

  var REGISTRATION = 150;    /* §4 · one-time */
  var MATERIALS = 10;        /* §4 · per week */
  var INSURANCE_DAY = 4;     /* §9 · US$4 per day through CEL */
  var ESTA = 40.27;          /* §9 */
  var MRV = 185;             /* §9 · visa application fee, F-1 and B1/B2 alike */
  var SEVIS = 350;           /* §9 · F-1 only */
  var ESTA_WEEKS = 12;       /* §6 · ESTA covers ~90 days */

  /* Why THIS route — one sentence per case, from §6 (course/stay rules) and §9 (fees). */
  var ROUTE_WHY = {
    f1: 'The 24- and 28-lesson courses are full-time academic study, so they need an F-1 student visa \u2014 that is also the route for stays past about 6 months.',
    esta: 'Up to about 12 weeks you can study on ESTA or a B1/B2 visitor visa; no student visa is needed.',
    b1b2: 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this length of stay assumes a B1/B2 visitor visa.'
  };
  var ROUTE_FEES = {
    f1: 'SEVIS I-901 US$350 + visa application (MRV) US$185',
    esta: 'ESTA US$40.27',
    b1b2: 'Visa application (MRV) US$185'
  };

  /* Currency symbol for the total's prefix slot. Derived from Intl rather than a hand-kept
     table of 43 symbols; USD is special-cased because the page writes "US$", not "$". Any
     engine that rejects narrowSymbol throws in the constructor and falls through to the ISO
     code, which is always meaningful. */
  function symbolFor(code) {
    if (code === 'USD') return 'US$';
    try {
      var parts = new Intl.NumberFormat('en-US', {
        style: 'currency', currency: code, currencyDisplay: 'narrowSymbol'
      }).formatToParts(0);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === 'currency') return parts[i].value;
      }
    } catch (e) { /* unknown code or no narrowSymbol support */ }
    return code;
  }

  /* Visa route follows the course's published VISA TYPE and the length of stay (§6 + §9).
     Reads COURSES[].visa rather than testing one course key, so adding a course cannot
     leave it silently on the ESTA path. */
  function route(state) {
    var c = COURSES[state.course] || COURSES.ge20;
    if (c.visa === 'f1') {
      return { key: 'f1', chip: 'F-1 visa', label: 'SEVIS I-901 + visa application', cost: SEVIS + MRV };
    }
    if (state.weeks <= ESTA_WEEKS) {
      return { key: 'esta', chip: 'ESTA or B1/B2', label: 'ESTA travel authorization', cost: ESTA };
    }
    return { key: 'b1b2', chip: 'B1/B2 visa', label: 'Visa application (MRV)', cost: MRV };
  }

  /* One honest caveat at a time — never a stack of warnings.
     The old first branch ("stays under 12 weeks pay slightly higher weekly housing rates —
     your written quote confirms the exact figure") existed only because the short-stay
     brackets were not published. The 2026 price list publishes all of them and the tiers
     above now price them exactly, so that sentence is no longer true and is gone. The
     branch it leaves behind carries the homestay surcharge, which IS published and which
     this tool does not model. */
  function note(state) {
    if (HOMESTAY[state.room]) {
      return 'Homestay rates include the meals shown below. A lactose-free, gluten-free or vegan diet adds US$50 a week and a halal diet US$75 \u2014 neither is counted above.';
    }
    if (state.weeks > ESTA_WEEKS && isEsta(state.course)) {
      return 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this budget assumes a B1/B2 visitor visa.';
    }
    return 'Standard-season rates \u2014 accommodation carries a supplement from May 30 to September 26, 2026. Flights, food outside homestay and personal spending are not included.';
  }

  var config = {
    root: 'calcTool',
    chipBase: 'plan_chip',
    state: { weeks: 12, course: 'ge20', room: 'std', insurance: false, visa: false, fx: 'USD' },

    compute: function (s, h) {
      var w = s.weeks;
      var weeks = h.plural(w, 'week', 'weeks');
      /* Guarded like ROOMS below: an empty or unknown course key must degrade to the
         documented default (state.course) rather than throw inside h.bracket() and take
         every later IIFE in this bundle down with it. */
      var course = COURSES[s.course] || COURSES.ge20;
      var tRate = h.bracket(course.tiers, w);
      /* An unknown key renders NOTHING rather than silently borrowing Standard's rate —
         a tile without a published rate must not print another residence's figure. */
      var room = ROOMS[s.room] || ROOMS.none;
      var rRate = h.bracket(room.tiers, w);
      var hasRoom = s.room !== 'none' && !!ROOMS[s.room];
      var r = route(s);

      var tuition = w * tRate;
      var materials = w * MATERIALS;
      var housing = hasRoom ? w * rRate + room.fee : 0;
      var insurance = s.insurance ? w * 7 * INSURANCE_DAY : 0;
      var visa = s.visa ? r.cost : 0;
      var total = tuition + REGISTRATION + materials + housing + insurance + visa;

      /* The TOTAL itself is shown in the currency the reader picks. Rates come from the ONE
         table the §3 converter publishes (window.CELFxRates) — never a second copy here. With
         no rate source, or on US$, the figure stays in dollars and no rate line is printed;
         CEL bills in US$ either way, which the note says whenever a conversion is shown. */
      var fx = window.CELFxRates;
      var fxRate = s.fx && s.fx !== 'USD' && fx && fx.get ? fx.get(s.fx) : null;
      var totalValue = fxRate ? total * fxRate : total;
      /* The currency belongs to the FIGURE, not to a separate slot: the old "from" element sits
         on the far side of the currency picker, so a symbol placed there renders two elements
         away from the number it qualifies ("US$  [USD v]  8,050") and duplicates the picker's
         own label. Prefixing the digits gives "US$8,050" (client, 8 Sep). */
      var totalAmount = (fxRate ? '\u2248' + symbolFor(s.fx) : 'US$') +
                        Math.round(totalValue).toLocaleString('en-US');
      var fxNote = fxRate
        ? '1 US$ = ' + fxRate.toLocaleString(undefined, { maximumFractionDigits: 4 }) + ' ' + s.fx +
          ' \u00b7 ' + ((fx.liveFor ? fx.liveFor(s.fx) : fx.live) ? 'live mid-market rate, ' : 'indicative rate, ') + fx.date +
          '. CEL bills in US$.'
        : '';
      var flagCode = FLAG[s.fx] || 'us';

      return {
        out: {
          fxNote: fxNote,
          fxCode: s.fx,
          /* PUBLISHING: prefer the flag already inlined in the currency menu's own markup — a URL
             built here is invisible to a bundler and unreachable from a published artifact. */
          fxFlag: flagSrc(flagCode, 'w40'),
          fxFlag2x: flagSrc(flagCode, 'w80'),
          weeks: w,
          weeksUnit: w === 1 ? 'week' : 'weeks',
          weeksAria: weeks,
          tuition: h.money(tuition),
          tuitionSub: weeks + ' \u00d7 ' + h.money(tRate),
          materials: h.money(materials),
          materialsSub: weeks + ' \u00d7 ' + h.money(MATERIALS),
          room: h.money(housing),
          roomSub: room.label + ' \u00b7 ' + h.money(rRate) + '/wk + ' + h.money(room.fee) + ' placement',
          insurance: h.money(insurance),
          insuranceSub: (w * 7) + ' days \u00d7 ' + h.money(INSURANCE_DAY),
          visa: h.money(r.cost),
          visaSub: r.label,
          /* the tiles show what THIS length of stay costs per week, not a from-price */
          courseName: course.name,
          courseRate: h.money(tRate) + '/wk',
          roomNote: hasRoom
            ? h.money(rRate) + '/wk + ' + h.money(room.fee) + ' placement fee'
            : 'No CEL accommodation in this budget',
          visaHint: r.cost === ESTA ? 'US$40.27' : h.money(r.cost),
          visaWhy: ROUTE_WHY[r.key],
          visaFees: ROUTE_FEES[r.key],
          totalAmount: totalAmount,
          /* "from" is gone (client, 8 Sep) and is no longer true either: the 2026 list publishes
             every bracket, so this tool prices a stay exactly rather than quoting a from-price.
             The slot is left empty rather than deleted — its live min-width is 0, so an empty
             element collapses to nothing but its 6px margin, and keeping it means the markup can
             carry a prefix again without a rebuild. */
          totalPrefix: '',
          month: h.money(total / (w / 4.345)),
          note: note(s)
        },
        rows: { room: hasRoom, insurance: s.insurance, visa: s.visa },
        flags: {
          'is-over': w > ESTA_WEEKS && isEsta(s.course),
          'is-esta-limit': isEsta(s.course),         /* the 12-week tick only means something on an ESTA course */
          'is-f1': r.key === 'f1',
          /* One root flag per route so the SLIDER can wear the verdict's colour (client, 4 Aug:
             "the progress bar color and the visa color should match"). The chip styles itself from
             its own class; the track sits in a different subtree, so it needs the state on the root. */
          'is-route-esta': r.key === 'esta',
          'is-route-b1b2': r.key === 'b1b2',
          'is-route-f1': r.key === 'f1'
        },
        /* One class per route, not two. b1b2 previously fell through to 'is-esta', so a visitor-visa
         verdict was painted as the visa-free one — the colour said "nothing extra needed" while the
         sentence beside it said the opposite. */
      chips: { visa: { class: 'is-' + r.key, text: r.chip } },
        fill: { weeks: (w - 1) / 35 }
      };
    }
  };

  /* ── PUBLISHING REPAIR ────────────────────────────────────────────────
     Webflow blanks the FIRST <option> value of a Select field, treating it as a
     placeholder: #calcCourse shipped value="" for "ge20", #calcRoom "" for "std".
     The engine reads the DOM over its own state defaults, so TUITION[""] was
     undefined and h.bracket() threw on .length — killing this bundle on load, and
     with it every IIFE that follows. Option values are not reachable through the
     Designer API (a FormSelect exposes no choices setting), so repair them here.

     Reconciles the SET of values, never a position or a label: a reordered list or
     an edited option label cannot mislabel a rate, and anything ambiguous is left
     exactly as authored. */
  function repairSelect(id, expected) {
    var el = document.getElementById(id);
    if (!el || !el.options) return;
    var present = {}, blanks = [], i;
    for (i = 0; i < el.options.length; i++) {
      if (el.options[i].value) present[el.options[i].value] = true;
      else blanks.push(el.options[i]);
    }
    var missing = [];
    for (i = 0; i < expected.length; i++) if (!present[expected[i]]) missing.push(expected[i]);
    if (blanks.length !== 1 || missing.length !== 1) return;   /* ambiguous → leave as authored */
    var wasSelected = el.selectedIndex === blanks[0].index;
    blanks[0].value = missing[0];
    if (wasSelected) el.value = missing[0];
  }
  repairSelect('calcCourse', ['ge20', 'ge24']);
  repairSelect('calcRoom', ['std', 'prm', 'sup', 'hss', 'hsd', 'hpr', 'none']);

  /* ── Add the course options the Designer's Select does not carry ──────
     The 2026 price list has four San Diego ladders (COURSES above); the Webflow
     Select carries two, from when GE23 was merged into the GE24 option. A FormSelect
     exposes NO option-list setting over the Designer API — the same wall that forces
     repairSelect() above — so an option cannot be added by MCP at all. It is added
     here, before mount, or it does not exist.

     Runs AFTER repairSelect so the blanked first option already holds its value and
     is seen as present. Reconciles by VALUE and inserts in COURSE_ORDER, so an option
     added by hand in the Designer later is detected and left alone rather than
     duplicated, and running twice changes nothing. */
  function ensureOptions(id, order, spec) {
    var el = document.getElementById(id);
    if (!el || !el.options) return;
    var have = {}, i;
    for (i = 0; i < el.options.length; i++) {
      if (el.options[i].value) have[el.options[i].value] = el.options[i];
    }
    var prev = null;
    for (i = 0; i < order.length; i++) {
      var key = order[i];
      if (have[key]) { prev = have[key]; continue; }   /* already authored — never touch it */
      if (!spec[key]) continue;
      var opt = document.createElement('option');
      opt.value = key;
      opt.textContent = spec[key].option;
      /* after the previous option in COURSE_ORDER; nextSibling === null appends */
      if (prev && prev.parentNode === el) el.insertBefore(opt, prev.nextSibling);
      else el.insertBefore(opt, el.firstChild);
      have[key] = opt;
      prev = opt;
    }
  }
  ensureOptions('calcCourse', COURSE_ORDER, COURSES);

  /* The GE24 option's label still reads "· or GE23" on the live page — true when the two
     shared one option, wrong now that GE23 is its own entry with its own ESTA route.
     Same wall: a Select option's TEXT is not writable over MCP either. */
  (function () {
    var el = document.getElementById('calcCourse');
    if (!el || !el.options) return;
    for (var i = 0; i < el.options.length; i++) {
      var o = el.options[i];
      if (COURSES[o.value] && o.textContent !== COURSES[o.value].option) {
        o.textContent = COURSES[o.value].option;
      }
    }
  })();

  /* The 43 menu options ship with src="" — Webflow drops external image URLs on publish.
     The picker's own flag recovers through out.fxFlag, but the menu's do not, so rebuild
     them from each option's currency code. An existing src is never overwritten. */
  var fxOpts = document.querySelectorAll('.fx_option[data-calc-value]');
  for (var fi = 0; fi < fxOpts.length; fi++) {
    var fImg = fxOpts[fi].querySelector('img.fx_flag');
    var fCc = FLAG[fxOpts[fi].getAttribute('data-calc-value')];
    if (!fImg || !fCc || fImg.getAttribute('src')) continue;
    fImg.src = 'https://flagcdn.com/w40/' + fCc + '.png';
    fImg.srcset = 'https://flagcdn.com/w80/' + fCc + '.png 2x';
  }

  /* Mount now if the engine is loaded, otherwise queue — the engine flushes the
     queue when it evaluates, so script order can never break the page. */
  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);
  else {
    window.CELCalculator = window.CELCalculator || { __queue: [] };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
/* ═══════════════════════════════════════════════════════════
   CEL San Diego — costs page · page-scoped JS
   Loaded AFTER ../cost-of-studying-english/scripts.js.
   Convention matches that file: one IIFE per behaviour, one unique
   window guard flag, no DOMContentLoaded, no globals beyond the flag.

   DEPLOY: folds into the CEL page-script bundle under
   tools/cel-page-scripts/src/ and ships minified via /deploy-page-scripts.
   It does NOT become a Webflow inline script. Webflow's budget is 15
   scripts per page — this page needs one bundle slot, shared with
   currency.js.
   ═══════════════════════════════════════════════════════════ */

/* ── §3 card 4 — currency converter ──────────────────────────
   MOVED 3 Aug (client direction): the converter lives in its own file,
   pages/san-diego/currency.js, loaded just before this one. It shares no
   state with anything here — do not re-add it to this file.
   ── */

/* ── §6 price-table bars — D1 RESOLVED (handoff review) ──────
   The live VC page's ../cost-of-studying-english/scripts.js animates ONE table
   (document.querySelector('.price-table')), so Table 2 — General English 24 — shipped
   with flat bars. That file is the Vancouver page's and must never be edited, so the
   fix lives here: run the same scaleX reveal over EVERY .price-table on the page.
   · data-tier / data-w are authored on all 14 rows (three tables since the GE28 ladder
     was added 2026-09-08 — the querySelectorAll below picks it up for free), and Table 2's
     price-bar-wrap > price-bar markup was added in the same review — the JS had nothing
     to drive there before that
   · existing WAAPI animations are cancelled first, exactly as the VC file does, so a
     table the VC script already animated is re-driven rather than fighting an IX2 lock
   · a snap fallback writes the final transform if the animation never finishes (a
     document timeline that does not advance would otherwise leave an EMPTY track)
   · reveal is a passive rect check, not IntersectionObserver: when IO does not fire the
     bars would stay at scaleX(0) forever, i.e. permanently wrong (same reasoning as §11)
   · its own guard flag — never reuse __costsPriceBarDone, that is the VC script's
   ── */
(function () {
  if (window.__costsAllPriceBarsDone) return;
  window.__costsAllPriceBarsDone = true;

  var tables = document.querySelectorAll('.price-table');
  if (!tables.length) return;

  var pending = Array.prototype.slice.call(tables);

  function animate(table) {
    var rows = table.querySelectorAll('.price-row[data-w]');
    for (var i = 0; i < rows.length; i++) {
      var bar = rows[i].querySelector('.price-bar');
      if (!bar) continue;
      var w = parseFloat(rows[i].getAttribute('data-w')) || 0.08;
      if (bar.getAnimations) {
        var running = bar.getAnimations();
        for (var a = 0; a < running.length; a++) running[a].cancel();
      }
      var delay = i * 90;
      bar.animate(
        [{ transform: 'scaleX(0)' }, { transform: 'scaleX(' + w + ')' }],
        { delay: delay, duration: 900, easing: 'cubic-bezier(0.16,1,0.3,1)', fill: 'forwards' }
      );
      /* Snap fallback. WAAPI with fill:forwards is correct, but a document timeline
         that never advances — throttled tab, a view that is not painting, a browser
         that drops the animation — would leave the bar at scaleX(0), i.e. a price row
         showing an EMPTY track rather than an un-animated one. Same doctrine as §11
         below: never let a decorative timing failure read as wrong data.
         The running animation must be CANCELLED first: an animation in flight lives in
         the animation cascade origin, which outranks inline style, so writing the
         transform while it is still running has no effect at all. */
      (function (el, width) {
        setTimeout(function () {
          var live = el.getAnimations ? el.getAnimations() : [];
          for (var n = 0; n < live.length; n++) {
            if (live[n].playState === 'finished') return;   /* it ran — leave it alone */
          }
          for (var c = 0; c < live.length; c++) live[c].cancel();
          /* transitions are on the same frozen clock, so a transitioned snap would
             never arrive either — the fallback paints, it does not animate */
          el.style.transition = 'none';
          el.style.transform = 'scaleX(' + width + ')';
        }, delay + 1100);
      })(bar, w);
    }
  }

  function sweep() {
    var h = window.innerHeight || document.documentElement.clientHeight;
    for (var i = pending.length - 1; i >= 0; i--) {
      var r = pending[i].getBoundingClientRect();
      if (r.top < h * 0.85 && r.bottom > 0) {
        animate(pending[i]);
        pending.splice(i, 1);
      }
    }
    if (!pending.length) {
      window.removeEventListener('scroll', sweep);
      window.removeEventListener('resize', sweep);
    }
  }

  window.addEventListener('scroll', sweep, { passive: true });
  window.addEventListener('resize', sweep);
  sweep();
})();

/* ── §11 mobile sticky CTA bar — reveal after the hero ────────
   The bar is fixed to the viewport bottom, so at every width ≤991px it would sit
   directly on top of the hero's own .hero_actions row (the hero is full-fold, its
   CTAs live in the bottom ~75px). DESIGN-RULES.md §6.6: all hero content visible
   without scrolling. So the bar stays translated out of view until the hero CTA row
   has scrolled past, then slides in.

   Driven by a passive scroll listener, NOT an IntersectionObserver. IO is the site
   convention (see the TOC scroll-spy) but it is the wrong tool here: when IO does not
   fire — throttled rAF, a non-painting tab, a browser without it — the spy merely
   looks frozen, whereas this bar would never appear at all, silently killing the
   mobile CTA. A scrollY comparison always resolves. The handler is synchronous and
   state-guarded (see the note on apply), and above 991px the bar is display:none so
   the work is inert.

   `is-visible` is a runtime state and is added HERE, never authored in costs.html
   (CLASS-CONTRACT.md §1, corollary 2). The CSS lives in costs.css block B (B6).
   ── */
(function () {
  if (window.__costsStickyCtaDone) return;
  window.__costsStickyCtaDone = true;

  var bar = document.querySelector('.sticky-cta_bar');
  if (!bar) return;

  var anchor = document.querySelector('.hero_actions');
  /* Nothing to clear: show it and move on — the bar must never be the reason a CTA
     is unreachable. */
  if (!anchor) {
    bar.classList.add('is-visible');
    return;
  }

  var threshold = 0;
  var shown = false;

  function measure() {
    var top = 0;
    for (var el = anchor; el; el = el.offsetParent) top += el.offsetTop;
    threshold = top + anchor.offsetHeight;
  }

  /* Synchronous on purpose. A requestAnimationFrame-coalesced handler looks tidier but
     it is a correctness bug here: in a throttled or non-painting tab the frame never
     arrives, the "queued" latch never clears, and the bar is stuck for the rest of the
     page's life. Two reads plus a state-guarded classList write is cheaper than the
     latch it replaces. */
  function apply() {
    var y = window.pageYOffset || document.documentElement.scrollTop || 0;
    var next = y > threshold;
    if (next === shown) return;
    shown = next;
    bar.classList.toggle('is-visible', next);
    /* The bar is hidden with opacity:0 + pointer-events:none, which leaves its two links in the
       tab order and the accessibility tree — measured 2 focusable links inside an opacity:0
       ancestor at every width <=991. `inert` removes both without touching any visual property,
       so the fade is unchanged. */
    bar.inert = !next;
  }

  /* apply() early-returns when the state has not changed, so the initial hidden state has to be
     stamped here or the bar ships focusable on first paint. */
  bar.inert = true;

  measure();
  apply();
  window.addEventListener('scroll', apply, { passive: true });
  window.addEventListener('resize', function () { measure(); apply(); }, { passive: true });
})();

/* ── §2 TOC — the mobile drawer closes itself now ────────────
   celtocmob2 put `is-menu-open` on #tocSidebar (the .stoc_component), so this
   page carried a patch that stripped it after a jump. celtocmob3 v2.0.0 —
   shipped in cel-cost-of-studying-english.min.js, which this page also loads —
   puts the class on .stoc_label/.stoc_nav where the stylesheet actually
   defines it, and closes on link click itself. The patch removed 2026-09-02:
   it listened for a class that is no longer set anywhere.
   ── */

/* ── §3 TOC toggle — make the <=991 drawer reachable by keyboard ─────────────
   The drawer's trigger ships from Webflow as `<p class="stoc_label">On this page</p>`.
   celtocmob3 (in cel-cost-of-studying-english.min.js) writes `aria-expanded` onto it and binds a
   keydown handler — but a <p> has no role and no tab stop, so that handler can never fire and the
   element is never announced. Measured on the live page (2026-09-08 responsiveness audit): a full
   focus walk finds 8 TOC stops at 1440 and ZERO at 375, because the <=991 rule
   `.stoc_nav{visibility:hidden}` also removes all eight links from the tab order. Below 992px the
   table of contents for an ~18,000px document was therefore pointer-only — WCAG 2.1.1, Level A.

   This only promotes the existing element to a real control; it does not re-implement opening.
   celtocmob3 still owns the click handler, and Enter/Space here are forwarded to it as a click so
   there is exactly one code path for opening the drawer.

   Not fixed here: the element should be a Button or Link Block in the Designer. That is an element
   rebuild, so the runtime promotion is the page-scoped half of it. */
(function () {
  if (window.__costsTocA11yDone) return;
  window.__costsTocA11yDone = true;

  var label = document.querySelector('.stoc_label');
  var nav = document.querySelector('.stoc_nav');
  if (!label || !nav) return;
  /* If Webflow is ever changed to ship a real control, leave it alone. */
  if (/^(a|button)$/i.test(label.tagName)) return;

  if (!nav.id) nav.id = 'stoc-nav';
  label.setAttribute('role', 'button');
  label.setAttribute('tabindex', '0');
  label.setAttribute('aria-controls', nav.id);
  if (!label.hasAttribute('aria-expanded')) label.setAttribute('aria-expanded', 'false');

  label.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    e.preventDefault();          /* stop Space from scrolling the page */
    label.click();               /* one owner for open/close: celtocmob3's click handler */
  });

  /* Escape closes the drawer and returns focus to the trigger. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (label.getAttribute('aria-expanded') !== 'true') return;
    label.click();
    label.focus();
  });
})();


/* ── §4 FAQ — collapsed answers must leave the tab order ─────────────────────
   The accordion collapses an answer with `max-height:0; overflow:hidden` and leaves
   `visibility:visible`, so every link inside a closed panel stays focusable and stays in the
   accessibility tree. Measured on the live page (2026-09-08): 9 of 9 panels closed, 4 focusable
   links inside three of them — a keyboard user tabs into links they cannot see.

   `inert` is used rather than `visibility:hidden` because `.faq-body` animates `max-height` over
   .38s; toggling visibility would either hide the text abruptly on close or force this file to
   restate Webflow's whole `transition` shorthand, which would then drift if that value changed.
   `inert` touches no visual property at all.

   The open-state hook is `data-faq-open` on `.faq-item`. Measured: the attribute does NOT exist
   until the first interaction, so "absent" has to be read as closed — hence the `!== 'true'` test
   rather than `=== 'false'`. The accordion itself lives in cel-cost-of-studying-english.min.js,
   which is why this observes rather than hooks the toggle. */
(function () {
  if (window.__costsFaqInertDone) return;
  window.__costsFaqInertDone = true;

  var items = [].slice.call(document.querySelectorAll('.faq-item'));
  if (!items.length) return;

  function sync(item) {
    var body = item.querySelector('.faq-body');
    if (!body) return;
    body.inert = item.getAttribute('data-faq-open') !== 'true';
  }

  items.forEach(function (item) {
    sync(item);
    new MutationObserver(function () { sync(item); })
      .observe(item, { attributes: true, attributeFilter: ['data-faq-open'] });
  });
})();

/* RESPONSIVE REPAIR 2026-09-08 — hero backdrop resolution on tall/narrow boxes.
   The hero image is `object-fit:cover` in a `min-height:100vh` box, but Webflow
   generates `sizes="(max-width:2560px) 100vw, 2560px"` — which describes the box's
   WIDTH only. Cover scales the source by max(boxW/srcW, boxH/srcH), so on a
   portrait viewport the height drives the scale and the width-derived candidate is
   far too small. Measured at 375x900 on a 16:9 source: the browser picks the 500w
   candidate (real file 500x281) and paints it at 3.2x, cropped to a 117px-wide
   strip of the original. The needed source is ~1600w.
   This computes the width cover actually needs, and only intervenes when the
   current pick is materially short — so it is a no-op at 1440 and 1920, where the
   width-derived candidate is already correct. It also promotes the LCP image out
   of `loading="lazy"`, which Webflow puts on every image including this one. */
(function () {
  if (window.__celHeroImg) return;
  window.__celHeroImg = true;
  var hero = document.querySelector('.section_hero, .abouthero');
  if (!hero) return;
  var img = hero.querySelector('img.hero_bg-image, img.abouthero_bg-image')
         || hero.querySelector('img');
  if (!img || !img.srcset) return;

  /* Real candidate widths, from the srcset itself — naturalWidth is
     density-corrected for a srcset image and cannot be compared against them. */
  var cands = img.srcset.split(',').map(function (c) {
    var m = c.trim().match(/(\S+)\s+(\d+)w$/);
    return m ? { url: m[1], w: +m[2] } : null;
  }).filter(Boolean).sort(function (a, b) { return a.w - b.w; });
  if (!cands.length) return;

  img.setAttribute('fetchpriority', 'high');
  if (img.getAttribute('loading') === 'lazy') img.setAttribute('loading', 'eager');

  function need() {
    var r = img.getBoundingClientRect();
    if (!r.width || !r.height) return 0;
    var aspect = img.naturalWidth && img.naturalHeight
      ? img.naturalWidth / img.naturalHeight : 16 / 9;   /* ratio survives density correction */
    var dpr = window.devicePixelRatio || 1;
    return Math.ceil(Math.max(r.width, r.height * aspect) * dpr);
  }

  function apply() {
    var w = need();
    if (!w) return;
    var r = img.getBoundingClientRect();
    /* Only when the cover crop needs materially more than the box width — i.e.
       exactly the portrait case Webflow's `sizes` cannot describe. */
    if (w < r.width * (window.devicePixelRatio || 1) * 1.15) return;
    /* 5% tolerance: a 1600w candidate for a 1608px need is a 0.5% shortfall no one
       can see, and the next step up is a 2000px JPEG on a phone. */
    var pick = cands.filter(function (c) { return c.w >= w * 0.95; })[0] || cands[cands.length - 1];
    var cur = (img.currentSrc || '').split('/').pop();
    var have = (cands.filter(function (c) { return c.url.split('/').pop() === cur; })[0] || {}).w || 0;
    if (have >= pick.w) return;                 /* already good enough */
    /* Write the CANDIDATE's width, not the raw need: `sizes:1608px` makes the
       browser reach past a 1600w file to a 2000w one for a 0.5% gain. */
    img.setAttribute('sizes', pick.w + 'px');
  }

  apply();
  if (img.complete) apply(); else img.addEventListener('load', apply, { once: true });
  var queued = 0;
  window.addEventListener('resize', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { queued = 0; apply(); });
  }, { passive: true });
})();

/* RESPONSIVE REPAIR 2026-09-08 — keyboard-reachable horizontal scrollers.
   A scroll container with no focusable descendant and no tabindex cannot be
   reached or scrolled from the keyboard, so whatever it hides is pointer-only.
   Only the boxes that ACTUALLY overflow are marked, re-evaluated on resize, so
   this adds no tab stops at the widths where they fit. */
(function () {
  if (window.__celScrollA11y) return;
  window.__celScrollA11y = true;
  var boxes = [].slice.call(document.querySelectorAll('.feetable, .compare-table'));
  if (!boxes.length) return;
  function label(box) {
    var head = box.querySelector('.feetable_headcell, .compare-duration');
    var txt = head ? (head.textContent || '').trim() : '';
    return txt ? 'Table: ' + txt + ' \u2014 scrollable' : 'Scrollable table';
  }
  function sync() {
    boxes.forEach(function (box) {
      var scrolls = box.scrollWidth > box.clientWidth + 1;
      if (scrolls) {
        if (box.getAttribute('tabindex') !== '0') {
          box.setAttribute('tabindex', '0');
          box.setAttribute('role', 'region');
          box.setAttribute('aria-label', label(box));
        }
      } else if (box.getAttribute('tabindex') === '0') {
        box.removeAttribute('tabindex');
        box.removeAttribute('role');
        box.removeAttribute('aria-label');
      }
    });
  }
  var queued = 0;
  window.addEventListener('resize', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { sync(); queued = 0; });
  }, { passive: true });
  sync();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(sync);
})();
