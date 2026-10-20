/*
 * The Export window and Re-translate of the document page (desk v2, CEL-027).
 *
 * generate_document_page.py inlines this file right after document_desk.js, which hands it the
 * page's state and a few of its functions as `window.DocDesk` (the one door; see the block before
 * `boot()` there). Everything this file shows is built with createElement / textContent and every
 * word comes from COPY.md. The contract with the tests: runtime/out/loc2/CEL-027/contract.md.
 *
 *   Export        pick pages x languages -> for each (page, language), one after the other: the page's
 *                 texts become decisions (the reviewer's edit, else Gemini's draft, approved against the
 *                 wording the website shows now) through desk-write in chunks of 50 -> the engine's
 *                 export job for that page -> its Weglot file. One file is downloaded as it is, several
 *                 as one zip made here. What was left out is listed, and a click shows the paragraph.
 *   Re-translate  one text (with an optional note) or the whole page, as the engine's retranslate job;
 *                 the old wording of a text stays on the undo stack. The page has ONE Translate page button
 *                 (the desk's): on a page that already has a translation it opens the whole-page window here
 *                 (`DocDesk.retranslatePage`); on one that has none it asks the desk's own confirm (CEL-073).
 */
(function () {
  'use strict';

  // ── pure helpers (also loaded by node for the zip test) ─────────────────────────────
  const CRC_TABLE = (function () {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();
  function crc32(bytes) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function concat(parts) {
    let total = 0;
    parts.forEach(function (p) { total += p.length; });
    const out = new Uint8Array(total);
    let at = 0;
    parts.forEach(function (p) { out.set(p, at); at += p.length; });
    return out;
  }
  // A zip of stored (uncompressed) files: [{name, data: Uint8Array}] -> Uint8Array. Names are UTF-8.
  function zip(files, when) {
    const enc = new TextEncoder();
    const time = ((when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1)) & 0xFFFF;
    const date = (((when.getFullYear() - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate()) & 0xFFFF;
    const parts = [], central = [];
    let offset = 0;
    files.forEach(function (f) {
      const name = enc.encode(f.name), crc = crc32(f.data), size = f.data.length;
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
      lh.setUint16(10, time, true); lh.setUint16(12, date, true); lh.setUint32(14, crc, true);
      lh.setUint32(18, size, true); lh.setUint32(22, size, true); lh.setUint16(26, name.length, true);
      parts.push(new Uint8Array(lh.buffer), name, f.data);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
      ch.setUint16(8, 0x0800, true); ch.setUint16(12, time, true); ch.setUint16(14, date, true);
      ch.setUint32(16, crc, true); ch.setUint32(20, size, true); ch.setUint32(24, size, true);
      ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), name);
      offset += 30 + name.length + size;
    });
    const dir = concat(central);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true);
    end.setUint16(10, files.length, true); end.setUint32(12, dir.length, true); end.setUint32(16, offset, true);
    return concat(parts.concat([dir, new Uint8Array(end.buffer)]));
  }
  // The decision a text is exported as: the reviewer's wording else Gemini's draft, approved against
  // the wording the website shows now (the English where the page shows English). null = nothing to say.
  function exportRecord(rec, draftText, block, lang, canon) {
    const edit = rec && rec.text ? rec.text : '';
    const text = edit || draftText || '';
    if (!text) return null;
    return canon(Object.assign({}, rec || {}, { tray: 'csv', text: text, approvedAgainst: (block.w && block.w[lang]) || block.en }));
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { crc32: crc32, zip: zip, exportRecord: exportRecord };
  }

  const D = typeof window !== 'undefined' ? window.DocDesk : null;
  if (!D || D.saveOff) return;

  // ── the page's state and doors ──────────────────────────────────────────────────────
  const S = D.S, L = D.L, M = D.M, PAGES = D.PAGES, LANGS = D.LANGS, TIMING = D.TIMING;
  const CFG = JSON.parse(document.getElementById('doc-config').textContent);
  const FLAG = {};
  CFG.locales.forEach(function (l) { FLAG[l.code] = l.flag; });
  const NOTE_MAX = 500;                          // the Worker's JOB_NOTE_MAX
  const SHOWN = 50;                              // list items shown per group before "and N more"

  // Spelled out so the copy check sees every key.
  const STEP_KEY = {
    waiting: 'export.step.waiting', saving: 'export.step.saving', queued: 'export.step.queued',
    running: 'export.step.running', nothing: 'export.step.nothing', stopped: 'export.step.stopped'
  };
  const GROUP_KEY = {
    refused: 'export.group.refused', orphan: 'export.group.orphan', conflict: 'export.group.conflict',
    empty: 'export.group.empty', unsaved: 'export.group.unsaved'
  };
  const GROUP_ORDER = ['refused', 'orphan', 'conflict', 'unsaved', 'empty'];

  const $ = function (id) { return document.getElementById(id); };
  function h(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function button(id, cls, text) {
    const b = h('button', cls, text);
    b.type = 'button';
    if (id) b.id = id;
    return b;
  }
  function sleep(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }
  async function until(test, ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      if (test()) return true;
      await sleep(50);
    }
    return test();
  }
  function ready() { return !S.loading && $('doc').getAttribute('data-state') === 'ready'; }
  function snippet(s) {
    const plain = String(s || '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
    return plain.length > 80 ? plain.slice(0, 79) + '…' : plain;
  }
  function jobReason(job) {
    const code = (job && job.error) || '';
    return COPY['job.failed.' + code] ? t('job.failed.' + code) : t('doc.job.failed.unknown');
  }
  function why(r) { return t('save.reason.' + D.failureReason(r)); }

  // ── windows ─────────────────────────────────────────────────────────────────────────
  // The same overlay and box the page's own confirm window uses.
  function makeOverlay(id, titleId) {
    const root = h('div', 'cpw-overlay');
    root.id = id;
    root.hidden = true;
    const box = h('div', 'cpw-modal');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', titleId);
    root.appendChild(box);
    $('doc').appendChild(root);
    return { root: root, box: box };
  }
  const opened = [];                              // the windows that are open, last = on top
  let busy = false;                               // an export is running: Escape waits
  function openOverlay(o, opener, focus) {
    o.opener = opener || null;
    o.root.hidden = false;
    opened.push(o);
    if (focus) focus.focus();
  }
  function closeOverlay(o) {
    o.root.hidden = true;
    const at = opened.indexOf(o);
    if (at >= 0) opened.splice(at, 1);
    const back = o.opener;
    o.opener = null;
    if (back && back.focus) back.focus();
  }
  document.addEventListener('keydown', function (ev) {
    const top = opened[opened.length - 1];
    if (!top) return;
    if (ev.key === 'Escape') {
      ev.stopPropagation();
      if (!busy) top.close();
      return;
    }
    if (ev.key !== 'Tab') return;
    const items = Array.prototype.filter.call(
      top.box.querySelectorAll('button, input, textarea, select, [href]'),
      function (e) { return !e.disabled && !e.hidden && e.offsetParent !== null; });
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1], at = document.activeElement;
    if (ev.shiftKey && (at === first || !top.box.contains(at))) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && (at === last || !top.box.contains(at))) { ev.preventDefault(); first.focus(); }
  }, true);

  // ── the buttons ─────────────────────────────────────────────────────────────────────
  const exportButton = button('doc-export', 'desk-btn is-primary', t('export.button'));
  (function mountButtons() {
    const bar = document.querySelector('#doc-bar .doc-actions');
    if (!bar) return;
    bar.appendChild(exportButton);
  })();

  // ── the job, watched ────────────────────────────────────────────────────────────────
  // The engine's answer to desk-job-get, polled; null when the desk could not reach it for good.
  // `maxMs`: give up on a job that never ends and call it failed (CEL-077 item 5); 0 = poll as long as it takes.
  async function watch(lang, id, onState, maxMs) {
    let misses = 0;
    const began = Date.now();
    for (;;) {
      await sleep(TIMING.poll);
      if (maxMs && Date.now() - began > maxMs) return { status: 'failed', timedOut: true };
      const r = await D.call({ action: 'desk-job-get', locale: lang, id: id });
      const job = r && r.ok && r.body && r.body.job;
      if (!job) { if (++misses >= 8) return null; continue; }
      misses = 0;
      if (job.status === 'queued' || job.status === 'running') { if (onState) onState(job.status); continue; }
      return job;
    }
  }

  // ── Export ──────────────────────────────────────────────────────────────────────────
  const ex = makeOverlay('ex-modal', 'ex-title');
  ex.close = closeEx;
  const exTitle = h('h2', 'cpw-title', t('export.title'));
  exTitle.id = 'ex-title';
  const exSelect = h('div', 'ex-select');
  const exCount = h('p', 'ex-count');
  exCount.id = 'ex-count';
  exCount.setAttribute('aria-live', 'polite');
  const exProgress = h('ol', 'ex-progress');
  exProgress.id = 'ex-progress';
  exProgress.hidden = true;
  const exResult = h('div', 'ex-result');
  exResult.id = 'ex-result';
  exResult.hidden = true;
  const exCancel = button('ex-cancel', 'cpw-btn cpw-cancel', t('export.cancel'));
  const exGo = button('ex-go', 'cpw-btn cpw-save', t('export.go'));
  const exDownload = button('ex-download', 'desk-btn', t('export.download'));
  const exClose = button('ex-close', 'cpw-btn cpw-cancel', t('export.close'));
  const exStop = button('ex-stop', 'cpw-btn cpw-cancel', t('export.stop'));
  exDownload.hidden = true;
  exClose.hidden = true;
  exStop.hidden = true;
  let stopRequested = false;
  exStop.addEventListener('click', function () {
    // The file being made cannot be taken back (its job is already running); the next ones are not started.
    stopRequested = true;
    exStop.disabled = true;
    exStop.textContent = t('export.stopping');
  });
  const exActions = h('div', 'cpw-actions');
  [exDownload, exClose, exStop, exCancel, exGo].forEach(function (b) { exActions.appendChild(b); });
  [exTitle, exSelect, exCount, exProgress, exResult, exActions].forEach(function (e) { ex.box.appendChild(e); });
  ex.root.classList.add('ex-modal');

  const sel = {};                                 // "page|lang" -> true
  const none = {};                                // "page|lang" -> true: nothing to export there (greyed)
  const boxes = { cell: {}, row: {}, col: {}, all: null };
  // A page in a language with no draft and no edit has nothing to export: the grid already says so
  // (paintGrid: data-status "none"). "unknown" (language not read yet), "translating" and "queued" are
  // not "nothing", so those stay pickable.
  function noneCell(p, l) {
    const c = document.querySelector('.doc-cell[data-page="' + p + '"][data-lang="' + l + '"]');
    return !!c && c.getAttribute('data-status') === 'none';
  }
  function usable(p, l) { return !none[p + '|' + l]; }
  function setCell(p, l, on) { if (usable(p, l)) sel[p + '|' + l] = on; }
  function pickedCells() {
    const out = [];
    PAGES.forEach(function (p) { LANGS.forEach(function (l) { if (sel[p + '|' + l] && usable(p, l)) out.push({ page: p, lang: l }); }); });
    return out;
  }
  function syncSelection() {
    const n = pickedCells().length;
    PAGES.forEach(function (p) {
      const free = LANGS.filter(function (l) { return usable(p, l); });
      const on = free.filter(function (l) { return sel[p + '|' + l]; }).length;
      LANGS.forEach(function (l) { boxes.cell[p + '|' + l].checked = !!sel[p + '|' + l]; });
      boxes.row[p].checked = free.length > 0 && on === free.length;
      boxes.row[p].indeterminate = on > 0 && on < free.length;
      boxes.row[p].disabled = !free.length;
    });
    LANGS.forEach(function (l) {
      const free = PAGES.filter(function (p) { return usable(p, l); });
      const on = free.filter(function (p) { return sel[p + '|' + l]; }).length;
      boxes.col[l].checked = free.length > 0 && on === free.length;
      boxes.col[l].indeterminate = on > 0 && on < free.length;
      boxes.col[l].disabled = !free.length;
    });
    const total = PAGES.reduce(function (a, p) { return a + LANGS.filter(function (l) { return usable(p, l); }).length; }, 0);
    boxes.all.checked = total > 0 && n === total;
    boxes.all.indeterminate = n > 0 && n < total;
    boxes.all.disabled = !total;
    exCount.textContent = n ? tn('export.count', n) : t('export.count.none');
    exGo.disabled = n === 0;
  }
  function pickBox(label, change) {
    const i = document.createElement('input');
    i.type = 'checkbox';
    i.setAttribute('aria-label', label);
    i.addEventListener('change', function () { change(i.checked); syncSelection(); });
    return i;
  }
  function buildSelect() {
    PAGES.forEach(function (p) { LANGS.forEach(function (l) { none[p + '|' + l] = noneCell(p, l); }); });
    Object.keys(sel).forEach(function (k) { if (none[k]) delete sel[k]; });
    exSelect.textContent = '';
    const wrap = h('div', 'scroll-x');
    const table = h('table', 'ex-grid');
    table.id = 'ex-grid';
    const head = document.createElement('tr');
    head.appendChild(h('th', null, t('export.grid.page'))).setAttribute('scope', 'col');
    head.appendChild(h('th', null, t('export.all.languages'))).setAttribute('scope', 'col');
    LANGS.forEach(function (l) {
      const th = h('th', 'ex-lang');
      th.setAttribute('scope', 'col');
      th.setAttribute('data-lang', l);
      th.setAttribute('aria-label', t('lang.' + l));
      const flag = h('span', 'doc-flag', FLAG[l] || '');
      flag.setAttribute('aria-hidden', 'true');
      th.appendChild(flag);
      th.appendChild(document.createTextNode(l.toUpperCase()));
      head.appendChild(th);
    });
    table.appendChild(document.createElement('thead')).appendChild(head);
    const body = document.createElement('tbody');
    const all = document.createElement('tr');
    all.appendChild(h('th', 'ex-page', t('export.all.pages'))).setAttribute('scope', 'row');
    boxes.all = pickBox(t('export.aria.all'), function (on) {
      PAGES.forEach(function (p) { LANGS.forEach(function (l) { setCell(p, l, on); }); });
    });
    boxes.all.id = 'ex-all';
    all.appendChild(h('td', 'ex-check')).appendChild(boxes.all);
    LANGS.forEach(function (l) {
      boxes.col[l] = pickBox(t('export.aria.col', { language: t('lang.' + l) }), function (on) {
        PAGES.forEach(function (p) { setCell(p, l, on); });
      });
      boxes.col[l].setAttribute('data-col', l);
      all.appendChild(h('td', 'ex-check')).appendChild(boxes.col[l]);
    });
    body.appendChild(all);
    PAGES.forEach(function (p) {
      const tr = document.createElement('tr');
      tr.setAttribute('data-page', p);
      tr.appendChild(h('th', 'ex-page', t('page.' + p))).setAttribute('scope', 'row');
      boxes.row[p] = pickBox(t('export.aria.row', { page: t('page.' + p) }), function (on) {
        LANGS.forEach(function (l) { setCell(p, l, on); });
      });
      boxes.row[p].setAttribute('data-row', p);
      tr.appendChild(h('td', 'ex-check')).appendChild(boxes.row[p]);
      LANGS.forEach(function (l) {
        const c = pickBox(t('export.aria.cell', { page: t('page.' + p), language: t('lang.' + l) }), function (on) {
          setCell(p, l, on);
        });
        c.disabled = !usable(p, l);
        c.setAttribute('data-page', p);
        c.setAttribute('data-lang', l);
        boxes.cell[p + '|' + l] = c;
        tr.appendChild(h('td', 'ex-check')).appendChild(c);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    exSelect.appendChild(wrap);
  }
  function openEx() {
    if (busy) return;
    Object.keys(sel).forEach(function (k) { delete sel[k]; });
    if (S.page && S.lang) sel[S.page + '|' + S.lang] = true;
    buildSelect();
    syncSelection();
    exSelect.hidden = false;
    exCount.hidden = false;
    exProgress.hidden = true;
    exResult.hidden = true;
    exProgress.textContent = '';
    exResult.textContent = '';
    exCancel.hidden = false;
    exGo.hidden = false;
    exDownload.hidden = true;
    exClose.hidden = true;
    lastDownload = null;
    openOverlay(ex, exportButton, exGo.disabled ? exCancel : exGo);
  }
  function closeEx() { if (!busy) closeOverlay(ex); }
  exportButton.addEventListener('click', openEx);
  exCancel.addEventListener('click', closeEx);
  exClose.addEventListener('click', closeEx);

  // One file's row in the list, and its state.
  function fileRow(cell) {
    const li = h('li', 'ex-file');
    li.setAttribute('data-page', cell.page);
    li.setAttribute('data-lang', cell.lang);
    li.appendChild(h('span', 'ex-file-name', t('page.' + cell.page) + ' · ' + t('lang.' + cell.lang)));
    li.appendChild(h('span', 'ex-file-state'));
    exProgress.appendChild(li);
    return li;
  }
  function setState(li, state, text) {
    li.setAttribute('data-state', state);
    li.querySelector('.ex-file-state').textContent = text !== undefined ? text : t(STEP_KEY[state]);
  }
  // The language has no edit the autosave can still send (a conflict, or one the Worker refused, stays
  // in P for good: the autosave never resends it); false after a minute.
  async function flush(lang) {
    const end = Date.now() + 60000;
    for (;;) {
      if (!D.sendable(lang).length) return true;
      if (Date.now() > end) return false;
      D.saveNow();
      await sleep(Math.max(100, Math.min(500, TIMING.quiet)));
    }
  }
  function item(cell, block, extra) {
    return Object.assign({ page: cell.page, lang: cell.lang, uid: block ? block.id : '', en: block ? block.en : '' }, extra || {});
  }

  // Step 1 for one (page, language): the page's texts become decisions. Returns the work found.
  async function approve(cell, out) {
    const lang = cell.lang, page = cell.page;
    const data = await D.getPage(page);
    await D.ensureLang(lang);
    const decisions = L[lang].decisions, drafts = L[lang].drafts;
    const changes = [];
    let kept = 0, written = 0;                    // kept = already the very record; written = the server applied
    data.blocks.forEach(function (b) {
      // An edit still held back is never exported over: someone else's newer version (conflict), or a
      // change the Worker refused (unsaved).
      const held = D.pending()[lang] && D.pending()[lang][b.id];
      if (held) {
        if (held.conflict) out.conflict.push(item(cell, b));
        else out.unsaved.push(item(cell, b, { reason: t('export.reason.refused-by-server') }));
        return;
      }
      const rec = D.canon(decisions[b.id]);
      const next = exportRecord(rec, drafts[b.id] && drafts[b.id].text, b, lang, D.canon);
      if (!next) { out.empty.push(item(cell, b)); return; }
      if (D.same(rec, next)) { kept++; return; }
      changes.push({ unit: b.id, page: page, base: D.serverVer(lang, b.id), record: next });
    });
    const byId = {};
    data.blocks.forEach(function (b) { byId[b.id] = b; });
    for (let i = 0; i < changes.length; i += D.CHUNK) {
      const part = changes.slice(i, i + D.CHUNK);
      const r = await D.call({ action: 'desk-write', locale: lang, client: D.client, changes: part });
      if (!r || !r.ok || !r.body) return { error: t('export.error.write', { reason: why(r) }), data: data, byId: byId };
      const applied = {}, conflicts = {};
      (r.body.applied || []).forEach(function (a) { applied[a.unit] = a.version; });
      (r.body.conflicts || []).forEach(function (c) { conflicts[c.unit] = true; });
      const now = new Date().toISOString();
      part.forEach(function (c) {
        if (Object.prototype.hasOwnProperty.call(applied, c.unit)) {
          written++;
          decisions[c.unit] = Object.assign({}, c.record, { page: page, version: applied[c.unit], by: D.who(), at: now });
        } else if (conflicts[c.unit]) {
          out.conflict.push(item(cell, byId[c.unit]));
        } else {
          out.unsaved.push(item(cell, byId[c.unit], { reason: t('export.reason.refused-by-server') }));
        }
      });
    }
    D.gridSoon();
    return { written: written, kept: kept, data: data, byId: byId };
  }

  // The export job for one page: started (after any export of that language that is still open),
  // watched, and its file fetched. Returns {job} or {error}.
  async function runJob(cell, li) {
    const lang = cell.lang;
    let job = null;
    for (let tries = 0; tries < 6 && !job; tries++) {
      const r = await D.call({ action: 'desk-job-start', locale: lang, kind: 'export', ref: { page: cell.page } });
      if (r && r.ok && r.body && r.body.job) { job = r.body.job; break; }
      if (r && r.status === 409 && r.body && r.body.job && r.body.job.id) {
        setState(li, 'queued');
        await watch(lang, r.body.job.id);
        continue;
      }
      return { error: t('export.error.start', { reason: why(r) }) };
    }
    if (!job) return { error: t('export.error.start', { reason: why(null) }) };
    setState(li, 'queued');
    const done = await watch(lang, job.id, function (status) { setState(li, status === 'running' ? 'running' : 'queued'); });
    if (!done) return { error: t('save.reason.offline') };
    if (done.status !== 'done') return { error: jobReason(done), job: done };
    return { job: done };
  }

  async function exportOne(cell, li, files) {
    const out = { refused: [], orphan: [], conflict: [], unsaved: [], empty: [] };
    setState(li, 'saving');
    if (!(await flush(cell.lang))) { setState(li, 'failed', t('export.step.failed', { reason: t('export.error.write', { reason: why(null) }) })); return out; }
    let found;
    try { found = await approve(cell, out); } catch (_) { found = { error: t('export.error.write', { reason: why(null) }) }; }
    if (found.error) { setState(li, 'failed', t('export.step.failed', { reason: found.error })); return out; }
    if (!found.written && !found.kept) { setState(li, 'nothing'); return out; }
    const run = await runJob(cell, li);
    // A job that ended failed still says what it refused (every text refused = "export-refused"): list it.
    const result = (run.job && run.job.result) || {};
    (result.refused || []).forEach(function (r) {
      const block = found.byId[r.unit] || null;
      if (r.rule === 'EXPORT-SKIP-NO-LONGER-ON-THE-PAGE') {
        const saved = L[cell.lang].decisions[r.unit];
        out.orphan.push(item(cell, null, { uid: r.unit, en: snippet(saved && saved.text) }));
      } else {
        out.refused.push(item(cell, block, { uid: r.unit, reason: COPY['refusal.' + r.rule] ? t('refusal.' + r.rule) : '' }));
      }
    });
    if (run.error) { setState(li, 'failed', t('export.step.failed', { reason: run.error })); return out; }
    if (!result.batchId || !result.rows) { setState(li, 'nothing'); return out; }
    const got = await D.call({ action: 'desk-export-get', batch_id: result.batchId });
    if (got && got.status === 410) { setState(li, 'failed', t('export.step.failed', { reason: t('flow.file.stale') })); return out; }
    if (!got || !got.ok || !got.body || !got.body.export) {
      setState(li, 'failed', t('export.step.failed', { reason: t('export.error.download', { reason: why(got) }) }));
      return out;
    }
    files.push({ name: 'weglot-' + cell.lang + '-' + cell.page + '.csv', csv: got.body.export.csv });
    setState(li, 'done', tn('export.step.done', result.rows));
    return out;
  }

  let lastDownload = null;
  function saveBlob(name, blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }
  function stampName(when) {
    const p = function (n) { return String(n).padStart(2, '0'); };
    return when.getFullYear() + p(when.getMonth() + 1) + p(when.getDate()) + '-' + p(when.getHours()) + p(when.getMinutes());
  }
  function prepareDownload(files) {
    if (!files.length) return null;
    if (files.length === 1) {
      return { name: files[0].name, blob: new Blob([files[0].csv], { type: 'text/csv;charset=utf-8' }) };
    }
    const enc = new TextEncoder(), when = new Date();
    const bytes = zip(files.map(function (f) { return { name: f.name, data: enc.encode(f.csv) }; }), when);
    return { name: 'weglot-export-' + stampName(when) + '.zip', blob: new Blob([bytes], { type: 'application/zip' }) };
  }

  async function jump(page, lang, uid) {
    closeOverlay(ex);
    if (S.page !== page || S.lang !== lang) D.open(page, lang);
    await until(function () { return S.page === page && S.lang === lang && ready() && M.has(uid); }, 20000);
    if (M.has(uid)) D.reveal(uid);
  }
  function renderResult(all, cells, made) {
    exResult.textContent = '';
    // One line on top that says how it ended (the download starts by itself, so the end is said, not implied)
    const head = !made ? t('export.result.none')
      : stopRequested ? t('export.result.stopped', { done: made, total: cells.length })
      : t('export.result.done', { done: made, total: cells.length });
    exResult.appendChild(h('p', 'ex-headline', head));
    const many = cells.length > 1;
    GROUP_ORDER.forEach(function (kind) {
      const items = [];
      all.forEach(function (r) { r[kind].forEach(function (i) { items.push(i); }); });
      if (!items.length) return;
      const group = h('div', 'ex-group');
      group.setAttribute('data-kind', kind);
      group.appendChild(h('h3', 'ex-group-title', tn(GROUP_KEY[kind], items.length)));
      const list = h('ul', 'ex-items');
      const add = function (i) {
        const li = h('li', 'ex-item');
        li.setAttribute('data-page', i.page);
        li.setAttribute('data-lang', i.lang);
        li.setAttribute('data-uid', i.uid);
        const text = (many ? t('page.' + i.page) + ' · ' + t('lang.' + i.lang) + ': ' : '') + snippet(i.en);
        li.appendChild(h('span', 'ex-item-text', text));
        if (i.reason) li.appendChild(h('span', 'ex-item-reason', i.reason));
        if (kind !== 'orphan') {
          const go = button(null, 'desk-btn ex-jump', t('export.jump'));
          go.addEventListener('click', function () { jump(i.page, i.lang, i.uid); });
          li.appendChild(go);
        }
        list.appendChild(li);
      };
      items.slice(0, SHOWN).forEach(add);
      if (items.length > SHOWN) {
        // The rest are one click away (every text left out is listed, Outcome).
        const more = h('li', 'ex-more');
        const rest = button(null, 'desk-btn ex-show-more', t('export.more', { n: items.length - SHOWN }));
        rest.addEventListener('click', function () {
          more.remove();
          items.slice(SHOWN).forEach(add);
        });
        more.appendChild(rest);
        list.appendChild(more);
      }
      group.appendChild(list);
      exResult.appendChild(group);
    });
  }

  async function runExport() {
    const cells = pickedCells();
    if (!cells.length || busy) return;
    busy = true;
    exSelect.hidden = true;
    exCount.hidden = true;
    exCancel.hidden = true;
    exGo.hidden = true;
    exProgress.textContent = '';
    exProgress.hidden = false;
    exResult.hidden = true;
    stopRequested = false;
    exStop.disabled = false;
    exStop.textContent = t('export.stop');
    exStop.hidden = false;
    const rows = cells.map(function (c) { const li = fileRow(c); setState(li, 'waiting'); return li; });
    const files = [], all = [];
    for (let i = 0; i < cells.length; i++) {
      if (stopRequested) { setState(rows[i], 'stopped'); continue; }
      all.push(await exportOne(cells[i], rows[i], files));
    }
    exStop.hidden = true;
    const langs = {};
    cells.forEach(function (c) { langs[c.lang] = true; });
    await Promise.all(Object.keys(langs).map(function (l) { return D.refreshLang(l); }));
    D.gridSoon();
    busy = false;
    renderResult(all, cells, files.length);
    exResult.hidden = false;
    lastDownload = prepareDownload(files);
    exClose.hidden = false;
    exDownload.hidden = !lastDownload;
    if (lastDownload) saveBlob(lastDownload.name, lastDownload.blob);
    exClose.focus();
  }
  exGo.addEventListener('click', runExport);
  exDownload.addEventListener('click', function () { if (lastDownload) saveBlob(lastDownload.name, lastDownload.blob); });

  // ── Re-translate ────────────────────────────────────────────────────────────────────
  const rt = makeOverlay('rt-modal', 'rt-title');
  rt.close = function () { closeOverlay(rt); };
  const rtTitle = h('h2', 'cpw-title', t('retr.text.title'));
  rtTitle.id = 'rt-title';
  const rtBody = h('p', null, t('retr.text.body'));
  rtBody.id = 'rt-body';
  const rtLabel = h('label', 'ex-note-label', t('retr.note.label'));
  rtLabel.setAttribute('for', 'rt-note');
  const rtNote = document.createElement('textarea');
  rtNote.id = 'rt-note';
  rtNote.className = 'ex-note';
  rtNote.rows = 3;
  rtNote.maxLength = NOTE_MAX;
  // Ctrl/Cmd+Z in the note is the note's own undo, not the page's.
  rtNote.addEventListener('keydown', function (ev) { if (ev.ctrlKey || ev.metaKey) ev.stopPropagation(); });
  const rtCancel = button('rt-cancel', 'cpw-btn cpw-cancel', t('retr.cancel'));
  const rtGo = button('rt-go', 'cpw-btn cpw-save', t('retr.text.go'));
  const rtActions = h('div', 'cpw-actions');
  rtActions.appendChild(rtCancel);
  rtActions.appendChild(rtGo);
  [rtTitle, rtBody, rtLabel, rtNote, rtActions].forEach(function (e) { rt.box.appendChild(e); });

  const rp = makeOverlay('rp-modal', 'rp-title');
  rp.close = function () { closeOverlay(rp); };
  const rpTitle = h('h2', 'cpw-title', t('retr.page.title'));
  rpTitle.id = 'rp-title';
  const rpBody = h('p', null, t('retr.page.body'));
  rpBody.id = 'rp-body';
  const rpLabel = h('label', 'ex-mine');
  const rpMine = document.createElement('input');
  rpMine.type = 'checkbox';
  rpMine.id = 'rp-mine';
  rpLabel.appendChild(rpMine);
  rpLabel.appendChild(document.createTextNode(' ' + t('retr.page.mine')));
  const rpCount = h('p', null, '');
  rpCount.id = 'rp-count';
  rpCount.hidden = true;
  const rpCancel = button('rp-cancel', 'cpw-btn cpw-cancel', t('retr.cancel'));
  const rpGo = button('rp-go', 'cpw-btn cpw-save', t('retr.page.go'));
  const rpActions = h('div', 'cpw-actions');
  rpActions.appendChild(rpCancel);
  rpActions.appendChild(rpGo);
  [rpTitle, rpBody, rpLabel, rpCount, rpActions].forEach(function (e) { rp.box.appendChild(e); });
  // The page's texts the reviewer has edited, and what they say now: what "Include my edits" would hand to Gemini.
  function editedHere() {
    const out = {};
    Object.keys(L[S.lang].decisions).forEach(function (uid) {
      const r = D.curRec(S.lang, uid);
      if (r && r.text && M.has(uid)) out[uid] = r.text;
    });
    return out;
  }
  // What the engine re-asks when "Include my edits" is ticked (`keepEdited: false`): every SETTLED text of the page, an edit
  // (`text`) or an approval with no text (`tray: 'csv'`), as tools/localize/job.py `settled()` reads it.
  function settledHere() {
    let n = 0;
    Object.keys(L[S.lang].decisions).forEach(function (uid) {
      const r = D.curRec(S.lang, uid);
      if (r && (r.text || r.tray === 'csv') && M.has(uid)) n++;
    });
    return n;
  }
  function paintCount() {
    const n = settledHere();
    rpCount.hidden = !(rpMine.checked && n);
    rpCount.textContent = n ? tn('retr.page.count', n) : '';
  }
  rpMine.addEventListener('change', paintCount);

  // The job, started; its end handled by `done(job)` once the language is read again.
  async function startRetranslate(lang, kind, ref, done) {
    const r = await D.call({ action: 'desk-job-start', locale: lang, kind: kind, ref: ref });
    if (!r || !r.ok || !r.body || !r.body.job) {
      if (r && r.status === 409) D.toast(t('retr.busy'), 'warn');
      else D.toast(t('retr.failed', { reason: why(r) }), 'err');
      return;
    }
    D.toast(t('retr.started'));
    // The text says it is being re-translated (and its button is off) until the job ends, however it ends.
    if (ref.unit) { D.setRetranslating(lang, ref.unit, true); markRetranslating(); }
    let job;
    try { job = await watch(lang, r.body.job.id, null, TIMING.jobMax); }
    finally { if (ref.unit) { D.setRetranslating(lang, ref.unit, false); markRetranslating(); } }
    if (!job || job.status !== 'done') {
      const reason = job ? (job.timedOut ? t('retr.timeout') : jobReason(job)) : t('save.reason.offline');
      D.toast(t('retr.failed', { reason: reason }), 'err');
      return;
    }
    await D.refreshLang(lang);
    done();
  }
  // A new draft is SHOWN: the text's own edit is cleared, and the wording it had goes on the undo stack.
  function adopt(lang, page, uid, shown) {
    const rec = D.curRec(lang, uid);
    const next = D.withText(rec, '');
    const key = lang + '/' + page;
    const stack = D.U[key] || (D.U[key] = { undo: [], redo: [] });
    stack.undo.push({ uid: uid, from: D.withText(rec, shown), to: next });
    if (stack.undo.length > 100) stack.undo.shift();
    stack.redo = [];
    D.changeRecord(uid, next);
    D.saveStacks();
    D.paintBlock(uid, true);
    D.paintUndo();
  }
  let rtCtx = null;
  function openText(uid, opener) {
    if (!ready()) return;
    rtCtx = { uid: uid, lang: S.lang, page: S.page, shown: D.effText(S.lang, uid) };
    rtNote.value = '';
    openOverlay(rt, opener, rtNote);
  }
  rtCancel.addEventListener('click', rt.close);
  rtGo.addEventListener('click', function () {
    const ctx = rtCtx;
    if (!ctx) return;
    // The Worker refuses a note with a control character (a new line is one): they become a space.
    const note = rtNote.value.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
    const ref = { page: ctx.page, unit: ctx.uid };
    if (note) ref.note = note;
    ref.keepEdited = true;
    const block = M.get(ctx.uid);
    closeOverlay(rt);
    if (block && block.tgt) { try { block.tgt.focus(); } catch (_) {} }
    startRetranslate(ctx.lang, 'retranslate', ref, function () {
      const draft = L[ctx.lang].drafts[ctx.uid];
      if (!draft || !draft.text || draft.text === ctx.shown) { D.toast(t('retr.none-arrived'), 'warn'); return; }
      if (S.lang === ctx.lang && S.page === ctx.page && M.has(ctx.uid)) adopt(ctx.lang, ctx.page, ctx.uid, ctx.shown);
      D.toast(t('retr.done'));
      D.gridSoon();
    });
  });
  function openPage(opener) {
    if (!ready()) return;
    rpMine.checked = false;
    paintCount();
    openOverlay(rp, opener, rpGo);
  }
  D.retranslatePage = openPage;               // the desk's Translate page opens this when the page already has a translation
  rpCancel.addEventListener('click', rp.close);
  rpGo.addEventListener('click', function () {
    const lang = S.lang, page = S.page, mine = rpMine.checked;
    // The texts the reviewer has edited, and what they say now: with "include my edits" they get
    // Gemini's new wording, each one undoable.
    const before = editedHere();
    closeOverlay(rp);
    // The whole page is the engine's translate-page job (a retranslate with no text always keeps edits), started through
    // the desk's own start: it waits behind a page already being translated in this language, the banner says so, and the
    // Translate page button is off meanwhile (CEL-073). The desk calls `done` once the new drafts are read.
    D.startPageJob(lang, page, {
      keepEdited: !mine,
      done: function () {
        if (mine && S.lang === lang && S.page === page) {
          Object.keys(before).forEach(function (uid) {
            const d = L[lang].drafts[uid];
            if (d && d.text && d.text !== before[uid]) adopt(lang, page, uid, before[uid]);
          });
        }
        D.toast(t('retr.done'));
        D.gridSoon();
      }
    });
  });

  // The Worker keeps ONE open re-translate job per language, so while a text of the open language is being re-translated
  // every Re-translate button of that language is off (a second one would only be refused as busy); the other texts'
  // buttons say why in the desk's own tooltip (`data-tip`; the browser's `title` is not used on the desk, ruling #51).
  function paintRetranslate(li) {
    const b = li.querySelector('.doc-tool-retranslate');
    if (!b) return;
    const own = D.isRetranslating(S.lang, li.getAttribute('data-uid'));
    const busy = D.isRetranslatingLang(S.lang);
    b.disabled = busy;
    if (busy && !own) b.setAttribute('data-tip', t('retr.wait')); else b.removeAttribute('data-tip');
  }
  function markRetranslating() {
    document.querySelectorAll('li.doc-block').forEach(paintRetranslate);
  }
  // A "Re-translate" in each text's floating toolbar.
  function addToTool(li) {
    const tools = li.querySelector('.doc-tools');
    if (!tools || tools.querySelector('.doc-tool-retranslate')) return;
    const b = button(null, 'desk-btn doc-tool-retranslate', t('retr.button'));
    b.addEventListener('click', function () { openText(li.getAttribute('data-uid'), b); });
    tools.insertBefore(b, tools.firstChild);
    paintRetranslate(li);
  }
  const list = $('doc-blocks');
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) { if (n.nodeType === 1 && n.classList.contains('doc-block')) addToTool(n); });
    });
  }).observe(list, { childList: true });
  list.querySelectorAll('.doc-block').forEach(addToTool);
})();
