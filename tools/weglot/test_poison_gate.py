"""Tests + stress cases for the tracker-114 poison gate (tools/weglot/poison_gate.py)."""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.weglot import poison_gate  # noqa: E402
from tools.weglot.csv_engine import CSV_COLUMNS, format_csv_text, atomic_write_text  # noqa: E402

_HDR = list(CSV_COLUMNS)


def _write(csv_dir: Path, name: str, data_rows):
    atomic_write_text(csv_dir / name, format_csv_text([_HDR] + data_rows))


def test_clean_dir_passes(tmp_path):
    _write(tmp_path, "de.csv", [
        ["", "en", "de", "Amenities", "Ausstattung", "Text"],
        ["", "en", "de", "Welcome to CEL and our schools here.", "Willkommen bei CEL.", "Text"],
    ])
    assert poison_gate.scan(tmp_path, set())["total"] == 0
    assert poison_gate.main(["--dir", str(tmp_path), "--allowlist", str(tmp_path / "none.json")]) == 0


def test_poison_dir_fails_exit_2(tmp_path):
    # stress: several distinct mis-pairing shapes that broke the live site
    _write(tmp_path, "de.csv", [
        ["", "en", "de", "and", "Welcher Standort bietet die richtige Sichtbarkeit?", "Text"],
        ["", "en", "de", ".", "Überlegungen zur Unterkunft für ein langfristiges Studium", "Text"],
        ["", "en", "de", "CEL", "unsere TOEFL-Prüfungsvorbereitung empfiehlt sich heute", "Text"],
    ])
    rep = poison_gate.scan(tmp_path, set())
    assert rep["total"] == 3 and rep["by_file"] == {"de.csv": 3}
    assert poison_gate.main(["--dir", str(tmp_path), "--allowlist", str(tmp_path / "none.json")]) == 2


def test_allowlist_exempts_fidelo_label(tmp_path):
    # "Sleeping pods" is a Fidelo amenity label whose translation can exceed 30 chars —
    # it must NOT trip the gate when present in the allowlist.
    _write(tmp_path, "pt.csv", [
        ["", "en", "pt", "Sleeping pods", "Quartos com cápsulas para dormir confortavelmente", "Text"],
    ])
    assert poison_gate.scan(tmp_path, set())["total"] == 1            # flagged without allowlist
    assert poison_gate.scan(tmp_path, {"Sleeping pods"})["total"] == 0  # exempt with allowlist


def test_skips_all_languages_matrix(tmp_path):
    _write(tmp_path, "all-languages.csv", [
        ["", "en", "de", "and", "Welcher Standort bietet die richtige Sichtbarkeit?", "Text"],
    ])
    assert poison_gate.scan(tmp_path, set())["total"] == 0  # matrix file is ignored


def test_import_safe():
    import importlib
    importlib.import_module("tools.weglot.poison_gate")  # no module-level I/O / sys.exit
