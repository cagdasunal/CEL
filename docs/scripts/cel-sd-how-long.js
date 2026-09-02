/*!
 * CEL — /san-diego-ca/how-long-to-learn-english page bundle
 * Source of truth: sites/cel/claude-design-export/project/pages/san-diego/
 *   how-long.html
 * Deployed minified as cel-sd-how-long.min.js — see tools/cel-page-scripts/build.sh
 *
 * Created 2026-09-02. This page shipped with NO page bundle at all — only the
 * site-wide cookie-consent / events / offers / whatsapp tags. Measured on the
 * live page that day: all 13 .faq-item blocks were inert (clicking a question
 * left .faq-body at max-height:0px and aria-expanded=false) and the TOC rail sat
 * at opacity:0 for the whole page on mobile, because nothing set is-visible.
 *
 * Every block below is the same code the neighbouring San Diego bundles run —
 * copied from cel-sd-pacific-beach.js, not rewritten — so this page picks up the
 * shared behaviour rather than a second implementation of it. The only edit is
 * the w--current guard flag, which must be per-page.
 */

/* 1. Webflow stamps w--current on any same-page anchor, and .hero_cta-ghost.w--current
   forces color:var(--cream-soft). All live page bundles ship this identical cleanup. */
(function () {
  if (window.__celHlCurrent) return;
  window.__celHlCurrent = true;
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
    /* The deploy added href="#" to these triggers, which the comment above says they
       must not have. It is inert today only because Webflow's own a[href^="#"] handler
       cancels it — a third-party handler this bundle does not control. Cancel it here so
       the accordion does not depend on that, and so a click cannot push "#" onto history. */
    if (q.tagName === 'A' && (q.getAttribute('href') || '') === '#') e.preventDefault();
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

/* 4. Mobile TOC drawer (<=991px) — celtocmob3 v2.0.0, the same block the
   Vancouver-family bundles carry. Replaces celtocmob2 v1.0.0, which put `is-menu-open` on
   .stoc_component. No stylesheet has ever defined
   `.stoc_component.is-menu-open`; the rules are `.stoc_label.is-menu-open`
   and `.stoc_nav.is-menu-open`, so tapping the pill did nothing on every
   page that shipped v1. Measured 2026-09-02 on
   /vancouver/cost-of-studying-english at 375px with transitions disabled:
   v1's class left .stoc_nav at visibility:hidden/opacity:0; label+nav gave
   visibility:visible/opacity:1.
   v1 also appended a `.stoc_backdrop` div that no stylesheet styles, so it
   had zero height and could never receive the outside click it existed for;
   a document-level listener replaces it.
   `is-visible` on .stoc_component is carried over unchanged — that half
   always worked. */
(function () {
  if (window.__celTocMob) return;
  window.__celTocMob = true;

  var comp = document.querySelector('.stoc_component');
  var label = document.querySelector('.stoc_label');
  var nav = document.querySelector('.stoc_nav');
  if (!comp || !label || !nav) return;

  var navbar = document.querySelector('.navbar_component');
  var hero = document.querySelector('.section_hero');
  var links = [].slice.call(document.querySelectorAll('.stoc_link[data-target]'));
  var sections = links.map(function (l) {
    return document.getElementById(l.dataset.target);
  }).filter(Boolean);
  var last = sections[sections.length - 1];
  var navH = navbar ? navbar.offsetHeight : 80;

  label.setAttribute('aria-expanded', 'false');

  function close() {
    label.classList.remove('is-menu-open');
    nav.classList.remove('is-menu-open');
    label.setAttribute('aria-expanded', 'false');
  }
  function open() {
    label.classList.add('is-menu-open');
    nav.classList.add('is-menu-open');
    label.setAttribute('aria-expanded', 'true');
  }
  function toggle() {
    if (label.classList.contains('is-menu-open')) close(); else open();
  }

  /* Offer the rail only between the end of the hero and the end of the last
     TOC target: above the hero it repeats the page title, past the last
     section it points at nothing. */
  function updateVisibility() {
    var heroBottom = hero ? hero.getBoundingClientRect().bottom : -1;
    var lastBottom = last ? last.getBoundingClientRect().bottom : Infinity;
    if (heroBottom < navH + 20 && lastBottom > navH + 40) {
      comp.classList.add('is-visible');
    } else {
      comp.classList.remove('is-visible');
      close();
    }
  }

  window.addEventListener('scroll', updateVisibility, { passive: true });
  window.addEventListener('resize', updateVisibility, { passive: true });
  updateVisibility();

  label.addEventListener('click', function (e) { e.preventDefault(); toggle(); });
  label.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
  });
  links.forEach(function (l) { l.addEventListener('click', close); });

  document.addEventListener('click', function (e) {
    if (!label.classList.contains('is-menu-open')) return;
    if (comp.contains(e.target)) return;
    close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
})();

/* Navbar-over-hero — the site-standard scroll behaviour (celnavtoc3 / __celNt).
   Present on vancouver, vs-toronto, cost-of-studying-english and
   how-long-to-learn-english since the original build; never ported to the five
   pages added in the 2026-09 San Diego + About round, even though
   rules/webflow-javascript.md §9 lists it as a standard script for EVERY page.

   What it does: the navbar ships a `transparent` variant whose background Webflow
   applies as an INLINE style. This keeps that inline background off while the hero
   is still under the navbar, and lets it return once the hero has scrolled past —
   so the bar reads as transparent over the hero and solid over the content.

   Two deliberate choices:
   - The hero selector covers `.section_hero` AND `.abouthero`. /about has no
     .section_hero at all, so a single-selector port would have silently no-opped
     there — the failure mode is invisible, which is why it is spelled out.
   - Guard is __celNavHero, and it also defers to __celNt. If the full celnavtoc3
     ever loads on these pages it does this job plus more, so this must stand down
     rather than claim its flag (rules/webflow-javascript.md §12). */
(function () {
  if (window.__celNt || window.__celNavHero) return;
  window.__celNavHero = true;

  const nav = document.querySelector('[data-wf--navbar--variant="transparent"]');
  const hero = document.querySelector('.section_hero, .abouthero');
  if (!nav || !hero) return;

  const OPTS = { attributes: true, attributeFilter: ['style'] };
  const overHero = function () { return hero.getBoundingClientRect().bottom > 80; };
  /* Re-observing after each write avoids reacting to our own mutation. */
  const clear = function () {
    mo.disconnect();
    nav.style.removeProperty('background-color');
    mo.observe(nav, OPTS);
  };
  const mo = new MutationObserver(function () { if (overHero()) clear(); });
  mo.observe(nav, OPTS);

  let queued = 0;
  window.addEventListener('scroll', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { if (overHero()) clear(); queued = 0; });
  }, { passive: true });

  if (overHero()) nav.style.removeProperty('background-color');
})();
