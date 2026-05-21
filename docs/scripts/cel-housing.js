/*!
 * cel-housing.js — CEL Accommodations CMS template (video-tour player)
 *
 * Source-of-truth: tools/cel-page-scripts/src/cel-housing.js (cagdasunal/webflow monorepo)
 * Mirrored to:     docs/scripts/cel-housing.{js,min.js} (cagdasunal/CEL repo)
 * Public URL:      https://cel.englishcollege.com/scripts/cel-housing.min.js
 *
 * Loaded via Webflow Page Settings (Accommodations Template) -> Custom Code -> Footer:
 *   <script src="https://cel.englishcollege.com/scripts/cel-housing.min.js" defer></script>
 *
 * Behavior bundled (1 IIFE, guarded __celHousingVideo):
 *   1. celHousingVideo v1.0.0 — click-to-load Vimeo facade for .video_player.
 *      Same UX as the vancouver player, but the per-item Vimeo ID comes from
 *      the CMS-bound #vimeo-id element (Accommodations `vimeo-id` PlainText
 *      field) instead of a data-vimeo-id attribute. A data-vimeo-id attribute
 *      on .video_player is still honored as a fallback, for parity with the
 *      other CEL video pages.
 *
 * Why a facade: the Vimeo iframe is injected only on the first click, so the
 * heavy player + autoplay never load until the visitor opts in (LCP/INP win,
 * same pattern as cel-vancouver.js).
 *
 * No-video items: 8 of 22 accommodations have no Vimeo ID, so #vimeo-id renders
 * empty. The script then no-ops (no handler, no iframe). Hide the whole
 * .video_player for those items via Webflow CMS conditional visibility.
 *
 * v1.0.0 (2026-05-21) — Initial bundle.
 */

(function () {
  if (window.__celHousingVideo) return;
  window.__celHousingVideo = true;

  // The `vimeo-id` CMS field normally renders as a bare numeric ID, but tolerate
  // surrounding whitespace and an editor pasting a full Vimeo URL.
  function extractVimeoId(raw) {
    if (!raw) return '';
    raw = String(raw).trim();
    if (/^\d+$/.test(raw)) return raw;
    const url = raw.match(/vimeo\.com\/(?:video\/)?(\d+)/i);
    if (url) return url[1];
    const digits = raw.match(/\d{6,}/);
    return digits ? digits[0] : '';
  }

  function resolveVimeoId(player) {
    const node = document.getElementById('vimeo-id');
    const fromNode = node ? extractVimeoId(node.textContent) : '';
    if (fromNode) return fromNode;
    return extractVimeoId(player.getAttribute('data-vimeo-id'));
  }

  function initPlayer(player) {
    if (player.__celHousingInit) return;

    // Resolve at load time and close over it — #vimeo-id may live inside the
    // thumbnail that we remove on click.
    const id = resolveVimeoId(player);
    if (!id) return; // no video tour for this accommodation — leave the DOM untouched

    const btn = player.querySelector('.video_play-btn');
    const thumb = player.querySelector('.video_thumbnail');
    if (!btn && !thumb) return;

    player.__celHousingInit = true;

    function loadVideo(e) {
      if (e && e.preventDefault) e.preventDefault();
      if (player.classList.contains('is-playing')) return;
      player.classList.add('is-playing');

      // Anchor the absolutely-positioned iframe to the player box.
      if (window.getComputedStyle(player).position === 'static') {
        player.style.position = 'relative';
      }

      const iframe = document.createElement('iframe');
      iframe.className = 'video_embed';
      iframe.src = 'https://player.vimeo.com/video/' + id +
        '?autoplay=1&color=FAF3E8&title=0&byline=0&portrait=0';
      iframe.setAttribute('frameborder', '0');
      iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
      iframe.setAttribute('allowfullscreen', '');
      iframe.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;border:0;';
      iframe.title = player.getAttribute('data-video-title') ||
        'CEL Accommodation — Video Tour';

      if (thumb) thumb.remove();
      if (btn) btn.remove();
      player.appendChild(iframe);
    }

    if (btn) btn.addEventListener('click', loadVideo);
    if (thumb) thumb.addEventListener('click', loadVideo);
  }

  const players = document.querySelectorAll('.video_player');
  for (let i = 0; i < players.length; i++) initPlayer(players[i]);
})();
