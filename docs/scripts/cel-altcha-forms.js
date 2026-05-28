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

  // Neutralize ALTCHA's links to altcha.org (footer link + logo anchor) so a
  // visitor can't accidentally click off-site. Keeps the text/logo visible but
  // non-clickable. Re-applied on every re-render via a MutationObserver.
  function stripAltchaLinks(root) {
    const links = root.querySelectorAll('a[href*="altcha.org"]');
    for (let i = 0; i < links.length; i++) {
      const a = links[i];
      a.removeAttribute("href");
      a.removeAttribute("target");
      a.style.pointerEvents = "none";
      a.style.cursor = "default";
      a.style.textDecoration = "none";
      a.style.color = "inherit";
    }
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
    w.setAttribute("auto", "onload"); // solve invisibly on load — no click needed
    w.setAttribute("name", "altcha"); // hidden field submitted with the form
    w.setAttribute("language", lang); // page language (mapped to ALTCHA i18n code)
    if (rtl) w.setAttribute("dir", "rtl"); // Arabic
    w.className = "cel-altcha";
    // Brand background (cream); set on the host so it cascades to .altcha-main.
    w.style.setProperty("--altcha-color-base", "#F9F1DF");
    w.style.setProperty("--altcha-color-base-content", "#37332c"); // dark text for contrast
    // Match the form's .form_checkbox-icon: 20px, 1px #E8DECA border, 5px radius,
    // black fill + white check when checked (ALTCHA's checked state uses --altcha-color-success).
    w.style.setProperty("--altcha-checkbox-size", "20px");
    w.style.setProperty("--altcha-checkbox-border-width", "1px");
    w.style.setProperty("--altcha-checkbox-border-color", "#E8DECA");
    w.style.setProperty("--altcha-checkbox-border-radius", "5px");
    w.style.setProperty("--altcha-color-success", "#000000");
    w.style.setProperty("--altcha-color-success-content", "#FFFFFF");
    placeWidget(form, w);
    stripAltchaLinks(w);
    const obs = new MutationObserver(function () {
      stripAltchaLinks(w);
    });
    obs.observe(w, { childList: true, subtree: true });
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
            try { if (w && typeof w.reset === "function") w.reset(); } catch (err) { /* no-op */ }
          }
        })();
      },
      true, // capture: run before webflow.js's submit handler
    );
  }

  function setup(form, lang, rtl) {
    if (form.__celAltchaReady) return;
    form.__celAltchaReady = true;
    injectWidget(form, lang, rtl);
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
