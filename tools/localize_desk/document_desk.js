/*
 * The document page of the localization desk (desk v2, CEL-026): one page read as a document,
 * English on the left, the translation on the right (Weglot's wording as an optional third
 * column), every translation editable in place.
 *
 * generate_document_page.py inlines this file, after rich_field.js, into
 * /admin/localization/document/. It reads three globals the page defines first: COPY with
 * t() / tn() (every word comes from COPY.md), callProxy() (the Worker door) and SAVE_OFF.
 * The contract between the generator, this file and the tests: runtime/out/loc2/CEL-026/contract.md.
 *
 * What it does, and how, in one paragraph: a text is saved the way the v1 desk saves one (desk-write,
 * the Worker keeps a version of every change, `base` = the version this page last saw), so
 *   - autosave is a quiet 2 s / 10 s ceiling queue in chunks of 50 under one cross-tab lock;
 *   - undo, redo and "restore" are ordinary writes: nothing here can overwrite a version this
 *     page has not seen, the Worker answers "conflict" and the reviewer chooses (keep mine / take theirs);
 *   - the server's own history is the backup, and History per text reads it (desk-history {unit}).
 * DOM is built with createElement / textContent only: texts are data, never markup.
 */
(function () {
  'use strict';

  const cfgNode = document.getElementById('doc-config');
  if (!cfgNode || !window.RichField || typeof callProxy !== 'function') return;
  const CFG = JSON.parse(cfgNode.textContent);
  const LOCALES = CFG.locales;
  const PAGES = CFG.pages;
  const DATA = CFG.data;
  const LANGS = LOCALES.map(function (l) { return l.code; });

  const DESK_CLIENT = 1;                       // the Worker's DESK_MIN_CLIENT: below it, it says reload
  const CHUNK = 50;                            // texts per desk-write (the free plan's 10 ms CPU)
  const RETRY_MS = [2000, 5000, 15000, 30000, 60000];
  const STOPS = ['reload', 'signed_out', 'cap', 'daily', 'refused'];   // saving waits for the reviewer
  // jobMax: how long a Re-translate is watched before the desk calls it failed. It stays ABOVE the Worker's own sweep of
  // an open job (JOB_STALE_MS, 35 min): giving up earlier leaves the job open on the Worker, and Try again answers busy.
  const TIMING = Object.assign({ quiet: 2000, maxWait: 10000, undoPause: 1500, timeout: 20000, poll: 15000, jobMax: 2400000 },
    window.DOC_TIMING || {});
  const SAVE_OFF_ON = typeof SAVE_OFF !== 'undefined' && SAVE_OFF === true;
  const UNDO_CAP = 100;
  const KEYS = { pending: 'cel-doc-pending', undo: 'cel-doc-undo', last: 'cel-doc-last', weglot: 'cel-doc-weglot', seen: 'cel-doc-seen' };
  const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || '');

  // The block labels, spelled out so the copy check sees every key.
  const BLOCK_KEY = {
    'meta-title': 'doc.block.meta-title', 'meta-description': 'doc.block.meta-description',
    h1: 'doc.block.h1', h2: 'doc.block.h2', h3: 'doc.block.h3', h4: 'doc.block.h4', h5: 'doc.block.h5',
    h6: 'doc.block.h6', p: 'doc.block.p', li: 'doc.block.li', button: 'doc.block.button',
    link: 'doc.block.link', other: 'doc.block.other'
  };
  const STATUS_KEY = {
    none: 'doc.status.none', drafted: 'doc.status.drafted', edited: 'doc.status.edited',
    exported: 'doc.status.exported', unknown: 'doc.status.unknown',
    translating: 'doc.status.translating', queued: 'doc.status.queued'
  };
  const FIELDS = ['tray', 'text', 'approvedAgainst', 'rejected'];   // what a decision record may carry

  const $ = function (id) { return document.getElementById(id); };
  function h(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  // ── storage (a browser that refuses it must not break the page) ───────────────────
  let storageWarned = false;
  function lsGet(key) {
    try { const s = localStorage.getItem(key); return s === null ? null : JSON.parse(s); } catch (_) { return null; }
  }
  function lsSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) {
      if (!storageWarned) { storageWarned = true; toast(t('toast.storage.title'), 'warn'); }
      return false;
    }
  }

  // ── decision records ───────────────────────────────────────────────────────────────
  // canon(): only the fields a record may carry, in one fixed order, empty ones dropped; null
  // when nothing is left (= no decision). Two records are the same when their canon text is.
  function canon(r) {
    if (!r) return null;
    const out = {};
    FIELDS.forEach(function (k) {
      const v = r[k];
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return;
      out[k] = v;
    });
    return Object.keys(out).length ? out : null;
  }
  const same = function (a, b) { return JSON.stringify(canon(a)) === JSON.stringify(canon(b)); };
  // A wording typed here IS the decision (ruling #55 A11, #63: leaving a changed field approves it with
  // your edit): `against`, when given, stamps the v1 decision (`tray:'csv'`, `approvedAgainst` = the wording
  // the website shows now) so the page export takes the text. No text means no edit: the stamp goes with it.
  function withText(r, text, against) {
    const next = Object.assign({}, r || {});
    if (text) {
      next.text = text;
      if (typeof against === 'string') { next.tray = 'csv'; next.approvedAgainst = against; }
    } else { delete next.text; delete next.tray; delete next.approvedAgainst; }
    return canon(next);
  }
  // What the website shows for this text in this language now: Weglot's wording, or the English where
  // Weglot has none yet (the page shows English there; the export reads the same line).
  function liveWording(uid) {
    const b = M.get(uid), d = b ? b.d : null;
    return d ? ((d.w && d.w[S.lang]) || d.en || '') : '';
  }
  function decide(uid, text) { return withText(curRec(S.lang, uid), text, liveWording(uid)); }
  function unstamped(rec) {
    if (!rec) return rec;
    const next = Object.assign({}, rec);
    delete next.approvedAgainst;
    return next;
  }
  // A record with a text, stamped against the wording the page shows now (a record with none, or a text this
  // page does not hold, is left as it is).
  function restamp(uid, rec) {
    if (!rec || !rec.text || typeof rec.approvedAgainst !== 'string' || !M.get(uid)) return rec;
    return withText(rec, rec.text, liveWording(uid));
  }

  // ── state ──────────────────────────────────────────────────────────────────────────
  const S = { page: null, lang: null, doc: null, loading: true, token: 0 };
  const L = {};                      // per language: {loaded, decisions, drafts, pipeline}
  LANGS.forEach(function (c) { L[c] = { loaded: false, decisions: {}, drafts: {}, pipeline: {}, findings: {} }; });
  const PI = new Map();              // page -> {count, ids}
  const PAGE_CACHE = new Map();      // page -> data
  let P = lsGet(KEYS.pending) || {}; // unsent: {lang: {uid: {record, base, page, conflict?}}}
  const C = {};                      // conflicts: {lang: {uid: {current}}}
  const U = lsGet(KEYS.undo) || {};  // undo stacks: {"lang/page": {undo: [], redo: []}}
  const M = new Map();               // uid -> block model of the open document
  const net = { timer: null, maxTimer: null, running: false, again: false, retry: 0, failure: null,
                stopped: null, inflight: new Set(), refused: new Set() };
  let group = null, groupTimer = null;
  let readError = false;
  let focusBack = null;

  function pend(lang) { return P[lang] || (P[lang] = {}); }
  function conf(lang) { return C[lang] || (C[lang] = {}); }
  const RT = new Set();     // 'lang|uid' of a text whose Re-translate is on its way (document_export.js reports it; CEL-077)
  function serverRec(lang, uid) { return canon(L[lang].decisions[uid]); }
  function serverVer(lang, uid) { const d = L[lang].decisions[uid]; return d ? d.version || 0 : 0; }
  function curRec(lang, uid) {
    const e = P[lang] && P[lang][uid];
    return e ? e.record : serverRec(lang, uid);
  }
  function effText(lang, uid) {
    const r = curRec(lang, uid);
    if (r && r.text) return r.text;
    const d = L[lang].drafts[uid];
    return d && d.text ? d.text : '';
  }
  function who() {
    const u = window.__CEL_USER__ || {};
    return u.email || '';
  }
  function persistPending() {
    const out = {};
    Object.keys(P).forEach(function (lang) {
      const ids = Object.keys(P[lang]);
      if (ids.length) out[lang] = P[lang];
    });
    lsSet(KEYS.pending, out);
  }
  function pendingTotal() {
    let n = 0;
    Object.keys(P).forEach(function (lang) {
      Object.keys(P[lang]).forEach(function (uid) {
        if (!P[lang][uid].conflict && !net.refused.has(lang + '|' + uid)) n++;
      });
    });
    return n;
  }
  function conflictTotal() {
    let n = 0;
    Object.keys(C).forEach(function (lang) { n += Object.keys(C[lang]).length; });
    return n;
  }

  // ── toasts ─────────────────────────────────────────────────────────────────────────
  function toast(message, level) {
    const stack = $('doc-toasts');
    if (!stack) return;
    const node = h('div', 'toast is-' + (level || 'ok'));
    node.appendChild(h('span', 'toast-title', message));
    stack.appendChild(node);
    setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 4000);
  }

  // ── the Worker ─────────────────────────────────────────────────────────────────────
  // Why a save stopped, as a COPY.md save.reason.* key (the same words as the v1 desk).
  function failureReason(r) {
    if (!r) return 'offline';
    if (r.status === 409) return 'reload';
    if (r.status === 401) return 'signed_out';
    if (r.status === 429) return /daily/.test((r.body && r.body.error) || '') ? 'daily' : 'cap';
    if (r.status === 503) return 'unavailable';
    if (r.status === 400 || r.status === 403) return 'refused';
    return 'trouble';
  }
  function call(payload) {
    return callProxy(payload, TIMING.timeout).catch(function () { return null; });
  }

  // ── autosave ───────────────────────────────────────────────────────────────────────
  function changed() {
    persistPending();
    updateBar();
    schedule();
    gridSoon();
  }
  function schedule() {
    if (SAVE_OFF_ON || net.stopped) return;
    clearTimeout(net.timer);
    net.timer = setTimeout(run, TIMING.quiet);
    if (!net.maxTimer) net.maxTimer = setTimeout(run, TIMING.maxWait);
  }
  function run() {
    clearTimeout(net.timer); clearTimeout(net.maxTimer);
    net.timer = null; net.maxTimer = null;
    // A cap or a daily stop sends nothing more, whoever asks: the `online` event and a write that was
    // queued behind the one that stopped used to send once again. Try again clears the stop first.
    if (SAVE_OFF_ON || net.stopped) return;
    if (net.running) { net.again = true; return; }
    net.running = true;
    const task = function () {
      return save().catch(function () {}).then(function () {
        net.running = false;
        if (net.again) { net.again = false; run(); }
      });
    };
    if (navigator.locks && navigator.locks.request) navigator.locks.request('cel-desk-save', task);
    else task();
  }
  function langOrder() {
    return [S.lang].concat(LANGS.filter(function (c) { return c !== S.lang; })).filter(Boolean);
  }
  function sendable(lang) {
    return Object.keys(pend(lang)).filter(function (uid) {
      return !pend(lang)[uid].conflict && !net.refused.has(lang + '|' + uid);
    });
  }
  async function save() {
    const order = langOrder();
    for (let i = 0; i < order.length; i++) {
      const lang = order[i];
      for (;;) {
        const ids = sendable(lang).slice(0, CHUNK);
        if (!ids.length) break;
        const sent = {};
        const changes = ids.map(function (uid) {
          const e = P[lang][uid];
          sent[uid] = JSON.stringify(e.record);
          net.inflight.add(lang + '|' + uid);
          return { unit: uid, page: e.page, base: e.base, record: e.record };
        });
        paintMany(lang, ids);
        updateBar();
        const r = await call({ action: 'desk-write', locale: lang, client: DESK_CLIENT, changes: changes });
        ids.forEach(function (uid) { net.inflight.delete(lang + '|' + uid); });
        if (!r || !r.ok) {
          failed(failureReason(r));
          paintMany(lang, ids);
          updateBar();
          return;
        }
        net.retry = 0; net.failure = null; net.stopped = null;
        written(lang, ids, sent, r.body || {});
        updateBar();
        gridSoon();
      }
    }
  }
  function failed(why) {
    net.failure = why;
    if (STOPS.indexOf(why) >= 0) { net.stopped = why; return; }
    const wait = RETRY_MS[Math.min(net.retry, RETRY_MS.length - 1)];
    net.retry++;
    clearTimeout(net.timer);
    net.timer = setTimeout(run, wait);
  }
  function written(lang, ids, sent, body) {
    const applied = {}, conflicts = {}, refused = {};
    (body.applied || []).forEach(function (a) { applied[a.unit] = a.version; });
    (body.conflicts || []).forEach(function (c) {
      // A "conflict" whose current record IS what this write sent is not someone else's change: the Worker
      // applied the write, its answer was lost (the 20 s timeout) and the text was sent again against the old
      // version. It is applied; the box with keep mine / take theirs is for a real conflict only.
      if (c.current && sent[c.unit] !== undefined && same(c.current, JSON.parse(sent[c.unit]))) applied[c.unit] = c.current.version;
      else conflicts[c.unit] = c.current || null;
    });
    (body.refused || []).forEach(function (x) { refused[x.unit] = true; });
    const now = new Date().toISOString();
    ids.forEach(function (uid) {
      const e = P[lang] && P[lang][uid];
      if (!e) return;
      if (Object.prototype.hasOwnProperty.call(applied, uid)) {
        const ver = applied[uid];
        // The server holds what was SENT, not what the box says now: typed (or undone) again while the
        // write was on its way, the entry stays and is sent next, on top of this version.
        L[lang].decisions[uid] = Object.assign({}, JSON.parse(sent[uid]) || {}, { page: e.page, version: ver, by: who(), at: now });
        if (JSON.stringify(e.record) === sent[uid]) delete P[lang][uid];
        else e.base = ver;                       // typed again while it was on its way: build on this version
        const b = M.get(uid);
        if (b && lang === S.lang) { b.savedUntil = Date.now() + 3000; setTimeout(function () { paintBlock(uid); }, 3100); }
      } else if (Object.prototype.hasOwnProperty.call(conflicts, uid)) {
        e.conflict = true;
        conf(lang)[uid] = { current: conflicts[uid], page: e.page };
      } else {
        net.refused.add(lang + '|' + uid);      // refused, or not mentioned: never resent in a loop
      }
    });
    persistPending();
    paintMany(lang, ids);
  }

  // ── the conflict the Worker reports: someone saved the same text after the version this page saw ─
  function keepMine(uid) {
    const lang = S.lang, e = pend(lang)[uid], c = conf(lang)[uid];
    if (!e || !c) return;
    e.base = c.current ? c.current.version || 0 : 0;
    delete e.conflict;
    delete conf(lang)[uid];
    changed();
    paintBlock(uid);
  }
  function takeTheirs(uid) {
    const lang = S.lang, c = conf(lang)[uid];
    if (!c) return;
    if (c.current) L[lang].decisions[uid] = c.current; else delete L[lang].decisions[uid];
    delete pend(lang)[uid];
    delete conf(lang)[uid];
    persistPending();
    changed();
    paintBlock(uid, true);
  }

  // ── making a change ────────────────────────────────────────────────────────────────
  // The one way a text changes: edit, undo, redo, restore. `next` is the whole new record.
  function changeRecord(uid, next) {
    const lang = S.lang, before = curRec(lang, uid);
    next = canon(next);
    if (same(before, next)) return false;
    const e = pend(lang)[uid];
    const base = e ? e.base : serverVer(lang, uid);
    net.refused.delete(lang + '|' + uid);
    // Back to what this page holds as the server's version is "nothing to send" -- unless a write of this
    // text is on its way: the server will have that one, so this change must follow it (re-based when
    // the write lands, see written()).
    if (e && e.conflict) { e.record = next; }
    else if (same(next, serverRec(lang, uid)) && base === serverVer(lang, uid) && !net.inflight.has(lang + '|' + uid)) delete pend(lang)[uid];
    else pend(lang)[uid] = { record: next, base: base, page: S.page };
    changed();
    return true;
  }

  // ── undo / redo (one stack pair per document: language + page) ─────────────────────
  function stack() {
    const k = S.lang + '/' + S.page;
    return U[k] || (U[k] = { undo: [], redo: [] });
  }
  function saveStacks() {
    const out = {};
    Object.keys(U).forEach(function (k) { if (U[k].undo.length || U[k].redo.length) out[k] = U[k]; });
    lsSet(KEYS.undo, out);
  }
  function closeGroup() {
    clearTimeout(groupTimer);
    if (!group) return;
    const g = group;
    group = null;
    const to = curRec(S.lang, g.uid);
    if (!same(g.from, to)) {
      const s = stack();
      s.undo.push({ uid: g.uid, from: g.from, to: to });
      if (s.undo.length > UNDO_CAP) s.undo.shift();
      s.redo = [];
      saveStacks();
    }
    paintUndo();
  }
  function onInput(uid, rf) {
    if (!group || group.uid !== uid) { closeGroup(); group = { uid: uid, from: curRec(S.lang, uid) }; }
    changeRecord(uid, decide(uid, rf.value()));
    paintBlock(uid);
    clearTimeout(groupTimer);
    groupTimer = setTimeout(closeGroup, TIMING.undoPause);
    paintUndo();
  }
  // An undo / redo step may change only the text it was made on. The stacks outlive a reload and a
  // re-read, so the text can stand at somebody else's version by now: then the step is NOT written
  // but held as a conflict (keep mine / take theirs, fix 15), exactly as when the Worker reports one.
  function holdAsConflict(uid, wanted) {
    const lang = S.lang, e = pend(lang)[uid];
    if (e) e.record = canon(wanted);
    else pend(lang)[uid] = { record: canon(wanted), base: serverVer(lang, uid), page: S.page };
    pend(lang)[uid].conflict = true;
    conf(lang)[uid] = { current: L[lang].decisions[uid] || null, page: pend(lang)[uid].page };
    net.refused.delete(lang + '|' + uid);
    changed();
  }
  function step(dir) {
    closeGroup();
    const s = stack();
    const from = dir < 0 ? s.undo : s.redo, to = dir < 0 ? s.redo : s.undo;
    const entry = from[from.length - 1];
    if (!entry) return;
    const lang = S.lang, uid = entry.uid, e = pend(lang)[uid];
    // "The state this step made": its wording, not the stamp it carries (a replayed step re-stamps the
    // record, so a neighbouring step's stored stamp may be older than what the text now holds).
    const standing = same(unstamped(curRec(lang, uid)), unstamped(dir < 0 ? entry.to : entry.from));
    from.pop();
    // Not the state this step made, and an unsent change of this page's own that the stack does not
    // know about: the step has nothing to stand on and is dropped, never written over it.
    if (!standing && e && !e.conflict) { saveStacks(); paintUndo(); toast(t('doc.undo.dropped')); return; }
    to.push(entry);
    // Replayed, the record is a fresh decision on what the page shows now: a text in it is stamped against
    // today's wording like an edit is, not the Weglot wording of the day it was made (a moved wording would
    // make the export refuse it as TRANSLATION-MOVED and show it as Edited, never Exported).
    const wanted = restamp(uid, dir < 0 ? entry.from : entry.to);
    if (standing) changeRecord(uid, wanted); else holdAsConflict(uid, wanted);
    saveStacks();
    paintBlock(uid, true);
    reveal(uid);
    paintUndo();
  }
  const undo = function () { step(-1); };
  const redo = function () { step(1); };
  function reveal(uid) {
    const b = M.get(uid);
    if (!b) return;
    try { b.li.scrollIntoView({ block: 'nearest' }); } catch (_) {}
    b.li.setAttribute('data-flash', '1');
    setTimeout(function () { b.li.removeAttribute('data-flash'); }, 1000);
  }
  function keysFor(kind) {
    const k = kind === 'undo'
      ? (IS_MAC ? 'doc.keys.undo.mac' : 'doc.keys.undo.other')
      : (IS_MAC ? 'doc.keys.redo.mac' : 'doc.keys.redo.other');
    return t(k);
  }
  function paintUndo() {
    const s = stack();
    const u = $('doc-undo'), r = $('doc-redo');
    const canU = s.undo.length > 0 || !!group, canR = s.redo.length > 0;
    u.disabled = !canU; r.disabled = !canR;
    const ut = canU ? t('doc.undo.tip', { keys: keysFor('undo') }) : t('doc.undo.none');
    const rt = canR ? t('doc.redo.tip', { keys: keysFor('redo') }) : t('doc.redo.none');
    u.setAttribute('data-tip', ut); u.setAttribute('aria-label', ut);
    r.setAttribute('data-tip', rt); r.setAttribute('aria-label', rt);
    const uk = u.querySelector('.doc-kbd'), rk = r.querySelector('.doc-kbd');
    if (uk) uk.textContent = keysFor('undo');
    if (rk) rk.textContent = keysFor('redo');
  }

  // ── the text cells ─────────────────────────────────────────────────────────────────
  function blockLabel(d) {
    if (d.b === 'meta-title' && d.r === 'og_title') return t('doc.block.og-title');
    return t(BLOCK_KEY[d.b] || BLOCK_KEY.other);
  }
  function lockReason(d) {
    if (d.lock === 'summary') return t('refusal.SUMMARY-OWNED');
    if (d.lock === 'link') return t('refusal.LINK-ONLY-UNPROVEN');
    // Only a text of numbers and symbols is "left as it is"; a lock this desk does not know says nothing
    // rather than the wrong reason.
    return d.lock === 'noise' ? t('doc.locked.noise') : '';
  }
  function caretEnd(el) {
    const r = document.createRange();
    r.selectNodeContents(el);
    r.collapse(false);
    const s = window.getSelection();
    s.removeAllRanges();
    s.addRange(r);
  }
  function attachField(b, text) {
    const el = b.tgt;
    b.rf = window.RichField.attach(el, {
      text: text,
      onCommit: function () { el.blur(); }
    });
    return b.rf;
  }
  // ── a text that is also on other pages (CEL-072) ────────────────────────────────────────────────────
  // One translation serves every page that carries the same English, so a wording saved here is the wording there. The
  // reviewer is told, but not in a line of the page: ONE small marker (the number of other pages) sits in the translation's
  // gutter; hover or keyboard focus shows the sentence (the desk's tooltip), a click opens a popover that lists the pages
  // by path, and the sentence shows once, in the note row under the text, while the text has focus. The marker and the
  // popover take no room in the grid; the note row is empty (0 high) until then, exactly as for a text that is not shared.
  function sharedSentence(d) {
    const parts = [];
    if (d.also && d.also.length) {
      parts.push(t('doc.also', { pages: d.also.map(function (p) { return t('page.' + p); }).join(', ') }));
    }
    if (d.out) {
      const eg = d.outEg === '/' ? t('row.shared.home') : (d.outEg || '');
      parts.push(tn('doc.shared', d.out, { example: eg }));
    }
    return parts.join(' ');
  }
  function sharedPaths(d) {
    const out = [];
    (d.also || []).forEach(function (k) { const pi = PI.get(k); if (pi && pi.path) out.push(pi.path); });
    (d.outAll || (d.outEg ? [d.outEg] : [])).forEach(function (p) { out.push(p); });
    return out;
  }
  let sharedOpen = null;                  // {pop, mark}: the one popover that is open
  function closeShared(refocus) {
    if (!sharedOpen) return;
    const o = sharedOpen;
    sharedOpen = null;
    o.pop.remove();
    o.mark.setAttribute('aria-expanded', 'false');
    if (refocus && o.mark.focus) o.mark.focus();
  }
  // A click anywhere else closes it. Escape closes it first and alone: the capturing listener stops the key before the page's
  // own Escape (which closes the confirm window, then the history panel), so one press never closes two things.
  document.addEventListener('click', function (ev) { if (sharedOpen && !sharedOpen.pop.contains(ev.target)) closeShared(false); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && sharedOpen) { ev.stopImmediatePropagation(); ev.preventDefault(); closeShared(true); }
  }, true);
  function openShared(b) {
    closeShared(false);
    const sentence = sharedSentence(b.d);
    const pop = h('div', 'doc-shared-pop');
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-modal', 'false');
    pop.setAttribute('aria-label', sentence);
    pop.setAttribute('tabindex', '-1');
    pop.appendChild(h('p', 'doc-shared-pop-text', sentence));
    const list = h('ul', 'doc-shared-pop-list');
    sharedPaths(b.d).forEach(function (p) { list.appendChild(h('li', null, p === '/' ? t('row.shared.home') : p)); });
    pop.appendChild(list);
    // Focus leaving the marker and its popover (Tab on, a click elsewhere) closes it; a click inside it does not.
    pop.addEventListener('focusout', function (ev) {
      if (!ev.relatedTarget || !b.sharedBox.contains(ev.relatedTarget)) closeShared(false);
    });
    b.sharedBox.appendChild(pop);
    // Under the marker unless that runs into the bottom edge (the status bar) and there is room above it.
    const bar = $('doc-status');
    const floor = bar && !bar.hidden ? bar.getBoundingClientRect().top : window.innerHeight;
    if (pop.getBoundingClientRect().bottom > floor - 4 && b.mark.getBoundingClientRect().top - pop.offsetHeight - 10 >= 4) {
      pop.classList.add('doc-shared-pop-up');
    }
    b.mark.setAttribute('aria-expanded', 'true');
    sharedOpen = { pop: pop, mark: b.mark };
    pop.focus();
  }
  function buildSharedNote(b, note) {
    const d = b.d;
    const n = (d.also ? d.also.length : 0) + (d.out || 0);
    if (!n) return;
    const sentence = sharedSentence(d);
    const box = h('span', 'doc-shared');
    const mark = h('button', 'doc-shared-mark', String(n));
    mark.type = 'button';
    mark.setAttribute('aria-label', tn('doc.mark', n) + ' ' + sentence);   // the name holds the count the chip shows (WCAG 2.5.3)
    mark.setAttribute('data-tip', sentence);
    mark.setAttribute('aria-haspopup', 'dialog');
    mark.setAttribute('aria-expanded', 'false');
    mark.addEventListener('click', function (ev) {
      ev.stopPropagation();               // the page's outside-click handler must not close what this click opens
      if (sharedOpen && sharedOpen.mark === mark) closeShared(true); else openShared(b);
    });
    box.appendChild(mark);
    b.li.appendChild(box);
    b.sharedBox = box;
    b.mark = mark;
    const warn = h('span', 'doc-shared-warn', sentence);        // first line of the note row, shown while the text has focus
    warn.hidden = true;
    note.insertBefore(warn, note.firstChild);
    b.warn = warn;
  }

  function buildBlock(d) {
    const lang = S.lang;
    const li = h('li', 'doc-block');
    li.setAttribute('data-uid', d.id);
    li.setAttribute('data-b', d.b);
    li.setAttribute('data-state', 'idle');
    li.setAttribute('data-lock', d.lock || '');
    li.setAttribute('data-source', 'none');
    const b = { d: d, li: li, savedUntil: 0 };
    li.appendChild(h('span', 'doc-tag', blockLabel(d)));
    const en = h('div', 'doc-en');
    en.setAttribute('lang', 'en');
    window.RichField.render(en, d.en);
    li.appendChild(en);
    b.en = en;
    const tgt = h('div', 'doc-tgt');
    tgt.setAttribute('lang', lang);
    tgt.setAttribute('role', 'textbox');
    tgt.setAttribute('aria-label', blockLabel(d));
    if (d.lock) tgt.setAttribute('aria-readonly', 'true');
    b.tgt = tgt;
    li.appendChild(tgt);
    const wg = h('div', 'doc-weglot');
    wg.setAttribute('lang', lang);
    wg.setAttribute('dir', 'auto');
    window.RichField.render(wg, (d.w && d.w[lang]) || '');
    if (!(d.w && d.w[lang])) wg.setAttribute('data-placeholder', t('doc.weglot.none'));
    wg.hidden = $('doc-blocks').getAttribute('data-weglot') !== 'on';
    li.appendChild(wg);
    b.wg = wg;
    const note = h('p', 'doc-note');
    b.state = h('span', 'doc-note-state');
    b.lockNote = h('span', 'doc-note-lock');
    b.same = h('span', 'doc-note-same');
    note.appendChild(b.state); note.appendChild(b.lockNote);
    note.appendChild(b.same);
    li.appendChild(note);
    buildSharedNote(b, note);    // a text that is also on other pages: one small marker, not a line of the page (CEL-072)
    const box = h('div', 'doc-conflict');
    box.hidden = true;
    b.conflictText = h('span');
    const mine = h('button', 'desk-btn doc-keep-mine', t('doc.conflict.mine'));
    mine.type = 'button';
    const theirs = h('button', 'desk-btn doc-take-theirs', t('doc.conflict.theirs'));
    theirs.type = 'button';
    box.appendChild(b.conflictText); box.appendChild(mine); box.appendChild(theirs);
    li.appendChild(box);
    b.box = box;
    mine.addEventListener('click', function () { keepMine(d.id); });
    theirs.addEventListener('click', function () { takeTheirs(d.id); });

    if (d.lock) {
      const why = lockReason(d);
      b.lockNote.textContent = t('doc.locked.tag') + (why ? ' — ' + why : '');
      tgt.setAttribute('dir', 'auto');
      window.RichField.render(tgt, (d.w && d.w[lang]) || '');
    } else {
      tgt.setAttribute('data-placeholder', t('doc.empty.cell'));
      attachField(b, effText(lang, d.id));
      tgt.addEventListener('input', function () { onInput(d.id, b.rf); });
      // Edit > Undo, a phone's shake and the like reach the field as beforeinput: they go to the
      // page's one undo stack too, never to the browser's own history of this field.
      tgt.addEventListener('beforeinput', function (ev) {
        if (ev.inputType === 'historyUndo') { ev.preventDefault(); undo(); }
        else if (ev.inputType === 'historyRedo') { ev.preventDefault(); redo(); }
      });
      tgt.addEventListener('focus', function () {
        li.setAttribute('data-open', '1');
        if (b.warn) b.warn.hidden = false;      // the sentence shows once, in the note row, when editing starts
      });
      tgt.addEventListener('blur', function () {
        li.removeAttribute('data-open');
        if (b.warn) b.warn.hidden = true;
        closeGroup();
        paintBlock(d.id);
      });
      // Esc leaves the text (the typing is already kept); the field's own Esc would put back
      // what the text was when the page opened.
      tgt.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') { ev.stopImmediatePropagation(); ev.preventDefault(); tgt.blur(); }
      }, true);
      en.addEventListener('click', function () {
        const sel = window.getSelection && window.getSelection().toString();
        if (!sel) tgt.focus();
      });
      // The actions for this text float above it while focus is inside the block (CSS :focus-within).
      const tools = h('div', 'doc-tools');
      tools.setAttribute('role', 'toolbar');
      tools.setAttribute('aria-label', t('doc.tools.label'));
      const hb = h('button', 'desk-btn doc-history-btn', t('doc.history'));
      const wb = h('button', 'desk-btn doc-tool-weglot', t('doc.tool.weglot'));
      const rb = h('button', 'desk-btn doc-tool-revert', t('doc.tool.revert'));
      [hb, wb, rb].forEach(function (x) { x.type = 'button'; });
      tools.appendChild(hb);
      // Weglot has no wording for this text: no "Use Weglot's text" button (it would erase the edit).
      if (d.w && d.w[lang]) tools.appendChild(wb);
      tools.appendChild(rb);
      hb.addEventListener('click', function () { openHistory(d.id, hb); });
      wb.addEventListener('click', function () { commitText(d.id, (d.w && d.w[lang]) || ''); });
      rb.addEventListener('click', function () { commitText(d.id, ''); });
      li.appendChild(tools);
      b.hist = hb;
    }
    if (d.b === 'meta-title' || d.b === 'meta-description') {
      b.chars = h('span', 'doc-note-chars');
      note.appendChild(b.chars);
    }
    M.set(d.id, b);
    return b;
  }

  // Why a text is not saved, in the words of its cause (CEL-077 item 12): refused by the server, saving stopped,
  // offline, or just trying again.
  function errorLabel(lang, uid) {
    if (net.refused.has(lang + '|' + uid)) return t('doc.text.refused');
    if (net.stopped) return t('doc.text.stopped');
    if (navigator.onLine === false) return t('doc.text.offline');
    return t('doc.text.error');
  }
  function stateOf(lang, uid, b) {
    if (conf(lang)[uid]) return 'conflict';
    const key = lang + '|' + uid;
    if (net.inflight.has(key)) return 'saving';
    if (net.refused.has(key)) return 'error';
    if (P[lang] && P[lang][uid]) return net.failure ? 'error' : 'dirty';
    if (b && b.savedUntil > Date.now()) return 'saved';
    return 'idle';
  }
  function paintBlock(uid, rerender) {
    const b = M.get(uid);
    if (!b) return;
    const lang = S.lang;
    const d = b.d;
    const rec = curRec(lang, uid);
    const draft = L[lang].drafts[uid];
    b.li.setAttribute('data-source', rec && rec.text ? 'edit' : (draft && draft.text ? 'draft' : 'none'));
    if (!d.lock) {
      const text = effText(lang, uid);
      const focused = document.activeElement === b.tgt;
      if (rerender || (!focused && b.rf.value() !== text)) {
        attachField(b, text);
        if (focused) { b.tgt.focus(); caretEnd(b.tgt); }       // an undo from inside the text keeps the caret there
      }
    }
    const st = stateOf(lang, uid, b);
    b.li.setAttribute('data-state', st);
    let label = '';
    if (!d.lock) {
      if (st === 'dirty' && navigator.onLine === false) label = t('doc.text.offline');
      else if (st === 'saving' || st === 'dirty') label = t('doc.text.saving');
      else if (st === 'saved') label = t('doc.text.saved');
      else if (st === 'error') label = errorLabel(lang, uid);
      else if (rec && rec.text) label = t('doc.text.edited');
    }
    // A Re-translate on its way is said on the text itself, whatever else is true of it (CEL-077 item 5)
    if (RT.has(lang + '|' + uid)) { label = t('doc.text.retranslating'); b.li.setAttribute('data-retranslating', ''); }
    else b.li.removeAttribute('data-retranslating');
    b.state.textContent = label;
    // One small mark when the text is word for word what Weglot has (the reviewer can skip it). Shown only
    // while the Weglot column is on (CSS); nothing is highlighted otherwise.
    const wgText = (d.w && d.w[lang]) || '';
    b.same.textContent = !d.lock && wgText && effText(lang, uid) === wgText ? t('doc.weglot.same') : '';
    if (b.chars) {
      const shown = d.lock ? ((d.w && d.w[lang]) || '') : effText(lang, uid);
      b.chars.textContent = shown ? tn('doc.chars', plain(shown).length) : '';
    }
    const c = conf(lang)[uid];
    b.box.hidden = !c;
    if (c) {
      const cur = c.current;
      b.conflictText.textContent = cur && cur.text
        ? t('doc.conflict.text', { who: cur.by || t('doc.conflict.someone'), text: cur.text })
        : t('doc.conflict.gone');
    }
  }
  function paintMany(lang, ids) {
    if (lang !== S.lang) return;
    ids.forEach(function (uid) { paintBlock(uid); });
  }

  // ── the save bar ───────────────────────────────────────────────────────────────────
  function updateBar() {
    const bar = $('doc-save');
    if (!bar) return;
    const n = pendingTotal();
    const conflicts = conflictTotal();
    let state = 'saved', text = '';
    if (S.loading) { state = 'loading'; text = t('doc.loading'); }
    else if (conflicts) { state = 'conflict'; text = tn('autosave.conflict', conflicts); }
    else if (net.stopped) { state = 'stopped'; text = t('autosave.stopped', { reason: t('save.reason.' + net.failure) }); }
    else if (net.failure && n) {
      state = navigator.onLine === false ? 'offline' : 'retrying';
      text = state === 'offline' ? tn('autosave.offline', n) : tn('autosave.retrying', n, { reason: t('save.reason.' + net.failure) });
    }
    else if (n && (SAVE_OFF_ON || navigator.onLine === false)) { state = 'offline'; text = tn('autosave.offline', n); }
    else if (n) { state = 'saving'; text = tn('autosave.saving', n); }
    else if (net.refused.size) { state = 'refused'; text = tn('autosave.refused', net.refused.size); }
    else text = t('autosave.saved');
    bar.setAttribute('data-state', state);
    bar.textContent = '';
    bar.appendChild(document.createTextNode(text));
    if (state === 'stopped' || state === 'retrying') {
      const retry = h('button', 'desk-btn', t('autosave.retry'));
      retry.type = 'button';
      retry.id = 'doc-save-retry';
      retry.addEventListener('click', function () { net.stopped = null; net.retry = 0; run(); updateBar(); });
      bar.appendChild(retry);
    }
    barMore(state);
  }
  // Where the trouble is, beside the bar (its own element: the bar's own text stays the count). A conflict names
  // the language and the page and goes there; an unsaved or refused text on the open page can be gone to.
  function conflictList() {
    const out = [];
    Object.keys(C).forEach(function (lang) {
      Object.keys(C[lang]).forEach(function (uid) {
        const e = P[lang] && P[lang][uid];
        out.push({ lang: lang, uid: uid, page: (C[lang][uid] && C[lang][uid].page) || (e && e.page) || S.page });
      });
    });
    const here = function (c) { return c.lang === S.lang && c.page === S.page ? 1 : 0; };
    out.sort(function (a, b) { return here(b) - here(a); });       // the open page and language first
    return out;
  }
  let conflictAt = 0;
  function goConflict() {
    const list = conflictList();
    if (!list.length) return;
    const c = list[conflictAt++ % list.length];
    if (c.lang === S.lang && c.page === S.page) jumpTo(c.uid);
    else open(c.page, c.lang).then(function () { jumpTo(c.uid); });
  }
  function unsavedTarget() {
    if (!S.doc) return null;
    const mine = P[S.lang] || {};
    const hit = S.doc.blocks.filter(function (d) { return mine[d.id] || net.refused.has(S.lang + '|' + d.id); })[0];
    return hit ? hit.id : null;
  }
  function barMore(state) {
    const bar = $('doc-save');
    let more = $('doc-save-more');
    if (!more) { more = h('span', 'doc-save-more'); more.id = 'doc-save-more'; bar.parentNode.insertBefore(more, bar.nextSibling); }
    more.textContent = '';
    if (state === 'conflict') {
      const first = conflictList()[0];
      if (first) {
        more.appendChild(document.createTextNode(t('autosave.conflict.where', { language: t('lang.' + first.lang), page: t('page.' + first.page) })));
        const go = h('button', 'desk-btn', t('autosave.conflict.go'));
        go.type = 'button';
        go.id = 'doc-conflict-go';
        go.addEventListener('click', goConflict);
        more.appendChild(go);
      }
    } else if (state === 'stopped' || state === 'retrying' || state === 'offline' || state === 'refused') {
      const uid = unsavedTarget();
      if (uid) {
        const go = h('button', 'desk-btn', t('doc.save.go'));
        go.type = 'button';
        go.id = 'doc-save-go';
        go.addEventListener('click', function () { jumpTo(uid); });
        more.appendChild(go);
      }
    }
  }

  // ── the grid: pages x languages ────────────────────────────────────────────────────
  // A text counts as exported only for the wording it was exported for: the Worker counts the stamp
  // at or after the decision (cloudflare-worker.js deskShape), so a change made since -- saved or
  // not yet sent -- puts it back to "edited".
  function exportedNow(lang, uid) {
    const p = L[lang].pipeline[uid];
    if (!p || !p.exportedAt) return false;
    if (P[lang] && P[lang][uid]) return false;
    const d = L[lang].decisions[uid];
    if (d && d.at) {
      const decided = Date.parse(d.at), exported = Date.parse(p.exportedAt);
      if (!isNaN(decided) && !isNaN(exported) && exported < decided) return false;
    }
    return true;
  }
  function statusOf(page, lang) {
    const info = PI.get(page), l = L[lang];
    if (!info || !l.loaded) return null;
    let nText = 0, nEdit = 0, nExp = 0;
    info.ids.forEach(function (uid) {
      const r = curRec(lang, uid), d = l.drafts[uid];
      const edited = !!(r && r.text);
      if (!edited && !(d && d.text)) return;
      nText++;
      if (edited) nEdit++;
      if (exportedNow(lang, uid)) nExp++;
    });
    const status = !nText ? 'none' : (nExp === nText ? 'exported' : (nEdit ? 'edited' : 'drafted'));
    return { status: status, n: nText, total: info.ids.length };
  }
  function paintGrid() {
    PAGES.forEach(function (page) {
      LANGS.forEach(function (lang) {
        const cell = document.querySelector('.doc-cell[data-page="' + page + '"][data-lang="' + lang + '"]');
        if (!cell) return;
        const s = statusOf(page, lang);
        let status = s ? s.status : 'unknown';
        // The language's open translate-page job (one per language) shows on its page's cell; a page
        // waiting behind it shows as queued.
        const js = jstate(lang);
        if (js.job && js.page === page) status = 'translating';
        else if (js.waiting.indexOf(page) >= 0) status = 'queued';
        cell.setAttribute('data-status', status);
        cell.setAttribute('aria-pressed', page === S.page && lang === S.lang ? 'true' : 'false');
        cell.querySelector('.doc-cell-status').textContent = t(STATUS_KEY[status]);
        cell.querySelector('.doc-cell-count').textContent =
          s && s.status !== 'none' ? tn('doc.cell.count', s.n, { total: s.total }) : '';
        cell.setAttribute('aria-label', t('doc.cell.aria', {
          page: t('page.' + page), language: t('lang.' + lang), status: t(STATUS_KEY[status])
        }));
      });
    });
    paintBanner();
  }
  let gridQueued = false;
  function gridSoon() {
    if (gridQueued) return;
    gridQueued = true;
    setTimeout(function () { gridQueued = false; paintGrid(); paintOutline(); paintWords(); updateNext(); }, 0);
  }

  // ── the banner: not translated yet / a translation under way ───────────────────────
  function paintBanner() {
    const box = $('doc-banner'), text = $('doc-banner-text'), go = $('doc-banner-translate');
    if (!box) return;
    let msg = '', button = false;
    if (S.loading) { box.hidden = true; return; }
    const js = jstate(S.lang);
    if (readError) { msg = t('doc.read.failed'); }
    else if (js.waiting.indexOf(S.page) >= 0) {
      msg = t('doc.job.waiting', { page: t('page.' + js.page), language: t('lang.' + S.lang) });
    }
    else if (runningHere()) { msg = t('doc.job.queued'); }
    else if (js.failed && js.failed.page === S.page) { msg = js.failed.message; }
    else {
      const s = statusOf(S.page, S.lang);
      if (s && s.status === 'none') { msg = t('doc.banner.none', { language: t('lang.' + S.lang) }); button = true; }
    }
    box.hidden = !msg;
    text.textContent = msg;
    go.hidden = !button;
    $('doc-translate').disabled = readError || runningHere() || js.waiting.indexOf(S.page) >= 0;
    $('doc-translate').hidden = button;       // one Translate page at a time: the banner's while the page is untranslated
  }

  // ── translate page ─────────────────────────────────────────────────────────────────
  // The Worker allows one open translate-page job per language. Asking for more pages while one runs
  // QUEUES them here, every one, in the order asked: each starts by itself when the one before it ends
  // (plan v2 fix 8). The queue lives in this window only, and the banner says so.
  const J = {};                       // per language: {job, page, waiting: [pages], failed, timer, opts: {page: {keepEdited, done, jobId}}}
  function jstate(lang) { return J[lang] || (J[lang] = { job: null, page: null, waiting: [], failed: null, timer: null, opts: {} }); }
  function runningHere() { const js = jstate(S.lang); return !!(js.job && js.page === S.page); }
  // ONE Translate page button (CEL-073): a page with no translation asks the confirm below and starts the job; a page that
  // already has one opens the whole-page window document_export.js owns (edited texts kept unless the reviewer ticks
  // "Include my edits"). Without that module, or while the language is unread, it asks the confirm: the page still translates.
  function hasTranslation() { const s = statusOf(S.page, S.lang); return !!s && s.status !== 'none'; }
  function translatePage(opener) {
    if (readError || runningHere() || jstate(S.lang).waiting.indexOf(S.page) >= 0) return;
    if (hasTranslation() && window.DocDesk && typeof window.DocDesk.retranslatePage === 'function') window.DocDesk.retranslatePage(opener);
    else openConfirm(opener);
  }
  let confirmReturn = null;
  function openConfirm(opener) {
    if (readError || runningHere() || jstate(S.lang).waiting.indexOf(S.page) >= 0) return;
    const n = (PI.get(S.page) || { ids: [] }).ids.length;
    $('doc-confirm-title').textContent = t('doc.confirm.title');
    $('doc-confirm-body').textContent = tn('doc.confirm.body', n, { language: t('lang.' + S.lang) });
    confirmReturn = opener || $('doc-translate');
    $('doc-confirm').hidden = false;
    $('doc-confirm-ok').focus();
  }
  function closeConfirm() {
    $('doc-confirm').hidden = true;
    if (confirmReturn && confirmReturn.focus) confirmReturn.focus();
    confirmReturn = null;
  }
  function jobWatch(lang, j) {
    const js = jstate(lang);
    js.job = j;
    js.page = j.ref && j.ref.page ? j.ref.page : S.page;
    js.failed = null;
    paintBanner();
    gridSoon();
    clearTimeout(js.timer);
    js.timer = setTimeout(function poll() {
      call({ action: 'desk-job-get', locale: lang, id: j.id }).then(function (r) {
        const cur = r && r.ok && r.body && r.body.job;
        if (!cur || cur.status === 'queued' || cur.status === 'running') { js.timer = setTimeout(poll, TIMING.poll); return; }
        const page = js.page;
        js.job = null;
        // The whole-page window's choices go with the job that window started (its id), never with another job that
        // happens to run for the same page: those wait for their own job.
        const own = js.opts[page] && js.opts[page].jobId === j.id ? js.opts[page] : null;
        if (own) delete js.opts[page];
        if (cur.status === 'done') {
          if (own && own.done) Promise.resolve(refreshLang(lang)).then(own.done);
          else { toast(t('doc.job.done')); refreshLang(lang); }
        } else {
          const code = cur.error || '';
          const reason = COPY['job.failed.' + code] ? t('job.failed.' + code) : t('doc.job.failed.unknown');
          js.failed = { page: page, message: t('doc.job.failed', { reason: reason }) };
        }
        drain(lang);
      });
    }, TIMING.poll);
  }
  function enqueue(js, page, front) {
    if (js.waiting.indexOf(page) >= 0) return;
    if (front) js.waiting.unshift(page); else js.waiting.push(page);
  }
  function dequeue(js, page) {
    js.waiting = js.waiting.filter(function (p) { return p !== page; });
  }
  // The job in this language is over (or a start failed): the page first in line starts.
  function drain(lang) {
    const next = jstate(lang).waiting.shift();
    if (next) startJob(lang, next, true); else { paintBanner(); gridSoon(); }
  }
  // `opts` ({keepEdited, done}) comes from the whole-page window (CEL-073) and waits with its page while it is queued.
  function startJob(lang, page, fromQueue, opts) {
    closeConfirm();
    const js = jstate(lang);
    js.failed = null;
    if (opts) js.opts[page] = opts;
    const keep = (js.opts[page] || {}).keepEdited !== false;
    call({ action: 'desk-job-start', locale: lang, kind: 'translate-page', ref: { page: page, keepEdited: keep } })
      .then(function (r) {
        if (r && r.ok && r.body && r.body.job) {
          dequeue(js, page);
          if (js.opts[page]) js.opts[page].jobId = r.body.job.id;     // the window's choices belong to this job
          jobWatch(lang, Object.assign({}, r.body.job, { ref: { page: page } }));
          return;
        }
        if (r && r.status === 409) {
          const running = (r.body && r.body.job) || null;
          const on = running && running.ref && running.ref.page ? running.ref.page : page;
          if (running && running.id) {
            // Another page runs first: ours follows it, behind the pages already waiting (a page that
            // was first in line goes back to the front).
            const mine = js.opts[page];
            if (on !== page) enqueue(js, page, fromQueue);
            else if (mine && mine.keepEdited === false && !(running.ref && running.ref.keepEdited === false)) {
              // This page is being translated already, keeping the edits, and the window asked to include them: the
              // window's own job follows the running one, with its own choices (CEL-073 round 3).
              enqueue(js, page, true);
            } else {
              // The running job already does what was asked: it is watched, and the window's choices go with nothing.
              dequeue(js, page);
              delete js.opts[page];
            }
            jobWatch(lang, running);
            return;
          }
        }
        dequeue(js, page);
        delete js.opts[page];
        toast(t('doc.job.error'), 'err');
        // A page that could not start does not hold the ones behind it.
        if (js.waiting.length && !js.job) drain(lang); else { paintBanner(); gridSoon(); }
      });
  }
  function checkJob(lang) {
    call({ action: 'desk-job-get', locale: lang }).then(function (r) {
      const js = jstate(lang);
      if (!r || !r.ok || js.job) return;
      const latest = r.body && r.body.jobs && r.body.jobs['translate-page'];
      if (!latest || (latest.status !== 'queued' && latest.status !== 'running')) return;
      jobWatch(lang, latest);
    });
  }

  // ── history of one text ────────────────────────────────────────────────────────────
  let histUid = null;
  function closeHistory() {
    const aside = $('doc-history');
    if (!aside || aside.hidden) return;
    aside.hidden = true;
    histUid = null;
    if (focusBack && focusBack.focus) focusBack.focus();
    focusBack = null;
  }
  // "Oct 19, 23:02": the reader's own time zone, the month spelled (a US "10/19" reads as another day to
  // most of the team), the 24-hour clock. A date from an earlier year carries its year.
  function stamp(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const o = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
    if (d.getFullYear() !== new Date().getFullYear()) o.year = 'numeric';
    return new Intl.DateTimeFormat('en-US', o).format(d);
  }
  function versionRow(uid, text, meta, onRestore, version) {
    const li = h('li', 'doc-version');
    if (version !== undefined) li.setAttribute('data-version', String(version));
    li.appendChild(h('span', 'doc-version-meta', meta));
    const body = h('div', 'doc-version-text');
    body.setAttribute('dir', 'auto');
    body.setAttribute('lang', S.lang);
    window.RichField.render(body, text);
    li.appendChild(body);
    const btn = h('button', 'desk-btn doc-restore', t('doc.history.restore'));
    btn.type = 'button';
    btn.addEventListener('click', onRestore);
    li.appendChild(btn);
    return li;
  }
  function openHistory(uid, opener) {
    const lang = S.lang;
    histUid = uid;
    focusBack = opener || null;
    const aside = $('doc-history'), list = $('doc-history-list');
    list.textContent = '';
    aside.hidden = false;
    $('doc-history-close').focus();
    if (SAVE_OFF_ON) { list.appendChild(h('li', 'doc-version-empty', t('doc.history.empty'))); return; }
    call({ action: 'desk-history', locale: lang, unit: uid }).then(function (r) {
      if (histUid !== uid || lang !== S.lang) return;
      list.textContent = '';
      if (!r || !r.ok || !r.body) { list.appendChild(h('li', 'doc-version-empty', t('doc.history.failed'))); return; }
      // A strip of cards, oldest on the left, the newest on the right: Gemini's draft first.
      const draft = L[lang].drafts[uid];
      if (draft && draft.text) {
        list.appendChild(versionRow(uid, draft.text, t('doc.history.draft') + (draft.arrivedAt ? ' · ' + stamp(draft.arrivedAt) : ''),
          function () { restore(uid, ''); }));
      }
      (r.body.history || []).filter(function (x) { return x.text; }).reverse().forEach(function (x) {
        const meta = (x.byName || x.by || t('doc.history.you')) + ' · ' + stamp(x.at);
        list.appendChild(versionRow(uid, x.text, meta, function () { restore(uid, x.text); }, x.version));
      });
      if (!list.firstChild) list.appendChild(h('li', 'doc-version-empty', t('doc.history.empty')));
      list.scrollLeft = list.scrollWidth;
    });
  }
  // One change that is its own undo step: a restore, "Use Weglot's text", "Undo this". All are
  // ordinary writes of the wording (a version of their own), so Undo takes any of them back.
  function commitText(uid, text) {
    closeGroup();
    const from = curRec(S.lang, uid);
    if (changeRecord(uid, decide(uid, text))) {
      const s = stack();
      s.undo.push({ uid: uid, from: from, to: curRec(S.lang, uid) });
      if (s.undo.length > UNDO_CAP) s.undo.shift();
      s.redo = [];
      saveStacks();
    }
    paintBlock(uid, true);
    paintUndo();
    reveal(uid);
  }
  function restore(uid, text) {
    commitText(uid, text);
    toast(t('doc.history.restored'));
    closeHistory();
  }

  // ── "On this page": the outline, its counts, and the word count ───────────────────
  let outline = [];                  // [{target, name, ids, btn, count}]
  let spyQueued = false, wordsTimer = null;
  const segmenters = {};
  function plain(text) { return String(text || '').replace(/<a wg-[0-9]+="">|<\/a>|<br>/g, ''); }
  function countWords(text, lang) {
    if (!text) return 0;
    if (typeof Intl !== 'undefined' && Intl.Segmenter) {
      const seg = segmenters[lang] || (segmenters[lang] = new Intl.Segmenter(lang, { granularity: 'word' }));
      let n = 0;
      for (const s of seg.segment(text)) if (s.isWordLike) n++;
      return n;
    }
    return text.trim().split(/\s+/).filter(Boolean).length;
  }
  // ── the filter and "Next to check" (CEL-036) ────────────────────────────────────
  // What the page already knows about a text, in this language: EDITED (a decision with a wording),
  // NEW from Gemini (a draft and no edit), FLAGGED by a check (the language's findings from desk-read).
  // "To check" is a text from Gemini or a check that has not been edited and has not been looked at in
  // this browser: pressing Next to check moves on from a text, which counts as looking at it.
  let filter = 'all';
  let cursor = null;                 // the text Next to check last went to
  function isEdited(uid) { const r = curRec(S.lang, uid); return !!(r && r.text); }
  function isNew(uid) { const d = L[S.lang].drafts[uid]; return !!(d && d.text) && !isEdited(uid); }
  // A finding belongs to one wording (its `subject`: 'live' = Weglot's current text, 'draft' = Gemini's;
  // the engine writes only 'live' for now, and deletes the stale ones every run). A text is flagged only by a
  // finding on the wording the page shows: an edited text is a saved wording no check has run on, and a
  // text with a Gemini draft shows the draft, not the live text the finding is about.
  function isFlagged(uid) {
    const f = L[S.lang].findings[uid];
    if (!f || !f.length) return false;
    const d = L[S.lang].drafts[uid];
    const shown = isEdited(uid) ? 'edit' : (d && d.text ? 'draft' : 'live');
    return f.some(function (x) { return x.subject === shown; });
  }
  function matches(uid) {
    if (filter === 'new') return isNew(uid);
    if (filter === 'edited') return isEdited(uid);
    if (filter === 'flagged') return isFlagged(uid);
    return true;
  }
  function seenKey(uid) { return S.lang + '|' + uid; }
  function markSeen(uid) {
    const m = lsGet(KEYS.seen) || {};
    if (m[seenKey(uid)]) return;
    m[seenKey(uid)] = 1;
    lsSet(KEYS.seen, m);
  }
  // `seen` is the stored map, read once by a caller that asks about many texts.
  function toCheck(uid, seen) {
    return !isEdited(uid) && (isNew(uid) || isFlagged(uid)) && !(seen || lsGet(KEYS.seen) || {})[seenKey(uid)];
  }
  // The texts to check that show, in the page's order.
  function candidates() {
    if (!S.doc) return [];
    const seen = lsGet(KEYS.seen) || {};
    return S.doc.blocks.map(function (d) { return d.id; }).filter(function (uid) {
      const b = M.get(uid);
      return b && !b.d.lock && !b.li.hidden && toCheck(uid, seen);
    });
  }
  // The texts of this page the reviewer has looked at (Next marks them): they are not counted again until asked.
  function seenHere() {
    if (!S.doc) return [];
    const seen = lsGet(KEYS.seen) || {};
    return S.doc.blocks.map(function (d) { return d.id; }).filter(function (uid) { return seen[seenKey(uid)]; });
  }
  function showSeenAgain() {
    const m = lsGet(KEYS.seen) || {};
    seenHere().forEach(function (uid) { delete m[seenKey(uid)]; });
    lsSet(KEYS.seen, m);
    updateNext();
  }
  function updateNext() {
    const btn = $('doc-next'), count = $('doc-next-count');
    if (!btn) return;
    const n = S.loading ? 0 : candidates().length;
    btn.disabled = !n;
    count.textContent = S.loading ? '' : (n ? tn('doc.next.left', n) : t('doc.next.none'));
    let again = $('doc-seen-reset');
    if (!again) {
      again = h('button', 'desk-btn doc-seen-reset', '');
      again.type = 'button';
      again.id = 'doc-seen-reset';
      again.addEventListener('click', showSeenAgain);
      count.parentNode.insertBefore(again, count.nextSibling);
    }
    const m = S.loading ? 0 : seenHere().length;
    again.hidden = !m;
    again.textContent = m ? tn('doc.next.again', m) : '';
  }
  // Show the texts the filter keeps. When the page re-reads (new drafts arrive) a text with the caret
  // in it stays, whatever it matches now: the text being typed in must never vanish. A filter the
  // reviewer has just chosen (`chosen`) is followed to the letter.
  function applyFilter(chosen) {
    let shown = 0;
    M.forEach(function (b, uid) {
      const keep = matches(uid) || (!chosen && b.li.contains(document.activeElement));
      b.li.hidden = !keep;
      if (keep) shown++;
    });
    $('doc-filter-empty').hidden = !(filter !== 'all' && M.size && !shown);
    paintOutline();
    updateNext();
  }
  // A window is open over the page: the translate confirm, the history drawer, the export and re-translate windows.
  function windowOpen() {
    return !$('doc-history').hidden || !!document.querySelector('.cpw-overlay:not([hidden])');
  }
  function goNext() {
    if (S.loading || !S.doc) return;
    const order = S.doc.blocks.map(function (d) { return d.id; });
    const at = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.doc-block') : null;
    const cur = at ? at.getAttribute('data-uid') : cursor;
    if (cur && M.has(cur) && toCheck(cur)) markSeen(cur);        // moving on from a text means it was looked at
    const list = candidates();
    if (!list.length) { updateNext(); return; }
    const from = cur ? order.indexOf(cur) : -1;
    const uid = list.filter(function (u) { return order.indexOf(u) > from; })[0] || list[0];
    const b = M.get(uid);
    cursor = uid;
    try { b.li.scrollIntoView({ behavior: 'auto', block: 'start' }); } catch (_) {}
    b.tgt.focus({ preventScroll: true });
    caretEnd(b.tgt);
    b.li.setAttribute('data-flash', '1');
    setTimeout(function () { b.li.removeAttribute('data-flash'); }, 1000);
    updateNext();
  }

  function jumpTo(uid) {
    let b = M.get(uid);
    if (b && b.li.hidden) {       // a section's first text the filter hides: go to its first text that shows
      const o = outline.filter(function (x) { return x.target === uid; })[0];
      const first = o && shownIds(o)[0];
      b = first ? M.get(first) : null;
    }
    if (!b) return;
    const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    try { b.li.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' }); } catch (_) {}
  }
  function buildOutline(data) {
    outline = [];
    const search = { target: null, name: t('doc.outline.search'), ids: [] };
    let cur = null;
    data.blocks.forEach(function (d) {
      if (d.b === 'meta-title' || d.b === 'meta-description') {
        if (!search.target) search.target = d.id;
        if (!d.lock) search.ids.push(d.id);
        return;
      }
      // A section is what the unit's own `section` names (the page's h3 section titles; the h1 and the
      // small h2 taglines carry one too): a new entry where it changes, at the block that starts it.
      const sec = plain(d.sec || '');
      if (sec && (!cur || cur.sec !== sec)) {
        // A small h2 tagline that stands alone ("Our Campus" over a section title) is not a section of its
        // own: it joins the section that follows, which keeps its title, and the entry jumps to the tagline.
        const tagline = cur && cur.n === 1 && cur.kind === 'h2' ? outline.pop() : null;
        cur = { target: tagline ? tagline.target : d.id, name: sec, sec: sec, ids: tagline ? tagline.ids : [], n: tagline ? tagline.n : 0, kind: d.b };
        outline.push(cur);
      }
      if (cur) cur.n++;
      if (cur && !d.lock) cur.ids.push(d.id);
    });
    if (search.target) outline.unshift(search);
    const list = $('doc-outline-list'), sel = $('doc-sections');
    list.textContent = ''; sel.textContent = '';
    outline.forEach(function (o) {
      const li = h('li');
      o.btn = h('button', 'doc-outline-item');
      o.btn.type = 'button';
      o.btn.setAttribute('data-target', o.target);
      o.count = h('span', 'doc-outline-count');
      o.btn.appendChild(h('span', 'doc-outline-name', o.name));
      o.btn.appendChild(o.count);
      o.btn.addEventListener('click', function () { jumpTo(o.target); });
      li.appendChild(o.btn);
      list.appendChild(li);
      const opt = h('option', null, o.name);
      opt.value = o.target;
      sel.appendChild(opt);
      o.li = li; o.opt = opt;
    });
    sel.onchange = function () { jumpTo(sel.value); };
    paintOutline();
  }
  // With a filter on, an entry counts the texts the filter leaves in it, and an entry with none is
  // out of the list (and out of the Sections select) until the filter is back on All texts.
  function shownIds(o) {
    if (filter === 'all') return o.ids;
    return o.ids.filter(function (uid) { const b = M.get(uid); return b && !b.li.hidden; });
  }
  function paintOutline() {
    outline.forEach(function (o) {
      let edited = 0;
      const ids = shownIds(o);
      ids.forEach(function (uid) { const r = curRec(S.lang, uid); if (r && r.text) edited++; });
      o.count.textContent = tn('doc.outline.count', ids.length, { edited: edited });
      const gone = filter !== 'all' && !ids.length;
      if (o.li) o.li.hidden = gone;
      if (o.opt) { o.opt.hidden = gone; o.opt.disabled = gone; }
    });
    spy();
  }
  // The section being read: the last heading whose top has passed the top of the screen.
  function spy() {
    spyQueued = false;
    let now = outline.filter(function (o) { return !(o.li && o.li.hidden); })[0] || null;
    outline.forEach(function (o) {
      if (o.li && o.li.hidden) return;
      const b = M.get(filter === 'all' ? o.target : (shownIds(o)[0] || o.target));
      if (b && !b.li.hidden && b.li.getBoundingClientRect().top <= 140) now = o;
    });
    outline.forEach(function (o) {
      if (o === now) o.btn.setAttribute('aria-current', 'true'); else o.btn.removeAttribute('aria-current');
    });
    if (now) $('doc-sections').value = now.target;
  }
  function paintWords() {
    clearTimeout(wordsTimer);
    wordsTimer = setTimeout(function () {
      let n = 0;
      M.forEach(function (b, uid) {
        const shown = b.d.lock ? ((b.d.w && b.d.w[S.lang]) || '') : effText(S.lang, uid);
        n += countWords(plain(shown), S.lang);
      });
      $('doc-words').textContent = S.loading ? '' : tn('doc.words', n, { n: n.toLocaleString() });
    }, 250);
  }

  // ── loading ────────────────────────────────────────────────────────────────────────
  function getJson(path) {
    return fetch(path, { cache: 'no-cache' }).then(function (resp) {
      if (!resp.ok) throw new Error('load');
      return resp.json();
    });
  }
  function getPage(page) {
    if (PAGE_CACHE.has(page)) return Promise.resolve(PAGE_CACHE.get(page));
    return getJson(DATA + page + '.json').then(function (d) { PAGE_CACHE.set(page, d); return d; });
  }
  function getInfo() {
    if (PI.size) return Promise.resolve();
    return getJson(DATA + 'pages.json').then(function (d) {
      d.pages.forEach(function (p) { PI.set(p.key, p); });
    });
  }
  // A conflict is kept in storage as the entry's `conflict` flag; what the other editor saved is read
  // again from the server, so a reload shows the same choice (keep mine / take theirs) and the edit is
  // neither sent over it nor forgotten.
  function restoreConflicts(lang) {
    const mine = P[lang] || {};
    Object.keys(mine).forEach(function (uid) {
      if (mine[uid].conflict) conf(lang)[uid] = { current: L[lang].decisions[uid] || null, page: mine[uid].page };
    });
  }
  function ensureLang(lang) {
    if (L[lang].loaded) return Promise.resolve();
    if (SAVE_OFF_ON) { L[lang].loaded = true; return Promise.resolve(); }
    return call({ action: 'desk-read', locale: lang }).then(function (r) {
      if (!r || !r.ok || !r.body) throw new Error('read');
      L[lang].decisions = r.body.decisions || {};
      L[lang].drafts = r.body.drafts || {};
      L[lang].pipeline = r.body.pipeline || {};
      L[lang].findings = r.body.findings || {};
      L[lang].loaded = true;
      restoreConflicts(lang);
    });
  }
  // The language read again (a translation finished): new drafts show where nothing was edited.
  function refreshLang(lang) {
    if (SAVE_OFF_ON) return Promise.resolve();
    return call({ action: 'desk-read', locale: lang }).then(function (r) {
      if (!r || !r.ok || !r.body) return;
      L[lang].drafts = r.body.drafts || {};
      L[lang].pipeline = r.body.pipeline || {};
      L[lang].findings = r.body.findings || {};
      Object.keys(r.body.decisions || {}).forEach(function (uid) {
        const mine = P[lang] && P[lang][uid];
        if (!mine) L[lang].decisions[uid] = r.body.decisions[uid];
      });
      if (lang === S.lang) { M.forEach(function (b, uid) { paintBlock(uid); }); applyFilter(); }
      gridSoon();
    });
  }
  function remember() {
    lsSet(KEYS.last, { page: S.page, lang: S.lang });
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('page', S.page);
      url.searchParams.set('lang', S.lang);
      window.history.replaceState(null, '', url.pathname + url.search);
    } catch (_) {}
  }
  function headings() {
    const lang = S.lang;
    $('doc-title').textContent = t('doc.title', { page: t('page.' + S.page), language: t('lang.' + lang) });
    document.querySelector('.doc-head-en').textContent = t('doc.head.en');
    document.querySelector('.doc-head-tgt').textContent = t('doc.head.tgt', { language: t('lang.' + lang) });
    document.querySelector('.doc-head-weglot').textContent = t('doc.head.weglot');
  }
  function build(data, token) {
    const list = $('doc-blocks');
    list.textContent = '';
    M.clear();
    const blocks = data.blocks;
    let at = 0;
    (function slice() {
      if (token !== S.token) return;
      const end = Math.min(blocks.length, at + (at === 0 ? 40 : 80));
      const frag = document.createDocumentFragment();
      for (; at < end; at++) {
        const b = buildBlock(blocks[at]);
        frag.appendChild(b.li);
      }
      list.appendChild(frag);
      if (at < blocks.length) { setTimeout(slice, 0); return; }
      M.forEach(function (b, uid) { paintBlock(uid); });
      buildOutline(data);
      applyFilter();
      paintWords();
      $('doc').setAttribute('data-state', 'ready');
      updateBar();
    })();
  }
  async function open(page, lang) {
    closeGroup();
    closeHistory();
    readError = false;
    S.page = page; S.lang = lang; S.loading = true;
    cursor = null;
    const token = ++S.token;
    remember();
    headings();
    $('doc').setAttribute('data-state', 'loading');
    $('doc-blocks').textContent = '';
    $('doc-outline-list').textContent = '';
    $('doc-sections').textContent = '';
    outline = [];
    $('doc-words').textContent = '';
    M.clear();
    $('doc-filter-empty').hidden = true;
    updateNext();
    paintUndo();
    updateBar();
    paintGrid();
    let data;
    try {
      data = await getPage(page);
      await getInfo();
    } catch (_) {
      if (token !== S.token) return;
      S.loading = false;
      $('doc').setAttribute('data-state', 'error');
      $('doc-banner').hidden = false;
      $('doc-banner-text').textContent = t('doc.load.failed');
      $('doc-banner-translate').hidden = true;
      updateBar();
      return;
    }
    try { await ensureLang(lang); } catch (_) { readError = true; }
    if (token !== S.token) return;
    S.doc = data;
    S.loading = false;
    if (readError) {
      $('doc').setAttribute('data-state', 'error');
      updateBar();
      paintBanner();
      return;
    }
    build(data, token);
    paintGrid();
    checkJob(lang);
    // With the first language on screen, read the rest for the grid, one at a time.
    const rest = LANGS.filter(function (c) { return c !== lang && !L[c].loaded; });
    (function next() {
      const c = rest.shift();
      if (!c || token !== S.token) return;
      // Each language also says whether a translate-page job is open for it (the grid shows it).
      ensureLang(c).catch(function () {}).then(function () { checkJob(c); updateBar(); gridSoon(); setTimeout(next, 0); });
    })();
  }

  // ── wiring ─────────────────────────────────────────────────────────────────────────
  function weglot(on) {
    $('doc-blocks').setAttribute('data-weglot', on ? 'on' : 'off');
    document.querySelector('.doc-head-weglot').hidden = !on;
    M.forEach(function (b) { b.wg.hidden = !on; });
    $('doc-weglot').checked = on;
    lsSet(KEYS.weglot, on);
  }
  function startPoint() {
    const q = new URLSearchParams(window.location.search);
    const last = lsGet(KEYS.last) || {};
    let page = q.get('page'), lang = q.get('lang');
    if (PAGES.indexOf(page) < 0) page = PAGES.indexOf(last.page) >= 0 ? last.page : PAGES[0];
    if (LANGS.indexOf(lang) < 0) lang = LANGS.indexOf(last.lang) >= 0 ? last.lang : LANGS[0];
    return { page: page, lang: lang };
  }
  function wire() {
    document.querySelectorAll('.doc-cell').forEach(function (cell) {
      cell.addEventListener('click', function () {
        const page = cell.getAttribute('data-page'), lang = cell.getAttribute('data-lang');
        if (page === S.page && lang === S.lang) return;
        open(page, lang);
      });
    });
    $('doc-undo').addEventListener('click', undo);
    $('doc-redo').addEventListener('click', redo);
    $('doc-weglot').addEventListener('change', function (ev) { weglot(ev.target.checked); });
    $('doc-filter').addEventListener('change', function (ev) {
      filter = ev.target.value;
      applyFilter(true);
      const spot = $('doc-blocks');
      try { window.scrollTo({ top: Math.max(0, spot.getBoundingClientRect().top + window.scrollY - 140), behavior: 'auto' }); } catch (_) {}
    });
    $('doc-next').addEventListener('click', goNext);
    $('doc-translate').addEventListener('click', function (ev) { translatePage(ev.currentTarget); });
    $('doc-banner-translate').addEventListener('click', function (ev) { openConfirm(ev.currentTarget); });
    $('doc-confirm-cancel').addEventListener('click', closeConfirm);
    $('doc-confirm-ok').addEventListener('click', function () { startJob(S.lang, S.page); });
    $('doc-history-close').addEventListener('click', closeHistory);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        if (!$('doc-confirm').hidden) { closeConfirm(); return; }
        if (!$('doc-history').hidden) { closeHistory(); return; }
      }
      // The confirm window holds the focus: Tab goes round its two buttons.
      if (ev.key === 'Tab' && !$('doc-confirm').hidden) {
        const first = $('doc-confirm-cancel'), last = $('doc-confirm-ok');
        const at = document.activeElement;
        if (ev.shiftKey && at === first) { ev.preventDefault(); last.focus(); }
        else if (!ev.shiftKey && at === last) { ev.preventDefault(); first.focus(); }
        else if (at !== first && at !== last) { ev.preventDefault(); last.focus(); }
        return;
      }
      // Next to check: Alt+Enter (Option+Return on a Mac), the caret in a text included. It is a key that
      // types nothing in any layout (Option+a letter is a dead key on a Mac: n gives ñ, ã, õ) and that the
      // text field does nothing with on its own. Not while a window (translate, history, export) is open.
      if (ev.altKey && !ev.ctrlKey && !ev.metaKey && !ev.shiftKey && ev.key === 'Enter' && !ev.isComposing && ev.keyCode !== 229) {
        if (windowOpen()) return;
        ev.preventDefault();
        goNext();
        return;
      }
      if (!(ev.ctrlKey || ev.metaKey) || ev.altKey) return;
      const k = ev.key.toLowerCase();
      if (k !== 'z' && k !== 'y') return;
      // Not while an IME is composing, and not in a form field that is not one of the desk's own texts (the
      // account menu's fields, the Re-translate note): those keep the browser's own undo.
      if (ev.isComposing || ev.keyCode === 229) return;
      const field = ev.target && ev.target.closest ? ev.target.closest('input, textarea, select, [contenteditable]') : null;
      if (field && !field.closest('.doc-tgt')) return;
      // ONE undo stack (Manager Ruling): inside a text being typed too, the page's undo runs and the
      // browser's own is stopped, so Undo means the same thing wherever the caret is.
      ev.preventDefault();
      if (k === 'y' || ev.shiftKey) redo(); else undo();
    });
    window.addEventListener('scroll', function () {
      if (!spyQueued) { spyQueued = true; requestAnimationFrame(spy); }
    }, { passive: true });
    window.addEventListener('online', function () { run(); updateBar(); });
    window.addEventListener('offline', updateBar);
  }

  function boot() {
    wire();
    paintUndo();
    $('doc-filter').value = filter;       // a browser may bring back an old choice from a visit before
    const nextKeys = $('doc-next').querySelector('.doc-kbd');
    if (nextKeys) nextKeys.textContent = t(IS_MAC ? 'doc.keys.next.mac' : 'doc.keys.next.other');
    weglot(lsGet(KEYS.weglot) === true);
    const at = startPoint();
    // Unsent changes of an earlier visit go out as soon as the page is up.
    if (pendingTotal()) { updateBar(); schedule(); }
    open(at.page, at.lang);
  }
  // The one door document_export.js (CEL-027: the Export window and Re-translate) comes in by. It is
  // inlined after this file and reads these; nothing else does. `pending` is a function because P is
  // read from storage once and a module must not hold a copy of it.
  window.DocDesk = {
    S: S, L: L, PI: PI, M: M, U: U, PAGES: PAGES, LANGS: LANGS, CHUNK: CHUNK, TIMING: TIMING,
    saveOff: SAVE_OFF_ON, client: DESK_CLIENT,
    pending: function () { return P; }, sendable: sendable,
    call: call, getPage: getPage, getInfo: getInfo, ensureLang: ensureLang, refreshLang: refreshLang,
    curRec: curRec, serverVer: serverVer, effText: effText, jstate: jstate, canon: canon, same: same,
    withText: withText, changeRecord: changeRecord, saveStacks: saveStacks, paintUndo: paintUndo,
    paintBlock: paintBlock, gridSoon: gridSoon, toast: toast, open: open, reveal: reveal, saveNow: run,
    failureReason: failureReason, who: who,
    setRetranslating: function (lang, uid, on) {
      if (on) RT.add(lang + '|' + uid); else RT.delete(lang + '|' + uid);
      if (lang === S.lang && M.has(uid)) paintBlock(uid);
    },
    isRetranslating: function (lang, uid) { return RT.has(lang + '|' + uid); },
    // The Worker keeps ONE open re-translate job per language: while any text of the language runs, no other can start.
    isRetranslatingLang: function (lang) {
      const head = lang + '|';
      let any = false;
      RT.forEach(function (k) { if (k.indexOf(head) === 0) any = true; });
      return any;
    },
    retranslatePage: null,           // document_export.js fills this: the whole-page window the one Translate page opens (CEL-073)
    startPageJob: function (lang, page, opts) { startJob(lang, page, false, opts); }   // that window starts its job through the desk's
  };
  boot();
})();
