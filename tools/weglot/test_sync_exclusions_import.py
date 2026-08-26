"""Import-time safety of tools/weglot/sync_exclusions.py.

This module deliberately does NOT import `requests`, so it runs everywhere —
including the environment whose absence of `requests` caused the original bug.

History: sync_exclusions.py used to do two things at import time.

  1. `except ImportError: sys.exit(1)` when `requests` was missing.
  2. `HTTP = create_robust_session()` at module scope.

Either one turns `import sync_exclusions` into a fatal action. On a machine
without `requests`, test_sync_exclusions.py's import raised SystemExit during
collection, which pytest reports as INTERNALERROR and which aborts the entire
session. That silently zeroed tools/_stress/test_00_regression.py's baseline
guard (it read 0 passed against a baseline of 462) — a guard designed to catch
test loss was itself disabled by test loss.

See rules/quality.md 12 (module-level code must be side-effect-free).
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = Path(__file__).resolve().parent

# Import sync_exclusions with `requests` forced to be unimportable, then report
# what happened. Runs in a subprocess so a SystemExit cannot take this suite out.
_PROBE = """
import sys

class _Block:
    # MetaPathFinder must implement find_spec. The legacy find_module/load_module
    # pair was removed in Python 3.12, so a finder using it is silently ignored
    # and `requests` imports anyway — which made this guard pass vacuously on an
    # interpreter that HAD requests installed.
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "requests" or fullname.startswith("requests."):
            raise ModuleNotFoundError("No module named 'requests'", name=fullname)
        return None

sys.meta_path.insert(0, _Block())
for mod in [m for m in sys.modules if m == "requests" or m.startswith("requests.")]:
    del sys.modules[mod]

sys.path.insert(0, {module_dir!r})
import sync_exclusions as m
print("IMPORTED_OK")
print("SESSION_BUILT", m._HTTP_SESSION is not None)
"""


def _run_probe():
    return subprocess.run(
        [sys.executable, "-c", _PROBE.format(module_dir=str(MODULE_DIR))],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def test_import_does_not_exit_when_requests_is_missing():
    """The original bug: importing the module killed the interpreter."""
    r = _run_probe()
    assert r.returncode == 0, (
        "importing sync_exclusions without `requests` must not exit "
        f"(returncode={r.returncode}).\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "IMPORTED_OK" in r.stdout


def test_import_does_not_build_an_http_session():
    """No I/O at import: the session must be built lazily, on first use."""
    r = _run_probe()
    assert "SESSION_BUILT False" in r.stdout, (
        "an HTTP session was constructed at import time.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )


def test_missing_requests_still_fails_loudly_at_point_of_use():
    """Deferring the failure must not swallow it."""
    probe = _PROBE.format(module_dir=str(MODULE_DIR)) + """
try:
    m.require_requests()
except RuntimeError as e:
    assert "requests" in str(e), e
    print("RAISED_OK")
else:
    raise AssertionError("require_requests() did not raise without requests")
"""
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, cwd=str(REPO_ROOT))
    assert "RAISED_OK" in r.stdout, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
