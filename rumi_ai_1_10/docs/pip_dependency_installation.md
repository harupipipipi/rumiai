# Pip Dependency Installation

Pack が必要とする Python ライブラリ（PyPI パッケージ）を安全に導入するシステムの完成像ドキュメントです。

---

## 概要

Pack は `requirements.lock` を同梱することで、PyPI パッケージへの依存を宣言できます。ユーザーが API で承認すると、公式が起動するビルダー用 Docker コンテナで依存をダウンロード・インストールし、Pack 実行コンテナから `import` 可能にします。

ホスト Python 環境は一切汚れません。全ての生成物は `user_data/packs/<pack_id>/python/` 配下に閉じ込められます。

---

## API エンドポイント

全て `Authorization: Bearer <token>` 必須。`candidate_key` は `:` を含むため URL encode が必要です。

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/pip/candidates/scan` | 候補をスキャン |
| GET | `/api/pip/requests?status=pending` | 申請一覧 |
| POST | `/api/pip/requests/{candidate_key}/approve` | 承認＋インストール |
| POST | `/api/pip/requests/{candidate_key}/reject` | 却下 |
| GET | `/api/pip/blocked` | ブロック一覧 |
| POST | `/api/pip/blocked/{candidate_key}/unblock` | ブロック解除 |

---

## 状態遷移

```
  scan
   │
   ▼
pending ──approve──▶ installed
   │                     ▲
   │ reject              │ (re-scan after fix)
   ▼                     │
rejected ──(cooldown 1h)──▶ pending
   │
   │ reject ×3
   ▼
blocked ──unblock──▶ pending
```

| 状態 | 説明 |
|------|------|
| `pending` | スキャンで検出され承認待ち |
| `installed` | 承認済み、依存インストール完了 |
| `rejected` | 却下（1h cooldown 後に再 scan で pending に戻る） |
| `blocked` | 3回却下でブロック（unblock するまで scan に上がらない） |
| `failed` | インストール失敗（再 scan で pending に戻る） |

---

## セキュリティ方針

### ビルダーコンテナ（download 用）

`pip download` は `--network=bridge` で PyPI にアクセスしますが、以下で保護されます:

- `--cap-drop=ALL`
- `--security-opt=no-new-privileges:true`
- `--read-only` + `--tmpfs=/tmp`
- `--user=65534:65534` (nobody)
- `--memory=512m`

### ビルダーコンテナ（install 用）

`pip install` は `--network=none`（完全オフライン）で実行します。

### 実行コンテナ

Pack のコード実行コンテナは引き続き `--network=none` です。site-packages は **読み取り専用** でマウントされます。

### sdist 制御

デフォルトでは wheel のみ許可（`--only-binary=:all:`）。sdist が必要な場合は `allow_sdist: true` を明示する必要があります。

---

## 生成物

```
user_data/packs/<pack_id>/python/
├── wheelhouse/         # pip download したファイル
├── site-packages/      # pip install --target の展開先
└── state.json          # インストールメタデータ
```

### state.json

```json
{
  "candidate_key": "my_pack:requirements.lock:abc123...",
  "requirements_sha256": "abc123...",
  "allow_sdist": false,
  "index_url": "https://pypi.org/simple",
  "installed_at": "2025-01-15T10:00:00Z",
  "packages": [
    {"name": "requests", "version": "2.31.0"},
    {"name": "flask", "version": "3.0.0"}
  ]
}
```

---

## candidate_key

`{pack_id}:{requirements_relpath}:{sha256(requirements.lock)}`

requirements.lock の内容が変わると sha256 が変わり、新しい candidate_key になります。

---

## 監査ログ

以下のイベントが `system` カテゴリに記録されます:

- `pip_request_created`
- `pip_request_rejected`
- `pip_request_blocked`
- `pip_install_started`
- `pip_install_completed`
- `pip_install_failed`
- `pip_unblocked`

---

## 関連ドキュメント

- [requirements.lock 規約](spec/requirements_lock.md)
- [運用手順](runbook/dependency_workflow.md)
- [PYTHONPATH と site-packages](architecture/pythonpath_and_sitepackages.md)
