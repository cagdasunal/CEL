/*!
 * cel-whatsapp.js — Portuguese-only WhatsApp number override for CEL.
 *
 * WHY: CEL is a Weglot site. On Portuguese (/pt) pages Weglot can keep serving
 * a stale WhatsApp number from its translation memory even after the Webflow
 * source is updated. This script forces the correct number on /pt pages ONLY,
 * and re-applies it whenever Weglot re-renders the DOM after load.
 *
 * SCOPE: Portuguese pages only — locale = first URL segment (/pt) or
 * <html lang="pt"> (the same locale signal cel-events.js uses).
 *
 * TARGETS (custom attributes added in the Webflow Designer):
 *   [whatsapp="url"]    -> an <a> whose href is set to the wa link.
 *                          Also matches the "whatsap" typo in the footer markup.
 *   [whatsapp="number"] -> an element whose visible text is set to the number.
 *                          If that element is itself an <a>, its href is set too
 *                          (covers the footer link, which is both).
 *
 * DEPLOY: SSOT = monorepo tools/cel-whatsapp-js/cel-whatsapp.js. ./build.sh
 * minifies it and mirrors both files to the CEL repo docs/scripts/; GitHub
 * Pages serves https://cel.englishcollege.com/scripts/cel-whatsapp.min.js.
 * Loaded via <script src=... defer> in Webflow Site Settings -> Footer Code.
 *
 * Init runs immediately inside the IIFE — never waits on a dom-ready event,
 * because a CDN script may load after that event has already fired
 * (see rules/cel-offers-deploy.md).
 */
(function () {
  "use strict";

  if (window.__celWhatsAppPt_v1) return; // run-once guard (unique per version)
  window.__celWhatsAppPt_v1 = true;

  // --- Portuguese gate ------------------------------------------------------
  const seg = (location.pathname.split("/")[1] || "").toLowerCase();
  const lang = (document.documentElement.getAttribute("lang") || "")
    .toLowerCase()
    .split("-")[0];
  if (seg !== "pt" && lang !== "pt") return; // not Portuguese -> do nothing

  // --- The number to enforce on Portuguese pages (single source of truth) ---
  const PHONE = "5598933007034"; // digits only (api.whatsapp.com ?phone=) — PT/Brazil number
  const DISPLAY = "+5598933007034"; // visible text
  const WA_URL = "https://api.whatsapp.com/send?phone=" + PHONE;

  function apply() {
    // Links — tolerate the "whatsap" typo present in the footer markup.
    document.querySelectorAll('[whatsapp="url"], [whatsap="url"]').forEach(function (a) {
      if (a.tagName === "A" && a.getAttribute("href") !== WA_URL) {
        a.setAttribute("href", WA_URL);
      }
    });
    // Visible numbers.
    document.querySelectorAll('[whatsapp="number"]').forEach(function (el) {
      if (el.textContent.trim() !== DISPLAY) el.textContent = DISPLAY;
      // Footer case: the number element is itself the link.
      if (el.tagName === "A" && el.getAttribute("href") !== WA_URL) {
        el.setAttribute("href", WA_URL);
      }
    });
  }

  // Weglot rewrites text nodes after load — debounce-re-apply so it sticks.
  // apply() only writes when a value is wrong, so it self-terminates (no loop).
  let t;
  function schedule() {
    clearTimeout(t);
    t = setTimeout(apply, 50);
  }

  function start() {
    apply();
    new MutationObserver(schedule).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    if (window.Weglot && typeof window.Weglot.on === "function") {
      try {
        window.Weglot.on("languageChanged", schedule);
      } catch (e) {}
    }
  }

  // defer-loaded => <body> is ready. If injected early, wait for <body> via a
  // MutationObserver (the dom-ready event may already have fired for a CDN file).
  if (document.body) {
    start();
  } else {
    new MutationObserver(function (_, obs) {
      if (document.body) {
        obs.disconnect();
        start();
      }
    }).observe(document.documentElement, { childList: true });
  }
})();
