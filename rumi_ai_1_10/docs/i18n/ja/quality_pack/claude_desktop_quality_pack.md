<!-- docs-i18n-links:start -->
[EN](../../../quality_pack/claude_desktop_quality_pack.md) | [JP](./claude_desktop_quality_pack.md) | [KR](../../ko/quality_pack/claude_desktop_quality_pack.md) | [CN](../../zh-cn/quality_pack/claude_desktop_quality_pack.md)
<!-- docs-i18n-links:end -->

# Claude rumi_ai 用デスクトップレベルの品質パック

このドキュメントは、rumi_ai を高品質で継続的に開発、監査、検証するための実践的なパックです。
**PR1 は高品質の資産を追加するだけであり、製品の動作は変更しません。**

---

## 1. パックの目的

1. 既存のテストと不足している領域を 1 つの操作手順に統合します。
2. 短時間で障害の切り分けと再現ができるようにする。
3. README/設計理念との一貫性を機械的にチェックします (えこひいきの禁止、フェイルソフト、悪意のある仮定、最小権限)。

---

## 2. 実行コマンド(推奨順序)

リポジトリのルートから実行します。

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

完全な監査モード (既存の従来の lint 負債を含む):

```bash
RUMI_FULL_QUALITY=1 bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
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
cd rumi_viewer/frontend && npm run lint && npm run build && cd ../..
cd pack-shell && cargo test && cd ..
```

---

## 3. 追加のテストが必要な領域

## 3.1 イデオロギーの適合性チェック
- 思考メモや品質パック文書の必須セクションの存在を確認する
- README/CI 定義規約が壊れていないかどうかを確認するための静的検証

## 3.2 CLI/バックエンドコントラクト
- ルートエントリポイント (`rumi_ai/__main__.py`) が `rumi_ai_1_10.app` に接続するコントラクト
- バージョンの調整 (`rumi_ai/__init__.py` および `rumi_ai_1_10/pyproject.toml`)

## 3.3 UI/Playwright に相当するもの (静的コントラクト)
- Tauri設定のCSPに`localhost:8765`を含める必要があります
- `connect-src` は、`https://` または `*` を許可しません。
- タイプチェック/ビルドスクリプトがフロントエンドパッケージに存在する必要があります

## 3.4 設定/権限/障害システム
- ルート pytest / パッケージ pytest / カーゴ テストは CI ワークフローで定義する必要があります
- リリース ワークフローには `v*` タグ トリガーと `cargo tauri build` があります。

---

## 4. 監査手順

1. 監査ログを確認する
   - `user_data/audit/security_YYYY-MM-DD.jsonl`
   - `user_data/audit/network_YYYY-MM-DD.jsonl`
   - `user_data/audit/permission_YYYY-MM-DD.jsonl`
2.承認状況の確認
   - 不正なパックは実行されていません
   - `modified` ステータス パックが再認証なしで実行されない
3. 権限を確認する
   - 機能付与とネットワーク付与は最小権限です
4. 失敗記録
   - 再現コマンド、期待値、実績値、影響範囲、回避策、恒久対策候補を残す

---

## 5. 手動検証手順 (最小セット)

1. 始動時の安全性
   - 厳密な起動: `python app.py`
- 開発開始：`python app.py --permissive` (許可条件の確認)
2.承認の流れ
   - パックスキャン -> 保留中 -> 承認/拒否 -> ステータス 遷移を確認
3. ネットワーク権限
   - 助成金がなければ拒否される
   - 付与 付与後に付与されるもの
4.ビューワ表示
   - ビューアはローカルホストパネルを表示できます
   - 外部 URL ガイダンスは CSP/権限によって制御されます

---

## 6. リグレッション確認手順

1. 既存CI(root/package/cargo)と同等のコマンドを実行
2. 追加された品質契約テストを実行する
3. lint/typecheck/build を渡す
4. 失敗した場合は「テスト実施の問題」か「製品のバグ」かを切り分ける
   - テスト実装の問題: PR1 で修正されました
   - 製品のバグ: PR2 候補として記録
   - 過去の糸くず債務: `RUMI_FULL_QUALITY=1` で検出し、段階的な返済計画を作成します

---

## 7. リリース前チェック

1. `.github/workflows/test.yml` および `release.yml` は現在の操作と一致します。
2. 追加のテストは緑色です
3. 監査/トラブルシューティング手順は最新のものである
4. セキュリティ モード (厳密/寛容) の説明は一貫しています。
5. ルート README および `rumi_ai_1_10/README.md` リンクは有効です

---

## 8. イデオロギーの互換性チェックリスト

- [ ] 特定のドメインの前提条件ロジックが公式コアで増加されていない (優遇なし)
- [ ] 部分故障時の継続動作（フェイルソフト）は壊れません。
- [ ] 悪意のあるパックに基づく承認、検証、隔離は弱まりません。
- [ ] 外部通信および危険な操作は、機能の範囲外に転用されません。
- [ ] 監査ログで追跡可能な実装を維持します。

---

## 9. 障害発生時の切り分け手順

1. どのゲートが失敗したかを分類する
   - ルート pytest / パッケージ pytest / ruff / mypy / フロントエンド lint-build / カーゴ テスト
2. 最小限の再生産
   - 単一のテスト ファイルまたは単一のコマンドに削減
3. 原因の分類
   - 設定の不一致
- テストの前提条件が不十分
   - 製品のバグ (PR2 の場合)
4. 影響評価
   - 重大度 (高/中/低)
   - 再現性（一定/条件付き）
- ユーザーへの影響 (セキュリティ/データ/UX)

---

## 10. AIエージェント操作プロンプト（操作テンプレート）

先頭に以下を追加して操作します。

```text
README・docs・思想メモを先に読み、No Favoritism / Fail-Soft / 悪意前提 / 最小権限を判断基準にする。
PR1では品質資産のみ、PR2で実害バグを修正する。
失敗時はテスト不備と製品バグを分離し、製品バグは再現条件と優先度付きで記録する。
全検証コマンドを実行し、結果をコマンド単位で報告する。
```

---

## 11. 既知の PR2 候補レコード テンプレート

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
