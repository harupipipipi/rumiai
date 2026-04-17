# test coverage matrix

rumi_ai の主要テストを運用観点で分類し、どの境界をどこで守るかを明示する。

| 分類 | 代表テスト | 狙い |
|---|---|---|
| unit | `tests/test_unit_gate.py` ほか | 低レベル関数や境界条件の壊れを早期検知 |
| integration | `tests/test_route_handlers.py`, `tests/test_egress_proxy.py` | 複数モジュール連携とAPI動作の整合を検証 |
| contract | `tests/test_entrypoint_contracts.py`, `tests/test_claude_quality_pack_contract.py` | README/CI/entrypoint/public契約の破壊を検知 |
| regression | `tests/test_wave*.py` 群 | 過去修正の再発を抑止 |
| CLI/backend | `tests/test_health.py`, `tests/test_phase_a_health.py` | 起動・ヘルス・CLI経路の運用継続性を検証 |
| frontend/UI | `tests/test_claude_quality_pack_contract.py`, `frontend lint/build` 実行 | 設定境界・ビルド破綻・型崩れの回帰検知 |
| security/permission | `tests/test_security_guards.py`, `tests/test_capability_*` | 最小権限・承認・ガード・能力境界の破壊を検知 |
| failure-path | `tests/test_wave20d_rate_limit.py`, `tests/test_security_guards.py` | 外部失敗・ガード失敗時の挙動を検証 |
| philosophy-alignment | `tests/test_claude_quality_pack_contract.py` | No Favoritism / Fail-Soft / 悪意Pack前提 / 最小権限を契約として維持 |

## 未テスト・薄い領域（優先順）

1. frontend の画面横断ルーティング（Setup -> Dashboard -> Packs -> Flows）の統合E2E
2. viewer 側の表示失敗時UX（CSP/localhost未接続時の回復導線）
3. strict/permissive を跨ぐ長時間運用時の監査ログ完全性（夜間ラン耐性）

## 継続運用ルール

1. 新機能を追加するときは、上表のどの分類に守りを追加するかをPR本文に明記する。
2. 修正PRは、最低1件の failure-path または regression テストを含める。
3. 重大修正は、contract と integration の両方で守る。
