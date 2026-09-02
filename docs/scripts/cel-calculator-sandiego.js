/*!
 * CEL — cel-calculator-sandiego.js
 * Page config for the §16 study-budget & visa planner in the #budget section of
 * /san-diego-ca/san-diego. Verbatim from the design project's
 * pages/san-diego/calculator-sandiego.js — it owns only the rates, the
 * arithmetic and the copy; every mechanic comes from cel-calculator.min.js.
 * REQUIRES cel-calculator.min.js to be loaded (before or after — it queues).
 */
/* ═══════════════════════════════════════════════════════════════════════════
   CEL San Diego — calculator-sandiego.js
   The §16 study-budget & visa planner on pages/san-diego/san-diego.html.
   Engine: shared/calculator.js (load that FIRST — see its header for the API).

   Replaces the old §16 inline <script>. Same behaviour, same markup classes
   (plan_*), same numbers — the arithmetic and copy live here, the mechanics
   (tweened figures, slider fill, radio groups, verdict panels, chip pop, the
   one-click fixes) come from the shared engine.

   STARTING PRICES ONLY, as the section's callout states: courses from
   US$300/week, CEL housing from US$270/week. The full itemised calculation is
   the §4 calculator on /san-diego-ca/cost-of-studying-english.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  var COURSE = 300;        /* US$/week, from-price (§16 callout) */
  var HOUSE = 270;         /* US$/week, CEL housing from-price */
  var ESTA_WEEKS = 12;     /* ESTA / visa-waiver caps at 90 days ≈ 12 weeks */
  var MAX_WEEKS = 52;      /* matches the range input's max */

  var CHIP = {
    f1:   { class: 'is-f1',   text: 'F-1 Student Visa' },
    esta: { class: 'is-esta', text: 'ESTA \u2014 no visa needed' },
    cap:  { class: 'is-cap',  text: 'Over the 90-day limit' }
  };

  var config = {
    root: 'plan-tool',
    chipBase: 'plan_chip',
    state: { weeks: 12, pace: 'full', home: 'cel' },

    compute: function (s, h) {
      var w = s.weeks;
      var weeks = h.plural(w, 'week', 'weeks');
      var tuition = w * COURSE;
      var housing = s.home === 'cel' ? w * HOUSE : 0;

      /* 24+ lessons a week is full-time study → F-1 at any length. Part-time is
         visa-free up to the 90-day window, and over it the tool goes into the cap
         state, which offers the two one-click fixes in the markup. */
      var visa = s.pace === 'full' ? 'f1' : (w > ESTA_WEEKS ? 'cap' : 'esta');

      return {
        out: {
          weeks: w,
          weeksUnit: w === 1 ? 'week' : 'weeks',
          weeksAria: weeks,
          tuition: h.number(tuition),
          tuitionMath: weeks + ' \u00d7 from US$' + COURSE,
          housing: h.number(housing),
          housingMath: housing ? weeks + ' \u00d7 from US$' + HOUSE : 'arranged by you',
          total: h.number(tuition + housing),
          capWeeks: w,
          visa: visa
        },
        rows: { housing: !!housing },
        flags: {
          'is-part': s.pace === 'part',
          'is-over': s.pace === 'part' && w > ESTA_WEEKS,
          /* One root flag per verdict so the SLIDER can wear the verdict's colour, exactly as the
             costs-page calculator does (client, 4 Aug: "update the coloring in the slider for
             san-diego.html ... it should use similar ux, styling and coloring"). The chip styles
             itself from its own class; the track is in another subtree and needs the state on the
             root. is-over stays — the one-click fixes and the scale still read it. */
          'is-route-esta': visa === 'esta',
          'is-route-f1': visa === 'f1',
          'is-route-cap': visa === 'cap'
        },
        chips: { visa: CHIP[visa] },
        fill: { weeks: (w - 1) / (MAX_WEEKS - 1) }
      };
    }
  };

  /* ── Deploy repair 1: the two plan-tool selects lost their first option's value.
     Live markup is <option value="">24 or more — full-time</option> and
     <option value="">CEL Apartments</option>; the source declares value="full"
     and value="cel". This is NOT cosmetic: the engine treats markup as the source
     of truth for initial state, so an empty first option loads state.pace="" and
     state.home="" — which makes `s.home === 'cel'` false and zeroes the housing
     line, and makes `s.pace === 'full'` false and mis-routes the visa verdict to
     ESTA. It also breaks the page's own data-calc-set="pace:full" shortcut, which
     can never match a value no option carries.

     Webflow stores select choices as element settings, not child elements, and
     that surface is not writable over MCP (set_settings rejects `choices` as
     "not applicable to this element"), so the values are restored here, before
     mount. Idempotent, and a silent no-op once the Designer is corrected. */
  const restoreOptionValue = function (id, value) {
    const sel = document.getElementById(id);
    if (!sel || !sel.options || !sel.options.length) return;
    if (sel.options[0].value === '') sel.options[0].value = value;
    if (sel.selectedIndex < 0) sel.selectedIndex = 0;
    if (sel.value === '') sel.value = value;
  };
  restoreOptionValue('plan-pace', 'full');
  restoreOptionValue('plan-home', 'cel');

  /* ── Deploy repair 2: @keyframes planRise / planPop reach the page from nowhere.
     Webflow style objects cannot hold at-rules, and this page's head custom code is
     their documented home — but set_page_freeform_code currently returns HTTP 406
     for every write to this page, including a byte-identical rewrite of what is
     already stored. rules/webflow-javascript.md §1 exempts
     tools/cel-page-scripts/src/*.js from the no-inject rule for a bundle's own
     self-contained component CSS, which is exactly what these are: both selectors
     are states this script drives. Scoped to plan_* so it stays page-local instead
     of riding along in the shared engine. Move to head code once the 406 clears. */
  const injectPlanKeyframes = function () {
    if (document.getElementById('cel-plan-keyframes')) return;
    const css =
      '@keyframes planRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}' +
      '@keyframes planPop{0%{transform:scale(.82)}100%{transform:scale(1)}}' +
      '.plan_visa-state.is-on{animation:planRise .5s cubic-bezier(0.16,1,0.3,1)}' +
      '.plan_chip.is-pop{animation:planPop .45s cubic-bezier(0.34,1.56,0.64,1)}' +
      '@media (prefers-reduced-motion:reduce){' +
      '.plan_visa-state.is-on,.plan_chip.is-pop{animation:none}}';
    const st = document.createElement('style');
    st.id = 'cel-plan-keyframes';
    st.appendChild(document.createTextNode(css));
    (document.head || document.documentElement).appendChild(st);
  };
  injectPlanKeyframes();

  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);
  else {
    window.CELCalculator = window.CELCalculator || { __queue: [] };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
