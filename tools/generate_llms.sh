#!/bin/bash

# ==============================================================================
# Script: generate_llms.sh
# Description: Generates llms.txt files from XML sitemaps using the llmstxt
#              NPM package. Supports multi-site via tools/sites.json config.
#
# Usage:
#   ./tools/generate_llms.sh                 # Process all sites
#   ./tools/generate_llms.sh --site <id>     # Process one site by ID
#   ./tools/generate_llms.sh --help          # Show help
# ==============================================================================

set -euo pipefail

# Make sure we can find npx and node
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Disable color output from Node.js to prevent ANSI codes in parsed values
export NO_COLOR=1
export NODE_DISABLE_COLORS=1

# --- Constants ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SITES_CONFIG="$SCRIPT_DIR/sites.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Helper Functions ---
log_info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

die() {
  log_error "$1"
  exit 1
}

print_usage() {
  cat << EOF
Usage: $(basename "$0") [OPTIONS]

Generates llms.txt context files from XML sitemaps.
Reads site configuration from tools/sites.json.

Options:
  --site <id>   Process only the site with this ID
  --all         Process all sites (default)
  -h, --help    Show this help message and exit

Sites config: $SITES_CONFIG
EOF
}

check_dependencies() {
  if ! command -v npx >/dev/null 2>&1; then
    die "npx is required but not installed. Please install Node.js."
  fi
  if ! command -v node >/dev/null 2>&1; then
    die "node is required but not installed. Please install Node.js."
  fi
  if [[ ! -f "$SITES_CONFIG" ]]; then
    die "Sites config not found: $SITES_CONFIG"
  fi
}

process_site() {
  local site_id="$1"
  local site_name="$2"
  local site_desc="$3"
  local sitemap_url="$4"          # URL fed to llmstxt (may be a CI-local override)
  local output_path="$5"
  local public_sitemap_url="$6"   # canonical public URL, advertised in the header

  local full_output="$REPO_ROOT/$output_path"

  log_info "Processing site: $site_name ($site_id)"
  log_info "  Sitemap: $sitemap_url"
  log_info "  Output:  $full_output"

  # Back up the existing good file BEFORE truncating, so a failed or degraded
  # generation can restore it (the truncate below would otherwise destroy it).
  local backup=""
  if [[ -f "$full_output" && -s "$full_output" ]]; then
    backup="${full_output}.bak"
    cp "$full_output" "$backup"
  fi

  # Truncate or create output file
  > "$full_output"

  # Write header
  {
    echo "# $site_name"
    echo ""
    echo "> $site_desc"
    echo ""
    echo "## Sitemaps"
    echo "- $public_sitemap_url"
    echo ""
    echo "---"
    echo ""
  } >> "$full_output"

  log_info "  Running llmstxt gen (this may take several minutes)..."

  # Run generator — append output to file. Capture stderr to a log (not
  # /dev/null) so silent failures are diagnosable; removed on success.
  local gen_err="${full_output}.genlog"
  if ! npx -y llmstxt gen "$sitemap_url" >> "$full_output" 2>"$gen_err"; then
    log_error "  llmstxt gen failed for $sitemap_url:"
    sed 's/^/    /' "$gen_err" >&2 || true
    rm -f "$gen_err"
    # Restore the previous good file if we backed one up
    if [[ -n "$backup" && -f "$backup" ]]; then
      mv "$backup" "$full_output"
      log_warn "  Generation failed — restored previous llms.txt"
    else
      rm -f "$full_output"
      log_error "  Failed to extract content from sitemap: $sitemap_url"
    fi
    return 1
  fi
  rm -f "$gen_err"

  # Demote any H1 the tool emitted to H2, then restore OUR H1 (the first line).
  # Portable in-place edit — GNU and BSD sed disagree on `-i`, so use a temp file.
  local tmp_fix
  tmp_fix=$(mktemp)
  if sed -e 's/^# /## /' -e '1s/^## /# /' "$full_output" > "$tmp_fix"; then
    mv "$tmp_fix" "$full_output"
  else
    rm -f "$tmp_fix"
  fi

  # Safety check: if output is suspiciously small (< 100 lines), the tool failed silently
  local line_count
  line_count=$(wc -l < "$full_output")
  if [[ "$line_count" -lt 100 ]]; then
    log_warn "  llmstxt produced only $line_count lines — likely failed silently"
    if [[ -n "$backup" && -f "$backup" ]]; then
      mv "$backup" "$full_output"
      log_warn "  Restored previous llms.txt ($(wc -l < "$full_output") lines)"
    fi
    return 1
  fi

  # Clean up backup
  rm -f "$backup"

  echo "" >> "$full_output"
  log_success "  Created: $full_output ($line_count lines)"
  return 0
}

# --- Parse Arguments ---
FILTER_SITE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    --site)
      FILTER_SITE="$2"
      shift 2
      ;;
    --all)
      FILTER_SITE=""
      shift
      ;;
    *)
      die "Unknown option: $1. Use --help for usage."
      ;;
  esac
done

# --- Main ---
check_dependencies

log_info "Reading sites from: $SITES_CONFIG"

# Helper: run node and strip any residual ANSI codes
node_val() {
  node -e "$1" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\r'
}

# Parse sites.json with node (available since we checked npx)
SITE_COUNT=$(node_val "const cfg = require('$SITES_CONFIG'); console.log(cfg.sites.length);")

if [[ "$SITE_COUNT" -eq 0 ]]; then
  die "No sites configured in $SITES_CONFIG"
fi

log_info "Found $SITE_COUNT site(s) in config."

# Validate --site up front — fail fast instead of looping over nothing.
if [[ -n "$FILTER_SITE" ]]; then
  FOUND=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites.some(s=>s.id==='$FILTER_SITE'))")
  if [[ "$FOUND" != "true" ]]; then
    die "Site '$FILTER_SITE' not found in config. Available: $(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites.map(s=>s.id).join(', '))")"
  fi
fi

ERRORS=0

for i in $(seq 0 $((SITE_COUNT - 1))); do
  SITE_ID=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites[$i].id)")
  SITE_NAME=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites[$i].name)")
  SITE_DESC=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites[$i].description)")
  PUBLIC_SITEMAP_URL=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites[$i].sitemap_url)")
  # LLMS_SITEMAP_URL is a CI-only override (e.g. http://localhost:8081/sitemap.xml)
  # that replaces the CDN URL so llms.txt is GENERATED from the freshly built
  # sitemap.xml rather than a stale CDN copy. It does NOT change the canonical
  # URL advertised in the llms.txt header — that stays PUBLIC_SITEMAP_URL.
  # WARNING: this override applies to ALL sites in the loop with the same URL.
  # If a second site is added to sites.json, use per-site env vars instead
  # (e.g. LLMS_SITEMAP_URL_<SITE_ID_UPPERCASE>) to avoid cross-site contamination.
  GEN_SITEMAP_URL="${LLMS_SITEMAP_URL:-$PUBLIC_SITEMAP_URL}"
  OUTPUT=$(node_val "const c=require('$SITES_CONFIG'); console.log(c.sites[$i].output)")

  # Filter if --site was specified
  if [[ -n "$FILTER_SITE" && "$SITE_ID" != "$FILTER_SITE" ]]; then
    continue
  fi

  if ! process_site "$SITE_ID" "$SITE_NAME" "$SITE_DESC" "$GEN_SITEMAP_URL" "$OUTPUT" "$PUBLIC_SITEMAP_URL"; then
    ERRORS=$((ERRORS + 1))
  fi
done

if [[ "$ERRORS" -gt 0 ]]; then
  log_error "$ERRORS site(s) failed. Check logs above."
  exit 1
fi

log_success "All sites processed successfully."
exit 0
