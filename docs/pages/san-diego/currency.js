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
