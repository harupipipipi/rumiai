# Claude Desktop-level quality pack for rumi_ai

このドキュメントは、rumi_ai を継続的に高品質で開発・監査・検証するための実務パックです。  
**PR1では品質資産のみを追加し、プロダクト挙動は変更しません。**

---

## 1. パックの目的

1. 既存テストと不足領域を一つの運用手順に統合する。
2. 失敗時の切り分けを短時間で再現可能にする。
3. README/設計思想（No Favoritism, Fail-Soft, 悪意前提, 最小権限）との整合を機械的に点検する。

---

## 2. 実行コマンド（推奨順）

リポジトリルートから実行:

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

高速モード（局所確認のみ。既定はフル監査）:

```bash
RUMI_FAST_QUALITY=1 bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

デバッグ用の再現バンドル（失敗層を素早く切り分ける）:

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_debug_bundle.sh
```

既定フル監査では、repo-wide lint/type の既存負債を **ベースライン比較** で判定します。  
現状値を超えた場合のみ fail させ、負債を隠さず非退行を保証します。

```bash
RUMI_BASELINE_RUFF_ERRORS=1194 \
RUMI_BASELINE_RUFF_FORMAT_FILES=835 \
RUMI_BASELINE_MYPY_ERRORS=660 \
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

実行ログの保存先を変更する場合:

```bash
RUMI_QUALITY_LOG_DIR=/tmp/rumi_quality_logs \
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

個別実行:

```bash
# root (version-stable entrypoint) テスト
python -m pytest tests -v

# package テスト
cd rumi_ai_1_10
python -m pytest tests -v

# 追加した品質契約テストのみ
python -m pytest tests/test_claude_quality_pack_contract.py -v
cd ..
python -m pytest tests/test_entrypoint_contracts.py -v

# Python 品質ゲート
cd rumi_ai_1_10
python -m ruff check tests/test_claude_quality_pack_contract.py
python -m ruff format --check tests/test_claude_quality_pack_contract.py
python -m mypy tests/test_claude_quality_pack_contract.py
cd ..
python -m ruff check tests/test_entrypoint_contracts.py
python -m ruff format --check tests/test_entrypoint_contracts.py
python -m mypy tests/test_entrypoint_contracts.py

# Frontend/Viewer/Pack-shell
cd rumi_ai_1_10/frontend && npm run lint && npm run build && cd ../..
cd pack-shell && cargo test && cd ..
```

---

## 3. 追加テストの対象領域

## 3.1 思想適合チェック
- 思想メモと品質パック文書の必須セクション存在チェック
- README/CI定義の契約が崩れていないかを静的検証

## 3.2 CLI / バックエンド契約
- root entrypoint (`rumi_ai/__main__.py`) が `rumi_ai_1_10.app` へ接続する契約
- バージョン整合 (`rumi_ai/__init__.py` と `rumi_ai_1_10/pyproject.toml`)

## 3.3 UI / Playwright相当（設定・ビルド・契約）
- frontend build/lint を実行し、型崩れ・依存崩れ・ビルド破綻を検知
- `tests/test_frontend_build_config.py` で tsconfig / Tailwind の設定境界を検証
- Tauri 設定のCSPに `localhost:8765` が含まれ、`connect-src` が `https://` や `*` を許可していないこと

## 3.4 設定 / 権限 / 失敗系
- CI workflow に root pytest / package pytest / cargo test が定義されていること
- release workflow が `v*` tag trigger と `cargo tauri build` を持つこと

## 4. 監査手順

1. 監査ログ確認
   - `user_data/audit/security_YYYY-MM-DD.jsonl`
   - `user_data/audit/network_YYYY-MM-DD.jsonl`
   - `user_data/audit/permission_YYYY-MM-DD.jsonl`
2. 承認状態確認
   - 未承認Packが実行されていないこと
   - `modified` 状態Packが再承認なしで動いていないこと
3. 権限確認
   - capability grant と network grant が最小権限であること
4. 失敗時記録
   - 再現コマンド、期待値、実値、影響範囲、回避策、恒久対策候補を残す

---

## 5. 手動検証手順（最小セット）

1. 起動安全性
   - strict 起動: `python app.py`
   - 開発起動: `python app.py --permissive`（許可条件の確認）
2. 承認フロー
   - Pack scan -> pending -> approve/reject -> status 遷移確認
3. ネットワーク権限
   - grant 無しで拒否されること
   - grant 付与後に許可されること
4. Viewer表示
   - Viewer が localhost panel を表示できること
   - 外部URL誘導がCSP/権限で制御されること

---

## 6. 回帰確認手順

1. 既存CI相当コマンド（root/package/cargo）を実行
2. 追加した品質契約テストを実行
3. lint/typecheck/build を通す
4. 失敗した場合は「テスト実装問題」か「製品バグ」かを分離する
   - テスト実装問題: PR1内で修正
   - 製品バグ: PR2候補へ記録
   - レガシーlint負債: ベースライン管理で非退行を保証し、段階的に返済計画を作る

---

## 7. リリース前チェック

1. `.github/workflows/test.yml` と `release.yml` が現行運用と一致
2. 追加テストが green
3. 監査/トラブルシュート手順が最新
4. セキュリティモード（strict/permissive）の説明が矛盾していない
5. root README と `rumi_ai_1_10/README.md` のリンクが有効

---

## 8. 思想適合チェックリスト

- [ ] 公式コアに特定ドメイン前提ロジックを増やしていない（No Favoritism）
- [ ] 部分故障時の継続運用（Fail-Soft）を壊していない
- [ ] 悪意Pack前提の承認・検証・隔離を弱めていない
- [ ] 外部通信や危険操作をCapability外へ迂回させていない
- [ ] 監査ログで追跡可能な実装を維持している

---

## 9. 失敗時の切り分け手順

1. どのゲートで失敗したか分類
   - root pytest / package pytest / ruff / mypy / frontend lint-build / cargo test
   - 実行ログ: `rumi_ai_1_10/.quality_logs/<run_id>/summary.txt` と各 `*.log`
2. 最小再現
   - 単一テストファイルや単一コマンドに縮小
3. 原因分類
   - 設定不整合
   - テスト想定不備
   - 製品バグ（PR2対象）
4. 影響評価
   - 重大度（高/中/低）
   - 再現性（常時/条件付き）
   - ユーザー影響（セキュリティ/データ/UX）

---

## 10. AIエージェント運用プロンプト（運用テンプレート）

以下を冒頭に付けて運用する:

```text
README・docs・思想メモを先に読み、No Favoritism / Fail-Soft / 悪意前提 / 最小権限を判断基準にする。
PR1では品質資産のみ、PR2で実害バグを修正する。
失敗時はテスト不備と製品バグを分離し、製品バグは再現条件と優先度付きで記録する。
全検証コマンドを実行し、結果をコマンド単位で報告する。
```

---

## 11. 既知のPR2候補記録テンプレート

```text
- 事象:
- 再現手順:
- 期待挙動:
- 実際の挙動:
- 重大度:
- 再現性:
- ユーザー影響:
- 思想逸脱:
```

---

## 12. 分類表・再評価ログ

- テスト分類表: `docs/quality_pack/test_coverage_matrix.md`
- 思想再評価ログ: `docs/quality_pack/philosophy_re_evaluation_log.md`
- デバッグ手順: `docs/quality_pack/debug_playbook.md`
