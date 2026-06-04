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
 * Events (all carry page_id + page_type + page_locale + content_group).
 * >>> CANONICAL REFERENCE: tools/cel-events-js/EVENTS.md (full params, firing conditions,
 *     multilang notes, GA4 dim + key-event status). Keep that file + this legend in sync. <<<
 *   content_group                              coarse content bucket on EVERY event (home|landing|courses|
 *                                              housing|blog|offers|contact|booking|support) — from page_type,
 *                                              so reports cleanly separate content types per the client need
 *   page_entry                                 acquisition source on load (need b: organic -> /post)
 *   view_item_list / select_item / view_item   courses+housing catalog (GA4 items; item_category courses|housing)
 *   select_content                             blog-post link clicks — carries content_id (target slug),
 *                                              source_block (from_our_blog|blog_list|related_posts|category|in_content)
 *                                              AND source_page_type (WHICH page the click came from)
 *   generate_lead                              umbrella lead event; lead_type=contact|newsletter|sales_call|booking
 *                                              + lead_channel=web_form|scheduler|booking_widget (form_name kept)
 *   form_start                                 first focus/input on a tracked lead form (contact|newsletter) — start->submit rate
 *   cta_click                                  apply offers contact email phone whatsapp directions blog_see_all
 *                                              (+ cta_location: header/footer/hero/body_top/mid/bottom, + cta_text:
 *                                               button label — so multiple Apply/Contact buttons per page are comparable)
 *   language_select                            Weglot language switch
 *   tab_select | faq_toggle | toc_click        on-page engagement
 *   navigation_click                           header/footer nav + in_content links
 *   outbound_click                             cross-origin links (link_domain + outbound:true) — first-class, no longer a navigation_click
 *   video_start/_progress/_complete            native HTML5 <video> engagement (25/50/75/100; inert if no <video>; YT/Vimeo handled in GTM)
 *   search                                     site-search submit (search_term) — inert unless a type=search / [role=search] form exists
 *   scroll_depth                               25/50/75/90 (site-wide)
 *   engaged_page                               ONE genuine-engagement signal/page (15s active OR 50% scroll; trigger=dwell_15s|scroll_50, engaged_seconds) — page_type+locale aware, comparable across pages
 *   --- offers/promotions engagement (GA4-standard; inert unless .offer_item cards exist;
 *       works on /offers AND any page where promotions are embedded — same .offer_item class) ---
 *   view_promotion                             offer card VISIBLE in view (skips geo-hidden cards); promotion_id
 *                                              = language-invariant (data-offer-id | image CMS asset-id), + name/slot
 *   select_promotion                           offer card clicked: carries promotion_id/name/creative_slot, AND
 *                                              cta_id (apply|contact) when the click was on a card BUTTON
 *   offer_code_copy                            promo code copied (scoped to .page_code_base / [data-offer-code])
 *   cta_click (when inside .offer_item)        the offer card's Apply Now / Contact us button: cta_id (apply|contact),
 *                                              cta_location='offer_card', + promotion_id/promotion_name/creative_slot
 *                                              -> ties OFFER -> WHICH BUTTON -> outcome (booking/contact)
 *   --- blog deep engagement (Phase 1, 2026-06-04; per-language via page_locale) ---
 *   post_read                                  genuine read of a post: 30s active time OR 50% scroll (once; trigger=dwell_30s|scroll_50)
 *   post_scroll_depth                          per-post scroll 25/50/75/90 (carries post_slug, unlike generic scroll_depth)
 *   post_read_complete                         reached ~90% of a post; read_seconds = active read-time
 *   category_click                             click on a /category/ link (category_slug, source_page_type) — language-agnostic
 *   blog_list_scroll                           blog homepage / category list scroll 25/50/75/90 (list_type)
 *   related_post_click                         related-post click from inside a post (from_post -> to_post, position)
 *   --- Fidelo booking bridge (cel-fidelo.js postMessage from the cross-origin iframe) ---
 *   widget_open                                booking widget opened (clean denominator, distinct from apply_click + step=1)
 *   booking_step                               per-step progress (+ step_total, step_direction forward|back, step_duration_ms, selections, value/currency)
 *   booking_abandon                            left the widget without completing (carries the last step reached)
 *
 * Version: 2.4.1
 * Last update: 2026-06-05
 */
(function () {
  'use strict';

  const LOCALES = ['de', 'fr', 'es', 'it', 'pt', 'ko', 'ja', 'ar'];
  // Webflow template ids -> friendly type. IDs are identical across all locales
  // (verified: /de/kurse == course_list, /de/unterkunft == housing_list). New pages
  // are still tracked via the raw page_id; add them here only for a friendly name.
  // NOTE: when you add a page id here (or to CONTENT_GROUP below), ALSO add it to the GTM
  // mirror in gtm_fix_page_context.py (JS_PAGE_TYPE / JS_CONTENT_GROUP) or that page's GA4
  // AUTOMATIC events get page_type/content_group='other'. Guarded by test_page_context_sync.py.
  const PAGE_TYPES = {
    '667453c576e8d35c454cc9bc': 'home',
    '667453c576e8d35c454ccc54': 'landing', '685a4a48f7d57ee291672413': 'landing_sandiego',
    '685a950e98870e8352d6cbae': 'landing_vancouver', '69c7d70e7b6c140db0aba732': 'landing',
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
  // content_group = the COARSE content bucket, so reports cleanly separate courses vs housing
  // vs blog vs landing etc. on EVERY event (the user's "different type of content" need). Derived
  // purely from page_type (data-wf-page template id) — never a slug/word — so it's identical
  // across all 8 Weglot locales. content_group is a GA4-RESERVED page-scoped dimension (auto
  // populates the built-in "Content group" report), so it is set on the Google-tag config too.
  const CONTENT_GROUP = {
    home: 'home',
    landing: 'landing', landing_sandiego: 'landing', landing_vancouver: 'landing',
    course_list: 'courses', course_detail: 'courses',
    housing_list: 'housing', housing_detail: 'housing',
    blog_post: 'blog', blog_list: 'blog', category: 'blog', voices: 'blog',
    offers: 'offers', contact: 'contact', booking: 'booking',
    faq: 'support', policies: 'support', student_services: 'support'
  };
  function contentGroup(pt) { return CONTENT_GROUP[pt] || 'other'; }
  // A blog-post link, locale-agnostically: Weglot keeps the /post/ segment on every
  // locale (verified: /post/..., /de/post/..., /fr/post/...). Strip locale, test /post/.
  function isPostPath(pathname) { return /^\/post\//.test(barePath(pathname || '')); }
  // A blog-CATEGORY link, locale-agnostically (Weglot keeps /category/ on every locale,
  // same as /post/). Used to track category navigation as a first-class blog signal.
  function isCategoryPath(pathname) { return /^\/category\//.test(barePath(pathname || '')); }
  // Acquisition source from referrer host + utm_source (need b). utm wins; google host
  // -> organic/paid umbrella 'google_organic'; own host -> internal; other host -> referral.
  function acqSource(referrerHost, utmSource) {
    if (utmSource) return utmSource;
    if (!referrerHost) return 'direct';
    if (/(^|\.)google\./.test(referrerHost)) return 'google_organic';
    if (referrerHost.indexOf('englishcollege.com') !== -1) return 'internal';
    return 'referral';
  }
  // Contact-page slugs across ALL 8 locales (the contact CTA is a conversion, not nav,
  // and appears in nav/footer/hero/body — so match the DESTINATION, not a styling class).
  // Weglot TRANSLATES this slug, so unlike /booking & /offers it is NOT byte-identical;
  // this is the complete verified set (curl'd is-apply hrefs across all 8 locales 2026-05-30).
  // RE-VERIFY if Weglot changes a contact slug or a new locale is added (else it falls back to nav).
  //   /contact-cel (en, fr, ko, ja, ar) · /contact (de) · /contacta-con-cel (es) · /contato (it, pt)
  const CONTACT_PATHS = ['/contact-cel', '/contact', '/contacta-con-cel', '/contato'];

  // CTA intent. Protocol/host signals are universal. Path literals: /booking & /offers are
  // byte-identical across all 8 locales; the contact slug set is translated-but-enumerated
  // (CONTACT_PATHS). Other translated slugs (courses->kurse) are NEVER matched here —
  // unmatched links degrade to navigation_click (carrying the raw link_url).
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
    if (CONTACT_PATHS.indexOf(p) !== -1) return 'contact';  // translated slug set (verified 2026-05-30)
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
  const CG = contentGroup(PT);
  const LOC = (function () {
    const seg = (location.pathname.split('/')[1] || '').toLowerCase();
    if (LOCALES.indexOf(seg) !== -1) return seg;
    return ((document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0]) || 'en';
  })();

  window.dataLayer = window.dataLayer || [];
  function push(name, params) {
    const o = { event: name, page_id: PAGE_ID, page_type: PT, page_locale: LOC, content_group: CG };
    for (const k in params) if (Object.prototype.hasOwnProperty.call(params, k)) o[k] = params[k];
    window.dataLayer.push(o);
  }
  function pushEcom(name, ecommerce) {
    window.dataLayer.push({ ecommerce: null });
    window.dataLayer.push({ event: name, page_id: PAGE_ID, page_type: PT, page_locale: LOC, content_group: CG, ecommerce: ecommerce });
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
  // ---- offer-card identity (shared by the click handler's offer-CTA enrichment AND the
  //   offers IIFE below). promotion_id is language-invariant (data-offer-id attr, else the
  //   offer image's Webflow CMS asset-id 24-hex prefix, else positional). promotion_name is
  //   the visible title and IS locale-specific — join across locales via promotion_id. ----
  function offerCardName(card) {
    const t = card.querySelector('.offer-bento_title');
    return ((t && (t.textContent || '')).replace(/\s+/g, ' ').trim().slice(0, 80)) || '(untitled offer)';
  }
  function offerCardId(card) {
    const explicit = card.getAttribute('data-offer-id');
    if (explicit) return explicit;
    const img = card.querySelector('img[src]');
    const m = img && (img.getAttribute('src') || '').match(/([0-9a-f]{24})_/);
    if (m) return m[1];
    const slot = card.getAttribute('data-cel-offer-i');
    return 'offer-' + (slot != null ? slot : indexAmong(card, '.offer_item'));
  }
  function offerPromoParams(card) {
    return { promotion_id: offerCardId(card), promotion_name: offerCardName(card),
             creative_slot: indexAmong(card, '.offer_item') };
  }
  function navLocation(a) {
    if (a.closest('nav, .navbar, [class*="navbar"], .w-nav')) return a.closest('.w-dropdown') ? 'header_dropdown' : 'header';
    if (a.closest('footer, .footer, [class*="footer_"]')) return 'footer';
    return null;
  }
  function linkText(a) { return (a.textContent || '').trim().slice(0, 80); }
  function urlOf(a) { try { return new URL(a.href, location.href); } catch (_) { return null; } }

  // ---- CTA placement + label (so multiple Apply/Contact buttons on one page are distinguishable) ----
  // cta_location: WHERE the button sits, language-agnostic (no Webflow class dependence — CTAs aren't
  //   wrapped in stable section_* blocks). header/footer come from nav ancestry; otherwise bucket by the
  //   element's vertical position in the document: hero (first viewport), body_top/body_mid/body_bottom.
  function ctaLocation(a) {
    if (a.closest('nav, .navbar, [class*="navbar"], .w-nav')) return a.closest('.w-dropdown') ? 'header_dropdown' : 'header';
    if (a.closest('footer, .footer, [class*="footer_"]')) return 'footer';
    if (a.closest('.w-nav-overlay, [class*="mobile-menu"], [class*="menu_overlay"]')) return 'mobile_menu';
    let top;
    try {
      const r = a.getBoundingClientRect();
      top = r.top + (window.pageYOffset || document.documentElement.scrollTop || 0);
    } catch (_) { return 'unknown'; }
    const vh = window.innerHeight || 800;
    const docH = Math.max(document.documentElement.scrollHeight || 0, vh);
    if (top < vh) return 'hero';                         // within the first viewport
    const frac = top / docH;                              // position through the page
    if (frac < 0.34) return 'body_top';
    if (frac < 0.67) return 'body_mid';
    return 'body_bottom';
  }
  // cta_text: the button's own visible label, normalized (collapse whitespace, cap length). Lets you compare
  //   wording (e.g. "Apply Now" vs "Get Started"). Language-specific by nature — that's intended for A/B of copy.
  function ctaText(a) { return ((a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 60)) || '(none)'; }

  // ---- acquisition source on load (once) — client need (b): organic landings on /post ----
  (function () {
    let rh = '';
    try { const r = document.referrer; if (r) rh = new URL(r).hostname; } catch (_) {}
    let us = '';
    try { us = new URLSearchParams(location.search).get('utm_source') || ''; } catch (_) {}
    push('page_entry', { entry_source: acqSource(rh, us), referrer_host: rh, is_blog_post: (PT === 'blog_post') });
  })();

  const CARD_SEL = 'a.course-card_link, a.accom_float-card';
  // Weglot language switcher (JS-injected widget): <ul class="weglot_switcher country-select">
  //   <li class="wg-li de wg-flags"><a aria-label="Deutsch" href="#"></a></li>. Match ONLY the real
  //   switcher — the old broad arms [class*="weglot"] a / [class*="wg-"] a also matched <a> inside
  //   weglot-exclude content on other pages, poisoning to_language with scraped sentence text
  //   ("What a Langu", "why it's so…"). See audit 2026-05-30 H3/H4.
  const WEGLOT_SEL = '.weglot_switcher a, .wg-li a, .button_weglot a, .country-selector a, a[data-l]';

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
    const hc = PT === 'home' ? t.closest('a.button.course') : null;    // homepage course selector (href=# JS tabs) — home-guarded (audit M2)
    if (hc) {                                                          // keyed by position (language-agnostic)
      const ix = indexAmong(hc, 'a.button.course');
      pushEcom('select_item', { item_list_name: 'home_course_selector', items: [{ item_id: 'home-course-' + ix, item_name: 'Home course ' + (ix + 1), item_category: 'courses', index: ix }] });
      return;
    }
    const faq = t.closest('.faq_question, .faq-q');                    // FAQ accordion question header (live site uses Client-First .faq_question; .faq-q kept as legacy fallback)
    if (faq) { push('faq_toggle', { faq_index: indexAmong(faq, '.faq_question, .faq-q') }); return; }
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
    const wgLi = a.closest('.wg-li');                                  // the real switcher item carries the ISO code as a class token
    const wg = wgLi || a.closest(WEGLOT_SEL) || (a.matches && a.matches(WEGLOT_SEL) ? a : null);
    if (wg) {
      // to_language = ISO code ONLY (never scraped link text). Sources, in order: data-l (future-proof)
      // -> the .wg-li class token (e.g. "wg-li de wg-flags" -> "de") -> first path segment of the href.
      let to = a.getAttribute('data-l') || '';
      if (!to && wgLi) {
        const toks = wgLi.className.split(/\s+/);
        for (let i = 0; i < toks.length; i++) { if (toks[i] === 'en' || LOCALES.indexOf(toks[i]) !== -1) { to = toks[i]; break; } }
      }
      if (!to) { const wu = urlOf(a); if (wu) { const seg = (wu.pathname.split('/')[1] || '').toLowerCase(); if (seg === 'en' || LOCALES.indexOf(seg) !== -1) to = seg; } }
      push('language_select', { to_language: to || 'unknown' });
      return;
    }

    // "From Our Blog" promo (.section_blog) -> select_content (post) or cta blog_see_all  [client need a]
    if (a.closest('.section_blog')) {
      const u = urlOf(a);
      if (u && isPostPath(u.pathname)) { push('select_content', { content_type: 'blog_post', content_id: lastSeg(u), link_url: a.href, source_block: 'from_our_blog', source_page_type: PT }); return; }
      if (u && barePath(u.pathname) === '/blog') { push('cta_click', { cta_id: 'blog_see_all', link_url: a.href, cta_location: ctaLocation(a), cta_text: ctaText(a) }); return; }
      // any other .section_blog link falls through to normal classification below
    }

    // blog CATEGORY link -> category_click (first-class: "do people use categories, which?")
    // Checked BEFORE the /post/ branch so a category link never falls through as a post.
    const cu = urlOf(a);
    if (cu && isCategoryPath(cu.pathname)) {
      push('category_click', { category_slug: lastSeg(cu), link_url: a.href, source_page_type: PT });
      return;
    }

    // any blog-post link (blog list cards, related posts, category cards, in-content) -> select_content
    const au = urlOf(a);
    if (au && isPostPath(au.pathname)) {
      const sb = PT === 'blog_list' ? 'blog_list' : PT === 'blog_post' ? 'related_posts' : PT === 'category' ? 'category' : 'in_content';
      push('select_content', { content_type: 'blog_post', content_id: lastSeg(au), link_url: a.href, source_block: sb, source_page_type: PT });
      // When clicked from inside a post, this is a RELATED-POST click — emit a dedicated
      // event carrying which post we came from -> to, and the position among related cards
      // (so reports can see which related slot wins). Position = index among /post/ links in
      // the nearest related container, falling back to index among all /post/ links on page.
      if (PT === 'blog_post') {
        let pos = 0;
        const container = a.closest('.related, .related-posts, [class*="related"]') || document;
        const links = container.querySelectorAll('a[href*="/post/"]');
        for (let i = 0; i < links.length; i++) { if (links[i] === a) { pos = i; break; } }
        push('related_post_click', { from_post: PAGE_ID, to_post: lastSeg(au), position: pos, link_url: a.href });
      }
      return;
    }

    // CTA intent (apply / offers / email / phone / whatsapp / directions)
    const id = classifyHref(href, a);
    if (id) {
      // email/phone/whatsapp hrefs embed a contact identifier (CEL's own address/number);
      // GA4 redacts emails regardless + its no-PII policy bans them, so send the scheme
      // label, never the raw href. cta_id already says which channel was clicked.
      const SAFE_URL = { email: 'mailto:', phone: 'tel:', whatsapp: 'whatsapp:' };
      const params = { cta_id: id, link_url: SAFE_URL[id] || a.href, cta_location: ctaLocation(a), cta_text: ctaText(a) };
      // If this CTA lives INSIDE an offer card (the Apply Now / Contact us buttons on the
      // /offers page AND wherever promotions are embedded on other pages), enrich it with the
      // promotion so reports can tie offer -> which button -> outcome. cta_location becomes
      // 'offer_card' and select_promotion (below) fires too with the same cta_id as creative.
      const offerCard = a.closest('.offer_item');
      if (offerCard) {
        const pp = offerPromoParams(offerCard);
        params.cta_location = 'offer_card';
        params.promotion_id = pp.promotion_id;
        params.promotion_name = pp.promotion_name;
        params.creative_slot = pp.creative_slot;
        push('select_promotion', { promotion_id: pp.promotion_id, promotion_name: pp.promotion_name, creative_slot: pp.creative_slot, cta_id: id });
      }
      push('cta_click', params);
      return;
    }

    // "Unlock Offer" influencer CTA (href=#, sits in navbar) -> offers intent (is-influencer is an English class)
    if (a.classList.contains('is-influencer')) { push('cta_click', { cta_id: 'offers', link_url: a.href, cta_location: ctaLocation(a), cta_text: ctaText(a) }); return; }

    // header / footer navigation
    const loc = navLocation(a);
    if (loc) { push('navigation_click', { link_url: a.href, link_text: linkText(a), nav_location: loc }); return; }

    // in-content link catch-all (every other real link: same-origin internal OR outbound).
    // Contact CTAs are now classified as cta_click(contact) above; this captures cross-links,
    // sibling landings, partners. Skips pure in-page anchors (#...) and schemes w/o hostname.
    if (href && href.charAt(0) !== '#' && au && au.hostname) {
      if (au.hostname !== location.hostname) {
        // Outbound link -> first-class GA4 `outbound_click` (GA4 recommended `click` shape).
        // link_domain = the destination host only (never the full URL/query -> no PII leak).
        push('outbound_click', { link_domain: au.hostname, link_url: a.href, link_text: linkText(a), outbound: true });
      } else {
        push('navigation_click', { link_url: a.href, link_text: linkText(a), nav_location: 'in_content' });
      }
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
  // generate_lead stays the GA4-recommended umbrella event, but every lead now carries a
  // clear lead_type + lead_channel so reports distinguish contact vs newsletter vs sales call
  // vs booking (form_name alone was too generic). Both derive from the internal name CONSTANT
  // (never DOM/Weglot text) so they're byte-identical across all 8 locales. form_name and the
  // live GTM trigger / contact_lead Create-event rule (which key on form_name) are untouched.
  // form_name VALUES are what reach GA4 — keep them vendor-neutral ('booking', not 'fidelo_booking':
  // it's our only booking system, so the vendor name would just leak into GA4 reports). The
  // internal fidelo_* postMessage event names (from the iframe bridge) are NOT in this map and
  // never reach GA4 — they're translated to the clean events below.
  const LEAD_META = {
    contact: { type: 'contact', channel: 'web_form' },
    newsletter: { type: 'newsletter', channel: 'web_form' },
    schedule_call: { type: 'sales_call', channel: 'scheduler' },
    booking: { type: 'booking', channel: 'booking_widget' }
  };
  const leadFired = {};
  function fireLead(name, extra) {
    if (leadFired[name]) return;
    leadFired[name] = true;
    const meta = LEAD_META[name] || { type: name, channel: 'other' };
    const params = { form_name: name, lead_type: meta.type, lead_channel: meta.channel };
    if (extra) for (const k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) params[k] = extra[k];
    push('generate_lead', params);
  }
  function leadName(form) {
    const n = (form.getAttribute('data-name') || form.id || '').toLowerCase();
    if (n.indexOf('contact') !== -1) return 'contact';
    if (n.indexOf('newsletter') !== -1) return 'newsletter';
    return null;
  }
  function visible(el) { return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length)); }
  // form_start: a once-per-form engagement signal on the first focus/input inside a tracked
  // lead form. Pairs with generate_lead so reports can compute a start->submit completion rate.
  const startFired = {};
  function watchFormStart(form, name) {
    function onFirst() {
      if (startFired[name]) return;
      startFired[name] = true;
      form.removeEventListener('focusin', onFirst, true);
      form.removeEventListener('input', onFirst, true);
      push('form_start', { form_name: name });
    }
    // capture-phase + both focusin (keyboard/tab into a field) and input (typing/checkbox)
    // so the start is caught regardless of how the visitor engages first.
    form.addEventListener('focusin', onFirst, true);
    form.addEventListener('input', onFirst, true);
  }
  function watchForm(form) {
    const name = leadName(form);
    if (!name) return;
    watchFormStart(form, name);
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
    if (/(^|\.)meetings(-[a-z0-9]+)?\.hubspot\.com$/.test(oh)) {
      if (e.data && e.data.meetingBookSucceeded === true) fireLead('schedule_call');
      return;
    }
    // Fidelo booking widget: cel-fidelo.js bridge inside the cross-origin iframe.
    // Anchored origin test (rejects fidelo.com.evil.com); validate before trusting e.data.
    if (/(^|\.)fidelo\.com$/.test(oh)) {
      const d = e.data || {};
      // Booking value (GA4 ecommerce convention: 'value' + 'currency') is forwarded
      // when cel-fidelo.js confidently parsed the displayed total. Type-guarded so a
      // missing/garbled value never reaches GA4 as NaN or an empty currency.
      const money = {};
      if (typeof d.value === 'number' && isFinite(d.value) && typeof d.currency === 'string' && d.currency) {
        money.value = d.value;
        money.currency = d.currency;
      }
      // step_total is a positive integer (count of nav steps) — future-proofs a variable denominator.
      const stepTotal = (typeof d.step_total === 'number' && isFinite(d.step_total) && d.step_total > 0) ? d.step_total : undefined;
      if (d.event === 'fidelo_widget_open') {
        // Clean "opened the booking widget" denominator (distinct from apply_click + step=1).
        const params = { form_name: 'booking' };
        if (stepTotal !== undefined) params.step_total = stepTotal;
        push('widget_open', params);
      } else if (d.event === 'fidelo_booking_abandon' && d.step_name) {
        // Explicit drop-off: the last step reached before leaving without completing.
        const params = { step: d.step, step_name: d.step_name, form_name: 'booking' };
        push('booking_abandon', params);
      } else if (d.event === 'fidelo_booking_step' && d.step_name) {
        const params = { step: d.step, step_name: d.step_name, form_name: 'booking' };
        if (money.value !== undefined) { params.value = money.value; params.currency = money.currency; }
        if (stepTotal !== undefined) params.step_total = stepTotal;
        // step_direction (forward|back) lets reports strip back-nav from forward-funnel counts.
        if (d.step_direction === 'forward' || d.step_direction === 'back') params.step_direction = d.step_direction;
        // step_duration_ms = time spent on the step just left (non-negative finite ms).
        if (typeof d.step_duration_ms === 'number' && isFinite(d.step_duration_ms) && d.step_duration_ms >= 0) params.step_duration_ms = d.step_duration_ms;
        // selections is an ARRAY in the bridge message; GA4 params reject arrays, so join to a
        // capped delimited string. Only strings are kept (defensive against a malformed payload).
        if (Array.isArray(d.selections) && d.selections.length) {
          const sel = d.selections.filter(function (x) { return typeof x === 'string' && x; }).join(' | ').slice(0, 200);
          if (sel) params.selections = sel;
        }
        push('booking_step', params);
      } else if (d.event === 'fidelo_application_submitted') {
        // Completion: carry booking value/currency (now sourced from the authoritative
        // PostAffiliatePro checkout total in cel-fidelo.js) + the Fidelo order/booking id
        // as transaction_id (GA4 de-dupes conversions on it + ties the lead to the record).
        const extra = money.value !== undefined ? { value: money.value, currency: money.currency } : {};
        if (typeof d.transaction_id === 'string' && d.transaction_id) extra.transaction_id = d.transaction_id;
        fireLead('booking', Object.keys(extra).length ? extra : null);
      }
    }
  });

  // ---- passive: scroll depth (25/50/75/90, once each, short-page guarded) ----
  const THRESH = [25, 50, 75, 90];
  const hit = {};
  let ticking = false;

  // ---- active read-time ticker (site-wide) — counts only while the tab is visible, so
  //   background tabs don't inflate engagement. Shared by engaged_page (any page) AND the
  //   post_read/_complete blog timers below. ----
  let readMs = 0, lastTick = 0, readCounting = false;
  function tickStart() { if (!readCounting && document.visibilityState === 'visible') { readCounting = true; lastTick = Date.now(); } }
  function tickStop() { if (readCounting) { readMs += Date.now() - lastTick; readCounting = false; } }
  function activeMs() { if (readCounting) { readMs += Date.now() - lastTick; lastTick = Date.now(); } return readMs; }
  tickStart();
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') tickStart(); else tickStop(); });

  // ---- engaged_page: ONE genuine-engagement signal per page, page_type + language aware
  //   (unlike GA4's built-in engaged-session, this knows WHICH page type + locale and is
  //   comparable across pages). Fires once on whichever comes first: 15s of ACTIVE time
  //   (tab visible) OR 50% scroll. trigger = dwell_15s | scroll_50. Generic — works on every
  //   page. The dwell path gates on activeMs() (NOT wall-clock), so a never-focused/background
  //   tab does NOT count as engaged; a poll re-checks so a tab that becomes active later still
  //   fires once it accrues 15s of real attention. ----
  let engagedFired = false, engagedTimer = 0;
  function fireEngaged(trigger) {
    if (engagedFired) return;
    engagedFired = true;
    if (engagedTimer) { window.clearInterval(engagedTimer); engagedTimer = 0; }
    push('engaged_page', { trigger: trigger, engaged_seconds: Math.round(activeMs() / 1000) });
  }
  // Poll active time every 3s; fire only once it crosses 15s of visible attention.
  engagedTimer = window.setInterval(function () {
    if (activeMs() >= 15000) fireEngaged('dwell_15s');
  }, 3000);
  // ---- blog engagement: read vs bounce, per-post scroll, read-time, blog-list scroll ----
  // page_locale rides every event automatically, so this is per-language with no extra work.
  // category for posts/lists, so reports can group reads by topic. Two hard rules:
  //   (1) NEVER el.textContent — Weglot translates the visible category label (the .blog_category
  //       div reads "English" / "Englisch" / …), fragmenting one topic into 8 strings.
  //   (2) NEVER a bare [data-category] selector — on this site that attribute is used by the
  //       cookie-consent scripts (data-category="functional"/"marketing"), NOT the blog.
  // So: prefer the structural /category/<slug> link segment (a real category nav link), then a
  // data-category attribute ONLY if it sits inside a blog container (.blog_category / .categories_*).
  // Computed lazily and ONLY on post/list pages (no full-DOM scan on home/courses/etc.).
  // Note: Weglot also translates the /category/ slug per locale, so blog_category is a
  // per-locale-stable token (join across locales via post_slug, which IS invariant).
  const isPost = PT === 'blog_post';
  const isList = PT === 'blog_list' || PT === 'category';
  const blogCat = (isPost || isList) ? (function () {
    const links = document.querySelectorAll('a[href]');
    for (let i = 0; i < links.length; i++) {
      const u = urlOf(links[i]);
      if (u && isCategoryPath(u.pathname)) return lastSeg(u).slice(0, 60);
    }
    const scoped = document.querySelector('.blog_category [data-category], .categories_collection [data-category]');
    const ds = scoped && scoped.getAttribute('data-category');
    return ds ? ds.trim().slice(0, 60) : '';
  })() : '';
  function postParams(extra) {
    const o = { post_slug: PAGE_ID, blog_category: blogCat };
    if (extra) for (const k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) o[k] = extra[k];
    return o;
  }
  // Active read-time uses the site-wide ticker (tickStart/tickStop/activeMs) declared above.
  // Same milestones as the site-wide scroll_depth (THRESH) so percent_scrolled has ONE
  // value-space across scroll_depth / post_scroll_depth / blog_list_scroll — a cross-event
  // report on percent_scrolled isn't ambiguous at the top bucket. 90 (not 100) matches GA4's
  // native Enhanced-Measurement scroll milestone; 100 rarely fires on pages with footers.
  const POST_THRESH = [25, 50, 75, 90];
  const postHit = {};
  let readFired = false, readCompleteFired = false;
  if (isPost) {
    // post_read = a GENUINE read: 30s of active time on the post (fires once, dwell path).
    window.setTimeout(function () {
      if (!readFired && activeMs() >= 30000) { readFired = true; push('post_read', postParams({ trigger: 'dwell_30s' })); }
    }, 30000);
  }
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
      // engaged_page (scroll path): 50% scrolled = genuine engagement, any page (once).
      if (!engagedFired && pct >= 50) fireEngaged('scroll_50');
      // blog HOMEPAGE / category list scroll (25/50/75/100) — "do they scroll the list?"
      if (isList) {
        for (let k = 0; k < POST_THRESH.length; k++) {
          if (pct >= POST_THRESH[k] && !postHit['l' + POST_THRESH[k]]) {
            postHit['l' + POST_THRESH[k]] = true;
            push('blog_list_scroll', { percent_scrolled: POST_THRESH[k], list_type: PT });
          }
        }
      }
      if (isPost) {
        // per-post scroll depth (carries the post slug, unlike generic scroll_depth)
        for (let k = 0; k < POST_THRESH.length; k++) {
          if (pct >= POST_THRESH[k] && !postHit[POST_THRESH[k]]) {
            postHit[POST_THRESH[k]] = true;
            push('post_scroll_depth', postParams({ percent_scrolled: POST_THRESH[k] }));
          }
        }
        // post_read via the scroll path: 50% scrolled = a genuine read (fires once).
        if (!readFired && pct >= 50) { readFired = true; push('post_read', postParams({ trigger: 'scroll_50' })); }
        // post_read_complete: reached the end (~90%), with active read-time in seconds.
        if (!readCompleteFired && pct >= 90) {
          readCompleteFired = true;
          push('post_read_complete', postParams({ read_seconds: Math.round(activeMs() / 1000) }));
        }
      }
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });

  // ---- HTML5 <video> engagement (GA4 recommended video_start/_progress/_complete) ----
  // Attaches ONLY to native <video> elements present at load. YouTube/Vimeo are <iframe>
  // embeds (NOT matched here) — those are handled at the GTM layer (GTM's built-in YouTube
  // trigger), per the GTM setup doc. So this block is fully inert on embed-only pages.
  // video_title prefers a labelling attribute (never reads arbitrary page text); video_percent
  // marks the 25/50/75/100 milestones once each per element.
  (function () {
    const videos = document.querySelectorAll('video');
    if (!videos.length) return;
    const MILE = [25, 50, 75];
    function titleOf(v) {
      const t = v.getAttribute('title') || v.getAttribute('aria-label') || v.getAttribute('data-video-title') || '';
      return (t.replace(/\s+/g, ' ').trim().slice(0, 80)) || '(untitled)';
    }
    for (let i = 0; i < videos.length; i++) {
      (function (v) {
        const seen = {};
        let started = false;
        v.addEventListener('play', function () {
          if (started) return;
          started = true;
          push('video_start', { video_title: titleOf(v), video_provider: 'html5', video_percent: 0 });
        });
        v.addEventListener('timeupdate', function () {
          const dur = v.duration;
          if (!isFinite(dur) || dur <= 0) return;
          const pct = (v.currentTime / dur) * 100;
          for (let k = 0; k < MILE.length; k++) {
            if (pct >= MILE[k] && !seen[MILE[k]]) {
              seen[MILE[k]] = true;
              push('video_progress', { video_title: titleOf(v), video_provider: 'html5', video_percent: MILE[k] });
            }
          }
        });
        v.addEventListener('ended', function () {
          if (seen[100]) return;
          seen[100] = true;
          push('video_complete', { video_title: titleOf(v), video_provider: 'html5', video_percent: 100 });
        });
      })(videos[i]);
    }
  })();

  // ---- site search (GA4 recommended `search` with search_term) ----
  // Conservative, structural detection: a real search input is type=search OR sits inside a
  // [role="search"] form. NEVER matches generic lead/newsletter inputs, so this is inert on
  // pages without a search box. search_term is the visitor's query (a search box is a query
  // surface by design, not PII); capped + only emitted on a non-empty submit.
  (function () {
    function searchInput(form) {
      return form.querySelector('input[type="search"]') ||
        (form.getAttribute('role') === 'search' ? form.querySelector('input[type="text"], input:not([type])') : null);
    }
    // Collect candidate forms: role="search" forms + any form wrapping a type=search input.
    // Built by hand (no :has() — unsupported in older engines + a bad selector throws in
    // querySelectorAll). De-duplicated so a form isn't double-bound.
    const set = [];
    function add(f) { if (f && set.indexOf(f) === -1) set.push(f); }
    const roleForms = document.querySelectorAll('form[role="search"]');
    for (let i = 0; i < roleForms.length; i++) add(roleForms[i]);
    const inputs = document.querySelectorAll('input[type="search"]');
    for (let i = 0; i < inputs.length; i++) add(inputs[i].form || inputs[i].closest('form'));
    const list = set;
    for (let i = 0; i < list.length; i++) {
      (function (form) {
        form.addEventListener('submit', function () {
          let term = '';
          try { const inp = searchInput(form); term = inp && inp.value ? String(inp.value).replace(/\s+/g, ' ').trim() : ''; } catch (_) { return; }
          if (term) push('search', { search_term: term.slice(0, 100) });
        });
      })(list[i]);
    }
  })();

  // ---- offers engagement (GA4-standard view_promotion / select_promotion + offer_code_copy)
  //   Fully inert unless the page actually has offer cards (.offer_item).
  //   promotion_id is LANGUAGE-INVARIANT (Weglot doesn't translate it): a data-offer-id attr if
  //   present, else the offer image's Webflow CMS asset-id (the 24-hex prefix of the image
  //   filename — stable across all 8 locales), else a positional fallback. promotion_name is the
  //   .offer-bento_title text and IS locale-specific by nature (use promotion_id to join across
  //   languages). creative_slot = position. The offers list is GEO-FILTERED after load
  //   (cel-offers.js removes/hides cards by visitor country), so view_promotion fires ONLY for
  //   cards actually visible at fire time — never the hidden ones. ----
  (function () {
    const cards = document.querySelectorAll('.offer_item');
    if (!cards.length) return;
    function isVisible(el) {
      if (!el || el.offsetParent === null) return false;  // display:none / removed
      const r = el.getBoundingClientRect();
      return !!(r.width || r.height);
    }
    // Uses the SHARED offer helpers (offerPromoParams/offerCardId/offerCardName) declared near
    // cardItem — same identity the click handler's offer-CTA enrichment uses, so a card's
    // view_promotion / select_promotion / cta_click all carry the SAME promotion_id.
    // Index every card up front so offer_code_copy can always resolve a slot.
    for (let i = 0; i < cards.length; i++) cards[i].setAttribute('data-cel-offer-i', i);
    // view_promotion — once per card, only when the card is actually visible (post geo-filter)
    const seen = {};
    function fireView(card, i) {
      if (seen[i] || !isVisible(card)) return;
      seen[i] = true;
      push('view_promotion', offerPromoParams(card));
    }
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { const i = +e.target.getAttribute('data-cel-offer-i'); fireView(e.target, i); io.unobserve(e.target); }
        });
      }, { threshold: 0.5 });
      for (let i = 0; i < cards.length; i++) io.observe(cards[i]);
    } else {
      // No IO: defer past cel-offers.js's async geo-filter so we don't count cards it's
      // about to remove/hide for this visitor's country (isVisible re-checks at fire time).
      window.setTimeout(function () {
        for (let i = 0; i < cards.length; i++) fireView(cards[i], i);
      }, 2000);
    }
    // select_promotion — a click on the card that is NOT on a classified CTA button. The
    // Apply Now / Contact us buttons (-> /booking, /contact-cel) are handled by the main click
    // handler, which fires a RICHER select_promotion carrying cta_id (which button) + the
    // cta_click. Skipping them here avoids a double select_promotion for the same click.
    for (let i = 0; i < cards.length; i++) {
      (function (card) {
        card.addEventListener('click', function (ev) {
          const a = ev.target && ev.target.closest && ev.target.closest('a[href]');
          if (a && card.contains(a) && classifyHref((a.getAttribute('href') || ''), a)) return;  // CTA button -> handled upstream
          push('select_promotion', offerPromoParams(card));
        }, { passive: true });
      })(cards[i]);
    }
    // offer_code_copy — when a promo code is copied. Scoped to the code element / an explicit
    //   data-offer-code (NOT a broad [class*="copy"], which would match footer_copyright etc.).
    function nearestPromo(el) {
      const card = el.closest && el.closest('.offer_item');
      return card ? offerPromoParams(card) : {};
    }
    const codeEls = document.querySelectorAll('.page_code_base, [data-offer-code]');
    for (let i = 0; i < codeEls.length; i++) {
      (function (el) {
        el.addEventListener('copy', function () { push('offer_code_copy', nearestPromo(el)); }, { passive: true });
        el.addEventListener('click', function () {
          if (el.hasAttribute('data-offer-code')) push('offer_code_copy', nearestPromo(el));
        }, { passive: true });
      })(codeEls[i]);
    }
  })();
})();
