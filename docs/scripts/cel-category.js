/*!
 * cel-category.js — CEL Blog Category Page (/category/*)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-category.js
 * Mirrored to:     docs/scripts/cel-category.{js,min.js}
 * Public URL:      https://cel.englishcollege.com/scripts/cel-category.min.js
 *
 * Webflow integration:
 *   Page Settings → Custom Code → Before </body>:
 *     <script src="https://cel.englishcollege.com/scripts/cel-category.min.js" defer></script>
 *
 * Bundle contents:
 *   1. Finsweet Attributes v2 (self-hosted) — fs-toc
 *   2. Finsweet a11y v1 (self-hosted)
 *   3. Finsweet modal v1 (self-hosted)
 *   4. Heading word spans (XSS-safe, idempotent)
 *   5. Modal binding (translated aria-label, 5 langs)
 *   6. Category links builder (Weglot-aware)
 *
 * NOT in this bundle (stays in Webflow HEAD because it uses CMS template tokens):
 *   - Canonical/redirect/hreflang normalization script
 *
 * Loaded with `defer` in footer → DOM is parsed when this runs.
 */

/* 1. Finsweet Attributes v2 — fs-toc mode */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-toc','');document.head.appendChild(s)})();

/* 2. Finsweet a11y v1 */
(function(){if(window.__celA11y)return;window.__celA11y=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';document.head.appendChild(s)})();

/* 3. Finsweet modal v1 */
(function(){if(window.__celModal)return;window.__celModal=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-modal@1/modal.js';document.head.appendChild(s)})();

/* 4. Heading word spans (XSS-safe via textContent, idempotency guard) */
(function () {
  const headings = document.querySelectorAll('[data-span="true"]');
  for (let i = 0; i < headings.length; i++) {
    const heading = headings[i];
    if (heading.querySelector('.heading_span')) continue;
    const text = heading.textContent.trim();
    if (!text) continue;

    const outerSpan = document.createElement('span');
    outerSpan.className = 'heading_span';

    const words = text.split(/\s+/);
    for (let j = 0; j < words.length; j++) {
      const wordSpan = document.createElement('span');
      wordSpan.className = 'word_span';
      wordSpan.textContent = words[j];
      outerSpan.appendChild(wordSpan);
    }

    heading.textContent = '';
    heading.appendChild(outerSpan);
  }
})();

/* 5. Modal binding — translated aria-label, role/dialog wiring */
(function () {
  window.Webflow = window.Webflow || [];
  window.Webflow.push(function () {
    const CLOSE_LABELS = {
      en: 'Close modal',
      it: 'Chiudi finestra',
      de: 'Fenster schließen',
      fr: 'Fermer la fenêtre',
      ko: '모달 닫기'
    };
    const lang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase().split('-')[0];
    const closeLabel = CLOSE_LABELS[lang] || CLOSE_LABELS.en;

    const popups = document.querySelectorAll('.modal_popup');
    popups.forEach(function (popup, i) {
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

/* 6. Category links builder (Weglot-aware, reload on languageChanged) */
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

      if (window.Webflow && window.Webflow.require) {
        const ix2 = window.Webflow.require('ix2');
        if (ix2) {
          ix2.init();
          document.dispatchEvent(new CustomEvent('IX2_AFTER_SETUP'));
        }
      }
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
