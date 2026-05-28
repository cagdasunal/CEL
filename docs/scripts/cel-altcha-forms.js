/*!
 * CEL — ALTCHA form protection (glue)
 *
 * Injects an <altcha-widget> into Webflow forms, points it at the self-hosted
 * challenge endpoint, and gates the form's submit on a server-verified
 * proof-of-work. Self-loads the ALTCHA web component (altcha.min.js), so the
 * site needs only ONE script tag — this file.
 *
 * FAIL-OPEN by design: if the widget never solves, or /verify times out or
 * errors, the form is allowed to submit anyway. This guarantees the Submit
 * button can never be permanently dead-locked (the failure mode of the earlier
 * Turnstile attempt). The trade-off: during an ALTCHA/Worker outage the form is
 * unprotected but still works — correct priority for a contact form.
 *
 * Worker: https://cel-altcha.max-c7e.workers.dev  (/challenge, /verify)
 * Hosting: served from cel.englishcollege.com/scripts/cel-altcha-forms.js
 */
(function () {
  "use strict";

  if (window.__celAltchaForms_v1) return;
  window.__celAltchaForms_v1 = true;

  const WORKER = "https://cel-altcha.max-c7e.workers.dev";
  const CHALLENGE_URL = WORKER + "/challenge";
  const VERIFY_URL = WORKER + "/verify";
  const ALTCHA_LIB = "https://cel.englishcollege.com/scripts/altcha.min.js";
  const FORM_SELECTOR = ".w-form form";
  const TIMEOUT_MS = 8000;

  function widgetOf(form) {
    return form.querySelector("altcha-widget");
  }
  function submitBtn(form) {
    return form.querySelector('[type="submit"]');
  }
  function payloadOf(form) {
    const field = form.querySelector('input[name="altcha"]');
    if (field && field.value) return field.value;
    const w = widgetOf(form);
    if (w && w.value) return w.value;
    return null;
  }

  function injectWidget(form) {
    if (widgetOf(form)) return; // respect a manually-placed widget
    const w = document.createElement("altcha-widget");
    w.setAttribute("challengeurl", CHALLENGE_URL);
    w.setAttribute("auto", "onload"); // solve invisibly on load — no click needed
    w.setAttribute("hidefooter", "");
    w.className = "cel-altcha";
    // Brand theming via ALTCHA's CSS custom properties (component-level config).
    w.style.setProperty("--altcha-border-radius", "12px");
    w.style.setProperty("--altcha-color-border", "#d8d2c4");
    w.style.setProperty("--altcha-color-base", "#fbf8f1");
    const btn = submitBtn(form);
    if (btn && btn.parentNode) btn.parentNode.insertBefore(w, btn);
    else form.appendChild(w);
  }

  function waitForPayload(form) {
    return new Promise(function (resolve) {
      const have = payloadOf(form);
      if (have) return resolve(have);
      const w = widgetOf(form);
      let settled = false;
      const finish = function (v) {
        if (settled) return;
        settled = true;
        if (w) w.removeEventListener("statechange", onChange);
        resolve(v);
      };
      const onChange = function () {
        const p = payloadOf(form);
        if (p) finish(p);
      };
      if (w) w.addEventListener("statechange", onChange);
      setTimeout(function () {
        finish(payloadOf(form));
      }, TIMEOUT_MS);
    });
  }

  function verifyPayload(payload) {
    return Promise.race([
      fetch(VERIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: payload }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          return d && d.ok === true ? "ok" : "fail";
        })
        .catch(function () {
          return "timeout";
        }),
      new Promise(function (resolve) {
        setTimeout(function () {
          resolve("timeout");
        }, TIMEOUT_MS);
      }),
    ]);
  }

  function gate(form) {
    form.addEventListener(
      "submit",
      function (e) {
        if (form.__celAltchaPassed) return; // cleared — let Webflow handle it
        e.preventDefault();
        e.stopImmediatePropagation();
        (async function () {
          const payload = await waitForPayload(form);
          let result = "timeout";
          if (payload) result = await verifyPayload(payload);
          // FAIL-OPEN on no-payload / timeout / network error; only an explicit
          // "fail" (forged/expired solution) blocks and re-arms the widget.
          if (payload === null || result === "ok" || result === "timeout") {
            form.__celAltchaPassed = true;
            if (typeof form.requestSubmit === "function") form.requestSubmit(submitBtn(form));
            else form.submit();
          } else {
            const w = widgetOf(form);
            try {
              if (w && typeof w.reset === "function") w.reset();
            } catch (err) {
              /* no-op */
            }
          }
        })();
      },
      true, // capture: run before webflow.js's submit handler
    );
  }

  function setup(form) {
    if (form.__celAltchaReady) return;
    form.__celAltchaReady = true;
    injectWidget(form);
    gate(form);
  }

  function loadAltcha() {
    if (window.customElements && customElements.get("altcha-widget")) return;
    if (document.querySelector("script[data-cel-altcha-lib]")) return;
    const s = document.createElement("script");
    s.src = ALTCHA_LIB;
    s.defer = true;
    s.setAttribute("data-cel-altcha-lib", "");
    (document.head || document.documentElement).appendChild(s);
  }

  function boot() {
    loadAltcha();
    let tries = 0;
    const timer = setInterval(function () {
      tries++;
      const ready = window.customElements && customElements.get("altcha-widget");
      if (ready) {
        const forms = document.querySelectorAll(FORM_SELECTOR);
        if (forms.length) {
          for (let i = 0; i < forms.length; i++) setup(forms[i]);
          clearInterval(timer);
          return;
        }
      }
      if (tries > 200) clearInterval(timer); // ~20s cap
    }, 100);
  }

  boot();
})();
