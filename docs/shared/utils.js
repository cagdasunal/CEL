/**
 * CEL Shared Utilities - REFERENCE IMPLEMENTATION
 * This file is NOT deployed to Webflow directly.
 * Individual functions are copy-pasted into separate IIFEs for deployment.
 * See each page's scripts.js for deployed versions.
 */

/* ── Motion Preference Detection (from Webflow Brand Studio) ── */
var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

/**
 * Check if user prefers reduced motion.
 * Use before adding scroll animations, auto-play, or transitions.
 * @returns {boolean} true if user prefers reduced motion
 */
function shouldReduceMotion() {
  return prefersReducedMotion.matches;
}

/* ── TOC Core — scroll-position tracking ── */
function initTocCore(options) {
  var opts = options || {};
  var tocLinks = document.querySelectorAll('.stoc_link[data-target]');
  var sectIds  = [].slice.call(tocLinks).map(function(l) { return l.dataset.target; });
  var sections = sectIds.map(function(id) { return document.getElementById(id); }).filter(Boolean);

  if (!sections.length || !tocLinks.length) return null;

  var stocLabel = document.querySelector('.stoc_label');

  // Remove Webflow's hash-tracking
  tocLinks.forEach(function(l) {
    l.removeAttribute('href');
    l.setAttribute('tabindex', '0');
    l.setAttribute('role', 'link');
  });

  function setActive(id) {
    tocLinks.forEach(function(l) {
      var isActive = l.dataset.target === id;
      l.classList.toggle('is-active', isActive);
      var dot = l.querySelector('.stoc_dot');
      if (dot) dot.classList.toggle('is-active', isActive);
    });
    if (stocLabel) {
      var active = [].slice.call(tocLinks).find(function(l) { return l.dataset.target === id; });
      if (active) {
        var textEl = active.querySelector('.stoc_text');
        stocLabel.textContent = textEl ? textEl.textContent.trim() : active.textContent.trim();
      }
    }
  }

  // Scroll spy
  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) setActive(entry.target.id);
    });
  }, { rootMargin: '-20% 0px -75% 0px' });

  sections.forEach(function(s) { observer.observe(s); });

  // Click-to-scroll
  tocLinks.forEach(function(l) {
    l.addEventListener('click', function() {
      var target = document.getElementById(l.dataset.target);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    l.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); l.click(); }
    });
  });

  // Set initial active
  if (sectIds.length) setActive(sectIds[0]);

  return { setActive: setActive, tocLinks: tocLinks, sections: sections };
}

/* ── TOC Mobile — floating tab + slide-out menu ── */
function initTocMobile(tocCore) {
  if (!tocCore) return;

  var stocComponent = document.querySelector('.stoc_component');
  var stocLabel = document.querySelector('.stoc_label');
  if (!stocComponent || !stocLabel) return;

  var backdrop = document.createElement('div');
  backdrop.className = 'stoc_backdrop';
  document.body.appendChild(backdrop);

  var isOpen = false;

  function toggleMenu(open) {
    isOpen = typeof open === 'boolean' ? open : !isOpen;
    stocComponent.classList.toggle('is-menu-open', isOpen);
    stocLabel.classList.toggle('is-menu-open', isOpen);
    backdrop.classList.toggle('is-visible', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  }

  stocLabel.addEventListener('click', function() { toggleMenu(); });
  backdrop.addEventListener('click', function() { toggleMenu(false); });

  tocCore.tocLinks.forEach(function(l) {
    l.addEventListener('click', function() {
      if (window.innerWidth <= 991) toggleMenu(false);
    });
  });

  // Show/hide floating tab on scroll
  var lastScroll = 0;
  var heroHeight = document.querySelector('.section_hero') ?
    document.querySelector('.section_hero').offsetHeight : 400;

  window.addEventListener('scroll', function() {
    var scrollY = window.pageYOffset;
    stocComponent.classList.toggle('is-visible', scrollY > heroHeight);
    stocLabel.classList.toggle('is-visible', scrollY > heroHeight);
    lastScroll = scrollY;
  }, { passive: true });
}

/* ── FAQ Accordion ── */
function initFaqAccordion(containerSelector) {
  var container = document.querySelector(containerSelector || '.section_faq');
  if (!container) return;

  container.querySelectorAll('.faq_question').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var item = btn.closest('.faq_item');
      var answer = item.querySelector('.faq_answer');
      var isOpen = btn.getAttribute('aria-expanded') === 'true';

      btn.setAttribute('aria-expanded', !isOpen);
      item.classList.toggle('is-open', !isOpen);

      if (!isOpen) {
        answer.style.maxHeight = answer.scrollHeight + 'px';
      } else {
        answer.style.maxHeight = '0';
      }
    });
  });
}

/* ── CEL Slider — reusable Swiper init with progress bar + arrows ── */
/* Usage: initCardSlider('.courses')  →  looks for .courses .card-slider, .courses .card-slider_arrow, etc. */
/* Or:    initCardSlider(null, { swiper: '.my_swiper', nav: '.my_nav' })  for custom selectors */
function initCardSlider(sectionSelector, options) {
  if (typeof Swiper === 'undefined') return null;

  var opts = options || {};
  var root = sectionSelector ? document.querySelector(sectionSelector) : document;
  if (!root) return null;

  var el = root.querySelector(opts.swiper || '.card-slider');
  if (!el) return null;

  var navRoot = opts.nav ? document.querySelector(opts.nav) : root;
  var prevBtn = navRoot.querySelector('.card-slider_arrow.is-prev');
  var nextBtn = navRoot.querySelector('.card-slider_arrow.is-next');
  var progressFill = navRoot.querySelector('.card-slider_progress-fill');

  /* Respect prefers-reduced-motion: disable slide transitions */
  var reducedSpeed = shouldReduceMotion() ? 0 : (opts.speed || 500);

  var config = {
    slidesPerView: opts.slidesPerView || 1.15,
    spaceBetween: opts.spaceBetween || 4,
    grabCursor: true,
    speed: reducedSpeed,
    breakpoints: opts.breakpoints || {
      480: { slidesPerView: 1.5, spaceBetween: 4 },
      768: { slidesPerView: 2.4, spaceBetween: 6 },
      992: { slidesPerView: 3.2, spaceBetween: 6 },
      1400: { slidesPerView: 3.8, spaceBetween: 8 }
    }
  };

  var swiper = new Swiper(el, config);

  function updateNav() {
    if (!swiper) return;
    /* Use swiper.progress (0->1) — works reliably with slidesPerView: 'auto' */
    var p = swiper.progress;
    if (p < 0) p = 0;
    if (p > 1) p = 1;
    if (progressFill) progressFill.style.width = (p * 100) + '%';
    if (prevBtn) prevBtn.classList.toggle('is-disabled', swiper.isBeginning);
    if (nextBtn) nextBtn.classList.toggle('is-disabled', swiper.isEnd);
  }

  swiper.on('slideChange', updateNav);
  swiper.on('progress', updateNav);
  swiper.on('resize', updateNav);
  swiper.on('reachEnd', updateNav);
  swiper.on('reachBeginning', updateNav);
  swiper.on('fromEdge', updateNav);
  updateNav();

  if (prevBtn) prevBtn.addEventListener('click', function() { swiper.slidePrev(config.speed); });
  if (nextBtn) nextBtn.addEventListener('click', function() { swiper.slideNext(config.speed); });

  return swiper;
}

/* ── Navbar Transparent Over Hero ── */
/* IX2-compatible: overrides Webflow's auto-fired inline background-color.
   Transparent while hero is visible, indigo-bright (#5d60ee) after scroll.
   CDN equivalent: celnavtoc3 handles this on Webflow production.
   Retries on sharedComponentsReady (navbar loaded via fetch in local dev). */
function initNavbarTransparent() {
  if (window.__celNt || window.__celNavDone) return;
  var n = document.querySelector('[data-wf--navbar--variant]');
  if (!n) return;
  window.__celNavDone = true;
  var hero = document.querySelector('.section_hero');
  if (!hero) return;

  function check() {
    if (hero.getBoundingClientRect().bottom > 80) {
      n.style.setProperty('background-color', 'transparent', 'important');
    } else {
      n.style.setProperty('background-color', '#5d60ee', 'important');
    }
  }
  check();
  var raf = false;
  window.addEventListener('scroll', function() {
    if (raf) return; raf = true;
    requestAnimationFrame(function() { check(); raf = false; });
  }, { passive: true });

  /* Strip Webflow w--current from hero CTA buttons */
  document.querySelectorAll('.hero_actions a').forEach(function(a) {
    a.classList.remove('w--current');
  });
}

/* ── Inline CTA Component Loader ── */
/* Usage: loadInlineCta({ title: '...', body: '...' }) */
/* Fetches shared/inline-cta.html, replaces {{TITLE}} and {{BODY}}, mounts into #inline-cta-mount */
function loadInlineCta(options) {
  var mount = document.getElementById('inline-cta-mount');
  if (!mount) return;
  var opts = options || {};
  var title = opts.title || mount.getAttribute('data-title') || '';
  var body  = opts.body  || mount.getAttribute('data-body')  || '';
  fetch('../../shared/inline-cta.html')
    .then(function(r) { return r.text(); })
    .then(function(html) {
      var filled = html
        .replace('{{TITLE}}', title)
        .replace('{{BODY}}',  body);
      var tmp = document.createElement('div');
      tmp.innerHTML = filled;
      mount.parentNode.replaceChild(tmp.firstElementChild, mount);
    })
    .catch(function() {
      /* Fallback: render inline if fetch fails (e.g. file:// protocol) */
      mount.outerHTML =
        '<section class="section_inline-cta" id="apply">' +
          '<div class="inline-cta">' +
            '<div class="inline-cta-text">' +
              '<h2 class="inline-cta-title">' + title + '</h2>' +
              '<p class="inline-cta-body">' + body + '</p>' +
            '</div>' +
            '<div class="inline-cta-actions">' +
              '<a class="cta-btn-primary" href="https://www.englishcollege.com/contact-cel">Contact Us</a>' +
            '</div>' +
          '</div>' +
        '</section>';
    });
}

/* ── TOC Auto-Init — runs on every page that includes utils.js ── */
/* NOTE: __celNt is celnavtoc3 (navbar+dot polling only) — does NOT init TOC.
   So we must NOT gate on __celNt here. Only skip if TOC itself already ran. */
(function() {
  if (window.__celTocDone) return;
  window.__celTocDone = true;
  const tocCore = initTocCore();
  if (tocCore) initTocMobile(tocCore);
})();

/* ── Navbar Transparent Auto-Init ── */
/* Runs on every page. Retries after shared components load (navbar via fetch). */
(function() {
  initNavbarTransparent();
  document.addEventListener('sharedComponentsReady', initNavbarTransparent);
})();

/* ── TOC Dot Active Color Polling ── */
/* IX2 sets is-active async after scroll. Polling reads settled state.
   CDN equivalent: celnavtoc3 handles this on Webflow production. */
(function() {
  if (window.__celNt || window.__celTocDotDone) return;
  window.__celTocDotDone = true;
  function pd() {
    document.querySelectorAll('.stoc_dot').forEach(function(d) {
      var l = d.closest('.stoc_link');
      var on = l && l.classList.contains('is-active');
      d.style.backgroundColor = on ? '#e78b10' : '';
      d.style.borderColor = on ? '#e78b10' : '';
    });
  }
  setInterval(pd, 300);
  pd();
})();

/* ── TOC Link-Row Hover — shared (mirrors celtochov1 v2.0.0 on Webflow) ── */
/* Dot has :hover only on the 10px dot itself. Link-row hover must be JS,
   but INLINE styles conflict with celnavtoc3 polling (clears borderColor
   every 300ms). Toggle .is-hover combo class instead — immune to polling.
   Guard name matches celtochov1 CDN script — §12 of webflow-javascript.md. */
(function() {
  if (window.__celToh || window.__celTohDone) return;
  window.__celTohDone = true;
  function init() {
    const links = document.querySelectorAll('.stoc_link');
    if (!links.length) { setTimeout(init, 200); return; }
    links.forEach(function(l) {
      const d = l.querySelector('.stoc_dot');
      if (!d) return;
      l.addEventListener('mouseenter', function() {
        if (!l.classList.contains('is-active')) d.classList.add('is-hover');
      });
      l.addEventListener('mouseleave', function() {
        d.classList.remove('is-hover');
      });
    });
  }
  init();
})();

/* ── FAQ Accordion — Shared Component ── */
/* Cancels IX2 animations, toggles is-open on faq-item + faq-q + faq-icon */
(function() {
  if (window.__celFq || window.__celFaqDone) return;
  window.__celFaqDone = true;

  function cancelFaqAnimations() {
    document.querySelectorAll('.faq-body').forEach(function(b) {
      if (b.getAnimations) b.getAnimations().forEach(function(a) { a.cancel(); });
    });
  }

  document.addEventListener('click', function(e) {
    var q = e.target.closest('.faq-q');
    if (!q) return;
    var clickedItem = q.closest('.faq-item');
    if (!clickedItem) return;
    var wasOpen = clickedItem.dataset.faqOpen === 'true';

    cancelFaqAnimations();

    document.querySelectorAll('.faq-item').forEach(function(item) {
      var body = item.querySelector('.faq-body');
      var btn  = item.querySelector('.faq-q');
      var icon = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'false';
      item.classList.remove('is-open');
      if (btn)  { btn.classList.remove('is-open');  btn.setAttribute('aria-expanded', 'false'); }
      if (icon)   icon.classList.remove('is-open');
      if (body)   body.style.maxHeight = '0px';
    });

    if (!wasOpen) {
      var body  = clickedItem.querySelector('.faq-body');
      var inner = clickedItem.querySelector('.faq-body-inner');
      var btn   = clickedItem.querySelector('.faq-q');
      var icon  = clickedItem.querySelector('.faq-icon');
      clickedItem.dataset.faqOpen = 'true';
      clickedItem.classList.add('is-open');
      if (btn)  { btn.classList.add('is-open');  btn.setAttribute('aria-expanded', 'true'); }
      if (icon)   icon.classList.add('is-open');
      if (body && inner) body.style.maxHeight = inner.scrollHeight + 'px';
    }
  });
})();
