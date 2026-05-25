"""(a) Regression baseline — the legacy + copywriter suite still passes at >= baseline.

Runs the non-stress suite in a SUBPROCESS (so it can't perturb this session's plugin
state) and reads the result from a JUnit XML report — NOT by scraping stdout. pytest 9.x
omits the trailing "N passed" line in `-q` runs to a pipe, so a regex over stdout silently
matched nothing; the XML `<testsuite>` counts are deterministic across pytest versions.

Two guards:
  * passed >= BASELINE_PASSED — catches accidental test loss during a refactor.
  * failures <= KNOWN_FAILURES — catches a NEW failure (the 2 known ones are the
    pre-existing tools/test_update_log.py sitemap-host assertions, OUT OF SCOPE).
Bump BASELINE_PASSED deliberately when the suite legitimately grows.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytestmark = pytest.mark.stress

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PASSED = 462   # legacy + copywriter non-stress subset (real count 464; small cushion). Bump on real growth.
KNOWN_FAILURES = 0      # suite is fully green (the test_update_log host asserts were corrected 2026-05-25).


def test_legacy_suite_passed_count_at_or_above_baseline(tmp_path):
    junit = tmp_path / "legacy-junit.xml"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tools/", "-m", "not stress",
         "-p", "no:cacheprovider", "-q", f"--junitxml={junit}"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    tail = (r.stdout + r.stderr)[-2000:]
    assert junit.exists(), f"no JUnit report written (pytest crashed before run?):\n{tail}"

    ts = ET.parse(junit).getroot()
    ts = ts if ts.tag == "testsuite" else ts.find("testsuite")
    tests = int(ts.attrib["tests"])
    failures = int(ts.attrib.get("failures", 0))
    errors = int(ts.attrib.get("errors", 0))
    skipped = int(ts.attrib.get("skipped", 0))
    passed = tests - failures - errors - skipped

    assert passed >= BASELINE_PASSED, (
        f"possible test loss: {passed} passed < baseline {BASELINE_PASSED} "
        f"(tests={tests} fail={failures} err={errors} skip={skipped})\n{tail}"
    )
    assert failures + errors <= KNOWN_FAILURES, (
        f"NEW failures beyond the {KNOWN_FAILURES} known: fail={failures} err={errors}\n{tail}"
    )
