(function () {
  try {
    const raw = sessionStorage.getItem('cel_unlocked');
    if (raw) {
      const ts = parseInt(raw, 10);
      if (!isNaN(ts) && (Date.now() - ts) < 12 * 60 * 60 * 1000) {
        return; // valid session, <12h old
      }
    }
  } catch (_) { /* sessionStorage unavailable → force redirect */ }
  const ret = encodeURIComponent(window.location.pathname + window.location.hash);
  window.location.replace('/?return=' + ret);
})();
