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
