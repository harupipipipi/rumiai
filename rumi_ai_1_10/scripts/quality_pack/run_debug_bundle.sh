#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

echo "==> [debug] root entrypoint contracts"
cd "$ROOT_DIR"
python -m pytest tests/test_entrypoint_contracts.py -v

echo
echo "==> [debug] package quality contracts"
cd "$ROOT_DIR/rumi_ai_1_10"
python -m pytest \
  tests/test_claude_quality_pack_contract.py \
  tests/test_quality_debug_playbook_contract.py \
  tests/test_manual_regression_scenarios_contract.py \
  tests/test_api_route_coverage_matrix_contract.py \
  tests/test_frontend_ux_contract_matrix_contract.py \
  -v

echo
echo "==> [debug] frontend lint/build"
cd "$ROOT_DIR/rumi_ai_1_10/frontend"
npm run lint
npm run build

echo
echo "==> [debug] pack-shell tests"
cd "$ROOT_DIR/pack-shell"
cargo test

echo
echo "==> [debug] bundle complete"
