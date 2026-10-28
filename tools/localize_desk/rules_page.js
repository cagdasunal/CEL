/*
 * The rules page of the localization desk: /admin/localization/rules/ (CEL-089 option A; CEL-113 the editor).
 * The client picks a page tab (Rules / Word list / Import) and a language, reads the translation rules the
 * engine gives Gemini for it (that language's own rule set, Worker scope `<lang>`, read with desk-rules-read)
 * and edits them in place: every rule line carries its ID as a tag ([DE-12] at the end of the line, shown apart),
 * Edit opens the row with Save / Cancel, Remove drops it, "Add a rule" ends each section. Each Save, Remove and
 * Add is ONE desk-rules-write that applies at once (no draft, no publish step), sent with the version the page
 * read as baseVersion; a 409 says someone changed the language first and keeps the typed text; the desk toast
 * "<ID> applied." carries Undo (one more write). The Word list tab is one table of the language's words (scope
 * `words:<lang>`: Term, Translation, Type), chips by Type, a search, "Add a word", Edit / Remove per row; each Save,
 * Remove and Add is one write of that scope the same way. Import is drawn by rules_import.js (CEL-114).
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
  const TIMING = Object.assign({ timeout: 20000, toast: 6000 }, window.RULES_TIMING || {});

  const root = document.getElementById('rules-app');
  if (!root) return;
  const $ = function (s, r) { return (r || document).querySelector(s); };
  const panel = $('#rulesPanel');
  const tabs = Array.prototype.slice.call(root.querySelectorAll('.r-tab'));
  const navs = Array.prototype.slice.call(root.querySelectorAll('.r-nav-b'));      // Rules / Word list / Import

  function h(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ── state ────────────────────────────────────────────────────────────────────────
  const known = function (code) { return LOCALES.some(function (l) { return l.code === code; }); };
  const PTABS = ['rules', 'words', 'import'];
  const wanted = new URLSearchParams(location.search).get('lang');
  const wantedTab = new URLSearchParams(location.search).get('tab');
  const S = {
    lang: known(wanted) ? wanted : (known('de') ? 'de' : LOCALES[0].code),
    tab: PTABS.indexOf(wantedTab) >= 0 ? wantedTab : 'rules',
    scopes: {},       // scope -> {state: 'loading' | 'ok' | 'error', body, version, key}
    q: '',            // the Rules tab's search
    open: null,       // the one rule being edited or added: {kind: 'edit', idx, id, text, err} | {kind: 'new', sec, text, err}
    wq: '',           // the Word list's search
    wtype: 'all',     // the Word list's Type chip: all | keep | always | kw
    wopen: null,      // the one word being edited or added: {kind: 'edit' | 'add', idx, term, tr, type, err}
    wlast: null,      // the word just added: scrolled into view once
    busy: false,      // a write is on its way
  };
  const langName = function (code) {
    const l = LOCALES.find(function (x) { return x.code === code; });
    return l ? l.name : code;
  };
  const sc = function (scope) {
    if (!S.scopes[scope]) S.scopes[scope] = { state: 'loading', body: null, version: 0, key: null };
    return S.scopes[scope];
  };
  const wordsScope = function (lang) { return 'words:' + lang; };
  const blank = function (body) { return String(body == null ? '' : body).trim() === ''; };
  // The scopes the open tab reads for a language: Rules reads the language, Word list reads `words:<lang>` and, while
  // nothing has been written there, the client's `glossary:<lang>` as its starting table; Import reads nothing yet.
  const scopesFor = function (lang) {
    if (S.tab === 'rules') return [lang];
    if (S.tab !== 'words') return [];
    const w = sc(wordsScope(lang));
    return w.state === 'ok' && blank(w.body) ? [wordsScope(lang), 'glossary:' + lang] : [wordsScope(lang)];
  };

  // ── the Worker ───────────────────────────────────────────────────────────────────
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
      s.version = Number.isInteger(r.body.version) ? r.body.version : 0;     // the baseVersion of the next write
    });
  }
  function load() {
    const lang = S.lang, tab = S.tab;
    scopesFor(lang).forEach(function (x) { if (sc(x).state !== 'ok') sc(x).state = 'loading'; });
    root.dataset.state = 'loading';
    render();
    // a first answer can name one more scope to read (the glossary behind an empty word list): read again until none is missing
    const pass = function () {
      return Promise.all(scopesFor(lang).map(readScope)).then(function () {
        if (lang !== S.lang || tab !== S.tab) return;      // the reader moved on to another language or tab meanwhile
        if (scopesFor(lang).some(function (x) { return sc(x).state === 'loading'; })) return pass();
        root.dataset.state = scopesFor(lang).every(function (x) { return sc(x).state === 'ok'; }) ? 'ready' : 'error';
        render();
      });
    };
    return pass();
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
  // A language with no row yet (version 0, no body), or the pre-CEL-085 seed's one quoted line: no rules yet.
  function isSeedNone(body) {
    const b = String(body || '').trim();
    return b === '' || (/^>/.test(b) && b.split('\n').length === 1);
  }

  // ── option A (CEL-089, the operator's pick of CEL-088): the client's document, section by section ──
  // Every request line of the client's numbered sections, in their order, with how the tool carries it out.
  // "Done by" comes from CFG.doneBy (built from the engine and CEL-083's checklists by the monorepo's
  // runtime/out/loc2/CEL-089/build_done_by.py): a line is keyed by the FNV-1a 32 of its trimmed text WITHOUT its
  // trailing ` [XX-N]` rule ID (CEL-113: the ID is a tag, not part of the line the map was built from), the values
  // are reason keys, so the public page carries no client words and no rule ids. A line the map does not name
  // (a rule whose text was edited here, or added here) is in the prompt: the whole language block is what Gemini reads.
  const DONE = CFG.doneBy || { sections: [], langs: {} };
  const SHOWN = DONE.sections || [];
  const BY_KEY = { check: 'rules.by.check', prompt: 'rules.by.prompt', none: 'rules.by.none' };
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
  // A rule's ID is the last thing on its line: ` [DE-12]` (two capitals, a dash, digits; CEL-113 rule-id scheme).
  const ID_TAIL = /\s\[([A-Z]{2}-\d+)\]\s*$/;
  const unid = function (raw) { return String(raw).replace(ID_TAIL, ''); };
  const idOf = function (raw) { const m = ID_TAIL.exec(String(raw)); return m ? m[1] : ''; };
  function doneBy(lang, raw) {
    const got = (DONE.langs[lang] || {})[fnv(unid(raw))];
    return { by: got ? got[0] : 'prompt', code: got ? got[1] || '' : '', warn: got ? got[2] || '' : '' };
  }
  // Our own quality rules (CEL-099): per language [kind, key, params], built from the engine's draft.py, gates.py and
  // rules/ (runtime/out/loc2/CEL-099/build_quality.py); the words are COPY's `rules.qc.<key>`, the numbers the source's.
  const QUALITY = (CFG.quality || {}).langs || {};
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
  const leadIn = function (b) { return /:\**\s*$/.test(unid(b.text || b.raw)); };
  const indented = function (b) { return /^\s+/.test(b.raw); };

  // The language block as option A reads it: the numbered sections the canvas shows, their rows, the tone pairs.
  // Every row of a section keeps its block (`block`) so a Save can change that one line of the body; a section keeps
  // where its last request ends (`end`, a block index) so "Add a rule" can put a new line there.
  function readBlock(lang, body) {
    const blocks = M.parse(body);
    blocks.forEach(function (b, i) { b.idx = i; });
    const parts = M.sections(blocks);
    const intro = parts[0].blocks.filter(function (b) { return b.kind === 'para' || b.kind === 'quote'; });
    const secs = [], pairs = [], drift = [];
    parts.slice(1).forEach(function (p) {
      const m = /^(\d+)\.\s+(.*)$/.exec(p.head.text.trim());
      if (m && SHOWN.indexOf(m[1]) >= 0) {
        const rows = [];
        let header = null, prevRow = false, end = p.head.idx;
        p.blocks.forEach(function (b, i) {
          if (b.kind === 'sep' || b.kind === 'blank' || b.kind === 'hr') return;
          end = b.idx;
          if (b.kind === 'row') {
            const next = p.blocks[i + 1];
            if (!prevRow && next && next.kind === 'sep') { header = b.cells; prevRow = true; return; }
            prevRow = true;
            rows.push({ kind: 'req', cells: b.cells, header: header, raw: b.raw, d: doneBy(lang, b.raw), block: b });
            return;
          }
          prevRow = false;
          if (b.kind === 'head') { rows.push({ kind: 'sub', text: b.text }); return; }
          if (b.kind === 'item' && indented(b)) { rows.push({ kind: 'ctx', text: b.text }); return; }
          if (leadIn(b)) { rows.push({ kind: 'ctx', text: b.text }); return; }
          rows.push({ kind: 'req', text: unid(b.text), id: idOf(b.text), raw: b.raw, d: doneBy(lang, b.raw), block: b });
        });
        secs.push({ no: m[1], title: m[2], rows: rows, end: end });
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
    return { blocks: blocks, intro: intro, secs: secs, pairs: pairs, drift: drift };
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
  // ── a rule: its ID tag, its words (or its editor), how it is carried out, Edit / Remove ──────────────
  const labelOf = function (r) { return r.id || String(r.text || '').slice(0, 28); };
  const clean = function (x, block) {
    const v = String(x == null ? '' : x).replace(/\r/g, '');
    return (block.kind === 'item' ? v.replace(/\s*\n\s*/g, ' ') : v).trim();
  };
  function actBtn(key, label, fn) {
    const b = h('button', 'r-act', t(key));
    b.type = 'button';
    b.setAttribute('aria-label', t(key) + ' ' + label);
    b.addEventListener('click', fn);
    return b;
  }
  function deskBtn(cls, key, fn) {
    const b = h('button', 'desk-btn' + (cls ? ' ' + cls : ''), t(key));
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }
  // The open editor of a rule being edited or added: one textarea, Save and Cancel; a refusal says why under it.
  function editBox(o, label) {
    const box = h('div', 'r-editbox');
    const lab = h('label', 'r-vh', t('rules.rule.label', { id: label }));
    const ta = h('textarea', 'r-input');
    ta.id = 'rules-ed';
    lab.htmlFor = ta.id;
    ta.rows = o.kind === 'new' ? 3 : 4;
    ta.value = o.text;
    if (o.kind === 'new') ta.placeholder = t('rules.new.placeholder');
    ta.addEventListener('input', function () { o.text = ta.value; });
    ta.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); closeEditor(); } });
    box.appendChild(lab);
    box.appendChild(ta);
    if (o.err) {
      const n = h('div', 'r-notice');
      n.setAttribute('role', 'alert');
      n.appendChild(h('p', null, o.err));
      box.appendChild(n);
    }
    const acts = h('div', 'r-edit-acts');
    acts.appendChild(deskBtn('is-strong', 'rules.save', function () { saveEditor(); }));
    acts.appendChild(deskBtn('', 'rules.cancel', closeEditor));
    box.appendChild(acts);
    return box;
  }
  function sideOf(r) {
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
    return side;
  }
  function reqRow(r) {
    const row = h('div', 'r-rule');
    row.dataset.by = r.d.by;
    if (r.id) row.dataset.id = r.id;
    const editing = S.open && S.open.kind === 'edit' && S.open.idx === r.block.idx;
    if (editing) row.classList.add('is-editing');
    const rid = h('div', 'r-rid');
    if (r.id) rid.appendChild(h('span', 'r-id', r.id));
    row.appendChild(rid);
    if (editing) row.appendChild(editBox(S.open, r.id || labelOf(r)));
    else {
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
    }
    row.appendChild(sideOf(r));
    const acts = h('div', 'r-acts');
    if (!editing && !r.cells) {                    // a table row has no ID and no Edit: the table is the client's layout
      acts.appendChild(actBtn('rules.edit', labelOf(r), function () { openEditor({ kind: 'edit', idx: r.block.idx, text: r.text, initial: r.text, id: r.id }); }));
      acts.appendChild(actBtn('rules.remove', labelOf(r), function () { removeRule(r.block.idx, labelOf(r)); }));
    }
    row.appendChild(acts);
    row.dataset.q = (r.id + ' ' + (r.cells ? r.cells.join(' ') : r.text)).toLowerCase();
    return row;
  }
  function newRow(sec) {
    const lang = S.lang.toUpperCase();
    const row = h('div', 'r-rule is-new');
    const rid = h('div', 'r-rid');
    rid.appendChild(h('span', 'r-id is-new', t('rules.new.id', { lang: lang })));
    rid.appendChild(h('span', 'r-state is-new', t('rules.state.new')));
    row.appendChild(rid);
    row.appendChild(editBox(S.open, lang + '-?'));
    row.appendChild(h('div'));
    row.appendChild(h('div'));
    return row;
  }
  function renderSec(s) {
    const sec = section('rules-s' + s.no, s.title, s.no);
    sec.dataset.sec = s.no;
    s.rows.forEach(function (r) {
      if (r.kind === 'sub') sec.appendChild(textNode('h3', 'r-sub', r.text));
      else if (r.kind === 'ctx') sec.appendChild(textNode('p', 'r-ctx', r.text));
      else sec.appendChild(reqRow(r));
    });
    const adding = S.open && S.open.kind === 'new' && S.open.sec === s.no;
    if (adding) sec.appendChild(newRow(s));
    const add = h('button', 'r-add', t('rules.add'));
    add.type = 'button';
    add.hidden = !!adding;
    add.addEventListener('click', function () { openEditor({ kind: 'new', sec: s.no, text: '' }); });
    sec.appendChild(add);
    return sec;
  }
  function renderQuality(lang) {
    const sec = section('rules-quality', t('rules.quality'));
    QUALITY[lang].forEach(function (e) {
      const row = h('div', 'r-qc');
      row.dataset.kind = e[0];
      const words = t('rules.qc.' + e[1], Object.assign({ language: langName(lang) }, e[2]));
      row.appendChild(h('div', 'r-words', words));
      row.dataset.q = words.toLowerCase();
      const side = h('div', 'r-side');
      if (e[0] === 'prompt') side.appendChild(pill('prompt'));
      else {
        const p = h('span', 'r-by check');
        p.appendChild(h('span', 'r-mk'));
        p.appendChild(document.createTextNode(t('rules.qc.auto')));
        side.appendChild(p);
      }
      row.appendChild(side);
      sec.appendChild(row);
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
  function count(doc) {
    let n = 0;
    doc.secs.forEach(function (s) { s.rows.forEach(function (r) { if (r.kind === 'req') n++; }); });
    return n;
  }
  function renderSummary(doc, into) {
    const sum = h('div', 'r-sum-a');
    const lead = h('div', 'r-lead');
    lead.appendChild(h('div', 'r-big', tn('rules.count', count(doc))));
    lead.appendChild(h('p', 'r-sub', t('rules.count.sub', { language: langName(S.lang) })));
    doc.intro.forEach(function (b) { lead.appendChild(textNode('p', 'r-intro', b.text)); });
    sum.appendChild(lead);
    const box = h('label', 'r-search');
    box.appendChild(h('span', 'r-vh', t('rules.search')));
    const inp = h('input');
    inp.type = 'search';
    inp.placeholder = t('rules.search');
    inp.value = S.q;
    inp.dataset.search = '';
    inp.addEventListener('input', function () { S.q = inp.value; applyFilter(); });
    box.appendChild(inp);
    sum.appendChild(box);
    into.appendChild(sum);
  }
  // The search hides the rules and checks that do not hold the words typed, then a section or rail entry with none left.
  // An open editor is never hidden. Nothing is read or written.
  function applyFilter() {
    const q = S.q.trim().toLowerCase();
    let shown = 0;
    panel.querySelectorAll('.r-doc > section').forEach(function (sec) {
      let n = 0;
      sec.querySelectorAll('[data-q], .r-rule.is-new').forEach(function (x) {
        const hit = !q || x.classList.contains('is-editing') || x.classList.contains('is-new') || x.dataset.q.indexOf(q) >= 0;
        x.hidden = !hit;
        if (hit) n++;
      });
      const has = sec.querySelector('[data-q], .r-rule.is-new');
      sec.hidden = !!q && has != null && n === 0;
      if (!sec.hidden && has) shown += n;
      const link = panel.querySelector('.r-rail-a[href="#' + sec.id + '"]');
      if (link) link.hidden = sec.hidden;
    });
    const none = panel.querySelector('[data-noresult]');
    if (none) none.hidden = !q || shown > 0;
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
      if ((QUALITY[lang] || []).length) wrap.appendChild(renderQuality(lang));     // ours apply without the client's
      return wrap;
    }
    const doc = readBlock(lang, s.body);
    renderSummary(doc, wrap);
    const layout = h('div', 'r-layout');
    const rail = h('nav', 'r-rail');
    rail.setAttribute('aria-label', t('rules.sections'));
    const main = h('div', 'r-doc');
    doc.secs.forEach(function (x) {
      const n = x.rows.filter(function (r) { return r.kind === 'req'; }).length;
      rail.appendChild(railLink('rules-s' + x.no, x.title, n, x.no));
      main.appendChild(renderSec(x));
    });
    if ((QUALITY[lang] || []).length) {
      rail.appendChild(railLink('rules-quality', t('rules.quality')));
      main.appendChild(renderQuality(lang));
    }
    if (doc.pairs.length || doc.drift.length) {
      rail.appendChild(railLink('rules-tone', t('rules.tone')));
      main.appendChild(renderTone(doc));
    }
    const none = h('p', 'r-empty', t('rules.noresult'));
    none.dataset.noresult = '';
    none.hidden = true;
    main.appendChild(none);
    layout.appendChild(rail);
    layout.appendChild(main);
    wrap.appendChild(layout);
    return wrap;
  }

  // ── writing: each Save, Remove and Add is ONE rules write that applies at once ───────────────────────
  // The write carries the version this page read (`baseVersion`). A 409 means someone changed the language first:
  // the message says so, the typed text stays in its open row. Undo is one more write, of the body as it was.
  function problem(o, r, lang) {
    let msg;
    if (r && r.status === 409) msg = t('rules.apply.stale', { language: langName(lang) });
    else if (!r || r.status === 401 || r.status === 429) msg = t(failureKey(r));
    else msg = t('rules.apply.failed', { reason: (r.body && r.body.error) || String(r.status) });
    if (o && (S.open === o || S.wopen === o) && lang === S.lang) { o.err = msg; o.focus = true; render(); }
    else toast(msg, 'err');
  }
  // `scope` is the language (its rules) or `words:<lang>`; the write carries that scope's own version.
  function put(scope, body) {
    return call({ action: 'desk-rules-write', scope: scope, body: body, baseVersion: sc(scope).version });
  }
  // `prevBody` (words only) is what Undo writes back when the scope had no body to write back. The language is the
  // scope's own, never the tab shown now: a write that waited on a read still goes to, and reports on, its language.
  function commit(o, newBody, label, doneKey, scope0, prevBody) {
    const scope = scope0 || S.lang, lang = scope.indexOf('words:') === 0 ? scope.slice(6) : scope;
    const s = sc(scope), prev = prevBody != null ? prevBody : s.body;
    S.busy = true;
    root.dataset.busy = 'true';
    return put(scope, newBody).then(function (r) {
      S.busy = false;
      delete root.dataset.busy;
      if (r && r.ok) {
        s.body = newBody;
        if (r.body && Number.isInteger(r.body.version)) s.version = r.body.version;
        if (S.open === o) S.open = null;
        if (S.wopen === o) S.wopen = null;
        if (lang === S.lang) render();
        toast(t(doneKey, { id: label, term: label }), 'ok', function () { undo(scope, prev, lang); });
        return;
      }
      problem(o, r, lang);
    });
  }
  function undo(scope, prevBody, lang) {
    if (S.busy) return;
    S.busy = true;
    return put(scope, prevBody).then(function (r) {
      S.busy = false;
      if (r && r.ok) {
        const s = sc(scope);
        s.body = prevBody;
        if (r.body && Number.isInteger(r.body.version)) s.version = r.body.version;
        if (lang === S.lang) render();
        return;
      }
      problem(null, r, lang);
    });
  }
  // The number after the highest this language ever used: the body now and every body in its history (a removed
  // rule's number is not given again). A history that cannot be read leaves the body now.
  function nextNumber(lang, body) {
    const re = new RegExp('\\[' + lang.toUpperCase() + '-(\\d+)\\]', 'g');
    const seen = function (text) { let m, hi = 0; re.lastIndex = 0; while ((m = re.exec(String(text || '')))) hi = Math.max(hi, Number(m[1])); return hi; };
    return call({ action: 'desk-rules-history', scope: lang }).then(function (r) {
      let hi = seen(body);
      if (r && r.ok && r.body && Array.isArray(r.body.history)) r.body.history.forEach(function (x) { hi = Math.max(hi, seen(x.body)); });
      return hi + 1;
    });
  }
  function openEditor(o) {
    if (S.busy) return;
    o.focus = true;
    S.open = o;
    render();
  }
  function closeEditor() {
    S.open = null;
    render();
  }
  function saveEditor() {
    const o = S.open;
    if (!o || S.busy) return;
    const s = sc(S.lang);
    const doc = readBlock(S.lang, s.body);
    if (o.kind === 'edit') {
      const b = doc.blocks[o.idx];
      if (!b || (b.kind !== 'item' && b.kind !== 'para')) { o.err = t('rules.apply.stale', { language: langName(S.lang) }); o.focus = true; render(); return; }
      const text = clean(o.text, b);
      if (!text) { o.err = t('rules.empty.rule'); o.focus = true; render(); return; }
      if (text === o.initial) { closeEditor(); return; }                 // nothing changed: nothing to write
      b.text = text + (o.id ? ' [' + o.id + ']' : '');
      b.edited = true;
      commit(o, M.serialize(doc.blocks), o.id || text.slice(0, 28), 'rules.applied');
      return;
    }
    const sec = doc.secs.find(function (x) { return x.no === o.sec; });
    const text = clean(o.text, { kind: 'item' });
    if (!sec) { o.err = t('rules.apply.stale', { language: langName(S.lang) }); o.focus = true; render(); return; }
    if (!text) { o.err = t('rules.empty.rule'); o.focus = true; render(); return; }
    const lang = S.lang;                   // taken before the read: a tab switched during it must not change the scope
    S.busy = true;
    nextNumber(lang, s.body).then(function (n) {
      S.busy = false;
      const id = lang.toUpperCase() + '-' + n;
      const after = doc.blocks[sec.end];
      const ins = [];
      if (after && after.kind !== 'item') ins.push({ kind: 'blank', raw: '' });
      ins.push({ kind: 'item', raw: '', prefix: after && after.kind === 'item' && !/\d/.test(after.prefix) ? after.prefix : '- ', text: text + ' [' + id + ']', edited: true });
      Array.prototype.splice.apply(doc.blocks, [sec.end + 1, 0].concat(ins));
      return commit(o, M.serialize(doc.blocks), id, 'rules.applied', lang);
    });
  }
  function removeRule(idx, label) {
    if (S.busy) return;
    const s = sc(S.lang);
    const doc = readBlock(S.lang, s.body);
    const b = doc.blocks[idx];
    if (!b || (b.kind !== 'item' && b.kind !== 'para')) { problem(null, { status: 409 }, S.lang); return; }
    doc.blocks.splice(idx, 1);
    S.open = null;
    commit(null, M.serialize(doc.blocks), label, 'rules.removed');
  }

  // ── the Word list tab: one table of the language's words (scope `words:<lang>`), chips by Type, a search, ────────
  // "Add a word" (opens the add row), Edit / Remove per row. Each Save, Remove and Add is ONE write of the scope,
  // with the version the page read; the body is changed block by block, so a line this page does not know stays as it was.
  const TYPES = ['keep', 'always', 'kw'];
  const TYPE_KEY = { keep: 'words.keep', always: 'words.always', kw: 'words.keyword' };
  const TYPE_CLS = { keep: 'is-keep', always: 'is-always', kw: 'is-kw' };
  const one = function (x) { return String(x == null ? '' : x).replace(/\s+/g, ' ').trim(); };

  // The table now shown, as a body: `words:<lang>`, or, while nothing is written there, the client's glossary as
  // the starting table ('' = no table at all). The first write of a language writes this whole table.
  function wordsNow(lang) {
    const w = sc(wordsScope(lang));
    if (!blank(w.body)) return String(w.body);
    const g = sc('glossary:' + lang);
    const rows = g.state === 'ok' && !blank(g.body) ? M.wordsFromGlossary(g.body) : [];
    return rows.length ? M.wordsBody(rows) : '';
  }
  function translationCell(w) {
    const td = h('td');
    if (w.type === 'keep') td.appendChild(h('span', 'r-same', t('words.same')));
    else if (w.type === 'kw') {
      const dash = h('span', null, '–');
      dash.setAttribute('aria-hidden', 'true');
      td.appendChild(dash);
      td.appendChild(h('span', 'r-vh', t('words.none.sr')));
    } else td.textContent = w.tr;
    return td;
  }
  function wordRow(w) {
    const row = h('tr');
    row.dataset.type = w.type;
    row.dataset.q = (w.term + ' ' + (w.type === 'always' ? w.tr : '')).toLowerCase();
    row.appendChild(h('td', 'r-w-term', w.term));
    row.appendChild(translationCell(w));
    const ty = h('td');
    ty.appendChild(h('span', 'r-type ' + TYPE_CLS[w.type], t(TYPE_KEY[w.type])));
    row.appendChild(ty);
    const acts = h('td', 'r-w-acts');
    acts.appendChild(actBtn('rules.edit', w.term, function () { openWord({ kind: 'edit', idx: w.idx, term: w.term, tr: w.tr, type: w.type }); }));
    acts.appendChild(actBtn('rules.remove', w.term, function () { removeWord(w); }));
    row.appendChild(acts);
    return row;
  }
  // The open row of a word being added or edited: Word or phrase, Translation (off unless the Type is Always
  // translate as), Type, Save, Cancel; a refusal says why in a row under it. Enter saves, Escape cancels.
  function wordEditRows(o) {
    const lab = function (text, id) { const l = h('label', 'r-vh', text); l.htmlFor = id; return l; };
    const row = h('tr', 'is-adding');
    const term = h('input', 'r-field');
    term.id = 'words-ed-term';
    term.value = o.term;
    term.placeholder = t('words.new.term');
    term.addEventListener('input', function () { o.term = term.value; });
    const tr = h('input', 'r-field');
    tr.id = 'words-ed-tr';
    tr.addEventListener('input', function () { o.tr = tr.value; });
    const type = h('select', 'desk-select');
    type.id = 'words-ed-type';
    TYPES.forEach(function (k) {
      const op = h('option', null, t(TYPE_KEY[k]));
      op.value = k;
      op.selected = k === o.type;
      type.appendChild(op);
    });
    const sync = function () {
      const on = o.type === 'always';
      tr.disabled = !on;
      tr.value = on ? o.tr : '';
      tr.placeholder = t(on ? 'words.translation' : 'words.new.none');
    };
    type.addEventListener('change', function () { o.type = type.value; sync(); });
    sync();
    [term, tr, type].forEach(function (x) {
      x.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); closeWord(); }
        else if (e.key === 'Enter' && x !== type) { e.preventDefault(); saveWord(); }
      });
    });
    [[lab(t('words.new.term'), term.id), term], [lab(t('words.translation'), tr.id), tr], [lab(t('words.type'), type.id), type]].forEach(function (p) {
      const td = h('td');
      td.appendChild(p[0]);
      td.appendChild(p[1]);
      row.appendChild(td);
    });
    const acts = h('td', 'r-w-acts');
    acts.appendChild(deskBtn('is-strong', 'rules.save', function () { saveWord(); }));
    acts.appendChild(deskBtn('', 'rules.cancel', closeWord));
    row.appendChild(acts);
    const out = [row];
    if (o.err) {
      const er = h('tr', 'is-adding');
      const td = h('td');
      td.colSpan = 4;
      const n = h('div', 'r-notice');
      n.setAttribute('role', 'alert');
      n.appendChild(h('p', null, o.err));
      td.appendChild(n);
      er.appendChild(td);
      out.push(er);
    }
    return out;
  }
  function renderWords() {
    const lang = S.lang;
    const wrap = h('div', 'r-page');
    wrap.id = 'rules-words';
    const need = scopesFor(lang);
    const bad = need.find(function (x) { return sc(x).state === 'error'; });
    if (bad) { wrap.appendChild(notice(bad)); return wrap; }
    if (need.some(function (x) { return sc(x).state === 'loading'; })) { wrap.appendChild(skeleton()); return wrap; }
    const rows = M.wordRows(M.parse(wordsNow(lang)));
    const adding = !!(S.wopen && S.wopen.kind === 'add');

    // The count with Add a word beside it (the Rules tab's summary); the filters (chips + search) have the row below,
    // so the button is not read as part of the search (operator OL-335, CEL-110's revised option A).
    const sum = h('div', 'r-sum-a');
    sum.appendChild(h('div', 'r-big', tn('words.count', rows.length)));
    const add = deskBtn('is-strong', 'words.add', function () { openWord({ kind: 'add', term: '', tr: '', type: 'always' }); });
    add.dataset.addOpen = '';
    add.hidden = adding;
    sum.appendChild(add);
    wrap.appendChild(sum);
    const tools = h('div', 'r-wtools');
    const chips = h('div', 'r-chips');
    chips.setAttribute('role', 'group');
    chips.setAttribute('aria-label', t('words.type'));
    [['all', 'words.all']].concat(TYPES.map(function (k) { return [k, TYPE_KEY[k]]; })).forEach(function (c) {
      const b = h('button', 'r-chip');
      b.type = 'button';
      b.dataset.chip = c[0];
      b.appendChild(document.createTextNode(t(c[1]) + ' '));
      b.appendChild(h('span', 'r-chip-n', String(c[0] === 'all' ? rows.length : rows.filter(function (w) { return w.type === c[0]; }).length)));
      b.addEventListener('click', function () { S.wtype = c[0]; applyWordFilter(); });
      chips.appendChild(b);
    });
    tools.appendChild(chips);
    const box = h('label', 'r-search');
    box.appendChild(h('span', 'r-vh', t('words.search')));
    const inp = h('input');
    inp.type = 'search';
    inp.placeholder = t('words.search');
    inp.value = S.wq;
    inp.dataset.search = '';
    inp.addEventListener('input', function () { S.wq = inp.value; applyWordFilter(); });
    box.appendChild(inp);
    tools.appendChild(box);
    wrap.appendChild(tools);

    const table = h('table', 'r-table r-wtable');
    const head = h('tr');
    [['words.term'], ['words.translation'], ['words.type'], ['words.actions', true]].forEach(function (c) {
      const th = h('th');
      if (c[1]) th.appendChild(h('span', 'r-vh', t(c[0])));
      else th.textContent = t(c[0]);
      head.appendChild(th);
    });
    const thead = h('thead');
    thead.appendChild(head);
    table.appendChild(thead);
    const body = h('tbody');
    if (adding) wordEditRows(S.wopen).forEach(function (r) { body.appendChild(r); });
    rows.forEach(function (w) {
      const editing = S.wopen && S.wopen.kind === 'edit' && S.wopen.idx === w.idx;
      if (editing) wordEditRows(S.wopen).forEach(function (r) { body.appendChild(r); });
      else body.appendChild(wordRow(w));
    });
    table.appendChild(body);
    wrap.appendChild(table);
    const empty = h('p', 'r-empty', t('words.empty', { language: langName(lang) }));
    empty.hidden = rows.length > 0 || adding;
    wrap.appendChild(empty);
    const none = h('p', 'r-empty', t('words.noresult'));
    none.dataset.noresult = '';
    none.hidden = true;
    wrap.appendChild(none);
    return wrap;
  }
  // The chips and the search hide the words that do not match; an open row is never hidden. Nothing is read or written.
  function applyWordFilter() {
    const q = S.wq.trim().toLowerCase();
    let shown = 0, all = 0;
    panel.querySelectorAll('.r-wtable tbody tr[data-type]').forEach(function (row) {
      all++;
      const hit = (S.wtype === 'all' || row.dataset.type === S.wtype) && (!q || row.dataset.q.indexOf(q) >= 0);
      row.hidden = !hit;
      if (hit) shown++;
    });
    panel.querySelectorAll('.r-chip').forEach(function (c) { c.setAttribute('aria-pressed', c.dataset.chip === S.wtype ? 'true' : 'false'); });
    const none = panel.querySelector('[data-noresult]');
    if (none) none.hidden = all === 0 || shown > 0;
  }
  function openWord(o) {
    if (S.busy) return;
    o.focus = true;
    S.wopen = o;
    render();
  }
  function closeWord() {
    S.wopen = null;
    render();
  }
  function wordFail(o, msg) {
    o.err = msg;
    o.focus = true;
    render();
  }
  function saveWord() {
    const o = S.wopen;
    if (!o || S.busy) return;
    const lang = S.lang, scope = wordsScope(lang), s = sc(scope);
    const base = wordsNow(lang);
    const blocks = M.parse(base || M.wordsBody([]));
    const rows = M.wordRows(blocks);
    const term = one(o.term), tr = o.type === 'always' ? one(o.tr) : '';
    if (!term) { wordFail(o, t('words.empty.term')); return; }
    if (o.type === 'always' && !tr) { wordFail(o, t('words.empty.translation')); return; }
    if (term.indexOf('|') >= 0 || tr.indexOf('|') >= 0) { wordFail(o, t('words.pipe')); return; }      // the engine splits a row at every pipe
    const same = function (x) { return x.toLowerCase(); };                  // one() already collapsed the spacing of the typed word
    if (rows.some(function (w) { return same(one(w.term)) === same(term) && !(o.kind === 'edit' && w.idx === o.idx); })) {
      wordFail(o, t('words.duplicate', { term: term }));
      return;
    }
    const w = { term: term, tr: tr, type: o.type };
    if (o.kind === 'edit') {
      const cur = rows.find(function (x) { return x.idx === o.idx; });
      if (!cur) { wordFail(o, t('rules.apply.stale', { language: langName(lang) })); return; }
      if (cur.term === term && cur.tr === tr && cur.type === o.type) { closeWord(); return; }     // nothing changed: nothing to write
      M.setWord(blocks, o.idx, w);
    } else {
      M.addWord(blocks, w);
      S.wtype = 'all';                 // the new word must not be hidden by a chip or a search
      S.wq = '';
      S.wlast = term;
    }
    commit(o, M.serialize(blocks), term, 'words.applied', scope, blank(s.body) ? (base || M.wordsBody([])) : null);
  }
  function removeWord(w) {
    if (S.busy) return;
    const lang = S.lang, scope = wordsScope(lang), s = sc(scope);
    const base = wordsNow(lang);
    const blocks = M.parse(base);
    const cur = M.wordRows(blocks).find(function (x) { return x.idx === w.idx && x.term === w.term; });
    if (!cur) { problem(null, { status: 409 }, lang); return; }
    blocks.splice(w.idx, 1);
    S.wopen = null;
    commit(null, M.serialize(blocks), w.term, 'rules.removed', scope, blank(s.body) ? base : null);
  }

  // ── the desk's toast (document_desk.js toast(), with an Undo): a message goes after a few seconds, an error stays ──
  function toast(message, level, undoFn) {
    const stack = $('#rules-toasts');
    if (!stack) return;
    const node = h('div', 'toast is-' + (level || 'ok'));
    node.appendChild(h('span', 'toast-title r-toast-t', message));
    const drop = function () { if (node.parentNode) node.parentNode.removeChild(node); };
    if (undoFn) {
      const u = h('button', 'toast-close toast-undo', t('rules.undo'));
      u.type = 'button';
      u.addEventListener('click', function () { drop(); undoFn(); });
      node.appendChild(u);
    }
    if (level === 'err' || level === 'warn') {
      const x = h('button', 'toast-close', t('toast.close'));
      x.type = 'button';
      x.addEventListener('click', drop);
      node.appendChild(x);
    } else setTimeout(drop, TIMING.toast);
    stack.appendChild(node);
  }

  // ── the page ─────────────────────────────────────────────────────────────────────
  // Rules and Word list are drawn here; Import (rules_import.js, CEL-114) draws into the same panel.
  // The Import tab keeps its own state; it gets the page's helpers and the Worker door.
  const IMP = window.RulesImport && window.RulesDownload ? window.RulesImport.create({
    h: h, textNode: textNode, call: call, toast: toast, langName: langName, locales: LOCALES,
    lang: function () { return S.lang; }, rerender: render, failure: failureKey,
    invalidate: function () { S.scopes = {}; load(); },          // the rules changed: the next view reads them again
  }) : null;
  function renderTab() {
    if (S.tab === 'rules') return renderLang();
    if (S.tab === 'words') return renderWords();
    if (S.tab === 'import' && IMP) return IMP.render();
    const wrap = h('div', 'r-page');
    wrap.id = 'rules-' + S.tab;
    return wrap;
  }
  function render() {
    tabs.forEach(function (b) {
      const on = b.dataset.lang === S.lang;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    navs.forEach(function (b) {
      const on = b.dataset.ptab === S.tab;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    panel.setAttribute('aria-labelledby', 'rulesTab-' + S.lang);
    panel.dataset.lang = S.lang;
    panel.dataset.ptab = S.tab;
    panel.textContent = '';
    panel.appendChild(renderTab());
    if (S.tab === 'rules') applyFilter();
    if (S.tab === 'words') {
      applyWordFilter();
      const last = S.wlast;
      S.wlast = null;
      if (last) {                                      // the word just added is at the end of the table: show it
        const row = Array.prototype.find.call(panel.querySelectorAll('.r-wtable .r-w-term'), function (x) { return x.textContent === last; });
        if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
      }
    }
    if (S.open && S.open.focus) {
      const ta = $('#rules-ed', panel);
      S.open.focus = false;
      if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
    }
    if (S.wopen && S.wopen.focus) {
      const f = $('#words-ed-term', panel);
      S.wopen.focus = false;
      if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); }
    }
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
      S.open = null;                       // an open editor belongs to the language it was opened in
      S.wopen = null;
      S.q = '';                            // and a search starts empty on each language
      S.wq = '';
      S.wtype = 'all';
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
  // The page tabs (B's top menu): Rules / Word list / Import, the language stays.
  function pick(ptab, focus) {
    if (PTABS.indexOf(ptab) < 0) return;
    if (ptab !== S.tab) {
      S.tab = ptab;
      S.open = null;
      S.wopen = null;
      const u = new URL(location.href);
      u.searchParams.set('tab', ptab);
      history.replaceState(null, '', u);
      load();                              // the tab reads its own scopes; one already read is not asked again
    }
    if (focus) { const b = navs.find(function (x) { return x.dataset.ptab === ptab; }); if (b) b.focus(); }
  }
  navs.forEach(function (b, i) {
    b.addEventListener('click', function () { pick(b.dataset.ptab, false); });
    b.addEventListener('keydown', function (e) {
      let to = null;
      if (e.key === 'ArrowRight') to = navs[(i + 1) % navs.length];
      else if (e.key === 'ArrowLeft') to = navs[(i - 1 + navs.length) % navs.length];
      if (!to) return;
      e.preventDefault();
      pick(to.dataset.ptab, true);
    });
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
