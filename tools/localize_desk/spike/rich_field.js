/*
 * The always-open translation field -- a SPIKE for monorepo runbook WO-22 (guard G13).
 *
 * WO-22 replaces the desk's edit box with Weglot's kind of field: always open, the link
 * markers shown as chips. Before anything is built on it, this proves -- in a real browser,
 * against the whole corpus -- that such a field can hold a translation without changing it:
 *   - no-break spaces (U+00A0) survive, and typing never adds one;
 *   - Japanese / Korean IME: no key acts while a composition is open (R28);
 *   - Arabic, right to left, with chips;
 *   - paste arrives as plain text, and can never forge a marker;
 *   - every text round-trips its <a wg-N=""> markers byte for byte (R29);
 *   - native undo works;
 *   - no edit, by any path, changes the markers: an edit over a selection that takes one
 *     does nothing (typing, paste), an IME composition cannot take one, and anything else
 *     that would is rolled back (#5 review, 2026-09-28).
 * tests/browser/test_rich_field.py is the matrix. If it cannot pass, WO-22 stops here.
 *
 * A translation carries exactly two kinds of markup (measured on all 11,214 texts):
 * Weglot's link markers <a wg-N="">...</a>, and one raw <br>. They are rendered as tokens
 * the reviewer cannot edit or delete; everything else is plain text. The field is built
 * with DOM calls only, never by assigning markup (the desk's rule: site copy is data).
 * A token's label is real text inside it (a bare ‹ or ›, or the raw marker under
 * "Show HTML"); the text is never read back -- a token serialises as its data-raw.
 *
 * CEL-096: no number is drawn in the text (only the hover and the note under it name "Link N"). A reviewer
 * reads a link as a link:
 *   - in a column nobody types in, read() wraps the words between a pair in one dotted-underlined
 *     span (the hover names it, "Link 1");
 *   - in the field being edited, a pair is two compact chips (‹ and ›) that light up together on
 *     hover, a chip with no partner is drawn broken, and linkProblem() says what a text lacks.
 * The markers themselves, the data and what is saved are exactly what they were.
 */
(function () {
  'use strict';

  const TOKEN = /(<a wg-[0-9]+="">|<\/a>|<br>)/;
  const TOKEN_ALL = /<a wg-[0-9]+="">|<\/a>|<br>/g;
  const IS_TOKEN = /^(?:<a wg-[0-9]+="">|<\/a>|<br>)$/;
  const MARK = { open: '‹', close: '›', break: '↵' };   // ‹ › ↵
  const ATTACHED = new WeakMap();                          // field -> detach()

  function label(tok, showHtml) {
    const side = tok.getAttribute('data-side');
    tok.textContent = showHtml ? tok.getAttribute('data-raw') : MARK[side];
  }

  // The words a caller gives for a chip's hover and accessible name: tip(side, n) with side 'open' or 'close'.
  function tipOf(opts, side, link) {
    return opts && typeof opts.tip === 'function' ? String(opts.tip(side, link) || '') : '';
  }

  function tokenEl(raw, link, opts) {
    const s = document.createElement('span');
    s.className = 'rf-token';
    s.contentEditable = 'false';
    // A dir attribute takes the chip out of the field's dir=auto: under "Show HTML" its
    // raw marker's Latin letters flipped an Arabic field that starts with a link to LTR.
    s.setAttribute('dir', 'ltr');
    s.setAttribute('data-raw', raw);
    if (raw === '<br>') s.setAttribute('data-side', 'break');
    else {
      s.setAttribute('data-side', raw === '</a>' ? 'close' : 'open');
      s.setAttribute('data-link', link);
      const tip = tipOf(opts, raw === '</a>' ? 'close' : 'open', link);
      if (tip) {
        s.setAttribute('data-tip', tip);
        s.setAttribute('role', 'img');
        s.setAttribute('aria-label', tip);
      }
    }
    label(s, false);
    return s;
  }

  // Text -> field. Each closing marker takes the number of the link it closes and the same
  // data-pair as its opening chip (so the two light up together); a chip whose partner is
  // missing is marked data-broken.
  function render(el, text, opts) {
    el.textContent = '';
    const open = [];
    let seq = 0;
    String(text).split(TOKEN).forEach(function (part) {
      if (!part) return;
      if (!IS_TOKEN.test(part)) { el.appendChild(document.createTextNode(part)); return; }
      const m = part.match(/wg-([0-9]+)/);
      if (m) {
        const tok = tokenEl(part, m[1], opts);
        tok.setAttribute('data-pair', String(++seq));
        tok.setAttribute('data-broken', '1');                 // until a closing marker takes it
        open.push({ link: m[1], tok: tok });
        el.appendChild(tok);
      } else if (part === '</a>') {
        const mate = open.pop();
        const tok = tokenEl(part, mate ? mate.link : '', opts);
        if (mate) {
          tok.setAttribute('data-pair', mate.tok.getAttribute('data-pair'));
          mate.tok.removeAttribute('data-broken');
        } else {
          tok.setAttribute('data-pair', String(++seq));
          tok.setAttribute('data-broken', '1');
        }
        el.appendChild(tok);
      } else {
        el.appendChild(tokenEl(part, '', opts));
      }
    });
  }

  // Text -> a column nobody types in: the words between a pair sit in one span with a dotted underline and
  // the link's hover; no marker and no number is drawn. A break stays its chip. A pair left open runs to
  // the end of the text, and a closing marker with nothing open draws nothing.
  function read(el, text, opts) {
    el.textContent = '';
    const stack = [el];
    String(text).split(TOKEN).forEach(function (part) {
      if (!part) return;
      const here = stack[stack.length - 1];
      if (!IS_TOKEN.test(part)) { here.appendChild(document.createTextNode(part)); return; }
      const m = part.match(/wg-([0-9]+)/);
      if (m) {
        const a = document.createElement('span');
        a.className = 'rf-link';
        a.setAttribute('data-link', m[1]);
        const tip = tipOf(opts, 'open', m[1]);
        if (tip) a.setAttribute('data-tip', tip);
        a.setAttribute('data-open', '1');                     // until its closing marker comes
        here.appendChild(a);
        stack.push(a);
      } else if (part === '</a>') {
        if (stack.length > 1) stack.pop().removeAttribute('data-open');
        else {                                                  // nothing open: kept, drawn as nothing
          const z = document.createElement('span');
          z.setAttribute('data-raw', part);
          here.appendChild(z);
        }
      } else {
        here.appendChild(tokenEl(part, '', opts));
      }
    });
  }

  // What a translation lacks of the English's links, in the engine's own order of checks (gates.py g3_placeholders):
  // null when it has them all, else {kind, n}: 'missing' (a link the English has), 'extra' (a link it does not),
  // 'order' (the links are in another order, which would point a label at the wrong page), or 'broken' (a link with no
  // start or no end). An empty translation has nothing to compare.
  function linkProblem(source, text) {
    if (!String(text || '').trim()) return null;
    function stream(t) {
      const out = [];
      const re = /<a wg-([0-9]+)="">|<\/a>/g;
      let m;
      while ((m = re.exec(String(t || '')))) out.push(m[1] ? { open: true, n: m[1] } : { open: false });
      return out;
    }
    const a = stream(source), b = stream(text);
    const ia = a.filter(function (x) { return x.open; }).map(function (x) { return x.n; });
    const ib = b.filter(function (x) { return x.open; }).map(function (x) { return x.n; });
    const sa = new Set(ia), sb = new Set(ib);
    for (const n of sa) if (!sb.has(n)) return { kind: 'missing', n: n };
    for (const n of sb) if (!sa.has(n)) return { kind: 'extra', n: n };
    const fa = Array.from(sa), fb = Array.from(sb);
    if (fa.join() !== fb.join()) return { kind: 'order', n: '' };
    const same = ia.length === ib.length && ia.slice().sort().join() === ib.slice().sort().join();
    if (same && ia.join() !== ib.join()) return { kind: 'order', n: '' };
    const stack = [];
    for (const x of b) {
      if (x.open) stack.push(x.n);
      else if (!stack.pop()) return { kind: 'broken', n: '' };
    }
    if (stack.length) return { kind: 'broken', n: stack[stack.length - 1] };
    return null;
  }

  // Field -> text. Adjacent text is joined before anything is stripped, so a marker typed
  // across two text nodes is caught too. Markers come ONLY from tokens: typed or pasted
  // marker syntax is removed, or the reviewer could forge a link Weglot would then import.
  // Elements the browser adds while editing (a formatting span, a placeholder <br>) give
  // up their text and nothing else.
  function serialize(el) {
    let out = '', text = '';
    function flush() { out += text.replace(TOKEN_ALL, ''); text = ''; }
    (function walk(node) {
      for (let c = node.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) text += c.nodeValue;
        else if (c.nodeType === 1) {
          if (c.hasAttribute('data-raw')) { flush(); out += c.getAttribute('data-raw'); }
          else if (c.classList.contains('rf-link')) {          // read(): the span stands for its two markers
            flush(); out += '<a wg-' + c.getAttribute('data-link') + '="">';
            walk(c);
            flush(); if (!c.hasAttribute('data-open')) out += '</a>';
          }
          else if (c.tagName !== 'BR') walk(c);
        }
      }
    })(el);
    flush();
    return out;
  }

  // The markers in document order: the one thing no edit may change.
  function markers(el) {
    return Array.prototype.map.call(el.querySelectorAll('.rf-token'),
      function (t) { return t.getAttribute('data-raw'); }).join('\u0000');
  }

  function caretAtEnd(el) {
    const r = document.createRange();
    r.selectNodeContents(el);
    r.collapse(false);
    const s = window.getSelection();
    s.removeAllRanges();
    s.addRange(r);
  }

  // The selection's ranges inside the field.
  function selectionIn(el) {
    const s = window.getSelection(), out = [];
    for (let i = 0; s && i < s.rangeCount; i++) {
      const r = s.getRangeAt(i);
      if (el.contains(r.commonAncestorContainer)) out.push(r);
    }
    return out;
  }

  function touchesToken(el, ranges) {
    const tokens = el.querySelectorAll('.rf-token');
    for (const sr of ranges) {
      const r = document.createRange();
      r.setStart(sr.startContainer, sr.startOffset);
      r.setEnd(sr.endContainer, sr.endOffset);
      for (const tok of tokens) if (r.intersectsNode(tok)) return true;
    }
    return false;
  }

  function attach(el, opts) {
    opts = opts || {};
    // Attached again (a re-render into the same element): the old listeners go first, or
    // every paste would land twice.
    if (ATTACHED.has(el)) ATTACHED.get(el)();
    const original = String(opts.text || '');
    el.classList.add('rf-field');
    el.contentEditable = 'true';
    el.setAttribute('dir', 'auto');       // the text's own direction, as the desk's cells
    el.setAttribute('spellcheck', 'false');
    render(el, original, opts);
    const expected = markers(el);
    let composing = false;
    let lastGood = original;
    const on = [];
    function listen(type, fn) { el.addEventListener(type, fn); on.push([type, fn]); }

    // The backstop, after every edit: markers that changed by ANY path (a future browser, an
    // editing command, an undo that replays a refused edit) put the field back to its last
    // good text. The guards below keep this from ever being the reviewer's experience.
    function settle() {
      if (markers(el) !== expected) {
        render(el, lastGood, opts);
        caretAtEnd(el);
      } else {
        lastGood = serialize(el);
      }
    }

    // A composition cannot be cancelled, and the first thing it does is replace the
    // selection. When that selection takes a marker, it collapses to its end first: the
    // composed text goes in, nothing selected goes out.
    listen('compositionstart', function () {
      composing = true;
      const ranges = selectionIn(el);
      if (touchesToken(el, ranges)) window.getSelection().collapseToEnd();
    });
    listen('compositionend', function () { composing = false; settle(); });
    listen('input', function (ev) { if (!composing && !ev.isComposing) settle(); });

    listen('keydown', function (ev) {
      // Mid-composition every key belongs to the IME: Enter picks a candidate, it does not
      // commit the row (R28). keyCode 229 is how Chrome marks such a key.
      if (composing || ev.isComposing || ev.keyCode === 229) return;
      if (ev.key === 'Enter') {
        ev.preventDefault();               // one paragraph: no text in the corpus breaks a line
        if ((ev.metaKey || ev.ctrlKey) && opts.onCommit) opts.onCommit(serialize(el));
        return;
      }
      if (ev.key === 'Escape') {
        ev.preventDefault();
        render(el, original, opts);
        lastGood = original;
        if (opts.onCancel) opts.onCancel();
      }
    });

    listen('beforeinput', function (ev) {
      const t = ev.inputType || '';
      if (t === 'historyUndo' || t === 'historyRedo') return;
      // Structure is not the reviewer's to change: no new paragraphs, no bold, no dropped
      // markup -- and no edit that would take a marker with it.
      if (t === 'insertParagraph' || t === 'insertLineBreak' || t.indexOf('format') === 0 ||
          t === 'insertFromDrop' || t === 'deleteByDrag') { ev.preventDefault(); return; }
      const ranges = ev.getTargetRanges ? ev.getTargetRanges() : [];
      if (touchesToken(el, ranges)) ev.preventDefault();
    });

    // Paste arrives as plain text on one line, with any marker syntax taken out. It goes in
    // through the browser's own editing command, so Undo takes it back out -- and that
    // command fires no beforeinput, so the marker guard is applied here: a paste over a
    // selection that takes a marker does nothing, as typing over it does (#5 review E-1).
    // A clipboard with only HTML gives its text, read in an inert document (nothing in it
    // runs or loads).
    listen('paste', function (ev) {
      ev.preventDefault();
      if (touchesToken(el, selectionIn(el))) return;
      const cd = ev.clipboardData;
      let text = (cd && cd.getData('text/plain')) || '';
      if (!text && cd && cd.getData('text/html')) {
        text = new DOMParser().parseFromString(cd.getData('text/html'), 'text/html').body.textContent || '';
      }
      text = text.replace(TOKEN_ALL, '').replace(/[\r\n\t]+/g, ' ');
      if (text) document.execCommand('insertText', false, text);
    });
    listen('drop', function (ev) { ev.preventDefault(); });

    // The two chips of one pair light up together while the pointer is on either.
    function lit(ev, on) {
      const tok = ev.target && ev.target.closest ? ev.target.closest('.rf-token[data-pair]') : null;
      if (!tok || !el.contains(tok)) return;
      el.querySelectorAll('.rf-token[data-pair="' + tok.getAttribute('data-pair') + '"]').forEach(function (t) {
        t.classList.toggle('rf-lit', on);
      });
    }
    listen('mouseover', function (ev) { lit(ev, true); });
    listen('mouseout', function (ev) { lit(ev, false); });

    function detach() {
      on.forEach(function (h) { el.removeEventListener(h[0], h[1]); });
      ATTACHED.delete(el);
    }
    ATTACHED.set(el, detach);

    return {
      detach: detach,
      value: function () { return serialize(el); },
      changed: function () { return serialize(el) !== original; },
      // "Show HTML": each chip shows its marker exactly as Weglot stores it.
      showHtml: function (on) {
        el.classList.toggle('rf-show-html', !!on);
        el.querySelectorAll('.rf-token').forEach(function (tok) { label(tok, !!on); });
      }
    };
  }

  window.RichField = { render: render, read: read, serialize: serialize, attach: attach, linkProblem: linkProblem };
})();
