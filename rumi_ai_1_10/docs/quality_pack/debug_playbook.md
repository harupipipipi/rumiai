# quality debug playbook

品質ゲートが失敗したときに、層ごとに再現・切り分け・修正確認を行うための実務手順。

## 1. 失敗層の特定

1. `bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh` を実行。
2. `Quality gate summary` の失敗ゲート名を記録。
3. `rumi_ai_1_10/.quality_logs/<run_id>/summary.txt` と該当 `*.log` を確認。
4. ゲート名ごとに以下の再現コマンドへ移る。

## 2. ゲート別の最小再現コマンド

- root pytest
  - `python -m pytest tests -v`
- package pytest
  - `cd rumi_ai_1_10 && python -m pytest tests -v`
- frontend lint/build
  - `cd rumi_ai_1_10/frontend && npm run lint && npm run build`
- pack-shell
  - `cd pack-shell && cargo test`
- entrypoint contract
  - `python -m pytest tests/test_entrypoint_contracts.py -v`
- quality contracts（matrix系）
  - `cd rumi_ai_1_10 && python -m pytest tests/test_claude_quality_pack_contract.py tests/test_manual_regression_scenarios_contract.py tests/test_api_route_coverage_matrix_contract.py tests/test_frontend_ux_contract_matrix_contract.py tests/test_viewer_release_contract_matrix_contract.py tests/test_longrun_migration_contract_matrix_contract.py tests/test_security_permission_contract_matrix_contract.py tests/test_ui_viewer_recovery_contract_matrix_contract.py tests/test_runtime_boundary_contract_matrix_contract.py -v`
- viewer/release契約
  - `cd rumi_ai_1_10 && python -m pytest tests/test_viewer_release_contract_matrix_contract.py -v`
- longrun/migration契約
  - `cd rumi_ai_1_10 && python -m pytest tests/test_longrun_migration_contract_matrix_contract.py -v`
- security/permission契約
  - `cd rumi_ai_1_10 && python -m pytest tests/test_security_permission_contract_matrix_contract.py -v`
- ui/viewer recovery契約
  - `cd rumi_ai_1_10 && python -m pytest tests/test_ui_viewer_recovery_contract_matrix_contract.py -v`
- runtime boundary契約
  - `cd rumi_ai_1_10 && python -m pytest tests/test_runtime_boundary_contract_matrix_contract.py -v`

## 3. 典型デバッグ（frontend-lint）

1. `cd rumi_ai_1_10/frontend && npm run lint`
2. 型エラーのファイル/行を抽出して修正対象を列挙。
3. 修正後に `npm run lint` -> `npm run build` の順で再実行。
4. 最後に quality pack 全体を再実行して他層への副作用を確認。

## 4. 典型デバッグ（Python lint/type）

1. `cd rumi_ai_1_10 && python -m ruff check .`
2. `cd rumi_ai_1_10 && python -m ruff format --check .`
3. `cd rumi_ai_1_10 && python -m mypy`
4. ベースライン運用時は新規悪化のみ fail。悪化件数とファイルを記録して修正する。

## 5. セキュリティ/監査系の確認

1. `user_data/audit/security_*.jsonl` を確認。
2. `user_data/audit/network_*.jsonl` を確認。
3. `user_data/audit/permission_*.jsonl` を確認。
4. 未承認 Pack 実行、改変 Pack 再承認、grant 境界の逸脱がないことを確認。

## 6. 修正完了条件

1. 失敗していた最小再現コマンドが pass。
2. `run_claude_quality_pack.sh` の同一ゲートが pass。
3. 変更に応じた回帰テストを追加済み。
4. PR本文に再現方法、修正理由、残リスクを記載済み。
5. `manual_regression_scenarios*.yaml` の該当シナリオを更新済み。
