#!/usr/bin/env python3
"""Lint GitHub Actions workflows for unattended-reliability gaps.

Catches the classes of bug that make scheduled / auto-running jobs FAIL SILENTLY,
HANG, or CORRUPT shared state without anyone noticing — the gaps found in the
2026-06-01 CI reliability audit (docs/reviews/138*) and the April-2026 `ci.yml`
`| tail -30` incident (rules/verify-the-verifier.md):

  - no_failure_notify : a scheduled/auto workflow with NO `if: failure()` step
                        (a broken nightly run is invisible until someone looks)
  - no_timeout        : a job with no `timeout-minutes` (can hang to the 6h cap)
  - no_concurrency    : a scheduled workflow with no `concurrency:` group
                        (overlapping runs race on the same repo/CMS/state)
  - push_race         : `git push` with no `git pull --rebase` / retry nearby
                        (a concurrent push -> "failed to push some refs" -> red)
  - silent_pipe       : a run block piping to tail|head|grep|tee|sort WITHOUT
                        `set -o pipefail` / `${PIPESTATUS}` (lost exit code)
  - masked_failure    : `git push || echo ...` / `|| true` on a load-bearing cmd
  - missing_permissions: a workflow using GITHUB_TOKEN with no `permissions:` block

Stdlib only (text/regex; no PyYAML). Designed to run locally, in pre-commit, in
`system_inspector` (check_workflow_reliability), and as a CI job in BOTH the
monorepo and cagdasunal/cel.

Usage:
    lint_workflows.py [<workflows-dir> ...]   # default: <repo>/.github/workflows
    lint_workflows.py --json                  # machine-readable for system_inspector
    lint_workflows.py --strict                # exit 1 on medium+ (default: high+)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _run_blocks(text: str):
    """Yield (start_line, block_text) for each `run: |` / `run: >` multiline block."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(- )?run:\s*[|>]", lines[i])
        if m:
            indent = len(m.group(1)) + (2 if m.group(2) else 0)
            body, j = [], i + 1
            while j < len(lines):
                ln = lines[j]
                if ln.strip() == "":
                    body.append(ln)
                    j += 1
                    continue
                cur = len(ln) - len(ln.lstrip())
                if cur <= indent:
                    break
                body.append(ln)
                j += 1
            yield i + 1, "\n".join(body)
            i = j
            continue
        # single-line `run: cmd`
        m2 = re.match(r"^\s*(- )?run:\s*(\S.*)$", lines[i])
        if m2 and not m2.group(2).startswith(("|", ">")):
            yield i + 1, m2.group(2)
        i += 1


def _job_blocks(text: str):
    """Yield (job_name, start_line, block_text) for each job under `jobs:`."""
    lines = text.split("\n")
    # find `jobs:` at col 0
    try:
        js = next(i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*$", ln))
    except StopIteration:
        return
    i = js + 1
    cur_name, cur_start, cur = None, None, []
    for k in range(i, len(lines) + 1):
        ln = lines[k] if k < len(lines) else "ZZZ:"  # sentinel flush
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", ln)
        if m or k == len(lines):
            if cur_name is not None:
                yield cur_name, cur_start, "\n".join(cur)
            if k == len(lines):
                break
            cur_name, cur_start, cur = m.group(1), k + 1, []
        elif re.match(r"^\S", ln):  # dedent out of jobs:
            if cur_name is not None:
                yield cur_name, cur_start, "\n".join(cur)
            break
        elif cur_name is not None:
            cur.append(ln)


def lint_workflow(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    name = path.name
    findings = []

    def add(sev, cat, line, issue, fix):
        findings.append({"file": name, "line": line, "severity": sev,
                         "category": cat, "issue": issue, "fix": fix})

    is_scheduled = bool(re.search(r"^\s*schedule:\s*$", text, re.M)) and \
        bool(re.search(r"^\s*-?\s*cron:\s*['\"]", text, re.M))
    is_dispatch = "workflow_dispatch:" in text
    is_auto = is_scheduled or is_dispatch
    uses_token = bool(re.search(r"GITHUB_TOKEN|github\.token|secrets\.|gh \w|git push", text))

    # 1. failure notification (scheduled / auto only)
    if is_scheduled and not re.search(r"if:\s*\$?\{?\{?\s*failure\(\)", text):
        add("high", "no_failure_notify", 1,
            "scheduled workflow has no `if: failure()` step — a broken run is invisible",
            "add a final `- name: Notify on failure` step with `if: failure()` that "
            "creates/updates a ci-failure GitHub issue (gh issue create) or Slack ping")

    # 2. concurrency (scheduled only)
    if is_scheduled and "concurrency:" not in text:
        add("high", "no_concurrency", 1,
            "scheduled workflow has no `concurrency:` group — overlapping runs can race",
            "add a top-level `concurrency:` with a `group:` and `cancel-in-progress: false`")

    # 3. permissions present when using the token
    if uses_token and not re.search(r"^\s*permissions:\s*$", text, re.M):
        add("medium", "missing_permissions", 1,
            "workflow uses GITHUB_TOKEN/secrets but declares no `permissions:` block",
            "add a least-privilege `permissions:` block (e.g. contents: write, issues: write)")

    # 4. per-job timeout
    for jname, jline, jblock in _job_blocks(text):
        if "uses:" in jblock and "steps:" not in jblock:
            continue  # reusable-workflow call job — timeout not applicable
        if "timeout-minutes:" not in jblock:
            add("medium", "no_timeout", jline,
                f"job `{jname}` has no `timeout-minutes` — can hang to the 6h cap",
                "add `timeout-minutes: <N>` to the job (e.g. 20-30)")

    # 5. run-block level: silent pipes, masked failures, push race
    has_push = "git push" in text
    has_rebase = bool(re.search(r"pull\s+--rebase|--autostash", text))
    if has_push and not has_rebase:
        ln = next((i + 1 for i, l in enumerate(text.split("\n")) if "git push" in l), 1)
        add("high", "push_race", ln,
            "`git push` with no `git pull --rebase`/retry — a concurrent push fails the job",
            "wrap push in a 3-attempt loop: `for i in 1 2 3; do git push && break; "
            "git pull --rebase --autostash origin main || exit 1; done`")

    for bline, block in _run_blocks(text):
        # Only flag the exit-code-LOSING filters (tail/head/tee) — these mask the
        # upstream command's failure (the ci.yml `pytest | tail -30` bug). A
        # `... | grep -q`/`| jq` boolean/extract is a benign idiom, not flagged.
        piped = re.search(r"\|\s*(tail|head|tee)\b", block)
        if piped and not re.search(r"pipefail|PIPESTATUS", block):
            add("high", "silent_pipe", bline,
                "run block pipes a command to tail/head/tee without `set -o pipefail` "
                "— the upstream command's exit code is lost (the ci.yml `| tail -30` bug)",
                "add `set -euo pipefail` at the top of the run block, or capture "
                "`${PIPESTATUS[0]}` and exit on it")
        for ml in re.finditer(r"(git push|publish|deploy|--sync|--publish)[^\n]*\|\|\s*(echo|true)\b", block):
            add("high", "masked_failure", bline,
                f"load-bearing command masked with `|| {ml.group(2)}`: `{ml.group(0)[:60]}` "
                "— a real failure is swallowed and the job stays green",
                "remove the `|| echo/true`; let it fail, or handle the specific recoverable case explicitly")

    return findings


def find_workflow_dirs(args_dirs):
    if args_dirs:
        return [Path(d) for d in args_dirs]
    here = Path(__file__).resolve()
    for parent in here.parents:
        wf = parent / ".github" / "workflows"
        if wf.is_dir():
            return [wf]
    return [Path(".github/workflows")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint GitHub Actions workflows for reliability gaps.")
    ap.add_argument("dirs", nargs="*", help="workflow dirs (default: <repo>/.github/workflows)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on medium+ (default: high+)")
    args = ap.parse_args()

    all_findings = []
    files = []
    for d in find_workflow_dirs(args.dirs):
        files.extend(sorted(Path(d).glob("*.yml")) + sorted(Path(d).glob("*.yaml")))
    for f in files:
        all_findings.extend(lint_workflow(f))

    all_findings.sort(key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["file"], x["line"]))
    threshold = SEV_ORDER["medium"] if args.strict else SEV_ORDER["high"]
    blocking = [f for f in all_findings if SEV_ORDER.get(f["severity"], 9) <= threshold]

    if args.json:
        print(json.dumps({"files_scanned": len(files), "findings": all_findings,
                          "blocking": len(blocking)}, indent=2))
    else:
        if not all_findings:
            print(f"✅ {len(files)} workflow(s) clean — no reliability gaps.")
        for f in all_findings:
            print(f"  [{f['severity']:8}] {f['file']}:{f['line']} {f['category']}: {f['issue']}")
            print(f"             fix: {f['fix']}")
        print(f"\n{len(files)} scanned, {len(all_findings)} findings "
              f"({len(blocking)} blocking at {'medium' if args.strict else 'high'}+).")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
