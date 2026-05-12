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
 *
 * Bundles:
 *   1. Finsweet Attributes v2 (self-hosted) — loaded with fs-list for CMS pagination.
 *      Idempotent: skips if Finsweet already loaded (safe during CDN→self-hosted cutover).
 *   2. Finsweet a11y v1 (self-hosted) — accessibility companion.
 *      Idempotent: skips if already loaded.
 */

/* 1. Finsweet Attributes v2 — fs-list mode */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-list','');document.head.appendChild(s)})();

/* 2. Finsweet a11y v1 */
(function(){if(window.__celA11y)return;window.__celA11y=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';document.head.appendChild(s)})();
