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
 *   - native undo works.
 * tests/browser/test_rich_field.py is the matrix. If it cannot pass, WO-22 stops here.
 *
 * A translation carries exactly two kinds of markup (measured on all 11,214 texts):
 * Weglot's link markers <a wg-N="">...</a>, and one raw <br>. They are rendered as tokens
 * the reviewer cannot edit or delete; everything else is plain text. The field is built
 * with DOM calls only, never by assigning markup (the desk's rule: site copy is data).
 * A token's label is real text inside it (the pair's number, or the raw marker under
 * "Show HTML"); the text is never read back -- a token serialises as its data-raw.
 */
(function () {
  'use strict';

  const TOKEN = /(<a wg-[0-9]+="">|<\/a>|<br>)/;
  const TOKEN_ALL = /<a wg-[0-9]+="">|<\/a>|<br>/g;
  const IS_TOKEN = /^(?:<a wg-[0-9]+="">|<\/a>|<br>)$/;
  const MARK = { open: '‹', close: '›', break: '↵' };   // ‹ › ↵

  function label(tok, showHtml) {
    const side = tok.getAttribute('data-side');
    tok.textContent = showHtml ? tok.getAttribute('data-raw')
      : side === 'break' ? MARK.break : MARK[side] + tok.getAttribute('data-link');
  }

  function tokenEl(raw, link) {
    const s = document.createElement('span');
    s.className = 'rf-token';
    s.contentEditable = 'false';
    s.setAttribute('data-raw', raw);
    if (raw === '<br>') s.setAttribute('data-side', 'break');
    else {
      s.setAttribute('data-side', raw === '</a>' ? 'close' : 'open');
      s.setAttribute('data-link', link);
    }
    label(s, false);
    return s;
  }

  // Text -> field. Each closing marker takes the number of the link it closes, so a pair of
  // chips shows one number.
  function render(el, text) {
    el.textContent = '';
    const open = [];
    String(text).split(TOKEN).forEach(function (part) {
      if (!part) return;
      if (!IS_TOKEN.test(part)) { el.appendChild(document.createTextNode(part)); return; }
      const m = part.match(/wg-([0-9]+)/);
      if (m) { open.push(m[1]); el.appendChild(tokenEl(part, m[1])); }
      else el.appendChild(tokenEl(part, part === '</a>' ? (open.pop() || '') : ''));
    });
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
          else if (c.tagName !== 'BR') walk(c);
        }
      }
    })(el);
    flush();
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
    const original = String(opts.text || '');
    el.classList.add('rf-field');
    el.contentEditable = 'true';
    el.setAttribute('dir', 'auto');       // the text's own direction, as the desk's cells
    el.setAttribute('spellcheck', 'false');
    render(el, original);
    let composing = false;

    el.addEventListener('compositionstart', function () { composing = true; });
    el.addEventListener('compositionend', function () { composing = false; });

    el.addEventListener('keydown', function (ev) {
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
        render(el, original);
        if (opts.onCancel) opts.onCancel();
      }
    });

    el.addEventListener('beforeinput', function (ev) {
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
    // through the browser's own editing command, so Undo takes it back out.
    el.addEventListener('paste', function (ev) {
      ev.preventDefault();
      let text = (ev.clipboardData && ev.clipboardData.getData('text/plain')) || '';
      text = text.replace(TOKEN_ALL, '').replace(/[\r\n\t]+/g, ' ');
      if (text) document.execCommand('insertText', false, text);
    });
    el.addEventListener('drop', function (ev) { ev.preventDefault(); });

    return {
      value: function () { return serialize(el); },
      changed: function () { return serialize(el) !== original; },
      // "Show HTML": each chip shows its marker exactly as Weglot stores it.
      showHtml: function (on) {
        el.classList.toggle('rf-show-html', !!on);
        el.querySelectorAll('.rf-token').forEach(function (tok) { label(tok, !!on); });
      }
    };
  }

  window.RichField = { render: render, serialize: serialize, attach: attach };
})();
