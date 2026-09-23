"""Tests for the Localization Desk generator.

Each test here guards something that has ALREADY gone wrong once, or a safety
property the desk's whole design rests on. Nothing tests HTML prose for its own
sake -- the assertions on generated markup are about structure and about the one
JS invariant that decides whether a mis-click can cost money.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import generate_desk_page as G  # noqa: E402


def _unit(uid: str, *, word_from: str = "Hello", noise: bool = False,
          summary_owned: bool = False, current: dict | None = None) -> dict:
    return {
        "unit_id": uid,
        "word_from": word_from,
        "type": "Text",
        "role": "body",
        "section": "Sec",
        "markup_class": "plain",
        "pages": [],
        "noise": noise,
        "summary_owned": summary_owned,
        "current": current if current is not None else {"de": {"word_to": "Hallo"}},
    }


@pytest.fixture()
def units_dir(tmp_path, monkeypatch):
    d = tmp_path / "units"
    d.mkdir()
    monkeypatch.setattr(G, "UNITS_DIR", d)
    return d


def _write(d: Path, page: str, units: list[dict]) -> None:
    (d / f"{page}.json").write_text(
        json.dumps({"page": page, "path": f"/{page}", "units": units}), encoding="utf-8"
    )


class TestLoadUnits:
    def test_excludes_noise_and_summary_owned(self, units_dir):
        _write(units_dir, "vancouver", [
            _unit("keep"),
            _unit("drop-noise", noise=True),
            _unit("drop-summary", summary_owned=True),
        ])
        assert [u["unit_id"] for u in G.load_units()] == ["keep"]

    def test_dedupes_by_unit_id_and_unions_pages(self, units_dir):
        # The same string on two pages is ONE Weglot unit; approving it approves it
        # everywhere. It must appear once, but stay findable from either page filter.
        _write(units_dir, "vancouver", [_unit("shared")])
        _write(units_dir, "vs-toronto", [_unit("shared")])
        units = G.load_units()
        assert len(units) == 1
        assert units[0]["_pages"] == {"vancouver", "vs-toronto"}

    def test_missing_dir_yields_nothing_rather_than_raising(self, tmp_path, monkeypatch):
        monkeypatch.setattr(G, "UNITS_DIR", tmp_path / "nope")
        assert G.load_units() == []


class TestMainRefusesEmptyOutput:
    """The first run of this generator wrote eight complete, correctly-styled,
    entirely EMPTY pages: REPO_ROOT pointed one directory too high, and
    Path.glob on a missing directory returns nothing -- indistinguishable from
    'no units matched'. Silence is not an acceptable outcome here."""

    def test_missing_units_dir_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(G, "UNITS_DIR", tmp_path / "nope")
        monkeypatch.setattr(G, "OUT_ROOT", tmp_path / "out")
        assert G.main() == 2
        assert not (tmp_path / "out").exists()

    def test_zero_units_exits_nonzero_and_writes_nothing(self, units_dir, tmp_path, monkeypatch):
        _write(units_dir, "vancouver", [_unit("drop", noise=True)])
        monkeypatch.setattr(G, "OUT_ROOT", tmp_path / "out")
        assert G.main() == 2
        assert not (tmp_path / "out").exists()

    def test_real_units_write_index_and_every_locale(self, units_dir, tmp_path, monkeypatch):
        _write(units_dir, "vancouver", [
            _unit("a", current={code: {"word_to": "x"} for code, *_ in G.LOCALES}),
        ])
        out = tmp_path / "out"
        monkeypatch.setattr(G, "OUT_ROOT", out)
        assert G.main() == 0
        assert (out / "index.html").is_file()
        for code, *_ in G.LOCALES:
            assert (out / code / "index.html").is_file(), code


class TestRenderedPage:
    @pytest.fixture()
    def page(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", current={"de": {"word_to": "Hallo"}})])
        units = G.load_units()
        return G.render_locale("de", "German", "Deutsch", "ltr", units)

    def test_chrome_is_emitted_exactly_once(self, page):
        # render_admin_close() already emits the account modal, the closing div AND
        # the <script> wrapper. Appending them again printed the whole chrome script
        # as visible body text under the cards.
        assert page.count('id="cpw-overlay"') == 1
        assert page.count("shell-root") == 1
        assert page.count("<body>") == 1

    def test_uses_the_shared_stylesheet_and_no_inline_style_block(self, page):
        assert '<link rel="stylesheet" href="/assets/css/dashboard.css">' in page
        # Desk rules belong in dashboard.DESK_CSS, not in a per-page <style>.
        assert "<style>" not in page

    def test_tray_assignment_is_not_a_toggle(self, page):
        """The safety property the whole flow rests on.

        A toggle survives five clicks (odd -> still queued) but not four, and a
        double-click is the commonest mis-click there is -- it would have silently
        un-queued the row. setTray() assigns; it never flips.
        """
        assert "if (tray) s.tray = tray; else delete s.tray;" in page
        assert "s.tray = !s.tray" not in page
        assert "!s.queued" not in page  # the old two-boolean model is gone

    def test_the_active_decision_is_the_undo(self, page):
        """Reversal of an earlier rule, and the reason is worth keeping.

        Tray assignment used to be add-only, so a mis-click could not multiply. It
        also meant a decision could only be taken back from the tray screen, which
        is not where anyone looks -- the operator reported being unable to undo at
        all. Clicking the decision a row already carries now clears it. That is
        safe because nothing is sent until a tray is explicitly submitted, and a
        stray double-click is visible: the row's colour wash and the filled icon
        both go.
        """
        assert "cur === 'csv' ? null : 'csv'" in page
        assert "cur === 'draft' ? null : 'draft'" in page
        # Neither control is ever disabled -- the active one IS the way back.
        assert "bApprove.disabled = false;" in page
        assert "bQueue.disabled = false;" in page

    def test_state_is_shown_by_colour_not_by_dimming(self, page):
        # Fading a decided row made the reviewer's own finished work the hardest
        # thing on the page to read, and it read as "disabled" rather than "done".
        assert "is-approved" in page and "is-queued" in page
        assert "is-done" not in page

    def test_trays_are_mutually_exclusive_by_construction(self, page):
        """One `tray` field, not two booleans.

        The contradictory state (queued AND approved) is unrepresentable, so no
        code path has to resolve it and none can forget to.
        """
        assert "'csv'" in page and "'draft'" in page
        assert "setTray(uid," in page
        # No separate approved/queued BOOLEANS anywhere. Matched precisely: the
        # bare prefix "s.approved" also matches s.approvedAgainst, which is a
        # legitimate field recording the wording an approval was given to.
        import re
        assert not re.search(r"s\.approved\s*=", page)
        assert not re.search(r"s\.approved\b(?!Against)", page)
        assert not re.search(r"s\.queued\b", page)

    def test_editing_counts_as_approving(self, page):
        # Typing the wording you want IS the decision; a follow-up Approve click
        # could only ever be "yes".
        assert "setTray(uid, 'csv', 'edit-approve');" in page

    def test_bulk_actions_exist_for_both_trays(self, page):
        assert "bulk('csv', 'approve')" in page
        assert "bulk('draft', 'queue')" in page
        assert 'id="bulk-approve"' in page
        assert 'id="bulk-draft"' in page

    def test_select_all_acts_on_what_is_shown_not_everything(self, page):
        # Selecting "all" while a filter is active must not silently take the
        # 900 rows the reviewer cannot see.
        assert "shown().forEach(function (tr) {" in page

    def test_history_is_recorded_and_capped(self, page):
        assert "function note(action, uid, from, to)" in page
        assert "LOG_CAP" in page
        assert "hist.slice(hist.length - LOG_CAP)" in page

    def test_history_is_reachable_but_not_rendered(self, page):
        assert "window.deskLog = function" in page
        # It is a console affordance, not UI: nothing in the page shows it.
        assert "deskLog()" not in page[:page.index("<script>")]

    def test_rtl_is_flagged_to_the_row_builder(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", current={"ar": {"word_to": "مرحبا"}})])
        page = G.render_locale("ar", "Arabic", "العربية", "rtl", G.load_units())
        # Without <bdi> the subtitle renders as "990 — العربية units."
        assert "<bdi>العربية</bdi>" in page
        assert "var RTL = true;" in page

    def test_ltr_locale_does_not_flag_rtl(self, page):
        assert "var RTL = false;" in page

    def test_source_text_is_separable_from_its_section_label(self, page):
        # The queue list reads .desk-srctext; reading the whole cell glued the
        # section eyebrow onto the source ("Is Vancouver Expensive?(summer surcharge)").
        assert "srcText.className = 'desk-srctext';" in page

    def test_unit_text_never_reaches_the_dom_as_markup(self, page):
        """Rows are built from JSON now, so escaping is structural, not textual.

        The guarantee is that no unit field is ever concatenated into markup: the
        builder assigns textContent / value only. An innerHTML anywhere in the desk
        script would reopen the hole that HTML-escaping used to close.
        """
        script = page[page.index("var KEY = "):]
        assert "innerHTML" not in script
        assert "srcText.textContent = u.src;" in script
        assert "live.textContent = u.tgt;" in script

    def test_payload_carries_raw_text_not_escaped_text(self, units_dir):
        # The JSON is data. Escaping it here would double-escape once textContent
        # renders it, and the reviewer would read "&amp;" on screen.
        _write(units_dir, "vancouver", [
            _unit("a", word_from="Tom & Jerry <b>",
                  current={"de": {"word_to": "Tom & Jerry"}}),
        ])
        payload = G.locale_payload("de", G.load_units())
        assert payload[0]["src"] == "Tom & Jerry <b>"

    def test_payload_excludes_locales_the_page_will_not_show(self, units_dir):
        _write(units_dir, "vancouver", [
            _unit("a", current={"de": {"word_to": "Hallo"}, "fr": {"word_to": "Salut"}}),
        ])
        payload = G.locale_payload("de", G.load_units())
        assert payload[0]["tgt"] == "Hallo"
        assert set(payload[0]) == {"id", "src", "tgt", "sec", "pages"}

    def test_payload_skips_units_with_no_translation_in_this_locale(self, units_dir):
        _write(units_dir, "vancouver", [
            _unit("has", current={"de": {"word_to": "Hallo"}}),
            _unit("lacks", current={"fr": {"word_to": "Salut"}}),
        ])
        assert [u["id"] for u in G.locale_payload("de", G.load_units())] == ["has"]


class TestAuditRegressions2026_09_23:
    @pytest.fixture()
    def page(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", current={"de": {"word_to": "Hallo"}})])
        return G.render_locale("de", "German", "Deutsch", "ltr", G.load_units())

    """Every test here went RED before the 2026-09-23 audit fixes.

    They are not structural preferences. Each one names a defect that either
    destroyed a reviewer's typing, told them work was saved when it was not, or
    dropped a field the exporter depends on to avoid re-publishing a live row.
    """

    def test_the_editor_flush_asks_the_wrapper_not_the_textarea(self, page):
        """`hidden` sits on the wrapper and does not reflect to descendants.

        `ta.hidden` was therefore always false, so leaving the page committed EVERY
        row's closed editor. On a fresh load a closed editor holds the machine
        original, so the flush overwrote the reviewer's own wording with the text
        they had rejected -- badged "your wording" -- and pushed it to the repo.
        """
        assert "if (ta.hidden) return;" not in page
        assert "var wrap = ta.closest('.desk-editor');" in page
        assert "if (!wrap || wrap.hidden) return;" in page
        # and it must also refuse a box that was opened but never changed
        assert "if (!editorDirty(ta.closest('.desk-row'))) return;" in page

    def test_every_editor_is_born_knowing_what_it_opened_with(self, page):
        """Without this seed `editorDirty` reads true for a box nobody touched."""
        assert page.count("ta.setAttribute('data-opened-with', ta.value);") >= 2

    def test_the_save_carries_every_field_the_stage_function_reads(self, page):
        """Five stamps used to be dropped by both the diff and the payload, so
        sending/arrived/failed/exported/live never left the browser that made them.

        `liveAt` is the one that costs money: the exporter skips rows already on the
        website, it reads the saved file, and without this the exclusion can never
        fire -- an older wording gets re-imported over a newer one.
        """
        for field in ("sentAt", "arrivedAt", "failed", "exportedAt", "liveAt"):
            assert f"'{field}'" in page, f"{field} missing from SAVE_FIELDS"
        assert "var SAVE_FIELDS = [" in page
        # the old hand-listed payload is gone
        assert "{ tray: mine.tray, text: mine.text, rejected: mine.rejected," not in page

    def test_a_re_approval_after_the_wording_moved_is_a_real_change(self, page):
        """`sameDecision` ignored `approvedAgainst`, so re-approving produced no
        delta, the server kept the stale snapshot, and the exporter skipped the row
        as "changed since approval" permanently -- unclearable from the UI."""
        assert "a.tray === b.tray && a.text === b.text &&" not in page
        assert "SAVE_FIELDS" in page.split("function sameDecision")[1][:400]

    def test_a_record_is_kept_for_its_stamps_not_just_its_tray(self, page):
        """Keying on `.tray` told the server to forget a row that was out for
        translation."""
        assert "function hasContent(r)" in page
        assert "var mine = hasContent(now[uid]) ? now[uid] : null;" in page
        assert "var mine = now[uid] && now[uid].tray ? now[uid] : null;" not in page

    def test_the_run_poll_is_anchored_to_a_baseline(self, page):
        """`runs?per_page=1` returns the NEWEST run, not ours.

        Locales save one after another, so when the second dispatched, the newest
        run was the first one -- already completed, already successful. Every locale
        after the first was banked against its predecessor and the reviewer was told
        it was safe to close the page.
        """
        assert "function latestRunId(workflow)" in page
        assert "function awaitRun(workflow, baselineId)" in page
        assert "run.id !== baselineId" in page
        # and with no id available it must refuse rather than guess
        assert "cannot confirm the save yet" in page

    def test_the_save_is_split_to_fit_the_dispatch_ceiling(self, page):
        """A whole locale of approvals measures 61-66 KB base64 against a 65,536
        byte cap. Arabic is OVER it; Japanese clears by 87 bytes. "Select all,
        Approve, Save" is the ordinary way to get there."""
        assert "function chunksFor(locale, body)" in page
        assert "var MAX_B64 = " in page
        cap = int(page.split("var MAX_B64 = ")[1].split(";")[0])
        assert cap < 65536, "the split threshold must sit below the real ceiling"

    def test_a_storage_failure_is_not_reported_as_success(self, page):
        """persist() swallowed the quota error and commitEditor toasted
        "Your wording saved." anyway."""
        assert "catch (e) { /* private mode */ }" not in page
        assert "This browser will not store your work" in page

    def test_adoption_only_fills_units_this_browser_has_never_touched(self, page):
        """The guard was "no tray", which is not the same thing. A row back from
        Gemini and a row deliberately un-approved both have no tray, and both were
        overwritten wholesale -- the first threw away a paid-for translation, the
        second made undo silently revert on reload."""
        assert "if (!hasContent(state[uid]))" in page
        assert "if (!state[uid] || !state[uid].tray) { state[uid] =" not in page

    def test_a_failed_baseline_fetch_is_not_mistaken_for_a_missing_file(self, page):
        """One catch covered both, so a 5xx booted the desk showing none of a
        colleague's decisions -- and the next save, merged last-writer-wins, erased
        them."""
        assert "else if (dr.status !== 404)" in page
        assert "Could not read what is already saved" in page

    def test_clearing_an_edit_restores_the_wording_the_approval_is_against(self, page):
        """Clearing the box left `tray:'csv'` with no `approvedAgainst`, so the
        export skipped its drift check and shipped whatever Weglot served that day."""
        assert "if (s.tray === 'csv') stampApproval(uid, tr, true);" in page
