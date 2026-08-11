/* ═══════════════════════════════════════════════════════════
   CEL Vancouver — Costs Page Scripts
   v=5 | 2026-03-27
   ═══════════════════════════════════════════════════════════ */

/* ── Navbar scroll colour (local dev only — production uses celnavtoc3 + IX2)
   CSS rule: .navbar_component           → background: var(--indigo-bright)  [base]
             .navbar_component:where(w-variant-...) → background: transparent [variant]
   Over hero  → remove inline style → variant CSS wins → transparent
   Past hero  → set inline indigo   → overrides variant CSS → indigo ── */
(function() {
  if (window.__celNt || window.__costsNavLocal) return;
  window.__costsNavLocal = true;

  let nav = document.querySelector('[data-wf--navbar--variant="transparent"]');
  if (!nav) return;
  let hero = document.querySelector('.section_hero');
  if (!hero) return;

  function check() {
    if (hero.getBoundingClientRect().bottom > 80) {
      nav.style.removeProperty('background-color');
    } else {
      nav.style.setProperty('background-color', 'rgb(93, 96, 238)', 'important'); /* --indigo-bright, beats IX2 inline */
    }
  }

  check();
  let raf = false;
  window.addEventListener('scroll', function() {
    if (raf) return;
    raf = true;
    requestAnimationFrame(function() { check(); raf = false; });
  }, { passive: true });
})();

/* ── Swiper Slider init (accommodation only) ── */
(function () {
  if (window.__costsSw3 || window.__costsSliderLocal) return;
  window.__costsSliderLocal = true;

  function initSlider(swiperEl, navEl, opts) {
    if (typeof Swiper === 'undefined' || !swiperEl) return null;
    let sw = new Swiper(swiperEl, {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      grabCursor: true,
      freeMode: { enabled: true, sticky: false },
      breakpoints: opts.breakpoints || {}
    });
    let prevBtn = navEl ? navEl.querySelector('.card-slider_arrow.is-prev') : null;
    let nextBtn = navEl ? navEl.querySelector('.card-slider_arrow.is-next') : null;
    let fill = navEl ? navEl.querySelector('.card-slider_progress-fill') : null;
    if (!fill) fill = document.getElementById(opts.fillId || '');
    if (prevBtn) prevBtn.addEventListener('click', function () { sw.slidePrev(); });
    if (nextBtn) nextBtn.addEventListener('click', function () { sw.slideNext(); });
    function prog() {
      if (!fill) return;
      let p = Math.max(0, Math.min(1, isNaN(sw.progress) ? 0 : sw.progress));
      fill.style.width = (p * 100) + '%';
    }
    sw.on('progress', prog);
    sw.on('slideChange', prog);
    prog();
    return sw;
  }

  function go() {
    if (typeof Swiper === 'undefined') return;
    // Accommodation slider
    let accomEl = document.getElementById('accomSlider');
    let accomNav = document.getElementById('accomSliderNav');
    initSlider(accomEl, accomNav, {
      slidesPerView: 'auto', spaceBetween: 16,
      breakpoints: {
        480:  { spaceBetween: 16 },
        768:  { spaceBetween: 18 },
        992:  { spaceBetween: 20 },
        1400: { spaceBetween: 22 }
      }
    });

    // Living in Vancouver showcase slider
    let livingEl = document.getElementById('livingSlider');
    let livingNav = document.getElementById('livingSliderNav');
    initSlider(livingEl, livingNav, {
      slidesPerView: 'auto', spaceBetween: 16, speed: 800,
      breakpoints: {
        480:  { spaceBetween: 16 },
        768:  { spaceBetween: 18 },
        992:  { spaceBetween: 20 },
        1400: { spaceBetween: 22 }
      }
    });
  }

  if (typeof Swiper !== 'undefined') { go(); return; }
  let swiperScript = document.querySelector('script[src*="swiper"]');
  if (swiperScript) {
    swiperScript.addEventListener('load', go);
  } else {
    // Retry up to 20× every 100ms — avoids banned DOMContentLoaded on Webflow CDN
    let retries = 0;
    let timer = setInterval(function() {
      if (typeof Swiper !== 'undefined') { clearInterval(timer); go(); }
      else if (++retries >= 20) clearInterval(timer);
    }, 100);
  }
})();

/* ── Price Bar Animation (IntersectionObserver + WAAPI) ── */
(function () {
  if (window.__costsPriceBarDone) return;
  window.__costsPriceBarDone = true;

  let table = document.querySelector('.price-table');
  if (!table) return;

  let animated = false;

  function animate() {
    if (animated) return;
    animated = true;
    let rows = table.querySelectorAll('.price-row[data-w]');
    rows.forEach(function (row, i) {
      let bar = row.querySelector('.price-bar');
      if (!bar) return;
      let w = parseFloat(row.dataset.w) || 0.08;
      // Cancel any existing WAAPI animations (IX2 locks)
      if (bar.getAnimations) bar.getAnimations().forEach(function (a) { a.cancel(); });
      bar.animate(
        [{ transform: 'scaleX(0)' }, { transform: 'scaleX(' + w + ')' }],
        { delay: i * 90, duration: 900, easing: 'cubic-bezier(0.16,1,0.3,1)', fill: 'forwards' }
      );
    });
  }

  if ('IntersectionObserver' in window) {
    let io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { animate(); io.disconnect(); } });
    }, { threshold: 0.2 });
    io.observe(table);
  } else {
    animate();
  }
})();

/* ── TOC Desktop — Scroll Spy + Active Highlight ── */
(function() {
  if (window.__costsTocDone) return;
  window.__costsTocDone = true;

  let links = document.querySelectorAll('.stoc_link[data-target]');
  if (!links.length) return;

  let sections = [];
  links.forEach(function(link) {
    let id = link.getAttribute('data-target');
    let el = document.getElementById(id);
    if (el) sections.push({ id: id, el: el, link: link });
  });

  sections.sort(function(a, b) { return a.el.offsetTop - b.el.offsetTop; });

  function updateActive() {
    let scrollY = window.scrollY + 160;
    let active = sections[0];
    for (let i = 0; i < sections.length; i++) {
      if (sections[i].el.getBoundingClientRect().top + window.scrollY <= scrollY) active = sections[i];
    }
    links.forEach(function(l) { l.classList.remove('is-active'); });
    if (active) active.link.classList.add('is-active');
  }

  let ticking = false;
  window.addEventListener('scroll', function() {
    if (!ticking) {
      requestAnimationFrame(function() { updateActive(); ticking = false; });
      ticking = true;
    }
  });
  updateActive();
})();

/* ── Budget Table Drag-to-Scroll ── */
(function() {
  if (window.__costsBudgetScrollDone) return;
  window.__costsBudgetScrollDone = true;

  let wrap = document.querySelector('.budget-wrap');
  if (!wrap) return;

  let outer = wrap.closest('.budget-scroll-outer');
  let isDragging = false;
  let startX = 0;
  let scrollLeft = 0;

  function updateFade() {
    if (!outer) return;
    let hasOverflow = wrap.scrollWidth > wrap.clientWidth + 4;
    outer.classList.toggle('has-overflow', hasOverflow);
    if (hasOverflow) {
      let atEnd = wrap.scrollLeft + wrap.clientWidth >= wrap.scrollWidth - 4;
      outer.classList.toggle('is-scrolled-end', atEnd);
    }
  }

  wrap.classList.add('is-scrollable');

  wrap.addEventListener('mousedown', function(e) {
    isDragging = true;
    wrap.classList.add('is-dragging');
    startX = e.pageX - wrap.offsetLeft;
    scrollLeft = wrap.scrollLeft;
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    let x = e.pageX - wrap.offsetLeft;
    wrap.scrollLeft = scrollLeft - (x - startX);
  });

  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    wrap.classList.remove('is-dragging');
  });

  wrap.addEventListener('touchstart', function(e) {
    startX = e.touches[0].pageX - wrap.offsetLeft;
    scrollLeft = wrap.scrollLeft;
  }, { passive: true });

  wrap.addEventListener('touchmove', function(e) {
    let x = e.touches[0].pageX - wrap.offsetLeft;
    wrap.scrollLeft = scrollLeft - (x - startX);
  }, { passive: true });

  wrap.addEventListener('scroll', updateFade);
  window.addEventListener('resize', updateFade);
  updateFade();
})();

/* ── FAQ Accordion — capture phase to beat webflow.js IX2 ── */
(function() {
  if (window.__celFq || window.__costsFaq) return;
  window.__costsFaq = true;

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

/* ── TOC Mobile — Floating Tab ── */
(function() {
  if (window.__costsTocMobileDone) return;
  window.__costsTocMobileDone = true;

  let sidebar = document.getElementById('tocSidebar');
  let label = document.querySelector('.stoc_label');
  if (!sidebar || !label) return;

  let navH = 0;
  let nav = document.querySelector('[data-w-id]');
  if (nav) navH = nav.offsetHeight || 80;

  function update() {
    if (window.innerWidth > 991) {
      sidebar.classList.remove('is-visible');
      sidebar.classList.remove('is-menu-open');
      sidebar.style.top = '';
      label.style.top = '';
      return;
    }
    sidebar.classList.add('is-visible');
    sidebar.style.top = (navH + 14) + 'px';
    label.style.top = (navH + 14) + 'px';
  }

  label.addEventListener('click', function() {
    sidebar.classList.toggle('is-menu-open');
  });

  document.addEventListener('click', function(e) {
    if (window.innerWidth > 991) return;
    if (!e.target.closest('.stoc_component') && !e.target.closest('.stoc_label')) {
      sidebar.classList.remove('is-menu-open');
    }
  });

  window.addEventListener('resize', update);
  update();
})();
