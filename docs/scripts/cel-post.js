/*!
 * cel-post.js — CEL Blog Post Template (/post/*)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-post.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-post.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-post.min.js
 *
 * Add via Webflow: Pages panel → Blog - Posts Template → ⚙️ Settings →
 *   Custom Code → Before </body> tag:
 *     <script src="https://cel.englishcollege.com/scripts/cel-post.min.js" defer></script>
 *
 * After adding, remove these tags from Webflow (Site Settings or page head custom code):
 *   <script async type="module" fs-toc src="https://cdn.jsdelivr.net/npm/@finsweet/attributes@2/attributes.js"></script>
 *   <script async src="https://cdn.jsdelivr.net/npm/@finsweet/attributes-a11y@1/a11y.js"></script>
 *   <script async src="https://cdn.jsdelivr.net/npm/@finsweet/attributes-modal@1/modal.js"></script>
 *
 * Bundles:
 *   1. Finsweet Attributes v2 (self-hosted) — loaded with fs-toc for table of contents.
 *      Idempotent: skips if Finsweet already loaded (safe during CDN→self-hosted cutover).
 *   2. Finsweet a11y v1 (self-hosted) — accessibility companion.
 *      Idempotent: skips if already loaded.
 *   3. Finsweet modal v1 (self-hosted) — powers the newsletter/subscribe modal.
 *      Idempotent: skips if already loaded.
 */

/* 1. Finsweet Attributes v2 — fs-toc mode */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-toc','');document.head.appendChild(s)})();

/* 2. Finsweet a11y v1 */
(function(){if(window.__celA11y)return;window.__celA11y=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-a11y@1/a11y.js';document.head.appendChild(s)})();

/* 3. Finsweet modal v1 */
(function(){if(window.__celModal)return;window.__celModal=1;const s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes-modal@1/modal.js';document.head.appendChild(s)})();
