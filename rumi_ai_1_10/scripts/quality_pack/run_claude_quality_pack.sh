#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FAST_QUALITY="${RUMI_FAST_QUALITY:-0}"
BASELINE_RUFF_ERRORS="${RUMI_BASELINE_RUFF_ERRORS:-1194}"
BASELINE_RUFF_FORMAT_FILES="${RUMI_BASELINE_RUFF_FORMAT_FILES:-835}"
BASELINE_MYPY_ERRORS="${RUMI_BASELINE_MYPY_ERRORS:-660}"
declare -a FAILURES=()

run_gate() {
  local gate="$1"
  shift
  echo
  echo "==> [$gate] $*"
  if "$@"; then
    echo "✅ [$gate] PASS"
  else
    echo "❌ [$gate] FAIL"
    FAILURES+=("$gate")
  fi
}

run_gate_with_baseline() {
  local gate="$1"
  local baseline="$2"
  local parse_pattern="$3"
  shift 3

  echo
  echo "==> [$gate] $*"

  local out_file
  out_file="$(mktemp)"
  "$@" >"$out_file" 2>&1
  local exit_code=$?
  cat "$out_file"

  if [[ $exit_code -eq 0 ]]; then
    echo "✅ [$gate] PASS"
    rm -f "$out_file"
    return
  fi

  local count
  count="$(grep -Eo "$parse_pattern" "$out_file" | tail -n 1 | grep -Eo '[0-9]+' | head -n 1)"
  rm -f "$out_file"

  if [[ -n "${count:-}" ]] && [[ "$count" -le "$baseline" ]]; then
    echo "⚠️ [$gate] BASELINE-ACCEPTED (current=$count baseline=$baseline)"
    return
  fi

  echo "❌ [$gate] FAIL"
  FAILURES+=("$gate")
}

cd "$ROOT_DIR"
run_gate "root-pytest" python -m pytest tests -v

cd "$ROOT_DIR/rumi_ai_1_10"
run_gate "package-pytest" python -m pytest tests -v
run_gate "quality-contract-pytest" python -m pytest tests/test_claude_quality_pack_contract.py -v

if [[ "$FAST_QUALITY" == "1" ]]; then
  run_gate "package-ruff-targeted" python -m ruff check tests/test_claude_quality_pack_contract.py
  run_gate "package-ruff-format-targeted" python -m ruff format --check tests/test_claude_quality_pack_contract.py
  run_gate "package-mypy-targeted" python -m mypy tests/test_claude_quality_pack_contract.py
else
  run_gate_with_baseline "package-ruff" "$BASELINE_RUFF_ERRORS" "Found [0-9]+ errors\\." python -m ruff check .
  run_gate_with_baseline "package-ruff-format" "$BASELINE_RUFF_FORMAT_FILES" "[0-9]+ files would be reformatted" python -m ruff format --check .
  run_gate_with_baseline "package-mypy" "$BASELINE_MYPY_ERRORS" "Found [0-9]+ errors in [0-9]+ files" python -m mypy
fi

cd "$ROOT_DIR"
run_gate "entrypoint-contracts-pytest" python -m pytest tests/test_entrypoint_contracts.py -v
run_gate "entrypoint-contracts-ruff" python -m ruff check tests/test_entrypoint_contracts.py
run_gate "entrypoint-contracts-ruff-format" python -m ruff format --check tests/test_entrypoint_contracts.py
run_gate "entrypoint-contracts-mypy" python -m mypy tests/test_entrypoint_contracts.py

cd "$ROOT_DIR/rumi_ai_1_10/frontend"
run_gate "frontend-lint" npm run lint
run_gate "frontend-build" npm run build

cd "$ROOT_DIR/pack-shell"
run_gate "pack-shell-tests" cargo test

echo
echo "==> Quality gate summary"
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  echo "✅ all gates passed"
  exit 0
fi

echo "❌ failed gates:"
for gate in "${FAILURES[@]}"; do
  echo " - $gate"
done
exit 1
