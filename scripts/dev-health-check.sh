#!/usr/bin/env bash
# dev-health-check.sh - Development environment health diagnostics
# MiMo V2.5 Pro - RumiAI Development Health Check
set -euo pipefail

JSON_MODE=false
[[ "${1:-}" == "--json" ]] && JSON_MODE=true

ISSUES=()
WARNINGS=()

check_pass() { echo "  ✓ $1"; }
check_fail() { echo "  ✗ $1"; ISSUES+=("$1"); }
check_warn() { echo "  ⚠ $1"; WARNINGS+=("$1"); }

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║       RumiAI Development Health Check (MiMo V2.5 Pro)    ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# --- Git ---
echo "▸ Git"
if git rev-parse --is-inside-work-tree &>/dev/null; then
  check_pass "Inside git repository"
else
  check_fail "Not inside a git repository"
fi

if git fsck --no-dangling --no-reflogs 2>&1 | grep -q "dangling\|missing\|error"; then
  check_warn "Repository integrity issues detected"
else
  check_pass "Repository integrity OK"
fi

REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
if [[ -n "$REMOTE_URL" ]]; then
  check_pass "Remote origin configured: ${REMOTE_URL}"
else
  check_warn "No remote origin configured"
fi

MERGE_CONFLICTS=$(git diff --name-only --diff-filter=U 2>/dev/null | head -5 || true)
if [[ -n "$MERGE_CONFLICTS" ]]; then
  check_fail "Unresolved merge conflicts: $MERGE_CONFLICTS"
else
  check_pass "No merge conflicts"
fi

# --- Toolchain ---
echo ""
echo "▸ Toolchain"
for cmd in python3 node docker make gh jq curl; do
  if command -v "$cmd" &>/dev/null; then
    check_pass "$cmd: $(command -v "$cmd")"
  else
    check_warn "$cmd: not found"
  fi
done

# --- Resources ---
echo ""
echo "▸ Resources"
DISK_AVAIL=$(df -h . 2>/dev/null | awk 'NR==2{print $4}' || echo "unknown")
check_pass "Disk available: $DISK_AVAIL"

# --- Network ---
echo ""
echo "▸ Network"
if curl -sf --max-time 5 https://github.com >/dev/null 2>&1; then
  check_pass "GitHub reachable"
else
  check_warn "GitHub unreachable (may be network/firewall issue)"
fi

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════════════════════"
ISSUE_COUNT=${#ISSUES[@]}
WARN_COUNT=${#WARNINGS[@]}

if [[ "$JSON_MODE" == "true" ]]; then
  printf '{"issues":%d,"warnings":%d,"status":"%s"}\n' \
    "$ISSUE_COUNT" "$WARN_COUNT" \
    "$( [[ $ISSUE_COUNT -eq 0 ]] && echo "pass" || echo "fail" )"
else
  if [[ $ISSUE_COUNT -eq 0 ]]; then
    echo "✅ HEALTH CHECK PASSED ($WARN_COUNT warning(s))"
  else
    echo "❌ HEALTH CHECK FAILED ($ISSUE_COUNT issue(s), $WARN_COUNT warning(s))"
  fi
fi

exit $ISSUE_COUNT
