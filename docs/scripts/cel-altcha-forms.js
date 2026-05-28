/*!
 * CEL — ALTCHA form protection (glue), multilingual
 *
 * Injects an <altcha-widget> into Webflow forms, points it at the self-hosted
 * challenge endpoint, gates submit on a server-verified proof-of-work, and
 * renders the widget in the page's language (Weglot sets <html lang>).
 *
 * Self-loads the ALTCHA engine (altcha.min.js) so the site needs ONE script tag.
 *
 * FAIL-OPEN by design: if the widget never solves, or /verify times out/errors,
 * the form still submits. The Submit button can never be permanently dead-locked.
 *
 * TURNSTILE COEXISTENCE: Webflow's native Cloudflare Turnstile is enabled site-wide,
 * but its own widget never renders on this "Blocks" form — Webflow's forms bundle binds
 * the Turnstile render to a jQuery "ready" event that doesn't fire post-load under
 * jQuery 3.5.1 — so the cf-turnstile-response token its SERVER requires is never produced
 * and every submit returns 422 ("Could not process the form submission"). This glue
 * renders Turnstile itself using the form's OWN data-turnstile-sitekey, captures the
 * token, and submits it as cf-turnstile-response (and sets data-wf-no-turnstile so
 * Webflow's broken flow can't disable the button / hang). Turnstile stays a real second
 * layer; ALTCHA is the first. If the form has no Turnstile sitekey, this is a no-op.
 *
 * Worker: https://cel-altcha.max-c7e.workers.dev  (/challenge, /verify)
 * Hosting: cel.englishcollege.com/scripts/cel-altcha-forms.js
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

  // Page 2-letter lang (Weglot) → ALTCHA i18n code. fr/es/pt need the regioned code.
  const LANG_MAP = { en: "en", de: "de", fr: "fr-fr", es: "es-es", it: "it", pt: "pt-pt", ko: "ko", ja: "ja", ar: "ar" };

  // Official ALTCHA translations (github.com/altcha-org/altcha) for the 8 non-English
  // CEL locales (en ships with the widget). Visible PoW-flow strings only.
  const I18N = {
    "de": { ariaLinkLabel: "Altcha (offizielle Website)", label: "Ich bin kein Roboter", loading: "Lade...", verifying: "Wird überprüft...", verified: "Überprüft", error: "Überprüfung fehlgeschlagen. Bitte versuchen Sie es später erneut.", expired: "Überprüfung abgelaufen. Bitte versuchen Sie es erneut.", verificationRequired: "Überprüfung erforderlich!", waitAlert: "Überprüfung läuft... bitte warten.", footer: 'Geschützt durch <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (offizielle Website)">ALTCHA</a>' },
    "fr-fr": { ariaLinkLabel: "Altcha (site officiel)", label: "Je ne suis pas un robot", loading: "Chargement...", verifying: "Vérification en cours...", verified: "Vérifié", error: "Échec de la vérification. Essayez à nouveau plus tard.", expired: "La vérification a expiré. Essayez à nouveau.", verificationRequired: "Vérification requise !", waitAlert: "Vérification en cours... veuillez patienter.", footer: 'Protégé par <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (site officiel)">ALTCHA</a>' },
    "es-es": { ariaLinkLabel: "Altcha (sitio web oficial)", label: "No soy un robot", loading: "Cargando...", verifying: "Verificando...", verified: "Verificado", error: "Falló la verificación. Por favor intente nuevamente más tarde.", expired: "Verificación expirada. Por favor intente nuevamente.", verificationRequired: "¡Verificación requerida!", waitAlert: "Verificando... por favor espere.", footer: 'Protegido por <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (sitio web oficial)">ALTCHA</a>' },
    "it": { ariaLinkLabel: "Altcha (sito ufficiale)", label: "Non sono un robot", loading: "Caricamento...", verifying: "Verifica in corso...", verified: "Verificato", error: "Verifica fallita. Riprova più tardi.", expired: "Verifica scaduta. Riprova.", verificationRequired: "Verifica richiesta!", waitAlert: "Verifica in corso... attendere.", footer: 'Protetto da <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (sito ufficiale)">ALTCHA</a>' },
    "pt-pt": { ariaLinkLabel: "Altcha (site oficial)", label: "Não sou um robô", loading: "A carregar...", verifying: "A verificar...", verified: "Verificado", error: "A verificação falhou. Por favor, tente novamente mais tarde.", expired: "Verificação expirada. Por favor, tente novamente.", verificationRequired: "Verificação necessária!", waitAlert: "A verificar... por favor aguarde.", footer: 'Protegido por <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (site oficial)">ALTCHA</a>' },
    "ko": { ariaLinkLabel: "Altcha (공식 웹사이트)", label: "저는 로봇이 아닙니다", loading: "로딩 중...", verifying: "확인 중...", verified: "확인됨", error: "인증 실패. 나중에 다시 시도해주세요.", expired: "인증이 만료되었습니다. 다시 시도해주세요.", verificationRequired: "인증이 필요합니다!", waitAlert: "확인 중... 잠시만 기다려주세요.", footer: '보호됨 <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (공식 웹사이트)">ALTCHA</a>' },
    "ja": { ariaLinkLabel: "Altcha (公式ウェブサイト)", label: "私はロボットではありません", loading: "読み込み中...", verifying: "確認中...", verified: "確認済み", error: "認証に失敗しました。後でもう一度試してください。", expired: "認証が期限切れです。再試行してください。", verificationRequired: "認証が必要です！", waitAlert: "確認中...少々お待ちください。", footer: '保護されています <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (公式ウェブサイト)">ALTCHA</a>' },
    "ar": { ariaLinkLabel: "Altcha (الموقع الرسمي)", label: "أنا لست روبوتاً", loading: "جارٍ التحميل...", verifying: "جارٍ التحقق...", verified: "تم التحقق", error: "فشل التحقق. حاول مرة أخرى لاحقاً.", expired: "انتهت صلاحية التحقق. حاول مرة أخرى.", verificationRequired: "مطلوب التحقق!", waitAlert: "جارٍ التحقق... يرجى الانتظار.", footer: 'محمي بواسطة <a href="https://altcha.org/" tabindex="-1" target="_blank" aria-label="Altcha (الموقع الرسمي)">ALTCHA</a>' }
  };

  function rawLang() {
    return (document.documentElement.lang || "en").slice(0, 2).toLowerCase();
  }
  function altchaLang() {
    return LANG_MAP[rawLang()] || "en";
  }
  function isRtl() {
    return rawLang() === "ar";
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

  function registerI18n() {
    if (!window.$altcha || !window.$altcha.i18n || window.__celAltchaI18nDone) return;
    for (const code in I18N) {
      try { window.$altcha.i18n.set(code, I18N[code]); } catch (e) { /* no-op */ }
    }
    window.__celAltchaI18nDone = true;
  }

  function widgetOf(form) { return form.querySelector("altcha-widget"); }
  function submitBtn(form) { return form.querySelector('[type="submit"]'); }
  function payloadOf(form) {
    const field = form.querySelector('input[name="altcha"]');
    if (field && field.value) return field.value;
    const w = widgetOf(form);
    if (w && w.value) return w.value;
    return null;
  }

  // Put the widget inside .form_field-altcha (use the form's own element if the
  // designer added one; otherwise create it before the submit button).
  function placeWidget(form, w) {
    let holder = form.querySelector(".form_field-altcha");
    if (!holder) {
      holder = document.createElement("div");
      holder.className = "form_field-altcha";
      const btn = submitBtn(form);
      if (btn && btn.parentNode) btn.parentNode.insertBefore(holder, btn);
      else form.appendChild(holder);
    }
    holder.appendChild(w);
  }

  function injectWidget(form, lang, rtl) {
    if (widgetOf(form)) return; // respect a manually-placed widget
    const w = document.createElement("altcha-widget");
    w.setAttribute("challenge", CHALLENGE_URL); // v3 attribute name (NOT the old "challengeurl")
    w.setAttribute("auto", "onload"); // solve the proof-of-work in the background on load
    w.setAttribute("name", "altcha"); // hidden field submitted with the form
    w.setAttribute("language", lang); // for a11y text / any adaptive challenge
    if (rtl) w.setAttribute("dir", "rtl");
    w.className = "cel-altcha";
    w.style.display = "none"; // INVISIBLE captcha — no visible checkbox/widget
    placeWidget(form, w);
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
      setTimeout(function () { finish(payloadOf(form)); }, TIMEOUT_MS);
    });
  }

  function verifyPayload(payload) {
    return Promise.race([
      fetch(VERIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: payload }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) { return d && d.ok === true ? "ok" : "fail"; })
        .catch(function () { return "timeout"; }),
      new Promise(function (resolve) { setTimeout(function () { resolve("timeout"); }, TIMEOUT_MS); }),
    ]);
  }

  // ─── Webflow native Turnstile coexistence ──────────────────────────────────
  // The form carries a data-turnstile-sitekey and Webflow's server REQUIRES a valid
  // cf-turnstile-response token, but Webflow's own widget never renders on this Blocks
  // form (its bundle binds the render to a jQuery "ready" event that never fires under
  // jQuery 3.5.1). We render Turnstile ourselves with the form's OWN sitekey, capture
  // the token, and attach it. No sitekey on the form → these are all no-ops.

  function turnstileSitekey(form) {
    return form.getAttribute("data-turnstile-sitekey") || null;
  }

  // Render an invisible Turnstile (idempotent). Kept full-size + opacity:0 so the
  // challenge actually executes (it won't run inside a display:none container).
  function renderTurnstile(form) {
    if (form.__celTsRendered) return;
    const sitekey = turnstileSitekey(form);
    if (!sitekey) return;
    if (!window.turnstile || typeof window.turnstile.render !== "function") return;
    let holder = form.querySelector(".cel-turnstile-holder");
    if (!holder) {
      holder = document.createElement("div");
      holder.className = "cel-turnstile-holder";
      holder.style.cssText = "position:fixed;right:0;bottom:0;opacity:0;pointer-events:none;z-index:-1;";
      form.appendChild(holder);
    }
    try {
      form.__celTsWidgetId = window.turnstile.render(holder, {
        sitekey: sitekey,
        callback: function (token) { form.__celTsToken = token; enableSubmit(form, token); },
        "error-callback": function () { form.__celTsToken = null; },
        "expired-callback": function () { form.__celTsToken = null; },
      });
      form.__celTsRendered = true;
    } catch (e) { /* no-op — fail open */ }
  }

  function waitForTurnstileToken(form) {
    return new Promise(function (resolve) {
      if (form.__celTsToken) return resolve(form.__celTsToken);
      let n = 0;
      const t = setInterval(function () {
        n++;
        if (form.__celTsToken) { clearInterval(t); resolve(form.__celTsToken); }
        else if (n >= 80) { clearInterval(t); resolve(form.__celTsToken || null); } // ~8s cap
      }, 100);
    });
  }

  function attachTurnstileToken(form) {
    if (!turnstileSitekey(form)) return Promise.resolve(); // not Turnstile-protected
    renderTurnstile(form); // ensure the widget exists (idempotent)
    return waitForTurnstileToken(form).then(function (token) {
      if (!token) return; // FAIL-OPEN: submit without it (no worse than the broken default)
      let inp = form.querySelector('input[name="cf-turnstile-response"]');
      if (!inp) {
        inp = document.createElement("input");
        inp.type = "hidden";
        inp.name = "cf-turnstile-response";
        form.appendChild(inp);
      }
      inp.value = token;
    });
  }

  // Turnstile tokens are single-use; reset so any resubmit gets a fresh one.
  function refreshTurnstile(form) {
    form.__celTsToken = null;
    try {
      if (form.__celTsWidgetId != null && window.turnstile && typeof window.turnstile.reset === "function") {
        window.turnstile.reset(form.__celTsWidgetId);
      }
    } catch (e) { /* no-op */ }
  }

  // Webflow's forms init DISABLES the submit button + adds w-form-loading whenever a
  // Turnstile sitekey is present but its own (never-firing) render hasn't set a token —
  // so on this page the button is dead on load and users can't click it. We feed
  // Webflow's form-state object (jQuery .data) our token so its O() re-arm keeps the
  // button enabled, and clear the stuck loading state. Best-effort + guarded.
  function enableSubmit(form, token) {
    try {
      if (window.jQuery && typeof window.jQuery.data === "function") {
        const st = window.jQuery.data(form, ".w-form");
        if (st) st.turnstileToken = token || st.turnstileToken || true;
      }
    } catch (e) { /* no-op */ }
    const btn = submitBtn(form);
    if (btn) { btn.disabled = false; btn.classList.remove("w-form-loading"); }
  }

  function prepareTurnstile(form) {
    if (!turnstileSitekey(form)) return;
    form.setAttribute("data-wf-no-turnstile", ""); // stop Webflow's broken native flow
    enableSubmit(form); // undo Webflow's init button-disable so the user can submit
    const onFocus = function () { // pre-solve on first interaction so the token is ready by submit
      form.removeEventListener("focusin", onFocus);
      enableSubmit(form);
      renderTurnstile(form);
    };
    form.addEventListener("focusin", onFocus);
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
          // Explicit ALTCHA "fail" (forged/expired solution) blocks + re-arms the widget.
          // Everything else (ok / timeout / no-payload / network error) FAILS OPEN.
          if (!(payload === null || result === "ok" || result === "timeout")) {
            const w = widgetOf(form);
            try { if (w && typeof w.reset === "function") w.reset(); } catch (err) { /* no-op */ }
            return;
          }
          // Attach a fresh Webflow Turnstile token (no-op if the form isn't Turnstile-protected).
          try { await attachTurnstileToken(form); } catch (err) { /* fail open — never block submit */ }
          form.__celAltchaPassed = true;
          if (typeof form.requestSubmit === "function") form.requestSubmit(submitBtn(form));
          else form.submit();
          form.__celAltchaPassed = false; // re-arm: next submit re-verifies + refreshes token
          refreshTurnstile(form); // invalidate the single-use token just sent
        })();
      },
      true, // capture: run before webflow.js's submit handler
    );
  }

  function setup(form, lang, rtl) {
    if (form.__celAltchaReady) return;
    form.__celAltchaReady = true;
    injectWidget(form, lang, rtl);
    prepareTurnstile(form);
    gate(form);
  }

  function boot() {
    loadAltcha();
    const lang = altchaLang();
    const rtl = isRtl();
    let tries = 0;
    const timer = setInterval(function () {
      tries++;
      const ready = window.customElements && customElements.get("altcha-widget") && window.$altcha && window.$altcha.i18n;
      if (ready) {
        registerI18n(); // register translations BEFORE injecting widgets
        const forms = document.querySelectorAll(FORM_SELECTOR);
        if (forms.length) {
          for (let i = 0; i < forms.length; i++) setup(forms[i], lang, rtl);
          clearInterval(timer);
          return;
        }
      }
      if (tries > 200) clearInterval(timer); // ~20s cap
    }, 100);
  }

  boot();
})();
