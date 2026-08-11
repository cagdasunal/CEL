/* @ds-bundle: {"format":4,"namespace":"CELDesignSystem_019dd9","components":[{"name":"Button","sourcePath":"components/Button/Button.jsx"},{"name":"TEAM","sourcePath":"pages/about/team-data.js"},{"name":"CHRIS_PHOTO","sourcePath":"pages/about/team-data.js"}],"sourceHashes":{"components/Button/Button.jsx":"d92c605d22a4","pages/about/team-data.js":"9d4d9d63be78","pages/cost-of-studying-english/scripts.js":"49c9820b4980","pages/how-long-to-learn-english/scripts.js":"c201701b3af1","pages/san-diego/calculator-sandiego-costs.js":"9e43c06fdcf7","pages/san-diego/calculator-sandiego.js":"8033cae1c912","pages/san-diego/costs.js":"0e3c3de03349","pages/san-diego/currency.js":"9aa7dd74a0ff","pages/vancouver/scripts.js":"b678ac7f4b3a","pages/vs-toronto/scripts.js":"49f06c7e25ae","sections/tweaks-panel.jsx":"57fac7f3caf9","shared/calculator.js":"8b1a130732d9","shared/swiper-init.js":"6ebd6aa1b2eb","shared/utils.js":"14ba2afed6ac","ui_kits/website/AccommodationCard.jsx":"2339ed98897d","ui_kits/website/BentoCampus.jsx":"44dce5b16dce","ui_kits/website/Comparison.jsx":"d845074db74c","ui_kits/website/Courses.jsx":"587d1922783a","ui_kits/website/FAQ.jsx":"f94d325cf6a3","ui_kits/website/Footer.jsx":"42bca2ea105c","ui_kits/website/Hero.jsx":"8e17d27288b5","ui_kits/website/Nav.jsx":"54edbad4630b","ui_kits/website/Testimonials.jsx":"967dadcb91b1","ui_kits/website/ui.jsx":"00d443a84cbc"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.CELDesignSystem_019dd9 = window.CELDesignSystem_019dd9 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/Button/Button.jsx
try { (() => {
const buttonBase = {
  fontFamily: "var(--font-body, 'LibreFranklin', sans-serif)",
  fontSize: 14,
  fontWeight: 600,
  letterSpacing: "1px",
  textTransform: "uppercase",
  borderRadius: 1600,
  border: "none",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  gap: 10,
  textDecoration: "none",
  transition: "background-color 150ms ease, transform 150ms ease, border-color 150ms ease, color 150ms ease"
};
const buttonVariants = {
  primary: {
    ...buttonBase,
    padding: "14px 30px",
    background: "var(--orange-gold, #e78b10)",
    color: "var(--cream-extra-light, #f9f0df)"
  },
  ghost: {
    ...buttonBase,
    padding: "14px 30px",
    background: "transparent",
    color: "var(--cream-soft, #f9f1df)",
    border: "1.5px solid rgba(249, 240, 223, 0.30)"
  },
  link: {
    ...buttonBase,
    padding: "14px 0",
    background: "transparent",
    color: "var(--indigo-bright, #5d60ee)"
  }
};

/**
 * CEL CTA button — primary (orange fill), ghost (outline on dark/photo), or link (inline + arrow).
 * LibreFranklin 600, uppercase, full-pill. Never invent a third fill style.
 */
function Button({
  variant = "primary",
  href,
  onClick,
  children
}) {
  const style = buttonVariants[variant] || buttonVariants.primary;
  const arrow = variant === "link" ? React.createElement("svg", {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true"
  }, React.createElement("path", {
    d: "M5 12h14"
  }), React.createElement("path", {
    d: "M13 5l7 7-7 7"
  })) : null;
  const Tag = href ? "a" : "button";
  return React.createElement(Tag, {
    style,
    href,
    onClick
  }, children, arrow);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/Button/Button.jsx", error: String((e && e.message) || e) }); }

// pages/about/team-data.js
try { (() => {
// CEL team — photos from the live site CMS. Categories: management / admission / teachers.
// Each person keeps their original role label as the card eyebrow.
// imgId pairs with the <meta name="ext-resource-dependency"> list in about.dc.html: these URLs live
// in JS, which a bundler cannot discover by reading markup, so publishing needs the meta tags and
// the page prefers window.__resources[imgId] when one exists.
const TEAM = [{
  name: 'Chris',
  role: 'CEO',
  cat: 'management',
  imgId: 'team01',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/667453c576e8d35c454cce88_Chris.avif',
  alt: 'Portrait of Chris, CEO and Managing Partner at CEL'
}, {
  name: 'Patrick',
  role: 'CEO',
  cat: 'management',
  imgId: 'team02',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/667453c576e8d35c454ccf32_Patrick.avif',
  alt: 'Portrait of Patrick, CEO at CEL'
}, {
  name: 'Laura',
  role: 'Vancouver Director',
  cat: 'management',
  imgId: 'team03',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed0e0f4fc42c943ce9b1_6a1eed0c94eca433de255a53_laura-1-Laura%252520profile%252520picture(3.4m.avif',
  alt: 'Portrait of Laura, Vancouver Director at CEL'
}, {
  name: 'Aaron',
  role: 'Education',
  cat: 'management',
  imgId: 'team04',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed3364ff1c263c50f854_6a1eed31eab018f34a6b3370_aaron-1-Aaron.avif',
  alt: 'Portrait of Aaron, Education team at CEL'
}, {
  name: 'Corinne',
  role: 'Education',
  cat: 'management',
  imgId: 'team05',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed0a409372b5e98954bd_6a1eed08eab018f34a6b2881_corinne-1-Corrine%252520profile%252520picture(3..avif',
  alt: 'Portrait of Corinne, Education team at CEL'
}, {
  name: 'Max',
  role: 'Marketing',
  cat: 'management',
  imgId: 'team06',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed597079a56e29d971bc_6a1eed57fb1b4aa8e954a244_max-1-Max.avif',
  alt: 'Portrait of Max, Marketing at CEL'
}, {
  name: 'Eva',
  role: 'Housing & Admissions',
  cat: 'admission',
  imgId: 'team07',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed130f4fc42c943ced2f_6a1eed110f4fc42c943ceb72_eva-1-Eva%252520profile%252520picture(4.0mb).avif',
  alt: 'Portrait of Eva, Housing and Admissions at CEL'
}, {
  name: 'Kim',
  role: 'Housing & Admissions',
  cat: 'admission',
  imgId: 'team08',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed4835298475e04e0d0f_6a1eed460a2d5ca1f77381d6_kim-1-Kim.avif',
  alt: 'Portrait of Kim, Housing and Admissions at CEL'
}, {
  name: 'Marni',
  role: 'Housing & Admissions',
  cat: 'admission',
  imgId: 'team09',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed0618e79d493bfb14f5_6a1eed040f4fc42c943cdee3_marni-1-Marni%252520profile%252520picture(3.2m.avif',
  alt: 'Portrait of Marni, Housing and Admissions at CEL'
}, {
  name: 'George',
  role: 'Student Services',
  cat: 'admission',
  imgId: 'team10',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed4d7cbf2f66c45ed8d1_6a1eed4c5e7790b000a244e8_george-1-George.avif',
  alt: 'Portrait of George, Student Services at CEL'
}, {
  name: 'Soomeen',
  role: 'Student Services',
  cat: 'admission',
  imgId: 'team11',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed010f4fc42c943cdbae_6a1eecff7901bcb46ceb6a30_soomeen-1-Sumin%252520profile%252520picture(3.7m.avif',
  alt: 'Portrait of Soomeen, Student Services at CEL'
}, {
  name: 'Jenna',
  role: 'Student Services',
  cat: 'admission',
  imgId: 'team12',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed176184a9b38624374b_6a1eed16bedfa74434e00e28_jenna-1-Jenna%252520profile%252520picture(3.4m.avif',
  alt: 'Portrait of Jenna, Student Services at CEL'
}, {
  name: 'Renata',
  role: 'Sales',
  cat: 'admission',
  imgId: 'team13',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed5594eca433de2580e2_6a1eed5355fa03ef35336d94_renata-1-Renata.avif',
  alt: 'Portrait of Renata, Sales at CEL'
}, {
  name: 'Rosalia',
  role: 'Sales',
  cat: 'admission',
  imgId: 'team14',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed274a3fbd80abd46b1b_6a1eed2678ec3029cbf36d41_rosalia-1-1.avif',
  alt: 'Portrait of Rosalia, Sales at CEL'
}, {
  name: 'Kazu',
  role: 'CEL Japan',
  cat: 'admission',
  imgId: 'team15',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed1c78ec3029cbf36668_6a1eed190f4fc42c943cf254_kazu-1-Japanese%252520man%252520profile%252520pic.avif',
  alt: 'Portrait of Kazu, CEL Japan office'
}, {
  name: 'Kaori',
  role: 'CEL Japan',
  cat: 'admission',
  imgId: 'team16',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed204653e1b057e4a5da_6a1eed1e6184a9b386243ca0_kaori-1-Japanese%252520women(1)%252520profile%2525.avif',
  alt: 'Portrait of Kaori, CEL Japan office'
}, {
  name: 'Rei',
  role: 'CEL Japan',
  cat: 'admission',
  imgId: 'team17',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed2464ff1c263c50f269_6a1eed2235298475e04dee2c_rei-1-Japanese%252520women(2)%252520profile%2525.avif',
  alt: 'Portrait of Rei, CEL Japan office'
}, {
  name: 'Andrea',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team18',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed5118e79d493bfb4d73_6a1eed4f244816344cbc2b97_andrea-1-Andrea.avif',
  alt: 'Portrait of Andrea, Teacher at CEL'
}, {
  name: 'Andrew',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team19',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed40809ef916acd96c54_6a1eed3f78ec3029cbf37a05_andrew-1-Andrew.avif',
  alt: 'Portrait of Andrew, Teacher at CEL'
}, {
  name: 'Christina',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team20',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed2fd09434a8aa0d7e5d_6a1eed2d55fa03ef353358b4_christina-1-Christina.avif',
  alt: 'Portrait of Christina, Teacher at CEL'
}, {
  name: 'David',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team21',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed3609e7cc277658a3a9_6a1eed3535298475e04dfc75_david-1-David.avif',
  alt: 'Portrait of David, Teacher at CEL'
}, {
  name: 'Mitch',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team22',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed2beab018f34a6b322d_6a1eed2978ec3029cbf3705e_mitch-1-Mitch.avif',
  alt: 'Portrait of Mitch, Teacher at CEL'
}, {
  name: 'Lydia',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team23',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed3b18e79d493bfb4094_6a1eed387cbf2f66c45ed0be_lydia-1-Lydia.avif',
  alt: 'Portrait of Lydia, Teacher at CEL'
}, {
  name: 'Leigh',
  role: 'Teacher',
  cat: 'teachers',
  imgId: 'team24',
  img: 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/6a1eed447cbf2f66c45ed53f_6a1eed4235298475e04e04e4_lee-1-Lee.avif',
  alt: 'Portrait of Leigh, Teacher at CEL'
}];
const CHRIS_PHOTO = 'https://cdn.prod.website-files.com/667453c576e8d35c454cc9df/667453c576e8d35c454cce88_Chris.avif';
Object.assign(__ds_scope, { TEAM, CHRIS_PHOTO });
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/about/team-data.js", error: String((e && e.message) || e) }); }

// pages/cost-of-studying-english/scripts.js
try { (() => {
/* ═══════════════════════════════════════════════════════════
   CEL Vancouver — Costs Page Scripts
   v=5 | 2026-03-27
   ═══════════════════════════════════════════════════════════ */

/* ── Navbar scroll colour — REMOVED, now in shared/utils.js ──
   This file used to carry its own copy of initNavbarTransparent. So did
   pages/cost-of-studying-english/scripts.js. shared/utils.js carried a third. The San Diego pages
   load these two, so san-diego.html and costs.html got the local copies and
   how-long-to-learn-english.html got nothing at all — which is why the four pages disagreed about
   the top navigation. One implementation now, in shared/utils.js, loaded by every page. ── */

/* ── Swiper Slider init (accommodation only) ── */
(function () {
  if (window.__costsSw3 || window.__costsSliderLocal) return;
  window.__costsSliderLocal = true;
  function initSlider(swiperEl, navEl, opts) {
    if (typeof Swiper === 'undefined' || !swiperEl) return null;
    let sw = new Swiper(swiperEl, {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      grabCursor: true,
      freeMode: {
        enabled: true,
        sticky: false
      },
      breakpoints: opts.breakpoints || {}
    });
    let prevBtn = navEl ? navEl.querySelector('.card-slider_arrow.is-prev') : null;
    let nextBtn = navEl ? navEl.querySelector('.card-slider_arrow.is-next') : null;
    let fill = navEl ? navEl.querySelector('.card-slider_progress-fill') : null;
    if (!fill) fill = document.getElementById(opts.fillId || '');
    if (prevBtn) prevBtn.addEventListener('click', function () {
      sw.slidePrev();
    });
    if (nextBtn) nextBtn.addEventListener('click', function () {
      sw.slideNext();
    });
    function prog() {
      if (!fill) return;
      let p = Math.max(0, Math.min(1, isNaN(sw.progress) ? 0 : sw.progress));
      fill.style.width = p * 100 + '%';
    }
    sw.on('progress', prog);
    sw.on('slideChange', prog);
    prog();
    return sw;
  }
  function go() {
    if (typeof Swiper === 'undefined') return;
    // Accommodation slider
    let accomEl = document.getElementById('accomSlider');
    let accomNav = document.getElementById('accomSliderNav');
    initSlider(accomEl, accomNav, {
      slidesPerView: 'auto',
      spaceBetween: 16,
      breakpoints: {
        480: {
          spaceBetween: 16
        },
        768: {
          spaceBetween: 18
        },
        992: {
          spaceBetween: 20
        },
        1400: {
          spaceBetween: 22
        }
      }
    });

    // Living in Vancouver showcase slider
    let livingEl = document.getElementById('livingSlider');
    let livingNav = document.getElementById('livingSliderNav');
    initSlider(livingEl, livingNav, {
      slidesPerView: 'auto',
      spaceBetween: 16,
      speed: 800,
      breakpoints: {
        480: {
          spaceBetween: 16
        },
        768: {
          spaceBetween: 18
        },
        992: {
          spaceBetween: 20
        },
        1400: {
          spaceBetween: 22
        }
      }
    });
  }
  if (typeof Swiper !== 'undefined') {
    go();
    return;
  }
  let swiperScript = document.querySelector('script[src*="swiper"]');
  if (swiperScript) {
    swiperScript.addEventListener('load', go);
  } else {
    // Retry up to 20× every 100ms — avoids banned DOMContentLoaded on Webflow CDN
    let retries = 0;
    let timer = setInterval(function () {
      if (typeof Swiper !== 'undefined') {
        clearInterval(timer);
        go();
      } else if (++retries >= 20) clearInterval(timer);
    }, 100);
  }
})();

/* ── Price Bar Animation (IntersectionObserver + WAAPI) ── */
(function () {
  if (window.__costsPriceBarDone) return;
  window.__costsPriceBarDone = true;
  let table = document.querySelector('.price-table');
  if (!table) return;
  let animated = false;
  function animate() {
    if (animated) return;
    animated = true;
    let rows = table.querySelectorAll('.price-row[data-w]');
    rows.forEach(function (row, i) {
      let bar = row.querySelector('.price-bar');
      if (!bar) return;
      let w = parseFloat(row.dataset.w) || 0.08;
      // Cancel any existing WAAPI animations (IX2 locks)
      if (bar.getAnimations) bar.getAnimations().forEach(function (a) {
        a.cancel();
      });
      bar.animate([{
        transform: 'scaleX(0)'
      }, {
        transform: 'scaleX(' + w + ')'
      }], {
        delay: i * 90,
        duration: 900,
        easing: 'cubic-bezier(0.16,1,0.3,1)',
        fill: 'forwards'
      });
    });
  }
  if ('IntersectionObserver' in window) {
    let io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          animate();
          io.disconnect();
        }
      });
    }, {
      threshold: 0.2
    });
    io.observe(table);
  } else {
    animate();
  }
})();

/* ── TOC Desktop — Scroll Spy + Active Highlight ── */
(function () {
  if (window.__costsTocDone) return;
  window.__costsTocDone = true;
  let links = document.querySelectorAll('.stoc_link[data-target]');
  if (!links.length) return;
  let sections = [];
  links.forEach(function (link) {
    let id = link.getAttribute('data-target');
    let el = document.getElementById(id);
    if (el) sections.push({
      id: id,
      el: el,
      link: link
    });
  });
  sections.sort(function (a, b) {
    return a.el.offsetTop - b.el.offsetTop;
  });
  function updateActive() {
    let scrollY = window.scrollY + 160;
    let active = sections[0];
    for (let i = 0; i < sections.length; i++) {
      if (sections[i].el.getBoundingClientRect().top + window.scrollY <= scrollY) active = sections[i];
    }
    links.forEach(function (l) {
      l.classList.remove('is-active');
    });
    if (active) active.link.classList.add('is-active');
  }
  let ticking = false;
  window.addEventListener('scroll', function () {
    if (!ticking) {
      requestAnimationFrame(function () {
        updateActive();
        ticking = false;
      });
      ticking = true;
    }
  });
  updateActive();
})();

/* ── Budget Table Drag-to-Scroll ── */
(function () {
  if (window.__costsBudgetScrollDone) return;
  window.__costsBudgetScrollDone = true;
  let wrap = document.querySelector('.budget-wrap');
  if (!wrap) return;
  let outer = wrap.closest('.budget-scroll-outer');
  let isDragging = false;
  let startX = 0;
  let scrollLeft = 0;
  function updateFade() {
    if (!outer) return;
    let hasOverflow = wrap.scrollWidth > wrap.clientWidth + 4;
    outer.classList.toggle('has-overflow', hasOverflow);
    if (hasOverflow) {
      let atEnd = wrap.scrollLeft + wrap.clientWidth >= wrap.scrollWidth - 4;
      outer.classList.toggle('is-scrolled-end', atEnd);
    }
  }
  wrap.classList.add('is-scrollable');
  wrap.addEventListener('mousedown', function (e) {
    isDragging = true;
    wrap.classList.add('is-dragging');
    startX = e.pageX - wrap.offsetLeft;
    scrollLeft = wrap.scrollLeft;
    e.preventDefault();
  });
  document.addEventListener('mousemove', function (e) {
    if (!isDragging) return;
    let x = e.pageX - wrap.offsetLeft;
    wrap.scrollLeft = scrollLeft - (x - startX);
  });
  document.addEventListener('mouseup', function () {
    if (!isDragging) return;
    isDragging = false;
    wrap.classList.remove('is-dragging');
  });
  wrap.addEventListener('touchstart', function (e) {
    startX = e.touches[0].pageX - wrap.offsetLeft;
    scrollLeft = wrap.scrollLeft;
  }, {
    passive: true
  });
  wrap.addEventListener('touchmove', function (e) {
    let x = e.touches[0].pageX - wrap.offsetLeft;
    wrap.scrollLeft = scrollLeft - (x - startX);
  }, {
    passive: true
  });
  wrap.addEventListener('scroll', updateFade);
  window.addEventListener('resize', updateFade);
  updateFade();
})();

/* ── FAQ Accordion — capture phase to beat webflow.js IX2 ── */
(function () {
  if (window.__celFq || window.__costsFaq) return;
  window.__costsFaq = true;
  function cancelAnims() {
    document.querySelectorAll('.faq-body').forEach(function (b) {
      if (b.getAnimations) b.getAnimations().forEach(function (a) {
        a.cancel();
      });
    });
  }

  /* Capture phase (3rd arg: true) fires BEFORE IX2's bubbling handler.
     stopPropagation() prevents IX2 from seeing the click at all,
     eliminating the double-toggle that causes "opens then cancels". */
  document.addEventListener('click', function (e) {
    const q = e.target.closest('.faq-q');
    if (!q) return;
    e.stopPropagation();
    const item = q.closest('.faq-item');
    if (!item) return;
    const wasOpen = item.dataset.faqOpen === 'true';
    cancelAnims();

    // Close all
    document.querySelectorAll('.faq-item').forEach(function (it) {
      const bd = it.querySelector('.faq-body');
      const bt = it.querySelector('.faq-q');
      const ic = it.querySelector('.faq-icon');
      it.dataset.faqOpen = 'false';
      it.classList.remove('is-open');
      if (bt) {
        bt.classList.remove('is-open');
        bt.setAttribute('aria-expanded', 'false');
      }
      if (ic) ic.classList.remove('is-open');
      if (bd) bd.style.maxHeight = '0px';
    });

    // Open clicked (if it was closed)
    if (!wasOpen) {
      const bd = item.querySelector('.faq-body');
      const inner = item.querySelector('.faq-body-inner');
      const bt = item.querySelector('.faq-q');
      const ic = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'true';
      item.classList.add('is-open');
      if (bt) {
        bt.classList.add('is-open');
        bt.setAttribute('aria-expanded', 'true');
      }
      if (ic) ic.classList.add('is-open');
      if (bd && inner) bd.style.maxHeight = inner.scrollHeight + 'px';
    }
  }, true);
})();

/* ── TOC Mobile — Floating Tab ── */
(function () {
  if (window.__costsTocMobileDone) return;
  window.__costsTocMobileDone = true;
  let sidebar = document.getElementById('tocSidebar');
  let label = document.querySelector('.stoc_label');
  if (!sidebar || !label) return;
  let navH = 0;
  let nav = document.querySelector('[data-w-id]');
  if (nav) navH = nav.offsetHeight || 80;
  function update() {
    if (window.innerWidth > 991) {
      sidebar.classList.remove('is-visible');
      sidebar.classList.remove('is-menu-open');
      sidebar.style.top = '';
      label.style.top = '';
      return;
    }
    sidebar.classList.add('is-visible');
    sidebar.style.top = navH + 14 + 'px';
    label.style.top = navH + 14 + 'px';
  }
  label.addEventListener('click', function () {
    sidebar.classList.toggle('is-menu-open');
  });
  document.addEventListener('click', function (e) {
    if (window.innerWidth > 991) return;
    if (!e.target.closest('.stoc_component') && !e.target.closest('.stoc_label')) {
      sidebar.classList.remove('is-menu-open');
    }
  });
  window.addEventListener('resize', update);
  update();
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/cost-of-studying-english/scripts.js", error: String((e && e.message) || e) }); }

// pages/how-long-to-learn-english/scripts.js
try { (() => {
/* ============================================================
   CEL Vancouver — Page Interactions
   Sidebar TOC + mobile floating pill + FAQ accordion
   ============================================================
   SVG icons are now standalone .svg files in this page directory.
   See: how-long-to-study-icon-*.svg
   data-svg attributes in HTML are kept for reference.
   ============================================================
   CDN guard reference (rules/webflow-javascript.md §12):
     window.__celNt — celnavtoc3 (navbar transparent + TOC dot polling)
     window.__celFq — celfaq1    (FAQ accordion — no local handler on this page,
                                   but referenced here so system_inspector knows
                                   the page intentionally delegates to the CDN)
   ============================================================ */

/* ── Navbar scroll colour (local dev only — production uses celnavtoc3 + IX2)
   Over hero  → remove inline style → CSS transparent variant wins
   Past hero  → set inline indigo   → overrides CSS transparent variant ── */
(function () {
  // CDN guard: celnavtoc3 handles this on Webflow. Skip if loaded.
  if (window.__celNt || window.__dgNavLocal) return;
  window.__dgNavLocal = true;
  const nav = document.querySelector('[data-wf--navbar--variant="transparent"]');
  const hero = document.querySelector('.section_hero');
  if (!nav || !hero) return;
  function check() {
    if (hero.getBoundingClientRect().bottom > 80) {
      nav.style.removeProperty('background-color');
    } else {
      nav.style.backgroundColor = 'rgb(93, 96, 238)';
    }
  }
  check();
  let raf = false;
  window.addEventListener('scroll', function () {
    if (raf) return;
    raf = true;
    requestAnimationFrame(function () {
      check();
      raf = false;
    });
  }, {
    passive: true
  });
})();
(function () {
  if (window.__dgPageDone) return;
  window.__dgPageDone = true;

  /* ----------------------------------------------------------
     SIDEBAR TOC — scroll-position tracking, single source of truth
      Root cause of the previous w--current conflict:
     Webflow adds/maintains w--current on <a href="#id"> links
     whose hash matches the current URL. Fix: remove the href
     attribute so Webflow never considers these links for
     w--current tracking. Keyboard accessibility is restored
     manually via tabindex + keydown handler.
  ---------------------------------------------------------- */
  const tocLinks = document.querySelectorAll('.stoc_link[data-target]');
  const sectIds = [...tocLinks].map(l => l.dataset.target);
  const sections = sectIds.map(id => document.getElementById(id)).filter(Boolean);
  const nav = document.querySelector('.navbar_component');
  if (sections.length && tocLinks.length) {
    // Mobile pill references
    const stocComponent = document.querySelector('.stoc_component');
    const stocLabel = document.querySelector('.stoc_label');

    // 1. Detach Webflow's hash-tracking by removing href.
    //    Add tabindex + role so links remain keyboard-accessible.
    tocLinks.forEach(function (l) {
      l.removeAttribute('href');
      l.setAttribute('tabindex', '0');
      l.setAttribute('role', 'link');
      // Hover: toggle is-hover on children so Webflow combo classes work
      l.addEventListener('mouseenter', function () {
        const dot = l.querySelector('.stoc_dot');
        const text = l.querySelector('.stoc_text');
        if (dot) dot.classList.add('is-hover');
        if (text) text.classList.add('is-hover');
      });
      l.addEventListener('mouseleave', function () {
        const dot = l.querySelector('.stoc_dot');
        const text = l.querySelector('.stoc_text');
        if (dot) dot.classList.remove('is-hover');
        if (text) text.classList.remove('is-hover');
      });
    });

    // 2. Single setter — is-active on link + dot + text children.
    //    Updates mobile tab label with current section name.
    function setActive(id) {
      tocLinks.forEach(function (l) {
        const isActive = l.dataset.target === id;
        l.classList.toggle('is-active', isActive);
        const dot = l.querySelector('.stoc_dot');
        if (dot) dot.classList.toggle('is-active', isActive);
        const text = l.querySelector('.stoc_text');
        if (text) text.classList.toggle('is-active', isActive);
      });
      if (stocLabel) {
        const active = [].slice.call(tocLinks).find(function (l) {
          return l.dataset.target === id;
        });
        if (active) {
          const textEl = active.querySelector('.stoc_text');
          stocLabel.textContent = textEl ? textEl.textContent.trim() : active.textContent.trim();
        }
      }
    }

    // 3. Scroll-position detector: "active" = last section whose
    //    top edge has crossed the reading line (navbar + 40px)
    function detectActive() {
      const readingLine = (nav ? nav.offsetHeight : 90) + 40;
      let activeId = sections[0].id;
      sections.forEach(sec => {
        if (sec.getBoundingClientRect().top <= readingLine) activeId = sec.id;
      });
      setActive(activeId);
    }

    // 4. Scroll listener — rAF-throttled, passive
    let rafPending = false;
    window.addEventListener('scroll', () => {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        detectActive();
        rafPending = false;
      });
    }, {
      passive: true
    });

    // 5. Click + keyboard: instant active + smooth scroll
    function scrollToSection(link) {
      const target = document.getElementById(link.dataset.target);
      if (!target) return;
      setActive(link.dataset.target);
      const navH = nav ? nav.offsetHeight : 90;
      const y = target.getBoundingClientRect().top + window.scrollY - navH - 24;
      window.scrollTo({
        top: y,
        behavior: 'smooth'
      });
    }
    tocLinks.forEach(link => {
      link.addEventListener('click', e => {
        e.preventDefault();
        scrollToSection(link);
        closeMenu(); // Close mobile menu on selection
      });
      link.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          scrollToSection(link);
          closeMenu();
        }
      });
    });

    // 6. Set initial state
    const hash = location.hash.replace('#', '');
    if (hash && sectIds.includes(hash)) {
      setActive(hash);
    } else {
      detectActive();
    }

    // 7. Mobile TOC — sticky tab below navbar, toggle menu, show/hide on scroll
    let backdrop = null;
    const heroSection = document.querySelector('.section_hero');
    function closeMenu() {
      if (!stocComponent) return;
      stocComponent.classList.remove('is-menu-open');
      if (backdrop) backdrop.classList.remove('is-visible');
    }
    if (stocComponent && stocLabel) {
      // Position below navbar with breathing room
      const navH = nav ? nav.offsetHeight : 80;
      stocComponent.style.top = navH + 14 + 'px';

      // Show/hide: visible only between hero bottom and last section bottom
      const lastSection = sections[sections.length - 1];
      function updateTabVisibility() {
        if (!heroSection) {
          stocComponent.classList.add('is-visible');
          return;
        }
        const heroBottom = heroSection.getBoundingClientRect().bottom;
        const lastBottom = lastSection ? lastSection.getBoundingClientRect().bottom : Infinity;
        if (heroBottom < navH + 20 && lastBottom > navH + 40) {
          stocComponent.classList.add('is-visible');
        } else {
          stocComponent.classList.remove('is-visible');
          closeMenu();
        }
      }
      window.addEventListener('scroll', updateTabVisibility, {
        passive: true
      });
      updateTabVisibility();

      // Create backdrop overlay (used on tablet/mobile)
      backdrop = document.createElement('div');
      backdrop.className = 'stoc_backdrop';
      document.body.appendChild(backdrop);

      // Toggle menu on tab tap
      stocLabel.addEventListener('click', () => {
        const isOpen = stocComponent.classList.toggle('is-menu-open');
        backdrop.classList.toggle('is-visible', isOpen);
      });

      // Close on backdrop tap
      backdrop.addEventListener('click', closeMenu);

      // Close on Escape key
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeMenu();
      });
    }
  }

  /* ----------------------------------------------------------
     PATHWAY RAIL — size to span first-dot-center → last-dot-center
  ---------------------------------------------------------- */
  const pathwayRail = document.querySelector('.pathway-rail');
  const pathwayDots = document.querySelectorAll('.pathway-dot');
  if (pathwayRail && pathwayDots.length >= 2) {
    const mobileQuery = window.matchMedia('(max-width: 767px)');
    function sizeRail() {
      if (!mobileQuery.matches) {
        pathwayRail.style.height = ''; // desktop: clear inline style, let CSS handle horizontal rail
        return;
      }
      // Mobile: calculate vertical rail height from dot centers
      const first = pathwayDots[0].getBoundingClientRect();
      const last = pathwayDots[pathwayDots.length - 1].getBoundingClientRect();
      const firstCenter = first.top + first.height / 2;
      const lastCenter = last.top + last.height / 2;
      pathwayRail.style.height = lastCenter - firstCenter + 'px';
    }
    sizeRail();
    window.addEventListener('resize', sizeRail);
  }

  /* ----------------------------------------------------------
     CEFR BARS — animate when section enters view
  ---------------------------------------------------------- */
  const cefrSection = document.getElementById('cefr');
  const cefrRows = document.querySelectorAll('.cefr-row');
  if (cefrSection && cefrRows.length) {
    const barObserver = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) {
        cefrRows.forEach((row, i) => {
          setTimeout(() => row.classList.add('animate-bars'), i * 90);
        });
        barObserver.disconnect();
      }
    }, {
      threshold: 0.25
    });
    barObserver.observe(cefrSection);
  }

  /* ----------------------------------------------------------
     INLINE CTA — mount from shared utils (utils.js must load first)
  ---------------------------------------------------------- */
  if (typeof loadInlineCta === 'function') {
    loadInlineCta();
  }
})();

/* ── Compare table — drag-to-scroll ── */
(function () {
  if (window.__dgCompareDragDone) return;
  window.__dgCompareDragDone = true;
  const el = document.querySelector('.compare-table');
  if (!el) return;
  let isDown = false,
    startX,
    scrollL;
  el.addEventListener('mousedown', function (e) {
    if (el.scrollWidth <= el.clientWidth) return;
    isDown = true;
    el.classList.add('is-dragging');
    startX = e.pageX - el.offsetLeft;
    scrollL = el.scrollLeft;
  });
  el.addEventListener('mouseleave', function () {
    isDown = false;
    el.classList.remove('is-dragging');
  });
  el.addEventListener('mouseup', function () {
    isDown = false;
    el.classList.remove('is-dragging');
  });
  el.addEventListener('mousemove', function (e) {
    if (!isDown) return;
    e.preventDefault();
    el.scrollLeft = scrollL - (e.pageX - el.offsetLeft - startX);
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/how-long-to-learn-english/scripts.js", error: String((e && e.message) || e) }); }

// pages/san-diego/calculator-sandiego-costs.js
try { (() => {
/* ═══════════════════════════════════════════════════════════════════════════
   CEL San Diego — calculator-sandiego-costs.js
   The §4 cost calculator on pages/san-diego/costs.html.
   Engine: shared/calculator.js (load that FIRST — see its header for the API).

   This file is ONLY rates + arithmetic + copy. No DOM, no events, no styling:
   the engine reads the data-calc-* hooks in the markup and writes the results.

   EVERY figure below is published on the page itself (copy SSOT
   pages/san-diego/costs.md §4/§6/§7/§9). Nothing is interpolated — where the
   copy does not publish a short-stay housing rate per residence, the nearest
   PUBLISHED bracket is used and the total is labelled "from" in the markup, with
   the note telling the reader the written quote confirms it. Never invent a
   figure here (DESIGN-RULES.md §1: "never widen or trim a figure").

   MAINTENANCE: when a rate changes, change it here and in costs.md together.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  /* ── published rates ──────────────────────────────────────────────────────
     Tuition US$/week by duration bracket, as [[maxWeeks, rate], …] (§6 tiers).
     GE24 also prices GE23 — §6: "priced the same as General English 24". */
  var COURSE_NAME = {
    ge20: 'General English 20',
    ge24: 'General English 24 / GE23'
  };
  var TUITION = {
    ge20: [[6, 370], [12, 360], [19, 340], [999, 300]],
    ge24: [[6, 410], [12, 400], [19, 380], [29, 340], [999, 320]]
  };

  /* Accommodation US$/week by bracket + the one-time placement fee (§4, §7). */
  var ROOMS = {
    std: {
      label: 'Shared apt Standard',
      fee: 100,
      tiers: [[11, 290], [23, 280], [999, 270]]
    },
    prm: {
      label: 'Shared apt Premium',
      fee: 100,
      tiers: [[23, 350], [999, 320]]
    },
    sup: {
      label: 'Shared apt Superior',
      fee: 100,
      tiers: [[23, 400], [999, 380]]
    },
    hss: {
      label: 'Homestay single',
      fee: 200,
      tiers: [[999, 320]]
    },
    hsd: {
      label: 'Homestay double',
      fee: 200,
      tiers: [[999, 290]]
    },
    hpr: {
      label: 'Premium homestay',
      fee: 200,
      tiers: [[999, 420]]
    },
    none: {
      label: 'Own accommodation',
      fee: 0,
      tiers: [[999, 0]]
    }
  };

  /* Resolve a flag from the DOM first: the currency menu ships one <img> per currency, so those
     bytes survive bundling. Falls back to the CDN URL when the menu is absent. */
  function flagSrc(cc, size) {
    var sel = 'img[src*="' + size + '/' + cc + '.png"], img[srcset*="' + size + '/' + cc + '.png"]';
    var el = document.querySelector(sel);
    if (el) {
      var attr = size === 'w80' ? el.getAttribute('srcset') || '' : '';
      if (attr) return attr.split(' ')[0];
      if (size === 'w40') return el.getAttribute('src');
    }
    return 'https://flagcdn.com/' + size + '/' + cc + '.png';
  }

  /* flagcdn country code per currency — real flag artwork, never a hand-drawn SVG */
  var FLAG = {
    AED: 'ae',
    ARS: 'ar',
    AUD: 'au',
    BRL: 'br',
    CAD: 'ca',
    CHF: 'ch',
    CLP: 'cl',
    CNY: 'cn',
    COP: 'co',
    CZK: 'cz',
    DKK: 'dk',
    EGP: 'eg',
    EUR: 'eu',
    GBP: 'gb',
    HKD: 'hk',
    HUF: 'hu',
    IDR: 'id',
    ILS: 'il',
    INR: 'in',
    JPY: 'jp',
    KRW: 'kr',
    KWD: 'kw',
    MAD: 'ma',
    MXN: 'mx',
    MYR: 'my',
    NOK: 'no',
    NZD: 'nz',
    PEN: 'pe',
    PHP: 'ph',
    PLN: 'pl',
    QAR: 'qa',
    RON: 'ro',
    RUB: 'ru',
    SAR: 'sa',
    SEK: 'se',
    SGD: 'sg',
    THB: 'th',
    TRY: 'tr',
    TWD: 'tw',
    UAH: 'ua',
    USD: 'us',
    VND: 'vn',
    ZAR: 'za'
  };
  var REGISTRATION = 150; /* §4 · one-time */
  var MATERIALS = 10; /* §4 · per week */
  var INSURANCE_DAY = 4; /* §9 · US$4 per day through CEL */
  var ESTA = 40.27; /* §9 */
  var MRV = 185; /* §9 · visa application fee, F-1 and B1/B2 alike */
  var SEVIS = 350; /* §9 · F-1 only */
  var ESTA_WEEKS = 12; /* §6 · ESTA covers ~90 days */

  /* Why THIS route — one sentence per case, from §6 (course/stay rules) and §9 (fees). */
  var ROUTE_WHY = {
    f1: 'General English 24 is a full-time academic course, so it needs an F-1 student visa \u2014 that is also the route for stays past about 6 months.',
    esta: 'Up to about 12 weeks you can study on ESTA or a B1/B2 visitor visa; no student visa is needed.',
    b1b2: 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this length of stay assumes a B1/B2 visitor visa.'
  };
  var ROUTE_FEES = {
    f1: 'SEVIS I-901 US$350 + visa application (MRV) US$185',
    esta: 'ESTA US$40.27',
    b1b2: 'Visa application (MRV) US$185'
  };

  /* Visa route follows the course and the length of stay (§6 + §9). */
  function route(state) {
    if (state.course === 'ge24') {
      return {
        key: 'f1',
        chip: 'F-1 visa',
        label: 'SEVIS I-901 + visa application',
        cost: SEVIS + MRV
      };
    }
    if (state.weeks <= ESTA_WEEKS) {
      return {
        key: 'esta',
        chip: 'ESTA or B1/B2',
        label: 'ESTA travel authorization',
        cost: ESTA
      };
    }
    return {
      key: 'b1b2',
      chip: 'B1/B2 visa',
      label: 'Visa application (MRV)',
      cost: MRV
    };
  }

  /* One honest caveat at a time — never a stack of warnings. */
  function note(state) {
    if (state.weeks < 12 && state.room !== 'none' && ROOMS[state.room]) {
      return 'Stays under 12 weeks pay slightly higher weekly housing rates \u2014 your written quote confirms the exact figure.';
    }
    if (state.weeks > ESTA_WEEKS && state.course === 'ge20') {
      return 'Past about 12 weeks you are beyond ESTA\u2019s 90 days, so this budget assumes a B1/B2 visitor visa.';
    }
    return 'Standard-season rates. Flights, food outside homestay and personal spending are not included.';
  }
  var config = {
    root: 'calcTool',
    chipBase: 'calc_chip',
    state: {
      weeks: 12,
      course: 'ge20',
      room: 'std',
      insurance: false,
      visa: false,
      fx: 'USD'
    },
    compute: function (s, h) {
      var w = s.weeks;
      var weeks = h.plural(w, 'week', 'weeks');
      var tRate = h.bracket(TUITION[s.course], w);
      /* An unknown key renders NOTHING rather than silently borrowing Standard's rate —
         a tile without a published rate must not print another residence's figure. */
      var room = ROOMS[s.room] || ROOMS.none;
      var rRate = h.bracket(room.tiers, w);
      var hasRoom = s.room !== 'none' && !!ROOMS[s.room];
      var r = route(s);
      var tuition = w * tRate;
      var materials = w * MATERIALS;
      var housing = hasRoom ? w * rRate + room.fee : 0;
      var insurance = s.insurance ? w * 7 * INSURANCE_DAY : 0;
      var visa = s.visa ? r.cost : 0;
      var total = tuition + REGISTRATION + materials + housing + insurance + visa;

      /* The TOTAL itself is shown in the currency the reader picks. Rates come from the ONE
         table the §3 converter publishes (window.CELFxRates) — never a second copy here. With
         no rate source, or on US$, the figure stays in dollars and no rate line is printed;
         CEL bills in US$ either way, which the note says whenever a conversion is shown. */
      var fx = window.CELFxRates;
      var fxRate = s.fx && s.fx !== 'USD' && fx && fx.get ? fx.get(s.fx) : null;
      var totalValue = fxRate ? total * fxRate : total;
      /* The symbol is the select's own label, so the figure is the NUMBER only. */
      var totalAmount = Math.round(totalValue).toLocaleString('en-US');
      var fxNote = fxRate ? '1 US$ = ' + fxRate.toLocaleString(undefined, {
        maximumFractionDigits: 4
      }) + ' ' + s.fx + ' \u00b7 ' + ((fx.liveFor ? fx.liveFor(s.fx) : fx.live) ? 'live mid-market rate, ' : 'indicative rate, ') + fx.date + '. CEL bills in US$.' : '';
      var flagCode = FLAG[s.fx] || 'us';
      return {
        out: {
          fxNote: fxNote,
          fxCode: s.fx,
          /* PUBLISHING: prefer the flag already inlined in the currency menu's own markup — a URL
             built here is invisible to a bundler and unreachable from a published artifact. */
          fxFlag: flagSrc(flagCode, 'w40'),
          fxFlag2x: flagSrc(flagCode, 'w80'),
          weeks: w,
          weeksUnit: w === 1 ? 'week' : 'weeks',
          weeksAria: weeks,
          tuition: h.money(tuition),
          tuitionSub: weeks + ' \u00d7 ' + h.money(tRate),
          materials: h.money(materials),
          materialsSub: weeks + ' \u00d7 ' + h.money(MATERIALS),
          room: h.money(housing),
          roomSub: room.label + ' \u00b7 ' + h.money(rRate) + '/wk + ' + h.money(room.fee) + ' placement',
          insurance: h.money(insurance),
          insuranceSub: w * 7 + ' days \u00d7 ' + h.money(INSURANCE_DAY),
          visa: h.money(r.cost),
          visaSub: r.label,
          /* the tiles show what THIS length of stay costs per week, not a from-price */
          courseName: COURSE_NAME[s.course] || COURSE_NAME.ge20,
          courseRate: h.money(tRate) + '/wk',
          roomNote: hasRoom ? h.money(rRate) + '/wk + ' + h.money(room.fee) + ' placement fee' : 'No CEL accommodation in this budget',
          visaHint: r.cost === ESTA ? 'US$40.27' : h.money(r.cost),
          visaWhy: ROUTE_WHY[r.key],
          visaFees: ROUTE_FEES[r.key],
          totalAmount: totalAmount,
          /* "from" only qualifies the US$ figure; a converted one is already approximate */
          totalPrefix: fxRate ? '\u2248' : 'from',
          month: h.money(total / (w / 4.345)),
          note: note(s)
        },
        rows: {
          room: hasRoom,
          insurance: s.insurance,
          visa: s.visa
        },
        flags: {
          'is-over': w > ESTA_WEEKS && s.course === 'ge20',
          'is-esta-limit': s.course === 'ge20',
          /* the tick only means something on GE20 */
          'is-f1': r.key === 'f1',
          /* One root flag per route so the SLIDER can wear the verdict's colour (client, 4 Aug:
             "the progress bar color and the visa color should match"). The chip styles itself from
             its own class; the track sits in a different subtree, so it needs the state on the root. */
          'is-route-esta': r.key === 'esta',
          'is-route-b1b2': r.key === 'b1b2',
          'is-route-f1': r.key === 'f1'
        },
        /* One class per route, not two. b1b2 previously fell through to 'is-esta', so a visitor-visa
         verdict was painted as the visa-free one — the colour said "nothing extra needed" while the
         sentence beside it said the opposite. */
        chips: {
          visa: {
            class: 'is-' + r.key,
            text: r.chip
          }
        },
        fill: {
          weeks: (w - 1) / 35
        }
      };
    }
  };

  /* Mount now if the engine is loaded, otherwise queue — the engine flushes the
     queue when it evaluates, so script order can never break the page. */
  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);else {
    window.CELCalculator = window.CELCalculator || {
      __queue: []
    };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/san-diego/calculator-sandiego-costs.js", error: String((e && e.message) || e) }); }

// pages/san-diego/calculator-sandiego.js
try { (() => {
/* ═══════════════════════════════════════════════════════════════════════════
   CEL San Diego — calculator-sandiego.js
   The §16 study-budget & visa planner on pages/san-diego/san-diego.html.
   Engine: shared/calculator.js (load that FIRST — see its header for the API).

   Replaces the old §16 inline <script>. Same behaviour, same markup classes
   (plan_*), same numbers — the arithmetic and copy live here, the mechanics
   (tweened figures, slider fill, radio groups, verdict panels, chip pop, the
   one-click fixes) come from the shared engine.

   STARTING PRICES ONLY, as the section's callout states: courses from
   US$300/week, CEL housing from US$270/week. The full itemised calculation is
   the §4 calculator on /san-diego-ca/cost-of-studying-english.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  var COURSE = 300; /* US$/week, from-price (§16 callout) */
  var HOUSE = 270; /* US$/week, CEL housing from-price */
  var ESTA_WEEKS = 12; /* ESTA / visa-waiver caps at 90 days ≈ 12 weeks */
  var MAX_WEEKS = 52; /* matches the range input's max */

  var CHIP = {
    f1: {
      class: 'is-f1',
      text: 'F-1 Student Visa'
    },
    esta: {
      class: 'is-esta',
      text: 'ESTA \u2014 no visa needed'
    },
    cap: {
      class: 'is-cap',
      text: 'Over the 90-day limit'
    }
  };
  var config = {
    root: 'plan-tool',
    chipBase: 'plan_chip',
    state: {
      weeks: 12,
      pace: 'full',
      home: 'cel'
    },
    compute: function (s, h) {
      var w = s.weeks;
      var weeks = h.plural(w, 'week', 'weeks');
      var tuition = w * COURSE;
      var housing = s.home === 'cel' ? w * HOUSE : 0;

      /* 24+ lessons a week is full-time study → F-1 at any length. Part-time is
         visa-free up to the 90-day window, and over it the tool goes into the cap
         state, which offers the two one-click fixes in the markup. */
      var visa = s.pace === 'full' ? 'f1' : w > ESTA_WEEKS ? 'cap' : 'esta';
      return {
        out: {
          weeks: w,
          weeksUnit: w === 1 ? 'week' : 'weeks',
          weeksAria: weeks,
          tuition: h.number(tuition),
          tuitionMath: weeks + ' \u00d7 from US$' + COURSE,
          housing: h.number(housing),
          housingMath: housing ? weeks + ' \u00d7 from US$' + HOUSE : 'arranged by you',
          total: h.number(tuition + housing),
          capWeeks: w,
          visa: visa
        },
        rows: {
          housing: !!housing
        },
        flags: {
          'is-part': s.pace === 'part',
          'is-over': s.pace === 'part' && w > ESTA_WEEKS,
          /* One root flag per verdict so the SLIDER can wear the verdict's colour, exactly as the
             costs-page calculator does (client, 4 Aug: "update the coloring in the slider for
             san-diego.html ... it should use similar ux, styling and coloring"). The chip styles
             itself from its own class; the track is in another subtree and needs the state on the
             root. is-over stays — the one-click fixes and the scale still read it. */
          'is-route-esta': visa === 'esta',
          'is-route-f1': visa === 'f1',
          'is-route-cap': visa === 'cap'
        },
        chips: {
          visa: CHIP[visa]
        },
        fill: {
          weeks: (w - 1) / (MAX_WEEKS - 1)
        }
      };
    }
  };
  if (window.CELCalculator && window.CELCalculator.__engine) window.CELCalculator.mount(config);else {
    window.CELCalculator = window.CELCalculator || {
      __queue: []
    };
    (window.CELCalculator.__queue = window.CELCalculator.__queue || []).push(config);
  }
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/san-diego/calculator-sandiego.js", error: String((e && e.message) || e) }); }

// pages/san-diego/costs.js
try { (() => {
/* ═══════════════════════════════════════════════════════════
   CEL San Diego — costs page · page-scoped JS
   Loaded AFTER ../cost-of-studying-english/scripts.js.
   Convention matches that file: one IIFE per behaviour, one unique
   window guard flag, no DOMContentLoaded, no globals beyond the flag.

   DEPLOY: folds into the CEL page-script bundle under
   tools/cel-page-scripts/src/ and ships minified via /deploy-page-scripts.
   It does NOT become a Webflow inline script. Webflow's budget is 15
   scripts per page — this page needs one bundle slot, shared with
   currency.js.
   ═══════════════════════════════════════════════════════════ */

/* ── §3 card 4 — currency converter ──────────────────────────
   MOVED 3 Aug (client direction): the converter lives in its own file,
   pages/san-diego/currency.js, loaded just before this one. It shares no
   state with anything here — do not re-add it to this file.
   ── */

/* ── §6 price-table bars — D1 RESOLVED (handoff review) ──────
   The live VC page's ../cost-of-studying-english/scripts.js animates ONE table
   (document.querySelector('.price-table')), so Table 2 — General English 24 — shipped
   with flat bars. That file is the Vancouver page's and must never be edited, so the
   fix lives here: run the same scaleX reveal over EVERY .price-table on the page.
   · data-tier / data-w are already authored on all 9 rows (both tables), and Table 2's
     price-bar-wrap > price-bar markup was added in the same review — the JS had nothing
     to drive there before that
   · existing WAAPI animations are cancelled first, exactly as the VC file does, so a
     table the VC script already animated is re-driven rather than fighting an IX2 lock
   · a snap fallback writes the final transform if the animation never finishes (a
     document timeline that does not advance would otherwise leave an EMPTY track)
   · reveal is a passive rect check, not IntersectionObserver: when IO does not fire the
     bars would stay at scaleX(0) forever, i.e. permanently wrong (same reasoning as §11)
   · its own guard flag — never reuse __costsPriceBarDone, that is the VC script's
   ── */
(function () {
  if (window.__costsAllPriceBarsDone) return;
  window.__costsAllPriceBarsDone = true;
  var tables = document.querySelectorAll('.price-table');
  if (!tables.length) return;
  var pending = Array.prototype.slice.call(tables);
  function animate(table) {
    var rows = table.querySelectorAll('.price-row[data-w]');
    for (var i = 0; i < rows.length; i++) {
      var bar = rows[i].querySelector('.price-bar');
      if (!bar) continue;
      var w = parseFloat(rows[i].getAttribute('data-w')) || 0.08;
      if (bar.getAnimations) {
        var running = bar.getAnimations();
        for (var a = 0; a < running.length; a++) running[a].cancel();
      }
      var delay = i * 90;
      bar.animate([{
        transform: 'scaleX(0)'
      }, {
        transform: 'scaleX(' + w + ')'
      }], {
        delay: delay,
        duration: 900,
        easing: 'cubic-bezier(0.16,1,0.3,1)',
        fill: 'forwards'
      });
      /* Snap fallback. WAAPI with fill:forwards is correct, but a document timeline
         that never advances — throttled tab, a view that is not painting, a browser
         that drops the animation — would leave the bar at scaleX(0), i.e. a price row
         showing an EMPTY track rather than an un-animated one. Same doctrine as §11
         below: never let a decorative timing failure read as wrong data.
         The running animation must be CANCELLED first: an animation in flight lives in
         the animation cascade origin, which outranks inline style, so writing the
         transform while it is still running has no effect at all. */
      (function (el, width) {
        setTimeout(function () {
          var live = el.getAnimations ? el.getAnimations() : [];
          for (var n = 0; n < live.length; n++) {
            if (live[n].playState === 'finished') return; /* it ran — leave it alone */
          }
          for (var c = 0; c < live.length; c++) live[c].cancel();
          /* transitions are on the same frozen clock, so a transitioned snap would
             never arrive either — the fallback paints, it does not animate */
          el.style.transition = 'none';
          el.style.transform = 'scaleX(' + width + ')';
        }, delay + 1100);
      })(bar, w);
    }
  }
  function sweep() {
    var h = window.innerHeight || document.documentElement.clientHeight;
    for (var i = pending.length - 1; i >= 0; i--) {
      var r = pending[i].getBoundingClientRect();
      if (r.top < h * 0.85 && r.bottom > 0) {
        animate(pending[i]);
        pending.splice(i, 1);
      }
    }
    if (!pending.length) {
      window.removeEventListener('scroll', sweep);
      window.removeEventListener('resize', sweep);
    }
  }
  window.addEventListener('scroll', sweep, {
    passive: true
  });
  window.addEventListener('resize', sweep);
  sweep();
})();

/* ── §11 mobile sticky CTA bar — reveal after the hero ────────
   The bar is fixed to the viewport bottom, so at every width ≤991px it would sit
   directly on top of the hero's own .hero_actions row (the hero is full-fold, its
   CTAs live in the bottom ~75px). DESIGN-RULES.md §6.6: all hero content visible
   without scrolling. So the bar stays translated out of view until the hero CTA row
   has scrolled past, then slides in.

   Driven by a passive scroll listener, NOT an IntersectionObserver. IO is the site
   convention (see the TOC scroll-spy) but it is the wrong tool here: when IO does not
   fire — throttled rAF, a non-painting tab, a browser without it — the spy merely
   looks frozen, whereas this bar would never appear at all, silently killing the
   mobile CTA. A scrollY comparison always resolves. The handler is synchronous and
   state-guarded (see the note on apply), and above 991px the bar is display:none so
   the work is inert.

   `is-visible` is a runtime state and is added HERE, never authored in costs.html
   (CLASS-CONTRACT.md §1, corollary 2). The CSS lives in costs.css block B (B6).
   ── */
(function () {
  if (window.__costsStickyCtaDone) return;
  window.__costsStickyCtaDone = true;
  var bar = document.querySelector('.sticky-cta_bar');
  if (!bar) return;
  var anchor = document.querySelector('.hero_actions');
  /* Nothing to clear: show it and move on — the bar must never be the reason a CTA
     is unreachable. */
  if (!anchor) {
    bar.classList.add('is-visible');
    return;
  }
  var threshold = 0;
  var shown = false;
  function measure() {
    var top = 0;
    for (var el = anchor; el; el = el.offsetParent) top += el.offsetTop;
    threshold = top + anchor.offsetHeight;
  }

  /* Synchronous on purpose. A requestAnimationFrame-coalesced handler looks tidier but
     it is a correctness bug here: in a throttled or non-painting tab the frame never
     arrives, the "queued" latch never clears, and the bar is stuck for the rest of the
     page's life. Two reads plus a state-guarded classList write is cheaper than the
     latch it replaces. */
  function apply() {
    var y = window.pageYOffset || document.documentElement.scrollTop || 0;
    var next = y > threshold;
    if (next === shown) return;
    shown = next;
    bar.classList.toggle('is-visible', next);
  }
  measure();
  apply();
  window.addEventListener('scroll', apply, {
    passive: true
  });
  window.addEventListener('resize', function () {
    measure();
    apply();
  }, {
    passive: true
  });
})();

/* ── §2 TOC — close the mobile drawer after a jump ────────────
   ../cost-of-studying-english/scripts.js closes .is-menu-open only for clicks OUTSIDE
   .stoc_component, so tapping a link left the drawer open on top of the section it had
   just jumped to (it is position:fixed at ≤991px). Own guard flag; the VC script is
   never edited. Desktop is untouched — the drawer classes only exist ≤991px.
   ── */
(function () {
  if (window.__costsTocCloseOnJumpDone) return;
  window.__costsTocCloseOnJumpDone = true;
  var sidebar = document.getElementById('tocSidebar');
  if (!sidebar) return;
  sidebar.addEventListener('click', function (e) {
    var link = e.target.closest ? e.target.closest('.stoc_link') : null;
    if (!link) return;
    if (window.innerWidth > 991) return;
    sidebar.classList.remove('is-menu-open');
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/san-diego/costs.js", error: String((e && e.message) || e) }); }

// pages/san-diego/currency.js
try { (() => {
/* ═══════════════════════════════════════════════════════════
   CEL San Diego — currency.js · the §3 currency converter, standalone
   Page: pages/san-diego/costs.html (§3 "All Prices in USD" card).
   Loaded BEFORE costs.js; owns nothing else on the page and shares no state with
   it. Same conventions as costs.js: one IIFE, one unique window guard flag, no
   DOMContentLoaded, no globals beyond the flag.

   DEPLOY: folds into the CEL page-script bundle under tools/cel-page-scripts/src/
   and ships minified via /deploy-page-scripts — NOT a Webflow inline script. It
   shares this page's single bundle slot with costs.js, so no extra slot is used.
   ═══════════════════════════════════════════════════════════ */

/* ── FAST FIRST, THEN FRESH ───────────────────────────────────
   1. The baked table renders instantly — the converted figure is on screen in the
      first frame, with no request and no spinner, ever.
   2. Rates are then refreshed from the ECB (frankfurter.app: free, no key, CORS,
      one small JSON) and cached in localStorage for one hour, so at most ONE
      request per visitor per hour, and repeat views are instant from cache.
   3. The refresh only fires once the widget is in view, so a visitor who never
      reaches §3 makes no third-party call at all.
   4. If the fetch fails, is blocked, or times out (4s), the baked table simply
      stays and the note reads "indicative rate" instead of "live mid-market rate".
      The figure never disappears and there is no error state to design around.
   MAINTENANCE: refresh RATES + RATE_DATE together (source: ECB reference rates) so
   the offline path stays close to reality. The picker list is built from RATES, so
   a currency can never be offered without a rate behind it.
   ── */
(function () {
  if (window.__celFxDone) return;
  window.__celFxDone = true;

  /* Baked ECB reference rates, 1 US$ = X — the instant, offline path.
     Order here is the order in the picker: CEL's biggest markets first. */
  var RATE_DATE = '3 August 2026';
  var RATES = {
    AED: 3.6725,
    ARS: 1452,
    AUD: 1.518,
    BRL: 5.0675,
    CAD: 1.4028,
    CHF: 0.808,
    CLP: 942,
    CNY: 6.7526,
    COP: 3985,
    CZK: 21.3,
    DKK: 6.468,
    EGP: 48.5,
    EUR: 0.8669,
    GBP: 0.7424,
    HKD: 7.795,
    HUF: 345,
    IDR: 17977,
    ILS: 3.0511,
    INR: 95.34,
    JPY: 156.68,
    KRW: 1427.05,
    KWD: 0.3062,
    MAD: 9.15,
    MXN: 17.3207,
    MYR: 4.21,
    NOK: 10.24,
    NZD: 1.665,
    PEN: 3.63,
    PHP: 57.4,
    PLN: 3.7306,
    QAR: 3.64,
    RON: 4.315,
    RUB: 82,
    SAR: 3.75,
    SEK: 9.58,
    SGD: 1.285,
    THB: 33.335,
    TRY: 47.536,
    TWD: 31.2,
    UAH: 42.5,
    USD: 1,
    VND: 26100,
    ZAR: 17.6
  };

  /* Codes the ECB feed publishes. Everything else is a POPULAR market currency the ECB does
     not quote (Gulf, LATAM, RUB, TWD, UAH, VND): its baked rate is correct as of RATE_DATE and
     is labelled "indicative" per currency, so a refreshed ECB code never lends its "live" wording
     to one that was not refreshed. */
  var ECB = {
    AUD: 1,
    BRL: 1,
    CAD: 1,
    CHF: 1,
    CNY: 1,
    CZK: 1,
    DKK: 1,
    EUR: 1,
    GBP: 1,
    HKD: 1,
    HUF: 1,
    IDR: 1,
    ILS: 1,
    INR: 1,
    JPY: 1,
    KRW: 1,
    MXN: 1,
    MYR: 1,
    NOK: 1,
    NZD: 1,
    PHP: 1,
    PLN: 1,
    RON: 1,
    SEK: 1,
    SGD: 1,
    THB: 1,
    TRY: 1,
    ZAR: 1
  };
  var ENDPOINT = 'https://api.frankfurter.app/latest?from=USD';
  var CACHE_KEY = 'celFxUsd'; /* the only key this page writes */
  var TTL = 60 * 60 * 1000; /* one hour */
  var TIMEOUT = 4000;
  var amountEl = document.getElementById('fxAmount');
  var pickEl = document.getElementById('fxPick');
  var pickCodeEl = document.getElementById('fxPickCode');
  var pickFlagEl = document.getElementById('fxPickFlag');
  var menuEl = document.getElementById('fxMenu');
  var resultEl = document.getElementById('fxResult');
  var noteEl = document.getElementById('fxNote');
  var widgetEl = document.getElementById('fxWidget');
  if (!amountEl || !pickEl || !menuEl || !resultEl) return;
  var code = 'EUR';
  var rates = RATES;
  var rateDate = RATE_DATE;
  var isLive = false;
  var liveSet = {}; /* per-code: was THIS rate refreshed from the feed? */

  function setText(el, text) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(text));
  }
  function format(value, cur) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: cur,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      }).format(value);
    } catch (e) {
      return Math.round(value).toLocaleString() + ' ' + cur;
    }
  }
  function render() {
    var rate = rates[code] || RATES[code];
    var usd = parseFloat(amountEl.value);
    if (!rate) {
      setText(resultEl, '');
      return;
    }
    if (!isFinite(usd) || usd < 0) {
      setText(resultEl, '');
      setText(noteEl, 'Enter an amount in US dollars.');
      return;
    }
    setText(resultEl, format(usd * rate, code));
    setText(noteEl, '1 US$ = ' + rate.toLocaleString(undefined, {
      maximumFractionDigits: 4
    }) + ' ' + code + ' \u00b7 ' + (isLive && liveSet[code] ? 'live mid-market rate, ' : 'indicative rate, ') + rateDate + '. CEL bills in US$.');
  }
  function publish() {
    /* ONE rate source per page. The §4 calculator reads this instead of carrying its own
       copy of the table, so a rate can never disagree between the two tools. */
    window.CELFxRates = {
      date: rateDate,
      live: isLive,
      codes: Object.keys(RATES),
      liveFor: function (c) {
        return !!(isLive && liveSet[c]);
      },
      get: function (code) {
        return rates[code] || RATES[code] || null;
      }
    };
    var tool = document.getElementById('calcTool');
    if (tool && tool.__celCalc) tool.__celCalc.render();
  }
  function adopt(payload, live) {
    if (!payload || !payload.rates) return;
    var merged = {};
    for (var k in RATES) if (RATES.hasOwnProperty(k)) {
      if (payload.rates[k]) {
        merged[k] = payload.rates[k];
        liveSet[k] = true;
      } else {
        merged[k] = RATES[k];
      } /* never drop a listed currency */
    }
    rates = merged;
    rateDate = payload.date || rateDate;
    isLive = !!live;
    publish();
    render();
  }

  /* ── hourly cache (localStorage; this page writes ONLY celFxUsd) ── */
  function readCache() {
    try {
      var raw = window.localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var c = JSON.parse(raw);
      if (!c || !c.rates || !c.ts) return null;
      if (Date.now() - c.ts > TTL) return null;
      return c;
    } catch (e) {
      return null;
    }
  }
  function writeCache(payload) {
    try {
      window.localStorage.setItem(CACHE_KEY, JSON.stringify({
        rates: payload.rates,
        date: payload.date,
        ts: Date.now()
      }));
    } catch (e) {/* private mode / quota — the baked table still works */}
  }
  var refreshed = false;
  function refresh() {
    if (refreshed) return;
    refreshed = true;
    var cached = readCache();
    if (cached) {
      adopt(cached, true);
      return;
    } /* instant, no request */
    if (typeof fetch !== 'function') return;
    var settled = false;
    var timer = setTimeout(function () {
      settled = true;
    }, TIMEOUT);
    fetch(ENDPOINT, {
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store'
    }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (data) {
      clearTimeout(timer);
      if (settled || !data || !data.rates) return;
      adopt(data, true);
      writeCache(data);
    }).catch(function () {
      clearTimeout(timer); /* baked table stays */
    });
  }

  /* ── picker: one column, code + name, full keyboard control ── */
  function options() {
    return menuEl.querySelectorAll('.fx_option');
  }
  function setOpen(open) {
    menuEl.hidden = !open;
    pickEl.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      document.addEventListener('click', onDocClick, true);
    } else {
      document.removeEventListener('click', onDocClick, true);
    }
  }
  function onDocClick(ev) {
    if (menuEl.contains(ev.target) || pickEl.contains(ev.target)) return;
    setOpen(false);
  }
  function choose(btn) {
    if (!btn) return;
    code = btn.getAttribute('data-code');
    var all = options();
    for (var i = 0; i < all.length; i++) {
      var on = all[i] === btn;
      all[i].classList.toggle('is-active', on);
      all[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    setText(pickCodeEl, code);
    /* PUBLISHING: copy the option's OWN <img> rather than rebuilding a flagcdn URL. Every option
       already carries its flag in the markup, so a bundler has inlined those bytes; a URL built in
       JS is invisible to it and unreachable from a published artifact (no CDN fetches). The CDN
       build stays as the fallback for markup that ships an option without an image. */
    var srcImg = btn.querySelector('img');
    var cc = btn.getAttribute('data-flag');
    if (pickFlagEl && srcImg && srcImg.getAttribute('src')) {
      pickFlagEl.src = srcImg.getAttribute('src');
      var ss = srcImg.getAttribute('srcset');
      if (ss) pickFlagEl.srcset = ss;else pickFlagEl.removeAttribute('srcset');
    } else if (pickFlagEl && cc) {
      pickFlagEl.src = 'https://flagcdn.com/w40/' + cc + '.png';
      pickFlagEl.srcset = 'https://flagcdn.com/w80/' + cc + '.png 2x';
    }
    pickEl.setAttribute('aria-label', 'Change currency, currently ' + code);
    setOpen(false);
    pickEl.focus();
    render();
  }
  function focusActive() {
    var target = menuEl.querySelector('.fx_option.is-active') || options()[0];
    if (target) target.focus();
  }
  pickEl.addEventListener('click', function () {
    var open = pickEl.getAttribute('aria-expanded') === 'true';
    setOpen(!open);
    refresh();
    if (!open) focusActive();
  });
  menuEl.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.fx_option') : null;
    if (btn) choose(btn);
  });

  /* ↑/↓ walk the list, Enter picks, Escape closes, a letter jumps to that code */
  menuEl.addEventListener('keydown', function (ev) {
    var all = options();
    var i = Array.prototype.indexOf.call(all, document.activeElement);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      var next = ev.key === 'ArrowDown' ? i + 1 : i - 1;
      if (next < 0) next = all.length - 1;
      if (next >= all.length) next = 0;
      all[next].focus();
      return;
    }
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      choose(all[i]);
      return;
    }
    if (ev.key === 'Escape') {
      ev.preventDefault();
      setOpen(false);
      pickEl.focus();
      return;
    }
    if (ev.key && ev.key.length === 1 && /[a-z]/i.test(ev.key)) {
      var letter = ev.key.toUpperCase();
      for (var n = 1; n <= all.length; n++) {
        var cand = all[(Math.max(i, 0) + n) % all.length];
        if (cand.getAttribute('data-code').charAt(0) === letter) {
          cand.focus();
          return;
        }
      }
    }
  });
  pickEl.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      setOpen(true);
      refresh();
      focusActive();
    }
  });
  amountEl.addEventListener('input', function () {
    render();
    refresh();
  });
  publish();
  render(); /* instant, from the baked table */

  /* refresh when the card comes into view — a rect check, not IntersectionObserver:
     when IO does not fire, nothing would ever refresh (see costs.js §11) */
  function inView() {
    if (!widgetEl) return true;
    var r = widgetEl.getBoundingClientRect();
    var h = window.innerHeight || document.documentElement.clientHeight;
    return r.top < h + 200 && r.bottom > -200;
  }
  function maybeRefresh() {
    if (!inView()) return;
    window.removeEventListener('scroll', maybeRefresh);
    window.removeEventListener('resize', maybeRefresh);
    refresh();
  }
  window.addEventListener('scroll', maybeRefresh, {
    passive: true
  });
  window.addEventListener('resize', maybeRefresh);
  maybeRefresh();
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/san-diego/currency.js", error: String((e && e.message) || e) }); }

// pages/vancouver/scripts.js
try { (() => {
/* ============================================================
   Vancouver Adults 16+ — Page-specific scripts
   Site: englishcollege | Page: adults-16
   ============================================================
   RULES:
   - const/let only, NEVER var
   - ALL code in IIFEs, NEVER pollute global scope
   - Idempotency guards on all init functions
   - NEVER inject <style> tags (CSS injection BANNED)
   - Scripts are for BEHAVIOR only, not styling
   ============================================================ */

/* ── Navbar scroll colour — REMOVED, now in shared/utils.js ──
   This file used to carry its own copy of initNavbarTransparent. So did
   pages/cost-of-studying-english/scripts.js. shared/utils.js carried a third. The San Diego pages
   load these two, so san-diego.html and costs.html got the local copies and
   how-long-to-learn-english.html got nothing at all — which is why the four pages disagreed about
   the top navigation. One implementation now, in shared/utils.js, loaded by every page. ── */

/* ── SVG Icons ──
   All SVG icons are now standalone .svg files in this page directory.
   See: adults-16-icon-*.svg, adults-16-compare-bar-*.svg
   data-svg attributes in HTML are kept for reference.
   Icons render natively via <img> on Webflow (uploaded as assets).
   ── */

/* ── Sidebar TOC — scroll-position tracking + mobile slide-out ── */
/* utils.js auto-inits TOC with __celTocDone guard. Skip if already done. */
(function () {
  if (window.__a16TocDone || window.__celTocDone) return;
  window.__a16TocDone = true;
  window.__celTocDone = true;
  const tocLinks = document.querySelectorAll('.stoc_link[data-target]');
  const sectIds = [].slice.call(tocLinks).map(function (l) {
    return l.dataset.target;
  });
  /* Spy in DOCUMENT order, not link order: detectActive() keeps the last section above the
     reading line, which is only correct if the array is in document order. A TOC whose link
     order differs from section order (San Diego §2: Courses before Location) would otherwise
     highlight the wrong link. No-op where the two orders already agree. */
  const sections = sectIds.map(function (id) {
    return document.getElementById(id);
  }).filter(Boolean).sort(function (a, b) {
    return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });
  const nav = document.querySelector('.navbar_component');
  function shouldReduce() {
    return matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  if (!sections.length || !tocLinks.length) return;
  const stocComponent = document.querySelector('.stoc_component');
  const stocLabel = document.querySelector('.stoc_label');
  tocLinks.forEach(function (l) {
    l.removeAttribute('href');
    l.setAttribute('tabindex', '0');
    l.setAttribute('role', 'link');
    // Hover: toggle is-hover on children so Webflow combo classes work
    l.addEventListener('mouseenter', function () {
      const dot = l.querySelector('.stoc_dot');
      const text = l.querySelector('.stoc_text');
      if (dot) dot.classList.add('is-hover');
      if (text) text.classList.add('is-hover');
    });
    l.addEventListener('mouseleave', function () {
      const dot = l.querySelector('.stoc_dot');
      const text = l.querySelector('.stoc_text');
      if (dot) dot.classList.remove('is-hover');
      if (text) text.classList.remove('is-hover');
    });
  });
  function setActive(id) {
    tocLinks.forEach(function (l) {
      const isActive = l.dataset.target === id;
      l.classList.toggle('is-active', isActive);
      const dot = l.querySelector('.stoc_dot');
      if (dot) dot.classList.toggle('is-active', isActive);
      const text = l.querySelector('.stoc_text');
      if (text) text.classList.toggle('is-active', isActive);
    });
    if (stocLabel) {
      const active = [].slice.call(tocLinks).find(function (l) {
        return l.dataset.target === id;
      });
      if (active) {
        const textEl = active.querySelector('.stoc_text');
        stocLabel.textContent = textEl ? textEl.textContent.trim() : active.textContent.trim();
      }
    }
  }
  function detectActive() {
    const readingLine = (nav ? nav.offsetHeight : 90) + 40;
    let activeId = sections[0].id;
    sections.forEach(function (sec) {
      if (sec.getBoundingClientRect().top <= readingLine) activeId = sec.id;
    });
    setActive(activeId);
  }
  let rafPending = false;
  window.addEventListener('scroll', function () {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(function () {
      detectActive();
      rafPending = false;
    });
  }, {
    passive: true
  });
  function closeMenu() {
    if (!stocComponent) return;
    stocComponent.classList.remove('is-menu-open');
    if (backdrop) backdrop.classList.remove('is-visible');
  }

  /* Duration-capped smooth scroll that tracks a LIVE target. Native `behavior:'smooth'`
     scales its duration with distance, so a 20,000px jump on this page animates for several
     seconds and reads as broken, while a plain jump reads as a hard cut. Fixed ~700ms ease-out
     instead. The destination MUST be recomputed every frame: a long jump crosses dozens of
     lazy images, and each one that decodes mid-flight grows the page and moves the target
     (an upward jump chasing a receding target used to land 10,000px off). After the ease we
     converge on the live target, then keep re-snapping briefly while layout settles — unless
     the reader takes over, in which case we get out of the way immediately. */
  function smoothScrollToEl(el, offset) {
    const want = function () {
      return el.getBoundingClientRect().top + window.scrollY - offset;
    };
    if (shouldReduce()) {
      window.scrollTo(0, want());
      return;
    }
    const DUR = 700,
      MAX = 1800;
    const t0 = performance.now();
    let cancelled = false;
    const stop = function () {
      cancelled = true;
    };
    ['wheel', 'touchstart', 'keydown'].forEach(function (e) {
      window.addEventListener(e, stop, {
        once: true,
        passive: true
      });
    });
    function release() {
      ['wheel', 'touchstart', 'keydown'].forEach(function (e) {
        window.removeEventListener(e, stop);
      });
    }
    function settle() {
      const t1 = performance.now();
      (function s() {
        if (cancelled) {
          release();
          return;
        }
        if (Math.abs(want() - window.scrollY) > 1) window.scrollTo(0, want());
        if (performance.now() - t1 < 700) requestAnimationFrame(s);else release();
      })();
    }
    (function step(now) {
      if (cancelled) {
        release();
        return;
      }
      const t = now - t0;
      const cur = window.scrollY,
        gap = want() - cur;
      if (t >= DUR && Math.abs(gap) <= 2 || t >= MAX) {
        window.scrollTo(0, want());
        settle();
        return;
      }
      const p = Math.min(1, t / DUR);
      window.scrollTo(0, cur + gap * (0.1 + 0.22 * p));
      requestAnimationFrame(step);
    })(t0);
  }
  function scrollToSection(link) {
    const target = document.getElementById(link.dataset.target);
    if (!target) return;
    setActive(link.dataset.target);
    smoothScrollToEl(target, (nav ? nav.offsetHeight : 90) + 24);
  }
  tocLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      scrollToSection(link);
      closeMenu();
    });
    link.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        scrollToSection(link);
        closeMenu();
      }
    });
  });
  const hash = location.hash.replace('#', '');
  if (hash && sectIds.indexOf(hash) !== -1) setActive(hash);else detectActive();

  /* Mobile TOC */
  let backdrop = null;
  const heroSection = document.querySelector('.section_hero');
  if (stocComponent && stocLabel) {
    const navH = nav ? nav.offsetHeight : 80;
    const lastSection = sections[sections.length - 1];
    function updateTabVisibility() {
      if (!heroSection) {
        stocComponent.classList.add('is-visible');
        return;
      }
      const heroBottom = heroSection.getBoundingClientRect().bottom;
      const lastBottom = lastSection ? lastSection.getBoundingClientRect().bottom : Infinity;
      if (heroBottom < navH + 20 && lastBottom > navH + 40) {
        stocComponent.classList.add('is-visible');
      } else {
        stocComponent.classList.remove('is-visible');
        closeMenu();
      }
    }
    window.addEventListener('scroll', updateTabVisibility, {
      passive: true
    });
    updateTabVisibility();
    backdrop = document.createElement('div');
    backdrop.className = 'stoc_backdrop';
    document.body.appendChild(backdrop);
    stocLabel.addEventListener('click', function () {
      const isOpen = stocComponent.classList.toggle('is-menu-open');
      backdrop.classList.toggle('is-visible', isOpen);
    });
    backdrop.addEventListener('click', closeMenu);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeMenu();
    });
  }
})();

/* ── Card Slider init + all sliders ── */
(function () {
  if (window.__a16SliderDone) return;
  window.__a16SliderDone = true;
  function initCardSlider(sectionSel, opts) {
    if (typeof Swiper === 'undefined') return null;
    opts = opts || {};
    const section = document.querySelector(sectionSel);
    if (!section) return null;
    let swiperEl = opts.swiper ? document.querySelector(opts.swiper) : section.querySelector('.card-slider.swiper');
    if (!swiperEl) swiperEl = section.querySelector('.swiper');
    if (!swiperEl) return null;
    let navEl = opts.nav ? document.querySelector(opts.nav) : section.querySelector('.card-slider_nav');
    if (!navEl) navEl = section;
    const config = {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      grabCursor: true,
      freeMode: {
        enabled: true,
        sticky: false
      },
      breakpoints: opts.breakpoints || {}
    };
    const swiper = new Swiper(swiperEl, config);
    const prevBtn = navEl.querySelector('.card-slider_arrow.is-prev');
    const nextBtn = navEl.querySelector('.card-slider_arrow.is-next');
    const progressFill = navEl.querySelector('.card-slider_progress-fill');
    if (prevBtn) prevBtn.addEventListener('click', function () {
      swiper.slidePrev();
    });
    if (nextBtn) nextBtn.addEventListener('click', function () {
      swiper.slideNext();
    });
    function updateProgress() {
      if (!progressFill || !swiper.slides || !swiper.slides.length) return;
      let progress = swiper.progress;
      if (isNaN(progress)) progress = 0;
      progress = Math.max(0, Math.min(1, progress));
      progressFill.style.width = progress * 100 + '%';
    }
    swiper.on('progress', updateProgress);
    swiper.on('slideChange', updateProgress);
    updateProgress();
    return swiper;
  }
  const autoBreakpoints = {
    0: {
      slidesPerView: 'auto',
      spaceBetween: 12
    },
    480: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    768: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    992: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    1400: {
      slidesPerView: 'auto',
      spaceBetween: 16
    }
  };
  function go() {
    if (typeof Swiper === 'undefined') return;
    initCardSlider('#courses', {
      slidesPerView: 'auto',
      spaceBetween: 16,
      breakpoints: autoBreakpoints
    });
    initCardSlider('#city', {
      swiper: '#showcaseSlider',
      nav: '#showcaseSliderNav',
      slidesPerView: 'auto',
      spaceBetween: 16,
      speed: 800,
      breakpoints: autoBreakpoints
    });
    // Testimonials: CMS Collection List (#testimonials-col) is the swiper root,
    // and the static Google-Reviews hero (#testimonial-hero) must be slide 0.
    const testCol = document.getElementById('testimonials-col');
    const testWrap = testCol ? testCol.querySelector('.swiper-wrapper') : null;
    const testHero = document.getElementById('testimonial-hero');
    if (testCol && !testCol.classList.contains('swiper')) testCol.classList.add('swiper');
    if (testHero && testWrap && testHero.parentNode !== testWrap) testWrap.insertBefore(testHero, testWrap.firstChild);
    initCardSlider('.section_testimonials', {
      swiper: '#testimonials-col',
      nav: '#testimonialsSliderNav',
      slidesPerView: 'auto',
      spaceBetween: 16,
      breakpoints: autoBreakpoints
    });
    initCardSlider('#activities', {
      swiper: '#activitiesSlider',
      nav: '#activitiesSliderNav',
      slidesPerView: 'auto',
      spaceBetween: 16,
      breakpoints: autoBreakpoints
    });
    initCardSlider('#accommodation', {
      swiper: '#accomSlider',
      nav: '#accomSliderNav',
      slidesPerView: 'auto',
      spaceBetween: 16,
      breakpoints: {
        480: {
          spaceBetween: 16
        },
        768: {
          spaceBetween: 18
        },
        992: {
          spaceBetween: 20
        },
        1400: {
          spaceBetween: 22
        }
      }
    });
  }
  if (typeof Swiper !== 'undefined') go();else document.addEventListener('swiperReady', go);
})();

/* ── Comparison bars — animate on scroll ── */
(function () {
  if (window.__a16CompareDone) return;
  window.__a16CompareDone = true;
  const el = document.querySelector('.compare_component');
  if (!el) return;
  const obs = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) {
      el.classList.add('is-visible');
      obs.disconnect();
    }
  }, {
    threshold: 0.3
  });
  obs.observe(el);
})();

/* ── Vimeo lazy-load facade ── */
(function () {
  if (window.__a16VimeoDone) return;
  window.__a16VimeoDone = true;
  const player = document.querySelector('.video_player[data-vimeo-id]');
  if (!player) return;
  const btn = player.querySelector('.video_play-btn');
  const thumb = player.querySelector('.video_thumbnail');
  if (!btn && !thumb) return;
  function loadVideo() {
    const id = player.getAttribute('data-vimeo-id');
    if (!id || player.classList.contains('is-playing')) return;
    const iframe = document.createElement('iframe');
    iframe.className = 'video_embed';
    iframe.src = 'https://player.vimeo.com/video/' + id + '?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';
    iframe.setAttribute('frameborder', '0');
    iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
    iframe.setAttribute('allowfullscreen', '');
    iframe.title = 'CEL Vancouver — English Language School';
    player.appendChild(iframe);
    player.classList.add('is-playing');
  }
  if (btn) btn.addEventListener('click', loadVideo);
  if (thumb) thumb.addEventListener('click', loadVideo);
})();

/* ── FAQ Accordion — capture phase to beat webflow.js IX2 ── */
(function () {
  if (window.__celFq || window.__a16Faq) return;
  window.__a16Faq = true;
  if (!document.querySelector('.faq-item')) return;
  function cancelAnims() {
    document.querySelectorAll('.faq-body').forEach(function (b) {
      if (b.getAnimations) b.getAnimations().forEach(function (a) {
        a.cancel();
      });
    });
  }

  /* Capture phase (3rd arg: true) fires BEFORE IX2's bubbling handler.
     stopPropagation() prevents IX2 from seeing the click at all,
     eliminating the double-toggle that causes "opens then cancels". */
  document.addEventListener('click', function (e) {
    const q = e.target.closest('.faq-q');
    if (!q) return;
    e.stopPropagation();
    const item = q.closest('.faq-item');
    if (!item) return;
    const wasOpen = item.dataset.faqOpen === 'true';
    cancelAnims();

    // Close all
    document.querySelectorAll('.faq-item').forEach(function (it) {
      const bd = it.querySelector('.faq-body');
      const bt = it.querySelector('.faq-q');
      const ic = it.querySelector('.faq-icon');
      it.dataset.faqOpen = 'false';
      it.classList.remove('is-open');
      if (bt) {
        bt.classList.remove('is-open');
        bt.setAttribute('aria-expanded', 'false');
      }
      if (ic) ic.classList.remove('is-open');
      if (bd) bd.style.maxHeight = '0px';
    });

    // Open clicked (if it was closed)
    if (!wasOpen) {
      const bd = item.querySelector('.faq-body');
      const inner = item.querySelector('.faq-body-inner');
      const bt = item.querySelector('.faq-q');
      const ic = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'true';
      item.classList.add('is-open');
      if (bt) {
        bt.classList.add('is-open');
        bt.setAttribute('aria-expanded', 'true');
      }
      if (ic) ic.classList.add('is-open');
      if (bd && inner) bd.style.maxHeight = inner.scrollHeight + 'px';
    }
  }, true);
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/vancouver/scripts.js", error: String((e && e.message) || e) }); }

// pages/vs-toronto/scripts.js
try { (() => {
/**
 * vs-toronto — Page Scripts
 * CEL Vancouver Subpage
 *
 * DEPENDENCIES:
 *   ../../shared/utils.js (loaded before this file)
 *     - initTocCore()        → scroll-spy + click-to-scroll (auto-init)
 *     - initTocMobile()      → floating tab + slide-out menu (auto-init)
 *     - initNavbarTransparent() → navbar bg over hero (auto-init + sharedComponentsReady retry)
 *     - TOC dot polling      → active dot color (auto-init)
 *     - FAQ accordion        → IX2 cancel + accordion (auto-init)
 *     - shouldReduceMotion() → respects prefers-reduced-motion
 *
 * ON WEBFLOW:
 *   These functions are deployed as separate inline scripts via MCP.
 *   See sites/cel/shared/standard-scripts.md for:
 *     - celnavtoc3  → navbar transparent fix + TOC dot polling + hero button fix
 *     - celfaq1     → FAQ IX2 cancel + accordion
 *   Both are MANDATORY on every page.
 *
 * ============================================================
 */

/* ── 1. Card Slider Init ── */
/* Copy of initCardSlider from shared/swiper-init.js (reference implementation).
   CDN guard: costsswiper3/a16swiperretry handle this on Webflow.
   CUSTOMIZE: Replace guard flag, section selectors, and breakpoint preset. */
(function () {
  if (window.__vstSlider) return;
  window.__vstSlider = true;

  /* ── Shared factory (from shared/swiper-init.js) ── */
  function initCardSlider(sectionSel, opts) {
    if (typeof Swiper === 'undefined') return null;
    opts = opts || {};
    const section = document.querySelector(sectionSel);
    if (!section) return null;
    let swiperEl = opts.swiper ? document.querySelector(opts.swiper) : section.querySelector('.card-slider.swiper');
    if (!swiperEl) swiperEl = section.querySelector('.swiper');
    if (!swiperEl) return null;
    let navEl = opts.nav ? document.querySelector(opts.nav) : section.querySelector('.card-slider_nav');
    if (!navEl) navEl = section;
    const swiper = new Swiper(swiperEl, {
      slidesPerView: opts.slidesPerView || 'auto',
      spaceBetween: opts.spaceBetween || 16,
      speed: opts.speed || 600,
      grabCursor: true,
      freeMode: {
        enabled: true,
        sticky: false
      },
      breakpoints: opts.breakpoints || {}
    });
    const prevBtn = navEl.querySelector('.card-slider_arrow.is-prev');
    const nextBtn = navEl.querySelector('.card-slider_arrow.is-next');
    const progressFill = navEl.querySelector('.card-slider_progress-fill');
    if (prevBtn) prevBtn.addEventListener('click', function () {
      swiper.slidePrev();
    });
    if (nextBtn) nextBtn.addEventListener('click', function () {
      swiper.slideNext();
    });
    function updateProgress() {
      if (!progressFill || !swiper.slides || !swiper.slides.length) return;
      let progress = swiper.progress;
      if (isNaN(progress)) progress = 0;
      progress = Math.max(0, Math.min(1, progress));
      progressFill.style.width = progress * 100 + '%';
    }
    swiper.on('progress', updateProgress);
    swiper.on('slideChange', updateProgress);
    updateProgress();
    return swiper;
  }

  /* ── Breakpoint presets ── */
  const autoBreakpoints = {
    0: {
      slidesPerView: 6,
      spaceBetween: 12
    },
    480: {
      slidesPerView: 6,
      spaceBetween: 16
    },
    768: {
      slidesPerView: 6,
      spaceBetween: 16
    },
    992: {
      slidesPerView: 6,
      spaceBetween: 16
    },
    1400: {
      slidesPerView: 6,
      spaceBetween: 16
    }
  };
  const wideGapBreakpoints = {
    480: {
      spaceBetween: 16
    },
    768: {
      spaceBetween: 18
    },
    992: {
      spaceBetween: 20
    },
    1400: {
      spaceBetween: 22
    }
  };

  /* ── Bootstrap missing Swiper structure (Webflow Designer drift recovery) ──
     If .swiper-wrapper is absent (Designer state lost the slide structure),
     rebuild it from the .vst_thumb image URLs so Swiper has slides to animate. */
  function bootstrap(g, thumbs) {
    if (g.querySelector('.swiper-wrapper')) return;
    g.classList.add('swiper');
    const wrap = document.createElement('div');
    wrap.className = 'swiper-wrapper';
    thumbs.forEach(function (t) {
      const slide = document.createElement('div');
      slide.className = 'swiper-slide';
      const ti = t.querySelector('.vst_thumb-img');
      if (ti) {
        const im = ti.cloneNode(false);
        im.classList.remove('vst_thumb-img');
        im.classList.add('vst_gallery-img');
        if (im.alt) im.alt = im.alt.replace(/\s*thumbnail\s*$/i, '');
        slide.appendChild(im);
      }
      wrap.appendChild(slide);
    });
    while (g.firstChild) g.removeChild(g.firstChild);
    g.appendChild(wrap);
    const ctr = document.createElement('div');
    ctr.className = 'vst_gallery-counter';
    const cur = document.createElement('p');
    cur.className = 'vst_gallery-current';
    cur.textContent = '01';
    const dv = document.createElement('div');
    dv.className = 'vst_gallery-divider';
    const tot = document.createElement('p');
    tot.className = 'vst_gallery-total';
    tot.textContent = String(thumbs.length).padStart(2, '0');
    ctr.appendChild(cur);
    ctr.appendChild(dv);
    ctr.appendChild(tot);
    g.appendChild(ctr);
  }

  /* ── Init all sliders on this page ── */
  function go() {
    if (typeof Swiper === 'undefined') return;
    /* Culture gallery — cinematic fade + side thumbnails + progress */
    const galleryEl = document.querySelector('.vst_gallery-slider');
    const thumbs = document.querySelectorAll('.vst_thumb');
    if (galleryEl && thumbs.length) {
      bootstrap(galleryEl, thumbs);
      const counterCurrent = document.querySelector('.vst_gallery-current');
      const gallery = new Swiper(galleryEl, {
        slidesPerView: 1,
        spaceBetween: 0,
        speed: 1200,
        loop: true,
        grabCursor: true,
        effect: 'fade',
        fadeEffect: {
          crossFade: true
        },
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
          pauseOnMouseEnter: true
        }
      });
      function setActiveThumb(idx) {
        thumbs.forEach(function (t) {
          t.classList.remove('is-active');
        });
        if (thumbs[idx]) thumbs[idx].classList.add('is-active');
        if (counterCurrent) counterCurrent.textContent = String(idx + 1).padStart(2, '0');
      }
      setActiveThumb(0);
      gallery.on('slideChange', function () {
        setActiveThumb(gallery.realIndex);
      });
      thumbs.forEach(function (t) {
        t.addEventListener('click', function () {
          const idx = parseInt(t.getAttribute('data-index'), 10);
          gallery.slideToLoop(idx, 1200);
        });
      });
    }
  }

  /* ── Safe Swiper CDN loading ── */
  if (typeof Swiper !== 'undefined') {
    go();
    return;
  }
  document.addEventListener('swiperReady', go, {
    once: true
  });
  let retries = 0;
  const timer = setInterval(function () {
    if (typeof Swiper !== 'undefined') {
      clearInterval(timer);
      go();
    } else if (++retries >= 20) clearInterval(timer);
  }, 100);
})();

/* ── 2. Compare Table — Bar Animation + Drag Scroll ── */
(function () {
  if (window.__vstCompare) return;
  window.__vstCompare = true;

  /* Scroll-triggered bar fill animation */
  const compEls = document.querySelectorAll('.compare_component');
  if (compEls.length && 'IntersectionObserver' in window) {
    const obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('is-visible');
          obs.unobserve(e.target);
        }
      });
    }, {
      threshold: 0.3
    });
    compEls.forEach(function (el) {
      obs.observe(el);
    });
  }

  /* Click-and-drag scroll (only when content overflows) */
  compEls.forEach(function (el) {
    let isDown = false,
      startX,
      scrollL;
    function checkScrollable() {
      const isNow = el.scrollWidth > el.clientWidth;
      el.classList.toggle('is-scrollable', isNow);
      if (isNow) el.scrollLeft = 0;
    }
    checkScrollable();
    window.addEventListener('resize', checkScrollable);
    el.addEventListener('mousedown', function (e) {
      if (el.scrollWidth <= el.clientWidth) return;
      isDown = true;
      el.classList.add('is-dragging');
      startX = e.pageX - el.offsetLeft;
      scrollL = el.scrollLeft;
    });
    el.addEventListener('mouseleave', function () {
      isDown = false;
      el.classList.remove('is-dragging');
    });
    el.addEventListener('mouseup', function () {
      isDown = false;
      el.classList.remove('is-dragging');
    });
    el.addEventListener('mousemove', function (e) {
      if (!isDown) return;
      e.preventDefault();
      el.scrollLeft = scrollL - (e.pageX - el.offsetLeft - startX);
    });
  });
})();

/* ── 3. Vimeo Lazy-Load Facade ── */
(function () {
  if (window.__vstVimeo) return;
  window.__vstVimeo = true;
  const player = document.querySelector('.video_player[data-vimeo-id]');
  if (!player) return;
  const btn = player.querySelector('.video_play-btn');
  const thumb = player.querySelector('.video_thumbnail');
  if (!btn && !thumb) return;
  function loadVideo() {
    const id = player.getAttribute('data-vimeo-id');
    if (!id || player.classList.contains('is-playing')) return;
    const iframe = document.createElement('iframe');
    iframe.className = 'video_embed';
    iframe.src = 'https://player.vimeo.com/video/' + id + '?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';
    iframe.setAttribute('frameborder', '0');
    iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
    iframe.setAttribute('allowfullscreen', '');
    iframe.title = 'CEL Vancouver — English Language School';
    player.appendChild(iframe);
    player.classList.add('is-playing');
  }
  if (btn) btn.addEventListener('click', loadVideo);
  if (thumb) thumb.addEventListener('click', loadVideo);
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "pages/vs-toronto/scripts.js", error: String((e && e.message) || e) }); }

// sections/tweaks-panel.jsx
try { (() => {
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;width:100%;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null ? keyOrEdits : {
      [keyOrEdits]: val
    };
    setValues(prev => ({
      ...prev,
      ...edits
    }));
    window.parent.postMessage({
      type: '__edit_mode_set_keys',
      edits
    }, '*');
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({
  title = 'Tweaks',
  children
}) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({
    x: 16,
    y: 16
  });
  const PAD = 16;
  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth,
      h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y))
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);
  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);
  React.useEffect(() => {
    const onMsg = e => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({
      type: '__edit_mode_available'
    }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);
  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({
      type: '__edit_mode_dismissed'
    }, '*');
  };
  const onDragStart = e => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX,
      sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = ev => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy)
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("style", null, __TWEAKS_STYLE), /*#__PURE__*/React.createElement("div", {
    ref: dragRef,
    className: "twk-panel",
    style: {
      right: offsetRef.current.x,
      bottom: offsetRef.current.y
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-hd",
    onMouseDown: onDragStart
  }, /*#__PURE__*/React.createElement("b", null, title), /*#__PURE__*/React.createElement("button", {
    className: "twk-x",
    "aria-label": "Close tweaks",
    onMouseDown: e => e.stopPropagation(),
    onClick: dismiss
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "twk-body"
  }, children)));
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "twk-sect"
  }, label), children);
}
function TweakRow({
  label,
  value,
  children,
  inline = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: inline ? 'twk-row twk-row-h' : 'twk-row'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label), value != null && /*#__PURE__*/React.createElement("span", {
    className: "twk-val"
  }, value)), children);
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label,
    value: `${value}${unit}`
  }, /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "twk-slider",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => onChange(Number(e.target.value))
  }));
}
function TweakToggle({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "twk-toggle",
    "data-on": value ? '1' : '0',
    role: "switch",
    "aria-checked": !!value,
    onClick: () => onChange(!value)
  }, /*#__PURE__*/React.createElement("i", null)));
}
function TweakRadio({
  label,
  value,
  options,
  onChange
}) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  const opts = options.map(o => typeof o === 'object' ? o : {
    value: o,
    label: o
  });
  const idx = Math.max(0, opts.findIndex(o => o.value === value));
  const n = opts.length;

  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;
  const segAt = clientX => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor((clientX - r.left - 2) / inner * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };
  const onPointerDown = e => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = ev => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    ref: trackRef,
    role: "radiogroup",
    onPointerDown: onPointerDown,
    className: dragging ? 'twk-seg dragging' : 'twk-seg'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-seg-thumb",
    style: {
      left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
      width: `calc((100% - 4px) / ${n})`
    }
  }), opts.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    type: "button",
    role: "radio",
    "aria-checked": o.value === value
  }, o.label))));
}
function TweakSelect({
  label,
  value,
  options,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("select", {
    className: "twk-field",
    value: value,
    onChange: e => onChange(e.target.value)
  }, options.map(o => {
    const v = typeof o === 'object' ? o.value : o;
    const l = typeof o === 'object' ? o.label : o;
    return /*#__PURE__*/React.createElement("option", {
      key: v,
      value: v
    }, l);
  })));
}
function TweakText({
  label,
  value,
  placeholder,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("input", {
    className: "twk-field",
    type: "text",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange
}) {
  const clamp = n => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({
    x: 0,
    val: 0
  });
  const onScrubStart = e => {
    e.preventDefault();
    startRef.current = {
      x: e.clientX,
      val: value
    };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = ev => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-num"
  }, /*#__PURE__*/React.createElement("span", {
    className: "twk-num-lbl",
    onPointerDown: onScrubStart
  }, label), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: value,
    min: min,
    max: max,
    step: step,
    onChange: e => onChange(clamp(Number(e.target.value)))
  }), unit && /*#__PURE__*/React.createElement("span", {
    className: "twk-num-unit"
  }, unit));
}
function TweakColor({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("input", {
    type: "color",
    className: "twk-swatch",
    value: value,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakButton({
  label,
  onClick,
  secondary = false
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: secondary ? 'twk-btn secondary' : 'twk-btn',
    onClick: onClick
  }, label);
}
Object.assign(window, {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRow,
  TweakSlider,
  TweakToggle,
  TweakRadio,
  TweakSelect,
  TweakText,
  TweakNumber,
  TweakColor,
  TweakButton
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "sections/tweaks-panel.jsx", error: String((e && e.message) || e) }); }

// shared/calculator.js
try { (() => {
/* ═══════════════════════════════════════════════════════════════════════════
   CEL — calculator.js · the shared calculator/planner ENGINE
   ---------------------------------------------------------------------------
   One engine, many calculators. Every CEL page that needs a "move the controls,
   watch the numbers" tool loads THIS file plus one small page config:

       shared/calculator.js                        ← the engine (this file)
       pages/san-diego/calculator-sandiego.js      ← §16 study-budget planner
       pages/san-diego/calculator-sandiego-costs.js← §4 full cost calculator

   The engine owns everything that is the same every time: reading controls,
   wiring clicks and keyboards, slider fill, number tweening, row visibility,
   verdict panels, chips, root state classes, reduced-motion handling. The page
   config owns only what is genuinely page-specific: the rates, the arithmetic,
   and the copy. Nothing here knows a class name — markup is bound by data-
   attributes, so a page can keep its own class family (plan_*, calc_*, …).

   HOW TO ADD A CALCULATOR TO A PAGE
   ---------------------------------------------------------------------------
   1. Mark up the tool with your own classes and add the data hooks below.
   2. Write pages/<page>/calculator-<page>.js with one CELCalculator.mount({…}).
   3. Load, in this order, both deferred:
        <script src="../../shared/calculator.js" defer></script>
        <script src="calculator-<page>.js" defer></script>
      Order matters: the engine defines window.CELCalculator; a config mounted
      before the engine exists is queued and flushed when the engine loads, so a
      race cannot break the page — but keep the order anyway, it is the contract.

   DATA HOOKS (all scoped inside the mount root)
   ---------------------------------------------------------------------------
   INPUTS
     data-calc-range="key"        <input type="range">  → numeric state.key
                                  optional data-calc-fill="selector" — element
                                  that receives --calc-fill / --calc-frac
                                  (default: the input's parent)
     data-calc-select="key"       <select> → state.key. The compact default for any
                                  choice with 2+ options; tiles are for 2-option
                                  choices that must stay visible side by side
     data-calc-radio="key"        button in a radio group → state.key
       data-calc-value="v"        the value it selects (required)
     data-calc-toggle="key"       button → boolean state.key (add/remove a line)
     data-calc-menu-toggle="key" button that opens the panel marked data-calc-menu="key"
     data-calc-menu="key"        the panel itself (start it `hidden`). Closes on Escape,
                                  on an outside click, and when a choice inside it is
                                  made — use it with data-calc-radio buttons when the
                                  options need artwork a native <select> cannot show
     data-calc-set="key:value"    one-click fix: sets state.key and re-renders
                                  ("switch to full-time", "set 12 weeks").
                                  Numeric-looking values become numbers, and a
                                  matching radio group re-syncs automatically.
   OUTPUTS  (all read from what compute() returns in `out`)
     data-calc-out="name"         textContent = out[name]
     data-calc-img="name"         src = out[name] (and srcset from out["name2x"], at 2x) —
                                  for a flag or icon that follows the state; the element
                                  is hidden when the value is empty
       data-calc-tween             animate integers up/down (skipped when the
                                   visitor prefers reduced motion)
     data-calc-row="name"         hidden unless rows[name] is truthy;
       data-calc-off="class"       …or, instead of hiding, toggle this class
     data-calc-state="name"       panel set: gets `is-on` when its own
       data-calc-state-value="v"   value equals out[name] (visa verdicts)
     data-calc-chip="name"        chips[name] = { class, text } → className is
                                  rewritten as "<base> <class>" and popped
     data-calc-flag="class"       root class toggled by flags[class]

   THE PAGE CONFIG
   ---------------------------------------------------------------------------
       CELCalculator.mount({
         root: 'calcTool',              // id or selector (required)
         state: { weeks: 12, … },       // initial state; controls override it
         chipBase: 'calc_chip',         // class kept when a chip variant swaps
         compute: function (state, h) { // pure: state in, display values out
           return {
             out:   { total: h.money(x), weeks: state.weeks },
             rows:  { insurance: state.insurance },
             flags: { 'is-over': state.weeks > 12 },
             chips: { visa: { class: 'is-f1', text: 'F-1 visa' } },
             fill:  { weeks: 0.31 }     // 0–1 per range key, for the track
           };
         },
         onRender: function (res, state, api) { … }   // optional escape hatch
       });

   HELPERS passed to compute() as the second argument
     h.money(n[, cur])   "US$8,050"     — rounded, grouped, no decimals
     h.number(n)         "8050" grouped
     h.bracket(tiers, n) tiers are [[max, value], …] → first value where n<=max
     h.plural(n, one, many)  "12 weeks" / "1 week"
     h.state             the same state object (convenience)

   RULES THIS ENGINE KEEPS FOR YOU
     · figures are LibreFranklin-friendly plain text — the engine never injects
       markup or styles, so type rules stay in CSS (README: numbers are never
       Cameraobscura)
     · reduced motion is respected for every tween and chip pop
     · no page load cost beyond one small file; nothing is fetched
     · one guard flag per root, so a double-loaded config cannot double-wire
     · never writes to localStorage, never touches anything outside its root

   DEPLOY: folds into the CEL page-script bundle (tools/cel-page-scripts/src/)
   and ships minified via /deploy-page-scripts. Not a Webflow inline script.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  if (window.CELCalculator && window.CELCalculator.__engine) return;
  var reduce = false;
  try {
    reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  /* ── helpers handed to every compute() ── */
  function money(n, cur) {
    return (cur || 'US$') + Math.round(n || 0).toLocaleString('en-US');
  }
  function number(n) {
    return Math.round(n || 0).toLocaleString('en-US');
  }
  function bracket(tiers, n) {
    for (var i = 0; i < tiers.length; i++) if (n <= tiers[i][0]) return tiers[i][1];
    return tiers.length ? tiers[tiers.length - 1][1] : 0;
  }
  function plural(n, one, many) {
    return n + ' ' + (n === 1 ? one : many);
  }
  function setText(el, text) {
    if (!el) return;
    var next = text == null ? '' : String(text);
    if (el.textContent === next) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(next));
  }

  /* rAF count-up so a changing figure reads as motion, not a jump. Only integers
     tween; anything with a currency symbol or letters is set directly.
     A requestAnimationFrame that never fires — throttled tab, background window,
     a tab that is not painting — must not leave a HALF-COUNTED figure on screen,
     which would be a wrong number, not a missing animation. So every tween also
     arms a timer that snaps the element to the final text; whichever lands first
     wins and the other is a no-op. */
  function tween(el, text) {
    var to = parseFloat(String(text).replace(/[^0-9.-]/g, ''));
    var prefix = String(text).replace(/[0-9.,\-].*$/, '');
    if (!isFinite(to) || reduce) {
      setText(el, text);
      return;
    }
    var from = el.__calcV == null ? to : el.__calcV;
    el.__calcV = to;
    el.__calcTarget = text;
    if (from === to) {
      setText(el, text);
      return;
    }
    if (el.__calcRaf) cancelAnimationFrame(el.__calcRaf);
    if (el.__calcTimer) clearTimeout(el.__calcTimer);
    el.__calcTimer = setTimeout(function () {
      if (el.__calcRaf) cancelAnimationFrame(el.__calcRaf);
      setText(el, el.__calcTarget);
    }, 520);
    var t0 = performance.now();
    (function step(t) {
      var p = Math.min(1, (t - t0) / 420);
      p = 1 - Math.pow(1 - p, 3);
      setText(el, prefix + Math.round(from + (to - from) * p).toLocaleString('en-US'));
      if (p < 1) {
        el.__calcRaf = requestAnimationFrame(step);
        return;
      }
      clearTimeout(el.__calcTimer);
      setText(el, el.__calcTarget);
    })(t0);
  }
  function coerce(v) {
    if (v === 'true') return true;
    if (v === 'false') return false;
    if (v !== '' && !isNaN(v)) return parseFloat(v);
    return v;
  }
  function Calculator(config) {
    var root = typeof config.root === 'string' ? document.getElementById(config.root) || document.querySelector(config.root) : config.root;
    if (!root) return null;
    if (root.__celCalc) return root.__celCalc; /* one instance per root */

    var self = this;
    var state = {};
    for (var k in config.state || {}) if (config.state.hasOwnProperty(k)) state[k] = config.state[k];
    var ranges = root.querySelectorAll('[data-calc-range]');
    var selects = root.querySelectorAll('[data-calc-select]');
    var radios = root.querySelectorAll('[data-calc-radio]');
    var toggles = root.querySelectorAll('[data-calc-toggle]');
    var setters = root.querySelectorAll('[data-calc-set]');
    var menus = root.querySelectorAll('[data-calc-menu]');
    var menuToggles = root.querySelectorAll('[data-calc-menu-toggle]');
    var outs = root.querySelectorAll('[data-calc-out]');
    var imgs = root.querySelectorAll('[data-calc-img]');
    var rows = root.querySelectorAll('[data-calc-row]');
    var panels = root.querySelectorAll('[data-calc-state]');
    var chips = root.querySelectorAll('[data-calc-chip]');
    var flags = root.querySelectorAll('[data-calc-flag]');

    /* markup is the source of truth for initial values, so the rendered page and
       the state can never disagree on load */
    Array.prototype.forEach.call(ranges, function (r) {
      state[r.getAttribute('data-calc-range')] = parseFloat(r.value);
    });
    Array.prototype.forEach.call(selects, function (s) {
      state[s.getAttribute('data-calc-select')] = s.value;
    });
    Array.prototype.forEach.call(radios, function (b) {
      if (b.classList.contains('is-on') || b.getAttribute('aria-checked') === 'true') {
        state[b.getAttribute('data-calc-radio')] = b.getAttribute('data-calc-value');
      }
    });
    Array.prototype.forEach.call(toggles, function (b) {
      var key = b.getAttribute('data-calc-toggle');
      if (state[key] == null) state[key] = b.classList.contains('is-on');
    });
    var helpers = {
      money: money,
      number: number,
      bracket: bracket,
      plural: plural,
      state: state
    };
    function syncRadios(key, value) {
      Array.prototype.forEach.call(selects, function (s) {
        if (s.getAttribute('data-calc-select') === key) s.value = String(value);
      });
      Array.prototype.forEach.call(radios, function (b) {
        if (b.getAttribute('data-calc-radio') !== key) return;
        var on = b.getAttribute('data-calc-value') === String(value);
        b.classList.toggle('is-on', on);
        /* some option lists are styled on .is-active (a listbox), some on .is-on (tiles) —
           keep both in step so a picker can reuse either vocabulary */
        b.classList.toggle('is-active', on);
        if (b.hasAttribute('aria-checked')) b.setAttribute('aria-checked', on ? 'true' : 'false');
        if (b.hasAttribute('aria-selected')) b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }
    function render() {
      var res = config.compute ? config.compute(state, helpers) || {} : {};
      var out = res.out || {},
        rowState = res.rows || {},
        flagState = res.flags || {},
        chipState = res.chips || {},
        fill = res.fill || {};
      Array.prototype.forEach.call(outs, function (el) {
        var name = el.getAttribute('data-calc-out');
        if (!(name in out)) return;
        if (el.hasAttribute('data-calc-tween')) tween(el, out[name]);else setText(el, out[name]);
      });
      Array.prototype.forEach.call(imgs, function (el) {
        var name = el.getAttribute('data-calc-img');
        if (!(name in out)) return;
        var url = out[name];
        if (!url) {
          el.hidden = true;
          return;
        }
        el.hidden = false;
        if (el.getAttribute('src') !== url) {
          el.setAttribute('src', url);
          if (out[name + '2x']) el.setAttribute('srcset', out[name + '2x'] + ' 2x');
        }
      });
      Array.prototype.forEach.call(rows, function (el) {
        var on = !!rowState[el.getAttribute('data-calc-row')];
        var off = el.getAttribute('data-calc-off');
        if (off) el.classList.toggle(off, !on);else el.hidden = !on;
      });
      Array.prototype.forEach.call(panels, function (el) {
        var name = el.getAttribute('data-calc-state');
        el.classList.toggle('is-on', String(out[name]) === el.getAttribute('data-calc-state-value'));
      });
      Array.prototype.forEach.call(chips, function (el) {
        var spec = chipState[el.getAttribute('data-calc-chip')];
        if (!spec) return;
        var base = config.chipBase || el.getAttribute('data-calc-chip-base') || '';
        var next = (base + ' ' + (spec.class || '')).trim();
        var changed = el.className !== next || el.textContent !== spec.text;
        el.className = next;
        setText(el, spec.text);
        if (changed && !reduce) {
          el.classList.remove('is-pop');
          void el.offsetWidth; /* restart the keyframe */
          el.classList.add('is-pop');
        }
      });
      Array.prototype.forEach.call(flags, function (el) {
        var cls = el.getAttribute('data-calc-flag');
        el.classList.toggle(cls, !!flagState[cls]);
      });
      for (var cls in flagState) if (flagState.hasOwnProperty(cls)) {
        root.classList.toggle(cls, !!flagState[cls]);
      }
      Array.prototype.forEach.call(ranges, function (r) {
        var key = r.getAttribute('data-calc-range');
        var frac = fill[key];
        if (frac == null) {
          var min = parseFloat(r.min || 0),
            max = parseFloat(r.max || 100);
          frac = max === min ? 0 : (parseFloat(r.value) - min) / (max - min);
        }
        var target = r.getAttribute('data-calc-fill');
        target = target ? root.querySelector(target) || r.parentNode : r.parentNode;
        var pct = (frac * 100).toFixed(2) + '%';
        target.style.setProperty('--calc-fill', pct);
        target.style.setProperty('--calc-frac', frac.toFixed(4));
        r.style.setProperty('--calc-fill', pct); /* the track may be the input itself */
        if (out[key + 'Aria']) r.setAttribute('aria-valuetext', out[key + 'Aria']);
      });
      if (config.onRender) config.onRender(res, state, self);
    }

    /* ── wiring ── */
    Array.prototype.forEach.call(ranges, function (r) {
      r.addEventListener('input', function () {
        state[r.getAttribute('data-calc-range')] = parseFloat(r.value);
        render();
      });
    });
    Array.prototype.forEach.call(selects, function (s) {
      s.addEventListener('change', function () {
        state[s.getAttribute('data-calc-select')] = s.value;
        render();
      });
    });

    /* ── option panels (for choices whose options carry artwork) ── */
    function panelFor(key) {
      for (var i = 0; i < menus.length; i++) {
        if (menus[i].getAttribute('data-calc-menu') === key) return menus[i];
      }
      return null;
    }
    function setMenu(key, open) {
      var panel = panelFor(key);
      if (!panel) return;
      panel.hidden = !open;
      Array.prototype.forEach.call(menuToggles, function (t) {
        if (t.getAttribute('data-calc-menu-toggle') === key) {
          t.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
      });
      if (open) document.addEventListener('click', onOutside, true);else document.removeEventListener('click', onOutside, true);
    }
    function closeMenus() {
      Array.prototype.forEach.call(menus, function (m) {
        setMenu(m.getAttribute('data-calc-menu'), false);
      });
    }
    function onOutside(ev) {
      var inside = false;
      Array.prototype.forEach.call(menus, function (m) {
        if (m.contains(ev.target)) inside = true;
      });
      Array.prototype.forEach.call(menuToggles, function (t) {
        if (t.contains(ev.target)) inside = true;
      });
      if (!inside) closeMenus();
    }
    root.addEventListener('click', function (ev) {
      var t = ev.target.closest ? ev.target.closest('[data-calc-radio],[data-calc-toggle],[data-calc-set],[data-calc-menu-toggle]') : null;
      if (!t || !root.contains(t)) return;
      if (t.hasAttribute('data-calc-menu-toggle')) {
        var mk = t.getAttribute('data-calc-menu-toggle');
        var panel = panelFor(mk);
        setMenu(mk, panel ? panel.hidden : false);
        return;
      }
      if (t.hasAttribute('data-calc-radio')) {
        var key = t.getAttribute('data-calc-radio');
        state[key] = t.getAttribute('data-calc-value');
        syncRadios(key, state[key]);
        closeMenus();
        render();
        return;
      }
      if (t.hasAttribute('data-calc-toggle')) {
        var tk = t.getAttribute('data-calc-toggle');
        state[tk] = !state[tk];
        t.classList.toggle('is-on', state[tk]);
        if (t.hasAttribute('aria-pressed')) t.setAttribute('aria-pressed', state[tk] ? 'true' : 'false');
        render();
        return;
      }
      /* data-calc-set="key:value" — the one-click fixes */
      var pair = (t.getAttribute('data-calc-set') || '').split(':');
      if (pair.length < 2) return;
      var sk = pair[0],
        sv = coerce(pair.slice(1).join(':'));
      state[sk] = sv;
      syncRadios(sk, sv);
      Array.prototype.forEach.call(ranges, function (r) {
        if (r.getAttribute('data-calc-range') === sk) r.value = sv;
      });
      render();
    });

    /* arrow keys walk a radio group, the way a native one does; Escape closes a panel */
    root.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        closeMenus();
        return;
      }
      if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft' && ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
      var btn = document.activeElement;
      if (!btn || !btn.hasAttribute || !btn.hasAttribute('data-calc-radio')) return;
      var key = btn.getAttribute('data-calc-radio');
      var group = root.querySelectorAll('[data-calc-radio="' + key + '"]');
      var i = Array.prototype.indexOf.call(group, btn);
      var next = ev.key === 'ArrowRight' || ev.key === 'ArrowDown' ? i + 1 : i - 1;
      if (next < 0) next = group.length - 1;
      if (next >= group.length) next = 0;
      ev.preventDefault();
      group[next].focus();
      group[next].click();
    });

    /* public surface — for a page that needs to drive the tool from outside */
    this.root = root;
    this.state = state;
    this.render = render;
    this.set = function (key, value) {
      state[key] = value;
      syncRadios(key, value);
      Array.prototype.forEach.call(ranges, function (r) {
        if (r.getAttribute('data-calc-range') === key) r.value = value;
      });
      render();
      return self;
    };
    root.__celCalc = this;
    render();
    return this;
  }
  var queued = window.CELCalculator && window.CELCalculator.__queue || [];
  window.CELCalculator = {
    __engine: true,
    /** Mount a calculator. Returns the instance, or null if the root is absent
     *  (a config may safely ship on a page that does not carry the tool). */
    mount: function (config) {
      return new Calculator(config) || null;
    },
    /** Same helpers compute() receives, for a config that needs them outside. */
    helpers: {
      money: money,
      number: number,
      bracket: bracket,
      plural: plural
    },
    reducedMotion: reduce
  };
  for (var i = 0; i < queued.length; i++) window.CELCalculator.mount(queued[i]);
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "shared/calculator.js", error: String((e && e.message) || e) }); }

// shared/swiper-init.js
try { (() => {
/**
 * CEL Shared Swiper Initialization — REFERENCE IMPLEMENTATION
 * This file is NOT deployed to Webflow directly.
 * Copy the initCardSlider function into each page's scripts.js IIFE.
 *
 * USAGE IN PAGE SCRIPTS:
 *   1. Copy initCardSlider() + BREAKPOINT_PRESETS into your slider IIFE
 *   2. Call initCardSlider(sectionSelector, opts) for each slider
 *   3. Wrap in ensureSwiperReady() for safe CDN loading
 *
 * ON WEBFLOW:
 *   Each page deploys its own slider script (a16swiperretry, costsswiper3, etc.)
 *   containing a copy of this factory function + page-specific init calls.
 *
 * ============================================================
 */

/**
 * Breakpoint presets for Swiper responsive config.
 * Use these instead of writing breakpoint objects inline.
 */
var BREAKPOINT_PRESETS = {
  /* Standard card slider — equal gaps at all viewports */
  auto: {
    0: {
      slidesPerView: 'auto',
      spaceBetween: 12
    },
    480: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    768: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    992: {
      slidesPerView: 'auto',
      spaceBetween: 16
    },
    1400: {
      slidesPerView: 'auto',
      spaceBetween: 16
    }
  },
  /* Accommodation/living — increasing gaps for breathing room */
  wideGap: {
    480: {
      spaceBetween: 16
    },
    768: {
      spaceBetween: 18
    },
    992: {
      spaceBetween: 20
    },
    1400: {
      spaceBetween: 22
    }
  }
};

/**
 * Initialize a card slider with navigation and progress bar.
 *
 * MANDATORY HTML STRUCTURE:
 *   <section id="sectionId">
 *     <div class="{prefix}-slider">
 *       <div class="{prefix}-slider_clip">
 *         <div class="card-slider swiper">         ← Swiper container
 *           <div class="swiper-wrapper">
 *             <div class="swiper-slide is-{type}"> ← Slides
 *           </div>
 *         </div>
 *       </div>
 *       <div class="card-slider_nav {prefix}-slider_nav" id="{prefix}SliderNav">
 *         <div class="card-slider_arrow {prefix}-slider_arrow is-prev" role="button" tabindex="0" aria-label="Previous">
 *           <img class="slider-arrow-icon" src="..." alt="Previous" loading="lazy">
 *         </div>
 *         <div class="card-slider_progress {prefix}-slider_progress">
 *           <div class="card-slider_progress-fill {prefix}-slider_progress-fill"></div>
 *         </div>
 *         <div class="card-slider_arrow {prefix}-slider_arrow is-next" role="button" tabindex="0" aria-label="Next">
 *           <img class="slider-arrow-icon" src="..." alt="Next" loading="lazy">
 *         </div>
 *       </div>
 *     </div>
 *   </section>
 *
 * SHARED INFRASTRUCTURE CLASSES (from base.css — same on every slider):
 *   .card-slider_arrow     → 36px circle, border, hover states
 *   .card-slider_progress  → 2px track bar
 *   .card-slider_progress-fill → animated fill (indigo)
 *   .card-slider_nav       → flex container, gap: 16px
 *   .card-slider_clip      → overflow:hidden + breakout calc
 *
 * SECTION-SPECIFIC CLASSES (unique per slider — MANDATORY per components.md):
 *   {prefix}-slider_arrow, {prefix}-slider_progress, {prefix}-slider_progress-fill
 *   These MUST be added alongside shared classes for independent styling.
 *
 * @param {string} sectionSel  CSS selector for the section wrapper (e.g. '#courses')
 * @param {Object} opts        Configuration options:
 *   @param {string}  [opts.swiper]         Custom Swiper container selector (default: auto-detect)
 *   @param {string}  [opts.nav]            Custom nav container selector (default: auto-detect)
 *   @param {string}  [opts.fillId]         Fallback progress fill element ID
 *   @param {string}  [opts.slidesPerView]  Swiper slidesPerView (default: 'auto')
 *   @param {number}  [opts.spaceBetween]   Gap between slides in px (default: 16)
 *   @param {number}  [opts.speed]          Transition speed in ms (default: 600)
 *   @param {Object}  [opts.breakpoints]    Swiper breakpoint config (use BREAKPOINT_PRESETS)
 * @returns {Swiper|null} The Swiper instance or null if init failed
 */
function initCardSlider(sectionSel, opts) {
  if (typeof Swiper === 'undefined') return null;
  opts = opts || {};
  var section = document.querySelector(sectionSel);
  if (!section) return null;

  /* Find swiper container: explicit selector → .card-slider.swiper → .swiper */
  var swiperEl = opts.swiper ? document.querySelector(opts.swiper) : section.querySelector('.card-slider.swiper');
  if (!swiperEl) swiperEl = section.querySelector('.swiper');
  if (!swiperEl) return null;

  /* Find nav container: explicit selector → .card-slider_nav → section itself */
  var navEl = opts.nav ? document.querySelector(opts.nav) : section.querySelector('.card-slider_nav');
  if (!navEl) navEl = section;

  /* Init Swiper */
  var swiper = new Swiper(swiperEl, {
    slidesPerView: opts.slidesPerView || 'auto',
    spaceBetween: opts.spaceBetween || 16,
    speed: opts.speed || 600,
    grabCursor: true,
    freeMode: {
      enabled: true,
      sticky: false
    },
    breakpoints: opts.breakpoints || {}
  });

  /* Wire navigation arrows */
  var prevBtn = navEl.querySelector('.card-slider_arrow.is-prev');
  var nextBtn = navEl.querySelector('.card-slider_arrow.is-next');
  var progressFill = navEl.querySelector('.card-slider_progress-fill');
  if (!progressFill && opts.fillId) {
    progressFill = document.getElementById(opts.fillId);
  }
  if (prevBtn) prevBtn.addEventListener('click', function () {
    swiper.slidePrev();
  });
  if (nextBtn) nextBtn.addEventListener('click', function () {
    swiper.slideNext();
  });

  /* Wire progress bar */
  function updateProgress() {
    if (!progressFill || !swiper.slides || !swiper.slides.length) return;
    var progress = swiper.progress;
    if (isNaN(progress)) progress = 0;
    progress = Math.max(0, Math.min(1, progress));
    progressFill.style.width = progress * 100 + '%';
  }
  swiper.on('progress', updateProgress);
  swiper.on('slideChange', updateProgress);
  updateProgress();
  return swiper;
}

/**
 * Safely initialize sliders after Swiper CDN loads.
 * Tries: immediate → swiperReady event → polling (20x @ 100ms).
 *
 * @param {Function} callback  Function that calls initCardSlider() for each slider
 */
function ensureSwiperReady(callback) {
  if (typeof Swiper !== 'undefined') {
    callback();
    return;
  }

  /* Listen for custom event (fired by CDN loader IIFE) */
  document.addEventListener('swiperReady', callback, {
    once: true
  });

  /* Fallback: poll in case event already fired */
  var retries = 0;
  var timer = setInterval(function () {
    if (typeof Swiper !== 'undefined') {
      clearInterval(timer);
      callback();
    } else if (++retries >= 20) {
      clearInterval(timer);
    }
  }, 100);
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "shared/swiper-init.js", error: String((e && e.message) || e) }); }

// shared/utils.js
try { (() => {
/**
 * CEL Shared Utilities - REFERENCE IMPLEMENTATION
 * This file is NOT deployed to Webflow directly.
 * Individual functions are copy-pasted into separate IIFEs for deployment.
 * See each page's scripts.js for deployed versions.
 */

/* ── Motion Preference Detection (from Webflow Brand Studio) ── */
var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

/**
 * Check if user prefers reduced motion.
 * Use before adding scroll animations, auto-play, or transitions.
 * @returns {boolean} true if user prefers reduced motion
 */
function shouldReduceMotion() {
  return prefersReducedMotion.matches;
}

/* ── TOC Core — scroll-position tracking ── */
function initTocCore(options) {
  var opts = options || {};
  var tocLinks = document.querySelectorAll('.stoc_link[data-target]');
  var sectIds = [].slice.call(tocLinks).map(function (l) {
    return l.dataset.target;
  });
  var sections = sectIds.map(function (id) {
    return document.getElementById(id);
  }).filter(Boolean);
  if (!sections.length || !tocLinks.length) return null;
  var stocLabel = document.querySelector('.stoc_label');

  // Remove Webflow's hash-tracking
  tocLinks.forEach(function (l) {
    l.removeAttribute('href');
    l.setAttribute('tabindex', '0');
    l.setAttribute('role', 'link');
  });
  function setActive(id) {
    tocLinks.forEach(function (l) {
      var isActive = l.dataset.target === id;
      l.classList.toggle('is-active', isActive);
      var dot = l.querySelector('.stoc_dot');
      if (dot) dot.classList.toggle('is-active', isActive);
      /* Also on .stoc_text itself. The deployed bundle already does this (TOC-RESPONSIVE-SPEC
         §8); this copy did not, which is why `.stoc_text.is-active` was inert and the only
         thing painting the active row's text was a descendant selector in landing.css. Flat
         combo instead of a descendant rule = one Webflow style object. */
      var txt = l.querySelector('.stoc_text');
      if (txt) txt.classList.toggle('is-active', isActive);
    });
    if (stocLabel) {
      var active = [].slice.call(tocLinks).find(function (l) {
        return l.dataset.target === id;
      });
      if (active) {
        var textEl = active.querySelector('.stoc_text');
        stocLabel.textContent = textEl ? textEl.textContent.trim() : active.textContent.trim();
      }
    }
  }

  // Scroll spy
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) setActive(entry.target.id);
    });
  }, {
    rootMargin: '-20% 0px -75% 0px'
  });
  sections.forEach(function (s) {
    observer.observe(s);
  });

  // Click-to-scroll
  tocLinks.forEach(function (l) {
    l.addEventListener('click', function () {
      var target = document.getElementById(l.dataset.target);
      if (target) target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    });
    l.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        l.click();
      }
    });
  });

  // Set initial active
  if (sectIds.length) setActive(sectIds[0]);
  return {
    setActive: setActive,
    tocLinks: tocLinks,
    sections: sections
  };
}

/* ── TOC Mobile — floating tab + slide-out menu ── */
function initTocMobile(tocCore) {
  if (!tocCore) return;
  var stocComponent = document.querySelector('.stoc_component');
  var stocLabel = document.querySelector('.stoc_label');
  var stocNav = document.querySelector('.stoc_nav');
  if (!stocComponent || !stocLabel) return;
  var backdrop = document.createElement('div');
  backdrop.className = 'stoc_backdrop';
  /* Geometry set INLINE, not by a stylesheet: this element is created here at runtime and
     never exists in the Designer, so Webflow has nothing to hang a style object on and would
     publish no rule for it (TOC-RESPONSIVE-SPEC §10). Inline is the sanctioned route. */
  backdrop.style.cssText = 'display:none;position:fixed;inset:0;z-index:899;' + 'background:rgba(55,51,44,.06);-webkit-tap-highlight-color:transparent';
  document.body.appendChild(backdrop);
  var isOpen = false;
  function toggleMenu(open) {
    isOpen = typeof open === 'boolean' ? open : !isOpen;
    stocComponent.classList.toggle('is-menu-open', isOpen);
    stocLabel.classList.toggle('is-menu-open', isOpen);
    /* The open state has to reach .stoc_nav as a class ON .stoc_nav. `.stoc_component.is-menu-open
       .stoc_nav` is a descendant selector and a Webflow combo can never express it, so the class
       is flattened onto the element itself (TOC-RESPONSIVE-SPEC §10, change 1). */
    if (stocNav) stocNav.classList.toggle('is-menu-open', isOpen);
    backdrop.classList.toggle('is-visible', isOpen);
    backdrop.style.display = isOpen ? 'block' : 'none';
    document.body.style.overflow = isOpen ? 'hidden' : '';
  }
  stocLabel.addEventListener('click', function () {
    toggleMenu();
  });
  backdrop.addEventListener('click', function () {
    toggleMenu(false);
  });
  tocCore.tocLinks.forEach(function (l) {
    l.addEventListener('click', function () {
      if (window.innerWidth <= 991) toggleMenu(false);
    });
  });

  // Show/hide floating tab on scroll
  var lastScroll = 0;
  var heroHeight = document.querySelector('.section_hero') ? document.querySelector('.section_hero').offsetHeight : 400;
  window.addEventListener('scroll', function () {
    var scrollY = window.pageYOffset;
    stocComponent.classList.toggle('is-visible', scrollY > heroHeight);
    stocLabel.classList.toggle('is-visible', scrollY > heroHeight);
    lastScroll = scrollY;
  }, {
    passive: true
  });
}

/* ── FAQ Accordion ── */
function initFaqAccordion(containerSelector) {
  var container = document.querySelector(containerSelector || '.section_faq');
  if (!container) return;
  container.querySelectorAll('.faq_question').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('.faq_item');
      var answer = item.querySelector('.faq_answer');
      var isOpen = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', !isOpen);
      item.classList.toggle('is-open', !isOpen);
      if (!isOpen) {
        answer.style.maxHeight = answer.scrollHeight + 'px';
      } else {
        answer.style.maxHeight = '0';
      }
    });
  });
}

/* ── CEL Slider — reusable Swiper init with progress bar + arrows ── */
/* Usage: initCardSlider('.courses')  →  looks for .courses .card-slider, .courses .card-slider_arrow, etc. */
/* Or:    initCardSlider(null, { swiper: '.my_swiper', nav: '.my_nav' })  for custom selectors */
function initCardSlider(sectionSelector, options) {
  if (typeof Swiper === 'undefined') return null;
  var opts = options || {};
  var root = sectionSelector ? document.querySelector(sectionSelector) : document;
  if (!root) return null;
  var el = root.querySelector(opts.swiper || '.card-slider');
  if (!el) return null;
  var navRoot = opts.nav ? document.querySelector(opts.nav) : root;
  var prevBtn = navRoot.querySelector('.card-slider_arrow.is-prev');
  var nextBtn = navRoot.querySelector('.card-slider_arrow.is-next');
  var progressFill = navRoot.querySelector('.card-slider_progress-fill');

  /* Respect prefers-reduced-motion: disable slide transitions */
  var reducedSpeed = shouldReduceMotion() ? 0 : opts.speed || 500;
  var config = {
    slidesPerView: opts.slidesPerView || 1.15,
    spaceBetween: opts.spaceBetween || 4,
    grabCursor: true,
    speed: reducedSpeed,
    breakpoints: opts.breakpoints || {
      480: {
        slidesPerView: 1.5,
        spaceBetween: 4
      },
      768: {
        slidesPerView: 2.4,
        spaceBetween: 6
      },
      992: {
        slidesPerView: 3.2,
        spaceBetween: 6
      },
      1400: {
        slidesPerView: 3.8,
        spaceBetween: 8
      }
    }
  };
  var swiper = new Swiper(el, config);
  function updateNav() {
    if (!swiper) return;
    /* Use swiper.progress (0->1) — works reliably with slidesPerView: 'auto' */
    var p = swiper.progress;
    if (p < 0) p = 0;
    if (p > 1) p = 1;
    if (progressFill) progressFill.style.width = p * 100 + '%';
    if (prevBtn) prevBtn.classList.toggle('is-disabled', swiper.isBeginning);
    if (nextBtn) nextBtn.classList.toggle('is-disabled', swiper.isEnd);
  }
  swiper.on('slideChange', updateNav);
  swiper.on('progress', updateNav);
  swiper.on('resize', updateNav);
  swiper.on('reachEnd', updateNav);
  swiper.on('reachBeginning', updateNav);
  swiper.on('fromEdge', updateNav);
  updateNav();
  if (prevBtn) prevBtn.addEventListener('click', function () {
    swiper.slidePrev(config.speed);
  });
  if (nextBtn) nextBtn.addEventListener('click', function () {
    swiper.slideNext(config.speed);
  });
  return swiper;
}

/* ── Navbar Transparent Over Hero ── */
/* IX2-compatible: overrides Webflow's auto-fired inline background-color.
   Transparent while hero is visible, indigo-bright (#5d60ee) after scroll.
   CDN equivalent: celnavtoc3 handles this on Webflow production.
   Retries on sharedComponentsReady (navbar loaded via fetch in local dev). */
function initNavbarTransparent() {
  if (window.__celNt || window.__celNavDone) return;
  var n = document.querySelector('[data-wf--navbar--variant]');
  if (!n) return;
  /* Option-review builds stack two .section_hero blocks (A and B) until the hero section is picked,
     so the end of the hero zone is the LAST one. querySelector took the first and flipped the navbar
     to indigo while option B's hero was still on screen. Single-hero pages are unaffected. */
  var heroes = document.querySelectorAll('.section_hero');
  var hero = heroes[heroes.length - 1];
  if (!hero) return;
  /* Claim the guard only once BOTH nodes are in hand. THIS ORDERING IS THE BUG THAT MADE THE FOUR
     SAN DIEGO PAGES DISAGREE: the flag used to be set above the hero lookup, so any call that ran
     before the hero existed marked the behaviour "done" and it never bound a listener — the navbar
     then held whatever colour it had at load for the entire page. san-diego.html and costs.html
     escaped it only because their copy of this code lived in a page script that ran later. */
  window.__celNavDone = true;
  function check() {
    if (hero.getBoundingClientRect().bottom > 80) {
      n.style.setProperty('background-color', 'transparent', 'important');
    } else {
      n.style.setProperty('background-color', '#5d60ee', 'important');
    }
  }
  check();

  /* Both an IntersectionObserver AND a plain scroll listener, because each one alone has a measured
     dead zone:
     1. The original code coalesced scroll behind a `raf` flag. In a throttled or hidden frame the
        scheduled callback never fires, so the flag stayed true and check() was never called again
        after the FIRST scroll — the navbar held its load-time colour for the whole page.
     2. requestAnimationFrame AND IntersectionObserver are both suspended while
        document.visibilityState === 'hidden' (measured: rafRan 0, ioRan 0, setTimeout still 1), so an
        IO-only version cannot self-correct in a background frame either.
     A scroll listener with no rAF gate is one getBoundingClientRect per event, and the observer keeps
     it correct when the flip happens without a scroll (resize, layout shift, anchor jump). Whichever
     fires, both write the same value, so they cannot disagree.
     rootMargin -80px reproduces the `bottom > 80` threshold exactly: the hero stops intersecting once
     its bottom edge passes 80px below the top of the viewport. */
  window.addEventListener('scroll', check, {
    passive: true
  });
  window.addEventListener('resize', check, {
    passive: true
  });
  if (typeof IntersectionObserver === 'function') {
    new IntersectionObserver(function (entries) {
      n.style.setProperty('background-color', entries[0].isIntersecting ? 'transparent' : '#5d60ee', 'important');
    }, {
      rootMargin: '-80px 0px 0px 0px',
      threshold: 0
    }).observe(hero);
  }
  /* A hidden frame dispatches neither, so re-check the moment the page becomes visible. */
  document.addEventListener('visibilitychange', check);

  /* Strip Webflow w--current from hero CTA buttons */
  document.querySelectorAll('.hero_actions a').forEach(function (a) {
    a.classList.remove('w--current');
  });
}

/* ── Inline CTA Component Loader ── */
/* Usage: loadInlineCta({ title: '...', body: '...' }) */
/* Fetches shared/inline-cta.html, replaces {{TITLE}} and {{BODY}}, mounts into #inline-cta-mount */
function loadInlineCta(options) {
  var mount = document.getElementById('inline-cta-mount');
  if (!mount) return;
  var opts = options || {};
  var title = opts.title || mount.getAttribute('data-title') || '';
  var body = opts.body || mount.getAttribute('data-body') || '';
  fetch('../../shared/inline-cta.html').then(function (r) {
    return r.text();
  }).then(function (html) {
    var filled = html.replace('{{TITLE}}', title).replace('{{BODY}}', body);
    var tmp = document.createElement('div');
    tmp.innerHTML = filled;
    mount.parentNode.replaceChild(tmp.firstElementChild, mount);
  }).catch(function () {
    /* Fallback: render inline if fetch fails (e.g. file:// protocol) */
    mount.outerHTML = '<section class="section_inline-cta" id="apply">' + '<div class="inline-cta">' + '<div class="inline-cta-text">' + '<h2 class="inline-cta-title">' + title + '</h2>' + '<p class="inline-cta-body">' + body + '</p>' + '</div>' + '<div class="inline-cta-actions">' + '<a class="cta-btn-primary" href="https://www.englishcollege.com/contact-cel">Contact Us</a>' + '</div>' + '</div>' + '</section>';
  });
}

/* ── TOC Auto-Init — runs on every page that includes utils.js ── */
/* NOTE: __celNt is celnavtoc3 (navbar+dot polling only) — does NOT init TOC.
   So we must NOT gate on __celNt here. Only skip if TOC itself already ran. */
(function () {
  if (window.__celTocDone) return;
  window.__celTocDone = true;
  const tocCore = initTocCore();
  if (tocCore) initTocMobile(tocCore);
})();

/* ── Navbar Transparent Auto-Init ── */
/* Runs on every page. Retries after shared components load (navbar via fetch). */
(function () {
  initNavbarTransparent();
  document.addEventListener('sharedComponentsReady', initNavbarTransparent);
})();

/* ── TOC Dot Active Color Polling ── */
/* IX2 sets is-active async after scroll. Polling reads settled state.
   CDN equivalent: celnavtoc3 handles this on Webflow production. */
(function () {
  if (window.__celNt || window.__celTocDotDone) return;
  window.__celTocDotDone = true;
  function pd() {
    document.querySelectorAll('.stoc_dot').forEach(function (d) {
      var l = d.closest('.stoc_link');
      var on = l && l.classList.contains('is-active');
      d.style.backgroundColor = on ? '#e78b10' : '';
      d.style.borderColor = on ? '#e78b10' : '';
    });
  }
  setInterval(pd, 300);
  pd();
})();

/* ── TOC Link-Row Hover — shared (mirrors celtochov1 v2.0.0 on Webflow) ── */
/* Dot has :hover only on the 10px dot itself. Link-row hover must be JS,
   but INLINE styles conflict with celnavtoc3 polling (clears borderColor
   every 300ms). Toggle .is-hover combo class instead — immune to polling.
   Guard name matches celtochov1 CDN script — §12 of webflow-javascript.md. */
(function () {
  if (window.__celToh || window.__celTohDone) return;
  window.__celTohDone = true;
  function init() {
    const links = document.querySelectorAll('.stoc_link');
    if (!links.length) {
      setTimeout(init, 200);
      return;
    }
    links.forEach(function (l) {
      const d = l.querySelector('.stoc_dot');
      if (!d) return;
      /* is-hover goes on the dot AND the text, so the row-hover colour can be a flat combo
         (.stoc_text.is-hover) instead of `.stoc_link:hover .stoc_text` — which is a descendant
         selector the deploy pipeline drops. */
      const t = l.querySelector('.stoc_text');
      l.addEventListener('mouseenter', function () {
        if (!l.classList.contains('is-active')) {
          d.classList.add('is-hover');
          if (t) t.classList.add('is-hover');
        }
      });
      l.addEventListener('mouseleave', function () {
        d.classList.remove('is-hover');
        if (t) t.classList.remove('is-hover');
      });
    });
  }
  init();
})();

/* ── FAQ Accordion — Shared Component ── */
/* Cancels IX2 animations, toggles is-open on faq-item + faq-q + faq-icon */
(function () {
  if (window.__celFq || window.__celFaqDone) return;
  window.__celFaqDone = true;
  function cancelFaqAnimations() {
    document.querySelectorAll('.faq-body').forEach(function (b) {
      if (b.getAnimations) b.getAnimations().forEach(function (a) {
        a.cancel();
      });
    });
  }
  document.addEventListener('click', function (e) {
    var q = e.target.closest('.faq-q');
    if (!q) return;
    var clickedItem = q.closest('.faq-item');
    if (!clickedItem) return;
    var wasOpen = clickedItem.dataset.faqOpen === 'true';
    cancelFaqAnimations();
    document.querySelectorAll('.faq-item').forEach(function (item) {
      var body = item.querySelector('.faq-body');
      var btn = item.querySelector('.faq-q');
      var icon = item.querySelector('.faq-icon');
      item.dataset.faqOpen = 'false';
      item.classList.remove('is-open');
      if (btn) {
        btn.classList.remove('is-open');
        btn.setAttribute('aria-expanded', 'false');
      }
      if (icon) icon.classList.remove('is-open');
      if (body) body.style.maxHeight = '0px';
    });
    if (!wasOpen) {
      var body = clickedItem.querySelector('.faq-body');
      var inner = clickedItem.querySelector('.faq-body-inner');
      var btn = clickedItem.querySelector('.faq-q');
      var icon = clickedItem.querySelector('.faq-icon');
      clickedItem.dataset.faqOpen = 'true';
      clickedItem.classList.add('is-open');
      if (btn) {
        btn.classList.add('is-open');
        btn.setAttribute('aria-expanded', 'true');
      }
      if (icon) icon.classList.add('is-open');
      if (body && inner) body.style.maxHeight = inner.scrollHeight + 'px';
    }
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "shared/utils.js", error: String((e && e.message) || e) }); }

// ui_kits/website/AccommodationCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const accomStyles = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 20
  },
  card: {
    background: "var(--cream)",
    borderRadius: 20,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    transition: "transform 250ms cubic-bezier(0.34, 1.3, 0.64, 1)"
  },
  photo: {
    aspectRatio: "5 / 4",
    backgroundSize: "cover",
    backgroundPosition: "center",
    borderRadius: 20,
    margin: 12,
    position: "relative"
  },
  badge: {
    position: "absolute",
    top: 16,
    left: 16,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 1,
    textTransform: "uppercase",
    padding: "6px 12px",
    borderRadius: 100,
    background: "var(--cream-soft)",
    color: "var(--brown-deep)"
  },
  body: {
    padding: "8px 24px 24px"
  },
  pillRow: {
    display: "flex",
    gap: 6,
    marginBottom: 12
  },
  title: {
    fontFamily: "var(--font-heading)",
    fontSize: 24,
    fontWeight: 500,
    color: "var(--brown-deep)",
    margin: "0 0 8px",
    lineHeight: 1.2
  },
  desc: {
    fontFamily: "var(--font-body)",
    fontSize: 14,
    lineHeight: 1.55,
    color: "var(--brown-dark)",
    margin: "0 0 16px"
  },
  rows: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    marginBottom: 18
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 13,
    paddingBottom: 6,
    borderBottom: "1px solid var(--cream-medium)"
  },
  rowLabel: {
    color: "var(--brown-soft)",
    fontWeight: 500
  },
  rowValue: {
    color: "var(--brown-deep)",
    fontWeight: 600,
    fontVariantNumeric: "tabular-nums"
  },
  price: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    paddingTop: 8
  },
  priceNum: {
    fontFamily: "var(--font-body)",
    fontSize: 30,
    fontWeight: 600,
    color: "var(--brown-deep)",
    letterSpacing: -0.5
  },
  priceUnit: {
    fontSize: 12,
    color: "var(--brown-soft)"
  }
};
const ACCOM = [{
  photo: "https://images.unsplash.com/photo-1505691938895-1758d7feb511?w=900&q=70&auto=format",
  badge: "Most chosen",
  pills: ["Homestay", "Shared"],
  title: "Shared homestay",
  desc: "A private bedroom in a Canadian family's home, sharing the kitchen and living room with other students.",
  rows: [["Distance to school", "30–45 min"], ["Meals", "2 per day"], ["Stay length", "From 2 weeks"]],
  price: "1,840"
}, {
  photo: "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=900&q=70&auto=format",
  badge: "",
  pills: ["Homestay", "Private"],
  title: "Private homestay",
  desc: "A private bedroom and a private bathroom — and the whole family experience to yourself.",
  rows: [["Distance to school", "30–45 min"], ["Meals", "2 per day"], ["Stay length", "From 2 weeks"]],
  price: "2,140"
}, {
  photo: "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?w=900&q=70&auto=format",
  badge: "Walk to class",
  pills: ["Residence", "Studio"],
  title: "Student residence",
  desc: "A modern, fully furnished studio apartment with everything included — 15 minutes on foot from CEL.",
  rows: [["Distance to school", "15 min walk"], ["Meals", "Self-catered"], ["Stay length", "From 4 weeks"]],
  price: "1,990"
}];
function AccommodationCard({
  photo,
  badge,
  pills,
  title,
  desc,
  rows,
  price
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: accomStyles.card
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...accomStyles.photo,
      backgroundImage: `url(${photo})`
    }
  }, badge && /*#__PURE__*/React.createElement("span", {
    style: accomStyles.badge
  }, badge)), /*#__PURE__*/React.createElement("div", {
    style: accomStyles.body
  }, /*#__PURE__*/React.createElement("div", {
    style: accomStyles.pillRow
  }, pills.map(p => /*#__PURE__*/React.createElement(Pill, {
    key: p
  }, p))), /*#__PURE__*/React.createElement("h3", {
    style: accomStyles.title
  }, title), /*#__PURE__*/React.createElement("p", {
    style: accomStyles.desc
  }, desc), /*#__PURE__*/React.createElement("div", {
    style: accomStyles.rows
  }, rows.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: accomStyles.row
  }, /*#__PURE__*/React.createElement("span", {
    style: accomStyles.rowLabel
  }, k), /*#__PURE__*/React.createElement("span", {
    style: accomStyles.rowValue
  }, v)))), /*#__PURE__*/React.createElement("div", {
    style: accomStyles.price
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: accomStyles.priceNum
  }, "$", price, /*#__PURE__*/React.createElement("span", {
    style: accomStyles.priceUnit
  }, " / month"))), /*#__PURE__*/React.createElement(LinkButton, null, "Details"))));
}
function Accommodation() {
  return /*#__PURE__*/React.createElement("section", {
    className: "section"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "Where you'll live"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "Three ways to live, one easy booking."), /*#__PURE__*/React.createElement("p", {
    className: "section-intro",
    style: {
      marginBottom: 48
    }
  }, "We help you book your stay in the same form as your course \u2014 no separate agents, no hidden fees, no surprises on arrival."), /*#__PURE__*/React.createElement("div", {
    style: accomStyles.grid
  }, ACCOM.map(a => /*#__PURE__*/React.createElement(AccommodationCard, _extends({
    key: a.title
  }, a))))));
}
Object.assign(window, {
  Accommodation,
  AccommodationCard
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/AccommodationCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/BentoCampus.jsx
try { (() => {
const bentoStyles = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(12, 1fr)",
    gridAutoRows: "180px",
    gap: 16
  },
  tile: {
    position: "relative",
    borderRadius: 20,
    overflow: "hidden",
    backgroundSize: "cover",
    backgroundPosition: "center",
    color: "var(--cream-soft)",
    transition: "transform 250ms cubic-bezier(0.34, 1.3, 0.64, 1)"
  },
  overlay: {
    position: "absolute",
    inset: 0,
    background: "linear-gradient(to top, rgba(30,28,50,0.78) 0%, rgba(30,28,50,0.0) 55%)"
  },
  tileBody: {
    position: "absolute",
    left: 24,
    right: 24,
    bottom: 22,
    zIndex: 2
  },
  title: {
    fontFamily: "var(--font-heading)",
    fontSize: 22,
    fontWeight: 500,
    color: "var(--cream-soft)",
    margin: 0,
    lineHeight: 1.2
  },
  desc: {
    fontFamily: "var(--font-body)",
    fontSize: 13,
    lineHeight: 1.5,
    color: "rgba(249, 241, 223, 0.85)",
    margin: "6px 0 0"
  },
  textTile: {
    background: "var(--cream)",
    borderRadius: 20,
    padding: 28,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between"
  },
  textTitle: {
    fontFamily: "var(--font-heading)",
    fontSize: 26,
    fontWeight: 500,
    color: "var(--brown-deep)",
    margin: 0,
    lineHeight: 1.15
  },
  textDesc: {
    fontFamily: "var(--font-body)",
    fontSize: 14,
    lineHeight: 1.55,
    color: "var(--brown-dark)",
    margin: "10px 0 0"
  }
};
const TILES = [{
  kind: "photo",
  span: "span 7 / span 7",
  row: "span 2",
  photo: "https://images.unsplash.com/photo-1497486751825-1233686d5d80?w=1200&q=70&auto=format",
  title: "A campus in the heart of downtown.",
  desc: "Two minutes from the SeaBus, five from English Bay."
}, {
  kind: "text",
  span: "span 5 / span 5",
  row: "span 1",
  title: "What you get.",
  desc: "Free Wi-Fi, two student lounges, kitchen with microwaves and fridges, quiet study rooms."
}, {
  kind: "photo",
  span: "span 5 / span 5",
  row: "span 1",
  photo: "https://images.unsplash.com/photo-1554995207-c18c203602cb?w=1000&q=70&auto=format",
  title: "Student lounge",
  desc: ""
}, {
  kind: "photo",
  span: "span 4 / span 4",
  row: "span 2",
  photo: "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=900&q=70&auto=format",
  title: "Vancouver, your classroom.",
  desc: "Stanley Park, Granville Island, the seawall — all within walking distance."
}, {
  kind: "photo",
  span: "span 4 / span 4",
  row: "span 1",
  photo: "https://images.unsplash.com/photo-1580130775562-0ef92da028de?w=900&q=70&auto=format",
  title: "Quiet study rooms",
  desc: ""
}, {
  kind: "photo",
  span: "span 4 / span 4",
  row: "span 1",
  photo: "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=900&q=70&auto=format",
  title: "Mornings outside",
  desc: ""
}];
function BentoCampus() {
  return /*#__PURE__*/React.createElement("section", {
    className: "section",
    style: {
      background: "var(--cream-soft)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "Your campus"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "A small school, a big city."), /*#__PURE__*/React.createElement("p", {
    className: "section-intro",
    style: {
      marginBottom: 48
    }
  }, "One campus, downtown Vancouver. Built for studying \u2014 not for selling tours."), /*#__PURE__*/React.createElement("div", {
    style: bentoStyles.grid
  }, TILES.map((t, i) => t.kind === "photo" ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      ...bentoStyles.tile,
      gridColumn: t.span,
      gridRow: t.row,
      backgroundImage: `url(${t.photo})`
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: bentoStyles.overlay
  }), /*#__PURE__*/React.createElement("div", {
    style: bentoStyles.tileBody
  }, /*#__PURE__*/React.createElement("h3", {
    style: bentoStyles.title
  }, t.title), t.desc && /*#__PURE__*/React.createElement("p", {
    style: bentoStyles.desc
  }, t.desc))) : /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      ...bentoStyles.textTile,
      gridColumn: t.span,
      gridRow: t.row
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", {
    style: bentoStyles.textTitle
  }, t.title), /*#__PURE__*/React.createElement("p", {
    style: bentoStyles.textDesc
  }, t.desc)), /*#__PURE__*/React.createElement(LinkButton, null, "See full tour"))))));
}
Object.assign(window, {
  BentoCampus
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/BentoCampus.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Comparison.jsx
try { (() => {
const cmpStyles = {
  wrap: {
    background: "var(--cream)",
    borderRadius: 28,
    padding: 32,
    marginTop: 32
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 32,
    position: "relative"
  },
  vs: {
    position: "absolute",
    top: 220,
    left: "50%",
    transform: "translate(-50%, -50%)",
    width: 64,
    height: 64,
    borderRadius: "50%",
    background: "var(--orange-gold)",
    color: "var(--cream-extra-light)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-heading)",
    fontSize: 22,
    fontWeight: 500,
    letterSpacing: 1,
    zIndex: 2
  },
  col: {
    display: "flex",
    flexDirection: "column",
    gap: 18
  },
  photo: {
    height: 220,
    borderRadius: 20,
    backgroundSize: "cover",
    backgroundPosition: "center",
    position: "relative"
  },
  cityName: {
    position: "absolute",
    left: 20,
    bottom: 20,
    zIndex: 2,
    fontFamily: "var(--font-heading)",
    fontSize: 24,
    fontWeight: 500,
    color: "var(--cream-soft)",
    margin: 0,
    textShadow: "0 2px 8px rgba(0,0,0,0.4)"
  },
  pgrad: {
    position: "absolute",
    inset: 0,
    borderRadius: 20,
    background: "linear-gradient(to top, rgba(30,28,50,0.55), rgba(30,28,50,0))"
  },
  rows: {
    display: "flex",
    flexDirection: "column",
    gap: 14
  },
  row: {
    display: "flex",
    alignItems: "flex-start",
    gap: 12
  },
  metric: {
    fontFamily: "var(--font-body)",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: "var(--brown-soft)"
  },
  value: {
    fontFamily: "var(--font-body)",
    fontSize: 20,
    fontWeight: 600,
    color: "var(--brown-deep)",
    lineHeight: 1.25,
    margin: "2px 0 0",
    letterSpacing: -0.2
  },
  valueMuted: {
    color: "var(--brown-muted)"
  },
  block: {
    flex: 1,
    paddingBottom: 14,
    borderBottom: "1px solid var(--cream-medium)"
  }
};
function CmpRow({
  icon,
  metric,
  value,
  muted
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      ...cmpStyles.row
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 4,
      color: muted ? "var(--brown-muted)" : "var(--indigo-bright)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    id: icon,
    size: 22
  })), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.block
  }, /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.metric
  }, metric), /*#__PURE__*/React.createElement("div", {
    style: {
      ...cmpStyles.value,
      ...(muted ? cmpStyles.valueMuted : {})
    }
  }, value)));
}
function Comparison() {
  return /*#__PURE__*/React.createElement("section", {
    className: "section",
    style: {
      background: "var(--cream-soft)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "Vancouver vs Toronto"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "Which Canadian city fits you better?"), /*#__PURE__*/React.createElement("p", {
    className: "section-intro"
  }, "The honest, side-by-side answer \u2014 based on real numbers from the cities, not marketing claims."), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.wrap
  }, /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.grid
  }, /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.vs
  }, "VS"), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.col
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...cmpStyles.photo,
      backgroundImage: "url(https://images.unsplash.com/photo-1559511260-66a654ae982a?w=900&q=70&auto=format)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.pgrad
  }), /*#__PURE__*/React.createElement("h3", {
    style: cmpStyles.cityName
  }, "Vancouver")), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.rows
  }, /*#__PURE__*/React.createElement(CmpRow, {
    icon: "dollar",
    metric: "Avg monthly cost",
    value: "$2,180 CAD"
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "sun",
    metric: "Sunny days / year",
    value: "289 days"
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "users",
    metric: "ESL students",
    value: "62,000+"
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "pin",
    metric: "Distance to nature",
    value: "Beach & mountains, 20 min"
  }))), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.col
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...cmpStyles.photo,
      backgroundImage: "url(https://images.unsplash.com/photo-1517090504586-fde19ea6066f?w=900&q=70&auto=format)",
      filter: "grayscale(100%)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.pgrad
  }), /*#__PURE__*/React.createElement("h3", {
    style: cmpStyles.cityName
  }, "Toronto")), /*#__PURE__*/React.createElement("div", {
    style: cmpStyles.rows
  }, /*#__PURE__*/React.createElement(CmpRow, {
    icon: "dollar",
    metric: "Avg monthly cost",
    value: "$2,640 CAD",
    muted: true
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "snowflake",
    metric: "Sunny days / year",
    value: "237 days",
    muted: true
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "users",
    metric: "ESL students",
    value: "74,000+",
    muted: true
  }), /*#__PURE__*/React.createElement(CmpRow, {
    icon: "pin",
    metric: "Distance to nature",
    value: "Lake; mountains 1.5 hrs",
    muted: true
  })))))));
}
Object.assign(window, {
  Comparison
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Comparison.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Courses.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const courseStyles = {
  card: {
    width: 320,
    background: "var(--cream)",
    borderRadius: 20,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    transition: "transform 250ms cubic-bezier(0.34, 1.3, 0.64, 1)"
  },
  photo: {
    aspectRatio: "4 / 3",
    background: "var(--cream-medium)",
    backgroundSize: "cover",
    backgroundPosition: "center",
    borderRadius: 20,
    margin: 12
  },
  body: {
    padding: "8px 24px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    flex: 1
  },
  pillRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap"
  },
  title: {
    fontFamily: "var(--font-heading)",
    fontSize: 22,
    fontWeight: 500,
    color: "var(--brown-deep)",
    margin: 0,
    lineHeight: 1.2
  },
  desc: {
    fontFamily: "var(--font-body)",
    fontSize: 14,
    lineHeight: 1.55,
    color: "var(--brown-dark)",
    margin: 0
  },
  meta: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    paddingTop: 16,
    borderTop: "1px solid var(--cream-medium)",
    marginTop: "auto"
  },
  price: {
    fontFamily: "var(--font-body)",
    fontSize: 24,
    fontWeight: 600,
    color: "var(--brown-deep)",
    letterSpacing: -0.4
  },
  perWeek: {
    fontSize: 12,
    color: "var(--brown-soft)",
    letterSpacing: 0.3
  }
};
function CourseCard({
  photo,
  tags,
  title,
  desc,
  price
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: courseStyles.card
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...courseStyles.photo,
      backgroundImage: `url(${photo})`
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: courseStyles.body
  }, /*#__PURE__*/React.createElement("div", {
    style: courseStyles.pillRow
  }, tags.map(t => /*#__PURE__*/React.createElement(Pill, {
    key: t
  }, t))), /*#__PURE__*/React.createElement("h3", {
    style: courseStyles.title
  }, title), /*#__PURE__*/React.createElement("p", {
    style: courseStyles.desc
  }, desc), /*#__PURE__*/React.createElement("div", {
    style: courseStyles.meta
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: courseStyles.price
  }, "$", price), /*#__PURE__*/React.createElement("div", {
    style: courseStyles.perWeek
  }, "per week \xB7 from")), /*#__PURE__*/React.createElement(LinkButton, null, "Details"))));
}
const COURSES = [{
  photo: "https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=600&q=70&auto=format",
  tags: ["Most popular", "16+"],
  title: "General English",
  desc: "Build confidence through daily conversation. 25 lessons per week, all levels A1–C1.",
  price: "315"
}, {
  photo: "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=600&q=70&auto=format",
  tags: ["B2+", "Exam prep"],
  title: "IELTS Preparation",
  desc: "Targeted practice for all four IELTS skills. Includes 2 full mock exams per month.",
  price: "375"
}, {
  photo: "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&q=70&auto=format",
  tags: ["Pathway", "B1+"],
  title: "University Pathway",
  desc: "Conditional admission to 25+ Canadian colleges and universities. Academic English focus.",
  price: "395"
}, {
  photo: "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=600&q=70&auto=format",
  tags: ["Speaking", "All levels"],
  title: "Conversation Plus",
  desc: "An extra 10 lessons per week of speaking practice with rotating teachers.",
  price: "175"
}, {
  photo: "https://images.unsplash.com/photo-1515187029135-18ee286d815b?w=600&q=70&auto=format",
  tags: ["Summer", "Youth"],
  title: "Summer Youth",
  desc: "For students 13–17. Mornings of class, afternoons of activities. June–August.",
  price: "395"
}];
function Courses() {
  const [page, setPage] = React.useState(0);
  const stripRef = React.useRef(null);
  const max = COURSES.length - 2;
  const move = dir => {
    const next = Math.max(0, Math.min(max, page + dir));
    setPage(next);
    stripRef.current?.scrollTo({
      left: next * 326,
      behavior: "smooth"
    });
  };
  return /*#__PURE__*/React.createElement("section", {
    className: "section",
    style: {
      paddingTop: 120,
      paddingBottom: 120
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "Our courses"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "Pick the course that fits your goal."), /*#__PURE__*/React.createElement("p", {
    className: "section-intro",
    style: {
      marginBottom: 48
    }
  }, "Every course starts on a Monday. You can begin at any level, switch programs after week one, and add private lessons as you go."), /*#__PURE__*/React.createElement("div", {
    className: "slider-strip",
    ref: stripRef
  }, COURSES.map(c => /*#__PURE__*/React.createElement(CourseCard, _extends({
    key: c.title
  }, c)))), /*#__PURE__*/React.createElement("div", {
    className: "slider-controls"
  }, /*#__PURE__*/React.createElement("button", {
    className: "slider-arrow",
    onClick: () => move(-1),
    disabled: page === 0,
    "aria-label": "Previous"
  }, /*#__PURE__*/React.createElement(Icon, {
    id: "chevron-left",
    size: 20
  })), /*#__PURE__*/React.createElement("button", {
    className: "slider-arrow",
    onClick: () => move(1),
    disabled: page >= max,
    "aria-label": "Next"
  }, /*#__PURE__*/React.createElement(Icon, {
    id: "chevron-right",
    size: 20
  })), /*#__PURE__*/React.createElement("div", {
    className: "slider-progress"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: `${(page + 1) / (max + 1) * 100}%`
    }
  })))));
}
Object.assign(window, {
  Courses,
  CourseCard
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Courses.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/FAQ.jsx
try { (() => {
const faqStyles = {
  wrap: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    maxWidth: 880
  },
  item: {
    background: "var(--cream-soft)",
    borderRadius: 16,
    padding: "20px 24px",
    cursor: "pointer",
    transition: "background-color 200ms ease"
  },
  itemOpen: {
    background: "var(--cream-extra-light)"
  },
  row: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16
  },
  q: {
    fontFamily: "var(--font-heading)",
    fontSize: 19,
    fontWeight: 500,
    color: "var(--brown-deep)",
    margin: 0,
    lineHeight: 1.3,
    flex: 1
  },
  chev: {
    color: "var(--brown-soft)",
    transition: "transform 250ms ease"
  },
  chevOpen: {
    transform: "rotate(180deg)",
    color: "var(--orange-gold)"
  },
  a: {
    fontFamily: "var(--font-body)",
    fontSize: 15,
    lineHeight: 1.65,
    color: "var(--brown-dark)",
    margin: "12px 0 0",
    maxWidth: "60ch"
  }
};
const FAQS = [{
  q: "How long does it take to improve one CEFR level?",
  a: "For most students, 12–16 weeks of full-time study moves you up one CEFR level (e.g., B1 to B2). Speaking and listening usually improve faster than reading and writing. We test you in week one and again every six weeks so you can see your progress."
}, {
  q: "Do I need a Canadian study permit?",
  a: "Courses up to 24 weeks can be taken on a visitor visa or eTA, depending on your nationality. Programs longer than 24 weeks need a study permit. We give you the official enrollment letter once you pay your deposit, which is what immigration asks for."
}, {
  q: "What's included in the homestay program?",
  a: "A private bedroom in a Canadian family's home, two meals a day, all utilities, Wi-Fi, and weekly laundry. Homestays are 30–45 minutes from CEL by transit. Your monthly transit pass is not included — that's $104 CAD."
}, {
  q: "Can I work while I study?",
  a: "On a study permit, you can work up to 24 hours per week off-campus. On a visitor visa, you cannot work in Canada. Most students who plan to work take a 25+ week course so they qualify for the study permit."
}, {
  q: "Do you place me in the right level?",
  a: "On your first morning at CEL, you take a 90-minute placement test (writing + speaking). We share your level the same afternoon and you start class the next day. If after one week the level feels wrong, we move you — no extra charge."
}];
function FAQ() {
  const [open, setOpen] = React.useState(0);
  return /*#__PURE__*/React.createElement("section", {
    className: "section"
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "Common questions"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "Real questions, real answers."), /*#__PURE__*/React.createElement("p", {
    className: "section-intro",
    style: {
      marginBottom: 40
    }
  }, "The five things students ask us every single week. Anything else? ", /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, "Send us a message"), "."), /*#__PURE__*/React.createElement("div", {
    style: faqStyles.wrap
  }, FAQS.map((f, i) => {
    const isOpen = open === i;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        ...faqStyles.item,
        ...(isOpen ? faqStyles.itemOpen : {})
      },
      onClick: () => setOpen(isOpen ? -1 : i)
    }, /*#__PURE__*/React.createElement("div", {
      style: faqStyles.row
    }, /*#__PURE__*/React.createElement("h3", {
      style: faqStyles.q
    }, f.q), /*#__PURE__*/React.createElement("span", {
      style: {
        ...faqStyles.chev,
        ...(isOpen ? faqStyles.chevOpen : {})
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      id: "chevron-down",
      size: 22
    }))), isOpen && /*#__PURE__*/React.createElement("p", {
      style: faqStyles.a
    }, f.a));
  }))));
}
Object.assign(window, {
  FAQ
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/FAQ.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Footer.jsx
try { (() => {
const footerStyles = {
  root: {
    background: "var(--cream)",
    padding: "80px 84px 40px"
  },
  inner: {
    maxWidth: 1600,
    margin: "0 auto"
  },
  top: {
    display: "grid",
    gridTemplateColumns: "2fr 1fr 1fr 1fr",
    gap: 48,
    paddingBottom: 48,
    borderBottom: "1px solid var(--cream-medium)"
  },
  brand: {
    display: "flex",
    flexDirection: "column",
    gap: 18
  },
  logoRow: {
    display: "flex",
    alignItems: "center",
    gap: 12
  },
  logoText: {
    fontFamily: "var(--font-heading)",
    fontSize: 18,
    color: "var(--brown-deep)",
    fontWeight: 500,
    letterSpacing: 0.3,
    lineHeight: 1.15
  },
  about: {
    fontSize: 14,
    lineHeight: 1.65,
    color: "var(--brown-dark)",
    maxWidth: 36,
    maxWidth: "36ch"
  },
  colTitle: {
    fontFamily: "var(--font-body)",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    color: "var(--brown-soft)",
    margin: "0 0 18px"
  },
  link: {
    display: "block",
    fontSize: 14,
    color: "var(--brown-dark)",
    textDecoration: "none",
    padding: "5px 0"
  },
  bottom: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: 28,
    fontSize: 12,
    color: "var(--brown-soft)"
  },
  bottomLinks: {
    display: "flex",
    gap: 24
  }
};
function Footer() {
  return /*#__PURE__*/React.createElement("footer", {
    style: footerStyles.root
  }, /*#__PURE__*/React.createElement("div", {
    style: footerStyles.inner
  }, /*#__PURE__*/React.createElement("div", {
    style: footerStyles.top
  }, /*#__PURE__*/React.createElement("div", {
    style: footerStyles.brand
  }, /*#__PURE__*/React.createElement("div", {
    style: footerStyles.logoRow
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logos/cel-logo-multicolor.svg",
    alt: "CEL",
    style: {
      width: 44,
      height: 44
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: footerStyles.logoText
  }, "Canadian English", /*#__PURE__*/React.createElement("br", null), "Language College")), /*#__PURE__*/React.createElement("p", {
    style: footerStyles.about
  }, "Teaching English in downtown Vancouver since 1980. Independently owned, family-run, accredited by Languages Canada."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Pill, null, "Languages Canada"), /*#__PURE__*/React.createElement(Pill, null, "DLI accredited"))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: footerStyles.colTitle
  }, "Programs"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "General English"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "IELTS Preparation"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "University Pathway"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Conversation Plus"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Summer Youth")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: footerStyles.colTitle
  }, "About CEL"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Our school"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Teachers"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Accreditations"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Reviews"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "Blog")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: footerStyles.colTitle
  }, "Contact"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "469 Howe St, Vancouver"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "+1 (604) 683-2150"), /*#__PURE__*/React.createElement("a", {
    style: footerStyles.link,
    href: "#"
  }, "hello@canadianenglish.com"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 18
    }
  }, /*#__PURE__*/React.createElement(PrimaryButton, null, "Apply now")))), /*#__PURE__*/React.createElement("div", {
    style: footerStyles.bottom
  }, /*#__PURE__*/React.createElement("span", null, "\xA9 1980\u20132026 Canadian English Language College"), /*#__PURE__*/React.createElement("div", {
    style: footerStyles.bottomLinks
  }, /*#__PURE__*/React.createElement("a", {
    style: {
      ...footerStyles.link,
      padding: 0
    },
    href: "#"
  }, "Privacy"), /*#__PURE__*/React.createElement("a", {
    style: {
      ...footerStyles.link,
      padding: 0
    },
    href: "#"
  }, "Terms"), /*#__PURE__*/React.createElement("a", {
    style: {
      ...footerStyles.link,
      padding: 0
    },
    href: "#"
  }, "Cookies")))));
}
Object.assign(window, {
  Footer
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Footer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Hero.jsx
try { (() => {
const heroStyles = {
  root: {
    position: "relative",
    minHeight: "100vh",
    minHeight: "100svh",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    justifyContent: "flex-end",
    paddingBottom: 80,
    paddingLeft: 84,
    paddingRight: 84,
    paddingTop: 120
  },
  bg: {
    position: "absolute",
    inset: 0,
    zIndex: 0,
    backgroundImage: "url(https://images.unsplash.com/photo-1609825488888-3a766db05542?w=1920&q=80&auto=format)",
    backgroundSize: "cover",
    backgroundPosition: "center"
  },
  overlay: {
    position: "absolute",
    inset: 0,
    zIndex: 1,
    background: "linear-gradient(to bottom, rgba(30,28,50,0.45) 0%, rgba(30,28,50,0.05) 30%, rgba(30,28,50,0.05) 50%, rgba(30,28,50,0.7) 100%)"
  },
  content: {
    position: "relative",
    zIndex: 2,
    maxWidth: 1600,
    margin: "0 auto",
    width: "100%"
  },
  breadcrumb: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    background: "rgba(30,28,50,0.45)",
    backdropFilter: "blur(10px)",
    WebkitBackdropFilter: "blur(10px)",
    color: "var(--cream-soft)",
    fontFamily: "var(--font-body)",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    padding: "8px 16px",
    borderRadius: 100,
    marginBottom: 24
  },
  title: {
    fontFamily: "var(--font-heading)",
    fontWeight: 500,
    fontSize: 64,
    lineHeight: 1.05,
    letterSpacing: 0.5,
    color: "var(--cream-soft)",
    margin: "0 0 24px",
    maxWidth: "16ch"
  },
  subtitle: {
    fontFamily: "var(--font-body)",
    fontSize: 18,
    lineHeight: 1.6,
    color: "rgba(249, 241, 223, 0.88)",
    margin: "0 0 36px",
    maxWidth: 56,
    maxWidth: "56ch"
  },
  ctas: {
    display: "flex",
    gap: 14,
    flexWrap: "wrap",
    marginBottom: 48
  },
  pillsGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 14,
    maxWidth: 720
  },
  hilightPill: {
    background: "rgba(249, 241, 223, 0.08)",
    backdropFilter: "blur(10px)",
    WebkitBackdropFilter: "blur(10px)",
    border: "1px solid rgba(249, 241, 223, 0.18)",
    borderRadius: 16,
    padding: "14px 18px",
    display: "flex",
    alignItems: "center",
    gap: 14,
    color: "var(--cream-soft)"
  },
  hpNum: {
    fontFamily: "var(--font-body)",
    fontSize: 30,
    fontWeight: 500,
    color: "var(--cream-soft)",
    lineHeight: 1,
    letterSpacing: -0.5
  },
  hpLabel: {
    fontFamily: "var(--font-body)",
    fontSize: 13,
    lineHeight: 1.4,
    color: "rgba(249, 241, 223, 0.85)"
  }
};
function HighlightPill({
  num,
  label
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: heroStyles.hilightPill
  }, /*#__PURE__*/React.createElement("span", {
    style: heroStyles.hpNum
  }, num), /*#__PURE__*/React.createElement("span", {
    style: heroStyles.hpLabel
  }, label));
}
function Hero() {
  return /*#__PURE__*/React.createElement("section", {
    style: heroStyles.root
  }, /*#__PURE__*/React.createElement("div", {
    style: heroStyles.bg,
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("div", {
    style: heroStyles.overlay,
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("div", {
    style: heroStyles.content
  }, /*#__PURE__*/React.createElement("div", {
    style: heroStyles.breadcrumb
  }, /*#__PURE__*/React.createElement(Icon, {
    id: "pin",
    size: 12
  }), " Vancouver, BC \xB7 Adults 16+"), /*#__PURE__*/React.createElement("h1", {
    style: heroStyles.title
  }, "English courses in Vancouver, made for real progress."), /*#__PURE__*/React.createElement("p", {
    style: heroStyles.subtitle
  }, "Small classes. Real conversations. A clear plan to move from where you are to where you want to be \u2014 at your own pace, in a city you'll love."), /*#__PURE__*/React.createElement("div", {
    style: heroStyles.ctas
  }, /*#__PURE__*/React.createElement(PrimaryButton, null, "Apply now"), /*#__PURE__*/React.createElement(GhostButton, null, "Book a free call")), /*#__PURE__*/React.createElement("div", {
    style: heroStyles.pillsGrid
  }, /*#__PURE__*/React.createElement(HighlightPill, {
    num: "7",
    label: "Average students per class"
  }), /*#__PURE__*/React.createElement(HighlightPill, {
    num: "12",
    label: "Max class size"
  }), /*#__PURE__*/React.createElement(HighlightPill, {
    num: "45",
    label: "Years teaching English in Vancouver"
  }), /*#__PURE__*/React.createElement(HighlightPill, {
    num: "60+",
    label: "Nationalities on campus this year"
  }))));
}
Object.assign(window, {
  Hero
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Hero.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Nav.jsx
try { (() => {
const navStyles = {
  nav: {
    position: "sticky",
    top: 0,
    zIndex: 50,
    background: "rgba(249, 241, 223, 0.92)",
    backdropFilter: "blur(16px)",
    WebkitBackdropFilter: "blur(16px)",
    borderBottom: "1px solid var(--cream-medium)"
  },
  inner: {
    maxWidth: 1600,
    margin: "0 auto",
    padding: "16px 84px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 24
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    textDecoration: "none"
  },
  logoImg: {
    width: 38,
    height: 38
  },
  logoText: {
    fontFamily: "var(--font-heading)",
    fontSize: 18,
    color: "var(--brown-deep)",
    fontWeight: 500,
    letterSpacing: 0.3,
    lineHeight: 1.1
  },
  nav_links: {
    display: "flex",
    gap: 28,
    alignItems: "center"
  },
  link: {
    fontFamily: "var(--font-body)",
    fontSize: 14,
    fontWeight: 500,
    color: "var(--brown-dark)",
    textDecoration: "none",
    transition: "color 150ms ease"
  },
  cta: {
    display: "flex",
    gap: 10,
    alignItems: "center"
  },
  langPill: {
    fontFamily: "var(--font-body)",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: "var(--brown-deep)",
    background: "var(--cream)",
    padding: "8px 14px",
    borderRadius: 100,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    cursor: "pointer",
    border: "none"
  }
};
function Nav({
  active = "Courses"
}) {
  const items = ["Courses", "Accommodation", "Why Vancouver", "Costs", "About"];
  return /*#__PURE__*/React.createElement("nav", {
    style: navStyles.nav,
    "aria-label": "Main"
  }, /*#__PURE__*/React.createElement("div", {
    style: navStyles.inner
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: navStyles.logo
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logos/cel-logo-multicolor.svg",
    alt: "CEL",
    style: navStyles.logoImg
  }), /*#__PURE__*/React.createElement("div", {
    style: navStyles.logoText
  }, "Canadian English", /*#__PURE__*/React.createElement("br", null), "Language College")), /*#__PURE__*/React.createElement("div", {
    style: navStyles.nav_links
  }, items.map(i => /*#__PURE__*/React.createElement("a", {
    key: i,
    href: "#",
    style: {
      ...navStyles.link,
      color: i === active ? "var(--indigo-bright)" : "var(--brown-dark)"
    }
  }, i))), /*#__PURE__*/React.createElement("div", {
    style: navStyles.cta
  }, /*#__PURE__*/React.createElement("button", {
    style: navStyles.langPill
  }, /*#__PURE__*/React.createElement(Icon, {
    id: "globe",
    size: 14
  }), " EN"), /*#__PURE__*/React.createElement(PrimaryButton, null, "Apply now"))));
}
Object.assign(window, {
  Nav
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Nav.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Testimonials.jsx
try { (() => {
const tStyles = {
  card: {
    width: 380,
    padding: 28,
    background: "var(--cream)",
    borderRadius: 20,
    display: "flex",
    flexDirection: "column",
    gap: 14
  },
  stars: {
    display: "flex",
    gap: 2,
    color: "var(--star-gold)"
  },
  quote: {
    fontFamily: "var(--font-body)",
    fontSize: 17,
    lineHeight: 1.55,
    color: "var(--brown-deep)",
    margin: 0,
    fontWeight: 400
  },
  author: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginTop: 8
  },
  flag: {
    width: 24,
    height: 18,
    borderRadius: 3,
    flexShrink: 0
  },
  name: {
    fontFamily: "var(--font-body)",
    fontSize: 14,
    fontWeight: 600,
    color: "var(--brown-deep)"
  },
  role: {
    fontSize: 12,
    color: "var(--brown-soft)"
  }
};
const flagBR = {
  background: "linear-gradient(to bottom, #002776 0 33%, #fedf00 33% 66%, #009c3b 66% 100%)"
};
const flagKR = {
  background: "white",
  border: "1px solid var(--cream-medium)"
};
const flagJP = {
  background: "white",
  border: "1px solid var(--cream-medium)",
  position: "relative"
};
const flagDE = {
  background: "linear-gradient(to bottom, #000 0 33%, #DD0000 33% 66%, #FFCE00 66% 100%)"
};
const flagES = {
  background: "linear-gradient(to bottom, #AA151B 0 25%, #F1BF00 25% 75%, #AA151B 75% 100%)"
};
const TESTIMONIALS = [{
  quote: "My class had only six students. I spoke English every day, not just listened. After 14 weeks I went from B1 to B2.",
  name: "Mariana, São Paulo",
  role: "14-week General English · 2025",
  flag: flagBR
}, {
  quote: "The teachers remember your goals. Mine was IELTS 7. I got 7.5 in eight weeks of preparation.",
  name: "Ji-woo, Seoul",
  role: "8-week IELTS Prep · 2025",
  flag: flagKR
}, {
  quote: "I was scared to start, but homestay was the best decision. My host family corrected me every dinner — kindly.",
  name: "Yuto, Osaka",
  role: "24-week Pathway · 2024",
  flag: flagJP
}, {
  quote: "Small enough that everyone knows your name. The administration helped me with my visa extension in one week.",
  name: "Lukas, Berlin",
  role: "32-week Pathway · 2024",
  flag: flagDE
}, {
  quote: "Vancouver is the best city to study English. Mountains, beaches, and people from everywhere — all in one bus ride.",
  name: "Sofía, Madrid",
  role: "12-week General English · 2025",
  flag: flagES
}];
function Testimonial({
  t
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: tStyles.card
  }, /*#__PURE__*/React.createElement("div", {
    style: tStyles.stars
  }, [...Array(5)].map((_, i) => /*#__PURE__*/React.createElement(Icon, {
    key: i,
    id: "star",
    size: 16
  }))), /*#__PURE__*/React.createElement("p", {
    style: tStyles.quote
  }, t.quote), /*#__PURE__*/React.createElement("div", {
    style: tStyles.author
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      ...tStyles.flag,
      ...t.flag
    }
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: tStyles.name
  }, t.name), /*#__PURE__*/React.createElement("div", {
    style: tStyles.role
  }, t.role))));
}
function Testimonials() {
  return /*#__PURE__*/React.createElement("section", {
    className: "section",
    style: {
      background: "var(--cream-soft)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "section-inner"
  }, /*#__PURE__*/React.createElement(Tagline, null, "What students say"), /*#__PURE__*/React.createElement("h2", {
    className: "section-title"
  }, "Honest reviews from real CEL students."), /*#__PURE__*/React.createElement("p", {
    className: "section-intro",
    style: {
      marginBottom: 40
    }
  }, "Pulled straight from Google. We don't pay students to review us, and we don't filter the bad ones."), /*#__PURE__*/React.createElement("div", {
    className: "slider-strip"
  }, TESTIMONIALS.map((t, i) => /*#__PURE__*/React.createElement(Testimonial, {
    key: i,
    t: t
  })))));
}
Object.assign(window, {
  Testimonials
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Testimonials.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/ui.jsx
try { (() => {
// Shared primitives — Tagline, PrimaryButton, GhostButton, Pill, Icon
function Tagline({
  children,
  className = ""
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: `tagline ${className}`
  }, children);
}
function PrimaryButton({
  children,
  onClick,
  href
}) {
  const Tag = href ? "a" : "button";
  return /*#__PURE__*/React.createElement(Tag, {
    className: "btn btn-primary",
    onClick: onClick,
    href: href
  }, children);
}
function GhostButton({
  children,
  onClick,
  href
}) {
  const Tag = href ? "a" : "button";
  return /*#__PURE__*/React.createElement(Tag, {
    className: "btn btn-ghost",
    onClick: onClick,
    href: href
  }, children);
}
function LinkButton({
  children,
  onClick,
  href
}) {
  const Tag = href ? "a" : "button";
  return /*#__PURE__*/React.createElement(Tag, {
    className: "btn btn-link",
    onClick: onClick,
    href: href
  }, children, /*#__PURE__*/React.createElement(Icon, {
    id: "arrow-right",
    size: 16
  }));
}
function Pill({
  children,
  variant
}) {
  const cls = variant === "dark" ? "pill is-on-dark" : variant === "indigo" ? "pill is-indigo" : "pill";
  return /*#__PURE__*/React.createElement("span", {
    className: cls
  }, children);
}

// inline svg icons (sprite is in /assets/icons/sprite.svg but we inline the small set we need)
const ICONS = {
  "arrow-right": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M5 12h14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M13 5l7 7-7 7"
  })),
  "arrow-up-right": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M7 17L17 7"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 7h9v9"
  })),
  "chevron-right": /*#__PURE__*/React.createElement("path", {
    d: "M9 6l6 6-6 6"
  }),
  "chevron-left": /*#__PURE__*/React.createElement("path", {
    d: "M15 6l-6 6 6 6"
  }),
  "chevron-down": /*#__PURE__*/React.createElement("path", {
    d: "M6 9l6 6 6-6"
  }),
  "plus": /*#__PURE__*/React.createElement("path", {
    d: "M12 5v14M5 12h14"
  }),
  "clock": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 7v5l3.5 2"
  })),
  "calendar": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
    x: "3.5",
    y: "5",
    width: "17",
    height: "16",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3.5 10h17M8 3v4M16 3v4"
  })),
  "users": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "9",
    cy: "9",
    r: "3.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 19c0-3 2.5-5 6-5s6 2 6 5"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "17",
    cy: "9",
    r: "2.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17 14c2.5 0 4 1.4 4 4"
  })),
  "graduation": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M2 9l10-5 10 5-10 5L2 9z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"
  })),
  "book": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M19 17H6a2 2 0 00-2 2"
  })),
  "globe": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 12h18"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 3a14 14 0 010 18M12 3a14 14 0 000 18"
  })),
  "pin": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M12 21s7-7 7-12a7 7 0 10-14 0c0 5 7 12 7 12z"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "9",
    r: "2.5"
  })),
  "home": /*#__PURE__*/React.createElement("path", {
    d: "M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6h-6v6H4a1 1 0 01-1-1v-9z"
  }),
  "menu": /*#__PURE__*/React.createElement("path", {
    d: "M4 7h16M4 12h16M4 17h16"
  }),
  "close": /*#__PURE__*/React.createElement("path", {
    d: "M6 6l12 12M18 6L6 18"
  }),
  "search": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "6.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M16 16l4 4"
  })),
  "play": /*#__PURE__*/React.createElement("path", {
    d: "M7 4l13 8-13 8V4z"
  }),
  "dollar": /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M12 2v20"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.5 9.2 9.5 12 10s5 1.5 5 3.5-2.2 3-5 3-5-1.1-5-3"
  })),
  "star": /*#__PURE__*/React.createElement("path", {
    d: "M12 3l2.7 5.8 6.3.8-4.7 4.4 1.2 6.4L12 17.7 6.5 20.4l1.2-6.4L3 9.6l6.3-.8L12 3z"
  })
};
function Icon({
  id,
  size = 24,
  fill
}) {
  const isFilled = id === "play" || id === "star";
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: isFilled ? fill || "currentColor" : "none",
    stroke: isFilled ? "none" : "currentColor",
    strokeWidth: "1.75",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true"
  }, ICONS[id]);
}
function StatTile({
  num,
  unit,
  label,
  title,
  icon
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "stat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "stat-num"
  }, num, unit && /*#__PURE__*/React.createElement("small", null, unit)), /*#__PURE__*/React.createElement("div", {
    className: "stat-label"
  }, label), /*#__PURE__*/React.createElement("p", {
    className: "stat-title"
  }, title), icon && /*#__PURE__*/React.createElement("div", {
    className: "stat-icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    id: icon,
    size: 80
  })));
}
Object.assign(window, {
  Tagline,
  PrimaryButton,
  GhostButton,
  LinkButton,
  Pill,
  Icon,
  StatTile
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/ui.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Button = __ds_scope.Button;

__ds_ns.TEAM = __ds_scope.TEAM;

__ds_ns.CHRIS_PHOTO = __ds_scope.CHRIS_PHOTO;

})();
