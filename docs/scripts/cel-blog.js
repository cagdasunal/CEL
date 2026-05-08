/*!
 * cel-blog.js — CEL Blog Posts (post template)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-blog.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-blog.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-blog.min.js
 *
 * Add via Webflow: Pages panel → Blog - Posts Template → ⚙️ Settings →
 *   Custom Code → Before </body> tag:
 *     <script src="https://cel.englishcollege.com/scripts/cel-blog.min.js" defer></script>
 *
 * Bundles:
 *   1. finsweet-loader v1 — Finsweet Attributes v2.6.33 (self-hosted on CEL).
 *      Loads the ES-module entry + 46 chunks under
 *      cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/.
 *      Replaces the previous jsdelivr <script async type="module">
 *      currently in Webflow Site Settings → Custom Code → Inside <head> tag
 *      (which can be removed after this bundle is added).
 *
 * Migration date: 2026-05-09. See rules/cel-page-scripts-deploy.md.
 */

/* ============================================================
   1. finsweet-loader v1 (self-hosted Finsweet Attributes 2.6.33)
   Original CDN: https://cdn.jsdelivr.net/npm/@finsweet/attributes@2/attributes.js
   Loads the Finsweet Attributes ES module with fs-toc enabled. Idempotent:
   skips if window.__fsR or window.fsAttributes is already set (e.g. when
   the user keeps the jsdelivr <script> tag in Webflow Site Settings as a
   parallel load during cutover).
   ============================================================ */
(function(){if(window.__fsR||window.fsAttributes)return;window.__fsR=1;const s=document.createElement('script');s.type='module';s.async=true;s.crossOrigin='anonymous';s.src='https://cel.englishcollege.com/scripts/vendor/@finsweet/attributes@2/attributes.js';s.setAttribute('fs-toc','');document.head.appendChild(s)})();
