/*!
 * cel-fidelo.js — CEL booking-funnel bridge for the Fidelo registration widget
 * -----------------------------------------------------------------------------
 * Runs INSIDE the cross-origin Fidelo iframe (proxy.fidelo.com), loaded by Fidelo
 * via a single <script src> tag. It reads ONLY the widget's step state and a
 * non-PII selection snapshot, and relays them to the CEL parent page via
 * window.parent.postMessage. The parent RECEIVER (to be ADDED to cel-events.js as the
 * fidelo.com origin branch — spec in BOOKING-FORM-TRACKING.md §3b; NOT present yet) MUST
 * validate the sender origin with an anchored /(^|\.)fidelo\.com$/ test before trusting
 * the data, then forward to GTM -> GA4 within the visitor's real session.
 *
 * SECURITY / PRIVACY (see README.md + the security review notes):
 *   - Sends ONLY to the exact CEL origin (PARENT_ORIGIN) — never '*'.
 *   - NEVER reads free-text / email / tel / textarea / number input VALUES.
 *     The only field content it reads is selection-control LABELS (checked
 *     radios, active service buttons) and the displayed price total.
 *   - Selection capture is gated to the non-PII steps (courses/housing/extras).
 *     The personal-details and confirmation steps emit the step MARKER only.
 *   - Sets no cookies, uses no storage, loads no resources, uses no eval.
 *   - Wrapped so it can never throw into the host (Fidelo) page.
 *
 * SSOT: tools/cel-fidelo-js/cel-fidelo.js  (served minified as cel-fidelo.min.js).
 * Message contract + GA4 wiring documented in README.md. Parent receiver (PLANNED):
 * the fidelo.com origin branch to be added to tools/cel-events-js/cel-events.js
 * (spec in BOOKING-FORM-TRACKING.md §3b) — not present in cel-events.js yet.
 */
(function () {
  'use strict';

  // The ONLY destination. Exact origin — the browser refuses to deliver a
  // postMessage whose targetOrigin does not match the recipient's origin, so a
  // wildcard ('*') is never used. Locale paths (/de/booking, /ar/booking, …) all
  // share this same origin.
  const PARENT_ORIGIN = 'https://www.englishcollege.com';

  // Stable, language-independent step keys, addressed by NAV INDEX. The visible
  // labels are translated per locale (COURSES/KURSE/دورة …) but the order is
  // identical across all locales (verified EN/DE/AR), so the index is the stable
  // key — we never depend on the translated label.
  const STEP_NAMES = ['courses', 'housing', 'extras', 'personal_details', 'confirmation'];

  // Steps on which a (non-PII) selection snapshot may be captured. personal_details
  // and confirmation are intentionally ABSENT — those screens carry personal data.
  const CAPTURE_STEPS = { courses: true, housing: true, extras: true };

  const NAV = '[component="block-nav-steps"]';
  const MAX_LABELS = 8;       // cap on selection labels per message
  const WAIT_TRIES = 100;     // ~15s budget for the SPA to render the nav
  const WAIT_MS = 150;
  const SUBMIT_POLL_MS = 1000;
  const SUBMIT_POLL_MAX = 90; // ~90s watch window after reaching confirmation

  let lastStep = -1;
  let leadSent = false;
  let watchingSubmit = false;

  function send(payload) {
    try { window.parent.postMessage(payload, PARENT_ORIGIN); } catch (e) { /* no-op */ }
  }

  function navLinks() {
    return document.querySelectorAll(NAV + ' .nav-link');
  }

  function activeIndex(links) {
    for (let i = 0; i < links.length; i++) {
      if (links[i].classList && links[i].classList.contains('active')) return i;
    }
    return -1;
  }

  // Non-PII selection snapshot for the CURRENT step. Reads ONLY selection-control
  // labels (checked radios, active service buttons) + the displayed price total.
  // It NEVER reads .value of any input/textarea, so names, emails, phone numbers,
  // dates, and free text cannot be captured even by accident.
  function captureSelection() {
    const out = {};
    try {
      const labels = [];
      const radios = document.querySelectorAll('input[type="radio"]:checked');
      for (let i = 0; i < radios.length; i++) {
        const lab = radios[i].closest('label') || radios[i].parentElement;
        const t = lab && lab.textContent ? lab.textContent.replace(/\s+/g, ' ').trim() : '';
        if (t) labels.push(t.slice(0, 60));
      }
      const btns = document.querySelectorAll(
        '[component="block-service-container"] .btn.active, ' +
        '[component="block-service-container"] .btn-secondary'
      );
      for (let j = 0; j < btns.length; j++) {
        const bt = (btns[j].textContent || '').replace(/\s+/g, ' ').trim();
        if (bt) labels.push(bt.slice(0, 60));
      }
      if (labels.length) out.selections = labels.slice(0, MAX_LABELS);

      const priceEl = document.querySelector('[component="block-prices"]');
      if (priceEl && priceEl.textContent) {
        const m = priceEl.textContent.replace(/\s+/g, ' ').match(/[£$€]\s?[\d.,]+/);
        if (m) out.amount_display = m[0].slice(0, 24);
      }
    } catch (e) { /* defensive: never throw into the host page */ }
    return out;
  }

  function onStep(links) {
    const idx = activeIndex(links);
    if (idx < 0 || idx === lastStep) return;
    lastStep = idx;
    const name = STEP_NAMES[idx] || ('step_' + (idx + 1));
    const msg = { event: 'fidelo_booking_step', step: idx + 1, step_name: name, step_total: links.length };
    if (CAPTURE_STEPS[name]) {
      const sel = captureSelection();
      if (sel.selections) msg.selections = sel.selections;
      if (sel.amount_display) msg.amount_display = sel.amount_display;
    }
    send(msg);
    if (name === 'confirmation') startSubmitWatch();
  }

  // Best-effort completion signal. Fires at most once.
  // NOTE (README "Open item"): the precise success marker is Bootstrap-convention
  // (.alert-success in the notifications block) but should be confirmed against a
  // live completed booking, or replaced by a success hook Fidelo points us to.
  function successPresent() {
    return !!document.querySelector(
      '[component="block-notifications"] .alert-success, ' +
      '.registration-success, [data-registration-complete]'
    );
  }

  function startSubmitWatch() {
    if (watchingSubmit || leadSent) return;
    watchingSubmit = true;
    let n = 0;
    const iv = setInterval(function () {
      if (leadSent || n++ > SUBMIT_POLL_MAX) { clearInterval(iv); return; }
      if (successPresent()) {
        leadSent = true;
        clearInterval(iv);
        send({ event: 'fidelo_application_submitted' });
      }
    }, SUBMIT_POLL_MS);
  }

  function init(nav) {
    onStep(navLinks());
    try {
      const obs = new MutationObserver(function () { try { onStep(navLinks()); } catch (e) { /* never throw into host */ } });
      obs.observe(nav, { subtree: true, attributes: true, attributeFilter: ['class'] });
    } catch (e) { /* observer unsupported — initial step already sent */ }
  }

  // The widget renders asynchronously, so wait (bounded) for the step nav to exist.
  // This is NOT a DOMContentLoaded dependency — it polls for the SPA-rendered node,
  // which may appear well after the document is ready.
  let tries = 0;
  (function waitForNav() {
    let nav = null;
    try { nav = document.querySelector(NAV); } catch (e) { /* no-op */ }
    if (nav) { init(nav); return; }
    if (tries++ < WAIT_TRIES) setTimeout(waitForNav, WAIT_MS);
  })();
})();
