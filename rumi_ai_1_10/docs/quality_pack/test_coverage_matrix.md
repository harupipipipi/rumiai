# test coverage matrix

rumi_ai の主要テストを運用観点で分類し、どの境界をどこで守るかを明示する。

| 分類 | 代表テスト | 狙い |
|---|---|---|
| unit | `tests/test_unit_gate.py` ほか | 低レベル関数や境界条件の壊れを早期検知 |
| integration | `tests/test_route_handlers.py`, `tests/test_egress_proxy.py` | 複数モジュール連携とAPI動作の整合を検証 |
| contract | `tests/test_entrypoint_contracts.py`, `tests/test_claude_quality_pack_contract.py`, `tests/test_quality_debug_playbook_contract.py`, `tests/test_manual_regression_scenarios_contract.py`, `tests/test_api_route_coverage_matrix_contract.py`, `tests/test_frontend_ux_contract_matrix_contract.py`, `tests/test_viewer_release_contract_matrix_contract.py`, `tests/test_longrun_migration_contract_matrix_contract.py` | README/CI/entrypoint/デバッグ手順/手動回帰台帳/API route網羅/frontend UX契約/viewer+release契約/longrun+migration契約の破壊を検知 |
| regression | `tests/test_wave*.py` 群 | 過去修正の再発を抑止 |
| CLI/backend | `tests/test_health.py`, `tests/test_phase_a_health.py`, `tests/test_wave20a_active_ecosystem_hmac.py` | 起動・ヘルス・migrate-hmac関連境界を含むCLI経路の運用継続性を検証 |
| frontend/UI | `tests/test_frontend_ux_contract_matrix_contract.py`, `tests/test_viewer_release_contract_matrix_contract.py`, `frontend_ux_contract_matrix.yaml`, `viewer_release_contract_matrix.yaml`, `frontend lint/build` 実行 | panel と viewer の状態遷移・DOM契約・導線・ビルド破綻の回帰検知 |
| security/permission | `tests/test_security_guards.py`, `tests/test_capability_*` | 最小権限・承認・ガード・能力境界の破壊を検知 |
| failure-path | `tests/test_wave20d_rate_limit.py`, `tests/test_security_guards.py` | 外部失敗・ガード失敗時の挙動を検証 |
| philosophy-alignment | `tests/test_claude_quality_pack_contract.py` | No Favoritism / Fail-Soft / 悪意Pack前提 / 最小権限を契約として維持 |

## 未テスト・薄い領域（優先順）

1. frontend の実ブラウザE2E（DOM契約に加えて操作遷移の自動再現）
2. strict/permissive を跨ぐ長時間運用時の監査ログ完全性（夜間ラン耐性）
3. viewer 主要操作の実ブラウザE2E（現在は契約テスト中心）

## 継続運用ルール

1. 新機能を追加するときは、上表のどの分類に守りを追加するかをPR本文に明記する。
2. 修正PRは、最低1件の failure-path または regression テストを含める。
3. 重大修正は、contract と integration の両方で守る。
