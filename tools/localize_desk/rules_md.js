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
    firstChange: firstChange,
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RulesMd = api;
})(typeof window !== 'undefined' ? window : this);
