/*!
 * CEL — /san-diego-ca/pacific-beach page bundle
 * Source of truth: sites/cel/claude-design-export/project/pages/san-diego/
 *   why-learn-english-pacific-beach.html (inline blocks 1-4)
 * Deployed minified as cel-sd-pacific-beach.min.js — see tools/cel-page-scripts/build.sh
 */

/* 1. Webflow stamps w--current on any same-page anchor, and .hero_cta-ghost.w--current
   forces color:var(--cream-soft). All live page bundles ship this identical cleanup. */
(function () {
  if (window.__celPbCurrent) return;
  window.__celPbCurrent = true;
  function clean() {
    document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current')
      .forEach(function (e) { e.classList.remove('w--current'); });
  }
  setInterval(clean, 300);
  clean();
})();

/* 2. TOC scroll-spy. */
(function () {
  if (window.__celToc) return;
  window.__celToc = true;
  var links = [].slice.call(document.querySelectorAll('.stoc_link[data-target]'));
  if (!links.length) return;
  var targets = links.map(function (l) { return l.dataset.target; });
  var sections = targets.map(function (t) { return document.getElementById(t); }).filter(Boolean);
  if (!sections.length) return;
  var navbar = document.querySelector('.navbar_component');
  var label = document.querySelector('.stoc_label');
  links.forEach(function (l) { l.removeAttribute('href'); l.setAttribute('tabindex', '0'); });
  function setActive(id) {
    links.forEach(function (l) {
      var on = l.dataset.target === id;
      var dot = l.querySelector('.stoc_dot');
      var txt = l.querySelector('.stoc_text');
      l.classList.toggle('is-active', on);
      if (dot) dot.classList.toggle('is-active', on);
      if (txt) txt.classList.toggle('is-active', on);
    });
    if (label) {
      var cur = links.filter(function (l) { return l.dataset.target === id; })[0];
      if (cur) {
        var t = cur.querySelector('.stoc_text');
        label.textContent = t ? t.textContent.trim() : cur.textContent.trim();
      }
    }
  }
  function spy() {
    var edge = (navbar ? navbar.offsetHeight : 90) + 40;
    var id = sections[0].id;
    sections.forEach(function (s) { if (s.getBoundingClientRect().top <= edge) id = s.id; });
    setActive(id);
  }
  var queued = 0;
  window.addEventListener('scroll', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { spy(); queued = 0; });
  }, { passive: true });
  links.forEach(function (l) {
    l.addEventListener('click', function (e) {
      e.preventDefault();
      var s = document.getElementById(l.dataset.target);
      if (!s) return;
      setActive(l.dataset.target);
      window.scrollTo({
        top: s.getBoundingClientRect().top + window.scrollY - (navbar ? navbar.offsetHeight : 90) - 24,
        behavior: 'smooth'
      });
    });
    l.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); l.click(); }
    });
  });
  var hash = location.hash.replace('#', '');
  if (targets.indexOf(hash) !== -1) setActive(hash); else spy();
})();

/* 3. FAQ accordion — single-open, maxHeight animation, aria-expanded.
   .faq-q is an <a> with no href, which Enter/Space do not natively activate. */
(function () {
  if (window.__celFq) return;
  window.__celFq = true;
  if (!document.querySelector('.faq-item')) return;
  document.addEventListener('click', function (e) {
    var q = e.target.closest && e.target.closest('.faq-q');
    if (!q) return;
    var item = q.closest('.faq-item');
    if (!item) return;
    var wasOpen = item.dataset.faqOpen === 'true';
    document.querySelectorAll('.faq-item').forEach(function (it) {
      var body = it.querySelector('.faq-body');
      var qq = it.querySelector('.faq-q');
      var ic = it.querySelector('.faq-icon');
      it.dataset.faqOpen = 'false';
      it.classList.remove('is-open');
      if (qq) { qq.classList.remove('is-open'); qq.setAttribute('aria-expanded', 'false'); }
      if (ic) ic.classList.remove('is-open');
      if (body) body.style.maxHeight = '0px';
    });
    if (!wasOpen) {
      var body2 = item.querySelector('.faq-body');
      var inner = item.querySelector('.faq-body-inner');
      var ic2 = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'true';
      item.classList.add('is-open');
      q.classList.add('is-open');
      q.setAttribute('aria-expanded', 'true');
      if (ic2) ic2.classList.add('is-open');
      if (body2 && inner) body2.style.maxHeight = inner.scrollHeight + 'px';
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var q = e.target.closest && e.target.closest('.faq-q');
    if (!q) return;
    e.preventDefault();
    q.click();
  });
})();

/* 4. Area switch. Three columns — attribute, Pacific Beach, one alternative — and the third
   column's header holds a native <select> that decides which alternative is shown, by toggling
   is-off on the cells carrying each area's data-area.

   The <option>s carry no value attribute, so select.value returns the OPTION LABEL
   ("Downtown / Gaslamp") while the cells are keyed by slug ("downtown"). Matching on
   select.value therefore hides EVERY alternative cell and blanks the column. Resolve the key by
   selectedIndex against the data-area values in document order instead, which needs no attribute
   on the markup and cannot drift from the option labels. */
(function () {
  if (window.__celPbCompare) return;
  window.__celPbCompare = true;
  var sel = document.getElementById('compareArea');
  if (!sel) return;
  var cells = [].slice.call(document.querySelectorAll('.compare-cell.is-alt'));
  if (!cells.length) return;

  var keys = [];
  cells.forEach(function (c) {
    var k = c.getAttribute('data-area');
    if (k && keys.indexOf(k) === -1) keys.push(k);
  });
  if (!keys.length) return;

  function keyFor() {
    var v = sel.value;
    if (keys.indexOf(v) !== -1) return v;            // honour explicit option values if added later
    return keys[Math.min(sel.selectedIndex, keys.length - 1)] || keys[0];
  }
  function apply() {
    var key = keyFor();
    cells.forEach(function (c) {
      c.classList.toggle('is-off', c.getAttribute('data-area') !== key);
    });
  }
  sel.addEventListener('change', apply);
  apply();
})();
