

```markdown
# Rumi AI OS — Operations Guide

運用者向けのガイドです。設計の全体像は [architecture.md](architecture.md)、Pack 開発は [pack-development.md](pack-development.md) を参照してください。

---

## 目次

1. [セットアップ](#セットアップ)
2. [起動](#起動)
3. [セキュリティモード](#セキュリティモード)
4. [HTTP API 概要](#http-api-概要)
5. [Pack 承認管理](#pack-承認管理)
6. [ネットワーク権限管理](#ネットワーク権限管理)
7. [Capability Handler 承認](#capability-handler-承認)
8. [Capability Grant 管理](#capability-grant-管理)
9. [pip 依存ライブラリ管理](#pip-依存ライブラリ管理)
10. [Secrets 管理](#secrets-管理)
11. [Pack Import / Apply](#pack-import--apply)
12. [Docker / コンテナ管理](#docker--コンテナ管理)
13. [UDS ソケット設定](#uds-ソケット設定)
14. [監査ログの読み方](#監査ログの読み方)
15. [Pending Export](#pending-export)
16. [トラブルシューティング](#トラブルシューティング)

---

## セットアップ

### 必要条件

- Python 3.9+
- Docker（本番環境で必須）
- Git

### インストール

```bash
git clone https://github.com/your-repo/rumi-ai.git
cd rumi-ai

# セットアップ（CLI）
python bootstrap.py --cli init

# または手動
pip install -r requirements.txt
```

### セットアップツール

セットアップツールは CLI と Web の 2 つのインターフェースを提供します。

```bash
# CLI モード
./setup.sh --cli              # 対話メニュー
./setup.sh --cli check        # 環境チェック
./setup.sh --cli init         # 初期セットアップ
./setup.sh --cli doctor       # 診断
./setup.sh --cli recover      # リカバリー
./setup.sh --cli run          # アプリ起動

# Web モード
./setup.sh --web              # ブラウザ操作（デフォルトポート 8080）
./setup.sh --web --port 9000  # ポート指定
```

Windows の場合は `setup.bat` を使用してください。

セットアップツールは以下を自動化します: Python / Git / Docker のチェック、仮想環境（.venv）の作成、依存関係のインストール、user_data ディレクトリの初期化、default pack のインストール（オプション）。

---

## 起動

```bash
# 本番環境（Docker 必須）
python app.py

# 開発環境（Docker 不要）
python app.py --permissive

# ヘッドレスモード
python app.py --headless
```

---

## セキュリティモード

環境変数 `RUMI_SECURITY_MODE` で設定します。

| モード | Docker | 動作 |
|--------|--------|------|
| `strict`（デフォルト） | 必須 | Docker 不可なら実行拒否 |
| `permissive` | 不要 | 警告付きでホスト実行を許可 |

```bash
# 本番
export RUMI_SECURITY_MODE=strict

# 開発
export RUMI_SECURITY_MODE=permissive
```

---

## HTTP API 概要

全エンドポイントは `Authorization: Bearer YOUR_TOKEN` が必須です。

### Pack 管理

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/packs` | 全 Pack 一覧 |
| GET | `/api/packs/pending` | 承認待ち Pack 一覧 |
| GET | `/api/packs/{pack_id}/status` | Pack 状態取得 |
| POST | `/api/packs/scan` | Pack スキャン |
| POST | `/api/packs/{pack_id}/approve` | Pack 承認 |
| POST | `/api/packs/{pack_id}/reject` | Pack 拒否 |
| POST | `/api/packs/import` | Pack import |
| POST | `/api/packs/apply` | Pack apply |
| DELETE | `/api/packs/{pack_id}` | Pack アンインストール |

### ネットワーク権限

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/network/list` | 全 Grant 一覧 |
| POST | `/api/network/grant` | ネットワーク権限を付与 |
| POST | `/api/network/revoke` | ネットワーク権限を取り消し |
| POST | `/api/network/check` | アクセス可否をチェック |

### Capability Handler 候補

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/capability/candidates/scan` | 候補スキャン |
| GET | `/api/capability/requests?status=pending` | 申請一覧 |
| POST | `/api/capability/requests/{key}/approve` | 承認（Trust + copy） |
| POST | `/api/capability/requests/{key}/reject` | 却下 |
| GET | `/api/capability/blocked` | ブロック一覧 |
| POST | `/api/capability/blocked/{key}/unblock` | ブロック解除 |

### Capability Grant

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/capability/grants?principal_id=xxx` | Grant 一覧 |
| POST | `/api/capability/grants/grant` | Grant を付与 |
| POST | `/api/capability/grants/revoke` | Grant を取り消し |

### pip 依存ライブラリ

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/pip/candidates/scan` | 候補スキャン |
| GET | `/api/pip/requests?status=pending` | 申請一覧 |
| POST | `/api/pip/requests/{key}/approve` | 承認 + インストール |
| POST | `/api/pip/requests/{key}/reject` | 却下 |
| GET | `/api/pip/blocked` | ブロック一覧 |
| POST | `/api/pip/blocked/{key}/unblock` | ブロック解除 |

### Secrets

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/secrets` | キー一覧（値はマスク） |
| POST | `/api/secrets/set` | 秘密値を設定 |
| POST | `/api/secrets/delete` | 秘密値を削除 |

### Docker / コンテナ

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/docker/status` | Docker 利用可否 |
| GET | `/api/containers` | コンテナ一覧 |
| POST | `/api/containers/{pack_id}/start` | コンテナ起動 |
| POST | `/api/containers/{pack_id}/stop` | コンテナ停止 |
| DELETE | `/api/containers/{pack_id}` | コンテナ削除 |

---

## Pack 承認管理

### 承認待ちの確認

```bash
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack の承認

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack の拒否

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'
```

### 再承認（Modified 状態の Pack）

ファイル変更でハッシュ不一致になると `modified` 状態になり、自動無効化されます。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## ネットワーク権限管理

### Grant の付与

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

### Grant の一覧

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

### Grant の取り消し

```bash
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'
```

---

## Capability Handler 承認

Capability handler は scan → pending → approve/reject → blocked の状態遷移を辿ります。

### 候補のスキャン

```bash
curl -X POST http://localhost:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 承認待ち一覧

```bash
curl "http://localhost:8765/api/capability/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 候補の承認

`candidate_key` に含まれる `:` は URL エンコードが必要です。

```bash
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123..."

curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

approve は Trust（sha256 allowlist）の登録 + `user_data/capabilities/handlers/` へのコピー + Registry reload を行います。実際に使用するには別途 Grant の付与が必要です。

### 候補の却下

```bash
curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なファイルシステムアクセス"}'
```

1 回目・2 回目は `rejected`（1 時間クールダウン）、3 回目で `blocked` になります。

### ブロック解除

```bash
curl -X POST "http://localhost:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## Capability Grant 管理

capability handler の approve 後、実際に Pack が capability を使用するには Grant（principal × permission）の付与が必要です。

### Grant の付与

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### Grant の一覧

```bash
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Grant の取り消し

```bash
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 全体フロー

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

## pip 依存ライブラリ管理

Pack の pip 依存を scan → approve → インストールするワークフローです。

### 候補のスキャン

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 承認待ち一覧

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 承認（インストール実行）

`candidate_key` は URL エンコードが必要です。

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123...', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

デフォルトは wheel のみ（`--only-binary=:all:`）。wheel が存在しないパッケージを含む場合は `"allow_sdist": true` を指定してください。

### 却下

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

1 回目・2 回目は `rejected`（1 時間クールダウン）、3 回目で `blocked` になります。

### ブロック解除

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

### 前提条件

Pack が承認済み（approved 状態）であることが前提です。未承認 Pack の依存導入は strict モードで拒否されます。

---

## Secrets 管理

### キー一覧（値はマスク）

```bash
curl http://localhost:8765/api/secrets \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 秘密値の設定

```bash
curl -X POST http://localhost:8765/api/secrets/set \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY", "value": "sk-..."}'
```

### 秘密値の削除

```bash
curl -X POST http://localhost:8765/api/secrets/delete \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY"}'
```

秘密値は `user_data/secrets/` に 1 key = 1 file で格納されます。API で再表示はできません（set と delete のみ）。ログに秘密値は一切出力されません。

---

## Pack Import / Apply

### Import（staging への取り込み）

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

フォルダ / `.zip` / `.rumipack`（zip 互換）に対応しています。

### Apply（staging から ecosystem へ適用）

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

apply 時にバックアップが自動作成されます。`pack_id` と `pack_identity` が既存 Pack と不一致の場合は拒否されます。

---

## Docker / コンテナ管理

### Docker 状態確認

```bash
curl http://localhost:8765/api/docker/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### コンテナ一覧

```bash
curl http://localhost:8765/api/containers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### コンテナ起動 / 停止

```bash
# 起動
curl -X POST http://localhost:8765/api/containers/{pack_id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# 停止
curl -X POST http://localhost:8765/api/containers/{pack_id}/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## UDS ソケット設定

strict モードで Pack 実行コンテナから UDS ソケットにアクセスするための設定です。

### 環境変数

| 環境変数 | 説明 | デフォルト |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | Egress ソケットの GID | なし |
| `RUMI_CAPABILITY_SOCKET_GID` | Capability ソケットの GID | なし |
| `RUMI_EGRESS_SOCKET_MODE` | Egress ソケットのパーミッション | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | Capability ソケットのパーミッション | `0660` |
| `RUMI_EGRESS_SOCK_DIR` | Egress ソケットのベースディレクトリ | `/run/rumi/egress/packs` |
| `RUMI_CAPABILITY_SOCK_DIR` | Capability ソケットのベースディレクトリ | `/run/rumi/capability/principals` |

### 設定手順

1. 専用 GID を決定（例: 1099）
2. 環境変数を設定:
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3. ソケット作成時に指定 GID の group が自動設定されます
4. `docker run` 時に `--group-add=1099` が自動付与されます

GID が未設定の場合、コンテナ（nobody:65534）からソケットにアクセスできません。

---

## 監査ログの読み方

監査ログは `user_data/audit/` に `{category}_{YYYY-MM-DD}.jsonl` の形式で保存されます。

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

### カテゴリ一覧

| カテゴリ | 内容 |
|----------|------|
| `flow_execution` | Flow 実行 |
| `modifier_application` | Modifier 適用 |
| `python_file_call` | ブロック実行 |
| `approval` | Pack 承認操作 |
| `permission` | 権限操作 |
| `network` | ネットワーク通信 |
| `security` | セキュリティイベント |
| `system` | システムイベント |

---

## Pending Export

起動時に `user_data/pending/summary.json` が自動生成されます。外部ツールはこのファイルを読むだけで承認待ち状況を把握できます。

```bash
cat user_data/pending/summary.json | jq .
```

---

## トラブルシューティング

### Docker が利用できない

```
Error: Docker is required but not available
```

開発時は `--permissive` フラグを使用するか、環境変数 `RUMI_SECURITY_MODE=permissive` を設定してください。

### Pack が承認されない

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack が無効化された（Modified）

ファイル変更でハッシュ不一致になると自動無効化されます。再承認してください。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### ネットワークアクセスが拒否される

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

### Capability が使えない

approve（Trust + copy）だけでは使えません。Grant の付与が必要です。

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### Capability Handler の approve が SHA-256 mismatch で失敗する

scan 後に handler.py の内容が変更されています。再度 scan を実行して新しい candidate_key で pending を作り直し、改めて approve してください。

### pip 依存のインストールが拒否される

1. Pack が承認済みか確認してください（strict モードでは必須）
2. `requirements.lock` の構文が正しいか確認してください（`NAME==VERSION` のみ許可）
3. `index_url` が https で外部ホストか確認してください

### UDS ソケットにアクセスできない

1. `RUMI_EGRESS_SOCKET_GID` / `RUMI_CAPABILITY_SOCKET_GID` が設定されているか確認
2. ソケットファイルのパーミッションを確認: `ls -la /run/rumi/egress/packs/`
3. 最終手段: `RUMI_EGRESS_SOCKET_MODE=0666`（非推奨）

### Pack 更新時に identity エラー

```
Error: pack_identity mismatch
```

既存 Pack と異なる `pack_identity` を持つ Pack で上書きしようとしています。意図的な置換の場合は、先に既存 Pack を削除してから再度 apply してください。

### lib が実行されない

```bash
# 監査ログで確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# 記録を確認（Kernel ハンドラ kernel:lib.list_records）
# 記録をクリアして再実行を強制（Kernel ハンドラ kernel:lib.clear_record）
```

### Modifier が適用されない

1. `target_flow_id` が正しいか確認
2. `phase` が対象 Flow に存在するか確認
3. `requires` の条件が満たされているか確認
4. 監査ログで確認:
   ```bash
   cat user_data/audit/modifier_application_$(date +%Y-%m-%d).jsonl | jq .
   ```

### 旧ディレクトリの警告

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

`flow/` や `ecosystem/flows/` から `flows/`、`user_data/shared/flows/`、または Pack 内 `flows/` へ移行してください。
```