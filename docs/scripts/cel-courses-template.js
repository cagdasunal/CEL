/*!
 * cel-courses-template.js — CEL Course detail CMS template
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-courses-template.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-courses-template.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-courses-template.min.js
 *
 * Loaded via Webflow Page Settings -> Custom Code:
 *   <script src="https://cel.englishcollege.com/scripts/cel-courses-template.min.js?v=1.0.0" defer></script>
 *
 * Behavior bundled (3 IIFEs, all guarded):
 *   1. celCoursesLocalize v1.0.0 — locale-rewrite of #ld-course JSON-LD + og:* meta
 *   2. celCoursesFaqToc v1.0.0   — category-FAQ DOM-move + TOC smooth scroll + scrollspy
 *   3. celCoursesSchemaList v1.0.0 — populate ItemList.itemListElement from .schema_link DOM (legacy fallback)
 *
 * Inline-in-Webflow contract (must remain in Page Settings -> Inside <head> tag):
 *   - <link rel="alternate" hreflang="x-default" href="..." data-wg-notranslate="true" class="weglot-exclude">
 *   - <script id="ld-course" type="application/ld+json" class="weglot-exclude" data-wg-notranslate="true"> {baseline JSON-LD with {{wf}} bindings}
 *   These cannot move out — Webflow CMS field bindings only render in inline custom code.
 *
 * Bundle is loaded with `defer`, so all IIFEs run AFTER document parse but before
 * the load event. Per rules/cel-page-scripts-deploy.md, IIFEs run immediately on
 * load — no event listener wrapper needed.
 *
 * Migration date: 2026-05-06. Tracker: docs/reviews/080-review-fix-2026-05-06.md
 */

/* ============================================================
   1. celCoursesLocalize v1.0.0
   Locale-rewrite of #ld-course JSON-LD + og:* meta injection.
   Bugs from the original inline code that this fixes:
     - Bug 1: breadcrumb position 3 name now uses pageTitle (was EN literal)
     - Bug 2: breadcrumb position 1 URL now localized per `lang` (was hardcoded EN)
     - Bug 3: x-default hreflang is now static in Webflow head (was JS-injected)
     - Bug 4: empty hasCourse:[] property removed entirely
     - Bug 7: localizedUrl falls back to window.location when hreflang is missing
   ============================================================ */
(function () {
  if (window.__celCoursesLocalize) return;
  window.__celCoursesLocalize = true;

  const LOCALE_RE = /^\/(de|es|fr|it|pt|ja|ko|ar)(?:\/|$)/;
  const ORIGIN = 'https://www.englishcollege.com';
  const m = window.location.pathname.match(LOCALE_RE);
  const lang = m ? m[1] : 'en';

  const ogLocaleMap = {
    en: 'en_US', it: 'it_IT', es: 'es_ES', de: 'de_DE',
    fr: 'fr_FR', pt: 'pt_BR', ja: 'ja_JP', ko: 'ko_KR', ar: 'ar_SA'
  };

  function setMeta(prop, content) {
    if (!content) return;
    let el = document.querySelector('meta[property="' + prop + '"]');
    if (!el) {
      el = document.createElement('meta');
      el.setAttribute('property', prop);
      document.head.appendChild(el);
    }
    el.setAttribute('content', content);
  }

  function homepageForLang(l) {
    return ORIGIN + '/' + (l === 'en' ? '' : l + '/');
  }

  const canonical = window.location.href.split('?')[0].split('#')[0];

  setMeta('og:url', canonical);
  setMeta('og:locale', ogLocaleMap[lang] || 'en_US');
  setMeta('og:site_name', 'College of English Language');

  const ldTag = document.getElementById('ld-course');
  if (!ldTag || !ldTag.textContent.trim()) return;

  try {
    const data = JSON.parse(ldTag.textContent.trim());
    if (!data['@graph'] || !Array.isArray(data['@graph'])) return;

    const pageTitle = (document.title || '').trim();
    const descMeta = document.querySelector('meta[name="description"]');
    const pageDesc = descMeta ? (descMeta.content || '').trim() : '';

    // Resolve localized URLs (with fallback to current location if hreflang missing)
    let localizedUrl = null, parentUrl = null, coursesLabel = 'Courses';
    if (lang !== 'en') {
      const altLink = document.querySelector('link[rel="alternate"][hreflang="' + lang + '"]');
      if (altLink && altLink.href) {
        localizedUrl = altLink.href.split('?')[0].split('#')[0];
      } else {
        // Bug 7 fix: fall back to current URL when Weglot hasn't injected matching hreflang
        localizedUrl = canonical;
      }
      if (localizedUrl.charAt(localizedUrl.length - 1) !== '/') localizedUrl += '/';
      parentUrl = localizedUrl.replace(/[^/]+\/$/, '');
      const coursesLink = document.querySelector('#link_courses');
      if (coursesLink && coursesLink.textContent.trim()) {
        coursesLabel = coursesLink.textContent.trim();
      }
    }

    data['@graph'].forEach(function (node) {
      if (!node || !node['@type']) return;

      if (node['@type'] === 'EducationalOccupationalProgram') {
        if (pageTitle) node.name = pageTitle;
        if (pageDesc) node.description = pageDesc;
        if (localizedUrl) {
          node['@id'] = localizedUrl + '#program';
          node.url = localizedUrl;
          node.inLanguage = lang;
        }
      }

      if (node['@type'] === 'BreadcrumbList' && localizedUrl) {
        node['@id'] = localizedUrl + '#breadcrumbs';
        if (Array.isArray(node.itemListElement)) {
          node.itemListElement.forEach(function (item) {
            if (item.position === 1) {
              // Bug 2 fix: localize CEL homepage so breadcrumb stays in-language
              item.item = homepageForLang(lang);
            } else if (item.position === 2) {
              item.name = coursesLabel;
              item.item = parentUrl;
            } else if (item.position === 3) {
              item.item = localizedUrl;
              // Bug 1 fix: localize course name from Weglot-translated <title>
              if (pageTitle) item.name = pageTitle;
            }
          });
        }
      }
    });

    ldTag.textContent = JSON.stringify(data);
  } catch (err) {
    if (window.console) console.error('[celCoursesLocalize]', err);
  }
})();

/* ============================================================
   2. celCoursesFaqToc v1.0.0
   Category-FAQ DOM-move + TOC smooth scroll + scrollspy.
   Consolidates the TWO duplicate FAQ scripts from the original inline code:
     - Removes the unguarded HEAD-level "[FAQ] init" script
     - Keeps the comprehensive setup logic (DOM moves, scrollspy, smooth scroll)
     - Strips production console.log calls
   Note: this is a category-grouped FAQ layout. For pages with the
   standard accordion FAQ (`celfaq1`), include that bundle separately.
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

/* ============================================================
   3. celCoursesSchemaList v1.0.0
   Populate ItemList.itemListElement from .schema_link DOM.
   Only fires if the page has BOTH a #ld-course JSON-LD WITH an ItemList node
   AND .schema_list .schema_link elements present. The course-detail template
   typically uses EducationalOccupationalProgram (no ItemList), so this is a
   no-op for course detail pages — included for the listing-page case.
   Bug fix from original inline code:
     - link.getAttribute("href", 2) had a bogus second argument; corrected.
   ============================================================ */
(function () {
  if (window.__celCoursesSchemaList) return;
  window.__celCoursesSchemaList = true;

  const schemaEl = document.getElementById('ld-course') || document.getElementById('schema');
  if (!schemaEl) return;

  const links = document.querySelectorAll('.schema_list .schema_link');
  if (!links.length) return;

  try {
    const data = JSON.parse(schemaEl.textContent);
    const graph = data['@graph'] || [];
    const itemList = graph.find(function (n) { return n && n['@type'] === 'ItemList'; });
    if (!itemList) return;

    const items = [];
    links.forEach(function (link, i) {
      const href = link.getAttribute('href');
      if (!href) return;
      const url = new URL(href, window.location.origin).href;
      const name = (link.textContent || '').trim();
      items.push({
        '@type': 'ListItem',
        position: i + 1,
        name: name,
        item: url
      });
    });

    if (items.length) {
      itemList.itemListElement = items;
      schemaEl.textContent = JSON.stringify(data);
    }
  } catch (e) {
    if (window.console) console.error('[celCoursesSchemaList]', e);
  }
})();
