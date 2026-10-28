/* Rules page: Markdown body <-> blocks. One block per editable unit
   (heading, list item, quote line, paragraph, table row); unchanged blocks
   keep their raw source, so parse -> serialize is byte-equal. Runs in the
   page (window.RulesMd) and in node for the round-trip test. */
(function (root) {
  'use strict';

  const HEAD = /^(#{1,6} )(.*)$/;
  const ITEM = /^(\s*(?:[-*+]|\d+[.)]) )(.*)$/;
  const QUOTE = /^(>\s?)(.*)$/;
  const HR = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
  const ROW = /^\s*\|.*\|\s*$/;
  const SEP = /^\s*\|(\s*:?-{2,}:?\s*\|)+\s*$/;

  function splitRow(line) {
    const s = line.trim().replace(/^\|/, '').replace(/\|$/, '');
    const out = [];
    let cur = '';
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (c === '\\' && s[i + 1] === '|') { cur += '\\|'; i++; continue; }
      if (c === '|') { out.push(cur.trim()); cur = ''; continue; }
      cur += c;
    }
    out.push(cur.trim());
    return out;
  }

  function cellText(t) {
    // every pipe not already escaped, adjacent ones included (a||b -> a\|\|b)
    return String(t).replace(/\r?\n/g, ' ').replace(/\\\|/g, '\u0000').replace(/\|/g, '\\|').replace(/\u0000/g, '\\|');
  }

  function joinRow(cells) {
    return '| ' + cells.map(cellText).join(' | ') + ' |';
  }

  /* A block: {kind, raw, prefix, text, cells?, level?}. kind is one of
     head, item, quote, para, row, sep, hr, blank. Only head, item, quote,
     para and row are editable. */
  function parse(body) {
    const lines = String(body == null ? '' : body).split('\n');
    const blocks = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let m;
      if (line.trim() === '') { blocks.push({ kind: 'blank', raw: line }); continue; }
      if (HR.test(line)) { blocks.push({ kind: 'hr', raw: line }); continue; }
      if ((m = HEAD.exec(line))) {
        blocks.push({ kind: 'head', raw: line, prefix: m[1], text: m[2], level: m[1].length - 1 });
        continue;
      }
      if (SEP.test(line)) { blocks.push({ kind: 'sep', raw: line }); continue; }
      if (ROW.test(line)) { blocks.push({ kind: 'row', raw: line, cells: splitRow(line) }); continue; }
      if ((m = ITEM.exec(line))) { blocks.push({ kind: 'item', raw: line, prefix: m[1], text: m[2] }); continue; }
      if ((m = QUOTE.exec(line))) { blocks.push({ kind: 'quote', raw: line, prefix: m[1], text: m[2] }); continue; }
      /* a paragraph runs until a blank line or another block starts */
      const para = [line];
      while (i + 1 < lines.length) {
        const nx = lines[i + 1];
        if (nx.trim() === '' || HR.test(nx) || HEAD.test(nx) || ROW.test(nx) || ITEM.test(nx) || QUOTE.test(nx)) break;
        para.push(nx);
        i++;
      }
      const raw = para.join('\n');
      blocks.push({ kind: 'para', raw: raw, prefix: '', text: raw });
    }
    return blocks;
  }

  function rawOf(b) {
    if (b.edited) {
      if (b.kind === 'row') return joinRow(b.cells);
      return (b.prefix || '') + b.text;
    }
    return b.raw;
  }

  function serialize(blocks) {
    return blocks.map(rawOf).join('\n');
  }

  /* Split a parsed body into sections at each level-2 heading. The part
     before the first `##` is section 0 (title + intro), which may be empty. */
  function sections(blocks) {
    const out = [{ head: null, blocks: [] }];
    blocks.forEach(function (b, i) {
      if (b.kind === 'head' && b.level === 2) out.push({ head: b, index: i, blocks: [] });
      else out[out.length - 1].blocks.push(b);
    });
    return out;
  }

  /* Glossary: one table | English | <Language> | Keep as is |. */
  function parseGlossary(body) {
    const rows = [];
    parse(body).forEach(function (b) {
      if (b.kind !== 'row') return;
      rows.push(b.cells);
    });
    const un = function (s) { return String(s || '').replace(/\\\|/g, '|'); };
    const terms = rows.slice(1).map(function (c) {
      return { en: un(c[0]), to: un(c[1]), keep: /^\s*yes\s*$/i.test(c[2] || '') };
    });
    return { header: rows[0] || null, terms: terms };
  }

  function serializeGlossary(language, terms) {
    const lines = [joinRow(['English', language, 'Keep as is']), '| --- | --- | --- |'];
    terms.forEach(function (t) { lines.push(joinRow([t.en, t.to, t.keep ? 'yes' : ''])); });
    return lines.join('\n') + '\n';
  }

  /* Word list (CEL-113): scope `words:<lang>`, one table | Term | Translation | Type |. The Type words below are the
     stored form (the page words them from COPY.md). A Keep as is word has no Translation, a Search keyword's Term IS
     the phrase in the language, only Always translate as carries a Translation. */
  const WORD_TYPES = { keep: 'Keep as is', always: 'Always translate as', kw: 'Search keyword' };
  const unpipe = function (s) { return String(s || '').replace(/\\\|/g, '|'); };

  /* The Type of a cell the way the engine reads it (case and spacing ignored); null = not a Type the engine knows, and
     the engine skips such a row (rules_store.parse_words), so the page does not show it either. */
  function wordType(label) {
    const s = String(label || '').toLowerCase().split(/\s+/).filter(Boolean).join(' ');
    return Object.keys(WORD_TYPES).find(function (x) { return WORD_TYPES[x].toLowerCase() === s; }) || null;
  }
  function wordCells(w) {
    return [w.term, w.type === 'always' ? w.tr : '', WORD_TYPES[w.type]];
  }
  /* The words of a parsed body, in order: {idx (index in blocks), term, tr, type}. What is not a row of exactly three
     cells with a term and a known Type (the header, a line of prose, a typo in the Type) is not a word: the engine skips it too. */
  function wordRows(blocks) {
    const out = [];
    blocks.forEach(function (b, idx) {
      if (b.kind !== 'row' || b.cells.length !== 3) return;
      const term = unpipe(b.cells[0]), type = wordType(b.cells[2]);
      if (!term || !type) return;
      out.push({ idx: idx, term: term, tr: type === 'always' ? unpipe(b.cells[1]) : '', type: type });
    });
    return out;
  }
  /* A whole body from word objects {term, tr, type}. */
  function wordsBody(rows) {
    const lines = ['| Term | Translation | Type |', '|---|---|---|'];
    rows.forEach(function (w) { lines.push(joinRow(wordCells(w))); });
    return lines.join('\n') + '\n';
  }
  /* The starting table when `words:<lang>` has not been written yet: the client's glossary the way the engine reads it
     (rules_store.words_from_glossary): `yes` is Keep as is, a row with a rendering is Always translate as, the header
     and a row with neither are skipped. */
  function wordsFromGlossary(body) {
    const out = [];
    parse(body).forEach(function (b) {
      if (b.kind !== 'row' || b.cells.length !== 3) return;
      const eng = unpipe(b.cells[0]), tgt = unpipe(b.cells[1]), keep = b.cells[2];
      if (!eng || keep.toLowerCase() === 'keep as is') return;
      if (/^\s*yes\s*$/i.test(keep)) out.push({ term: eng, tr: '', type: 'keep' });
      else if (tgt) out.push({ term: eng, tr: tgt, type: 'always' });
    });
    return out;
  }
  /* Change the word at block `idx` in place (the block keeps its place; every other line stays byte-equal). */
  function setWord(blocks, idx, w) {
    blocks[idx].cells = wordCells(w);
    blocks[idx].edited = true;
  }
  /* Add a word after the last table line of the body (or start the table when there is none). */
  function addWord(blocks, w) {
    let at = -1;
    blocks.forEach(function (b, i) { if (b.kind === 'row' || b.kind === 'sep') at = i; });
    const row = { kind: 'row', raw: '', cells: wordCells(w), edited: true };
    if (at >= 0) { blocks.splice(at + 1, 0, row); return; }
    if (blocks.length && blocks[blocks.length - 1].kind !== 'blank') blocks.push({ kind: 'blank', raw: '' });
    blocks.push({ kind: 'row', raw: '| Term | Translation | Type |', cells: ['Term', 'Translation', 'Type'] },
      { kind: 'sep', raw: '|---|---|---|' }, row, { kind: 'blank', raw: '' });
  }

  /* Line diff of two bodies: the first changed line, before -> after. */
  function firstChange(before, after) {
    const a = String(before || '').split('\n');
    const b = String(after || '').split('\n');
    let i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i++;
    if (i === a.length && i === b.length) return null;
    let ja = a.length - 1, jb = b.length - 1;
    while (ja >= i && jb >= i && a[ja] === b[jb]) { ja--; jb--; }
    return {
      before: a.slice(i, ja + 1).join('\n'),
      after: b.slice(i, jb + 1).join('\n'),
    };
  }

  const api = {
    parse: parse,
    serialize: serialize,
    rawOf: rawOf,
    sections: sections,
    splitRow: splitRow,
    joinRow: joinRow,
    parseGlossary: parseGlossary,
    serializeGlossary: serializeGlossary,
    WORD_TYPES: WORD_TYPES,
    wordRows: wordRows,
    wordsBody: wordsBody,
    wordsFromGlossary: wordsFromGlossary,
    setWord: setWord,
    addWord: addWord,
    firstChange: firstChange,
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RulesMd = api;
})(typeof window !== 'undefined' ? window : this);
