/*!
 * CEL — /san-diego-ca/language-school page bundle
 * Course chooser from the Claude Design source; TOC spy, FAQ accordion and the w--current
 * cleanup follow the same contracts as the other San Diego pages.
 * Deployed minified as cel-sd-san-diego.min.js — see tools/cel-page-scripts/build.sh
 */

/* 1. Webflow w--current cleanup on same-page anchors. */
(function () {
  if (window.__celSdCurrent) return;
  window.__celSdCurrent = true;
  function clean() {
    document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current')
      .forEach(function (e) { e.classList.remove('w--current'); });
  }
  setInterval(clean, 300);
  clean();
})();

/* 2. Course chooser (verbatim from the design source, wrapped with a guard flag). */
(function () {
  if (window.__celSdChooser) return;
  window.__celSdChooser = true;
  var root = document.querySelector('#courses .chooser_component');
  if (!root) return;
  var goals = [].slice.call(root.querySelectorAll('.chooser_goal'));
  var cards = [].slice.call(root.querySelectorAll('.chooser_card'));
  if (!goals.length || !cards.length) return;
  var current = 0;

  function select(i, moveFocus){
    current = (i + goals.length) % goals.length;
    var course = goals[current].getAttribute('data-course');
    goals.forEach(function(x, n){
      var on = n === current;
      x.classList.toggle('is-active', on);
      x.setAttribute('aria-selected', on ? 'true' : 'false');
      x.setAttribute('tabindex', on ? '0' : '-1');
    });
    cards.forEach(function(c){ c.classList.toggle('is-active', c.getAttribute('data-course') === course); });
    if (moveFocus) goals[current].focus();
  }

  goals.forEach(function(g, i){
    g.addEventListener('click', function(e){ e.preventDefault(); select(i); });
    g.addEventListener('keydown', function(e){
      var k = e.key;
      if (k === 'ArrowDown' || k === 'ArrowRight'){ e.preventDefault(); select(current + 1, true); }
      else if (k === 'ArrowUp' || k === 'ArrowLeft'){ e.preventDefault(); select(current - 1, true); }
      else if (k === 'Home'){ e.preventDefault(); select(0, true); }
      else if (k === 'End'){ e.preventDefault(); select(goals.length - 1, true); }
    });
  });

  select(0);
})();
/* 3. TOC scroll-spy. */
(function () {
  if (window.__celToc) return;
  window.__celToc = true;
  /* Only take ownership of links whose target section actually exists.
     This filter must run BEFORE the removeAttribute('href') loop below: the old
     order stripped the href from every .stoc_link and only then dropped the
     unresolvable ones from the scroll-spy, which left them as 119x35px,
     tabindex="0", cursor:pointer controls that preventDefault() and then no-op —
     focusable widgets that do nothing. Filtering first means a link whose section
     was never deployed keeps its native href and degrades to an ordinary anchor
     instead. Measured on this page: data-target="offers" and
     data-target="accommodation" both resolve to null. */
  const allLinks = [].slice.call(document.querySelectorAll('.stoc_link[data-target]'));
  if (!allLinks.length) return;
  const links = allLinks.filter(function (l) { return document.getElementById(l.dataset.target); });
  if (!links.length) return;
  const sections = links.map(function (l) { return document.getElementById(l.dataset.target); });
  const targets = links.map(function (l) { return l.dataset.target; });
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

/* 4. FAQ accordion — single-open, maxHeight animation, aria-expanded.
   .faq-q is an <a> with no href, which Enter/Space do not natively activate. */
(function () {
  if (window.__celFq) return;
  window.__celFq = true;
  if (!document.querySelector('.faq-item')) return;
  document.addEventListener('click', function (e) {
    var q = e.target.closest && e.target.closest('.faq-q');
    if (!q) return;
    var item = q.closest('.faq-item');
    if (!item) return;
    var wasOpen = item.dataset.faqOpen === 'true';
    document.querySelectorAll('.faq-item').forEach(function (it) {
      var body = it.querySelector('.faq-body');
      var qq = it.querySelector('.faq-q');
      var ic = it.querySelector('.faq-icon');
      it.dataset.faqOpen = 'false';
      it.classList.remove('is-open');
      if (qq) { qq.classList.remove('is-open'); qq.setAttribute('aria-expanded', 'false'); }
      if (ic) ic.classList.remove('is-open');
      if (body) body.style.maxHeight = '0px';
    });
    if (!wasOpen) {
      var body2 = item.querySelector('.faq-body');
      var inner = item.querySelector('.faq-body-inner');
      var ic2 = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'true';
      item.classList.add('is-open');
      q.classList.add('is-open');
      q.setAttribute('aria-expanded', 'true');
      if (ic2) ic2.classList.add('is-open');
      if (body2 && inner) body2.style.maxHeight = inner.scrollHeight + 'px';
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var q = e.target.closest && e.target.closest('.faq-q');
    if (!q) return;
    e.preventDefault();
    q.click();
  });
})();

/* 5. Swiper loader — the site serves Swiper 11 from the CEL scripts host and the
   Vancouver bundle uses the same `swiperReady` handshake. Loading it here keeps the
   San Diego page independent of which other bundle happens to be on the page. */
(function () {
  if (window.__swR) return;
  window.__swR = 1;
  var s = document.createElement('script');
  s.src = 'https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.js';
  s.onload = function () {
    window.__swOK = true;
    document.dispatchEvent(new Event('swiperReady'));
  };
  document.head.appendChild(s);
})();

/* 6. Card sliders — showcase (#city), testimonials, activities.
   Contract copied from pages/vancouver/scripts.js: the section ids and the
   .card-slider_* nav classes are identical on this page. */
(function () {
  if (window.__celSdSliders) return;
  window.__celSdSliders = true;

  var autoBreakpoints = {
    480: { spaceBetween: 16 },
    768: { spaceBetween: 18 },
    992: { spaceBetween: 20 },
    1400: { spaceBetween: 22 }
  };

  function initCardSlider(sectionSel, opts) {
    if (typeof Swiper === 'undefined') return null;
    var section = document.querySelector(sectionSel);
    if (!section) return null;
    var swiperEl = opts.swiper ? document.querySelector(opts.swiper) : section.querySelector('.card-slider.swiper');
    if (!swiperEl) swiperEl = section.querySelector('.swiper');
    if (!swiperEl) return null;
    /* The deploy can drop a second class silently, so make the Swiper root
       self-healing rather than trusting the class list that shipped. */
    if (!swiperEl.classList.contains('swiper')) swiperEl.classList.add('swiper');
    var wrap = swiperEl.querySelector('.swiper-wrapper');
    if (!wrap) return null;
    var navEl = opts.nav ? document.querySelector(opts.nav) : section.querySelector('.card-slider_nav');

    var swiper = new Swiper(swiperEl, {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      breakpoints: opts.breakpoints || autoBreakpoints,
      watchOverflow: true
    });
    if (!navEl) return swiper;

    var prevBtn = navEl.querySelector('.card-slider_arrow.is-prev');
    var nextBtn = navEl.querySelector('.card-slider_arrow.is-next');
    var progressFill = navEl.querySelector('.card-slider_progress-fill');
    if (prevBtn) prevBtn.addEventListener('click', function () { swiper.slidePrev(); });
    if (nextBtn) nextBtn.addEventListener('click', function () { swiper.slideNext(); });

    function updateProgress() {
      if (!progressFill || !swiper.slides || !swiper.slides.length) return;
      var p = swiper.progress;
      if (isNaN(p)) p = 0;
      progressFill.style.width = Math.max(8, Math.min(100, p * 100)) + '%';
    }
    swiper.on('progress', updateProgress);
    swiper.on('slideChange', updateProgress);
    updateProgress();
    return swiper;
  }

  function go() {
    if (typeof Swiper === 'undefined') return;
    initCardSlider('#city', { swiper: '#showcaseSlider', nav: '#showcaseSliderNav', speed: 800 });
    initCardSlider('#testimonials', { swiper: '#testimonials-col', nav: '#testimonialsSliderNav' });
    initCardSlider('#activities', { swiper: '#activitiesSlider', nav: '#activitiesSliderNav' });
  }

  if (typeof Swiper !== 'undefined') go();
  else document.addEventListener('swiperReady', go);
})();

/* 7. Vimeo lazy-load facade (same contract as the Vancouver page). */
(function () {
  if (window.__a16VimeoDone || window.__celSdVimeo) return;
  window.__celSdVimeo = true;
  var player = document.querySelector('.video_player[data-vimeo-id]');
  if (!player) return;
  var btn = player.querySelector('.video_play-btn');
  var thumb = player.querySelector('.video_thumbnail');
  if (!btn && !thumb) return;
  function loadVideo() {
    var id = player.getAttribute('data-vimeo-id');
    if (!id || player.classList.contains('is-playing')) return;
    var iframe = document.createElement('iframe');
    iframe.className = 'video_embed';
    iframe.src = 'https://player.vimeo.com/video/' + id + '?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';
    iframe.setAttribute('frameborder', '0');
    iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
    iframe.setAttribute('allowfullscreen', '');
    iframe.title = 'CEL San Diego — English Language School';
    player.appendChild(iframe);
    player.classList.add('is-playing');
  }
  if (btn) btn.addEventListener('click', loadVideo);
  if (thumb) thumb.addEventListener('click', loadVideo);
})();

/* 8. Mobile TOC drawer (<=991px) — celtocmob3 v2.0.0, the same block the
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

/* 8. WhatsApp glyph on the final CTA.
   The green pill reserves `gap:10px` for an icon that never renders: sd has no icon
   element at all (the anchor's only child is the string "WhatsApp"), and no whatsapp
   asset was ever uploaded. The design marks the icon alt="" i.e. decorative, so a
   ::before is the faithful shape.

   Why it ships from the bundle rather than Webflow: the rule needs an attribute
   selector to hit only the wa.me anchor and not the sibling "Get a Quote" button that
   shares .inline-cta-btn — and attribute selectors are not expressible as Webflow
   styles. Page head code is its normal home, but set_page_freeform_code returns HTTP
   406 for every write to this page. rules/webflow-javascript.md §1 exempts this path
   for a bundle's own self-contained component CSS. Move to head code when the 406
   clears. */
(function () {
  if (document.getElementById('cel-wa-glyph')) return;
  const css =
    /* .callout publishes margin:0 although the Designer holds margin-top/bottom:32px —
       a per-property publish defect on that one global style object, confirmed against
       a fresh sheet and reproduced on a sibling page. The head block already restores
       margin-top; the bottom is still lost at every breakpoint (measured 32px 0 0 at
       1440/900/420). Scoped to .section_page so it cannot reach .callout elsewhere. */
    ".section_page .callout:not(.accred_regulatory){margin-bottom:32px}" +
    "#final-cta .inline-cta-btn[href*='wa.me']::before{" +
    "content:\"\";flex:none;width:18px;height:18px;display:block;" +
    "background:center/contain no-repeat url(\"data:image/svg+xml,<svg%20fill=%22%23FAF3E8%22%20role=%22img%22%20viewBox=%220%200%2024%2024%22%20xmlns=%22http://www.w3.org/2000/svg%22><path%20d=%22M17.472%2014.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94%201.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198%200-.52.074-.792.372-.272.297-1.04%201.016-1.04%202.479%200%201.462%201.065%202.875%201.213%203.074.149.198%202.096%203.2%205.077%204.487.709.306%201.262.489%201.694.625.712.227%201.36.195%201.871.118.571-.085%201.758-.719%202.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421%207.403h-.004a9.87%209.87%200%2001-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86%209.86%200%2001-1.51-5.26c.001-5.45%204.436-9.884%209.888-9.884%202.64%200%205.122%201.03%206.988%202.898a9.825%209.825%200%20012.893%206.994c-.003%205.45-4.437%209.884-9.885%209.884m8.413-18.297A11.815%2011.815%200%200012.05%200C5.495%200%20.16%205.335.157%2011.892c0%202.096.547%204.142%201.588%205.945L.057%2024l6.305-1.654a11.882%2011.882%200%20005.683%201.448h.005c6.554%200%2011.89-5.335%2011.893-11.893a11.821%2011.821%200%2000-3.48-8.413Z%22></path></svg>\")}";
  const st = document.createElement('style');
  st.id = 'cel-wa-glyph';
  st.appendChild(document.createTextNode(css));
  (document.head || document.documentElement).appendChild(st);
})();
