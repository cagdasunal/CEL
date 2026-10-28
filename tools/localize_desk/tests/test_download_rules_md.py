"""download_rules_md.js (CEL-114): the "Download current rules" Markdown. Pure functions, run under node (skipped without it).
From the CEL-114 helper draft: rule IDs stay on their lines, the three Type names are exact, an empty list still has its
table, a pipe in a cell is escaped the way the stored word list writes it (\\|), and the stored body reads back."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "download_rules_md.js"
NODE = shutil.which("node")

SCRIPT = r"""
const assert = require('node:assert/strict');
const { rulesDownloadMarkdown, parseWordsBody } = require(process.argv[1]);
const BODY = '## 7.1 German (de)\n- **Formal:** use Sie [DE-1]\n- **Numbers:** write 1.000 with a dot [DE-12]\n';

let md = rulesDownloadMarkdown({ language: 'German', rulesBody: BODY, words: [] });
assert.ok(md.startsWith('# German translation rules\n'));
assert.ok(md.includes('- **Formal:** use Sie [DE-1]\n'));
assert.ok(md.includes('- **Numbers:** write 1.000 with a dot [DE-12]\n'));
assert.ok(md.includes('| Term | Translation | Type |\n| --- | --- | --- |\n| (no words yet) |  |  |\n'));

md = rulesDownloadMarkdown({ language: 'German', rulesBody: BODY, words: [
  { term: 'Pacific Beach', translation: 'Pacific Beach', type: 'Keep as is' },
  { term: 'homestay', translation: 'Gastfamilie', type: 'translate' },
  { term: 'learn english', translation: 'Englisch lernen', type: 'Search keyword' }] });
assert.ok(md.includes('| Pacific Beach | Pacific Beach | Keep as is |\n'));
assert.ok(md.includes('| homestay | Gastfamilie | Always translate as |\n'));
assert.ok(md.includes('| learn english | Englisch lernen | Search keyword |\n'));

md = rulesDownloadMarkdown({ language: 'German', rulesBody: '- **Code:** keep `a|b` as is [DE-3]\n',
  words: [{ term: 'a|b', translation: 'x`y', type: 'Keep as is' }] });
assert.ok(md.includes('- **Code:** keep `a|b` as is [DE-3]\n'));
assert.ok(md.includes('| a\\|b | x`y | Keep as is |\n'));

assert.equal(rulesDownloadMarkdown({ language: 'French', rulesBody: '', words: [] }).includes('(no rules stored yet)'), true);

const stored = '| Term | Translation | Type |\n|---|---|---|\n| a\\|b | x | Always translate as |\n| Pacific Beach |  | Keep as is |\n';
assert.deepStrictEqual(parseWordsBody(stored), [
  { term: 'a|b', translation: 'x', type: 'Always translate as' },
  { term: 'Pacific Beach', translation: '', type: 'Keep as is' }]);
assert.deepStrictEqual(parseWordsBody(null), []);
console.log('ok');
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_download_rules_markdown_keeps_ids_types_and_escapes():
    res = subprocess.run([NODE, "-e", SCRIPT, str(JS)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr or res.stdout
    assert res.stdout.strip() == "ok"
