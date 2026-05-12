/*!
 * cel-blog.js — CEL Blog Listing Page (/blog)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-blog.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-blog.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-blog.min.js
 *
 * Add via Webflow: Pages panel → Blog → ⚙️ Settings →
 *   Custom Code → Before </body> tag:
 *     <script src="https://cel.englishcollege.com/scripts/cel-blog.min.js" defer></script>
 *
 * After adding, remove these tags from Webflow (Site Settings or page head custom code):
 *   <script async type="module" fs-list src="https://cdn.jsdelivr.net/npm/@finsweet/attributes@2/attributes.js"></script>
 *   <script async src="https://cdn.jsdelivr.net/npm/@finsweet/attributes-a11y@1/a11y.js"></script>
 *   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css">
 *   <script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>
 *
 * Bundles:
 *   1. Finsweet Attributes v2 (self-hosted) — fs-list for CMS pagination/load-more.
 *      Idempotent: skips if Finsweet already loaded.
 *   2. Finsweet a11y v1 (self-hosted) — accessibility companion.
 *      Idempotent: skips if already loaded.
 *   3. Swiper v11 (self-hosted) — slider/carousel.
 *      Fires swiperReady event on load. Idempotent: skips if already loaded.
 */

/* 1. Finsweet Attributes v2 — fs-list mode */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-list','');document.head.appendChild(s)})();

/* 2. Finsweet a11y v1 */
(function(){if(window.__celA11y)return;window.__celA11y=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';document.head.appendChild(s)})();

/* 3. Swiper v11 — CSS + JS */
(function(){if(window.__swR)return;window.__swR=1;const l=document.createElement('link');l.rel='stylesheet';l.href='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.css';document.head.appendChild(l);const s=document.createElement('script');s.src='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.js';s.onload=function(){document.dispatchEvent(new Event('swiperReady'))};document.head.appendChild(s)})();
