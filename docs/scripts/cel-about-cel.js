/*!
 * CEL — /about-cel page bundle
 * The Claude Design source for this page ships NO inline JavaScript, so every behaviour the
 * markup implies (TOC spy, team tabs, team slider, timeline activation, hero parallax) is
 * authored here against the classes and data attributes the page actually carries.
 * Deployed minified as cel-about-cel.min.js — see tools/cel-page-scripts/build.sh
 */

/* 1. Webflow w--current cleanup on same-page anchors. */
(function () {
  if (window.__celAboutCurrent) return;
  window.__celAboutCurrent = true;
  function clean() {
    document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current')
      .forEach(function (e) { e.classList.remove('w--current'); });
  }
  setInterval(clean, 300);
  clean();
})();

/* 2. TOC scroll-spy (same contract as the San Diego pages: .stoc_link[data-target]). */
(function () {
  if (window.__celToc) return;
  window.__celToc = true;
  var links = [].slice.call(document.querySelectorAll('.stoc_link[data-target]'));
  if (!links.length) return;
  var targets = links.map(function (l) { return l.dataset.target; });
  var sections = targets.map(function (t) { return document.getElementById(t); }).filter(Boolean);
  if (!sections.length) return;
  var navbar = document.querySelector('.navbar_component');
  var label = document.querySelector('.stoc_label');
  links.forEach(function (l) { l.removeAttribute('href'); l.setAttribute('tabindex', '0'); });
  function setActive(id) {
    links.forEach(function (l) {
      var on = l.dataset.target === id;
      var dot = l.querySelector('.stoc_dot');
      var txt = l.querySelector('.stoc_text');
      l.classList.toggle('is-active', on);
      if (dot) dot.classList.toggle('is-active', on);
      if (txt) txt.classList.toggle('is-active', on);
    });
    if (label) {
      var cur = links.filter(function (l) { return l.dataset.target === id; })[0];
      if (cur) {
        var t = cur.querySelector('.stoc_text');
        label.textContent = t ? t.textContent.trim() : cur.textContent.trim();
      }
    }
  }
  function spy() {
    var edge = (navbar ? navbar.offsetHeight : 90) + 40;
    var id = sections[0].id;
    sections.forEach(function (s) { if (s.getBoundingClientRect().top <= edge) id = s.id; });
    setActive(id);
  }
  var queued = 0;
  window.addEventListener('scroll', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { spy(); queued = 0; });
  }, { passive: true });
  links.forEach(function (l) {
    l.addEventListener('click', function (e) {
      e.preventDefault();
      var s = document.getElementById(l.dataset.target);
      if (!s) return;
      setActive(l.dataset.target);
      window.scrollTo({
        top: s.getBoundingClientRect().top + window.scrollY - (navbar ? navbar.offsetHeight : 90) - 24,
        behavior: 'smooth'
      });
    });
    l.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); l.click(); }
    });
  });
  var hash = location.hash.replace('#', '');
  if (targets.indexOf(hash) !== -1) setActive(hash); else spy();
})();

/* 3. Native Webflow Tabs integration.
   #team was rebuilt on a native Tabs component (TabsWrapper > TabsMenu/TabsLink + TabsContent >
   TabsPane), so WEBFLOW owns tab switching now. The block that used to do it here is gone: it
   selected `.team_tab[data-tab]` and native tabs carry `data-w-tab`, so after the rebuild it
   matched 0 elements and returned at its first guard.
   What still has to happen on a tab change is measurement. An inactive TabsPane is display:none,
   so its track reports clientWidth 0 and any progress computed while hidden is meaningless. Webflow
   fades the panes over ~300ms (data-duration-in), so re-measure once the swap has settled.
   Note for anyone testing this in automation: Webflow's pane swap is requestAnimationFrame-driven,
   and rAF does not run in a hidden/background tab — the tabs will look stuck. That is the harness,
   not the page. */
(function () {
  if (window.__celAboutTeamTabs) return;
  window.__celAboutTeamTabs = true;
  var menu = document.querySelector('.team_tabs');
  if (!menu) return;

  function announce() {
    var pane = document.querySelector('.w-tab-pane.w--tab-active');
    var slider = pane && pane.querySelector('.team-slider_el');
    document.dispatchEvent(new CustomEvent('cel:teamTabChange', {
      detail: { tab: pane ? pane.getAttribute('data-w-tab') : null, slider: slider || null }
    }));
  }

  menu.addEventListener('click', function (e) {
    if (!e.target.closest || !e.target.closest('.w-tab-link')) return;
    /* once for an instant swap, once after the fade Webflow declares on the wrapper */
    setTimeout(announce, 60);
    setTimeout(announce, 420);
  });
  window.addEventListener('resize', announce);
})();

/* 4. Team card sliders — arrows + progress bar, ONE PER TAB PANE.
   The rebuild duplicated .card-slider_nav into every pane (three of them). This block used to do
   `document.querySelector('.card-slider_nav')`, which wired only the first: measured on the live
   page, the Admission and Teachers progress fills were never set and their arrows had no listeners
   at all. Each nav is now bound to the slider inside ITS OWN pane.
   Movement is native scroll on the track (see the `#team .swiper-wrapper` rule in
   cel-about-cel.css). Swiper is used instead when the library is present — this bundle does not
   ship the __swR loader, but the swiperReady guard means the panes upgrade themselves if one is
   ever added. */
(function () {
  if (window.__celAboutSlider) return;
  window.__celAboutSlider = true;

  var sliders = [].slice.call(document.querySelectorAll('.card-slider_nav')).map(function (nav) {
    var scope = (nav.closest && nav.closest('.w-tab-pane')) || nav.parentNode;
    return {
      nav: nav,
      el: scope.querySelector('.team-slider_el'),
      track: scope.querySelector('.swiper-wrapper'),
      prev: nav.querySelector('[data-slide="prev"]'),
      next: nav.querySelector('[data-slide="next"]'),
      fill: nav.querySelector('.team-slider_fill')
    };
  }).filter(function (s) { return s.el && s.track; });
  if (!sliders.length) return;

  function visible(track) {
    return [].slice.call(track.querySelectorAll('.swiper-slide.is-team'))
      .filter(function (s) { return s.style.display !== 'none'; });
  }
  function step(track) {
    var v = visible(track);
    return v.length > 1 ? (v[1].offsetLeft - v[0].offsetLeft) : (v[0] ? v[0].offsetWidth + 16 : 300);
  }
  function progress(s) {
    /* A pane that is still display:none measures 0 for both — leave its nav untouched rather
       than painting a bogus 4% fill and a wrongly-disabled arrow. */
    if (!s.track.clientWidth) return;
    var max = s.track.scrollWidth - s.track.clientWidth;
    var p = max > 0 ? (s.track.scrollLeft / max) : 0;
    if (s.fill) s.fill.style.width = Math.max(4, Math.min(100, p * 100)) + '%';
    if (s.prev) s.prev.classList.toggle('is-disabled', s.track.scrollLeft <= 1);
    if (s.next) s.next.classList.toggle('is-disabled', max <= 0 || s.track.scrollLeft >= max - 1);
  }
  function go(s, dir) {
    if (s.el.swiper) { dir < 0 ? s.el.swiper.slidePrev() : s.el.swiper.slideNext(); return; }
    s.track.scrollBy({ left: dir * step(s.track), behavior: 'smooth' });
  }
  function refresh() { sliders.forEach(progress); }

  sliders.forEach(function (s) {
    if (s.prev) s.prev.addEventListener('click', function (e) { e.preventDefault(); go(s, -1); });
    if (s.next) s.next.addEventListener('click', function (e) { e.preventDefault(); go(s, 1); });
    [s.prev, s.next].forEach(function (b) {
      if (!b) return;
      b.setAttribute('tabindex', '0');
      b.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); b.click(); }
      });
    });
    s.track.addEventListener('scroll', function () { progress(s); }, { passive: true });
  });

  function initSwipers() {
    if (!window.Swiper) return;
    sliders.forEach(function (s) {
      if (s.el.swiper) return;
      try {
        new window.Swiper(s.el, {
          slidesPerView: 'auto',
          spaceBetween: 16,
          watchOverflow: true,
          on: { init: refresh, slideChange: refresh, resize: refresh }
        });
      } catch (err) { /* fall through to native scroll */ }
    });
  }
  if (window.Swiper) initSwipers();
  else document.addEventListener('swiperReady', initSwipers);

  window.addEventListener('resize', refresh);
  document.addEventListener('cel:teamTabChange', refresh);
  refresh();
})();

/* 5. Timeline — mark the entry nearest the viewport centre as active. Purely additive: the
   markup already ships one is-active and one is-now, so with JS off the section still reads. */
(function () {
  if (window.__celAboutTimeline) return;
  window.__celAboutTimeline = true;
  var items = [].slice.call(document.querySelectorAll('.timeline_item'));
  if (items.length < 2) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  function mark() {
    var mid = window.innerHeight / 2;
    var best = null;
    var bestD = Infinity;
    items.forEach(function (it) {
      var r = it.getBoundingClientRect();
      var d = Math.abs(r.top + r.height / 2 - mid);
      if (d < bestD) { bestD = d; best = it; }
    });
    items.forEach(function (it) {
      var on = it === best;
      it.classList.toggle('is-active', on);
      var ring = it.querySelector('.timeline_ring');
      var fig = it.querySelector('.timeline_fig');
      if (ring) ring.classList.toggle('is-active', on);
      if (fig) fig.classList.toggle('is-active', on);
    });
  }
  var queued = 0;
  window.addEventListener('scroll', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { mark(); queued = 0; });
  }, { passive: true });
  mark();
})();

/* 6. Hero parallax. The design drives the tiles from a --hero-par custom property, which
   data_style_tool cannot author (var() is banned in Webflow style values), so the transform is
   written directly on each tile here. Respects prefers-reduced-motion. */
(function () {
  if (window.__celAboutParallax) return;
  window.__celAboutParallax = true;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var gallery = document.querySelector('.abouthero_gallery');
  if (!gallery) return;
  var tiles = [].slice.call(gallery.querySelectorAll('.abouthero_tile'));
  if (!tiles.length) return;
  /* Per-tile drift in px at full progress, matching the design's -34 / -14 / +26 pattern. */
  var DRIFT = [-34, -14, 26, -34, -14];
  var queued = 0;

  function frame() {
    var r = gallery.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return;
    var p = 1 - (r.top + r.height / 2) / window.innerHeight;   /* ~-1 .. 1 */
    p = Math.max(-1, Math.min(1, p));
    tiles.forEach(function (t, i) {
      t.style.transform = 'translateY(' + (p * (DRIFT[i % DRIFT.length])).toFixed(1) + 'px)';
    });
  }
  window.addEventListener('scroll', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { frame(); queued = 0; });
  }, { passive: true });
  window.addEventListener('resize', frame);
  frame();
})();

/* 7. Mobile TOC drawer (<=991px) — celtocmob3 v2.0.0, the same block the
   Vancouver-family bundles carry. Replaces celtocmob2 v1.0.0, which put `is-menu-open` on
   .stoc_component. No stylesheet has ever defined
   `.stoc_component.is-menu-open`; the rules are `.stoc_label.is-menu-open`
   and `.stoc_nav.is-menu-open`, so tapping the pill did nothing on every
   page that shipped v1. Measured 2026-09-02 on
   /vancouver/cost-of-studying-english at 375px with transitions disabled:
   v1's class left .stoc_nav at visibility:hidden/opacity:0; label+nav gave
   visibility:visible/opacity:1.
   v1 also appended a `.stoc_backdrop` div that no stylesheet styles, so it
   had zero height and could never receive the outside click it existed for;
   a document-level listener replaces it.
   `is-visible` on .stoc_component is carried over unchanged — that half
   always worked. */
(function () {
  if (window.__celTocMob) return;
  window.__celTocMob = true;

  var comp = document.querySelector('.stoc_component');
  var label = document.querySelector('.stoc_label');
  var nav = document.querySelector('.stoc_nav');
  if (!comp || !label || !nav) return;

  var navbar = document.querySelector('.navbar_component');
  var hero = document.querySelector('.section_hero');
  var links = [].slice.call(document.querySelectorAll('.stoc_link[data-target]'));
  var sections = links.map(function (l) {
    return document.getElementById(l.dataset.target);
  }).filter(Boolean);
  var last = sections[sections.length - 1];
  var navH = navbar ? navbar.offsetHeight : 80;

  label.setAttribute('aria-expanded', 'false');

  function close() {
    label.classList.remove('is-menu-open');
    nav.classList.remove('is-menu-open');
    label.setAttribute('aria-expanded', 'false');
  }
  function open() {
    label.classList.add('is-menu-open');
    nav.classList.add('is-menu-open');
    label.setAttribute('aria-expanded', 'true');
  }
  function toggle() {
    if (label.classList.contains('is-menu-open')) close(); else open();
  }

  /* Offer the rail only between the end of the hero and the end of the last
     TOC target: above the hero it repeats the page title, past the last
     section it points at nothing. */
  function updateVisibility() {
    var heroBottom = hero ? hero.getBoundingClientRect().bottom : -1;
    var lastBottom = last ? last.getBoundingClientRect().bottom : Infinity;
    if (heroBottom < navH + 20 && lastBottom > navH + 40) {
      comp.classList.add('is-visible');
    } else {
      comp.classList.remove('is-visible');
      close();
    }
  }

  window.addEventListener('scroll', updateVisibility, { passive: true });
  window.addEventListener('resize', updateVisibility, { passive: true });
  updateVisibility();

  label.addEventListener('click', function (e) { e.preventDefault(); toggle(); });
  label.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
  });
  links.forEach(function (l) { l.addEventListener('click', close); });

  document.addEventListener('click', function (e) {
    if (!label.classList.contains('is-menu-open')) return;
    if (comp.contains(e.target)) return;
    close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
})();

/* Navbar-over-hero (celnavtoc3 / __celNavHero) is DELIBERATELY ABSENT from this page.
   Removed 2026-09-05 at the operator's request: "we don't need it on about page".
   rules/webflow-javascript.md §9 lists it as a standard block for every page — /about is
   the documented exception, so do NOT port it back in. It was inert here in any case: the
   block selects [data-wf--navbar--variant="transparent"] and this page's navbar carries
   variant="base" (measured on the published page 2026-09-05, 0 matching nodes), so it set
   its guard flag and returned before touching anything. See the Navbar note in
   sites/cel/pages/about-cel/styles.css for why this page opts out. */
