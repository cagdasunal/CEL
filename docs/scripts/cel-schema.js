/*!
 * cel-schema.js — CEL site-wide JSON-LD schema injector
 *
 * Auto-extracts FAQPage from .faq-item DOM (no rebuild on FAQ edits)
 * Auto-builds BreadcrumbList from URL path + label map
 * Optional per-page static schema (Course / Article / etc.) via lookup table
 *
 * Selector contract — see rules/faq-schema-contract.md.
 *   Renaming any of these will silently disable FAQPage schema:
 *   .faq-item                     wrapper for one Q/A pair
 *   .faq-question-text [p]        question text source
 *   .faq-body-inner               answer text source
 *
 * Loaded with <script src="cel-schema.min.js" defer> in each page's Custom
 * Code, so the IIFE runs after HTML parsing completes — no DOM-ready
 * listener needed.
 *
 * Bundle pattern: tools/cel-page-scripts/ — see deploy-page-scripts skill.
 * Public URL: https://cel.englishcollege.com/scripts/cel-schema.min.js
 */
(function () {
  'use strict';

  if (window.__CEL_SCHEMA_V1__) return;
  window.__CEL_SCHEMA_V1__ = true;

  const ORIGIN = 'https://www.englishcollege.com';

  // Breadcrumb labels keyed by absolute path. Add an entry whenever a new
  // page is added; otherwise the extractor falls back to a title-cased slug.
  const BREADCRUMB_LABELS = {
    '/vancouver': 'Vancouver',
    '/vancouver/costs': 'Costs',
    '/vancouver/adults-16': 'Adults 16+',
    '/vancouver/duration-guide': 'How Long to Study',
    '/vancouver/vs-toronto': 'Vancouver vs Toronto'
  };

  // Per-page static JSON-LD blocks (Course / Article / etc.).
  // Filled in Phase 3 page-by-page. An empty map means FAQ + Breadcrumb only.
  const STATIC_SCHEMA_BY_PATH = {
    // '/vancouver/adults-16': { '@type': 'Course', name: '...', ... }
  };

  function inject(obj) {
    try {
      const s = document.createElement('script');
      s.type = 'application/ld+json';
      s.textContent = JSON.stringify(obj);
      document.head.appendChild(s);
    } catch (e) {
      // Schema must never break the page
    }
  }

  function clean(str) {
    return (str || '').replace(/\s+/g, ' ').trim();
  }

  function extractFAQs() {
    const items = document.querySelectorAll('.faq-item');
    if (!items.length) return [];
    const out = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const qEl = item.querySelector('.faq-question-text p') || item.querySelector('.faq-question-text');
      const aEl = item.querySelector('.faq-body-inner');
      const q = clean(qEl ? qEl.textContent : '');
      const a = clean(aEl ? aEl.textContent : '');
      if (q && a) {
        out.push({
          '@type': 'Question',
          name: q,
          acceptedAnswer: { '@type': 'Answer', text: a }
        });
      }
    }
    return out;
  }

  function titleCase(slug) {
    return slug.split('-').map(function (w) {
      return w ? w.charAt(0).toUpperCase() + w.slice(1) : w;
    }).join(' ');
  }

  function buildBreadcrumb(rawPath) {
    const path = (rawPath || '/').replace(/\/+$/, '') || '/';
    const items = [{
      '@type': 'ListItem',
      position: 1,
      name: 'Home',
      item: ORIGIN + '/'
    }];
    if (path !== '/') {
      const parts = path.split('/');
      let acc = '';
      for (let i = 1; i < parts.length; i++) {
        if (!parts[i]) continue;
        acc += '/' + parts[i];
        const label = BREADCRUMB_LABELS[acc] || titleCase(parts[i]);
        items.push({
          '@type': 'ListItem',
          position: items.length + 1,
          name: label,
          item: ORIGIN + acc
        });
      }
    }
    return {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: items
    };
  }

  const path = (location.pathname || '/').replace(/\/+$/, '') || '/';

  // 1. FAQPage — only emitted when the page actually has FAQs
  const faqs = extractFAQs();
  if (faqs.length) {
    inject({
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faqs
    });
  }

  // 2. BreadcrumbList — every page
  inject(buildBreadcrumb(path));

  // 3. Optional per-page static schema (Course / Article)
  const entry = STATIC_SCHEMA_BY_PATH[path];
  if (entry) {
    if (!entry['@context']) entry['@context'] = 'https://schema.org';
    inject(entry);
  }
})();
