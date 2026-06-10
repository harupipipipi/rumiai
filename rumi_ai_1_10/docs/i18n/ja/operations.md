<!-- docs-i18n-links:start -->
[EN](../../operations.md) | [JP](./operations.md) | [KR](../ko/operations.md) | [CN](../zh-cn/operations.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 操作ガイド

オペレーター向けのガイドです。全体的な設計については [architecture.md](./architecture.md) を、パックの開発については [pack-development.md](./pack-development.md) を参照してください。

---

## 目次

1. [セットアップ](#セットアップ)
2. [スタート](#スタート)
3. [セキュリティモード](#セキュリティモード)
4. [HTTP API 概要](#http-apiの概要)
5. [パック承認管理](#パック承認管理)
6. [ネットワーク権限管理](#network-privilege-management)
7. [能力ハンドラーの承認](#capability-handler-approval)
8. [能力付与管理](#能力付与管理)
9. [pip依存ライブラリ管理](#pip-dependency-library-management)
10. [秘密管理](#機密管理)
11. [Pack Import / Apply](#pack-import--apply)
12. [共同店舗運営](#共同店舗運営)
13. [Docker / Container management](#docker--container-management)
14. [フロー実行](#フローの実行)
15. [権限管理](#権限管理)
16. [UDSソケット設定](#udsソケット設定)
17. [監査ログの見方](#監査ログの読み方)
18. [エクスポート保留中](#エクスポート保留中)
19. [認証トークン](#認証トークン)
20. [構造化ログ設定](#構造化ログ設定)
21. [非推奨の警告レベル制御](#非推奨警告レベルの制御)
22. [ヘルスチェック操作](#ヘルスチェック動作)
23. [メトリクスの確認](#メトリクスを確認する)
24. [パックテンプレート生成(足場)](#パックテンプレートの生成（足場）)
25. [エラーコードリファレンス](#エラーコードリファレンス)
26. [環境変数リファレンス](#環境変数の参照)
27. [トラブルシューティング](#トラブルシューティング)

---

## セットアップ

### 要件

- Python 3.10+
- Docker (本番環境に必要)
- Git

### インストール

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10

# セットアップ（CLI）
python bootstrap.py --cli init

# または手動
pip install -r requirements.txt
```

### セットアップツール

セットアップ ツールは、CLI と Web の 2 つのインターフェイスを提供します。

```bash
# CLI モード
python bootstrap.py --cli              # 対話メニュー
python bootstrap.py --cli check        # 環境チェック
python bootstrap.py --cli init         # 初期セットアップ
python bootstrap.py --cli doctor       # 診断
python bootstrap.py --cli recover      # リカバリー
python bootstrap.py --cli run          # アプリ起動

# Web モード
python bootstrap.py --web              # ブラウザ操作（デフォルトポート 8080）
python bootstrap.py --web --port 9000  # ポート指定
```

セットアップ ツールは、Python / Git / Docker のチェック、仮想環境 (.venv) の作成、依存関係のインストール、user_data ディレクトリの初期化、およびデフォルト パック (オプション) のインストールを自動化します。

---

## 開始

```bash
# 本番環境（Docker 必須）
python app.py

# 開発環境（Docker 不要）
python app.py --permissive

# ヘッドレスモード
python app.py --headless

# ヘルスチェック実行
python app.py --health

# Pack バリデーション実行
python app.py --validate
```

`--health` はヘルスチェックを実行し、結果を JSON で stdout に出力して終了します。ステータスが `"UP"` の場合、終了コードは 0 です。それ以外の場合、終了コードは 1 です。組み込みプローブには、disk (ディスク空き領域) および writable_tmp (`/tmp` 書き込み可能性) が含まれます。 CI/CDやコンテナオーケストレーションのヘルスチェックに使用できます。

`--validate` はパック検証を実行し、結果を出力して終了します。

---

## セキュリティモード

環境変数`RUMI_SECURITY_MODE`で設定します。

|モード |ドッカー |行動 |
|--------|--------|------|
| `strict` (デフォルト) |必須 | Docker が利用できない場合は実行を拒否 |
| `permissive` |不要 |警告付きでホストの実行を許可する |

```bash
# 本番
export RUMI_SECURITY_MODE=strict

# 開発
export RUMI_SECURITY_MODE=permissive
```

---

## HTTP API の概要

すべてのエンドポイントには `Authorization: Bearer YOUR_TOKEN` が必要です。

### パック管理

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/packs` |全パックのリスト |
|入手 | `/api/packs/pending` |承認待ちのパックのリスト |
|入手 | `/api/packs/{pack_id}/status` |パックのステータスを取得 |
|投稿 | `/api/packs/scan` |パックスキャン |
|投稿 | `/api/packs/{pack_id}/approve` |パックの承認 |
|投稿 | `/api/packs/{pack_id}/reject` |パックが拒否されました |
|投稿 | `/api/packs/import` |パックのインポート |
|投稿 | `/api/packs/apply` |パック適用 |
|削除 | `/api/packs/{pack_id}` |パックのアンインストール |

### ネットワーク権限

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/network/list` |すべての助成金のリスト |
|投稿 | `/api/network/grant` |ネットワーク権限を付与する |
|投稿 | `/api/network/revoke` |ネットワーク権限を取り消す |
|投稿 | `/api/network/check` |アクセスを確認する |

### ケイパビリティハンドラー候補

|方法 |パス |説明 |
|----------|------|------|
|投稿 | `/api/capability/candidates/scan` |候補スキャン |
|入手 | `/api/capability/requests?status=pending` |アプリケーションリスト |
|投稿 | `/api/capability/requests/{key}/approve` |認可 (信頼 + コピー) |
|投稿 | `/api/capability/requests/{key}/reject` |拒否されました |
|入手 | `/api/capability/blocked` |ブロックリスト |
|投稿 | `/api/capability/blocked/{key}/unblock` |ブロックを解除 |

### 能力付与

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/capability/grants?principal_id=xxx` |助成金リスト |
|投稿 | `/api/capability/grants/grant` |助成金 |
|投稿 | `/api/capability/grants/revoke` |付与を取り消す |
|投稿 | `/api/capability/grants/batch` |一括付与（最大50件） |

### pip 依存ライブラリ

|方法 |パス |説明 |
|----------|------|------|
|投稿 | `/api/pip/candidates/scan` |候補スキャン |
|入手 | `/api/pip/requests?status=pending` |アプリケーションリスト |
|投稿 | `/api/pip/requests/{key}/approve` |承認 + インストール |
|投稿 | `/api/pip/requests/{key}/reject` |拒否されました |
|入手 | `/api/pip/blocked` |ブロックリスト |
|投稿 | `/api/pip/blocked/{key}/unblock` |ブロックを解除 |

### 秘密

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/secrets` |キーリスト (値はマスクされます) |
|投稿 | `/api/secrets/set` |シークレット値を設定する |
|投稿 | `/api/secrets/delete` |シークレット値を削除 |

### フローの実行

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/flows` |登録済みフロー一覧 |
|投稿 | `/api/flows/{flow_id}/run` |実行フロー |

###ストア

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/stores` |店舗一覧 |
|投稿 | `/api/stores/create` |ストアの作成 |
|入手 | `/api/stores/shared` |共通店舗一覧 |
|投稿 | `/api/stores/shared/approve` |共有ストアの承認 |
|投稿 | `/api/stores/shared/revoke` |共用店舗キャンセル |

### ユニット

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/units?store_id=xxx` |ユニット一覧 |
|投稿 | `/api/units/publish` |ユニットの発行 |
|投稿 | `/api/units/execute` |実行ユニット |

### 特権

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/privileges` |権限リスト |
|投稿 | `/api/privileges/{pack_id}/grant/{privilege_id}` |特権付与 |
|投稿 | `/api/privileges/{pack_id}/execute/{privilege_id}` |特権実行 |

### オリジナルルートをパックする

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/routes` |登録路線一覧 |
|投稿 | `/api/routes/reload` |ルート テーブルをリロードする |

### ドッカー/コンテナ

|方法 |パス |説明 |
|----------|------|------|
|入手 | `/api/docker/status` | Docker の可用性 |
|入手 | `/api/containers` |コンテナリスト |
|投稿 | `/api/containers/{pack_id}/start` |コンテナの開始 |
|投稿 | `/api/containers/{pack_id}/stop` |コンテナを停止 |
|削除 | `/api/containers/{pack_id}` |コンテナの削除 |

---

## パック承認管理

### 承認待ちのチェック

```bash
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### パックの承認

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### パック拒否

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'
```

### 再認証 (変更された状態でパック)

ファイル変更によりハッシュの不一致が生じた場合、ファイルは `modified` 状態になり、自動的に無効になります。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## ネットワーク権限管理

### 助成金 助成金

```bash
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "my_pack",
    "allowed_domains": ["api.openai.com", "*.anthropic.com"],
    "allowed_ports": [443]
  }'
```

### 助成金一覧

```bash
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### アクセスチェック

```bash
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.openai.com", "port": 443}'
```

### 付与の取り消し

```bash
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'
```

---

## 機能ハンドラーの承認

> **注意**: core_pack によって提供される関数 (store / Secrets / flow / communication / docker) は、この候補導入ワークフローを経由せず、カーネルの起動時に FunctionRegistry に自動的に登録されます。ユーザー パックに含まれるカスタム機能ハンドラーには、次の候補導入ワークフロー (スキャン → 承認 → 付与) が適用されます。

Capability ハンドラーは 2 段階の操作で使用可能になります。

1. **信頼登録** (ハンドラー承認): スキャンによって検出された候補を承認し、ハンドラー コード (sha256) を信頼済みとして登録します。
2. **Grant** (権限付与): 承認されたハンドラーの権限をパックに付与します。

```
候補スキャン (scan)
    ↓
pending（承認待ち）
    ↓
approve → Trust 登録 + コピー + Registry reload
    ↓
Grant 付与（principal × permission）
    ↓
Pack が capability を使用可能
```

候補は、スキャン→保留中→承認/拒否→ブロックという状態遷移に従います。

### 候補者をスキャンする

```bash
curl -X POST http://localhost:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 承認待ちリスト

```bash
curl "http://localhost:8765/api/capability/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### スキャン応答

候補スキャン後の応答の例:

```json
{
  "success": true,
  "data": {
    "scanned": 3,
    "new_candidates": 2,
    "candidates": [
      {
        "candidate_key": "my_pack:fs_read_v1:fs_read_handler:a1b2c3d4e5f6...",
        "pack_id": "my_pack",
        "slug": "fs_read_v1",
        "handler_id": "fs_read_handler",
        "permission_id": "fs.read",
        "sha256": "a1b2c3d4e5f6...",
        "status": "pending",
        "description": "ファイルシステム読み取り handler",
        "risk": "ファイルシステムへの読み取りアクセスを提供"
      }
    ]
  }
}
```

`candidate_key`の形式は`{pack_id}:{slug}:{handler_id}:{sha256}`となります。 sha256を含めることでhandler.pyの内容が変わった場合は別候補として扱われます。

### 候補者の承認

`candidate_key`に含まれる`:`にはURLエンコードが必要です。

```bash
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123..."

curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

承認は信頼を登録します (sha256 ホワイトリスト) + `user_data/capabilities/handlers/` にコピー + レジストリをリロードします。実際の利用には別途助成金が必要となります。

### 候補者の拒否

```bash
curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なファイルシステムアクセス"}'
```

1 回目と 2 回目の使用には `rejected` (クールダウン 1 時間)、3 回目の使用には `blocked` がかかります。

### ブロックを解除する

```bash
curl -X POST "http://localhost:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## 能力付与管理

機能ハンドラーが承認された後、パックが実際に機能を使用するには、許可 (プリンシパル × 許可) が必要です。

### 助成金 助成金

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 助成金一覧

```bash
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 付与の取り消し

```bash
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 一括（バッチ）で付与する

一度に最大 50 件の補助金を付与します。処理はベストエフォート型です (個々の失敗によって他の許可が妨げられることはありません)。

```bash
curl -X POST http://localhost:8765/api/capability/grants/batch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "grants": [
      {"principal_id": "pack_a", "permission_id": "store.get"},
      {"principal_id": "pack_a", "permission_id": "store.set"},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "config": {"allowed_keys": ["API_KEY"]}}
    ]
  }'
```

|パラメータ |必須 |説明 |
|-----------|------|------|
| `grants` | ✅ | Grant オブジェクトの配列 (最大 50) |
| `grants[].principal_id` | ✅ |ターゲット パック ID |
| `grants[].permission_id` | ✅ |認証ID |
| `grants[].config` |オプション |付与設定(`allowed_keys`など) |

応答例:

```json
{
  "success": true,
  "data": {
    "total": 3,
    "succeeded": 3,
    "failed": 0,
    "results": [
      {"principal_id": "pack_a", "permission_id": "store.get", "success": true},
      {"principal_id": "pack_a", "permission_id": "store.set", "success": true},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "success": true}
    ]
  }
}
```

### 全体の流れ

```
1. capability handler 候補をスキャン
   POST /api/capability/candidates/scan

2. 候補を承認（Trust 登録 + コピー）
   POST /api/capability/requests/{key}/approve

3. Grant を付与（principal × permission）
   POST /api/capability/grants/grant

4. Pack が capability を使用可能に
```

---

## pip 依存のライブラリ管理

これは、パックの pip 依存関係をスキャン→承認→インストールするワークフローです。

### 候補者をスキャンする

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 承認待ちリスト

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 承認(インストール実行)

`candidate_key` では URL エンコードが必要です。

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123...', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

デフォルトはホイールのみ (`--only-binary=:all:`) です。ホイールに存在しないパッケージが含まれる場合は`"allow_sdist": true`をご指定ください。

### 拒否されました

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

1 回目と 2 回目の使用には `rejected` (クールダウン 1 時間)、3 回目の使用には `blocked` がかかります。

### ブロックを解除する

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

### 前提条件

パックは承認された状態であると想定されます。未承認のパックの依存関係のある展開は、厳密モードでは拒否されます。

---

## 秘密の管理

### キーリスト (値はマスクされています)

```bash
curl http://localhost:8765/api/secrets \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### シークレット値の設定

```bash
curl -X POST http://localhost:8765/api/secrets/set \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY", "value": "sk-..."}'
```

### シークレット値を削除する

```bash
curl -X POST http://localhost:8765/api/secrets/delete \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY"}'
```

シークレット値は `user_data/secrets/` に 1 キー = 1 ファイルで格納されます。 APIを使用して再表示することはできません（設定と削除のみ）。シークレット値はログに出力されません。

### 暗号化

シークレット値は、Fernet (AES-128-CBC + HMAC-SHA256) を使用して暗号化されて保存されます。暗号化キーは次の優先順位で取得されます。

1. 環境変数 `RUMI_SECRETS_KEY` (Base64 エンコードされた Fernet キー)
2. `user_data/settings/.secrets_key` ファイル
3. 上記のいずれも存在しない場合は、キーを自動的に生成し、`.secrets_key` に保存します。

### キーのバックアップ

暗号化キーを紛失すると、既存のシークレット値を復号化できなくなります。 `user_data/settings/.secrets_key`を安全な場所にバックアップしてください。環境変数 `RUMI_SECRETS_KEY` を使用して外部でキーを管理する場合にもバックアップが必要です。

### 平文モード

`RUMI_SECRETS_ALLOW_PLAINTEXT` を使用して、暗号化されていないストレージを制御できます。

|値 |行動 |
|-----|------|
| `auto` (デフォルト) |暗号化キーが利用可能な場合は暗号化します。利用できない場合はプレーン テキストとして保存します。
| `true` |常にプレーン テキストでの保存を許可する |
| `false` |暗号化キーが必要です。キーが欠落している場合はシークレット値の保存を拒否する |

実稼働環境には `RUMI_SECRETS_ALLOW_PLAINTEXT=false` が推奨されます。

---

## パックのインポート/適用

### インポート (ステージングへ)

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

フォルダー / `.zip` / `.rumipack` (zip 互換) をサポートします。

### 適用 (ステージングからエコシステムに適用)

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

適用中にバックアップが自動的に作成されます。 `pack_id` および `pack_identity` が既存のパックと一致しない場合、そのパックは拒否されます。

---

## 共有ストア管理

パック間でストアを共有するための管理 API。共有リクエストには手動の承認が必要です (SharedStoreManager)。

### 共有店舗一覧

```bash
curl http://localhost:8765/api/stores/shared \
  -H "Authorization: Bearer YOUR_TOKEN"
```

応答例:

```json
{
  "success": true,
  "data": {
    "shared_stores": [
      {
        "store_id": "shared_data",
        "owner_pack": "pack_a",
        "shared_with": ["pack_b", "pack_c"],
        "status": "approved",
        "approved_at": "2026-01-15T10:00:00Z"
      }
    ]
  }
}
```

### 共有ストアの承認

```bash
curl -X POST http://localhost:8765/api/stores/shared/approve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

|パラメータ |必須 |説明 |
|-----------|------|------|
| `store_id` | ✅ |共有するストアID |
| `owner_pack` | ✅ |ストア所有のパック ID |
| `target_pack` | ✅ |共有するパック ID |

応答例:

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b",
    "status": "approved",
    "approved_at": "2026-01-15T10:00:00Z"
  }
}
```

### 共有ストアのキャンセル

```bash
curl -X POST http://localhost:8765/api/stores/shared/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

|パラメータ |必須 |説明 |
|-----------|------|------|
| `store_id` | ✅ |対象ストアID |
| `owner_pack` | ✅ |ストア所有のパック ID |
| `target_pack` | ✅ |パック ID の共有をキャンセル |

応答例:

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "target_pack": "pack_b",
    "status": "revoked"
  }
}
```

---

## Docker / コンテナ管理

### Docker のステータスを確認する

```bash
curl http://localhost:8765/api/docker/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### コンテナリスト

```bash
curl http://localhost:8765/api/containers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### コンテナの起動/停止

```bash
# 起動
curl -X POST http://localhost:8765/api/containers/{pack_id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# 停止
curl -X POST http://localhost:8765/api/containers/{pack_id}/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## フローの実行

### フローリストの取得

```bash
curl http://localhost:8765/api/flows \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### フローの実行

```bash
curl -X POST http://localhost:8765/api/flows/hello/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"name": "World"}, "timeout": 300}'
```

`inputs` はフロー入力データ (dict)、`timeout` は最大実行時間 (秒、デフォルト 300、最大 600) です。

同時実行の数は、`RUMI_MAX_CONCURRENT_FLOWS` 環境変数によって制限されます (デフォルトは 10)。制限に達すると、ステータス コード `429` が返されます。

### 応答成功

```json
{
  "success": true,
  "flow_id": "hello",
  "result": {
    "greeting": {"message": "Hello, World!"}
  },
  "execution_time": 1.234
}
```

`result` はフロー出力を保存します。ただし、`_` プレフィックスで始まるキー (`_kernel_step_status` などの内部キー) は自動的に除外されます。

### エラー応答

```json
{
  "success": false,
  "error": "Flow not found: nonexistent_flow",
  "flow_id": "nonexistent_flow",
  "status_code": 404
}
```

|ステータスコード |説明 |
|-------------|------|
| `404` |指定された `flow_id` は存在しません。
| `408` |フローの実行がタイムアウトしました |
| `429` |同時実行制限 (`RUMI_MAX_CONCURRENT_FLOWS`) に達しました |
| `500` |フローの実行中に予期しないエラーが発生しました |
| `503` |システムが一時的に利用できない（起動など） |

### 応答サイズの制限

フローの実行結果は、`RUMI_MAX_RESPONSE_BYTES` (デフォルトは 4MB) を超えると切り捨てられます。切り捨てが発生した場合、応答には `"truncated": true` のマークが付けられます。

---

## 権限管理

これは、Pack 上で特権操作 (例: `pack.update`、`system.restart` など) を許可および実行するための API です。これは、Capability Grant とは独立したメカニズムであり、ホスト側で危険な操作を明示的に許可するために使用されます。

### 権限リスト

```bash
curl http://localhost:8765/api/privileges \
  -H "Authorization: Bearer YOUR_TOKEN"
```

応答例:

```json
{
  "success": true,
  "data": {
    "privileges": [
      {
        "privilege_id": "pack.update",
        "description": "Pack の更新適用を許可",
        "granted_packs": ["updater_pack"]
      },
      {
        "privilege_id": "system.diagnostics",
        "description": "システム診断情報の取得を許可",
        "granted_packs": []
      }
    ]
  }
}
```

### 特権の付与

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/grant/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

|パラメータ |必須 |説明 |
|-----------|------|------|
| `pack_id` (パスパラメータ) | ✅ |ターゲット パック ID |
| `privilege_id` (パスパラメータ) | ✅ |付与する特権ID |

応答例:

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "granted_at": "2026-02-15T10:00:00Z"
  }
}
```

### 特権実行

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/execute/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"target_pack": "my_pack", "staging_id": "abc123"}}'
```

|パラメータ |必須 |説明 |
|-----------|------|------|
| `pack_id` (パスパラメータ) | ✅ |実行元パックID |
| `privilege_id` (パスパラメータ) | ✅ |実行する特権 ID |
| `args` (本体) |オプション |特権操作に渡される引数 |

応答例:

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "result": {"status": "applied", "target_pack": "my_pack"},
    "executed_at": "2026-02-15T10:05:00Z"
  }
}
```

非特権パックからの実行要求は`403 Forbidden`で拒否されます。

---

## UDSソケット設定

Pack 実行コンテナから Strict モードで UDS ソケットにアクセスするための設定。

### 環境変数

|環境変数 |説明 |デフォルト |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` |出口ソケット GID |なし |
| `RUMI_CAPABILITY_SOCKET_GID` |機能ソケット GID |なし |
| `RUMI_EGRESS_SOCKET_MODE` |出力ソケットのアクセス許可 | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` |機能ソケットの権限 | `0660` |
| `RUMI_EGRESS_SOCK_DIR` | Egress ソケットのベース ディレクトリ | `/run/rumi/egress/packs` |
| `RUMI_CAPABILITY_SOCK_DIR` |機能ソケットのベースディレクトリ | `/run/rumi/capability/principals` |

### 構成手順

1. 専用の GID (例: 1099) を決定します。
2. 環境変数を設定します。
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3. 指定した GID のグループは、ソケット作成時に自動的に設定されます。
4. `docker run`を取得すると、`--group-add=1099`が自動的に付与されます。

GID が設定されていない場合、コンテナーからソケットにアクセスできません (nobody:65534)。

---

## 監査ログの読み方

監査ログは、`user_data/audit/` に `{category}_{YYYY-MM-DD}.jsonl` 形式で保存されます。

### 基本的な読み方

```bash
# 今日のネットワークログ
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 拒否されたリクエスト
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.success == false)'

# 権限操作のログ
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq .

# lib 実行ログ
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# capability grant 操作
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq 'select(.details.permission_type == "capability_grant")'

# principal_id 上書き警告
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.action == "principal_id_overridden")'

# 共有辞書の操作履歴
cat user_data/settings/shared_dict/journal.jsonl | jq .

# 循環検出された共有辞書操作
cat user_data/settings/shared_dict/journal.jsonl | jq 'select(.result == "cycle_detected")'
```

### カテゴリリスト

|カテゴリー |目次 |
|----------|------|
| `flow_execution` |フローの実行 |
| `modifier_application` |モディファイアを適用 |
| `python_file_call` |ブロック実行 |
| `approval` |パック承認操作 |
| `permission` |権限操作 |
| `network` |ネットワーク通信 |
| `security` |セキュリティイベント |
| `system` |システムイベント |

---

## エクスポート保留中

`user_data/pending/summary.json`は起動時に自動生成されます。外部ツールはこのファイルを読み込むだけで承認状況を把握できます。

```bash
cat user_data/pending/summary.json | jq .
```

---

## 認証トークン

すべての HTTP API エンドポイントでは、`Authorization: Bearer YOUR_TOKEN` ヘッダーを使用した認証が必要です。トークンは HMAC キーから派生します。

### トークンの検証

トークンは起動時にコンソールに表示されます。さらに、トークンは HMAC キー ファイル (`user_data/settings/.hmac_key`) から派生するため、同じキー ファイルが存在する限り不変です。

キーファイルが存在しない場合は、初回起動時に自動生成されます。

### トークンのローテーション

トークンは、HMAC キーをローテーション (再生成) することで変更されます。

```bash
# HMAC 鍵ローテーションを有効にして起動
export RUMI_HMAC_ROTATE=true
python app.py
```

`RUMI_HMAC_ROTATE=true` を設定すると、次回の起動時に既存の HMAC キーが新しいキーに置き換えられます。ローテーション後は、以前のトークンは無効になるため、すべての API クライアントの構成を更新してください。

回転は 1 回だけ実行されます。ローテーションが完了したら、`RUMI_HMAC_ROTATE` を `false` に戻すか、環境変数を削除します。

---

## 構造化ログ設定

### 環境変数

|環境変数 |説明 |デフォルト |
|----------|------|-----------|
| `RUMI_LOG_LEVEL` |ログレベル。デバッグ / 情報 / 警告 / エラー / 重大 | `INFO` |
| `RUMI_LOG_FORMAT` |出力形式。 json/テキスト | `json` |

### 設定方法

```bash
export RUMI_LOG_LEVEL=DEBUG
export RUMI_LOG_FORMAT=text
python app.py --headless
```

`configure_logging()` は、app.py の起動時に自動的に呼び出され、`rumi.*` 名前空間のロガーに適用されます。

### JSON形式の出力例

```json
{"timestamp": "2026-02-24T12:00:00.000000Z", "level": "INFO", "module": "rumi.kernel.core", "message": "Flow loaded", "correlation_id": "req-123"}
```

### テキスト形式の出力例

```
2026-02-24T12:00:00.000000Z [INFO] rumi.kernel.core - Flow loaded (correlation_id=req-123)
```

---

## 非推奨警告レベルの制御

### 環境変数

|環境変数 |説明 |デフォルト |
|----------|------|-----------|
| `RUMI_DEPRECATION_LEVEL` |非推奨の API を呼び出すときの動作 | `warn` |

|値 |行動 |
|-----|------|
| `warn` | `DeprecationWarning` を `warnings.warn` として公開 |
| `error` | `DeprecationWarning` 例外を発生させる |
| `silent` |何もしない |
| `log` | `logging`でWARNINGレベル出力 |

### 設定例

```bash
export RUMI_DEPRECATION_LEVEL=error
python app.py --headless
```

---

## ヘルスチェック操作

### CLIで確認する

```bash
python app.py --health
```

ステータスが `"UP"` の場合は終了コード 0 が返され、それ以外の場合は終了コード 1 が返されます。

### プログラムによる使用

```python
from core_runtime.health import get_health_checker, probe_disk_space
checker = get_health_checker()
checker.register_probe("disk", lambda: probe_disk_space("/"))
result = checker.aggregate_health()
# result["status"]: "UP" / "DOWN" / "DEGRADED" / "UNKNOWN"
```

### カスタム プローブの追加

```python
from core_runtime.health import HealthStatus
def my_probe() -> HealthStatus:
    # カスタムチェックロジック
    return HealthStatus.UP
checker.register_probe("my_service", my_probe)
```

---

## メトリクスを確認する

### スナップショットの取得

```python
from core_runtime.metrics import get_metrics_collector
collector = get_metrics_collector()
snapshot = collector.snapshot()
# snapshot["counters"], snapshot["gauges"], snapshot["histograms"]
```

### 自動的に収集されるメトリクス

Wave 15 では、次のメトリクスが自動的に収集されます。

|メトリクス名 |タイプ |説明 |ラベル |
|-------------|------|------|--------|
| `flow.step.success` |カウンター |ステップ実行成功数 |ハンドラー |
| `flow.step.error` |カウンター |ステップ実行失敗数 |ハンドラー |
| `flow.execution.complete` |カウンター |フロー実行完了数 |フローID |
| `docker.available` |ゲージ | Docker の可用性 | — |
| `container.start.success` |カウンター |コンテナ起動成功数 | — |
| `container.start.failed` |カウンター |コンテナ起動失敗回数 | — |
| `flows.registered` |ゲージ |登録されたフローの数 | — |
| `python_file_call.duration_ms` |ヒストグラム | Python ファイルの実行時間 (ミリ秒) | — |

---

## パックテンプレートの生成 (足場)

新しいパック テンプレートを生成するコマンド ライン ツール。

### 使用方法

```bash
python -m core_runtime.pack_scaffold <pack_id> [--template TEMPLATE] [--output-dir DIR]
```

### テンプレートリスト

|テンプレート |説明 |
|-------------|------|
| `minimal` (デフォルト) |最小構成 (ecosystem.json + run.py) |
| `capability` |ケイパビリティハンドラーあり |
| `flow` |フロー定義あり |
| `full` |すべて含まれています |

### 実行例

```bash
python -m core_runtime.pack_scaffold my-pack --template full --output-dir ecosystem/
```

---

## エラーコードのリファレンス

エラー コードは、`RUMI-{CATEGORY}-{3_DIGIT_NUMBER}` の形式で構成されます。それぞれのエラーには提案が含まれています。

### カテゴリリスト

|カテゴリー |説明 |例 |
|---------|------|-----|
| `AUTH` |認証/認可 | `RUMI-AUTH-001` (トークン無効) |
| `NET` |ネットワーク | `RUMI-NET-001` (接続失敗) |
| `FLOW` |フローの実行 | `RUMI-FLOW-001` (フローが発見されない) |
| `PACK` |パック管理 | `RUMI-PACK-001` (pack_id が無効です) |
| `CAP` |能力 | `RUMI-CAP-001` (能力は未発見) |
| `VAL` |検証 | `RUMI-VAL-001` (空の値) |
| `SYS` |システム全般 | `RUMI-SYS-001` (内部エラー) |

---

## 環境変数の参照

Rumi AI OS の動作を制御する環境変数のリスト。

|変数名 |デフォルト |説明 |
|--------|-----------|------|
| `RUMI_SECURITY_MODE` | `strict` |セキュリティモード。 `strict` (Docker が必要) または `permissive` (開発の場合は Docker は不要) |
| `RUMI_LOG_LEVEL` | `INFO` |ログレベル。 `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `RUMI_LOG_FORMAT` | `json` |ログの出力形式。 `json` (構造化 JSON) または `text` (ヒューマン テキスト) |
| `RUMI_DEPRECATION_LEVEL` | `warn` |非推奨の API を呼び出すときの動作。 `warn` / `error` / `silent` / `log` |
| `RUMI_SECRETS_KEY` |なし |シークレットの Fernet 暗号化に使用されるキー (Base64 エンコード)。設定されていない場合は、`.secrets_key` ファイルまたは自動生成にフォールバックします。
| `RUMI_SECRETS_ALLOW_PLAINTEXT` | `auto` |平文のシークレットを許可します。 `auto` (暗号化キーが利用できない場合はプレーン テキストとして保存)、`true` (常にプレーン テキストを許可)、`false` (暗号化キーが必要、キーなしでの保存は拒否) |
| `RUMI_MAX_RESPONSE_BYTES` | `4194304` (4MB) |フロー実行結果と Egress Proxy 応答の最大サイズ (バイト) |
| `RUMI_MAX_CONCURRENT_FLOWS` | `10` |フロー同時実行数の上限 |
| `RUMI_MAX_REQUEST_BODY_BYTES` | `1048576` (1MB) | HTTP API が受け入れるリクエストボディの最大サイズ (バイト) |
| `RUMI_API_BIND_ADDRESS` | `127.0.0.1` | API サーバーのバインド アドレス。外部に公開する場合は、`0.0.0.0` に変更します (推奨されません)。
| `RUMI_CORS_ORIGINS` |なし | CORS で許可されるオリジンのカンマ区切りリスト (例: `http://localhost:3000,http://localhost:8080`) |
| `RUMI_HMAC_ROTATE` | `false` | `true` に設定すると、HMAC キーは次回の起動時にローテーションされます。
| `RUMI_DIAGNOSTICS_VERBOSE` | `false` |診断ログに詳細情報を含めるには、`true` に設定します。
| `RUMI_EGRESS_SOCKET_GID` |なし | Egress UDS ソケットの GID。 | `RUMI_EGRESS_SOCKET_GID` |なし | Egress UDS ソケットの GID。厳密モードでコンテナからソケットにアクセスするために必要です。
| `RUMI_CAPABILITY_SOCKET_GID` |なし |機能 UDS ソケット GID。厳密モードでコンテナからソケットにアクセスするために必要です。
| `RUMI_EGRESS_SOCKET_MODE` | `0660` |出力 UDS ソケット権限 |
| `RUMI_CAPABILITY_SOCKET_MODE` | `0660` |機能 UDS ソケットのアクセス許可 |
| `RUMI_EGRESS_SOCK_DIR` | `/run/rumi/egress/packs` |出力 UDS ソケット ベース ディレクトリ |
| `RUMI_CAPABILITY_SOCK_DIR` | `/run/rumi/capability/principals` |機能 UDS ソケット ベース ディレクトリ |
| `RUMI_SECRET_GET_RATE_LIMIT` | `60` | `secrets.get` レート制限 (回/分/パック、スライディング ウィンドウ) |
| `RUMI_LOCAL_PACK_MODE` | `off` | local_pack互換モード。 `off` (無効) または `require_approval` (承認が必要な場合に有効ですが、推奨されません) |

---

## トラブルシューティング

### Docker は使用できません

```
Error: Docker is required but not available
```

開発時には`--permissive`フラグを使用するか、環境変数`RUMI_SECURITY_MODE=permissive`を設定してください。

### パックは承認されていません

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### パックが変更されました

ファイルの変更によりハッシュの不一致が発生した場合は、自動的に無効になります。再認証してください。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### ネットワークアクセスが拒否されました

```bash
# Grant 状態を確認
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# 権限を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'
```

### 機能は使用できません

承認のみ（信頼＋コピー）は使用できません。助成金が必要です。

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### SHA-256 の不一致により、機能ハンドラーの承認が失敗する

handler.py の内容はスキャン後に変更されています。スキャンを再度実行し、新しい候補キーを使用して保留中のファイルを再作成し、再度承認してください。

### pip 依存関係のインストールが拒否されました

1. パックが承認されているかどうかを確認します (厳密モードで必要)
2. `requirements.lock` の構文が正しいことを確認します (`NAME==VERSION` のみが許可されます)。
3. `index_url` が https の外部ホストであるかどうかを確認します

### UDS ソケットにアクセスできません

1. `RUMI_EGRESS_SOCKET_GID` / `RUMI_CAPABILITY_SOCKET_GID` が設定されているか確認する
2. ソケット ファイルのアクセス許可を確認します: `ls -la /run/rumi/egress/packs/`
3. 最終手段: `RUMI_EGRESS_SOCKET_MODE=0666` (非推奨)

### パック更新時の ID エラー

```
Error: pack_identity mismatch
```

既存のパックを、異なる `pack_identity` を持つパックで上書きしようとしています。意図的な交換の場合は、まず既存のパックを削除してから、再度適用してください。

### ライブラリは実行されません

```bash
# 監査ログで確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# 記録を確認（Kernel ハンドラ kernel:lib.list_records）
# 記録をクリアして再実行を強制（Kernel ハンドラ kernel:lib.clear_record）
```

### 修飾子が適用されていません

1.`target_flow_id`が正しいかどうかを確認します
2.対象フローに`phase`が存在するか確認する
3. `requires`の条件が満たされているかどうかを確認します
4. 監査ログをチェックインします。
   ```bash
   cat user_data/audit/modifier_application_$(date +%Y-%m-%d).jsonl | jq .
   ```

### 古いディレクトリの警告

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

`flow/` または `ecosystem/flows/` から、パック内の `flows/`、`user_data/shared/flows/`、または `flows/` に移行します。
