"""Tests for tools.summary.match_verify — the Weglot match-verification gate (audit-108 H-1)."""
import types
from pathlib import Path

from tools.summary import match_verify, structure


_FOUR_PART = (
    "## Coastal Study\n\n"
    "### Why choose CEL in San Diego?\n\n"
    "Study English by the Pacific for 12 weeks with a [link](https://www.englishcollege.com/courses).\n\n"
    "#### What you get\n\n"
    "Small classes & real conversation — café culture included.\n"
)


def _write_csv(path: Path, word_from_values, locale="de"):
    """Write a minimal Weglot CSV with the given word_from values (Fidelo-style quoting)."""
    lines = ["id;language_from;language_to;word_from;word_to;type"]
    for wf in word_from_values:
        wf_q = '"' + wf.replace('"', '""') + '"'
        lines.append(f';en;{locale};{wf_q};"X";Text')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fetch_empty(url):
    # existing_summary_parts empty → verify falls back to en["markdown"] (we control the nodes there).
    return types.SimpleNamespace(existing_summary_parts={})


def test_live_summary_nodes_from_markdown_strips_links_and_markup():
    nodes = match_verify.live_summary_nodes(_FOUR_PART)
    assert nodes[0] == "Coastal Study"  # tagline, no '##'
    assert any("Study English by the Pacific" in n for n in nodes)
    # links stripped to anchor text; entity-free plain text
    assert all("](" not in n and "##" not in n for n in nodes)


def test_verify_pages_full_match(tmp_path):
    nodes = structure.summary_page_blocks(_FOUR_PART)
    _write_csv(tmp_path / "de.csv", nodes)  # every node present as word_from
    en = {"c1": {"url": "https://www.englishcollege.com/x", "content_type": "landing", "markdown": _FOUR_PART}}
    result = match_verify.verify_pages(en, tmp_path, ["de"], _fetch_empty)
    assert result["aggregate"]["de"]["rate"] == 1.0
    assert match_verify.all_pages_full_match(result) is True


def test_verify_pages_detects_drift(tmp_path):
    nodes = structure.summary_page_blocks(_FOUR_PART)
    _write_csv(tmp_path / "de.csv", nodes[:-1])  # drop ONE node → drift
    en = {"c1": {"url": "https://www.englishcollege.com/x", "content_type": "course", "markdown": _FOUR_PART}}
    result = match_verify.verify_pages(en, tmp_path, ["de"], _fetch_empty)
    pl = result["pages"][0]["per_locale"]["de"]
    assert pl["matched"] == pl["total"] - 1
    assert nodes[-1] in pl["missing"]
    assert match_verify.all_pages_full_match(result) is False


def test_verify_pages_skips_non_translatable(tmp_path):
    _write_csv(tmp_path / "de.csv", [])
    en = {"b1": {"url": "https://www.englishcollege.com/post/x", "content_type": "blog_post", "markdown": "## x\n\ny"}}
    result = match_verify.verify_pages(en, tmp_path, ["de"], _fetch_empty)
    assert result["pages"] == []  # blog skipped entirely


def test_verify_pages_fetch_failure_recorded(tmp_path):
    _write_csv(tmp_path / "de.csv", [])

    def _boom(url):
        raise RuntimeError("network down")

    en = {"c1": {"url": "https://www.englishcollege.com/x", "content_type": "housing", "markdown": _FOUR_PART}}
    result = match_verify.verify_pages(en, tmp_path, ["de"], _boom)
    assert "error" in result["pages"][0]
    assert match_verify.all_pages_full_match(result) is False


def test_missing_csv_file_means_zero_match(tmp_path):
    # No de.csv written → every node missing → 0%.
    en = {"c1": {"url": "https://www.englishcollege.com/x", "content_type": "landing", "markdown": _FOUR_PART}}
    result = match_verify.verify_pages(en, tmp_path, ["de"], _fetch_empty)
    assert result["aggregate"]["de"]["rate"] == 0.0


def test_csv_word_from_set_skips_header_and_strips(tmp_path):
    _write_csv(tmp_path / "de.csv", ["Hello world", "Café crème"])
    wf = match_verify.csv_word_from_set(tmp_path / "de.csv")
    assert "id" not in wf  # header skipped
    assert "Hello world" in wf
    assert "Café crème" in wf  # non-ASCII round-trips via UTF-8


def test_non_ascii_and_special_chars_match(tmp_path):
    # STRESS: CJK/Arabic + ampersand/accent nodes must match identical CSV word_from.
    md = "## 日本語\n\n### مرحبا\n\nSmall classes & a café.\n"
    nodes = structure.summary_page_blocks(md)
    _write_csv(tmp_path / "ja.csv", nodes, locale="ja")
    en = {"c1": {"url": "https://www.englishcollege.com/x", "content_type": "landing", "markdown": md}}
    result = match_verify.verify_pages(en, tmp_path, ["ja"], _fetch_empty)
    assert result["aggregate"]["ja"]["rate"] == 1.0
