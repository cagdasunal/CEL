/*
 * The Import tab of the rules page (CEL-114; design: CEL-110 option A, Import German). Three numbered steps:
 *   1 Get the files   - Copy prompt (clipboard), Download current rules (one language, .md, with the rule IDs),
 *                       Download template (the changes template as a new .md file)
 *   2 Upload your changes - one .md/.txt file, up to 64 KB, chosen or dropped
 *   3 Check the changes   - what the reader understood, language by language, Before -> After (a removal in red);
 *                           "Couldn't place these lines" lists every line that is not a change; Apply sends the accepted
 *                           changes in ONE desk-rules-import-apply call, or Cancel drops the file.
 * Reading writes nothing (desk-rules-import-read proposes, the Worker's code checks); only Apply writes, all
 * languages or none. rules_page.js hands over what it owns (the DOM helper, the Worker door, the toast) and draws
 * what render() returns into its panel. Every word comes from COPY.md through t(); DOM is createElement/textContent.
 * The prompt and the template are the files rules_import_template.md, put on the page by generate_rules_page.py.
 */
(function (root) {
  'use strict';

  const MAX_BYTES = 64 * 1024;                         // the route's cap (desk_store.IMPORT_MAX_BYTES)
  const COPIED_MS = 2000;
  const KIND = {
    add_rule: ['is-add', 'rules.change.add'], edit_rule: ['is-chg', 'rules.change.chg'], remove_rule: ['is-del', 'rules.change.del'],
    add_word: ['is-add', 'rules.change.add'], edit_word: ['is-chg', 'rules.change.chg'], remove_word: ['is-del', 'rules.change.del'],
  };
  const TYPE_KEY = { 'Keep as is': 'words.keep', 'Always translate as': 'words.always', 'Search keyword': 'words.keyword' };
  // Why a line was not placed: the reader's reasons and the code's refusals, each to one COPY line.
  const WHY_KEY = {
    unknown_language: 'import.why.page', language_not_requested: 'import.why.page',
    rule_not_found: 'import.why.noid',
    unreadable: 'import.why.unreadable', bad_shape: 'import.why.unreadable', empty_rule: 'import.why.unreadable', multiline: 'import.why.unreadable',
    ambiguous: 'import.why.ambiguous',
    type_unclear: 'import.why.type',
    already_exists: 'import.why.exists',
  };

  /* api: {h, textNode, call, toast, langName, locales: [{code, name, flag}], lang(), rerender(), invalidate(), failure(r)} */
  function create(api) {
    const h = api.h;
    const I = {
      dl: null,            // the language chosen for Download current rules (null = the page's language)
      phase: 'empty',      // empty | reading | ok | error
      file: null,          // {name, size, at}
      res: null,           // the read answer: {changes, unplaced, problems, bases}
      err: null,           // text of a read failure
      applying: false,
      applyErr: null,      // text of a refused Apply
      downloading: false,
    };
    const textOf = function (id) {
      const n = document.getElementById(id);
      return n ? n.textContent : '';
    };

    // ── step 1: the three files ────────────────────────────────────────────────────
    function copyPrompt(btn) {
      const text = textOf('rules-import-prompt').trim();
      const done = function () {
        btn.textContent = t('import.prompt.copied');
        setTimeout(function () { if (btn.isConnected) btn.textContent = t('import.prompt.copy'); }, COPIED_MS);
      };
      const fallback = function () {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.className = 'r-vh';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        ta.remove();
        if (ok) done();
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
      else fallback();
    }
    // A read that gives nothing to download: no answer, a refusal, or a stored text that is missing or blank.
    const nothing = function (r) { return !r || !r.ok || !r.body || r.body.body == null || String(r.body.body).trim() === ''; };
    function downloadCurrent(code) {
      if (I.downloading) return;
      I.downloading = true;
      Promise.all([
        api.call({ action: 'desk-rules-read', scope: code }),
        api.call({ action: 'desk-rules-read', scope: 'words:' + code }),
      ]).then(function (out) {
        I.downloading = false;
        const rules = out[0], words = out[1];
        if (nothing(rules) || nothing(words)) {
          api.toast(t(api.failure(nothing(rules) ? rules : words)), 'err');
          return;
        }
        const md = root.RulesDownload.rulesDownloadMarkdown({
          language: api.langName(code),
          rulesBody: rules.body.body,
          words: root.RulesDownload.parseWordsBody(words.body.body),
        });
        root.RulesDownload.saveText('cel-rules-' + code + '.md', md);
      });
    }
    function fileCard(titleKey) {
      const card = h('div', 'r-file');
      card.appendChild(h('h3', 'r-file-h', t(titleKey)));
      const acts = h('div', 'r-file-acts');
      card.appendChild(acts);
      return { card: card, acts: acts };
    }
    function button(cls, key, id) {
      const b = h('button', cls, t(key));
      b.type = 'button';
      if (id) b.id = id;
      return b;
    }
    function renderFiles() {
      const files = h('div', 'r-files');
      const p = fileCard('import.prompt');
      const copy = button('desk-btn is-strong', 'import.prompt.copy', 'imp-copy');
      copy.addEventListener('click', function () { copyPrompt(copy); });
      p.acts.appendChild(copy);
      files.appendChild(p.card);

      const c = fileCard('import.current');
      const lab = h('label', 'r-vh', t('rules.language'));
      lab.htmlFor = 'imp-dl-lang';
      const sel = h('select', 'desk-select');
      sel.id = 'imp-dl-lang';
      const picked = I.dl || api.lang();
      api.locales.forEach(function (l) {
        const o = h('option', null, l.name);
        o.value = l.code;
        o.selected = l.code === picked;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () { I.dl = sel.value; });
      const dl = button('desk-btn', 'import.current.download', 'imp-dl');
      dl.addEventListener('click', function () { downloadCurrent(sel.value); });
      c.acts.appendChild(lab);
      c.acts.appendChild(sel);
      c.acts.appendChild(dl);
      files.appendChild(c.card);

      const tp = fileCard('import.template');
      const tdl = button('desk-btn', 'import.template.download', 'imp-tpl');
      tdl.addEventListener('click', function () { root.RulesDownload.saveText('cel-rules-import-template.md', textOf('rules-import-template')); });
      tp.acts.appendChild(tdl);
      files.appendChild(tp.card);
      return files;
    }

    // ── step 2: the file ───────────────────────────────────────────────────────────
    const sizeText = function (n) { return n < 1024 ? n + ' B' : Math.round(n / 1024) + ' KB'; };
    const clock = function () {
      return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    };
    function take(file) {
      if (!file || I.phase === 'reading' || I.applying) return;
      const mine = { name: file.name, size: file.size, at: clock() };
      I.file = mine;
      I.res = null;
      I.err = null;
      I.applyErr = null;
      if (file.size > MAX_BYTES) { I.phase = 'error'; I.err = t('import.too.big'); api.rerender(); return; }
      I.phase = 'reading';
      api.rerender();
      file.text().then(function (text) {
        return api.call({ action: 'desk-rules-import-read', text: text, languages: api.locales.map(function (l) { return l.code; }) });
      }).then(function (r) {
        if (I.file !== mine) return;
        if (r && r.ok && r.body && Array.isArray(r.body.changes) && Array.isArray(r.body.unplaced)) {
          I.res = r.body;
          I.phase = 'ok';
        } else {
          I.phase = 'error';
          if (!r || r.status === 401 || r.status === 429) I.err = t(api.failure(r));       // no answer / signed out / over the cap: as for Apply
          else I.err = t('import.read.failed', { reason: r.body && r.body.error ? String(r.body.error).replace(/^invalid:\s*/, '') : r.status });
        }
        api.rerender();
      }).catch(function (e) {
        if (I.file !== mine) return;
        I.phase = 'error';
        I.err = t('import.read.failed', { reason: (e && e.message) || String(e) });
        api.rerender();
      });
    }
    function clear() {
      I.phase = 'empty';
      I.file = null;
      I.res = null;
      I.err = null;
      I.applyErr = null;
      api.rerender();
    }
    function renderUpload() {
      const box = h('div', 'r-upload');
      const input = h('input', 'r-vh');
      input.type = 'file';
      input.id = 'imp-file';
      input.accept = '.md,.txt,text/markdown,text/plain';
      input.tabIndex = -1;
      input.setAttribute('aria-hidden', 'true');
      input.addEventListener('change', function () {
        const f = input.files && input.files[0];
        input.value = '';                       // the same file can be chosen again
        take(f);
      });
      box.appendChild(input);
      const choose = function () { input.click(); };
      if (!I.file) {
        const drop = h('div', 'r-drop');
        drop.id = 'imp-drop';
        const p = h('p', 'r-drop-p', t('import.drop') + ' ');
        const b = button('desk-btn', 'import.choose', 'imp-choose');
        b.addEventListener('click', choose);
        p.appendChild(b);
        drop.appendChild(p);
        drop.appendChild(h('p', 'r-drop-cap', t('import.limits')));
        drop.addEventListener('dragover', function (e) { e.preventDefault(); });
        drop.addEventListener('drop', function (e) {
          e.preventDefault();
          take(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
        });
        box.appendChild(drop);
        return box;
      }
      const upl = h('div', 'r-upl');
      upl.appendChild(h('span', 'r-upl-name', I.file.name));
      upl.appendChild(h('span', 'r-upl-meta', t('import.file.meta', { size: sizeText(I.file.size), time: I.file.at })));
      const again = h('button', 'r-act', t('import.another'));
      again.type = 'button';
      again.id = 'imp-another';
      again.disabled = I.phase === 'reading' || I.applying;
      again.addEventListener('click', choose);
      upl.appendChild(again);
      box.appendChild(upl);
      return box;
    }

    // ── step 3: what the reader understood ─────────────────────────────────────────
    const typeName = function (type) { return TYPE_KEY[type] ? t(TYPE_KEY[type]) : (type || ''); };
    // A word on a side of the preview: the term in bold, its translation (or "same as the term"), its Type.
    function wordCell(cls, term, translation, type, keepSame) {
      const cell = h('div', cls);
      cell.appendChild(h('strong', null, term));
      const meta = [];
      if (translation) meta.push(translation);
      else if (keepSame && type === 'Keep as is') meta.push(t('words.same'));
      if (type) meta.push(typeName(type));
      if (meta.length) cell.appendChild(h('div', 'r-wmeta', meta.join(' · ')));
      return cell;
    }
    function none() { return h('div', 'r-was is-none', '—'); }
    function column(cap, node) {
      const col = h('div', 'r-pcol');
      col.appendChild(h('span', 'r-pcap', cap));
      col.appendChild(node);
      return col;
    }
    function changeRow(c) {
      const k = KIND[c.kind] || KIND.edit_rule;
      const isWord = /_word$/.test(c.kind);
      const row = h('div', 'r-pchg ' + k[0]);
      row.dataset.kind = c.kind;
      row.appendChild(isWord ? h('span', 'r-id', t('rules.change.words'))
        : c.kind === 'add_rule' ? h('span', 'r-id is-new', t('rules.new.id', { lang: c.language.toUpperCase() }))
          : h('span', 'r-id', c.target_id));
      row.appendChild(h('span', 'r-kind ' + k[0], t(k[1])));
      let before, after;
      if (isWord) {
        before = c.kind === 'add_word' ? none() : wordCell(c.kind === 'remove_word' ? 'r-gone' : 'r-was', c.term, c.before, c.kind === 'remove_word' ? c.type : null, false);
        after = c.kind === 'remove_word' ? none() : wordCell('r-now', c.term, c.after, c.type, true);
      } else {
        before = c.kind === 'add_rule' ? none() : api.textNode('div', c.kind === 'remove_rule' ? 'r-gone' : 'r-was', c.before);
        after = c.kind === 'remove_rule' ? none() : api.textNode('div', 'r-now', c.after);
      }
      row.appendChild(column(t('import.before'), before));
      row.appendChild(column(t('import.after'), after));
      return row;
    }
    // Every line the reader or the code left out, as {text, why}.
    function unplacedItems(res) {
      const out = [];
      const why = function (reason, text, lang, id) {
        const key = WHY_KEY[reason] || 'import.why.other';
        if (key !== 'import.why.noid') return t(key);
        const m = id || (/\b[A-Z]{2}-\d+\b/.exec(text) || [])[0];
        return m && lang ? t(key, { id: m, language: api.langName(lang) }) : t('import.why.other');
      };
      (res.unplaced || []).forEach(function (u) { out.push({ text: u.source_text, why: why(u.reason, u.source_text, u.language, null) }); });
      (res.problems || []).forEach(function (p) {
        const c = p.change || {};
        out.push({ text: p.source_text, why: why(p.reason, p.source_text, c.language, c.target_id) });
      });
      return out;
    }
    function renderUnplaced(items) {
      const box = h('section', 'r-unplaced');
      box.id = 'imp-unplaced';
      box.setAttribute('aria-labelledby', 'imp-unplaced-h');
      const head = h('h3', 'r-un-h', t('import.unplaced') + ' ');
      head.id = 'imp-unplaced-h';
      head.appendChild(h('span', 'r-plang-n', String(items.length)));
      box.appendChild(head);
      const list = h('ul', 'r-un-list');
      items.forEach(function (it) {
        const li = h('li', 'r-un-i');
        li.appendChild(h('q', 'r-un-q', it.text));
        li.appendChild(h('span', 'r-un-why', it.why));
        list.appendChild(li);
      });
      box.appendChild(list);
      return box;
    }
    function apply() {
      if (I.applying || !I.res || !I.res.changes.length) return;
      I.applying = true;
      I.applyErr = null;
      api.rerender();
      const n = I.res.changes.length;
      api.call({ action: 'desk-rules-import-apply', changes: I.res.changes, bases: I.res.bases }).then(function (r) {
        I.applying = false;
        if (r && r.ok) {
          clear();
          api.invalidate();
          api.toast(tn('import.applied', n), 'ok');
          return;
        }
        if (r && r.status === 409) {
          const langs = ((r.body && r.body.stale) || []).map(function (s) { return api.langName(String(s).replace(/^words:/, '')); });
          I.applyErr = t('rules.apply.stale', { language: Array.from(new Set(langs)).join(', ') });
        } else if (!r || r.status === 401 || r.status === 429) I.applyErr = t(api.failure(r));
        else I.applyErr = t('rules.apply.failed', { reason: String(r.body && r.body.error ? r.body.error : r.status).replace(/^invalid:\s*/, '') });
        api.rerender();
      });
    }
    function renderPreview() {
      const wrap = h('div', 'r-preview');
      wrap.id = 'imp-preview';
      if (I.phase === 'reading') { wrap.appendChild(h('p', 'r-empty', t('import.reading'))); return wrap; }
      if (I.phase === 'error') {
        const note = h('div', 'r-notice');
        note.setAttribute('role', 'alert');
        note.appendChild(h('p', null, I.err));
        wrap.appendChild(note);
        return wrap;
      }
      if (I.phase !== 'ok') { wrap.appendChild(h('p', 'r-empty', t('import.empty'))); return wrap; }
      const changes = I.res.changes;
      wrap.appendChild(h('p', 'r-sub-a', tn('import.found', changes.length)));
      const prev = h('div', 'r-prev');
      api.locales.forEach(function (l) {
        const mine = changes.filter(function (c) { return c.language === l.code; });
        if (!mine.length) return;
        const head = h('h3', 'r-plang');
        head.appendChild(h('span', 'r-flag', l.flag));
        head.appendChild(document.createTextNode(l.name));
        head.appendChild(h('span', 'r-plang-n', tn('import.lang.count', mine.length)));
        prev.appendChild(head);
        mine.forEach(function (c) { prev.appendChild(changeRow(c)); });
      });
      wrap.appendChild(prev);
      const un = unplacedItems(I.res);
      if (un.length) wrap.appendChild(renderUnplaced(un));
      if (I.applyErr) {
        const note = h('div', 'r-notice');
        note.setAttribute('role', 'alert');
        note.appendChild(h('p', null, I.applyErr));
        wrap.appendChild(note);
      }
      const acts = h('div', 'r-pub-a');
      if (changes.length) {
        const go = h('button', 'desk-btn is-primary', tn('import.apply', changes.length));
        go.type = 'button';
        go.id = 'imp-apply';
        go.disabled = I.applying;
        go.addEventListener('click', apply);
        acts.appendChild(go);
      }
      const cancel = button('desk-btn', 'import.cancel', 'imp-cancel');
      cancel.disabled = I.applying;
      cancel.addEventListener('click', clear);
      acts.appendChild(cancel);
      wrap.appendChild(acts);
      return wrap;
    }

    function step(n, key, body) {
      const li = h('li', 'r-step');
      li.appendChild(h('span', 'r-step-n', String(n)));
      li.lastChild.setAttribute('aria-hidden', 'true');
      const col = h('div');
      col.appendChild(h('h2', 'r-step-h', t(key)));
      col.appendChild(body);
      li.appendChild(col);
      return li;
    }
    function render() {
      const wrap = h('div', 'r-page r-import');
      wrap.id = 'rules-import';
      const steps = h('ol', 'r-steps');
      steps.appendChild(step(1, 'import.step1', renderFiles()));
      steps.appendChild(step(2, 'import.step2', renderUpload()));
      steps.appendChild(step(3, 'import.step3', renderPreview()));
      wrap.appendChild(steps);
      return wrap;
    }
    return { render: render };
  }

  root.RulesImport = { create: create };
})(typeof window !== 'undefined' ? window : globalThis);
