/* ============================================================
   Vancouver Adults 16+ — Page-specific scripts
   Site: englishcollege | Page: adults-16
   ============================================================
   RULES:
   - const/let only, NEVER var
   - ALL code in IIFEs, NEVER pollute global scope
   - Idempotency guards on all init functions
   - NEVER inject <style> tags (CSS injection BANNED)
   - Scripts are for BEHAVIOR only, not styling
   ============================================================ */

/* ── Navbar scroll colour — REMOVED, now in shared/utils.js ──
   This file used to carry its own copy of initNavbarTransparent. So did
   pages/cost-of-studying-english/scripts.js. shared/utils.js carried a third. The San Diego pages
   load these two, so san-diego.html and costs.html got the local copies and
   how-long-to-learn-english.html got nothing at all — which is why the four pages disagreed about
   the top navigation. One implementation now, in shared/utils.js, loaded by every page. ── */


/* ── SVG Icons ──
   All SVG icons are now standalone .svg files in this page directory.
   See: adults-16-icon-*.svg, adults-16-compare-bar-*.svg
   data-svg attributes in HTML are kept for reference.
   Icons render natively via <img> on Webflow (uploaded as assets).
   ── */

/* ── Sidebar TOC — scroll-position tracking + mobile slide-out ── */
/* utils.js auto-inits TOC with __celTocDone guard. Skip if already done. */
(function() {
  if (window.__a16TocDone || window.__celTocDone) return;
  window.__a16TocDone = true;
  window.__celTocDone = true;

  const tocLinks = document.querySelectorAll('.stoc_link[data-target]');
  const sectIds = [].slice.call(tocLinks).map(function(l) { return l.dataset.target; });
  /* Spy in DOCUMENT order, not link order: detectActive() keeps the last section above the
     reading line, which is only correct if the array is in document order. A TOC whose link
     order differs from section order (San Diego §2: Courses before Location) would otherwise
     highlight the wrong link. No-op where the two orders already agree. */
  const sections = sectIds.map(function(id) { return document.getElementById(id); }).filter(Boolean)
    .sort(function(a, b) { return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1; });
  const nav = document.querySelector('.navbar_component');
  function shouldReduce() { return matchMedia('(prefers-reduced-motion: reduce)').matches; }

  if (!sections.length || !tocLinks.length) return;

  const stocComponent = document.querySelector('.stoc_component');
  const stocLabel = document.querySelector('.stoc_label');

  tocLinks.forEach(function(l) {
    l.removeAttribute('href');
    l.setAttribute('tabindex', '0');
    l.setAttribute('role', 'link');
    // Hover: toggle is-hover on children so Webflow combo classes work
    l.addEventListener('mouseenter', function() {
      const dot = l.querySelector('.stoc_dot');
      const text = l.querySelector('.stoc_text');
      if (dot) dot.classList.add('is-hover');
      if (text) text.classList.add('is-hover');
    });
    l.addEventListener('mouseleave', function() {
      const dot = l.querySelector('.stoc_dot');
      const text = l.querySelector('.stoc_text');
      if (dot) dot.classList.remove('is-hover');
      if (text) text.classList.remove('is-hover');
    });
  });

  function setActive(id) {
    tocLinks.forEach(function(l) {
      const isActive = l.dataset.target === id;
      l.classList.toggle('is-active', isActive);
      const dot = l.querySelector('.stoc_dot');
      if (dot) dot.classList.toggle('is-active', isActive);
      const text = l.querySelector('.stoc_text');
      if (text) text.classList.toggle('is-active', isActive);
    });
    if (stocLabel) {
      const active = [].slice.call(tocLinks).find(function(l) { return l.dataset.target === id; });
      if (active) {
        const textEl = active.querySelector('.stoc_text');
        stocLabel.textContent = textEl ? textEl.textContent.trim() : active.textContent.trim();
      }
    }
  }

  function detectActive() {
    const readingLine = (nav ? nav.offsetHeight : 90) + 40;
    let activeId = sections[0].id;
    sections.forEach(function(sec) {
      if (sec.getBoundingClientRect().top <= readingLine) activeId = sec.id;
    });
    setActive(activeId);
  }

  let rafPending = false;
  window.addEventListener('scroll', function() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(function() { detectActive(); rafPending = false; });
  }, { passive: true });

  function closeMenu() {
    if (!stocComponent) return;
    stocComponent.classList.remove('is-menu-open');
    if (backdrop) backdrop.classList.remove('is-visible');
  }

  /* Duration-capped smooth scroll that tracks a LIVE target. Native `behavior:'smooth'`
     scales its duration with distance, so a 20,000px jump on this page animates for several
     seconds and reads as broken, while a plain jump reads as a hard cut. Fixed ~700ms ease-out
     instead. The destination MUST be recomputed every frame: a long jump crosses dozens of
     lazy images, and each one that decodes mid-flight grows the page and moves the target
     (an upward jump chasing a receding target used to land 10,000px off). After the ease we
     converge on the live target, then keep re-snapping briefly while layout settles — unless
     the reader takes over, in which case we get out of the way immediately. */
  function smoothScrollToEl(el, offset) {
    const want = function() { return el.getBoundingClientRect().top + window.scrollY - offset; };
    if (shouldReduce()) { window.scrollTo(0, want()); return; }
    const DUR = 700, MAX = 1800;
    const t0 = performance.now();
    let cancelled = false;
    const stop = function() { cancelled = true; };
    ['wheel', 'touchstart', 'keydown'].forEach(function(e) {
      window.addEventListener(e, stop, { once: true, passive: true });
    });
    function release() {
      ['wheel', 'touchstart', 'keydown'].forEach(function(e) { window.removeEventListener(e, stop); });
    }
    function settle() {
      const t1 = performance.now();
      (function s() {
        if (cancelled) { release(); return; }
        if (Math.abs(want() - window.scrollY) > 1) window.scrollTo(0, want());
        if (performance.now() - t1 < 700) requestAnimationFrame(s);
        else release();
      })();
    }
    (function step(now) {
      if (cancelled) { release(); return; }
      const t = now - t0;
      const cur = window.scrollY, gap = want() - cur;
      if ((t >= DUR && Math.abs(gap) <= 2) || t >= MAX) { window.scrollTo(0, want()); settle(); return; }
      const p = Math.min(1, t / DUR);
      window.scrollTo(0, cur + gap * (0.1 + 0.22 * p));
      requestAnimationFrame(step);
    })(t0);
  }

  function scrollToSection(link) {
    const target = document.getElementById(link.dataset.target);
    if (!target) return;
    setActive(link.dataset.target);
    smoothScrollToEl(target, (nav ? nav.offsetHeight : 90) + 24);
  }

  tocLinks.forEach(function(link) {
    link.addEventListener('click', function(e) { e.preventDefault(); scrollToSection(link); closeMenu(); });
    link.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scrollToSection(link); closeMenu(); }
    });
  });

  const hash = location.hash.replace('#', '');
  if (hash && sectIds.indexOf(hash) !== -1) setActive(hash);
  else detectActive();

  /* Mobile TOC */
  let backdrop = null;
  const heroSection = document.querySelector('.section_hero');

  if (stocComponent && stocLabel) {
    const navH = nav ? nav.offsetHeight : 80;

    const lastSection = sections[sections.length - 1];
    function updateTabVisibility() {
      if (!heroSection) { stocComponent.classList.add('is-visible'); return; }
      const heroBottom = heroSection.getBoundingClientRect().bottom;
      const lastBottom = lastSection ? lastSection.getBoundingClientRect().bottom : Infinity;
      if (heroBottom < navH + 20 && lastBottom > navH + 40) {
        stocComponent.classList.add('is-visible');
      } else {
        stocComponent.classList.remove('is-visible');
        closeMenu();
      }
    }
    window.addEventListener('scroll', updateTabVisibility, { passive: true });
    updateTabVisibility();

    backdrop = document.createElement('div');
    backdrop.className = 'stoc_backdrop';
    document.body.appendChild(backdrop);

    stocLabel.addEventListener('click', function() {
      const isOpen = stocComponent.classList.toggle('is-menu-open');
      backdrop.classList.toggle('is-visible', isOpen);
    });
    backdrop.addEventListener('click', closeMenu);
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeMenu(); });
  }
})();

/* ── Card Slider init + all sliders ── */
(function() {
  if (window.__a16SliderDone) return;
  window.__a16SliderDone = true;

  function initCardSlider(sectionSel, opts) {
    if (typeof Swiper === 'undefined') return null;
    opts = opts || {};
    const section = document.querySelector(sectionSel);
    if (!section) return null;
    let swiperEl = opts.swiper ? document.querySelector(opts.swiper) : section.querySelector('.card-slider.swiper');
    if (!swiperEl) swiperEl = section.querySelector('.swiper');
    if (!swiperEl) return null;
    let navEl = opts.nav ? document.querySelector(opts.nav) : section.querySelector('.card-slider_nav');
    if (!navEl) navEl = section;

    const config = {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      grabCursor: true,
      freeMode: { enabled: true, sticky: false },
      breakpoints: opts.breakpoints || {}
    };

    const swiper = new Swiper(swiperEl, config);

    const prevBtn = navEl.querySelector('.card-slider_arrow.is-prev');
    const nextBtn = navEl.querySelector('.card-slider_arrow.is-next');
    const progressFill = navEl.querySelector('.card-slider_progress-fill');

    if (prevBtn) prevBtn.addEventListener('click', function() { swiper.slidePrev(); });
    if (nextBtn) nextBtn.addEventListener('click', function() { swiper.slideNext(); });

    function updateProgress() {
      if (!progressFill || !swiper.slides || !swiper.slides.length) return;
      let progress = swiper.progress;
      if (isNaN(progress)) progress = 0;
      progress = Math.max(0, Math.min(1, progress));
      progressFill.style.width = (progress * 100) + '%';
    }
    swiper.on('progress', updateProgress);
    swiper.on('slideChange', updateProgress);
    updateProgress();
    return swiper;
  }

  const autoBreakpoints = {
    0:    { slidesPerView: 'auto', spaceBetween: 12 },
    480:  { slidesPerView: 'auto', spaceBetween: 16 },
    768:  { slidesPerView: 'auto', spaceBetween: 16 },
    992:  { slidesPerView: 'auto', spaceBetween: 16 },
    1400: { slidesPerView: 'auto', spaceBetween: 16 }
  };

  function go() {
    if (typeof Swiper === 'undefined') return;
    initCardSlider('#courses', { slidesPerView: 'auto', spaceBetween: 16, breakpoints: autoBreakpoints });
    initCardSlider('#city', { swiper: '#showcaseSlider', nav: '#showcaseSliderNav', slidesPerView: 'auto', spaceBetween: 16, speed: 800, breakpoints: autoBreakpoints });
    // Testimonials: CMS Collection List (#testimonials-col) is the swiper root,
    // and the static Google-Reviews hero (#testimonial-hero) must be slide 0.
    const testCol = document.getElementById('testimonials-col');
    const testWrap = testCol ? testCol.querySelector('.swiper-wrapper') : null;
    const testHero = document.getElementById('testimonial-hero');
    if (testCol && !testCol.classList.contains('swiper')) testCol.classList.add('swiper');
    if (testHero && testWrap && testHero.parentNode !== testWrap) testWrap.insertBefore(testHero, testWrap.firstChild);
    initCardSlider('.section_testimonials', { swiper: '#testimonials-col', nav: '#testimonialsSliderNav', slidesPerView: 'auto', spaceBetween: 16, breakpoints: autoBreakpoints });
    initCardSlider('#activities', { swiper: '#activitiesSlider', nav: '#activitiesSliderNav', slidesPerView: 'auto', spaceBetween: 16, breakpoints: autoBreakpoints });
    initCardSlider('#accommodation', { swiper: '#accomSlider', nav: '#accomSliderNav', slidesPerView: 'auto', spaceBetween: 16, breakpoints: { 480: { spaceBetween: 16 }, 768: { spaceBetween: 18 }, 992: { spaceBetween: 20 }, 1400: { spaceBetween: 22 } } });
  }

  if (typeof Swiper !== 'undefined') go();
  else document.addEventListener('swiperReady', go);
})();

/* ── Comparison bars — animate on scroll ── */
(function() {
  if (window.__a16CompareDone) return;
  window.__a16CompareDone = true;
  const el = document.querySelector('.compare_component');
  if (!el) return;
  const obs = new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting) { el.classList.add('is-visible'); obs.disconnect(); }
  }, { threshold: 0.3 });
  obs.observe(el);
})();

/* ── Vimeo lazy-load facade ── */
(function() {
  if (window.__a16VimeoDone) return;
  window.__a16VimeoDone = true;
  const player = document.querySelector('.video_player[data-vimeo-id]');
  if (!player) return;
  const btn = player.querySelector('.video_play-btn');
  const thumb = player.querySelector('.video_thumbnail');
  if (!btn && !thumb) return;
  function loadVideo() {
    const id = player.getAttribute('data-vimeo-id');
    if (!id || player.classList.contains('is-playing')) return;
    const iframe = document.createElement('iframe');
    iframe.className = 'video_embed';
    iframe.src = 'https://player.vimeo.com/video/' + id + '?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';
    iframe.setAttribute('frameborder', '0');
    iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
    iframe.setAttribute('allowfullscreen', '');
    iframe.title = 'CEL Vancouver — English Language School';
    player.appendChild(iframe);
    player.classList.add('is-playing');
  }
  if (btn) btn.addEventListener('click', loadVideo);
  if (thumb) thumb.addEventListener('click', loadVideo);
})();

/* ── FAQ Accordion — capture phase to beat webflow.js IX2 ── */
(function() {
  if (window.__celFq || window.__a16Faq) return;
  window.__a16Faq = true;
  if (!document.querySelector('.faq-item')) return;

  function cancelAnims() {
    document.querySelectorAll('.faq-body').forEach(function(b) {
      if (b.getAnimations) b.getAnimations().forEach(function(a) { a.cancel(); });
    });
  }

  /* Capture phase (3rd arg: true) fires BEFORE IX2's bubbling handler.
     stopPropagation() prevents IX2 from seeing the click at all,
     eliminating the double-toggle that causes "opens then cancels". */
  document.addEventListener('click', function(e) {
    const q = e.target.closest('.faq-q');
    if (!q) return;
    e.stopPropagation();

    const item = q.closest('.faq-item');
    if (!item) return;
    const wasOpen = item.dataset.faqOpen === 'true';

    cancelAnims();

    // Close all
    document.querySelectorAll('.faq-item').forEach(function(it) {
      const bd = it.querySelector('.faq-body');
      const bt = it.querySelector('.faq-q');
      const ic = it.querySelector('.faq-icon');
      it.dataset.faqOpen = 'false';
      it.classList.remove('is-open');
      if (bt) { bt.classList.remove('is-open'); bt.setAttribute('aria-expanded', 'false'); }
      if (ic) ic.classList.remove('is-open');
      if (bd) bd.style.maxHeight = '0px';
    });

    // Open clicked (if it was closed)
    if (!wasOpen) {
      const bd = item.querySelector('.faq-body');
      const inner = item.querySelector('.faq-body-inner');
      const bt = item.querySelector('.faq-q');
      const ic = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'true';
      item.classList.add('is-open');
      if (bt) { bt.classList.add('is-open'); bt.setAttribute('aria-expanded', 'true'); }
      if (ic) ic.classList.add('is-open');
      if (bd && inner) bd.style.maxHeight = inner.scrollHeight + 'px';
    }
  }, true);
})();
