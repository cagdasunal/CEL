/*
 * The rules page of the localization desk: /admin/localization/rules/ (CEL-080, read-only version 1).
 * The client picks a language and reads the translation rules the engine gives Gemini for it: the shared
 * rules, that language's own rules and its glossary (Worker scopes `global`, `<lang>`, `glossary:<lang>`,
 * read with desk-rules-read). Nothing on this page edits, saves or publishes, and the page-level briefs
 * (`brief:<page>:<lang>`) are not shown. Editing comes back in a later version.
 *
 * generate_rules_page.py inlines rules_md.js, then this file. It reads the globals the page defines first:
 * COPY with t() (every word comes from COPY.md) and callProxy() (the Worker door). DOM is built with
 * createElement / textContent only.
 */
(function () {
  'use strict';

  const cfgNode = document.getElementById('rules-config');
  if (!cfgNode || !window.RulesMd || typeof callProxy !== 'function') return;
  const CFG = JSON.parse(cfgNode.textContent);
  const M = window.RulesMd;
  const LOCALES = CFG.locales;            // [{code, name, flag}]
  const TIMING = Object.assign({ timeout: 20000 }, window.RULES_TIMING || {});

  const root = document.getElementById('rules-app');
  if (!root) return;
  const $ = function (s, r) { return (r || document).querySelector(s); };
  const panel = $('#rulesPanel');
  const tabs = Array.prototype.slice.call(root.querySelectorAll('.r-tab'));

  function h(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ── state ────────────────────────────────────────────────────────────────────────
  const known = function (code) { return LOCALES.some(function (l) { return l.code === code; }); };
  const wanted = new URLSearchParams(location.search).get('lang');
  const S = {
    lang: known(wanted) ? wanted : (known('de') ? 'de' : LOCALES[0].code),
    scopes: {},       // scope -> {state: 'loading' | 'ok' | 'error', body, key}
  };
  const langName = function (code) {
    const l = LOCALES.find(function (x) { return x.code === code; });
    return l ? l.name : code;
  };
  const scopesFor = function (lang) { return ['global', lang, 'glossary:' + lang]; };
  const sc = function (scope) {
    if (!S.scopes[scope]) S.scopes[scope] = { state: 'loading', body: null, key: null };
    return S.scopes[scope];
  };

  // ── the Worker (reads only) ──────────────────────────────────────────────────────
  function call(payload) {
    return callProxy(payload, TIMING.timeout).catch(function () { return null; });
  }
  // Why a read failed, as a COPY.md key.
  function failureKey(r) {
    if (!r) return navigator.onLine === false ? 'rules.error.offline' : 'rules.error.read';
    if (r.status === 401) return 'rules.error.signed_out';
    if (r.status === 429) return 'rules.error.cap';
    return 'rules.error.read';
  }
  function readScope(scope) {
    const s = sc(scope);
    if (s.state === 'ok') return Promise.resolve();
    s.state = 'loading';
    return call({ action: 'desk-rules-read', scope: scope }).then(function (r) {
      if (!r || !r.ok || !r.body) { s.state = 'error'; s.key = failureKey(r); return; }
      s.state = 'ok';
      s.key = null;
      s.body = r.body.body == null ? '' : String(r.body.body);
    });
  }
  function load() {
    const lang = S.lang;
    const scopes = scopesFor(lang);
    scopes.forEach(function (x) { if (sc(x).state !== 'ok') sc(x).state = 'loading'; });
    root.dataset.state = 'loading';
    render();
    return Promise.all(scopes.map(readScope)).then(function () {
      if (lang !== S.lang) return;                 // the reader moved on to another language meanwhile
      root.dataset.state = scopes.every(function (x) { return sc(x).state === 'ok'; }) ? 'ready' : 'error';
      render();
    });
  }

  // ── reading a body ───────────────────────────────────────────────────────────────
  // **bold**, *italic* and `code`; a Markdown escape (\* \| \_) is the character itself.
  function inline(node, raw0) {
    const raw = String(raw0).replace(/\\([*|_`])/g, function (_m, c) { return { '*': '\u0001', '|': '|', '_': '_', '`': '\u0002' }[c]; });
    const lit = function (s) { return document.createTextNode(s.replace(/\u0001/g, '*').replace(/\u0002/g, '`')); };
    // bold may hold italics (**bold *ital* bold**): the bold run ends at the first `**`
    const re = /(\*\*(?:[^*]|\*(?!\*))+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;
    let last = 0, m;
    while ((m = re.exec(raw))) {
      if (m.index > last) node.appendChild(lit(raw.slice(last, m.index)));
      const s = m[0];
      const wrapIn = s[0] === '`' ? h('code') : s[1] === '*' ? h('strong') : h('em');
      if (s[1] === '*') inline(wrapIn, s.slice(2, -2));
      else wrapIn.appendChild(lit(s.slice(1, -1)));
      node.appendChild(wrapIn);
      last = m.index + s.length;
    }
    if (last < raw.length) node.appendChild(lit(raw.slice(last)));
  }
  function textNode(tag, cls, raw) {
    const n = h(tag, cls);
    inline(n, raw);
    return n;
  }
  function tableOf(rows, header) {
    const table = h('table', 'r-table');
    rows.forEach(function (cells, i) {
      const tr = h('tr');
      cells.forEach(function (c) { tr.appendChild(textNode(header && i === 0 ? 'th' : 'td', null, c)); });
      table.appendChild(tr);
    });
    return table;
  }
  // The blocks of a rules body, in order: headings, lists, paragraphs, quotes, tables.
  function renderBlocks(blocks, into) {
    let list = null, rows = null, header = false;
    const flushTable = function () {
      if (rows) into.appendChild(tableOf(rows, header));
      rows = null; header = false;
    };
    blocks.forEach(function (b, i) {
      if (b.kind !== 'item') list = null;
      if (b.kind !== 'row' && b.kind !== 'sep') flushTable();
      if (b.kind === 'blank') return;
      if (b.kind === 'sep') { header = rows != null && rows.length === 1; return; }
      if (b.kind === 'row') { if (!rows) rows = []; rows.push(b.cells); return; }
      if (b.kind === 'hr') { into.appendChild(h('hr', 'r-hr')); return; }
      if (b.kind === 'head') { into.appendChild(textNode('h' + Math.min(6, Math.max(3, b.level + 1)), 'r-h', b.text)); return; }
      if (b.kind === 'item') {
        if (!list) { list = h('ul', 'r-items'); into.appendChild(list); }
        list.appendChild(textNode('li', 'r-item', b.text));
        return;
      }
      if (b.kind === 'quote') { into.appendChild(textNode('blockquote', 'r-quote', b.text)); return; }
      into.appendChild(textNode('p', 'r-p', b.text));
    });
    flushTable();
  }
  // ja / ko / ar: the seed holds one quoted "no rules" line (rules_store.split); that is no rules yet.
  function isSeedNone(body) {
    const b = String(body || '').trim();
    return b === '' || (/^>/.test(b) && b.split('\n').length === 1);
  }

  // ── the sections ─────────────────────────────────────────────────────────────────
  function skeleton() {
    const sk = h('div', 'r-skel');
    sk.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 4; i++) sk.appendChild(h('div', 'r-skel-line'));
    return sk;
  }
  // A scope that could not be read says why, with Try again.
  function notice(scope) {
    const s = sc(scope);
    const box = h('div', 'r-notice');
    box.setAttribute('role', 'alert');
    box.appendChild(h('p', null, t(s.key || 'rules.error.read')));
    const b = h('button', 'desk-btn', t('rules.retry'));
    b.type = 'button';
    b.addEventListener('click', function () { s.state = 'loading'; load(); });
    box.appendChild(b);
    return box;
  }
  function section(id, heading) {
    const sec = h('section', 'r-sec');
    sec.id = id;
    sec.appendChild(h('h2', 'r-sec-h', heading));
    return sec;
  }
  // The text of a scope, or its skeleton / notice. `fill(body, into)` draws a body that was read.
  function scopeBody(scope, sec, fill) {
    const s = sc(scope);
    if (s.state === 'loading') { sec.appendChild(skeleton()); return; }
    if (s.state === 'error') { sec.appendChild(notice(scope)); return; }
    const body = h('div', 'r-text');
    fill(s.body, body);
    sec.appendChild(body);
  }
  function renderShared() {
    const sec = section('rules-shared', t('rules.shared.all'));
    scopeBody('global', sec, function (body, into) { renderBlocks(M.parse(body), into); });
    return sec;
  }
  function renderLang() {
    const lang = S.lang;
    const sec = section('rules-lang', t('rules.lang', { language: langName(lang) }));
    scopeBody(lang, sec, function (body, into) {
      if (isSeedNone(body)) into.appendChild(h('p', 'r-empty', t('rules.empty', { language: langName(lang) })));
      else renderBlocks(M.parse(body), into);
    });
    return sec;
  }
  function renderGlossary() {
    const lang = S.lang;
    const sec = section('rules-glossary', t('rules.glossary'));
    scopeBody('glossary:' + lang, sec, function (body, into) {
      const terms = M.parseGlossary(body).terms;
      if (!terms.length) { into.appendChild(h('p', 'r-empty', t('rules.glossary.empty'))); return; }
      const rows = [[t('rules.glossary.en'), langName(lang), t('rules.glossary.keep')]];
      terms.forEach(function (term) { rows.push([term.en, term.to, term.keep ? t('rules.glossary.yes') : '']); });
      const table = tableOf(rows, true);
      table.classList.add('r-glossary');
      into.appendChild(table);
    });
    return sec;
  }
  function render() {
    tabs.forEach(function (b) {
      const on = b.dataset.lang === S.lang;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    panel.setAttribute('aria-labelledby', 'rulesTab-' + S.lang);
    panel.dataset.lang = S.lang;
    panel.textContent = '';
    panel.appendChild(renderShared());
    panel.appendChild(renderLang());
    panel.appendChild(renderGlossary());
  }

  // ── the language tabs ────────────────────────────────────────────────────────────
  function choose(code, focus) {
    if (!known(code)) return;
    const b = tabs.find(function (x) { return x.dataset.lang === code; });
    if (code !== S.lang) {
      S.lang = code;
      const u = new URL(location.href);
      u.searchParams.set('lang', code);
      history.replaceState(null, '', u);
      load();
    }
    if (focus && b) b.focus();
  }
  tabs.forEach(function (b, i) {
    b.addEventListener('click', function () { choose(b.dataset.lang, false); });
    b.addEventListener('keydown', function (e) {
      let to = null;
      if (e.key === 'ArrowRight') to = tabs[(i + 1) % tabs.length];
      else if (e.key === 'ArrowLeft') to = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (e.key === 'Home') to = tabs[0];
      else if (e.key === 'End') to = tabs[tabs.length - 1];
      if (!to) return;
      e.preventDefault();
      choose(to.dataset.lang, true);
    });
  });

  load();
})();
