#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FAST_QUALITY="${RUMI_FAST_QUALITY:-0}"
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
  run_gate "package-ruff" python -m ruff check .
  run_gate "package-ruff-format" python -m ruff format --check .
  run_gate "package-mypy" python -m mypy
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
