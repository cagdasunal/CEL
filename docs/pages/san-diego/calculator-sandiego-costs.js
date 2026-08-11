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
  var COURSE_NAME = { ge20: 'General English 20', ge24: 'General English 24 / GE23' };

  var TUITION = {
    ge20: [[6, 370], [12, 360], [19, 340], [999, 300]],
    ge24: [[6, 410], [12, 400], [19, 380], [29, 340], [999, 320]]
  };

  /* Accommodation US$/week by bracket + the one-time placement fee (§4, §7). */
  var ROOMS = {
    std:  { label: 'Shared apt Standard', fee: 100, tiers: [[11, 290], [23, 280], [999, 270]] },
    prm:  { label: 'Shared apt Premium',  fee: 100, tiers: [[23, 350], [999, 320]] },
    sup:  { label: 'Shared apt Superior', fee: 100, tiers: [[23, 400], [999, 380]] },
    hss:  { label: 'Homestay single',     fee: 200, tiers: [[999, 320]] },
    hsd:  { label: 'Homestay double',     fee: 200, tiers: [[999, 290]] },
    hpr:  { label: 'Premium homestay',    fee: 200, tiers: [[999, 420]] },
    none: { label: 'Own accommodation',   fee: 0,   tiers: [[999, 0]] }
  };

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
    f1: 'General English 24 is a full-time academic course, so it needs an F-1 student visa \u2014 that is also the route for stays past about 6 months.',
    esta: 'Up to about 12 weeks you can study on ESTA or a B1/B2 visitor visa; no student visa is needed.',
    b1b2: 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this length of stay assumes a B1/B2 visitor visa.'
  };
  var ROUTE_FEES = {
    f1: 'SEVIS I-901 US$350 + visa application (MRV) US$185',
    esta: 'ESTA US$40.27',
    b1b2: 'Visa application (MRV) US$185'
  };

  /* Visa route follows the course and the length of stay (§6 + §9). */
  function route(state) {
    if (state.course === 'ge24') {
      return { key: 'f1', chip: 'F-1 visa', label: 'SEVIS I-901 + visa application', cost: SEVIS + MRV };
    }
    if (state.weeks <= ESTA_WEEKS) {
      return { key: 'esta', chip: 'ESTA or B1/B2', label: 'ESTA travel authorization', cost: ESTA };
    }
    return { key: 'b1b2', chip: 'B1/B2 visa', label: 'Visa application (MRV)', cost: MRV };
  }

  /* One honest caveat at a time — never a stack of warnings. */
  function note(state) {
    if (state.weeks < 12 && state.room !== 'none' && ROOMS[state.room]) {
      return 'Stays under 12 weeks pay slightly higher weekly housing rates \u2014 your written quote confirms the exact figure.';
    }
    if (state.weeks > ESTA_WEEKS && state.course === 'ge20') {
      return 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this budget assumes a B1/B2 visitor visa.';
    }
    return 'Standard-season rates. Flights, food outside homestay and personal spending are not included.';
  }

  var config = {
    root: 'calcTool',
    chipBase: 'calc_chip',
    state: { weeks: 12, course: 'ge20', room: 'std', insurance: false, visa: false, fx: 'USD' },

    compute: function (s, h) {
      var w = s.weeks;
      var weeks = h.plural(w, 'week', 'weeks');
      var tRate = h.bracket(TUITION[s.course], w);
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
      /* The symbol is the select's own label, so the figure is the NUMBER only. */
      var totalAmount = Math.round(totalValue).toLocaleString('en-US');
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
          courseName: COURSE_NAME[s.course] || COURSE_NAME.ge20,
          courseRate: h.money(tRate) + '/wk',
          roomNote: hasRoom
            ? h.money(rRate) + '/wk + ' + h.money(room.fee) + ' placement fee'
            : 'No CEL accommodation in this budget',
          visaHint: r.cost === ESTA ? 'US$40.27' : h.money(r.cost),
          visaWhy: ROUTE_WHY[r.key],
          visaFees: ROUTE_FEES[r.key],
          totalAmount: totalAmount,
          /* "from" only qualifies the US$ figure; a converted one is already approximate */
          totalPrefix: fxRate ? '\u2248' : 'from',
          month: h.money(total / (w / 4.345)),
          note: note(s)
        },
        rows: { room: hasRoom, insurance: s.insurance, visa: s.visa },
        flags: {
          'is-over': w > ESTA_WEEKS && s.course === 'ge20',
          'is-esta-limit': s.course === 'ge20',      /* the tick only means something on GE20 */
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

  /* Mount now if the engine is loaded, otherwise queue — the engine flushes the
     queue when it evaluates, so script order can never break the page. */
  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);
  else {
    window.CELCalculator = window.CELCalculator || { __queue: [] };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
