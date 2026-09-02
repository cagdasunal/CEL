/*!
 * cel-duration-guide.js — CEL Vancouver / Duration Guide
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-duration-guide.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-duration-guide.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-duration-guide.min.js
 *
 * Bundles 7 scripts (was previously 7 inline-registered Webflow scripts):
   1. celnavtoc3 v1.0.0
   2. celfaq1 v1.0.0
   3. celtoc1 v1.0.0
   4. celtocmob3 v2.0.0
   5. dg40cefr v1.0.0
   6. dg27extras v1.0.0
   7. celtochov1 v2.0.0
 *
 * Each section is the verbatim source captured from the live Webflow CDN
 * on 2026-04-30 (see tools/cel-page-scripts/sources/manifest.json).
 *
 * Migration date: 2026-04-30. See rules/cel-page-scripts-deploy.md.
 */

/* ============================================================
   1. celnavtoc3 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c3b65e7f1bbaa658ac1132%2Fcelnavtoc3-1.0.0.js
   ============================================================ */
(function(){if(window.__celNt)return;window.__celNt=true;var n=document.querySelector('[data-wf--navbar--variant="transparent"]'),h=document.querySelector('.section_hero');if(n&&h){var mo=new MutationObserver(function(){if(h.getBoundingClientRect().bottom<=80)return;mo.disconnect();n.style.removeProperty('background-color');mo.observe(n,{attributes:true,attributeFilter:['style']});});mo.observe(n,{attributes:true,attributeFilter:['style']});var r=0;window.addEventListener('scroll',function(){if(r)return;r=1;requestAnimationFrame(function(){if(h.getBoundingClientRect().bottom>80){mo.disconnect();n.style.removeProperty('background-color');mo.observe(n,{attributes:true,attributeFilter:['style']});}r=0;});},{passive:true});if(h.getBoundingClientRect().bottom>80)n.style.removeProperty('background-color');}function fb(){document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current').forEach(function(b){b.classList.remove('w--current');});}setInterval(fb,300);fb();if(document.querySelector('.stoc_dot')){function ft(){document.querySelectorAll('.stoc_dot').forEach(function(d){var l=d.closest('.stoc_link');var a=l&&l.classList.contains('is-active');d.style.backgroundColor=a?'#e78b10':'';d.style.borderColor=a?'#e78b10':'';});}setInterval(ft,300);ft();}})();

/* ============================================================
   2. celfaq1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c2c4d097c0c97fc7d27f81%2Fcelfaq1-1.0.0.js
   ============================================================ */
(function(){if(window.__celFq)return;window.__celFq=true;if(!document.querySelector('.faq-item'))return;function ca(){['.faq-body','.faq-icon','.faq-q'].forEach(function(s){document.querySelectorAll(s).forEach(function(e){if(e.getAnimations)e.getAnimations().forEach(function(a){a.cancel();});});});}document.addEventListener('click',function(e){var q=e.target.closest('.faq-q');if(!q)return;var it=q.closest('.faq-item');if(!it)return;var wo=it.dataset.faqOpen==='true';ca();document.querySelectorAll('.faq-item').forEach(function(i){var b=i.querySelector('.faq-body'),t=i.querySelector('.faq-q'),c=i.querySelector('.faq-icon');i.dataset.faqOpen='false';i.classList.remove('is-open');if(t){t.classList.remove('is-open');t.setAttribute('aria-expanded','false');}if(c)c.classList.remove('is-open');if(b)b.style.maxHeight='0px';});if(!wo){var b=it.querySelector('.faq-body'),m=it.querySelector('.faq-body-inner'),t=it.querySelector('.faq-q'),c=it.querySelector('.faq-icon');it.dataset.faqOpen='true';it.classList.add('is-open');if(t){t.classList.add('is-open');t.setAttribute('aria-expanded','true');}if(c)c.classList.add('is-open');if(b&&m)b.style.maxHeight=m.scrollHeight+'px';}});})();

/* ============================================================
   3. celtoc1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce7f61e5dc51c9eebb606a%2Fceltoc1-1.0.0.js
   ============================================================ */
(function(){if(window.__celToc)return;window.__celToc=window.__celTocDone=true;var tl=[].slice.call(document.querySelectorAll('.stoc_link[data-target]'));if(!tl.length)return;var si=tl.map(function(l){return l.dataset.target});var ss=si.map(function(id){return document.getElementById(id)}).filter(Boolean);if(!ss.length)return;var nv=document.querySelector('.navbar_component'),sl=document.querySelector('.stoc_label');tl.forEach(function(l){l.removeAttribute('href');l.setAttribute('tabindex','0')});function sa(id){tl.forEach(function(l){var a=l.dataset.target===id,d=l.querySelector('.stoc_dot'),t=l.querySelector('.stoc_text');l.classList.toggle('is-active',a);if(d)d.classList.toggle('is-active',a);if(t)t.classList.toggle('is-active',a)});if(sl){var a=tl.find(function(l){return l.dataset.target===id});if(a){var t=a.querySelector('.stoc_text');sl.textContent=t?t.textContent.trim():a.textContent.trim()}}}function da(){var r=(nv?nv.offsetHeight:90)+40,ai=ss[0].id;ss.forEach(function(s){if(s.getBoundingClientRect().top<=r)ai=s.id});sa(ai)}var rp=0;window.addEventListener('scroll',function(){if(rp)return;rp=1;requestAnimationFrame(function(){da();rp=0})},{passive:true});tl.forEach(function(l){l.addEventListener('click',function(e){e.preventDefault();var t=document.getElementById(l.dataset.target);if(!t)return;sa(l.dataset.target);window.scrollTo({top:t.getBoundingClientRect().top+window.scrollY-(nv?nv.offsetHeight:90)-24,behavior:'smooth'})});l.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();l.click()}})});var h=location.hash.replace('#','');if(si.indexOf(h)!==-1)sa(h);else da()})();

/* ============================================================
   4. celtocmob3 v2.0.0 — mobile TOC drawer (<=991px)
   Replaces celtocmob2 v1.0.0, which put `is-menu-open` on
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
   always worked.
   ============================================================ */
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

/* ============================================================
   5. dg40cefr v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c2a9ac96104cbab09532b4%2Fdg40cefr-1.0.0.js
   ============================================================ */
(function(){if(window.__dg40cefr)return;window.__dg40cefr=true;var DATA={a1:{bg:'#e6be00',w:'33%'},a2:{bg:'#ff9800',w:'44%'},b1:{bg:'#5d60ee',w:'61%'},b2:{bg:'#5d60ee',w:'67%'},c1:{bg:'#4caf50',w:'100%'}};var rows=document.querySelectorAll('.cefr-row');if(!rows.length)return;rows.forEach(function(r){var lvl=r.dataset.level;var d=DATA[lvl];var bar=r.querySelector('.cefr-bar');if(bar&&d){bar.style.backgroundColor=d.bg;bar.style.width=d.w;}});var done=false;var io=new IntersectionObserver(function(e){if(!e[0].isIntersecting||done)return;done=true;rows.forEach(function(r,i){var bar=r.querySelector('.cefr-bar');if(!bar)return;if(bar.getAnimations)bar.getAnimations().forEach(function(a){a.cancel();});bar.animate([{transform:'scaleX(0)'},{transform:'scaleX(1)'}],{delay:i*90,duration:900,easing:'cubic-bezier(0.16,1,0.3,1)',fill:'forwards'});});io.disconnect();},{threshold:0.25});io.observe(rows[0]);})();

/* ============================================================
   6. dg27extras v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c289b27c58ea835aa2d2ed%2Fdg27extras-1.0.0.js
   ============================================================ */
(function(){if(window.__dg27ext)return;window.__dg27ext=true;var rail=document.querySelector('.pathway-rail');var dots=document.querySelectorAll('.pathway-dot');if(rail&&dots.length>=2){var mq=window.matchMedia('(max-width:767px)');function sizeRail(){if(!mq.matches){rail.style.height='';return;}var f=dots[0].getBoundingClientRect();var l=dots[dots.length-1].getBoundingClientRect();rail.style.height=(l.top+l.height/2-f.top-f.height/2)+'px';}sizeRail();window.addEventListener('resize',sizeRail);}var el=document.querySelector('.compare-table');if(el){var isDown=false,startX,scrollL;el.addEventListener('mousedown',function(e){if(el.scrollWidth<=el.clientWidth)return;isDown=true;el.classList.add('is-dragging');startX=e.pageX-el.offsetLeft;scrollL=el.scrollLeft;});el.addEventListener('mouseleave',function(){isDown=false;el.classList.remove('is-dragging');});el.addEventListener('mouseup',function(){isDown=false;el.classList.remove('is-dragging');});el.addEventListener('mousemove',function(e){if(!isDown)return;e.preventDefault();el.scrollLeft=scrollL-(e.pageX-el.offsetLeft-startX);});}})();

/* ============================================================
   7. celtochov1 v2.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ea49589152839d8d25a714%2Fceltochov1-2.0.0.js
   ============================================================ */
(function(){if(window.__celToh)return;window.__celToh=true;function init(){var ls=document.querySelectorAll('.stoc_link');if(!ls.length){setTimeout(init,200);return}ls.forEach(function(l){var d=l.querySelector('.stoc_dot');if(!d)return;l.addEventListener('mouseenter',function(){if(!l.classList.contains('is-active'))d.classList.add('is-hover')});l.addEventListener('mouseleave',function(){d.classList.remove('is-hover')})})}if(document.readyState!=='loading')init();else document.addEventListener('DOMContentLoaded',init)})();
