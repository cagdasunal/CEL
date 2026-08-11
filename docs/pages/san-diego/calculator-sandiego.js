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

  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);
  else {
    window.CELCalculator = window.CELCalculator || { __queue: [] };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
