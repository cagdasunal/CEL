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
   5. celtocmob2 v1.0.0
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
(function(){if(window.__swR)return;window.__swR=1;var s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js';s.onload=function(){window.__swOK=true;document.dispatchEvent(new Event('swiperReady'))};document.head.appendChild(s);var l=document.createElement('link');l.rel='stylesheet';l.href='https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css';document.head.appendChild(l)})();

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
   5. celtocmob2 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce76bdaf1388e4c4f64191%2Fceltocmob2-1.0.0.js
   ============================================================ */
(function(){var sc=document.querySelector('.stoc_component'),sl=document.querySelector('.stoc_label');if(!sc||!sl)return;var nv=document.querySelector('.navbar_component'),hs=document.querySelector('.section_hero'),tl=[].slice.call(document.querySelectorAll('.stoc_link[data-target]')),ss=tl.map(function(l){return document.getElementById(l.dataset.target);}).filter(Boolean),ls=ss[ss.length-1],bd=document.createElement('div'),nh=nv?nv.offsetHeight:80;bd.className='stoc_backdrop';document.body.appendChild(bd);function cm(){sc.classList.remove('is-menu-open');bd.classList.remove('is-visible');}function uv(){var hb=hs?hs.getBoundingClientRect().bottom:-1,lb=ls?ls.getBoundingClientRect().bottom:1e9;if(hb<nh+20&&lb>nh+40)sc.classList.add('is-visible');else{sc.classList.remove('is-visible');cm();}}window.addEventListener('scroll',uv,{passive:true});uv();sl.addEventListener('click',function(){var o=sc.classList.toggle('is-menu-open');bd.classList.toggle('is-visible',o);});bd.addEventListener('click',cm);tl.forEach(function(l){l.addEventListener('click',cm);});})();

/* ============================================================
   6. vstslider v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ce8a7bbfcfca73ffb93c9e%2Fvstslider-1.0.0.js
   ============================================================ */
(function(){if(window.__vstSlider)return;window.__vstSlider=true;function go(){if(typeof Swiper==='undefined')return;var g=document.querySelector('.vst_gallery-slider');var thumbs=document.querySelectorAll('.vst_thumb');var cc=document.querySelector('.vst_gallery-current');if(!g||!thumbs.length)return;var sw=new Swiper(g,{slidesPerView:1,spaceBetween:0,speed:1200,loop:true,grabCursor:true,effect:'fade',fadeEffect:{crossFade:true},autoplay:{delay:5000,disableOnInteraction:false,pauseOnMouseEnter:true}});function setActive(i){thumbs.forEach(function(t){t.classList.remove('is-active')});if(thumbs[i])thumbs[i].classList.add('is-active');if(cc)cc.textContent=String(i+1).padStart(2,'0')}setActive(0);sw.on('slideChange',function(){setActive(sw.realIndex)});thumbs.forEach(function(t){t.addEventListener('click',function(){sw.slideToLoop(parseInt(t.getAttribute('data-index'),10),1200)})})}if(typeof Swiper!=='undefined'){go();return}document.addEventListener('swiperReady',go,{once:true});var r=0;var tm=setInterval(function(){if(typeof Swiper!=='undefined'){clearInterval(tm);go()}else if(++r>=20)clearInterval(tm)},100)})();

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
