/*
 * The rules page of the localization desk: /admin/localization/rules/ (CEL-080 read-only; CEL-089 option A).
 * The client picks a language and reads the translation rules the engine gives Gemini for it: that
 * language's own rule set (one self-contained block per language since CEL-085; the old shared `global`
 * scope is retired and never read), its glossary and the client's keyword brief for each page that has one
 * (Worker scopes `<lang>`, `glossary:<lang>`, `brief:<page>:<lang>`, read with desk-rules-read). Nothing on
 * this page edits, saves or publishes. Editing comes back in a later version.
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
  const PAGES = CFG.pages;                // the desk's page keys, in the desk's order (labels: page.<key>)
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
    by: 'all',        // the Done-by filter of the summary's three cards
  };
  const langName = function (code) {
    const l = LOCALES.find(function (x) { return x.code === code; });
    return l ? l.name : code;
  };
  const briefScope = function (page, lang) { return 'brief:' + page + ':' + lang; };
  const scopesFor = function (lang) {
    return [lang, 'glossary:' + lang].concat(PAGES.map(function (p) { return briefScope(p, lang); }));
  };
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
  // A language with no row yet (version 0, no body), or the pre-CEL-085 seed's one quoted line: no rules yet.
  function isSeedNone(body) {
    const b = String(body || '').trim();
    return b === '' || (/^>/.test(b) && b.split('\n').length === 1);
  }

  // ── option A (CEL-089, the operator's pick of CEL-088): the client's document, section by section ──
  // Every request line of the client's numbered sections, in their order, with how the tool carries it out.
  // "Done by" comes from CFG.doneBy (built from the engine and CEL-083's checklists by the monorepo's
  // runtime/out/loc2/CEL-089/build_done_by.py): a line is keyed by the FNV-1a 32 of its trimmed text, the values
  // are reason keys, so the public page carries no client words and no rule ids. A line the map does not name is in the prompt: the whole language
  // block is what Gemini reads.
  const DONE = CFG.doneBy || { sections: [], langs: {} };
  const SHOWN = DONE.sections || [];
  const BY_KEY = { check: 'rules.by.check', prompt: 'rules.by.prompt', none: 'rules.by.none' };
  const CAP_KEY = { check: 'rules.by.check.cap', prompt: 'rules.by.prompt.cap', none: 'rules.by.none.cap' };
  const HOW_KEY = {
    meta: 'rules.how.check.meta', rule: 'rules.how.check.rule', 'builtin.page': 'rules.how.builtin.page', 'builtin.structure': 'rules.how.builtin.structure',
    'builtin.export': 'rules.how.builtin.export', slug: 'rules.how.none.slug', glossary: 'rules.how.none.glossary',
    flag: 'rules.how.none.flag', keywords: 'rules.how.none.keywords', schema: 'rules.how.none.schema',
  };
  function fnv(s) {
    const bytes = new TextEncoder().encode(String(s).trim());
    let x = 0x811c9dc5;
    for (let i = 0; i < bytes.length; i++) { x ^= bytes[i]; x = Math.imul(x, 0x01000193) >>> 0; }
    return ('0000000' + x.toString(16)).slice(-8);
  }
  function doneBy(lang, raw) {
    const got = (DONE.langs[lang] || {})[fnv(raw)];
    return { by: got ? got[0] : 'prompt', code: got ? got[1] || '' : '', warn: got ? got[2] || '' : '' };
  }
  function howText(d) {
    return d.by === 'prompt' || !HOW_KEY[d.code] ? t('rules.how.prompt') : t(HOW_KEY[d.code]);
  }
  function pill(by) {
    const p = h('span', 'r-by ' + by);
    p.appendChild(h('span', 'r-mk'));
    p.appendChild(document.createTextNode(t(BY_KEY[by])));
    return p;
  }
  // A lead-in ("In practice:") or an indented sub-line belongs to the request around it: shown, not counted.
  const leadIn = function (b) { return /:\**\s*$/.test(b.text || b.raw); };
  const indented = function (b) { return /^\s+/.test(b.raw); };

  // The language block as option A reads it: the numbered sections the canvas shows, their rows, the tone pairs.
  function readBlock(lang, body) {
    const blocks = M.parse(body);
    const parts = M.sections(blocks);
    const intro = parts[0].blocks.filter(function (b) { return b.kind === 'para' || b.kind === 'quote'; });
    const secs = [], pairs = [], drift = [];
    parts.slice(1).forEach(function (p) {
      const m = /^(\d+)\.\s+(.*)$/.exec(p.head.text.trim());
      if (m && SHOWN.indexOf(m[1]) >= 0) {
        const rows = [];
        let header = null, prevRow = false;
        p.blocks.forEach(function (b, i) {
          if (b.kind === 'sep' || b.kind === 'blank' || b.kind === 'hr') return;
          if (b.kind === 'row') {
            const next = p.blocks[i + 1];
            if (!prevRow && next && next.kind === 'sep') { header = b.cells; prevRow = true; return; }
            prevRow = true;
            rows.push({ kind: 'req', cells: b.cells, header: header, raw: b.raw, d: doneBy(lang, b.raw) });
            return;
          }
          prevRow = false;
          if (b.kind === 'head') { rows.push({ kind: 'sub', text: b.text }); return; }
          if (b.kind === 'item' && indented(b)) { rows.push({ kind: 'ctx', text: b.text }); return; }
          if (leadIn(b)) { rows.push({ kind: 'ctx', text: b.text }); return; }
          rows.push({ kind: 'req', text: b.text, raw: b.raw, d: doneBy(lang, b.raw) });
        });
        secs.push({ no: m[1], title: m[2], rows: rows });
        return;
      }
      if (/^Snippet\s/.test(p.head.text)) {
        const pair = { k: p.head.text.replace(/^Snippet\s+\d+\s*[—-]\s*/, ''), good: '', bad: '', why: '' };
        let want = null;
        p.blocks.forEach(function (b) {
          const s = (b.text || '').trim();
          if (/^\*\*Good \(/.test(s)) { want = 'good'; return; }
          if (/^\*\*Bad \(/.test(s)) { want = 'bad'; return; }
          if (/^\*\*Source \(/.test(s)) { want = null; return; }
          if (/^\*Why this fails:\*/.test(s)) { pair.why = s.replace(/^\*Why this fails:\*\s*/, ''); return; }
          if (b.kind === 'quote' && want) { pair[want] += (pair[want] ? ' ' : '') + b.text; }
        });
        if (pair.good && pair.bad) pairs.push(pair);
        return;
      }
      if (/^Drift modes/.test(p.head.text)) {
        p.blocks.forEach(function (b) { if (b.kind === 'item') drift.push(b.text); });
      }
    });
    return { intro: intro, secs: secs, pairs: pairs, drift: drift };
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
  function section(id, heading, no) {
    const sec = h('section', 'r-sec');
    sec.id = id;
    const head = h('div', 'r-sec-head');
    if (no) head.appendChild(h('span', 'r-no', '§' + no));
    head.appendChild(textNode('h2', 'r-sec-h', heading));
    sec.appendChild(head);
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
  function reqRow(r) {
    const row = h('div', 'r-req');
    row.dataset.by = r.d.by;
    if (S.by !== 'all' && r.d.by !== S.by) row.hidden = true;
    const words = h('div', 'r-words');
    if (r.cells) {
      r.cells.forEach(function (c, i) {
        const cell = h('span', 'r-cell');
        if (r.header && r.header[i]) cell.appendChild(textNode('span', 'r-cell-h', r.header[i]));
        inline(cell, c);
        words.appendChild(cell);
      });
    } else inline(words, r.text);
    row.appendChild(words);
    const side = h('div', 'r-side');
    side.appendChild(pill(r.d.by));
    if (r.d.warn) {
      const w = h('span', 'r-by warn');
      w.appendChild(h('span', 'r-mk'));
      w.appendChild(document.createTextNode(t('rules.by.warn')));
      w.dataset.tip = t('rules.by.warn.tip');
      side.appendChild(w);
    }
    side.appendChild(h('span', 'r-how', howText(r.d)));
    row.appendChild(side);
    return row;
  }
  function renderSec(s) {
    const sec = section('rules-s' + s.no, s.title, s.no);
    s.rows.forEach(function (r) {
      if (r.kind === 'sub') sec.appendChild(textNode('h3', 'r-sub', r.text));
      else if (r.kind === 'ctx') sec.appendChild(textNode('p', 'r-ctx', r.text));
      else sec.appendChild(reqRow(r));
    });
    return sec;
  }
  function renderTone(doc) {
    const sec = section('rules-tone', t('rules.tone'));
    const box = h('div', 'r-pairs');
    doc.pairs.forEach(function (p) {
      const pair = h('div', 'r-pair');
      pair.appendChild(textNode('div', 'r-pair-k', p.k));
      const good = h('div', 'r-good');
      good.appendChild(h('span', 'r-lbl', t('rules.tone.good')));
      inline(good, p.good);
      const bad = h('div', 'r-bad');
      bad.appendChild(h('span', 'r-lbl', t('rules.tone.bad')));
      inline(bad, p.bad);
      pair.appendChild(good);
      pair.appendChild(bad);
      if (p.why) {
        const why = h('div', 'r-why');
        why.appendChild(document.createTextNode(t('rules.tone.why') + ' '));
        inline(why, p.why);
        pair.appendChild(why);
      }
      box.appendChild(pair);
    });
    doc.drift.forEach(function (d) {
      const line = h('div', 'r-drift');
      line.appendChild(h('strong', null, t('rules.tone.drift') + ' '));
      inline(line, d);
      box.appendChild(line);
    });
    sec.appendChild(box);
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
  // The client's keyword brief per page (CEL-085): one card per page that has one, under the page's English
  // name, its text collapsed; none for this language says so. One notice if a brief could not be read.
  function renderBriefs() {
    const lang = S.lang;
    const sec = section('rules-briefs', t('rules.briefs'));
    const scopes = PAGES.map(function (p) { return briefScope(p, lang); });
    if (scopes.some(function (x) { return sc(x).state === 'loading'; })) { sec.appendChild(skeleton()); return sec; }
    const failed = scopes.find(function (x) { return sc(x).state === 'error'; });
    if (failed) { sec.appendChild(notice(failed)); return sec; }
    const given = PAGES.filter(function (p) { return String(sc(briefScope(p, lang)).body || '').trim(); });
    if (!given.length) { sec.appendChild(h('p', 'r-empty', t('rules.briefs.empty'))); return sec; }
    const grid = h('div', 'r-briefs');
    given.forEach(function (p) {
      const box = h('details', 'r-brief');
      box.dataset.page = p;
      const sum = h('summary', 'r-brief-h');
      sum.appendChild(h('span', 'r-brief-name', t('page.' + p)));
      sum.appendChild(pill('prompt'));
      box.appendChild(sum);
      const body = h('div', 'r-text');
      renderBlocks(M.parse(sc(briefScope(p, lang)).body), body);
      box.appendChild(body);
      grid.appendChild(box);
    });
    sec.appendChild(grid);
    return sec;
  }
  function count(doc) {
    const c = { all: 0, check: 0, prompt: 0, none: 0 };
    doc.secs.forEach(function (s) {
      s.rows.forEach(function (r) { if (r.kind === 'req') { c.all++; c[r.d.by]++; } });
    });
    return c;
  }
  function renderSummary(doc, into) {
    const c = count(doc);
    const sum = h('div', 'r-sum');
    const lead = h('div', 'r-lead');
    lead.appendChild(h('div', 'r-big', t('rules.summary', { n: c.all })));
    lead.appendChild(h('div', 'r-sub', t('rules.summary.sub', { language: langName(S.lang) })));
    doc.intro.forEach(function (b) { lead.appendChild(textNode('p', 'r-intro', b.text)); });
    sum.appendChild(lead);
    ['check', 'prompt', 'none'].forEach(function (by) {
      const b = h('button', 'r-stat');
      b.type = 'button';
      b.dataset.by = by;
      b.setAttribute('aria-pressed', S.by === by ? 'true' : 'false');
      b.appendChild(pill(by));
      b.appendChild(h('span', 'r-num', String(c[by])));
      b.appendChild(h('span', 'r-cap', t(CAP_KEY[by])));
      b.addEventListener('click', function () { S.by = S.by === by ? 'all' : by; render(); });
      sum.appendChild(b);
    });
    into.appendChild(sum);
    const line = h('p', 'r-filterline');
    if (S.by === 'all') line.textContent = t('rules.filter.all', { n: c.all });
    else {
      line.appendChild(document.createTextNode(t('rules.filter.some', { k: c[S.by], n: c.all }) + ' '));
      const clear = h('button', 'r-clear', t('rules.filter.clear'));
      clear.type = 'button';
      clear.addEventListener('click', function () { S.by = 'all'; render(); });
      line.appendChild(clear);
    }
    into.appendChild(line);
  }
  function railLink(id, label, n, no) {
    const a = h('a', 'r-rail-a');
    a.href = '#' + id;
    a.appendChild(h('span', 'r-no', no ? '§' + no : ''));
    a.appendChild(textNode('span', 'r-rail-t', label));
    a.appendChild(h('span', 'r-rail-n', n ? String(n) : ''));
    return a;
  }
  function renderLang() {
    const lang = S.lang;
    const wrap = h('div', 'r-page');
    wrap.id = 'rules-lang';
    const s = sc(lang);
    if (s.state === 'loading') { wrap.appendChild(skeleton()); return wrap; }
    if (s.state === 'error') { wrap.appendChild(notice(lang)); return wrap; }
    if (isSeedNone(s.body)) {
      wrap.appendChild(h('p', 'r-empty', t('rules.empty', { language: langName(lang) })));
      return wrap;
    }
    const doc = readBlock(lang, s.body);
    renderSummary(doc, wrap);
    const layout = h('div', 'r-layout');
    const rail = h('nav', 'r-rail');
    rail.setAttribute('aria-label', t('rules.sections'));
    const main = h('div', 'r-doc');
    doc.secs.forEach(function (x) {
      const n = x.rows.filter(function (r) { return r.kind === 'req' && (S.by === 'all' || r.d.by === S.by); }).length;
      rail.appendChild(railLink('rules-s' + x.no, x.title, n, x.no));
      main.appendChild(renderSec(x));
    });
    if (doc.pairs.length || doc.drift.length) {
      rail.appendChild(railLink('rules-tone', t('rules.tone')));
      main.appendChild(renderTone(doc));
    }
    rail.appendChild(railLink('rules-glossary', t('rules.glossary')));
    main.appendChild(renderGlossary());
    rail.appendChild(railLink('rules-briefs', t('rules.briefs')));
    main.appendChild(renderBriefs());
    layout.appendChild(rail);
    layout.appendChild(main);
    wrap.appendChild(layout);
    return wrap;
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
    panel.appendChild(renderLang());
  }

  // ── the language tabs ────────────────────────────────────────────────────────────
  // "Back to the desk" opens the desk on the language shown here (CEL-069, shell-spec §4).
  function deskLink() {
    const a = document.getElementById('rules-desk');
    if (a) a.setAttribute('href', '/admin/localization/document/?lang=' + encodeURIComponent(S.lang));
  }
  function choose(code, focus) {
    if (!known(code)) return;
    const b = tabs.find(function (x) { return x.dataset.lang === code; });
    if (code !== S.lang) {
      S.lang = code;
      S.by = 'all';
      const u = new URL(location.href);
      u.searchParams.set('lang', code);
      history.replaceState(null, '', u);
      deskLink();
      load();
    }
    if (focus && b) b.focus();
  }
  // Alt+1..8 picks the language (shell-spec §5): Alt alone (AltGr = Ctrl+Alt types), the digit's code (on a Mac
  // `key` is the character), no IME composition, focus outside a text box. Otherwise the key is left alone.
  document.addEventListener('keydown', function (e) {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.isComposing) return;
    const at = document.activeElement;
    if (at && (/^(INPUT|TEXTAREA|SELECT)$/.test(at.tagName) || (at.closest && at.closest('[contenteditable]:not([contenteditable="false"])')))) return;
    const m = /^Digit([1-8])$/.exec(e.code || '');
    if (!m || !LOCALES[Number(m[1]) - 1]) return;
    e.preventDefault();
    choose(LOCALES[Number(m[1]) - 1].code, false);
  });
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

  deskLink();
  load();
})();
