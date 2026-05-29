/*!
 * cel-events.js — CEL site-wide behavioral analytics -> dataLayer (Basecamp #457)
 *
 * Source-of-truth: tools/cel-events-js/cel-events.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-events.js        (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-events.min.js
 * Wire-up:         Site Settings -> Custom Code -> Footer  <script src=... defer></script>
 *
 * Pushes GTM-format events to window.dataLayer; GTM routes them to GA4
 * (G-VZSPVZ9NDR). INERT until GTM is live (GA4 gtag ignores {event:...} objects).
 * Strategy + the GA4-report map: ANALYTICS-STRATEGY.md.
 *
 * LANGUAGE-AGNOSTIC BY DESIGN (the site is 8-locale Weglot; we control only the
 * English source; Weglot TRANSLATES URL SLUGS on some locales — e.g. de:
 * /courses->/kurse, /housing->/unterkunft, contact->contato/contacta-con-cel).
 * So detection NEVER matches translated words:
 *   - page identity  -> `data-wf-page` (Webflow template id; identical on every locale)
 *   - catalog cards   -> classes `.course-card_link` / `.accom_float-card`
 *   - blog content    -> the `/post/` path segment (structural; NOT translated by Weglot — verified)
 *   - promo block     -> class `.section_blog` (Webflow class; not translated)
 *   - tabs/TOC/FAQ    -> `data-w-tab` / `data-target`|`data-category` / position index
 *   - lang switcher   -> class `.button_weglot` (+ Weglot wg-/weglot classes)
 *   - page_locale     -> URL locale prefix
 * The ONLY path literals matched are /booking (apply), /offers (offers), and /post/
 * (blog content) — all VERIFIED byte-identical across all 8 locales. Everything else
 * degrades to navigation_click (with the raw link_url) + page_id, so every link on
 * every page in every language produces data.
 *
 * Events (all carry page_id + page_type + page_locale):
 *   page_entry                                 acquisition source on load (need b: organic -> /post)
 *   view_item_list / select_item / view_item   courses+housing catalog (GA4 items)
 *   select_content                             blog-post link clicks (promo, list, related, category)
 *   generate_lead                              contact|newsletter|schedule_call(HubSpot)
 *   cta_click                                  apply offers contact-via-nav email phone whatsapp directions blog_see_all
 *   language_select                            Weglot language switch
 *   tab_select | faq_toggle | toc_click        on-page engagement
 *   navigation_click                           header/footer nav + in_content + outbound links
 *   scroll_depth                               25/50/75/90
 *
 * Version: 2.0.0
 * Last update: 2026-05-29
 */
(function () {
  'use strict';

  const LOCALES = ['de', 'fr', 'es', 'it', 'pt', 'ko', 'ja', 'ar'];
  // Webflow template ids -> friendly type. IDs are identical across all locales
  // (verified: /de/kurse == course_list, /de/unterkunft == housing_list). New pages
  // are still tracked via the raw page_id; add them here only for a friendly name.
  const PAGE_TYPES = {
    '667453c576e8d35c454cc9bc': 'home',
    '667453c576e8d35c454ccc54': 'landing', '685a4a48f7d57ee291672413': 'landing',
    '685a950e98870e8352d6cbae': 'landing', '69c7d70e7b6c140db0aba732': 'landing',
    '69ab1f80d2d74bc167e4fea1': 'landing', '69ce8a2a6612261e96d8a8c5': 'landing',
    '667453c576e8d35c454ccb11': 'course_detail', '667453c576e8d35c454cca68': 'course_list',
    '69e8ab613e1e04f22496dd5b': 'housing_detail', '667453c576e8d35c454ccbba': 'housing_list',
    '667453c576e8d35c454cca46': 'contact', '667453c576e8d35c454cca24': 'booking',
    '691c407175e5ecd4423479eb': 'offers', '667453c576e8d35c454ccb30': 'blog_post',
    // verified live 2026-05-29 (data-wf-page identical across locales)
    '667453c576e8d35c454cca09': 'blog_list', '687658b861f1ac622a2265ea': 'category',
    '667453c576e8d35c454ccc39': 'voices',
    '68d854edf776fcec7329321f': 'faq', '68d19d7e5774a9ebbdc286c4': 'policies',
    '69a8402e762a4d4bcafee808': 'student_services',
    '667453c576e8d35c454ccbdb': 'landing', '66bb673c372cddefba5be79b': 'landing',
    '667453c576e8d35c454ccc36': 'landing', '667453c576e8d35c454ccc38': 'landing',
    '667453c576e8d35c454ccc3a': 'landing'
  };

  function barePath(pathname) {
    const parts = (pathname || '').split('/');
    if (LOCALES.indexOf((parts[1] || '').toLowerCase()) !== -1) parts.splice(1, 1);
    return ('/' + parts.filter(Boolean).join('/')) || '/';
  }
  function lastSeg(url) {
    const ps = (url.pathname || '').split('/').filter(Boolean);
    return ps.length ? ps[ps.length - 1] : '';
  }
  function pageTypeFromId(id) { return PAGE_TYPES[id] || 'other'; }
  // A blog-post link, locale-agnostically: Weglot keeps the /post/ segment on every
  // locale (verified: /post/..., /de/post/..., /fr/post/...). Strip locale, test /post/.
  function isPostPath(pathname) { return /^\/post\//.test(barePath(pathname || '')); }
  // Acquisition source from referrer host + utm_source (need b). utm wins; google host
  // -> organic/paid umbrella 'google_organic'; own host -> internal; other host -> referral.
  function acqSource(referrerHost, utmSource) {
    if (utmSource) return utmSource;
    if (!referrerHost) return 'direct';
    if (/(^|\.)google\./.test(referrerHost)) return 'google_organic';
    if (referrerHost.indexOf('englishcollege.com') !== -1) return 'internal';
    return 'referral';
  }
  // CTA intent. Protocol/host signals are universal. The ONLY path literals matched
  // are /booking and /offers — VERIFIED byte-identical across all 8 locales. Translated
  // slugs are NEVER matched here (courses->kurse, contact->contato). Unmatched links
  // degrade to navigation_click (carrying the raw link_url) — so all pages, all langs.
  function classifyHref(raw, url) {
    if (!raw || raw.charAt(0) === '#') return null;
    if (/^mailto:/i.test(raw)) return 'email';
    if (/^tel:/i.test(raw)) return 'phone';
    const host = (url.hostname || '').toLowerCase();
    if (host.indexOf('whatsapp.com') !== -1 || host === 'wa.me') return 'whatsapp';
    if (host === 'maps.app.goo.gl' || host === 'maps.google.com' ||
        (/(^|\.)google\.[a-z.]+$/.test(host) && (url.pathname || '').indexOf('/maps') !== -1)) return 'directions';
    const p = barePath(url.pathname || '');
    if (p === '/booking') return 'apply';     // invariant across all 8 locales (verified)
    if (p === '/offers') return 'offers';      // invariant across all 8 locales (verified)
    return null;
  }

  // test seam — harmless in browser (module undefined)
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      classifyHref: classifyHref, lastSeg: lastSeg, barePath: barePath,
      pageTypeFromId: pageTypeFromId, isPostPath: isPostPath, acqSource: acqSource
    };
  }

  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.__celEvents) return;
  window.__celEvents = true;

  const PAGE_ID = (document.documentElement.getAttribute('data-wf-page') || '');
  const PT = pageTypeFromId(PAGE_ID);
  const LOC = (function () {
    const seg = (location.pathname.split('/')[1] || '').toLowerCase();
    if (LOCALES.indexOf(seg) !== -1) return seg;
    return ((document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0]) || 'en';
  })();

  window.dataLayer = window.dataLayer || [];
  function push(name, params) {
    const o = { event: name, page_id: PAGE_ID, page_type: PT, page_locale: LOC };
    for (const k in params) if (Object.prototype.hasOwnProperty.call(params, k)) o[k] = params[k];
    window.dataLayer.push(o);
  }
  function pushEcom(name, ecommerce) {
    window.dataLayer.push({ ecommerce: null });
    window.dataLayer.push({ event: name, page_id: PAGE_ID, page_type: PT, page_locale: LOC, ecommerce: ecommerce });
  }
  function humanize(slug) {
    return String(slug).replace(/-/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }
  function indexAmong(el, sel) {
    const list = document.querySelectorAll(sel);
    for (let i = 0; i < list.length; i++) if (list[i] === el) return i;
    return 0;
  }
  function cardItem(a, index) {
    const id = lastSeg(a);
    if (!id) return null;
    return { item_id: id, item_name: humanize(id), item_category: a.classList.contains('course-card_link') ? 'courses' : 'housing', index: index };
  }
  function navLocation(a) {
    if (a.closest('nav, .navbar, [class*="navbar"], .w-nav')) return a.closest('.w-dropdown') ? 'header_dropdown' : 'header';
    if (a.closest('footer, .footer, [class*="footer_"]')) return 'footer';
    return null;
  }
  function linkText(a) { return (a.textContent || '').trim().slice(0, 80); }
  function urlOf(a) { try { return new URL(a.href, location.href); } catch (_) { return null; } }

  // ---- acquisition source on load (once) — client need (b): organic landings on /post ----
  (function () {
    let rh = '';
    try { const r = document.referrer; if (r) rh = new URL(r).hostname; } catch (_) {}
    let us = '';
    try { us = new URLSearchParams(location.search).get('utm_source') || ''; } catch (_) {}
    push('page_entry', { entry_source: acqSource(rh, us), referrer_host: rh, is_blog_post: (PT === 'blog_post') });
  })();

  const CARD_SEL = 'a.course-card_link, a.accom_float-card';
  const WEGLOT_SEL = '.button_weglot a, [class*="weglot"] a, [class*="wg-"] a, .country-selector a, a[data-l]';

  // ---- one delegated capture-phase click listener (specific -> generic) ----
  document.addEventListener('click', function (e) {
    const t = e.target;
    if (!t || !t.closest) return;
    const card = t.closest(CARD_SEL);                                  // catalog card -> select_item
    if (card) {
      const it = cardItem(card, indexAmong(card, CARD_SEL));
      if (it) pushEcom('select_item', { item_list_name: PT, items: [it] });
      return;
    }
    const hc = t.closest('a.button.course');                           // homepage course selector (href=# JS tabs)
    if (hc) {                                                          // keyed by position (language-agnostic)
      const ix = indexAmong(hc, 'a.button.course');
      pushEcom('select_item', { item_list_name: 'home_course_selector', items: [{ item_id: 'home-course-' + ix, item_name: 'Home course ' + (ix + 1), item_category: 'courses', index: ix }] });
      return;
    }
    const faq = t.closest('.faq-q');                                   // FAQ accordion (open/close)
    if (faq) { push('faq_toggle', { faq_index: indexAmong(faq, '.faq-q') }); return; }
    const toc = t.closest('.stoc_link, .toc_link');                    // landing TOC (.stoc_link), blog/FAQ-category TOC (.toc_link[.is-faq])
    if (toc) {
      const s = toc.getAttribute('data-target') || toc.getAttribute('data-category') || (toc.getAttribute('href') || '').replace(/^#/, '');
      if (s) push('toc_click', { section: s });
      return;
    }
    const tab = t.closest('.w-tab-link');                              // Webflow tab
    if (tab) { const tn = tab.getAttribute('data-w-tab'); if (tn) push('tab_select', { tab_name: tn }); return; }

    const a = t.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href') || '';

    // language switcher (Weglot) -> language_select  (BEFORE /post + nav: a lang link can be /de/post/..)
    const wg = a.closest(WEGLOT_SEL) || (a.matches && a.matches(WEGLOT_SEL) ? a : null);
    if (wg) {
      const m = href.match(/\/(de|fr|es|it|pt|ko|ja|ar|en)(\/|$)/);
      const to = a.getAttribute('data-l') || (m && m[1]) || (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 12) || 'unknown';
      push('language_select', { from_locale: LOC, to_language: to });
      return;
    }

    // "From Our Blog" promo (.section_blog) -> select_content (post) or cta blog_see_all  [client need a]
    if (a.closest('.section_blog')) {
      const u = urlOf(a);
      if (u && isPostPath(u.pathname)) { push('select_content', { content_type: 'blog_post', content_id: lastSeg(u), link_url: a.href, source_block: 'from_our_blog' }); return; }
      if (u && barePath(u.pathname) === '/blog') { push('cta_click', { cta_id: 'blog_see_all', link_url: a.href }); return; }
      // any other .section_blog link falls through to normal classification below
    }

    // any blog-post link (blog list cards, related posts, category cards, in-content) -> select_content
    const au = urlOf(a);
    if (au && isPostPath(au.pathname)) {
      const sb = PT === 'blog_list' ? 'blog_list' : PT === 'blog_post' ? 'related_posts' : PT === 'category' ? 'category' : 'in_content';
      push('select_content', { content_type: 'blog_post', content_id: lastSeg(au), link_url: a.href, source_block: sb });
      return;
    }

    // CTA intent (apply / offers / email / phone / whatsapp / directions)
    const id = classifyHref(href, a);
    if (id) { push('cta_click', { cta_id: id, link_url: a.href }); return; }

    // "Unlock Offer" influencer CTA (href=#, sits in navbar) -> offers intent (is-influencer is an English class)
    if (a.classList.contains('is-influencer')) { push('cta_click', { cta_id: 'offers', link_url: a.href }); return; }

    // header / footer navigation
    const loc = navLocation(a);
    if (loc) { push('navigation_click', { link_url: a.href, link_text: linkText(a), nav_location: loc }); return; }

    // in-content link catch-all (every other real link: same-origin internal OR outbound).
    // Captures contact CTAs (/contact-cel etc.), cross-links, sibling landings, partners.
    // Skips pure in-page anchors (#...) and non-navigational schemes (no hostname).
    if (href && href.charAt(0) !== '#' && au && au.hostname) {
      push('navigation_click', { link_url: a.href, link_text: linkText(a), nav_location: (au.hostname === location.hostname) ? 'in_content' : 'outbound' });
    }
  }, true);

  // ---- catalog: view_item (detail) + view_item_list (card impressions) ----
  if (PT === 'course_detail' || PT === 'housing_detail') {
    const id = lastSeg(location);
    if (id) pushEcom('view_item', { items: [{ item_id: id, item_name: humanize(id), item_category: PT === 'course_detail' ? 'courses' : 'housing', index: 0 }] });
  }
  const cards = document.querySelectorAll(CARD_SEL);
  if (cards.length && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(function (entries) {
      const seen = [];
      for (let i = 0; i < entries.length; i++) {
        if (!entries[i].isIntersecting) continue;
        const it = cardItem(entries[i].target, indexAmong(entries[i].target, CARD_SEL));
        if (it) seen.push(it);
        io.unobserve(entries[i].target);
      }
      if (seen.length) pushEcom('view_item_list', { item_list_name: PT, items: seen });
    }, { threshold: 0.5 });
    for (let i = 0; i < cards.length; i++) io.observe(cards[i]);
  }

  // ---- conversions: forms (contact|newsletter) + HubSpot meeting booking ----
  const leadFired = {};
  function fireLead(name) {
    if (leadFired[name]) return;
    leadFired[name] = true;
    push('generate_lead', { form_name: name });
  }
  function leadName(form) {
    const n = (form.getAttribute('data-name') || form.id || '').toLowerCase();
    if (n.indexOf('contact') !== -1) return 'contact';
    if (n.indexOf('newsletter') !== -1) return 'newsletter';
    return null;
  }
  function visible(el) { return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length)); }
  function watchForm(form) {
    const name = leadName(form);
    if (!name) return;
    const wrap = form.closest('.w-form');
    const done = wrap ? wrap.querySelector('.w-form-done') : null;
    if (!done) return;
    const obs = new MutationObserver(function () {
      if (leadFired[name] || !visible(done)) return;
      fireLead(name); obs.disconnect();
    });
    obs.observe(done, { attributes: true, attributeFilter: ['style', 'class'] });
    if (visible(done)) { fireLead(name); obs.disconnect(); }
  }
  const forms = document.querySelectorAll('.w-form form');
  for (let i = 0; i < forms.length; i++) watchForm(forms[i]);
  window.addEventListener('message', function (e) {
    let oh;
    try { oh = new URL(e.origin).hostname; } catch (_) { return; }   // meetings.hubspot.com OR regional meetings-eu1 etc.
    if (!/(^|\.)meetings(-[a-z0-9]+)?\.hubspot\.com$/.test(oh)) return;
    if (e.data && e.data.meetingBookSucceeded === true) fireLead('schedule_call');
  });

  // ---- passive: scroll depth (25/50/75/90, once each, short-page guarded) ----
  const THRESH = [25, 50, 75, 90];
  const hit = {};
  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (max <= window.innerHeight * 0.2) return;
      const pct = (window.pageYOffset / max) * 100;
      for (let k = 0; k < THRESH.length; k++) {
        if (pct >= THRESH[k] && !hit[THRESH[k]]) {
          hit[THRESH[k]] = true;
          push('scroll_depth', { percent_scrolled: THRESH[k] });
        }
      }
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
})();
