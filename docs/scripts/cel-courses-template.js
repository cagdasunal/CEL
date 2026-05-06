/*!
 * cel-courses-template.js — CEL Course detail CMS template
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-courses-template.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-courses-template.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-courses-template.min.js
 *
 * Loaded via Webflow Page Settings -> Custom Code:
 *   <script src="https://cel.englishcollege.com/scripts/cel-courses-template.min.js?v=2.0.0" defer></script>
 *
 * Behavior bundled (1 IIFE, guarded):
 *   1. celCoursesFaqToc v1.0.0 — category-FAQ DOM-move + TOC smooth scroll + scrollspy
 *
 * Inline-in-Webflow contract (must remain in Page Settings -> Inside <head> tag):
 *   - <link rel="alternate" hreflang="x-default" ... data-wg-notranslate="true" class="weglot-exclude">
 *     (the x-default link MUST stay weglot-excluded so it always points to EN canonical)
 *   - <script id="ld-course" type="application/ld+json"> {baseline JSON-LD with {{wf}} bindings}
 *     (NOT weglot-excluded — Weglot now translates `name`/`description` and rewrites `url`
 *      automatically, so locale pages get correct schema server-side, no JS rewrite needed)
 *
 * Bundle is loaded with `defer`, so the IIFE runs after document parse but before
 * the load event. Per rules/cel-page-scripts-deploy.md, IIFEs run immediately on
 * load — no event listener wrapper needed.
 *
 * v2.0.0 (2026-05-06) — Removed celCoursesLocalize and celCoursesSchemaList IIFEs.
 * Schema is now fully server-rendered with Webflow CMS bindings + Weglot's automatic
 * JSON-LD translation (name/description keys + url/link/redirecturl URL rewriting).
 * No JavaScript-injected schema. Architectural decision per tracker 080 + Weglot
 * native JSON-LD support per https://developers.weglot.com/wordpress/filters/translations-filters
 *
 * v1.0.0 (2026-05-06) — Initial bundle. See tracker 080-review-fix-2026-05-06.md
 */

/* ============================================================
   1. celCoursesFaqToc v1.0.0
   Category-FAQ DOM-move + TOC smooth scroll + scrollspy.
   ============================================================ */
(function () {
  if (window.__celCoursesFaqToc) return;
  window.__celCoursesFaqToc = true;

  const categories = document.querySelectorAll('.faq_categories .w-dyn-item[data-category]');
  if (!categories.length) return;

  // 1) Map categories and set stable IDs = data-category slug
  const catMap = {};
  categories.forEach(function (cat) {
    const slug = (cat.getAttribute('data-category') || '').trim();
    if (!slug) return;
    if (cat.id !== slug) cat.id = slug;
    catMap[slug] = cat.querySelector('.faq_wrapper') || cat;
  });

  // 2) Move FAQ items into their matching category container (idempotent)
  let moved = 0;
  document.querySelectorAll('.faq_list .w-dyn-item[data-category]').forEach(function (item) {
    const slug = (item.getAttribute('data-category') || '').trim();
    const target = catMap[slug];
    if (target && !target.contains(item)) {
      target.appendChild(item);
      moved++;
    }
  });
  if (moved) {
    const faqList = document.querySelector('.faq_list');
    if (faqList) faqList.style.display = 'none';
  }

  // 3) Resolve scroll offset: data-attr -> CSS var -> header height -> 146 default
  function getCssVarPx(name) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }
  function getAttrPx() {
    const a = document.documentElement.getAttribute('data-scroll-offset')
         || document.documentElement.getAttribute('data-faq-offset');
    const n = parseInt(a || '', 10);
    return Number.isFinite(n) ? n : null;
  }
  function getHeaderPx() {
    const el = document.querySelector('[data-header], .navbar_component, .navbar, header[role="banner"], header');
    return el ? Math.ceil(el.getBoundingClientRect().height) : null;
  }
  let OFFSET = getAttrPx();
  if (OFFSET === null) OFFSET = getCssVarPx('--faq-scroll-offset');
  if (OFFSET === null) OFFSET = getHeaderPx();
  if (OFFSET === null) OFFSET = 146;

  // 4) Custom smooth scroll with controllable duration + offset
  function smoothScrollTo(targetY, duration) {
    const html = document.documentElement;
    const prevBehavior = html.style.scrollBehavior;
    html.style.scrollBehavior = 'auto';

    const startY = window.pageYOffset;
    const startTime = performance.now();

    function easeInOutQuad(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }

    function loop(now) {
      let t = (now - startTime) / duration;
      if (t > 1) t = 1;
      const p = easeInOutQuad(t);
      window.scrollTo(0, startY + (targetY - startY) * p);
      if (t < 1) {
        requestAnimationFrame(loop);
      } else {
        html.style.scrollBehavior = prevBehavior || '';
      }
    }
    requestAnimationFrame(loop);
  }

  // 5) Wire up TOC links (.toc_link or .toc-link)
  const tocLinks = document.querySelectorAll('.toc_link[data-category], .toc-link[data-category]');
  tocLinks.forEach(function (link) {
    const slug = (link.getAttribute('data-category') || '').trim();
    if (!slug) return;
    link.setAttribute('href', '#' + slug);

    link.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();

      const target = document.getElementById(slug);
      if (!target) return;
      const top = target.getBoundingClientRect().top + window.pageYOffset - OFFSET;
      smoothScrollTo(top, 900);
      if (history && history.replaceState) history.replaceState(null, '', '#' + slug);
    }, { passive: false });
  });

  // 6) If page loads with a hash, correct position with offset
  if (location.hash && location.hash.length > 1) {
    const initTarget = document.getElementById(location.hash.substring(1));
    if (initTarget) {
      setTimeout(function () {
        const top = initTarget.getBoundingClientRect().top + window.pageYOffset - OFFSET;
        window.scrollTo(0, top);
      }, 0);
    }
  }

  // 7) Scrollspy — highlight active TOC item
  function onScroll() {
    const scrollPos = window.pageYOffset + OFFSET + 5;
    let currentSlug = null;

    categories.forEach(function (cat) {
      if (cat.offsetTop <= scrollPos) {
        currentSlug = cat.id;
      }
    });

    if (currentSlug) {
      document.querySelectorAll('.toc_item.is-faq').forEach(function (item) {
        item.classList.toggle(
          'is-active',
          item.querySelector('[data-category="' + currentSlug + '"]') !== null
        );
      });
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  onScroll();
})();
