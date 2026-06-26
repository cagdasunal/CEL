#!/usr/bin/env bash
# PreToolUse WARN hook (never blocks) — warns when an edit writes `dry_run=False` into a .py file.
#
# Reads the PreToolUse payload as JSON on stdin (the stable hook contract) and inspects the edit
# content. Writing dry_run=False enables real spend / real Webflow writes — almost always you want a
# test to keep dry_run=True. This only WARNS (exit 0, message on stderr); it never denies, so a
# deliberate go-live or an `eval` real-model run is never blocked. CLAUDE.md rule 2 + CI stay the
# source of truth.
#
# Wired via .claude/settings.json PreToolUse (matcher Edit|Write|MultiEdit).
set -euo pipefail

payload="$(cat 2>/dev/null || true)"
[ -z "$payload" ] && exit 0

# Pull the target path + the new content, tolerating Edit/Write/MultiEdit shapes. python3 is always
# present here; jq may not be.
read -r path content <<EOF2
$(printf '%s' "$payload" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
ti=d.get("tool_input",{}) or {}
path=ti.get("file_path","") or ""
parts=[ti.get("new_string",""), ti.get("content","")]
for e in ti.get("edits",[]) or []:
    parts.append(e.get("new_string",""))
content=" ".join(p for p in parts if p)
print(path, content.replace("\n"," "))
' 2>/dev/null)
EOF2

case "$path" in
  *.py) ;;
  *) exit 0 ;;
esac

if printf '%s' "$content" | grep -Eq 'dry_run[[:space:]]*=[[:space:]]*False'; then
  echo "WARN: this edit writes 'dry_run=False' into $path — that enables REAL spend / Webflow writes." >&2
  echo "      Confirm it's a deliberate go-live, not a test edit. No-spend default is dry_run=True (CLAUDE.md rule 2)." >&2
fi
exit 0
