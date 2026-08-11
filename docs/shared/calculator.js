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
  try { reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}

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
    if (!isFinite(to) || reduce) { setText(el, text); return; }
    var from = (el.__calcV == null) ? to : el.__calcV;
    el.__calcV = to;
    el.__calcTarget = text;
    if (from === to) { setText(el, text); return; }
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
      if (p < 1) { el.__calcRaf = requestAnimationFrame(step); return; }
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
    var root = typeof config.root === 'string'
      ? (document.getElementById(config.root) || document.querySelector(config.root))
      : config.root;
    if (!root) return null;
    if (root.__celCalc) return root.__celCalc;   /* one instance per root */

    var self = this;
    var state = {};
    for (var k in (config.state || {})) if (config.state.hasOwnProperty(k)) state[k] = config.state[k];

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

    var helpers = { money: money, number: number, bracket: bracket, plural: plural, state: state };

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
      var res = config.compute ? (config.compute(state, helpers) || {}) : {};
      var out = res.out || {}, rowState = res.rows || {},
          flagState = res.flags || {}, chipState = res.chips || {}, fill = res.fill || {};

      Array.prototype.forEach.call(outs, function (el) {
        var name = el.getAttribute('data-calc-out');
        if (!(name in out)) return;
        if (el.hasAttribute('data-calc-tween')) tween(el, out[name]);
        else setText(el, out[name]);
      });

      Array.prototype.forEach.call(imgs, function (el) {
        var name = el.getAttribute('data-calc-img');
        if (!(name in out)) return;
        var url = out[name];
        if (!url) { el.hidden = true; return; }
        el.hidden = false;
        if (el.getAttribute('src') !== url) {
          el.setAttribute('src', url);
          if (out[name + '2x']) el.setAttribute('srcset', out[name + '2x'] + ' 2x');
        }
      });

      Array.prototype.forEach.call(rows, function (el) {
        var on = !!rowState[el.getAttribute('data-calc-row')];
        var off = el.getAttribute('data-calc-off');
        if (off) el.classList.toggle(off, !on);
        else el.hidden = !on;
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
          void el.offsetWidth;                 /* restart the keyframe */
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
          var min = parseFloat(r.min || 0), max = parseFloat(r.max || 100);
          frac = max === min ? 0 : (parseFloat(r.value) - min) / (max - min);
        }
        var target = r.getAttribute('data-calc-fill');
        target = target ? (root.querySelector(target) || r.parentNode) : r.parentNode;
        var pct = (frac * 100).toFixed(2) + '%';
        target.style.setProperty('--calc-fill', pct);
        target.style.setProperty('--calc-frac', frac.toFixed(4));
        r.style.setProperty('--calc-fill', pct);      /* the track may be the input itself */
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
      if (open) document.addEventListener('click', onOutside, true);
      else document.removeEventListener('click', onOutside, true);
    }

    function closeMenus() {
      Array.prototype.forEach.call(menus, function (m) {
        setMenu(m.getAttribute('data-calc-menu'), false);
      });
    }

    function onOutside(ev) {
      var inside = false;
      Array.prototype.forEach.call(menus, function (m) { if (m.contains(ev.target)) inside = true; });
      Array.prototype.forEach.call(menuToggles, function (t) { if (t.contains(ev.target)) inside = true; });
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
      var sk = pair[0], sv = coerce(pair.slice(1).join(':'));
      state[sk] = sv;
      syncRadios(sk, sv);
      Array.prototype.forEach.call(ranges, function (r) {
        if (r.getAttribute('data-calc-range') === sk) r.value = sv;
      });
      render();
    });

    /* arrow keys walk a radio group, the way a native one does; Escape closes a panel */
    root.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { closeMenus(); return; }
      if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft' &&
          ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
      var btn = document.activeElement;
      if (!btn || !btn.hasAttribute || !btn.hasAttribute('data-calc-radio')) return;
      var key = btn.getAttribute('data-calc-radio');
      var group = root.querySelectorAll('[data-calc-radio="' + key + '"]');
      var i = Array.prototype.indexOf.call(group, btn);
      var next = (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') ? i + 1 : i - 1;
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

  var queued = (window.CELCalculator && window.CELCalculator.__queue) || [];

  window.CELCalculator = {
    __engine: true,
    /** Mount a calculator. Returns the instance, or null if the root is absent
     *  (a config may safely ship on a page that does not carry the tool). */
    mount: function (config) { return new Calculator(config) || null; },
    /** Same helpers compute() receives, for a config that needs them outside. */
    helpers: { money: money, number: number, bracket: bracket, plural: plural },
    reducedMotion: reduce
  };

  for (var i = 0; i < queued.length; i++) window.CELCalculator.mount(queued[i]);
})();
