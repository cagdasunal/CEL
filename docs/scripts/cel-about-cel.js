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

/* 3. Team tabs. DUAL-MODE, so this bundle is correct both before and after the Webflow
   structure change.
   - CMS mode (current): #team holds one Collection List per tab, each an element carrying
     [data-tab-panel="management|admission|teachers"]. A tab shows its own panel and hides the
     others; nothing inside a list is touched, so Webflow owns the item markup end to end.
   - Legacy mode: the 24 hand-written .swiper-slide.is-team cards lived in ONE track and were
     filtered per slide by [data-cat]. Kept as a fallback so a stale cached bundle, or a rollback
     of the page structure, still filters correctly instead of showing all three groups at once.
   The design's CSS filter — .team-slider_el.is-tab-<cat> .swiper-slide.is-team:not([data-cat=...])
   — is a descendant + :not() + attribute selector, three separate reasons Webflow cannot express
   it as a style, which is why the state is applied inline here in both modes. */
(function () {
  if (window.__celAboutTeamTabs) return;
  window.__celAboutTeamTabs = true;
  var tabs = [].slice.call(document.querySelectorAll('.team_tab[data-tab]'));
  if (!tabs.length) return;
  var panels = [].slice.call(document.querySelectorAll('[data-tab-panel]'));
  var legacy = document.querySelector('.team-slider_el');
  if (!panels.length && !legacy) return;

  function show(cat) {
    tabs.forEach(function (t) { t.classList.toggle('is-active', t.dataset.tab === cat); });

    if (panels.length) {
      panels.forEach(function (p) {
        var on = p.getAttribute('data-tab-panel') === cat;
        /* '' restores the stylesheet's display:flex on .card-slider — never hard-code it. */
        p.style.display = on ? '' : 'none';
        p.setAttribute('aria-hidden', on ? 'false' : 'true');
        if (on && p.swiper) { p.swiper.update(); p.swiper.slideTo(0, 0); }
      });
    } else {
      legacy.setAttribute('data-tab-active', cat);
      [].slice.call(legacy.querySelectorAll('.swiper-slide.is-team')).forEach(function (s) {
        s.style.display = (s.getAttribute('data-cat') === cat) ? '' : 'none';
      });
      if (legacy.swiper) { legacy.swiper.update(); legacy.swiper.slideTo(0, 0); }
    }

    document.dispatchEvent(new CustomEvent('cel:teamTabChange', { detail: { cat: cat } }));
  }

  tabs.forEach(function (t) {
    t.setAttribute('tabindex', '0');
    t.addEventListener('click', function (e) { e.preventDefault(); show(t.dataset.tab); });
    t.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); t.click(); }
    });
  });

  var initial = (tabs.filter(function (t) { return t.classList.contains('is-active'); })[0]
    || tabs[0]).dataset.tab;
  show(initial);
})();

/* 4. Team card slider — arrows + progress bar, shared by all three tab panels.
   There is ONE .card-slider_nav for the whole section, so every read and every scroll resolves
   the ACTIVE track at call time rather than closing over one element: in CMS mode that is the
   visible [data-tab-panel]'s .swiper-wrapper, in legacy mode the single .team-slider_el's.
   Uses Swiper when the library is present (the markup carries .swiper / .swiper-wrapper /
   .swiper-slide) and falls back to native scroll otherwise. */
(function () {
  if (window.__celAboutSlider) return;
  window.__celAboutSlider = true;
  var nav = document.querySelector('.card-slider_nav');
  if (!nav) return;
  var prev = nav.querySelector('[data-slide="prev"]');
  var next = nav.querySelector('[data-slide="next"]');
  var fill = document.querySelector('.team-slider_fill');

  function sliders() {
    var panels = [].slice.call(document.querySelectorAll('[data-tab-panel]'));
    if (panels.length) return panels;
    var one = document.querySelector('.team-slider_el');
    return one ? [one] : [];
  }
  function activeEl() {
    var all = sliders();
    if (!all.length) return null;
    return all.filter(function (s) { return s.style.display !== 'none'; })[0] || all[0];
  }
  function activeTrack() {
    var el = activeEl();
    return el ? el.querySelector('.swiper-wrapper') : null;
  }
  function visible(track) {
    return [].slice.call(track.querySelectorAll('.swiper-slide.is-team'))
      .filter(function (s) { return s.style.display !== 'none'; });
  }
  function step(track) {
    var v = visible(track);
    return v.length > 1 ? (v[1].offsetLeft - v[0].offsetLeft) : (v[0] ? v[0].offsetWidth + 16 : 300);
  }
  function progress() {
    var track = activeTrack();
    if (!track) return;
    var max = track.scrollWidth - track.clientWidth;
    var p = max > 0 ? (track.scrollLeft / max) : 0;
    if (fill) fill.style.width = Math.max(4, Math.min(100, p * 100)) + '%';
    if (prev) prev.classList.toggle('is-disabled', track.scrollLeft <= 1);
    if (next) next.classList.toggle('is-disabled', track.scrollLeft >= max - 1);
  }
  function go(dir) {
    var el = activeEl();
    if (el && el.swiper) { dir < 0 ? el.swiper.slidePrev() : el.swiper.slideNext(); return; }
    var track = activeTrack();
    if (track) track.scrollBy({ left: dir * step(track), behavior: 'smooth' });
  }

  /* JAVASCRIPT.md (handoff): Swiper is injected at RUNTIME by a page bundle's __swR loader and is
     never in the page HTML, so a one-shot `if (window.Swiper)` can only miss it. This bundle does
     not ship that loader — measured on the published page, `typeof window.Swiper === "undefined"`
     — which is why #team runs on the native-scroll fallback today. Gate on the documented
     swiperReady event too, so the panels initialise the moment a loader is added, without
     touching this block again. */
  function initSwipers() {
    if (!window.Swiper) return;
    sliders().forEach(function (el) {
      if (el.swiper) return;
      try {
        new window.Swiper(el, {
          slidesPerView: 'auto',
          spaceBetween: 16,
          watchOverflow: true,
          on: { init: progress, slideChange: progress, resize: progress }
        });
      } catch (err) { /* fall through to native scroll */ }
    });
  }
  if (window.Swiper) initSwipers();
  else document.addEventListener('swiperReady', initSwipers);

  if (prev) prev.addEventListener('click', function (e) { e.preventDefault(); go(-1); });
  if (next) next.addEventListener('click', function (e) { e.preventDefault(); go(1); });
  [prev, next].forEach(function (b) {
    if (!b) return;
    b.setAttribute('tabindex', '0');
    b.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); b.click(); }
    });
  });
  sliders().forEach(function (el) {
    var t = el.querySelector('.swiper-wrapper');
    if (t) t.addEventListener('scroll', progress, { passive: true });
  });
  window.addEventListener('resize', progress);
  document.addEventListener('cel:teamTabChange', progress);
  progress();
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
