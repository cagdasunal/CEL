/* Rules page, Import tab: "Download current rules" Markdown. Pure (no DOM) apart from the Blob download: builds the
   file the client hands to their AI tool. Rule lines are kept exactly as stored, the trailing ` [DE-12]` ID included;
   the word list becomes a table Term | Translation | Type (the stored words:<lang> body, read by parseWordsBody).
   Runs in the page (window.RulesDownload) and in node (tests/test_download_rules_md.py). */
(function (root) {
  'use strict';

  const TYPE_NAMES = {
    keep: 'Keep as is',
    translate: 'Always translate as',
    keyword: 'Search keyword'
  };
  const EXACT = ['Keep as is', 'Always translate as', 'Search keyword'];
  const SEP = /^\s*\|(\s*:?-{2,}:?\s*\|)+\s*$/;

  /* A cell: one line, the pipe escaped as the stored word list writes it (\|), so a row cannot break. */
  function cell(t) {
    return String(t == null ? '' : t)
      .replace(/\r?\n/g, ' ')
      .replace(/\|/g, '\\|')
      .trim();
  }

  function typeName(t) {
    const s = String(t == null ? '' : t).trim();
    if (EXACT.indexOf(s) !== -1) return s;
    return TYPE_NAMES[s.toLowerCase()] || s;
  }

  /* The stored word-list body (| Term | Translation | Type | rows) as [{term, translation, type}]. A header row,
     a separator row and a line that is not a 3-cell table row are skipped. */
  function parseWordsBody(body) {
    const out = [];
    String(body == null ? '' : body).split('\n').forEach(function (line) {
      const s = line.trim();
      if (!/^\|/.test(s) || SEP.test(s)) return;
      const cells = s.replace(/^\|/, '').replace(/\|\s*$/, '').split(/(?<!\\)\|/).map(function (c) {
        return c.trim().replace(/\\\|/g, '|');
      });
      if (cells.length < 3) return;
      if (cells[0].toLowerCase() === 'term' && cells[2].toLowerCase() === 'type') return;
      out.push({ term: cells[0], translation: cells[1], type: cells[2] });
    });
    return out;
  }

  /* words: [{term, translation, type}] where type is one of the three names (or the keys keep | translate | keyword). */
  function rulesDownloadMarkdown(opts) {
    const o = opts || {};
    const language = String(o.language || '').trim();
    const body = String(o.rulesBody == null ? '' : o.rulesBody).replace(/\s+$/, '');
    const words = Array.isArray(o.words) ? o.words : [];
    const out = [];
    out.push('# ' + (language ? language + ' ' : '') + 'translation rules');
    out.push('');
    out.push('## Rules');
    out.push('');
    out.push(body === '' ? '(no rules stored yet)' : body);
    out.push('');
    out.push('## Word list');
    out.push('');
    out.push('| Term | Translation | Type |');
    out.push('| --- | --- | --- |');
    if (words.length === 0) {
      out.push('| (no words yet) |  |  |');
    } else {
      words.forEach(function (w) {
        out.push('| ' + cell(w.term) + ' | ' + cell(w.translation) + ' | ' + cell(typeName(w.type)) + ' |');
      });
    }
    return out.join('\n') + '\n';
  }

  /* Blob download, same steps as document_export.js saveBlob (:565-574). */
  function saveText(fileName, text) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  function downloadRulesMd(language, text) {
    saveText('cel-rules-' + String(language || 'rules').toLowerCase().replace(/[^a-z0-9-]+/g, '-') + '.md', text);
  }

  const api = {
    rulesDownloadMarkdown: rulesDownloadMarkdown, parseWordsBody: parseWordsBody,
    downloadRulesMd: downloadRulesMd, saveText: saveText
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RulesDownload = api;
})(typeof window !== 'undefined' ? window : globalThis);
