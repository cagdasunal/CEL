/*!
 * cel-vs-toronto.js — CEL Vancouver / VS Toronto
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-vs-toronto.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-vs-toronto.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-vs-toronto.min.js
 *
 * Bundles 9 scripts (was previously 9 inline-registered Webflow scripts):
   1. a16swipercdn v3.0.0
   2. celnavtoc3 v1.0.0
   3. celfaq1 v1.0.0
   4. celtoc1 v1.0.0
   5. celtocmob3 v2.0.0
   6. vstslider v1.0.0
   7. vstcompare v1.0.0
   8. celvideo1 v1.0.0
   9. celtochov1 v2.0.0
 *
 * Each section is the verbatim source captured from the live Webflow CDN
 * on 2026-04-30 (see tools/cel-page-scripts/sources/manifest.json).
 *
 * Migration date: 2026-04-30. See rules/cel-page-scripts-deploy.md.
 */

/* ============================================================
   1. a16swipercdn v3.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ba51a3905cc67b376c23af%2Fa16swipercdn-3.0.0.js
   ============================================================ */
(function(){if(window.__swR)return;window.__swR=1;var s=document.createElement('script');s.src='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.js';s.onload=function(){window.__swOK=true;document.dispatchEvent(new Event('swiperReady'))};document.head.appendChild(s);var l=document.createElement('link');l.rel='stylesheet';l.href='https://cel.englishcollege.com/scripts/vendor/swiper@11/swiper-bundle.min.css';document.head.appendChild(l)})();

/* ============================================================
   2. celnavtoc3 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c3b65e7f1bbaa658ac1132%2Fcelnavtoc3-1.0.0.js
   ============================================================ */
(function(){if(window.__celNt)return;window.__celNt=true;var n=document.querySelector('[data-wf--navbar--variant="transparent"]'),h=document.querySelector('.section_hero');if(n&&h){var mo=new MutationObserver(function(){if(h.getBoundingClientRect().bottom<=80)return;mo.disconnect();n.style.removeProperty('background-color');mo.observe(n,{attributes:true,attributeFilter:['style']});});mo.observe(n,{attributes:true,attributeFilter:['style']});var r=0;window.addEventListener('scroll',function(){if(r)return;r=1;requestAnimationFrame(function(){if(h.getBoundingClientRect().bottom>80){mo.disconnect();n.style.removeProperty('background-color');mo.observe(n,{attributes:true,attributeFilter:['style']});}r=0;});},{passive:true});if(h.getBoundingClientRect().bottom>80)n.style.removeProperty('background-color');}function fb(){document.querySelectorAll('.hero_cta-ghost.w--current,.hero_cta-primary.w--current').forEach(function(b){b.classList.remove('w--current');});}setInterval(fb,300);fb();if(document.querySelector('.stoc_dot')){function ft(){document.querySelectorAll('.stoc_dot').forEach(function(d){var l=d.closest('.stoc_link');var a=l&&l.classList.contains('is-active');d.style.backgroundColor=a?'#e78b10':'';d.style.borderColor=a?'#e78b10':'';});}setInterval(ft,300);ft();}})();

/* ============================================================
   3. celfaq1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c2c4d097c0c97fc7d27f81%2Fcelfaq1-1.0.0.js
   ============================================================ */
(function(){if(window.__celFq)return;window.__celFq=true;if(!document.querySelector('.faq-item'))return;function ca(){['.faq-body','.faq-icon','.faq-q'].forEach(function(s){document.querySelectorAll(s).forEach(function(e){if(e.getAnimations)e.getAnimations().forEach(function(a){a.cancel();});});});}document.addEventListener('click',function(e){var q=e.target.closest('.faq-q');if(!q)return;var it=q.closest('.faq-item');if(!it)return;var wo=it.dataset.faqOpen==='true';ca();document.querySelectorAll('.faq-item').forEach(function(i){var b=i.querySelector('.faq-body'),t=i.querySelector('.faq-q'),c=i.querySelector('.faq-icon');i.dataset.faqOpen='false';i.classList.remove('is-open');if(t){t.classList.remove('is-open');t.setAttribute('aria-expanded','false');}if(c)c.classList.remove('is-open');if(b)b.style.maxHeight='0px';});if(!wo){var b=it.querySelector('.faq-body'),m=it.querySelector('.faq-body-inner'),t=it.querySelector('.faq-q'),c=it.querySelector('.faq-icon');it.dataset.faqOpen='true';it.classList.add('is-open');if(t){t.classList.add('is-open');t.setAttribute('aria-expanded','true');}if(c)c.classList.add('is-open');if(b&&m)b.style.maxHeight=m.scrollHeight+'px';}});})();

/* ============================================================
   4. celtoc1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce7f61e5dc51c9eebb606a%2Fceltoc1-1.0.0.js
   ============================================================ */
(function(){if(window.__celToc)return;window.__celToc=window.__celTocDone=true;var tl=[].slice.call(document.querySelectorAll('.stoc_link[data-target]'));if(!tl.length)return;var si=tl.map(function(l){return l.dataset.target});var ss=si.map(function(id){return document.getElementById(id)}).filter(Boolean);if(!ss.length)return;var nv=document.querySelector('.navbar_component'),sl=document.querySelector('.stoc_label');tl.forEach(function(l){l.removeAttribute('href');l.setAttribute('tabindex','0')});function sa(id){tl.forEach(function(l){var a=l.dataset.target===id,d=l.querySelector('.stoc_dot'),t=l.querySelector('.stoc_text');l.classList.toggle('is-active',a);if(d)d.classList.toggle('is-active',a);if(t)t.classList.toggle('is-active',a)});if(sl){var a=tl.find(function(l){return l.dataset.target===id});if(a){var t=a.querySelector('.stoc_text');sl.textContent=t?t.textContent.trim():a.textContent.trim()}}}function da(){var r=(nv?nv.offsetHeight:90)+40,ai=ss[0].id;ss.forEach(function(s){if(s.getBoundingClientRect().top<=r)ai=s.id});sa(ai)}var rp=0;window.addEventListener('scroll',function(){if(rp)return;rp=1;requestAnimationFrame(function(){da();rp=0})},{passive:true});tl.forEach(function(l){l.addEventListener('click',function(e){e.preventDefault();var t=document.getElementById(l.dataset.target);if(!t)return;sa(l.dataset.target);window.scrollTo({top:t.getBoundingClientRect().top+window.scrollY-(nv?nv.offsetHeight:90)-24,behavior:'smooth'})});l.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();l.click()}})});var h=location.hash.replace('#','');if(si.indexOf(h)!==-1)sa(h);else da()})();

/* ============================================================
   5. celtocmob3 v2.0.0 — mobile TOC drawer (<=991px)
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
   6. vstslider v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce8a7bbfcfca73ffb93c9e%2Fvstslider-1.0.0.js
   ============================================================ */
(function(){if(window.__vstSlider)return;window.__vstSlider=true;function bootstrap(g,thumbs){if(g.querySelector('.swiper-wrapper'))return;g.classList.add('swiper');const wrap=document.createElement('div');wrap.className='swiper-wrapper';thumbs.forEach(function(t){const slide=document.createElement('div');slide.className='swiper-slide';const ti=t.querySelector('.vst_thumb-img');if(ti){const im=ti.cloneNode(false);im.classList.remove('vst_thumb-img');im.classList.add('vst_gallery-img');if(im.alt)im.alt=im.alt.replace(/\s*thumbnail\s*$/i,'');slide.appendChild(im)}wrap.appendChild(slide)});while(g.firstChild)g.removeChild(g.firstChild);g.appendChild(wrap);const ctr=document.createElement('div');ctr.className='vst_gallery-counter';const cur=document.createElement('p');cur.className='vst_gallery-current';cur.textContent='01';const div=document.createElement('div');div.className='vst_gallery-divider';const tot=document.createElement('p');tot.className='vst_gallery-total';tot.textContent=String(thumbs.length).padStart(2,'0');ctr.appendChild(cur);ctr.appendChild(div);ctr.appendChild(tot);g.appendChild(ctr)}function go(){if(typeof Swiper==='undefined')return;const g=document.querySelector('.vst_gallery-slider');const thumbs=document.querySelectorAll('.vst_thumb');if(!g||!thumbs.length)return;bootstrap(g,thumbs);const cc=document.querySelector('.vst_gallery-current');const sw=new Swiper(g,{slidesPerView:1,spaceBetween:0,speed:1200,loop:true,grabCursor:true,effect:'fade',fadeEffect:{crossFade:true},autoplay:{delay:5000,disableOnInteraction:false,pauseOnMouseEnter:true}});function setActive(i){thumbs.forEach(function(t){t.classList.remove('is-active')});if(thumbs[i])thumbs[i].classList.add('is-active');if(cc)cc.textContent=String(i+1).padStart(2,'0')}setActive(0);sw.on('slideChange',function(){setActive(sw.realIndex)});thumbs.forEach(function(t,i){t.addEventListener('click',function(){const di=parseInt(t.getAttribute('data-index'),10);sw.slideToLoop(isNaN(di)?i:di,1200)})})}if(typeof Swiper!=='undefined'){go();return}document.addEventListener('swiperReady',go,{once:true});let r=0;const tm=setInterval(function(){if(typeof Swiper!=='undefined'){clearInterval(tm);go()}else if(++r>=20)clearInterval(tm)},100)})();

/* ============================================================
   7. vstcompare v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce8a9c0c03fe141023a1f8%2Fvstcompare-1.0.0.js
   ============================================================ */
(function(){if(window.__vstCompare)return;window.__vstCompare=true;var els=document.querySelectorAll('.compare_component');if(els.length&&'IntersectionObserver'in window){var obs=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('is-visible');obs.unobserve(e.target)}})},{threshold:0.3});els.forEach(function(el){obs.observe(el)})}els.forEach(function(el){var isDown=false,startX,scrollL;function checkScrollable(){var isNow=el.scrollWidth>el.clientWidth;el.classList.toggle('is-scrollable',isNow);if(isNow)el.scrollLeft=0}checkScrollable();window.addEventListener('resize',checkScrollable);el.addEventListener('mousedown',function(e){if(el.scrollWidth<=el.clientWidth)return;isDown=true;el.classList.add('is-dragging');startX=e.pageX-el.offsetLeft;scrollL=el.scrollLeft});el.addEventListener('mouseleave',function(){isDown=false;el.classList.remove('is-dragging')});el.addEventListener('mouseup',function(){isDown=false;el.classList.remove('is-dragging')});el.addEventListener('mousemove',function(e){if(!isDown)return;e.preventDefault();el.scrollLeft=scrollL-((e.pageX-el.offsetLeft)-startX)})})})();

/* ============================================================
   8. celvideo1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69e4e6f0b8de5cf2df0cdee6%2Fcelvideo1-1.0.0.js
   ============================================================ */
(function(){if(window.__celVideoPlayer)return;window.__celVideoPlayer=true;function initPlayer(player){if(player.__celVideoInit)return;player.__celVideoInit=true;const btn=player.querySelector('.video_play-btn');const thumb=player.querySelector('.video_thumbnail');if(!btn&&!thumb)return;let loaded=false;function loadVideo(e){if(e&&e.preventDefault)e.preventDefault();if(loaded)return;const id=player.getAttribute('data-vimeo-id');if(!id)return;loaded=true;const iframe=document.createElement('iframe');iframe.className='video_embed';iframe.src='https://player.vimeo.com/video/'+id+'?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';iframe.setAttribute('frameborder','0');iframe.setAttribute('allow','autoplay; fullscreen; picture-in-picture');iframe.setAttribute('allowfullscreen','');iframe.title=player.getAttribute('data-video-title')||'CEL Vancouver — English Language School';if(thumb)thumb.remove();if(btn)btn.remove();player.appendChild(iframe);}if(btn)btn.addEventListener('click',loadVideo);if(thumb)thumb.addEventListener('click',loadVideo);}const players=document.querySelectorAll('.video_player[data-vimeo-id]');for(let i=0;i<players.length;i++)initPlayer(players[i]);})();

/* ============================================================
   9. celtochov1 v2.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ea49589152839d8d25a714%2Fceltochov1-2.0.0.js
   ============================================================ */
(function(){if(window.__celToh)return;window.__celToh=true;function init(){var ls=document.querySelectorAll('.stoc_link');if(!ls.length){setTimeout(init,200);return}ls.forEach(function(l){var d=l.querySelector('.stoc_dot');if(!d)return;l.addEventListener('mouseenter',function(){if(!l.classList.contains('is-active'))d.classList.add('is-hover')});l.addEventListener('mouseleave',function(){d.classList.remove('is-hover')})})}if(document.readyState!=='loading')init();else document.addEventListener('DOMContentLoaded',init)})();
