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
 * Messages posted to the parent (the cel-events.js fidelo.com branch validates origin then
 * forwards each to dataLayer -> GA4):
 *   fidelo_widget_open          { step_total }                              -> widget_open (open denominator)
 *   fidelo_booking_step         { step, step_name, step_total,
 *                                 step_direction:forward|back, step_duration_ms,
 *                                 selections[], amount_display, value, currency } -> booking_step
 *   fidelo_booking_abandon      { step, step_name }                         -> booking_abandon (drop-off, last step)
 *   fidelo_application_submitted{ value, currency }                         -> generate_lead(fidelo_booking)
 *
 * SSOT: tools/cel-fidelo-js/cel-fidelo.js  (served minified as cel-fidelo.min.js).
 * Message contract + GA4 wiring documented in README.md. Parent receiver: the fidelo.com
 * origin branch in tools/cel-events-js/cel-events.js (anchored /(^|\.)fidelo\.com$/ test).
 *
 * SKIN (Stage 2 — DORMANT): a SEPARATE IIFE appended at the BOTTOM of this file injects a
 * staging-gated CSS skin into the widget. It is currently a NO-OP (empty SKIN_CSS = zero DOM
 * writes) and is designed to fire ONLY when document.referrer matches the /booking-new staging
 * slug — so the analytics bridge below stays strictly read-only and the LIVE /booking page is
 * never restyled. Full rationale: sites/cel/docs/booking/ + the block's own header comment.
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
  let widgetOpened = false;   // fidelo_widget_open posted once when the nav first renders
  let abandonSent = false;    // fidelo_booking_abandon posted at most once on exit
  // Wall-clock at the moment we entered the CURRENT step, so the time spent ON that
  // step can be attached to the NEXT step transition (step_duration_ms describes the
  // step the visitor just LEFT). performance.now() is monotonic; falls back to Date.now.
  let stepEnteredAt = 0;
  // Last confidently-parsed booking value, carried into the completion event so
  // fidelo_application_submitted has a monetary value even though the price element
  // is not re-read at success time. Both null until a step parses a price.
  let lastValue = null;
  let lastCurrency = null;

  // Monotonic clock (performance.now when available; Date.now fallback). Wrapped so a
  // missing performance object can never throw into the host page.
  function now() {
    try { if (typeof performance !== 'undefined' && performance.now) return performance.now(); } catch (e) { /* no-op */ }
    return Date.now();
  }

  function send(payload) {
    try { window.parent.postMessage(payload, PARENT_ORIGIN); } catch (e) { /* no-op */ }
  }

  // ISO 4217 currency from the matched symbol. Only the three symbols the price
  // regex matches are mapped; anything else yields '' (treated as not-confident).
  // CEL is MULTI-CURRENCY: the Fidelo "Total Amount" line prefixes the dollar sign by
  // location — "$ 3,430" (USA = USD) vs "C$  3,565" (Canada = CAD). A bare '$' is USD;
  // a 'C'/'CA' prefix before '$' is CAD; 'A'/'AU' is AUD. Distinguishing them is the
  // whole point — a bare-'$'->USD map would mislabel every Canadian booking. (Confirmed
  // against real success-screen markup 2026-06-03.)
  function currencyFromSymbol(sym) {
    if (sym === '£') return 'GBP';
    if (sym === '€') return 'EUR';
    if (sym === '$' || sym === 'US$' || sym === 'USD' || sym === 'US') return 'USD';
    if (sym === 'C$' || sym === 'CA$' || sym === 'CAD' || sym === 'CA' || sym === 'CAN$') return 'CAD';
    if (sym === 'A$' || sym === 'AU$' || sym === 'AUD' || sym === 'AU') return 'AUD';
    return '';
  }

  // Parse a price string (e.g. "£1,234", "$ 1,234.56", "€1.234,56") into a
  // { value:Number, currency:ISO } pair, or null. Callers attach value/currency ONLY
  // on a confident parse (known symbol + finite non-negative number) — an ambiguous
  // or garbled total degrades to amount_display, never a wrong value.
  //
  // Decimal disambiguation (conservative, symbol-locale-aware):
  //   - Both '.' and ',' present -> the LAST-occurring separator is the decimal, the
  //     other is thousands grouping ("1,234.56"=>1234.56, "1.234,56"=>1234.56).
  //   - Only ',' present:
  //       £/$  -> comma is ALWAYS thousands grouping ("1,234"=>1234). £/$ EU-style
  //              comma-decimals are too rare to risk a wrong parse.
  //       €    -> ambiguous; with exactly one comma + 1-2 trailing digits it's the
  //              decimal ("12,50"=>12.50), otherwise thousands ("1,234"=>1234).
  //   - Only '.' present:
  //       £/$  -> dot is ALWAYS the decimal point (default dot-decimal locale).
  //       €    -> with exactly one dot + exactly 3 trailing digits it's thousands
  //              grouping ("1.234"=>1234); otherwise the decimal point.
  //   - Neither present: plain integer.
  function parsePrice(raw) {
    if (!raw) return null;
    // Match an optional currency-letter prefix (C/CA/US/A/AU/CAN) glued to a $, OR a
    // bare £/€/$, then 0+ spaces (Fidelo's Canadian total uses TWO spaces: "C$  3,565"),
    // then the number. The captured token (e.g. "C$") is mapped to an ISO code.
    // Require a non-letter (or string start) BEFORE the currency prefix, so a word ending in
    // C/A/US/CA/CAN/AU immediately before the symbol (e.g. "CANADA $5,000", "ACADEMY $3,000")
    // can't have its trailing letter mis-read as an AUD/USD prefix. The leading boundary group
    // is non-captured via the [^A-Za-z] class; m[1] is still the currency token.
    const m = String(raw).match(/(?:^|[^A-Za-z])((?:CAN|CA|US|AU|C|A)?\s?[£$€])\s*([\d.,]+)/);
    if (!m) return null;
    const currency = currencyFromSymbol(m[1].replace(/\s+/g, ''));
    if (!currency) return null;
    // Trim separators that aren't part of the number (leading/trailing . or ,).
    const digits = m[2].replace(/^[.,]+/, '').replace(/[.,]+$/, '');
    if (!/\d/.test(digits)) return null;

    const hasDot = digits.indexOf('.') !== -1;
    const hasComma = digits.indexOf(',') !== -1;
    let normalized;

    if (hasDot && hasComma) {
      if (digits.lastIndexOf(',') > digits.lastIndexOf('.')) {
        normalized = digits.replace(/\./g, '').replace(',', '.'); // "1.234,56" EU
      } else {
        normalized = digits.replace(/,/g, '');                    // "1,234.56" Anglo
      }
    } else if (hasComma) {
      const parts = digits.split(',');
      const after = parts[parts.length - 1];
      if (currency === 'EUR' && parts.length === 2 && (after.length === 1 || after.length === 2)) {
        normalized = digits.replace(',', '.');                    // "12,50" EUR decimal
      } else {
        normalized = digits.replace(/,/g, '');                    // thousands grouping
      }
    } else if (hasDot) {
      const parts = digits.split('.');
      const after = parts[parts.length - 1];
      // Lone dot + exactly 3 trailing digits = thousands grouping ("1.234" -> 1234). CEL's
      // Fidelo uses COMMA thousands for $/C$/US$ (verified: "$ 7,637", "C$ 3,565"), but some
      // locales render the dollar total German-style ("C$ 1.410"); without this a CAD/USD
      // total like that would mis-parse to 1.41. Restricted to EXACTLY 3 trailing digits +
      // single dot so a real decimal ("$ 12.50", "$ 999.5") is never wrongly stripped.
      if (parts.length === 2 && after.length === 3) {
        normalized = digits.replace('.', '');                     // "1.234"/"1.410" -> thousands
      } else {
        normalized = digits;                                      // decimal point
      }
    } else {
      normalized = digits;
    }

    const value = Number(normalized);
    if (!isFinite(value) || value < 0) return null;
    return { value: value, currency: currency };
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

      // Prefer the dedicated "Total Amount" line (.price-list-item-total) — it carries the
      // currency-distinguishing prefix ("$ 3,430" USD vs "C$ 3,565" CAD). Else fall back to the
      // whole prices block. EITHER WAY we take the LAST money token: in a multi-line block the
      // total is last (taking the FIRST would grab a line item — the bug R8 fixes); in the
      // dedicated total line / a single-total block it's the only token. The currency-prefix
      // match requires a non-letter before the symbol so "CANADA $5,000" can't read as AUD.
      const totalEl = document.querySelector('.price-list-item-total');
      const priceEl = totalEl || document.querySelector('[component="block-prices"]');
      if (priceEl && priceEl.textContent) {
        const text = priceEl.textContent.replace(/\s+/g, ' ');
        const all = text.match(/(?:^|[^A-Za-z])(?:CAN|CA|US|AU|C|A)?\s?[£$€]\s*[\d.,]+/g) || [];
        const token = all.length ? all[all.length - 1].replace(/^[^A-Za-z£$€]+/, '').trim() : '';
        if (token) out.amount_display = token.slice(0, 24);
        // Stamp the numeric value+currency from that LAST (=total) token. parsePrice only
        // returns a value when a currency is confidently resolved, so an unparseable block
        // keeps amount_display only.
        if (token) {
          const parsed = parsePrice(token);
          if (parsed) { out.value = parsed.value; out.currency = parsed.currency; }
        }
      }
    } catch (e) { /* defensive: never throw into the host page */ }
    return out;
  }

  function onStep(links) {
    const idx = activeIndex(links);
    if (idx < 0 || idx === lastStep) return;
    // direction: forward when the index advanced, back when the visitor navigated to an
    // earlier step. lastStep === -1 is the FIRST step seen (treated as forward / entry).
    const direction = (lastStep === -1 || idx > lastStep) ? 'forward' : 'back';
    // step_duration_ms = time spent on the step we just LEFT (rounded ms). Omitted on the
    // very first step (no prior step to time). Carried on the NEXT transition's message.
    const enteredPrev = stepEnteredAt;
    const prevSeen = lastStep !== -1;
    lastStep = idx;
    stepEnteredAt = now();
    const name = STEP_NAMES[idx] || ('step_' + (idx + 1));
    const msg = { event: 'fidelo_booking_step', step: idx + 1, step_name: name, step_total: links.length, step_direction: direction };
    if (prevSeen && enteredPrev) {
      const dur = Math.round(stepEnteredAt - enteredPrev);
      if (isFinite(dur) && dur >= 0) msg.step_duration_ms = dur;
    }
    if (CAPTURE_STEPS[name]) {
      const sel = captureSelection();
      if (sel.selections) msg.selections = sel.selections;
      if (sel.amount_display) msg.amount_display = sel.amount_display;
      if (typeof sel.value === 'number' && sel.currency) {
        msg.value = sel.value;
        msg.currency = sel.currency;
        // Remember the latest confidently-parsed total so the completion event
        // (which never re-reads the price element) can carry the booking value.
        lastValue = sel.value;
        lastCurrency = sel.currency;
      }
    }
    send(msg);
    if (name === 'confirmation') startSubmitWatch();
  }

  // Completion signal — CONFIRMED against a live completed booking 2026-06-03.
  // Fidelo's success screen renders a PostAffiliatePro sale block (present ONLY once a
  // booking is actually submitted): an inline <script id="pap_..."> that calls
  // PostAffTracker.createSale(), sums the line items into totalCost, and setOrderID(n).
  // That block is the most reliable, LANGUAGE-INDEPENDENT success marker (the visible
  // "Thank you …" text is translated per locale; the PAP block is not). The legacy
  // selectors + the block-static thank-you text are kept as fallbacks.
  function papSaleScript() {
    // Prefer the inline createSale() script (it carries the totals), not the loader.
    const tagged = document.querySelectorAll('script[id^="pap_"]');
    for (let i = 0; i < tagged.length; i++) {
      if (/createSale\s*\(/.test(tagged[i].textContent || '')) return tagged[i];
    }
    const all = document.getElementsByTagName('script');
    for (let i = 0; i < all.length; i++) {
      if (/PostAffTracker[\s\S]*createSale\s*\(/.test(all[i].textContent || '')) return all[i];
    }
    return null;
  }

  // Sum the `totalCost += N;` lines in the PAP inline script → the REAL booking total
  // (includes negative discount lines). Falls back to setTotalCost(n). Returns a finite
  // number or null. This is more accurate than the displayed-price parse (it reflects
  // discounts/fees applied at checkout).
  function papTotal(scriptEl) {
    if (!scriptEl) return null;
    const txt = scriptEl.textContent || '';
    const re = /totalCost\s*\+=\s*(-?\d+(?:\.\d+)?)/g;
    let m, sum = 0, any = false;
    while ((m = re.exec(txt))) { sum += Number(m[1]); any = true; }
    if (!any) {
      const direct = txt.match(/setTotalCost\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)/);
      if (direct) { sum = Number(direct[1]); any = true; }
    }
    return (any && isFinite(sum) && sum >= 0) ? sum : null;
  }

  function papOrderId(scriptEl) {
    if (!scriptEl) return null;
    const m = (scriptEl.textContent || '').match(/setOrderID\s*\(\s*['"]?([\w-]+)['"]?\s*\)/);
    return m ? m[1] : null;
  }

  // Read the currency (and value) from the "Total Amount" line if it's on the page right
  // now — the PAP total is unitless, so this is how we tell USD ("$ 3,430") from CAD
  // ("C$  3,565") AT COMPLETION, independent of whether an earlier step parsed a price.
  function currencyFromTotalLine() {
    const el = document.querySelector('.price-list-item-total');
    if (!el || !el.textContent) return null;
    return parsePrice(el.textContent.replace(/\s+/g, ' '));  // {value,currency} | null
  }

  // The SUMMARY/review step (the 'confirmation' nav step) is PRE-payment, NOT a completed
  // booking — it shows the final Total Amount + a unique `promotion_code` ("Voucher ID")
  // input + a "Book now" button, and its copy says a payment is required on the NEXT page.
  // We must NEVER treat it as a conversion (that would count unpaid/abandoned bookings). The
  // `promotion_code` field is unique to this screen and language-independent — use it as the
  // "this is the pre-payment summary, do not complete yet" guard. (Confirmed 2026-06-03.)
  function onSummaryPage() {
    return !!document.querySelector(
      'input[name="promotion_code"], #uid-435-promotion_code, [name="promotion_code"]');
  }

  // Returns a marker object {source, total, orderId, currency} when the booking is genuinely
  // COMPLETE (post-payment), else null.
  // VALUE + CURRENCY come from the "Total Amount" line (.price-list-item-total) — per the
  // client the amount settles across earlier screens (add-ons/discounts), so the final total
  // is authoritative. The PAP line-item sum is a fallback only. The summary page also shows a
  // total, so when present we capture it as `total` but DO NOT mark complete unless a real
  // completion signal (PAP createSale / success element) is also present.
  function successMarker() {
    const fromTotal = currencyFromTotalLine();           // {value,currency} from the total line
    const cur = fromTotal ? fromTotal.currency : null;
    const total = fromTotal ? fromTotal.value : null;
    const summary = onSummaryPage();

    // Primary completion: the PostAffiliatePro createSale() block (post-payment success page).
    const pap = papSaleScript();
    if (pap) {
      const v = (typeof total === 'number') ? total : papTotal(pap);
      return { source: 'pap', total: v, orderId: papOrderId(pap), currency: cur };
    }
    // Hard guard: if we're on the pre-payment SUMMARY page, do not complete — even if a
    // populated block-static is present (the summary has several). The total is captured into
    // lastValue/lastCurrency by the step handler regardless, so no value is lost.
    if (summary) return null;
    if (document.querySelector(
      '[component="block-notifications"] .alert-success, ' +
      '.registration-success, [data-registration-complete]')) {
      return { source: 'selector', total: total, orderId: null, currency: cur };
    }
    // Last-resort fallback: a POPULATED block-static (confirmation copy, empty/absent while
    // stepping). LANGUAGE-INDEPENDENT — keys on rendered content, not English (the form runs
    // in 9 languages). Min-length guard stops a placeholder node false-positive. Never reached
    // on the summary page (guarded above), so it can't count a pre-payment review as a booking.
    const stat = document.querySelector('[component="block-static"]');
    if (stat && (stat.textContent || '').replace(/\s+/g, ' ').trim().length > 20) {
      return { source: 'text', total: total, orderId: null, currency: cur };
    }
    return null;
  }

  function successPresent() { return !!successMarker(); }

  function startSubmitWatch() {
    if (watchingSubmit || leadSent) return;
    watchingSubmit = true;
    let n = 0;
    const iv = setInterval(function () {
      if (leadSent || n++ > SUBMIT_POLL_MAX) { clearInterval(iv); return; }
      const marker = successMarker();
      if (marker) {
        leadSent = true;
        clearInterval(iv);
        const done = { event: 'fidelo_application_submitted' };
        // Booking VALUE + CURRENCY both come from the FINAL "Total Amount" line
        // (marker.total / marker.currency, read from .price-list-item-total). Per the
        // client, the amount changes across earlier screens (add-ons/discounts), so only
        // that final total is authoritative — NOT an earlier step's price. Fall back to the
        // earlier-step parse (lastValue/lastCurrency) only if the final line wasn't read.
        // Attach value ONLY with a currency (GA4 drops value when currency is missing).
        const v = (typeof marker.total === 'number') ? marker.total : lastValue;
        const cur = marker.currency || lastCurrency;
        if (typeof v === 'number' && isFinite(v) && cur) {
          done.value = v;
          done.currency = cur;
        }
        // Order/booking id → transaction_id (lets GA4 de-dupe + ties to the Fidelo record).
        if (marker.orderId) done.transaction_id = marker.orderId;
        send(done);
      }
    }, SUBMIT_POLL_MS);
  }

  // Booking abandonment: posted at most once when the visitor leaves the widget WITHOUT
  // completing (pagehide / tab hidden). Carries the last step reached so GA4 can attribute
  // the drop-off to a specific step. Suppressed once the booking is submitted (leadSent).
  function postAbandon() {
    if (abandonSent || leadSent || lastStep < 0) return;
    abandonSent = true;
    const name = STEP_NAMES[lastStep] || ('step_' + (lastStep + 1));
    send({ event: 'fidelo_booking_abandon', step: lastStep + 1, step_name: name });
  }

  function init(nav) {
    // fidelo_widget_open: a clean "opened the widget" denominator, posted ONCE the moment
    // the step nav first renders — BEFORE/independent of the first onStep, so it is distinct
    // from apply_click (the parent CTA) and from step=1 (courses).
    if (!widgetOpened) {
      widgetOpened = true;
      send({ event: 'fidelo_widget_open', step_total: navLinks().length });
    }
    onStep(navLinks());
    try {
      const obs = new MutationObserver(function () { try { onStep(navLinks()); } catch (e) { /* never throw into host */ } });
      obs.observe(nav, { subtree: true, attributes: true, attributeFilter: ['class'] });
    } catch (e) { /* observer unsupported — initial step already sent */ }
    // Abandonment hooks — pagehide is the reliable "leaving the page" signal; visibilitychange
    // catches tab-switch/backgrounding. Both are wrapped so a missing API can't throw.
    try {
      window.addEventListener('pagehide', postAbandon);
      document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') postAbandon();
      });
    } catch (e) { /* listeners unsupported — abandonment simply not tracked */ }
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

/* =============================================================================
 * cel-fidelo SKIN — STAGING GATE configured, INJECTION DEFERRED (no CSS yet)
 * -----------------------------------------------------------------------------
 * Stage 2 of the booking-widget restyle. Docs: sites/cel/docs/booking/.
 * This block is intentionally SEPARATE from the analytics IIFE above and must
 * stay that way — the analytics bridge is read-only and must not be coupled to
 * styling. Adding the skin here keeps the one Fidelo integration point (a single
 * <script src> in Fidelo's "Application form V3" template); no second tag/CSP/SRI.
 *
 * WHY A REFERRER GATE: this script runs INSIDE the cross-origin Fidelo iframe,
 * which is embedded IDENTICALLY on the live page (/booking) and the staging
 * duplicate (/booking-new) — same iframe URL — so the script cannot read the
 * parent path directly (cross-origin throws). The one signal available with NO
 * parent-page change is document.referrer: Fidelo's loader (widget.js) builds the
 * iframe with referrerPolicy="no-referrer-when-downgrade" (and even errors if the
 * host sets a no-referrer / same-origin meta), so document.referrer here is the
 * FULL parent URL incl. the slug, e.g. https://www.englishcollege.com/booking-new.
 *
 * FAIL-CLOSED — the live page can never be restyled by staging work:
 *   • Skin applies ONLY when referrer is the CEL origin AND the path is /booking-new.
 *   • "/booking" does NOT contain "booking-new" → it can NEVER match.
 *   • Missing / origin-only referrer → no match → nothing applied anywhere.
 *
 * STATE TODAY: SKIN_CSS is empty AND the actual <style> injection is deferred
 * (see applySkin) — so this block writes NOTHING to the DOM and the read-only
 * contract is preserved exactly as today ("no css injection now"). The GATE is
 * fully wired and ready. Stage 2 = fill SKIN_CSS + add the injection line
 * (sites/cel/docs/booking/implementation-plan.md). PRODUCTION ROLLOUT later =
 * widen ALLOWED_PATH (e.g. also match /booking) — that single line is the switch.
 * ============================================================================= */
(function () {
  'use strict';

  // Which parent slugs receive the skin. Staging-only today; widen for production.
  const ALLOWED_ORIGIN = /^https?:\/\/(www\.)?englishcollege\.com\//;
  const ALLOWED_PATH = /(?:\/[a-z]{2})?\/booking-new(?:[\/?#]|$)/;   // ← widen for production

  // The CEL skin CSS. EMPTY = dormant. Stage-2 TEST value (2026-06-30): a minimal
  // background-color change to validate the staging gate end-to-end on /booking-new.
  // Replace with the full CEL skin (sites/cel/docs/booking/design-target.md) once confirmed.
  const SKIN_CSS = '@font-face{font-family:LibreFranklin;src:url(https://cel.englishcollege.com/fonts/LibreFranklin-Regular.ttf);font-weight:400;font-display:swap}@font-face{font-family:LibreFranklin;src:url(https://cel.englishcollege.com/fonts/LibreFranklin-Medium.ttf);font-weight:500;font-display:swap}html,body,html body{background-color:#f9f1df}.fidelo-registration-form.fidelo-registration-form{--primary:#5d60ee;--primary-hue:239;--primary-saturation:81%;--primary-lightness:65%;--secondary:#e78b10;--secondary-hue:34;--secondary-saturation:87%;--secondary-lightness:48%;background-color:#f3e7d3;border-radius:15px;padding:4rem 4.5rem;font-family:LibreFranklin,system-ui,sans-serif;font-size:16px;line-height:1.6;color:#5f5950}.fidelo-registration-form.fidelo-registration-form:focus-visible{outline:2px solid #5d60ee;outline-offset:2px}.fidelo-registration-form.fidelo-registration-form .container-fluid{padding:0}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]{margin-left:0;margin-right:0}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>:is(.col-md-8,.col-md-4,.col-md-6){padding-left:0;padding-right:0}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-4{padding-left:28px}.fidelo-registration-form.fidelo-registration-form:is(label,h4,h3,h2,p){color:#5f5950}.fidelo-registration-form.fidelo-registration-form [component="block-input"] label{color:#5f5950}.fidelo-registration-form.fidelo-registration-form:is(h2,h3,h4){font-family:LibreFranklin,system-ui,sans-serif;font-size:1rem;font-weight:500;color:#37332c;text-transform:uppercase;letter-spacing:1.5px;line-height:1.4;margin:1.75rem 0 .9rem}.fidelo-registration-form.fidelo-registration-form h2{font-size:1.15rem;letter-spacing:2px}.fidelo-registration-form.fidelo-registration-form h4{margin:0 0 .9rem}.fidelo-registration-form.fidelo-registration-form strong{color:#37332c;font-weight:500}.fidelo-registration-form.fidelo-registration-form a{color:#4e51be;text-decoration:underline;text-underline-offset:3px;transition:text-decoration-color .25s}.fidelo-registration-form.fidelo-registration-form a:hover{text-decoration-color:transparent}.fidelo-registration-form.fidelo-registration-form hr{border:0;margin:.5rem 0}.fidelo-registration-form.fidelo-registration-form .form-group{margin-bottom:1.5rem}.fidelo-registration-form.fidelo-registration-form nav[component="block-nav-steps"]{counter-reset:step;display:flex;align-items:flex-start;margin:8px 0 88px;font-family:LibreFranklin,system-ui,sans-serif;font-size:.8125rem;letter-spacing:.5px;line-height:1.35}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link{counter-increment:step;position:relative;flex:1 1 0;display:block;padding:42px 0 0;margin:0;font-size:.8125rem;color:#9a8f80;font-family:LibreFranklin,system-ui,sans-serif;font-weight:500;text-align:center;text-decoration:none;transition:color .2s}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link::before{content:counter(step);position:absolute;top:0;left:50%;right:auto;margin:0 0 0 -16px;transform:none;float:none;order:0;z-index:1;display:grid;place-items:center;width:32px;height:32px;border-radius:50%;border:0;background:#f9f0df;color:#5f5950;font-size:.8125rem;font-weight:500;line-height:1;font-variant-numeric:tabular-nums;transition:.2s}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link::after{content:"";position:absolute;top:15px;left:50%;right:auto;bottom:auto;width:100%;height:2px;margin:0;transform:none;z-index:0;display:block;background:#5f595038}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link:last-child::after{content:none}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link:hover{color:#5f5950}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link:is(.visited,.active){color:#4e51be}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link:is(.visited,.active)::before{background:#5d60ee;color:#f9f0df;transform:none}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link:is(.visited,.active)::after{background:#5d60ee;display:block;left:50%;width:100%;transform:none}.fidelo-registration-form.fidelo-registration-form .form-group.input-field>label:not(.custom-control-label){font-size:.8125rem;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:#37332c;margin-bottom:.6rem}.fidelo-registration-form.fidelo-registration-form .custom-control-label::before{background-color:#f9f0df;border:1.5px solid #e9deca}.fidelo-registration-form.fidelo-registration-form .custom-checkbox .custom-control-label::before{border-radius:5px}.fidelo-registration-form.fidelo-registration-form .custom-control-input:checked ~ .custom-control-label::before{background-color:#37332c;border-color:#37332c}.fidelo-registration-form.fidelo-registration-form .custom-control-input:focus ~ .custom-control-label::before{box-shadow:0 0 0 3px #5d60ee40}.fidelo-registration-form.fidelo-registration-form .input-field-checkbox{background:transparent;border-radius:0;padding:0}.fidelo-registration-form.fidelo-registration-form:is(.form-control,.custom-select){height:auto;min-height:3rem;padding:.5rem 1.25rem;background-color:#f9f0df;border:3px solid #e9deca;border-radius:7px;color:#37332c;font-size:1rem;line-height:1.6;transition:border-color .2s,box-shadow .2s}.fidelo-registration-form.fidelo-registration-form .custom-select{height:3rem;padding-right:2.6rem;background-image:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'16\' height=\'16\' viewBox=\'0 0 16 16\'%3E%3Cpath fill=\'none\' stroke=\'%235f5950\' stroke-width=\'1.6\' stroke-linecap=\'round\' stroke-linejoin=\'round\' d=\'M3.5 6 8 10.5 12.5 6\'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 1.1rem center;background-size:16px}.fidelo-registration-form.fidelo-registration-form textarea.form-control{min-height:11.25rem;padding-top:.75rem;padding-bottom:.75rem}.fidelo-registration-form.fidelo-registration-form .form-control::placeholder{color:#9a8f80}.fidelo-registration-form.fidelo-registration-form:is(.form-control,.custom-select):focus{background-color:#f9f0df;border-color:#5d60ee;box-shadow:0 0 0 3px #5d60ee29;color:#37332c;outline:none}.fidelo-registration-form.fidelo-registration-form .form-control:-webkit-autofill{-webkit-box-shadow:inset 0 0 0 50px #f9f0df;-webkit-text-fill-color:#37332c}.fidelo-registration-form.fidelo-registration-form .form-control.is-invalid{border-color:#e74c3c;box-shadow:none}.fidelo-registration-form.fidelo-registration-form .form-control.is-invalid:focus{box-shadow:0 0 0 3px #e74c3c33}.fidelo-registration-form.fidelo-registration-form .invalid-feedback{color:#8f2417;font-size:.8125rem;margin-top:6px}.fidelo-registration-form.fidelo-registration-form .input-group-text{padding:0 0 0 1.1rem;background:#f9f0df;border:3px solid #e9deca;border-right:0;border-radius:7px 0 0 7px;color:#9a8f80}.fidelo-registration-form.fidelo-registration-form .input-group>.form-control{border-left:0;border-radius:0 7px 7px 0}.fidelo-registration-form.fidelo-registration-form .input-group:focus-within{border-radius:7px;box-shadow:0 0 0 3px #5d60ee29}.fidelo-registration-form.fidelo-registration-form .input-group:focus-within:is(.form-control,.input-group-text){border-color:#5d60ee}.fidelo-registration-form.fidelo-registration-form .input-group .form-control:focus{box-shadow:none}.fidelo-registration-form.fidelo-registration-form .btn{border:0;border-radius:100px;font-weight:500;text-decoration:none;transition:.2s}.fidelo-registration-form.fidelo-registration-form .btn:focus{box-shadow:none}.fidelo-registration-form.fidelo-registration-form [component="block-service-container"] .btn{background:#ede3d0;padding:13px 24px;color:#5f5950;font-size:.9375rem;line-height:1.4}.fidelo-registration-form.fidelo-registration-form [component="block-service-container"] .btn:hover{background:#e9deca;color:#37332c}.fidelo-registration-form.fidelo-registration-form [component="block-service-container"] .btn.active{background:#37332c;color:#f9f0df}.fidelo-registration-form.fidelo-registration-form [component="block-service-container"] h4{color:#37332c;font-size:1rem;margin:0 0 1rem}.fidelo-registration-form.fidelo-registration-form .course-grouping-buttons .btn{margin-bottom:12px}.fidelo-registration-form.fidelo-registration-form .course-grouping-buttons .btn i{display:none}.fidelo-registration-form.fidelo-registration-form .btn-add-service{background:transparent;padding:10px 18px;color:#4e51be;font-size:.8125rem;letter-spacing:.5px}.fidelo-registration-form.fidelo-registration-form .btn-add-service:hover{background:#e9deca;color:#4e51be}.fidelo-registration-form.fidelo-registration-form .btn-outline-danger{background:transparent;padding:10px 18px;color:#8f2417;font-size:.8125rem;letter-spacing:.5px}.fidelo-registration-form.fidelo-registration-form .btn-outline-danger:hover{background:#e74c3c14;color:#8f2417}.fidelo-registration-form.fidelo-registration-form .card{background-color:transparent;border:none;color:inherit}.fidelo-registration-form.fidelo-registration-form .card-body{background:transparent;border-color:transparent;border-radius:0}.fidelo-registration-form.fidelo-registration-form [component="block-prices"]{background:#f9f0df;border-radius:20px}.fidelo-registration-form.fidelo-registration-form .service-container-transfer{background:transparent}.fidelo-registration-form.fidelo-registration-form .service-container-transfer .card-body{padding:0}.fidelo-registration-form.fidelo-registration-form .service-container-transfer .fa-bus{display:none}.fidelo-registration-form.fidelo-registration-form .course-card-container{margin-top:10px}.fidelo-registration-form.fidelo-registration-form .course-card-container .card-body{padding:0}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card{background:transparent;border-radius:15px;overflow:visible;margin:0 0 28px;display:grid;grid-template-columns:1fr;grid-template-areas:"img" "body" "footer"}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card::after{content:none}.fidelo-registration-form.fidelo-registration-form .accommodation-card.active{box-shadow:0 0 0 2px #5d60ee}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>img{grid-area:img;display:block;width:100%;height:auto;aspect-ratio:1 / 1;max-height:none;object-fit:cover;border-radius:15px;filter:none}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>.card-body{grid-area:body;width:auto;flex:none;padding:20px 0 8px}.fidelo-registration-form.fidelo-registration-form .accommodation-card .card-title{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:1.25rem;font-weight:500;letter-spacing:0;color:#37332c;margin:0}.fidelo-registration-form.fidelo-registration-form .accommodation-card .card-text{color:#7a6e5d;font-size:.9375rem;margin:4px 0 0}.fidelo-registration-form.fidelo-registration-form .accommodation-card hr{border:0;margin:16px 0}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card .accommodation-combinations{display:grid;grid-template-columns:1fr;gap:14px}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card .accommodation-combinations>.card-block{flex:none;width:100%;height:auto}.fidelo-registration-form.fidelo-registration-form .card-block-xs{width:100%;height:auto;background:transparent;border-radius:0;margin:0;padding:0;transition:none}.fidelo-registration-form.fidelo-registration-form .card-block-xs:hover{background:transparent}.fidelo-registration-form.fidelo-registration-form .card-block-xs.active{background:transparent;box-shadow:none}.fidelo-registration-form.fidelo-registration-form .card-block-xs .no-gutters{display:flex;align-items:center;gap:14px;flex-wrap:nowrap;width:100%;margin:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .no-gutters>.card-control{flex:0 0 auto;max-width:none;width:auto;padding:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .no-gutters>.card-body{flex:1 1 auto;max-width:none;min-width:0;padding:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-control .custom-control{width:1rem;height:1rem;min-height:1rem;padding:0;margin:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-control .custom-control-label{display:block;width:1rem;height:1rem}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-control .custom-control-label::before,.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-control .custom-control-label::after{top:0;left:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-title{font-size:.9375rem;font-weight:500;color:#37332c;margin:0;cursor:pointer}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-title label{display:block;margin:0}.fidelo-registration-form.fidelo-registration-form .card-block-xs .card-text{color:#7a6e5d;font-size:.875rem;margin:2px 0 0}.fidelo-registration-form.fidelo-registration-form .card-footer{grid-area:footer;background:transparent;border:0;padding:6px 0 4px}.fidelo-registration-form.fidelo-registration-form .accommodation-date>.col-md-6{flex:0 0 50%;max-width:50%}.fidelo-registration-form.fidelo-registration-form [component="block-nav-buttons"]{display:flex;justify-content:flex-end;gap:12px;margin-top:36px}.fidelo-registration-form.fidelo-registration-form:is(.btn-primary,.btn-success){background:#e78b10;color:#37332c;padding:15px 30px;font-size:.875rem;letter-spacing:1px;text-transform:uppercase}.fidelo-registration-form.fidelo-registration-form .btn:is(.btn-primary,.btn-success):is(:hover,:active){background:#c97a0d;color:#37332c;transform:translateY(-1px)}.fidelo-registration-form.fidelo-registration-form .btn-primary.float-left{background:transparent;color:#5f5950;margin-right:auto}.fidelo-registration-form.fidelo-registration-form .btn.btn-primary.float-left:is(:hover,:active){background:#e9deca;color:#37332c;transform:none}.fidelo-registration-form.fidelo-registration-form .btn-success{padding:16px 36px;font-size:.9375rem;color:#ffffff}.fidelo-registration-form.fidelo-registration-form .btn.btn-success:is(:hover,:active){color:#ffffff}.fidelo-registration-form.fidelo-registration-form .btn-success>i{display:none}.fidelo-registration-form.fidelo-registration-form [component="block-prices"] .card-body{padding:28px}.fidelo-registration-form.fidelo-registration-form [component="block-prices"] .card-title{font-size:.75rem;letter-spacing:2px;color:#e78b10;margin:0 0 14px}.fidelo-registration-form.fidelo-registration-form div[component="block-prices"] .price-block h5{display:flex;align-items:center;gap:10px;font-size:11px;font-weight:500;letter-spacing:2.5px;line-height:1.4;text-transform:uppercase;color:#e78b10;margin:26px 0 10px}.fidelo-registration-form.fidelo-registration-form .price-block .card{background:transparent;border-radius:0}.fidelo-registration-form.fidelo-registration-form [component="block-prices"] .price-block .card-body{padding:0}.fidelo-registration-form.fidelo-registration-form .price-list .list-group-item{display:flex;justify-content:space-between;align-items:baseline;gap:16px;background:transparent;border:0;color:#37332c;font-size:.9375rem;line-height:1.45}.fidelo-registration-form.fidelo-registration-form div[component="block-prices"]:is(.price-list,.price-list-no-lines) .list-group-item,.fidelo-registration-form.fidelo-registration-form div[component="block-prices"] .price-list .list-group-item:is(:first-child,:last-child){padding:10px 0}.fidelo-registration-form.fidelo-registration-form .price-list .list-group-item>span{font-weight:500;white-space:nowrap;font-variant-numeric:tabular-nums}.fidelo-registration-form.fidelo-registration-form div[component="block-prices"] .price-list .list-group-item:last-child{color:#37332c}.fidelo-registration-form.fidelo-registration-form div[component="block-prices"] .price-description{color:#9a8f80;font-size:.8125rem;margin:3px 0 0;line-height:1.5}.fidelo-registration-form.fidelo-registration-form div[component="block-prices"] .price-list .list-group-item.price-list-item-total{align-items:center;flex-wrap:wrap;row-gap:2px;background:transparent;border-radius:0;padding:2px 0 14px;margin:0}.fidelo-registration-form.fidelo-registration-form .price-list-item-total span:first-child{font-size:.9375rem;font-weight:400;letter-spacing:0;text-transform:none;color:#37332c}.fidelo-registration-form.fidelo-registration-form .price-list-item-total span:last-child{font-size:1.5rem;font-weight:600;color:#37332c;font-variant-numeric:tabular-nums}.fidelo-registration-form.fidelo-registration-form .alert,.fidelo-registration-form.fidelo-registration-form [component="block-notifications"] .list-group-item{display:flex;align-items:center;gap:10px;background:#f9f0df;border:0;border-radius:12px;padding:1rem 1.2rem;margin-bottom:20px;color:#37332c;font-size:.9375rem}.fidelo-registration-form.fidelo-registration-form .alert-danger,.fidelo-registration-form.fidelo-registration-form .alert-info,.fidelo-registration-form.fidelo-registration-form [component="block-notifications"] .list-group-item-danger{background:#e74c3c1f;color:#8f2417}.fidelo-registration-form.fidelo-registration-form .list-group-item-danger>.fas{display:none}.fidelo-registration-form.fidelo-registration-form .list-group-item-success>.fas{color:#1ea869}.fidelo-registration-form.fidelo-registration-form .close{margin-left:auto;opacity:1;color:#8f2417;font-size:1rem}.fidelo-registration-form.fidelo-registration-form .loading-overlay{display:flex;align-items:center;justify-content:center;background:transparent;color:#37332c}.fidelo-registration-form.fidelo-registration-form .loading-overlay .fa-spinner{font-size:1.75rem;color:#5d60ee}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-6{flex:0 0 100%;max-width:100%}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-6>div{display:grid;grid-template-columns:1fr 1fr;gap:0 24px;align-items:start}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-6>div>[component="block-static"]{grid-column:1 / -1}@media (min-width:768px){.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-8{flex:0 0 57%;max-width:57%}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-4{flex:0 0 43%;max-width:43%}}@media (min-width:1200px){.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-4{padding-left:84px}}@media (min-width:1100px){.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card{grid-template-columns:minmax(0,30%) 1fr;grid-template-areas:"img body" "img footer";column-gap:28px}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>img{width:100%;height:auto;min-height:0;aspect-ratio:1 / 1;margin:0;border-radius:15px;align-self:start}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>.card-body{padding:4px 0 8px}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>.card-footer{padding:6px 0 4px}}@media (max-width:767.98px){.fidelo-registration-form.fidelo-registration-form{padding:1.5rem 1rem 2rem}.fidelo-registration-form.fidelo-registration-form nav[component="block-nav-steps"]{margin-bottom:56px}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link{font-size:.75rem;padding:36px 0 0}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link::before{width:26px;height:26px;margin-left:-13px;font-size:.75rem}.fidelo-registration-form.fidelo-registration-form .nav[component="block-nav-steps"] .nav-link::after{top:12px;inset-inline-start:50%;width:100%}.fidelo-registration-form.fidelo-registration-form .input-field-radio .col{flex:0 0 100%;max-width:100%;margin-bottom:6px}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card{grid-template-columns:1fr;grid-template-areas:"img" "body" "footer"}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>img{height:auto;min-height:0;aspect-ratio:1 / 1}.fidelo-registration-form.fidelo-registration-form .service-container-accommodation .accommodation-card>.card-body{padding:18px 0 8px}.fidelo-registration-form.fidelo-registration-form .card-footer{padding:4px 22px 22px}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-4{padding-left:0}.fidelo-registration-form.fidelo-registration-form [component="block-prices"]{margin:28px 0}.fidelo-registration-form.fidelo-registration-form [component="block-columns"]>.col-md-6>div{grid-template-columns:1fr;gap:0}}@media (max-width:500px){.fidelo-registration-form.fidelo-registration-form nav[component="block-nav-steps"]{margin-bottom:26px}div.fidelo-registration-form.fidelo-registration-form nav[component="block-nav-steps"] a.nav-link span{display:none}div.fidelo-registration-form.fidelo-registration-form nav[component="block-nav-steps"] a.nav-link.active span{display:inline;visibility:visible}.fidelo-registration-form.fidelo-registration-form [component="block-nav-buttons"] .btn{flex:1 1 auto;text-align:center}}';

  // True ONLY when the widget is embedded on an allowed (staging) parent page.
  // Reads the parent slug from document.referrer (a URL, never PII / never an input value).
  function envAllowsSkin() {
    try {
      const ref = document.referrer || '';
      return ALLOWED_ORIGIN.test(ref) && ALLOWED_PATH.test(ref);
    } catch (e) { return false; }
  }

  function applySkin() {
    if (!SKIN_CSS) return;            // empty SKIN_CSS = no-op
    if (!envAllowsSkin()) return;     // gate: staging slug only — live /booking never matches
    // Inject exactly ONE <style id="cel-fidelo-skin"> — idempotent + try/catch-wrapped
    // so a CSP style-src block or a missing <head> can never throw into Fidelo's page.
    // This is the ONLY DOM write this file makes (the analytics IIFE above stays read-only).
    try {
      if (document.getElementById('cel-fidelo-skin')) return;  // idempotent
      const style = document.createElement('style');
      style.id = 'cel-fidelo-skin';
      style.textContent = SKIN_CSS;
      (document.head || document.documentElement).appendChild(style);
    } catch (e) { /* never throw into the host (Fidelo) page */ }
  }

  applySkin();
})();
