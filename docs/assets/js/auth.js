// Session gate for every /admin/* page. The login cookie holds a signed token
// issued by the cel-dashboard Worker; this script revalidates it WITH the Worker
// on each load (server-side authority — unforgeable, and a password change or a
// removed user revokes live sessions). The page is hidden until validation
// succeeds, so unauthenticated content never flashes.
(function () {
  const root = document.documentElement;
  const prevVis = root.style.visibility;
  root.style.visibility = 'hidden';
  function reveal() { root.style.visibility = prevVis || ''; }

  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? m[1] : '';
  }
  function clearSession() {
    document.cookie = 'cel_session=; Max-Age=0; Path=/; Secure; SameSite=Strict';
  }
  function b64urlToStr(b64url) {
    try {
      const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
      return decodeURIComponent(Array.prototype.map.call(atob(b64), function (c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
    } catch (_) { return ''; }
  }
  function gotoLogin() {
    const ret = encodeURIComponent(window.location.pathname + window.location.hash);
    window.location.replace('/?return=' + ret);
  }

  const token = getCookie('cel_session');
  if (!token) { gotoLogin(); return; }

  // Decode claims for DISPLAY only (not trusted for access) so the shell's
  // user menu can render the name immediately, before validation resolves.
  try {
    const payload = JSON.parse(b64urlToStr((token.split('.')[1]) || ''));
    if (payload && payload.sub) {
      window.__CEL_USER__ = { firstName: payload.fn || '', lastName: payload.ln || '', email: payload.sub };
    }
  } catch (_) { /* malformed token → validation below will reject it */ }

  const DISPATCH_URL = (typeof window.CEL_DISPATCH_URL === 'string') ? window.CEL_DISPATCH_URL : '';
  if (!DISPATCH_URL) { gotoLogin(); return; }

  fetch(DISPATCH_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'validate', token: token })
  }).then(function (r) { return r.json().catch(function () { return {}; }); })
    .then(function (j) {
      if (j && j.ok) {
        if (j.user) window.__CEL_USER__ = j.user;
        reveal();
      } else {
        clearSession();
        gotoLogin();
      }
    }).catch(function () {
      // Worker unreachable → fail closed (never expose the dashboard on error).
      gotoLogin();
    });
})();
