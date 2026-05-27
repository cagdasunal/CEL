/*!
 * CEL Cookie Consent configuration
 * Library: CookieConsent v3.1.0 (orestbida) — self-hosted at
 *   /scripts/vendor/cookieconsent@3/cookieconsent.{umd.js,css}
 *
 * SSOT (edit here):  cagdasunal/webflow  tools/cel-cookie-consent/cel-cookie-consent.js
 * Mirror (served):   cagdasunal/CEL      docs/scripts/cel-cookie-consent.js
 *   -> https://cel.englishcollege.com/scripts/cel-cookie-consent.js
 *   The CEL copy is a mechanical `cp` of this file. Never edit it directly.
 *
 * Categories & services (see sites/cel/legal/webflow-custom-code.md):
 *   necessary  (always on) - Webflow hosting, this consent record, Weglot language
 *   functional (opt-in)    - Geotargetly (regional offer personalisation)
 *   analytics  (opt-in)    - Google Analytics 4 (G-VZSPVZ9NDR)
 *   marketing  (opt-in)    - PostAffiliatePro (affiliate referral tracking)
 *
 * Two gating mechanisms:
 *   1. <script type="text/plain" data-category="..."> tags (PostAffiliatePro,
 *      Geotargetly) are activated automatically by CookieConsent once the
 *      matching category is granted.
 *   2. The GA4 lazy-loader (kept inline in Webflow Head Code) listens for the
 *      'cel:consent' event broadcast below and only arms itself when analytics
 *      consent is present.
 */
(function () {
  'use strict';

  if (!window.CookieConsent || typeof window.CookieConsent.run !== 'function') return;

  function broadcast() {
    try {
      window.dispatchEvent(new CustomEvent('cel:consent', {
        detail: {
          functional: CookieConsent.acceptedCategory('functional'),
          analytics: CookieConsent.acceptedCategory('analytics'),
          marketing: CookieConsent.acceptedCategory('marketing')
        }
      }));
    } catch (e) { /* no-op */ }
  }

  CookieConsent.run({
    // GDPR: non-essential categories stay off until the user opts in.
    mode: 'opt-in',
    revision: 1,

    cookie: {
      name: 'cel_cookie_consent',
      expiresAfterDays: 182 // ~6 months, then re-ask
    },

    guiOptions: {
      consentModal: {
        layout: 'box wide',
        position: 'bottom left',
        equalWeightButtons: true,
        flipButtons: false
      },
      preferencesModal: {
        layout: 'box',
        position: 'right',
        equalWeightButtons: true,
        flipButtons: false
      }
    },

    onFirstConsent: broadcast,
    onConsent: broadcast,
    onChange: broadcast,

    categories: {
      necessary: {
        enabled: true,
        readOnly: true
      },
      functional: {
        autoClear: {
          cookies: [
            { name: /^geotargetly/i },
            { name: /^gtly/i }
          ]
        }
      },
      analytics: {
        autoClear: {
          cookies: [
            { name: /^_ga/ },
            { name: '_gid' },
            { name: /^_gat/ }
          ]
        }
      },
      marketing: {
        autoClear: {
          cookies: [
            { name: /^PAP/i },
            { name: /^pap_/i }
          ]
        }
      }
    },

    language: {
      default: 'en',
      // The banner is rendered into the DOM, so Weglot auto-translates it into
      // the site's other languages. Only the English source is authored here.
      translations: {
        en: {
          consentModal: {
            title: 'We use cookies',
            description:
              'We use necessary cookies to make our website work. With your permission we also use functional, analytics and marketing cookies to remember your region, understand how the site is used, and credit our partner programme. You can accept all, reject non-essential cookies, or choose what to allow. Read our <a href="/page/privacy-policy" class="cc__link">Privacy Policy</a>.',
            acceptAllBtn: 'Accept all',
            acceptNecessaryBtn: 'Reject all',
            showPreferencesBtn: 'Manage preferences',
            footer:
              '<a href="/page/privacy-policy">Privacy Policy</a>\n<a href="/page/terms-conditions">Terms &amp; Conditions</a>'
          },
          preferencesModal: {
            title: 'Manage cookie preferences',
            acceptAllBtn: 'Accept all',
            acceptNecessaryBtn: 'Reject all',
            savePreferencesBtn: 'Save preferences',
            closeIconLabel: 'Close',
            sections: [
              {
                title: 'Your privacy choices',
                description:
                  'Strictly necessary cookies are always on. For every other category you decide whether to allow it. You can reopen this panel any time via the "Cookie settings" link in the page footer. Full details are in our <a href="/page/privacy-policy" class="cc__link">Privacy Policy</a>.'
              },
              {
                title: 'Strictly necessary',
                description:
                  'Required for the website to function: secure hosting (Webflow), this cookie-consent record, and remembering the language you are viewing (Weglot). These are always active.',
                linkedCategory: 'necessary'
              },
              {
                title: 'Functional',
                description:
                  'Lets us tailor regional content and offers to your approximate location (Geotargetly). If off, you may simply see our default offers.',
                linkedCategory: 'functional',
                cookieTable: {
                  headers: { name: 'Service', desc: 'Purpose', dur: 'Duration' },
                  body: [
                    {
                      name: 'Geotargetly',
                      desc: 'Detects your approximate country from your IP address to show relevant regional offers.',
                      dur: 'Session / up to 1 year'
                    }
                  ]
                }
              },
              {
                title: 'Analytics',
                description:
                  'Helps us understand how visitors find and use the site so we can improve it (Google Analytics 4). Data is reported in aggregate.',
                linkedCategory: 'analytics',
                cookieTable: {
                  headers: { name: 'Cookie', desc: 'Provider — purpose', dur: 'Duration' },
                  body: [
                    { name: '_ga', desc: 'Google Analytics — distinguishes unique visitors.', dur: '2 years' },
                    { name: '_ga_VZSPVZ9NDR', desc: 'Google Analytics — keeps session state.', dur: '2 years' }
                  ]
                }
              },
              {
                title: 'Marketing',
                description:
                  'Measures referrals from our partner/affiliate programme so partners are credited correctly (PostAffiliatePro). Embedded Vimeo videos may also set cookies when you play them.',
                linkedCategory: 'marketing',
                cookieTable: {
                  headers: { name: 'Cookie', desc: 'Provider — purpose', dur: 'Duration' },
                  body: [
                    { name: 'PAPVisitorId', desc: 'PostAffiliatePro — attributes a referral to the correct partner.', dur: 'Up to 1 year' },
                    { name: 'vuid', desc: 'Vimeo — video playback analytics (only if you play a video).', dur: '2 years' }
                  ]
                }
              }
            ]
          }
        }
      }
    }
  });

  // "Cookie settings" footer trigger: any element with [data-cc="show-preferences"]
  // or the .cookie-settings class reopens the preferences panel.
  document.addEventListener('click', function (e) {
    const trigger = e.target.closest('[data-cc="show-preferences"], .cookie-settings');
    if (trigger) {
      e.preventDefault();
      CookieConsent.showPreferences();
    }
  });
})();
