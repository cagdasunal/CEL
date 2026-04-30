/*!
 * cel-costs.js — CEL Vancouver / Costs
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-costs.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-costs.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-costs.min.js
 *
 * Bundles 9 scripts (was previously 9 inline-registered Webflow scripts):
   1. a16swipercdn v3.0.0
   2. celnavtoc3 v1.0.0
   3. celfaq1 v1.0.0
   4. celtoc1 v1.0.0
   5. celtocmob2 v1.0.0
   6. costsswiper3 v1.0.0
   7. costspricebar1 v1.0.0
   8. costsbudget1 v1.0.0
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
   6. costsswiper3 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c97e7b0afc6e9a3566a24f%2Fcostsswiper3-1.0.0.js
   ============================================================ */
(function(){if(window.__costsSw3)return;window.__costsSw3=true;function iS(sE,nE,o){if(typeof Swiper==='undefined'||!sE)return null;sE.classList.add('swiper');var sw=new Swiper(sE,{slidesPerView:o.spv||'auto',spaceBetween:o.sb||16,speed:o.speed||600,grabCursor:true,freeMode:{enabled:true,sticky:false},breakpoints:o.bps||{}});var pB=nE?nE.querySelector('.card-slider_arrow.is-prev'):null;var nB=nE?nE.querySelector('.card-slider_arrow.is-next'):null;var fl=nE?nE.querySelector('.card-slider_progress-fill'):null;if(pB)pB.addEventListener('click',function(){sw.slidePrev();});if(nB)nB.addEventListener('click',function(){sw.slideNext();});function pg(){if(!fl)return;var p=Math.max(0,Math.min(1,isNaN(sw.progress)?0:sw.progress));fl.style.width=(p*100)+'%';}sw.on('progress',pg);sw.on('slideChange',pg);pg();return sw;}function go(){if(typeof Swiper==='undefined')return;var aE=document.getElementById('accomSlider');var aN=document.getElementById('accomSliderNav');iS(aE,aN,{spv:'auto',sb:16,bps:{480:{spaceBetween:16},768:{spaceBetween:18},992:{spaceBetween:20},1400:{spaceBetween:22}}});var lE=document.getElementById('livingSlider');var lN=document.getElementById('livingSliderNav');iS(lE,lN,{spv:'auto',sb:16,speed:800,bps:{480:{spaceBetween:16},768:{spaceBetween:18},992:{spaceBetween:20},1400:{spaceBetween:22}}});}if(typeof Swiper!=='undefined'){go();return;}document.addEventListener('swiperReady',go);var r=0;var t=setInterval(function(){if(typeof Swiper!=='undefined'){clearInterval(t);go();}else if(++r>=30)clearInterval(t);},150);})();

/* ============================================================
   7. costspricebar1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c863827b3a80f534275777%2Fcostspricebar1-1.0.0.js
   ============================================================ */
(function(){if(window.__costsPriceBarDone)return;window.__costsPriceBarDone=true;var table=document.querySelector('.price-table');if(!table)return;var animated=false;function animate(){if(animated)return;animated=true;var rows=table.querySelectorAll('.price-row[data-w]');rows.forEach(function(row,i){var bar=row.querySelector('.price-bar');if(!bar)return;var w=parseFloat(row.dataset.w)||0.08;if(bar.getAnimations)bar.getAnimations().forEach(function(a){a.cancel();});bar.animate([{transform:'scaleX(0)'},{transform:'scaleX('+w+')'}],{delay:i*90,duration:900,easing:'cubic-bezier(0.16,1,0.3,1)',fill:'forwards'});});}if('IntersectionObserver' in window){var io=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){animate();io.disconnect();}});},{threshold:0.2});io.observe(table);}else{animate();}})();

/* ============================================================
   8. costsbudget1 v1.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69c8639cd33d6ecd09644e7f%2Fcostsbudget1-1.0.0.js
   ============================================================ */
(function(){if(window.__costsBudgetScrollDone)return;window.__costsBudgetScrollDone=true;var wrap=document.querySelector('.budget-wrap');if(!wrap)return;var outer=wrap.closest('.budget-scroll-outer');var isDragging=false;var startX=0;var scrollLeft=0;function updateFade(){if(!outer)return;var hasOverflow=wrap.scrollWidth>wrap.clientWidth+4;outer.classList.toggle('has-overflow',hasOverflow);if(hasOverflow){var atEnd=wrap.scrollLeft+wrap.clientWidth>=wrap.scrollWidth-4;outer.classList.toggle('is-scrolled-end',atEnd);}}wrap.classList.add('is-scrollable');wrap.addEventListener('mousedown',function(e){isDragging=true;wrap.classList.add('is-dragging');startX=e.pageX-wrap.offsetLeft;scrollLeft=wrap.scrollLeft;e.preventDefault();});document.addEventListener('mousemove',function(e){if(!isDragging)return;var x=e.pageX-wrap.offsetLeft;wrap.scrollLeft=scrollLeft-(x-startX);});document.addEventListener('mouseup',function(){if(!isDragging)return;isDragging=false;wrap.classList.remove('is-dragging');});wrap.addEventListener('touchstart',function(e){startX=e.touches[0].pageX-wrap.offsetLeft;scrollLeft=wrap.scrollLeft;},{passive:true});wrap.addEventListener('touchmove',function(e){var x=e.touches[0].pageX-wrap.offsetLeft;wrap.scrollLeft=scrollLeft-(x-startX);},{passive:true});wrap.addEventListener('scroll',updateFade);window.addEventListener('resize',updateFade);updateFade();})();

/* ============================================================
   9. celtochov1 v2.0.0
   Original CDN: https://cdn.prod.website-files.com/667453c576e8d35c454cc9ae%2F689e5ba67671442434f3ca35%2F69ea49589152839d8d25a714%2Fceltochov1-2.0.0.js
   ============================================================ */
(function(){if(window.__celToh)return;window.__celToh=true;function init(){var ls=document.querySelectorAll('.stoc_link');if(!ls.length){setTimeout(init,200);return}ls.forEach(function(l){var d=l.querySelector('.stoc_dot');if(!d)return;l.addEventListener('mouseenter',function(){if(!l.classList.contains('is-active'))d.classList.add('is-hover')});l.addEventListener('mouseleave',function(){d.classList.remove('is-hover')})})}if(document.readyState!=='loading')init();else document.addEventListener('DOMContentLoaded',init)})();
