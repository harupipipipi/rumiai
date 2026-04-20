#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FULL_QUALITY="${RUMI_FULL_QUALITY:-0}"

run() {
  echo
  echo "==> $*"
  "$@"
}

cd "$ROOT_DIR"

run python -m pytest tests -v

cd "$ROOT_DIR/rumi_ai_1_10"
run python -m pytest tests -v
run python -m pytest tests/test_claude_quality_pack_contract.py -v

if [[ "$FULL_QUALITY" == "1" ]]; then
  run python -m ruff check .
  run python -m ruff format --check .
  run python -m mypy
else
  run python -m ruff check tests/test_claude_quality_pack_contract.py
  run python -m ruff format --check tests/test_claude_quality_pack_contract.py
  run python -m mypy tests/test_claude_quality_pack_contract.py
fi

cd "$ROOT_DIR"
run python -m ruff check tests/test_entrypoint_contracts.py
run python -m ruff format --check tests/test_entrypoint_contracts.py
run python -m mypy tests/test_entrypoint_contracts.py

cd "$ROOT_DIR/rumi_ai_1_10/frontend"
run npm run lint
run npm run build

cd "$ROOT_DIR/pack-shell"
run cargo test
