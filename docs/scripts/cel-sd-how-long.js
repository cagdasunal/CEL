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
  document.querySelectorAll('.faq-item').forEach(function (it) {
    if (it.dataset.faqOpen === 'true') return;
    var b = it.querySelector('.faq-body');
    if (b) b.inert = true;
  });
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
      /* RESPONSIVE REPAIR 2026-09-08: a collapsed answer is max-height:0 with
         visibility:visible, so its links stay in the tab order — measured 7 links
         focusable while clipped to zero height, which walks keyboard focus into
         nothing. `inert` removes the subtree from the tab order and the a11y tree
         without touching layout, so the max-height transition is unaffected. */
      if (body) { body.style.maxHeight = '0px'; body.inert = true; }
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
      if (body2) body2.inert = false;
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
  /* RESPONSIVE REPAIR 2026-09-08: max-height is written once, in pixels, from the
     answer's height at click time. Narrow the window afterwards and the answer
     reflows taller than that frozen number, so the tail is clipped for good — the
     user has to close and reopen the item. Re-measure the open item on resize. */
  var reQueued = 0;
  window.addEventListener('resize', function () {
    if (reQueued) return;
    reQueued = 1;
    requestAnimationFrame(function () {
      reQueued = 0;
      var open = document.querySelector('.faq-item[data-faq-open="true"]');
      if (!open) return;
      var body = open.querySelector('.faq-body');
      var inner = open.querySelector('.faq-body-inner');
      if (body && inner) body.style.maxHeight = inner.scrollHeight + 'px';
    });
  }, { passive: true });
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

  /* RESPONSIVE REPAIR 2026-09-08: the toggle is a <p>, so it could never receive
     focus and the keydown handler below could never fire — the whole TOC drawer,
     and with it the page's 10 section links, were keyboard-dead at <=991px.
     Measured before: document.querySelector('.stoc_label').tabIndex === -1 at
     320 / 375 / 768 / 991. */
  if (!label.hasAttribute('tabindex')) label.setAttribute('tabindex', '0');
  if (!label.hasAttribute('role')) label.setAttribute('role', 'button');
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

/* RESPONSIVE REPAIR 2026-09-08 — keyboard-reachable horizontal scrollers.
   The four .feetable data tables keep a deliberate 600px floor at <=479px, which
   makes them horizontal scroll containers. A scroll container with no focusable
   descendant and no tabindex cannot be reached or scrolled from the keyboard, so
   up to 319px of every table was unreachable without a pointer (measured at 320:
   clientWidth 273 vs scrollWidth 600). Marking only the boxes that ACTUALLY
   overflow keeps the tab order clean at the widths where they fit — the CSS above
   makes them fit from 480px up, so on desktop this adds no tab stops at all.
   Re-evaluated on resize because the same element flips between the two states. */
(function () {
  if (window.__celScrollA11y) return;
  window.__celScrollA11y = true;
  var boxes = [].slice.call(document.querySelectorAll('.feetable, .compare-table'));
  if (!boxes.length) return;
  function label(box) {
    var head = box.querySelector('.feetable_headcell, .compare-duration');
    var txt = head ? (head.textContent || '').trim() : '';
    return txt ? 'Table: ' + txt + ' — scrollable' : 'Scrollable table';
  }
  function sync() {
    boxes.forEach(function (box) {
      var scrolls = box.scrollWidth > box.clientWidth + 1;
      if (scrolls) {
        if (box.getAttribute('tabindex') !== '0') {
          box.setAttribute('tabindex', '0');
          box.setAttribute('role', 'region');
          box.setAttribute('aria-label', label(box));
        }
      } else if (box.getAttribute('tabindex') === '0') {
        box.removeAttribute('tabindex');
        box.removeAttribute('role');
        box.removeAttribute('aria-label');
      }
    });
  }
  var queued = 0;
  window.addEventListener('resize', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { sync(); queued = 0; });
  }, { passive: true });
  sync();
  /* Fonts land after first paint and change scrollWidth, so re-measure once. */
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(sync);
})();


/* ── FAQ — collapsed answers must leave the tab order ────────────────────────
   The accordion collapses an answer with `max-height:0; overflow:hidden` and leaves
   `visibility:visible`, so every link inside a closed panel stays focusable and stays in the
   accessibility tree. Measured live 2026-09-08 on this page: 13 of 13 panels closed, 7 focusable links inside them.

   `inert` is used rather than `visibility:hidden` because `.faq-body` animates `max-height`;
   toggling visibility would either hide the text abruptly on close or force this file to restate
   Webflow's whole `transition` shorthand, which would then drift. `inert` touches no visual
   property at all.

   The open-state hook is `data-faq-open` on `.faq-item`, and it does NOT exist until the first
   interaction — so "absent" must read as closed, hence `!== 'true'` rather than `=== 'false'`. */
(function () {
  if (window.__hlFaqInertDone) return;
  window.__hlFaqInertDone = true;

  var items = [].slice.call(document.querySelectorAll('.faq-item'));
  if (!items.length) return;

  function sync(item) {
    var body = item.querySelector('.faq-body');
    if (!body) return;
    body.inert = item.getAttribute('data-faq-open') !== 'true';
  }

  items.forEach(function (item) {
    sync(item);
    new MutationObserver(function () { sync(item); })
      .observe(item, { attributes: true, attributeFilter: ['data-faq-open'] });
  });
})();

/* RESPONSIVE REPAIR 2026-09-08 — hero backdrop resolution on tall/narrow boxes.
   The hero image is `object-fit:cover` in a `min-height:100vh` box, but Webflow
   generates `sizes="(max-width:2560px) 100vw, 2560px"` — which describes the box's
   WIDTH only. Cover scales the source by max(boxW/srcW, boxH/srcH), so on a
   portrait viewport the height drives the scale and the width-derived candidate is
   far too small. Measured at 375x900 on a 16:9 source: the browser picks the 500w
   candidate (real file 500x281) and paints it at 3.2x, cropped to a 117px-wide
   strip of the original. The needed source is ~1600w.
   This computes the width cover actually needs, and only intervenes when the
   current pick is materially short — so it is a no-op at 1440 and 1920, where the
   width-derived candidate is already correct. It also promotes the LCP image out
   of `loading="lazy"`, which Webflow puts on every image including this one. */
(function () {
  if (window.__celHeroImg) return;
  window.__celHeroImg = true;
  var hero = document.querySelector('.section_hero, .abouthero');
  if (!hero) return;
  var img = hero.querySelector('img.hero_bg-image, img.abouthero_bg-image')
         || hero.querySelector('img');
  if (!img || !img.srcset) return;

  /* Real candidate widths, from the srcset itself — naturalWidth is
     density-corrected for a srcset image and cannot be compared against them. */
  var cands = img.srcset.split(',').map(function (c) {
    var m = c.trim().match(/(\S+)\s+(\d+)w$/);
    return m ? { url: m[1], w: +m[2] } : null;
  }).filter(Boolean).sort(function (a, b) { return a.w - b.w; });
  if (!cands.length) return;

  img.setAttribute('fetchpriority', 'high');
  if (img.getAttribute('loading') === 'lazy') img.setAttribute('loading', 'eager');

  function need() {
    var r = img.getBoundingClientRect();
    if (!r.width || !r.height) return 0;
    var aspect = img.naturalWidth && img.naturalHeight
      ? img.naturalWidth / img.naturalHeight : 16 / 9;   /* ratio survives density correction */
    var dpr = window.devicePixelRatio || 1;
    return Math.ceil(Math.max(r.width, r.height * aspect) * dpr);
  }

  function apply() {
    var w = need();
    if (!w) return;
    var r = img.getBoundingClientRect();
    /* Only when the cover crop needs materially more than the box width — i.e.
       exactly the portrait case Webflow's `sizes` cannot describe. */
    if (w < r.width * (window.devicePixelRatio || 1) * 1.15) return;
    /* 5% tolerance: a 1600w candidate for a 1608px need is a 0.5% shortfall no one
       can see, and the next step up is a 2000px JPEG on a phone. */
    var pick = cands.filter(function (c) { return c.w >= w * 0.95; })[0] || cands[cands.length - 1];
    var cur = (img.currentSrc || '').split('/').pop();
    var have = (cands.filter(function (c) { return c.url.split('/').pop() === cur; })[0] || {}).w || 0;
    if (have >= pick.w) return;                 /* already good enough */
    /* Write the CANDIDATE's width, not the raw need: `sizes:1608px` makes the
       browser reach past a 1600w file to a 2000w one for a 0.5% gain. */
    img.setAttribute('sizes', pick.w + 'px');
  }

  apply();
  if (img.complete) apply(); else img.addEventListener('load', apply, { once: true });
  var queued = 0;
  window.addEventListener('resize', function () {
    if (queued) return;
    queued = 1;
    requestAnimationFrame(function () { queued = 0; apply(); });
  }, { passive: true });
})();
