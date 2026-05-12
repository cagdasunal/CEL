/*!
 * cel-blog.js — CEL Blog Listing Page (/blog)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-blog.js
 * Mirrored to:     docs/scripts/cel-blog.{js,min.js}
 * Public URL:      https://cel.englishcollege.com/scripts/cel-blog.min.js
 *
 * Webflow integration:
 *   Page Settings → Custom Code → Before </body>:
 *     <script src="https://cel.englishcollege.com/scripts/cel-blog.min.js" defer></script>
 *
 * Bundle contents:
 *   1. Finsweet Attributes v2 (self-hosted) — fs-list
 *   2. Finsweet a11y v1 (self-hosted)
 *   3. Swiper v11 (self-hosted)
 *   4. data-lang cleaner
 *   5. "Continue reading" Weglot translation
 *   6. Blog post pre-fill (synchronous, for SEO render-pass safety)
 *   7. Heading word spans (with MutationObserver, 5s auto-disconnect)
 *   8. Blog post renderer (Weglot-aware)
 *   9. Blog category links (Weglot-aware)
 *
 * Loaded with `defer` in footer → DOM is parsed when this runs, so all
 * IIFEs operate directly on the live tree (no DOMContentLoaded waits).
 */

/* 1. Finsweet Attributes v2 — fs-list mode */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-list','');document.head.appendChild(s)})();

/* 2. Finsweet a11y v1 */
(function(){if(window.__celA11y)return;window.__celA11y=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';document.head.appendChild(s)})();

/* 3. Swiper v11 — CSS + JS */
(function(){if(window.__swR)return;window.__swR=1;const l=document.createElement('link');l.rel='stylesheet';l.href='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.css';document.head.appendChild(l);const s=document.createElement('script');s.src='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.js';s.onload=function(){document.dispatchEvent(new Event('swiperReady'))};document.head.appendChild(s)})();

/* 4. data-lang cleaner — remove [data-lang] elements that don't match current language */
(function () {
  const currentLang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase();
  const els = document.querySelectorAll('[data-lang]');
  for (let i = 0; i < els.length; i++) {
    const el = els[i];
    const raw = el.getAttribute('data-lang') || '';
    const langs = raw.toLowerCase().split(/[,\s]+/).map(function (l) { return l.trim(); }).filter(Boolean);
    if (!langs.includes(currentLang)) { el.remove(); }
  }
})();

/* 5. "Continue reading" Weglot translation */
(function () {
  const path = window.location.pathname.replace(/\/+$/, '');
  if (!/^\/(?:[a-z]{2}\/)?blog$/.test(path)) return;
  const TRANSLATIONS = { en:'Continue reading', de:'Weiterlesen', fr:'Lire la suite', it:'Continua a leggere', ko:'계속 읽기' };
  function applyTranslation() {
    const lang = (document.documentElement.getAttribute('lang') || '').toLowerCase();
    const label = TRANSLATIONS[lang]; if (!label) return;
    document.querySelectorAll('a.navbar_button.is-secondary.is-full').forEach(function (button) {
      button.textContent = label;
    });
  }
  if (window.Weglot && typeof window.Weglot.on === 'function') {
    if (window.Weglot.initialized) { applyTranslation(); }
    else { window.Weglot.on('initialized', applyTranslation); }
    window.Weglot.on('languageChanged', applyTranslation);
  } else { setTimeout(applyTranslation, 1500); }
})();

/* 6. Blog post pre-fill — synchronous SEO render-pass safety */
(function () {
  if (window.self !== window.top) return;
  if (window.__blogPrefillDone) return;

  function normalizeLang(val) {
    return (val || "").toLowerCase().split(/[-_]/)[0].trim();
  }

  const lang = normalizeLang(document.documentElement.getAttribute('lang') || 'en');

  const STORY_CATEGORIES = [
    "stories-ko", "temoignages-detudiants", "kundenberichte",
    "stories", "esperienze-studenti"
  ];

  const SINGLE_TARGETS = [
    { selector: '.post_featured[post-type="featured"]', allowed: STORY_CATEGORIES },
    { selector: '[post-type="featured_category1"]', allowed: ["usa-canada-ko","usa-canada-fr","usa-canada","usa-kanada-de","stati-uniti-canada"] },
    { selector: '[post-type="featured_category2"]', allowed: ["study-abroad-ko","sejour-linguistique-a-letranger","sprachaufenthalt","study-abroad","studiare-estero"] },
    { selector: '[post-type="featured_category3"]', allowed: ["local-life-ko","vie-locale","lokales-leben","local-life","vita-locale"] },
    { selector: '[post-type="featured_category4"]', allowed: ["career-growth-ko","carriere-developpement-personnel","karriere","career-growth","carriera-opportunita"] },
    { selector: '[post-type="featured_category5"]', allowed: STORY_CATEGORIES },
    { selector: '[post-type="featured_category6"]', allowed: STORY_CATEGORIES }
  ];

  function prefixUrl(href) {
    if (!href || lang === 'en') return href;
    if (/^\/(post|category)\//.test(href) && !new RegExp('^/' + lang + '/').test(href)) {
      return '/' + lang + href;
    }
    return href;
  }

  const sourceItems = Array.from(
    document.querySelectorAll('.posts_collection .w-dyn-item')
  ).filter(function (item) {
    const l = item.getAttribute('data-lang');
    return l && normalizeLang(l) === lang;
  });

  if (!sourceItems.length) return;

  const usedItems = new Set();

  function fillTarget(target, source) {
    ['title', 'paragraph', 'category'].forEach(function (slot) {
      const srcEl = source.querySelector('[data-blog-slot="' + slot + '"]');
      if (!srcEl) return;
      const text = (srcEl.textContent || '').trim();
      target.querySelectorAll('[data-blog-slot="' + slot + '"]').forEach(function (dst) {
        dst.textContent = text;
      });
    });

    const srcUrl = source.querySelector('[data-blog-slot="url"]');
    if (srcUrl) {
      const href = prefixUrl(srcUrl.getAttribute('href') || '');
      target.querySelectorAll('a[data-blog-slot="url"]').forEach(function (dst) {
        if (href) dst.setAttribute('href', href);
      });
    }

    const srcImg = source.querySelector('img[data-blog-slot="image"]');
    const dstImg = target.querySelector('img[data-blog-slot="image"]');
    if (srcImg && dstImg) {
      const imgSrc = srcImg.getAttribute('src');
      if (imgSrc) dstImg.setAttribute('src', imgSrc);
      const srcset = srcImg.getAttribute('srcset');
      if (srcset) dstImg.setAttribute('srcset', srcset);
      const sizes = srcImg.getAttribute('sizes');
      if (sizes) dstImg.setAttribute('sizes', sizes);
      const titleEl = source.querySelector('[data-blog-slot="title"]');
      if (titleEl) dstImg.setAttribute('alt', (titleEl.textContent || '').trim());
    }

    requestAnimationFrame(function () {
      target.classList.add('is-loaded');
    });
  }

  SINGLE_TARGETS.forEach(function (targetDef) {
    const target = document.querySelector(targetDef.selector);
    if (!target) return;

    const match = sourceItems.find(function (item) {
      if (usedItems.has(item)) return false;
      const catEl = item.querySelector('[data-blog-slot="category"]');
      const catSlug = catEl ? (catEl.getAttribute('data-blog-field') || '').trim().toLowerCase() : '';
      return targetDef.allowed.indexOf(catSlug) !== -1;
    });

    if (match) {
      usedItems.add(match);
      fillTarget(target, match);
    }
  });

  window.__blogPrefillDone = true;
})();

/* 7. Heading word spans (with MutationObserver, 5s auto-disconnect) */
(function() {
  function applyWordSpans(root) {
    const headings = (root || document).querySelectorAll('[data-span="true"]');
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
  }

  window.__celApplyWordSpans = applyWordSpans;

  applyWordSpans();

  const observer = new MutationObserver(function(mutations) {
    for (let i = 0; i < mutations.length; i++) {
      const added = mutations[i].addedNodes;
      for (let j = 0; j < added.length; j++) {
        if (added[j].nodeType === 1) {
          applyWordSpans(added[j]);
        }
      }
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(function() { observer.disconnect(); }, 5000);
})();

/* 8. Blog post renderer (Weglot-aware) */
(function () {
  if (window.self !== window.top) return;

  const STORY_CATEGORIES = [
    "stories-ko", "temoignages-detudiants", "kundenberichte",
    "stories", "esperienze-studenti"
  ];

  const TARGET_MODULES = [
    { id: "featured_post",      targetSelector: '.post_featured[post-type="featured"]', count: 1, isMultiplier: false, allowed: STORY_CATEGORIES },
    { id: "featured_category1", targetSelector: '[post-type="featured_category1"]', count: 1, isMultiplier: false,
      allowed: ["usa-canada-ko", "usa-canada-fr", "usa-canada", "usa-kanada-de", "stati-uniti-canada"] },
    { id: "featured_category2", targetSelector: '[post-type="featured_category2"]', count: 1, isMultiplier: false,
      allowed: ["study-abroad-ko", "sejour-linguistique-a-letranger", "sprachaufenthalt", "study-abroad", "studiare-estero"] },
    { id: "featured_category3", targetSelector: '[post-type="featured_category3"]', count: 1, isMultiplier: false,
      allowed: ["local-life-ko", "vie-locale", "lokales-leben", "local-life", "vita-locale"] },
    { id: "featured_category4", targetSelector: '[post-type="featured_category4"]', count: 1, isMultiplier: false,
      allowed: ["career-growth-ko", "carriere-developpement-personnel", "karriere", "career-growth", "carriera-opportunita"] },
    { id: "featured_category5", targetSelector: '[post-type="featured_category5"]', count: 1, isMultiplier: false, allowed: STORY_CATEGORIES },
    { id: "featured_category6", targetSelector: '[post-type="featured_category6"]', count: 1, isMultiplier: false, allowed: STORY_CATEGORIES },
    { id: "recent_big",         targetSelector: '[post-type="recent-big"]',     count: 2,   isMultiplier: true,  allowed: [] },
    { id: "recent_small",       targetSelector: '[post-type="recent-small"]',   count: 4,   isMultiplier: true,  allowed: [] },
    { id: "recent_regular",     targetSelector: '[post-type="recent-regular"]', count: 6,   isMultiplier: true,  allowed: [] },
    { id: "recent_xsmall",      targetSelector: '[post-type="recent-xsmall"]',  count: 999, isMultiplier: true,  allowed: [] }
  ];

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

  const prefixUrl = function (href, lang) {
    if (!href || lang === 'en') return href;
    if (/^\/(post|category)\//.test(href) && !new RegExp('^/' + lang + '/').test(href)) {
      return '/' + lang + href;
    }
    return href;
  };

  const extractPostData = function (item, index) {
    const getAttr = function (slot, attr) {
      const el = item.querySelector('[data-blog-slot="' + slot + '"]');
      return el ? (el.getAttribute(attr) || "").trim() : "";
    };
    const getText = function (slot) {
      const el = item.querySelector('[data-blog-slot="' + slot + '"]');
      return el ? (el.textContent || "").trim() : "";
    };
    const catEl = item.querySelector('[data-blog-slot="category"]');
    const imgEl = item.querySelector('img[data-blog-slot="image"]');
    const id = item.getAttribute("data-item-id") || "post-id-" + index;
    item.setAttribute("data-item-id", id);

    return {
      id: id,
      element: item,
      lang: normalizeLang(item.getAttribute("data-lang")),
      category: catEl ? catEl.textContent.trim() : "",
      categorySlug: catEl ? (catEl.getAttribute("data-blog-field") || "").trim().toLowerCase() : "",
      title: getText("title"),
      paragraph: getText("paragraph"),
      imageSrc: getAttr("image", "src"),
      imageSrcset: imgEl ? (imgEl.getAttribute("srcset") || "") : "",
      imageSizes: imgEl ? (imgEl.getAttribute("sizes") || "") : "",
      urlHref: getAttr("url", "href")
    };
  };

  const renderDataToTarget = function (targetElement, postData, lang) {
    if (!targetElement || !postData) return;
    targetElement.style.display = "";

    ["category", "title", "paragraph"].forEach(function (slot) {
      targetElement.querySelectorAll('[data-blog-slot="' + slot + '"]').forEach(function (el) {
        el.textContent = postData[slot] || "";
      });
    });

    targetElement.querySelectorAll('a[data-blog-slot="url"]').forEach(function (el) {
      el.setAttribute("href", prefixUrl(postData.urlHref, lang) || "#");
    });

    const img = targetElement.querySelector('img[data-blog-slot="image"]');
    if (img && postData.imageSrc) {
      img.setAttribute("src", postData.imageSrc);
      img.setAttribute("alt", postData.title || "");
      if (postData.imageSrcset) {
        img.setAttribute("srcset", postData.imageSrcset);
      }
      if (postData.imageSizes) {
        img.setAttribute("sizes", postData.imageSizes);
      }
    }

    requestAnimationFrame(function () {
      targetElement.classList.add('is-loaded');
    });
  };

  const buildAndRender = function () {
    try {
      const activeLang = getActiveLang();

      const sourceNodes = document.querySelectorAll(".posts_collection .w-dyn-item");
      sourceNodes.forEach(function (node) {
        const rawLang = node.getAttribute("data-lang");
        if (rawLang && normalizeLang(rawLang) !== activeLang) node.remove();
      });

      const currentNodes = Array.from(document.querySelectorAll(".posts_collection .w-dyn-item"));
      if (!currentNodes.length) return;

      const availablePosts = currentNodes.map(function (node, index) {
        return extractPostData(node, index);
      });
      const usedPostIds = new Set();

      TARGET_MODULES.forEach(function (mod) {
        const template = document.querySelector(mod.targetSelector);
        if (!template) return;

        if (mod.isMultiplier) {
          const parent = template.parentElement;
          let clonesAdded = 0;
          for (let i = 0; i < mod.count; i++) {
            const pool = availablePosts.filter(function (p) { return !usedPostIds.has(p.id); });
            const selectedPost = pool[0];
            if (selectedPost) {
              usedPostIds.add(selectedPost.id);
              const clone = clonesAdded === 0 ? template : template.cloneNode(true);
              if (clonesAdded > 0) parent.appendChild(clone);
              renderDataToTarget(clone, selectedPost, activeLang);
              clonesAdded++;
            } else {
              if (clonesAdded === 0) template.remove();
              break;
            }
          }
        } else {
          const pool = availablePosts.filter(function (p) { return !usedPostIds.has(p.id); });
          const selectedPost = pool.find(function (post) {
            return mod.allowed.includes(post.categorySlug);
          });
          if (selectedPost) {
            usedPostIds.add(selectedPost.id);
            renderDataToTarget(template, selectedPost, activeLang);
          } else {
            template.remove();
          }
        }
      });

      if (window.Webflow && window.Webflow.require) {
        const ix2 = window.Webflow.require('ix2');
        if (ix2) {
          ix2.init();
          document.dispatchEvent(new CustomEvent('IX2_AFTER_SETUP'));
        }
      }

      if (typeof window.__celApplyWordSpans === 'function') {
        window.__celApplyWordSpans();
      }
    } catch (error) {
      console.warn('blog-render failed:', error);
    }
  };

  const hookWeglot = function () {
    if (window.Weglot && window.Weglot.initialized) {
      buildAndRender();
    } else {
      window.Weglot.on("initialized", buildAndRender);
    }
    window.Weglot.on("languageChanged", function () { window.location.reload(); });
  };

  if (window.Weglot) {
    hookWeglot();
  } else {
    setTimeout(function () {
      if (window.Weglot) {
        hookWeglot();
      } else {
        buildAndRender();
      }
    }, 500);
  }
})();

/* 9. Blog category links (Weglot-aware) */
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
              let href = linkEl.getAttribute("href") || "#";
              if (activeLang !== 'en' && /^\/category\//.test(href) && !new RegExp('^/' + activeLang + '/').test(href)) {
                href = '/' + activeLang + href;
              }
              validCategories.push({ url: href, text: linkEl.textContent.trim() });
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
  } else {
    document.addEventListener("weglotInit", buildCategoryLinks);
  }
})();
