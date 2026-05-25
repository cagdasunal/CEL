/*!
 * cel-post.js — CEL Blog Post Template (/post/*)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-post.js
 * Mirrored to:     docs/scripts/cel-post.{js,min.js}
 * Public URL:      https://cel.englishcollege.com/scripts/cel-post.min.js
 *
 * Webflow integration:
 *   Page Settings → Custom Code → Before </body>:
 *     <script src="https://cel.englishcollege.com/scripts/cel-post.min.js" defer></script>
 *
 * Bundle contents:
 *   1. Finsweet Attributes v2 (self-hosted) — fs-toc
 *   2. Finsweet a11y v1 (self-hosted)
 *   3. Finsweet modal v1 (self-hosted)
 *   4. TOC class cleanup (remove .toc_link.w--current)
 *   5. Modal binding (translated aria-label)
 *   6. TOC builder + scrollspy
 *   7. Post date localization
 *   8. Posts filter by language (Weglot-aware)
 *   9. Category links builder (Weglot-aware)
 *
 * NOT in this bundle (stay in Webflow HEAD because they use CMS template
 * tokens `{{wf {...} }}` that only resolve in Webflow-rendered HTML):
 *   - Canonical/redirect/hreflang cleanup script
 *   - JSON-LD BlogPosting + BreadcrumbList schema
 *
 * Replaces inline Embed components (safe to delete from Blog Posts Template):
 *   - FAQ-section <div class="faq_embed w-embed w-script"> that contains
 *     the Finsweet a11y loader pointing at cdn.jsdelivr.net — IIFE #2 below
 *     does the same job from your own origin, with an idempotency guard
 *     so a leftover Embed wouldn't double-execute anyway.
 *
 * Loaded with `defer` in footer → DOM is parsed when this runs.
 */

/* 1. Finsweet Attributes v2 (self-hosted) — fs-toc mode
 *    Source: cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/
 *    Idempotent via window.__fsR (also short-circuits if Finsweet's own
 *    runtime has already set window.fsAttributes from a prior load).
 */
(function () {
  if (window.__fsR || window.fsAttributes) return;
  window.__fsR = 1;
  const s = document.createElement('script');
  s.type = 'module';
  s.async = true;
  s.crossOrigin = 'anonymous';
  s.src = 'https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';
  s.setAttribute('fs-toc', '');
  document.head.appendChild(s);
})();

/* 2. Finsweet a11y v1 (self-hosted) — FAQ accessibility behaviors
 *    Source: cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js
 *    Idempotent via window.__celA11y (safe even if an old FAQ Embed pointing
 *    at the same vendor is still in the DOM during the cleanup window).
 */
(function () {
  if (window.__celA11y) return;
  window.__celA11y = 1;
  const s = document.createElement('script');
  s.async = true;
  s.crossOrigin = 'anonymous';
  s.src = 'https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';
  document.head.appendChild(s);
})();

/* 3. Finsweet modal v1 (self-hosted)
 *    Source: cel.englishcollege.com/scripts/vendor/@finsweet/attributes-modal@1/modal.js
 *    Idempotent via window.__celModal.
 */
(function () {
  if (window.__celModal) return;
  window.__celModal = 1;
  const s = document.createElement('script');
  s.async = true;
  s.crossOrigin = 'anonymous';
  s.src = 'https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-modal@1/modal.js';
  document.head.appendChild(s);
})();

/* 4. TOC class cleanup — remove Webflow's auto-added w--current class */
(function () {
  function init() {
    function cleanTOC() {
      document.querySelectorAll('.toc_link.w--current').forEach(function (el) {
        el.classList.remove('w--current');
      });
    }
    cleanTOC();
    window.addEventListener('hashchange', cleanTOC);
    window.addEventListener('scroll', cleanTOC, { passive: true });
  }
  if (window.Webflow && typeof window.Webflow.push === 'function') {
    window.Webflow.push(init);
  } else {
    init();
  }
})();

/* 5. Modal binding — translated aria-label, role/dialog wiring */
(function () {
  window.Webflow = window.Webflow || [];
  window.Webflow.push(function () {
    const CLOSE_LABELS = {
      en: 'Close modal', it: 'Chiudi finestra', de: 'Fenster schließen',
      fr: 'Fermer la fenêtre', ko: '모달 닫기',
      es: 'Cerrar ventana', pt: 'Fechar janela',
      ar: 'إغلاق النافذة', ja: 'ウィンドウを閉じる'
    };
    const lang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0];
    const closeLabel = CLOSE_LABELS[lang] || CLOSE_LABELS.en;

    document.querySelectorAll('.modal_popup').forEach(function (popup, i) {
      if (!popup.hasAttribute('fs-modal-element')) popup.setAttribute('fs-modal-element', 'modal');
      if (!popup.hasAttribute('fs-modal-id')) popup.setAttribute('fs-modal-id', 'cel-modal-' + (i + 1));
      if (!popup.hasAttribute('role')) popup.setAttribute('role', 'dialog');
      if (!popup.hasAttribute('aria-modal')) popup.setAttribute('aria-modal', 'true');

      const closeEl = popup.querySelector('.modal_close');
      if (closeEl) {
        closeEl.setAttribute('fs-modal-element', 'close');
        if (!closeEl.hasAttribute('role')) closeEl.setAttribute('role', 'button');
        if (!closeEl.hasAttribute('tabindex')) closeEl.setAttribute('tabindex', '0');
        if (!closeEl.hasAttribute('aria-label')) closeEl.setAttribute('aria-label', closeLabel);
      }
    });
  });
})();

/* 6. TOC builder + scrollspy */
(function () {
  const TOC_LABELS = {
    en: 'Table of contents', it: 'Indice', de: 'Inhaltsverzeichnis',
    fr: 'Table des matières', ko: '목차',
    es: 'Tabla de contenidos', pt: 'Índice',
    ar: 'جدول المحتويات', ja: '目次'
  };

  function init() {
    const richText = document.querySelector('.blog_rich-text');
    if (!richText) return;

    const headings = Array.from(richText.querySelectorAll('h2')).filter(function (h) {
      return h.textContent.trim().length > 0;
    });
    if (!headings.length) return;

    const lang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0];
    const tocLabel = TOC_LABELS[lang] || TOC_LABELS.en;

    let tocList = document.querySelector('.toc_component .toc_list') || document.querySelector('.toc_list');
    if (!tocList) {
      const tocWrapper = document.createElement('nav');
      tocWrapper.className = 'toc_component';
      tocWrapper.setAttribute('aria-label', tocLabel);

      tocList = document.createElement('ul');
      tocList.className = 'toc_list';

      tocWrapper.appendChild(tocList);
      richText.parentNode.insertBefore(tocWrapper, richText);
    } else {
      tocList.innerHTML = '';
      const tocComponent = tocList.closest('.toc_component');
      if (tocComponent && !tocComponent.hasAttribute('aria-label')) {
        tocComponent.setAttribute('aria-label', tocLabel);
      }
    }

    const usedIds = new Set(Array.from(document.querySelectorAll('[id]')).map(function (el) { return el.id; }));

    function slugify(str) {
      const basic = str
        .toLowerCase()
        .replace(/ı/g, 'i').replace(/İ/g, 'i')
        .normalize('NFD').replace(/[̀-ͯ]/g, '')
        .replace(/&/g, 'and')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .replace(/-{2,}/g, '-');
      return basic || 'section';
    }

    function uniqueId(base, el) {
      let id = base;
      let n = 2;
      while (usedIds.has(id)) {
        if (document.getElementById(id) === el) break;
        id = base + '-' + n;
        n++;
      }
      usedIds.add(id);
      return id;
    }

    const linkMap = new Map();

    headings.forEach(function (h) {
      const base = h.id ? h.id : slugify(h.textContent.trim());
      const finalId = uniqueId(base, h);
      if (!h.id || h.id !== finalId) h.id = finalId;
      if (!h.hasAttribute('tabindex')) h.setAttribute('tabindex', '-1');

      const li = document.createElement('li');
      li.className = 'toc_item';

      const a = document.createElement('a');
      a.className = 'toc_link';
      a.href = '#' + finalId;
      a.textContent = h.textContent.trim();

      li.appendChild(a);
      tocList.appendChild(li);

      linkMap.set(h, a);
    });

    function setActive(link) {
      document.querySelectorAll('.toc_link.is-active').forEach(function (el) {
        el.classList.remove('is-active');
      });
      if (link) link.classList.add('is-active');
    }

    function getActiveHeading() {
      const offset = 146;
      let active = headings[0];
      for (let i = 0; i < headings.length; i++) {
        if (headings[i].getBoundingClientRect().top - offset <= 0) {
          active = headings[i];
        } else {
          break;
        }
      }
      return active;
    }

    function onScroll() {
      setActive(linkMap.get(getActiveHeading()));
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    onScroll();
  }

  if (window.Webflow && typeof window.Webflow.push === 'function') {
    window.Webflow.push(init);
  } else {
    init();
  }
})();

/* 7. Post date localization */
(function () {
  function init() {
    const lang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase();
    const node = document.querySelector('.post_date');
    if (!node) return;
    const text = node.textContent.trim();
    const parts = text.match(/^([A-Za-z]+) (\d{1,2}), (\d{4})$/);
    if (!parts) return;
    const monthEn = parts[1], day = parts[2], year = parts[3];
    const months = {
      en: ["January","February","March","April","May","June","July","August","September","October","November","December"],
      de: ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],
      fr: ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"],
      ko: ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"],
      it: ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"],
      es: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
      pt: ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"],
      ar: ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"],
      ja: ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
    };
    const monthIndex = months.en.findIndex(function (m) { return m.toLowerCase() === monthEn.toLowerCase(); });
    if (monthIndex === -1) return;
    let monthLocalized = monthEn;
    if (lang.startsWith('de')) monthLocalized = months.de[monthIndex];
    else if (lang.startsWith('fr')) monthLocalized = months.fr[monthIndex];
    else if (lang.startsWith('ko')) monthLocalized = months.ko[monthIndex];
    else if (lang.startsWith('it')) monthLocalized = months.it[monthIndex];
    else if (lang.startsWith('es')) monthLocalized = months.es[monthIndex];
    else if (lang.startsWith('pt')) monthLocalized = months.pt[monthIndex];
    else if (lang.startsWith('ar')) monthLocalized = months.ar[monthIndex];
    else if (lang.startsWith('ja')) monthLocalized = months.ja[monthIndex];
    if (lang.startsWith('ko')) {
      node.textContent = year + '년 ' + monthLocalized + ' ' + day + '일';
    } else if (lang.startsWith('ja')) {
      node.textContent = year + '年 ' + monthLocalized + ' ' + day + '日';
    } else {
      node.textContent = day + ' ' + monthLocalized + ' ' + year;
    }
  }
  if (window.Webflow && typeof window.Webflow.push === 'function') {
    window.Webflow.push(init);
  } else {
    init();
  }
})();

/* 8. Posts filter by language (Weglot-aware, fail-safe) */
(function () {
  window.Webflow = window.Webflow || [];
  window.Webflow.push(function () {
    function filterPostsByLang() {
      let currentLang = '';
      if (window.Weglot && typeof window.Weglot.getCurrentLang === 'function') {
        currentLang = window.Weglot.getCurrentLang();
      }
      if (!currentLang) {
        currentLang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0];
      }
      document.querySelectorAll('.w-dyn-item[data-lang]').forEach(function (item) {
        item.style.display = (item.getAttribute('data-lang') === currentLang) ? '' : 'none';
      });
    }
    filterPostsByLang();
    if (window.Weglot && typeof window.Weglot.on === 'function') {
      window.Weglot.on('languageChanged', filterPostsByLang);
    }
  });
})();

/* 9. Category links builder (Weglot-aware; no lang-prefix for post template) */
(function () {
  if (window.self !== window.top) return;

  const normalizeLang = function (val) {
    return (val || "").toLowerCase().split(/[-_]/)[0].trim();
  };

  const getActiveLang = function () {
    let l = "";
    if (window.Weglot) {
      if (typeof window.Weglot.getCurrentLang === "function") l = window.Weglot.getCurrentLang();
      else if (typeof window.Weglot.getCurrentLanguage === "function") l = window.Weglot.getCurrentLanguage();
    }
    l = normalizeLang(l);
    return l ? l : normalizeLang(document.documentElement.getAttribute("lang"));
  };

  const buildCategoryLinks = function () {
    try {
      const activeLang = getActiveLang();
      const validCategories = [];
      const sourceItems = document.querySelectorAll(".categories_collection .w-dyn-item");

      sourceItems.forEach(function (item) {
        const rawLang = item.getAttribute("data-lang");
        if (rawLang) {
          const nodeLang = normalizeLang(rawLang);
          if (nodeLang !== activeLang) {
            item.remove();
          } else {
            const linkEl = item.querySelector('a[data-blog-slot="url"]');
            if (linkEl) {
              validCategories.push({
                url: linkEl.getAttribute("href") || "#",
                text: linkEl.textContent.trim()
              });
            }
          }
        }
      });

      const parentContainers = document.querySelectorAll('.blog_links');
      parentContainers.forEach(function (parent) {
        const dynamicLinks = parent.querySelectorAll('.blog_link[data-dynamic-link="true"]');
        dynamicLinks.forEach(function (link) { link.remove(); });

        validCategories.forEach(function (catData) {
          const newLink = document.createElement('a');
          newLink.className = 'blog_link';
          newLink.setAttribute('data-blog-slot', 'url');
          newLink.setAttribute('data-dynamic-link', 'true');
          newLink.setAttribute('href', catData.url);
          newLink.textContent = catData.text;
          parent.appendChild(newLink);
        });
      });

      // No IX2 re-init: ix2.init() on the just-mutated category DOM throws inside Webflow's engine ("Cannot read properties of undefined (reading 'length')") and never completes; the category links work without it.
    } catch (error) {
      console.warn('category-render failed:', error);
    }
  };

  buildCategoryLinks();
  if (window.Weglot) {
    Weglot.on("initialized", buildCategoryLinks);
    Weglot.on("languageChanged", function () { window.location.reload(); });
  } else {
    document.addEventListener("weglotInit", buildCategoryLinks);
  }
})();
