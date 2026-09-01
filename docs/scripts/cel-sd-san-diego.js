/*!
 * CEL — /san-diego-ca/language-school page bundle
 * Course chooser from the Claude Design source; TOC spy, FAQ accordion and the w--current
 * cleanup follow the same contracts as the other San Diego pages.
 * Deployed minified as cel-sd-san-diego.min.js — see tools/cel-page-scripts/build.sh
 */

/* 1. Webflow w--current cleanup on same-page anchors. */
(function () {
  if (window.__celSdCurrent) return;
  window.__celSdCurrent = true;
  function clean() {
    document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current')
      .forEach(function (e) { e.classList.remove('w--current'); });
  }
  setInterval(clean, 300);
  clean();
})();

/* 2. Course chooser (verbatim from the design source, wrapped with a guard flag). */
(function () {
  if (window.__celSdChooser) return;
  window.__celSdChooser = true;
  var root = document.querySelector('#courses .chooser_component');
  if (!root) return;
  var goals = [].slice.call(root.querySelectorAll('.chooser_goal'));
  var cards = [].slice.call(root.querySelectorAll('.chooser_card'));
  if (!goals.length || !cards.length) return;
  var current = 0;

  function select(i, moveFocus){
    current = (i + goals.length) % goals.length;
    var course = goals[current].getAttribute('data-course');
    goals.forEach(function(x, n){
      var on = n === current;
      x.classList.toggle('is-active', on);
      x.setAttribute('aria-selected', on ? 'true' : 'false');
      x.setAttribute('tabindex', on ? '0' : '-1');
    });
    cards.forEach(function(c){ c.classList.toggle('is-active', c.getAttribute('data-course') === course); });
    if (moveFocus) goals[current].focus();
  }

  goals.forEach(function(g, i){
    g.addEventListener('click', function(e){ e.preventDefault(); select(i); });
    g.addEventListener('keydown', function(e){
      var k = e.key;
      if (k === 'ArrowDown' || k === 'ArrowRight'){ e.preventDefault(); select(current + 1, true); }
      else if (k === 'ArrowUp' || k === 'ArrowLeft'){ e.preventDefault(); select(current - 1, true); }
      else if (k === 'Home'){ e.preventDefault(); select(0, true); }
      else if (k === 'End'){ e.preventDefault(); select(goals.length - 1, true); }
    });
  });

  select(0);
})();
/* 3. TOC scroll-spy. */
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

/* 4. FAQ accordion — single-open, maxHeight animation, aria-expanded.
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
