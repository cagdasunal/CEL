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
   · data-tier / data-w are already authored on all 9 rows (both tables), and Table 2's
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
  }

  measure();
  apply();
  window.addEventListener('scroll', apply, { passive: true });
  window.addEventListener('resize', function () { measure(); apply(); }, { passive: true });
})();

/* ── §2 TOC — close the mobile drawer after a jump ────────────
   ../cost-of-studying-english/scripts.js closes .is-menu-open only for clicks OUTSIDE
   .stoc_component, so tapping a link left the drawer open on top of the section it had
   just jumped to (it is position:fixed at ≤991px). Own guard flag; the VC script is
   never edited. Desktop is untouched — the drawer classes only exist ≤991px.
   ── */
(function () {
  if (window.__costsTocCloseOnJumpDone) return;
  window.__costsTocCloseOnJumpDone = true;

  var sidebar = document.getElementById('tocSidebar');
  if (!sidebar) return;

  sidebar.addEventListener('click', function (e) {
    var link = e.target.closest ? e.target.closest('.stoc_link') : null;
    if (!link) return;
    if (window.innerWidth > 991) return;
    sidebar.classList.remove('is-menu-open');
  });
})();
