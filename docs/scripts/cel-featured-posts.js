/*!
 * cel-featured-posts.js — CEL "Featured Blog Posts" section (marketing pages)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-featured-posts.js
 * Mirrored to:     docs/scripts/cel-featured-posts.{js,min.js}  (cagdasunal/CEL)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-featured-posts.min.js
 *
 * Webflow integration (per page that has the section):
 *   Page Settings → Custom Code → Footer Code:
 *     <script src="https://cel.englishcollege.com/scripts/cel-featured-posts.min.js" defer></script>
 *
 * Loaded with `defer` in the footer → the DOM is fully parsed when this runs, so
 * every IIFE operates on the live tree without DOMContentLoaded waits. The section
 * sits at the end of the page and is non-critical (hover/animation polish only), so
 * late execution is fine.
 *
 * This is the lighter, marketing-page cousin of cel-blog.js (the heavy blog-listing
 * bundle with Finsweet + Swiper + featured/category modules). Keep them separate.
 *
 * Bundle contents (3 IIFEs):
 *   1. CSS injector — blog-bento hover/transition + reduced-motion + dot-blink
 *      keyframe (non-critical polish; injected once via a <style> element). CSS-in-JS
 *      is allowed here: external GitHub-Pages bundles ship their own component CSS
 *      (see rules/webflow-javascript.md §1 "Exception — external bundles").
 *   2. data-lang cleaner — removes [data-lang] elements that don't match <html lang>.
 *   3. Featured-posts renderer (Weglot-aware) — pulls .posts_collection .w-dyn-item
 *      source items into [post-type="recent-big"] (1) + [post-type="recent-small"] (4)
 *      target slots via [data-blog-slot] mapping, then REMOVES the hidden source list
 *      so the rendered DOM (what Google indexes) holds only active-language posts.
 *
 * DOM contract (renaming any of these silently disables the section):
 *   Source:  .posts_collection .w-dyn-item       (CMS list; per-item data-lang)
 *   Slots:   [data-blog-slot="title|paragraph|category|url|image"]
 *   Targets: [post-type="recent-big"] (1), [post-type="recent-small"] (4)
 *   CSS:     .blog-bento_hero, .blog-bento_hero-img, .blog-bento_hero-overlay,
 *            .blog-bento_item, .blog-bento_item-title, .cta-pill-cream
 */

/* 1. CSS injector — blog-bento hover states + reduced-motion + dot-blink keyframe */
(function () {
  if (window.__celFeaturedCSS) return;
  window.__celFeaturedCSS = true;

  const css = `
/* ── Hero card: lift + transitions ── */
.blog-bento_hero {
  transition: transform 0.35s cubic-bezier(0.34, 1.3, 0.64, 1);
}
.blog-bento_hero:hover {
  transform: translateY(-2px);
}

/* ── Hero image: zoom in ── */
.blog-bento_hero-img {
  transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.blog-bento_hero:hover .blog-bento_hero-img {
  transform: scale(1.04);
}

/* ── Hero overlay: deepen on hover ── */
.blog-bento_hero-overlay {
  transition: opacity 0.45s ease;
  opacity: 0.85;
}
.blog-bento_hero:hover .blog-bento_hero-overlay {
  opacity: 1;
}

/* ── Hero CTA pill: brighten border + subtle fill ── */
.blog-bento_hero .cta-pill-cream {
  transition: background 0.25s ease, border-color 0.25s ease;
}
.blog-bento_hero:hover .cta-pill-cream {
  border-color: #f9f1df;
  background: rgba(249, 241, 223, 0.08);
}

/* ── List items: title turns indigo on hover ── */
.blog-bento_item-title {
  transition: color 0.2s ease;
}
.blog-bento_item:hover .blog-bento_item-title {
  color: #5d60ee;
}

/* ── Last list item: no bottom border ── */
.blog-bento_item:last-of-type {
  border-bottom: none;
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  .blog-bento_hero,
  .blog-bento_hero-img,
  .blog-bento_hero-overlay,
  .blog-bento_hero .cta-pill-cream,
  .blog-bento_item-title {
    transition-duration: 0.01ms;
  }
  .blog-bento_hero:hover { transform: none; }
  .blog-bento_hero:hover .blog-bento_hero-img { transform: none; }
}

@keyframes dot-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
`;

  const s = document.createElement('style');
  s.setAttribute('data-cel', 'featured-posts');
  s.textContent = css;
  document.head.appendChild(s);
})();

/* 2. data-lang cleaner — remove [data-lang] elements that don't match current language */
(function () {
  if (window.__celFeaturedLangClean) return;
  window.__celFeaturedLangClean = true;

  const currentLang = (document.documentElement.getAttribute('lang') || 'en').toLowerCase();
  const els = document.querySelectorAll('[data-lang]');
  for (let i = 0; i < els.length; i++) {
    const el = els[i];
    const raw = el.getAttribute('data-lang') || '';
    const langs = raw.toLowerCase().split(/[,\s]+/).map(function (l) { return l.trim(); }).filter(Boolean);
    if (!langs.includes(currentLang)) el.remove();
  }
})();

/* 3. Featured-posts renderer (Weglot-aware) */
(function () {
  if (window.self !== window.top) return;
  if (window.__celFeaturedPostsRender) return;
  window.__celFeaturedPostsRender = true;

  const TARGET_MODULES = [
    { targetSelector: '[post-type="recent-big"]',   count: 1 },
    { targetSelector: '[post-type="recent-small"]', count: 4 }
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

  // Helper: find slot elements that may be the root itself OR its descendants
  const findSlotElements = function (root, selector) {
    const els = [];
    if (root.matches && root.matches(selector)) els.push(root);
    root.querySelectorAll(selector).forEach(function (el) { els.push(el); });
    return els;
  };

  const extractPostData = function (item, index) {
    const firstSlot = function (slot) {
      return findSlotElements(item, '[data-blog-slot="' + slot + '"]')[0] || null;
    };
    const firstAnchorSlot = function (slot) {
      return findSlotElements(item, 'a[data-blog-slot="' + slot + '"]')[0] || null;
    };
    const firstImgSlot = function () {
      return findSlotElements(item, 'img[data-blog-slot="image"]')[0] || null;
    };
    const getText = function (slot) {
      const el = firstSlot(slot);
      return el ? (el.textContent || "").trim() : "";
    };

    const imgEl = firstImgSlot();
    const urlEl = firstAnchorSlot("url");
    const id = item.getAttribute("data-item-id") || "post-id-" + index;
    item.setAttribute("data-item-id", id);

    return {
      id: id,
      title: getText("title"),
      paragraph: getText("paragraph"),
      category: getText("category"),
      imageSrc: imgEl ? (imgEl.getAttribute("src") || "").trim() : "",
      imageSrcset: imgEl ? (imgEl.getAttribute("srcset") || "") : "",
      imageSizes: imgEl ? (imgEl.getAttribute("sizes") || "") : "",
      urlHref: urlEl ? (urlEl.getAttribute("href") || "").trim() : ""
    };
  };

  const renderDataToTarget = function (targetElement, postData) {
    if (!targetElement || !postData) return;
    targetElement.style.display = "";

    // Text slots
    ["title", "paragraph", "category"].forEach(function (slot) {
      findSlotElements(targetElement, '[data-blog-slot="' + slot + '"]').forEach(function (el) {
        el.textContent = postData[slot] || "";
      });
    });

    // URL slot — may be the target element itself OR a descendant
    findSlotElements(targetElement, 'a[data-blog-slot="url"]').forEach(function (el) {
      el.setAttribute("href", postData.urlHref || "#");
    });

    // Image slot
    findSlotElements(targetElement, 'img[data-blog-slot="image"]').forEach(function (img) {
      if (!postData.imageSrc) return;
      img.setAttribute("src", postData.imageSrc);
      img.setAttribute("alt", postData.title || "");
      if (postData.imageSrcset) img.setAttribute("srcset", postData.imageSrcset);
      if (postData.imageSizes) img.setAttribute("sizes", postData.imageSizes);
    });

    requestAnimationFrame(function () {
      targetElement.classList.add('is-loaded');
    });
  };

  let didRender = false;
  const buildAndRender = function () {
    if (didRender) return;   // one-shot: never re-run (would wipe rendered content after source removal)
    didRender = true;
    try {
      const activeLang = getActiveLang();

      const sourceNodes = document.querySelectorAll(".posts_collection .w-dyn-item");
      sourceNodes.forEach(function (node) {
        const rawLang = node.getAttribute("data-lang");
        if (rawLang && normalizeLang(rawLang) !== activeLang) node.remove();
      });

      const currentNodes = Array.from(document.querySelectorAll(".posts_collection .w-dyn-item"));
      const availablePosts = currentNodes.map(function (node, index) {
        return extractPostData(node, index);
      });
      const usedPostIds = new Set();

      TARGET_MODULES.forEach(function (module) {
        const template = document.querySelector(module.targetSelector);
        if (!template) return;

        const parent = template.parentElement;
        let clonesAdded = 0;

        for (let i = 0; i < module.count; i++) {
          const pool = availablePosts.filter(function (p) { return !usedPostIds.has(p.id); });
          const selectedPost = pool[0];

          if (selectedPost) {
            usedPostIds.add(selectedPost.id);
            const clone = clonesAdded === 0 ? template : template.cloneNode(true);
            if (clonesAdded > 0) parent.appendChild(clone);
            renderDataToTarget(clone, selectedPost);
            clonesAdded++;
          } else {
            if (clonesAdded === 0) template.remove();
            break;
          }
        }
      });

      // SEO: the source collection is a hidden ("hide" + weglot-exclude) list carrying
      // blog posts in ALL languages. The active-language posts are now cloned into the
      // visible slots, so remove the hidden source entirely — this keeps the rendered
      // HTML (what Google indexes) free of other-language and duplicate post content.
      // Safe: a language switch triggers window.location.reload(), regenerating it.
      document.querySelectorAll('.posts_collection').forEach(function (list) {
        list.remove();
      });

      if (window.Webflow && window.Webflow.require) {
        const ix2 = window.Webflow.require('ix2');
        if (ix2) {
          ix2.init();
          document.dispatchEvent(new CustomEvent('IX2_AFTER_SETUP'));
        }
      }
    } catch (error) {
      console.warn('cel-featured-posts render failed:', error);
    }
  };

  const init = function () {
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
  };

  init();
})();
