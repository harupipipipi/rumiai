

```markdown
# Capability Handler Installation Guide

## 1. 概要

Rumi の Capability システムでは、Pack が提供する「候補 handler」を ecosystem に同梱し、ユーザーの明示的な承認を経て実働化する仕組みを持ちます。

このドキュメントでは、候補 handler の配置規約、承認ワークフロー（pending → approve/reject/block）、API 仕様、セキュリティ上の考慮事項を説明します。

**何ができるか:**

- Pack 開発者が capability handler を ecosystem に同梱できる
- 起動時または手動 API で候補を検出し、承認待ち（pending）として管理できる
- ユーザーが API で approve すると、Trust 登録 + コピー + Registry reload が同時に行われ即座に実働化される
- reject は履歴として残り、クールダウン 1 時間で再通知が抑制される
- 同一候補を 3 回 reject すると blocked（サイレントブロック）となり、明示的に unblock しない限り通知されない

---

## 2. 重要な設計原則

### No Favoritism（贔屓なし）
公式もサードパーティも同じ承認フローを通る。permission_id の意味をシステムは解釈しない。

### 悪意前提
候補は信頼できない外部コードとして扱う。entrypoint のパストラバーサル検証、sha256 による改ざん検知を必ず行う。

### Trust + Grant 分離
- **Trust**: handler_id + sha256 の allowlist。handler.py の内容が信頼済みかを判定する
- **Grant**: principal_id × permission_id の権限付与。誰がどの capability を使えるかを管理する
- approve は Trust のみを登録する。Grant は別途付与する

### ecosystem は候補、user_data は実働
- `ecosystem/` に置かれた handler は「候補」（配布物）であり、直接実行されない
- `user_data/capabilities/handlers/` にコピーされた handler のみが「実働」として扱われる
- コピーは approve 時に行われ、移動は禁止される（ecosystem 側は常に配布物として残る）

---

## 3. ディレクトリ規約

### 完成像のツリー

**候補（ecosystem 側）:**

```
ecosystem/<pack_id>/share/capability_handlers/<slug>/
  handler.json
  handler.py
```

**実働（user_data 側、approve 後にコピーされる）:**

```
user_data/capabilities/handlers/<slug>/
  handler.json
  handler.py
```

**申請・履歴:**

```
user_data/capabilities/requests/
  requests.jsonl     # イベントログ（追記のみ）
  index.json         # 状態スナップショット
```

**ブロック:**

```
user_data/capabilities/requests/
  blocked.json       # ブロックリスト
```

**Trust（sha256 allowlist）:**

```
user_data/capabilities/trust/trusted_handlers.json
```

**Grant（principal × permission）:**

```
user_data/permissions/capabilities/<principal_id_sanitized>.json
```

### 候補の配置規約

候補 handler は必ず以下のパスに配置する:

```
ecosystem/<pack_id>/share/capability_handlers/<slug>/handler.json
ecosystem/<pack_id>/share/capability_handlers/<slug>/handler.py
```

- `<slug>` はディレクトリ名。user_data へのコピー先もこの slug を使用する
- `handler.json` は以下のフィールドを必須とする:
  - `handler_id` (string): ハンドラーの一意識別子
  - `permission_id` (string): 要求される権限ID
  - `entrypoint` (string): 実行エントリポイント（例: `handler.py:execute`）

handler.json の例:

```json
{
  "handler_id": "fs_read_handler",
  "permission_id": "fs.read",
  "entrypoint": "handler.py:execute",
  "description": "ファイルシステム読み取り handler",
  "risk": "ファイルシステムへの読み取りアクセスを提供"
}
```

---

## 4. 状態モデル

### 状態一覧

| 状態 | 説明 |
|------|------|
| `pending` | 候補が検出され、ユーザーの承認待ち |
| `installed` | 承認済み。Trust 登録 + コピー完了 |
| `rejected` | ユーザーが却下。クールダウン（1時間）後に再通知可能 |
| `blocked` | 3回 reject されサイレントブロック。unblock するまで通知されない |
| `failed` | approve 処理中にエラー発生。手動対応が必要 |

### 状態遷移図

```
                    ┌─────────────────────────┐
                    │      (候補検出)          │
                    │    scan_candidates()     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                           ┌──────────┐
                      ┌───▶│ pending  │◀──────────────────────┐
                      │    └────┬─────┘                       │
                      │         │                              │
                      │    ┌────┴────┐                         │
                      │    │         │                         │
                      │    ▼         ▼                         │
                      │ approve   reject                       │
                      │    │         │                         │
                      │    ▼         ▼                         │
                      │ ┌──────┐ ┌──────────┐                 │
                      │ │installed│ │ rejected │                │
                      │ └──────┘ └────┬─────┘                 │
                      │               │                        │
                      │          reject_count                   │
                      │            >= 3 ?                       │
                      │          ┌────┴────┐                   │
                      │          │ YES     │ NO                │
                      │          ▼         │                   │
                      │     ┌─────────┐   │  cooldown 切れ    │
                      │     │ blocked │   └──────────────────▶│
                      │     └────┬────┘                        │
                      │          │                             │
                      │       unblock                          │
                      │          │                             │
                      │          ▼                             │
                      │     ┌──────────┐   cooldown 切れ      │
                      │     │ rejected │───────────────────────┘
                      │     └──────────┘
                      │
                      │  (approve失敗)
                      │         │
                      │         ▼
                      │    ┌────────┐
                      └────│ failed │
                           └────────┘
```

### candidate_key

候補の同一性は `candidate_key` で管理される:

```
candidate_key = "{pack_id}:{slug}:{handler_id}:{sha256}"
```

- sha256 を含めることで、handler.py の内容が変わると別の候補として扱われる
- 例: `my_pack:fs_read_v1:fs_read_handler:a1b2c3d4...`

---

## 5. API 仕様

すべてのエンドポイントは内部トークン認証が必要です:

```
Authorization: Bearer <token>
```

### 5.1 候補スキャン

**`POST /api/capability/candidates/scan`**

ecosystem を走査し、新しい候補を pending として登録する。

Request body (任意):
```json
{
  "ecosystem_dir": "ecosystem"
}
```

Response:
```json
{
  "success": true,
  "data": {
    "scanned_count": 3,
    "pending_created": 2,
    "skipped_blocked": 1,
    "skipped_cooldown": 0,
    "skipped_installed": 0,
    "skipped_pending": 0,
    "skipped_failed": 0,
    "errors": []
  }
}
```

### 5.2 候補一覧

**`GET /api/capability/requests?status=pending`**

status フィルタ: `pending` | `rejected` | `installed` | `failed` | `blocked` | `all`

Response:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "candidate_key": "my_pack:fs_read_v1:fs_read_handler:abc123...",
        "status": "pending",
        "reject_count": 0,
        "cooldown_until": null,
        "last_event_ts": "2026-02-07T12:00:00Z",
        "candidate": {
          "pack_id": "my_pack",
          "slug": "fs_read_v1",
          "handler_id": "fs_read_handler",
          "permission_id": "fs.read",
          "entrypoint": "handler.py:execute",
          "source_dir": "ecosystem/my_pack/share/capability_handlers/fs_read_v1",
          "handler_py_sha256": "abc123..."
        },
        "installed_to": null,
        "last_error": null
      }
    ],
    "count": 1,
    "status_filter": "pending"
  }
}
```

### 5.3 承認（同時 install）

**`POST /api/capability/requests/{candidate_key_urlencoded}/approve`**

candidate_key は URL エンコードが必要（`:` → `%3A`）。

Request body (任意):
```json
{
  "notes": "Approved after code review"
}
```

Response (成功時):
```json
{
  "success": true,
  "data": {
    "success": true,
    "status": "installed",
    "installed_to": "user_data/capabilities/handlers/fs_read_v1",
    "handler_id": "fs_read_handler",
    "permission_id": "fs.read",
    "sha256": "abc123..."
  }
}
```

Response (失敗時):
```json
{
  "success": false,
  "error": "SHA-256 mismatch: handler.py content changed since scan (TOCTOU)"
}
```

### 5.4 却下

**`POST /api/capability/requests/{candidate_key_urlencoded}/reject`**

Request body:
```json
{
  "reason": "Security concern with file system access"
}
```

Response:
```json
{
  "success": true,
  "data": {
    "success": true,
    "status": "rejected",
    "reject_count": 1,
    "cooldown_until": "2026-02-07T13:00:00Z"
  }
}
```

3回目の reject 時:
```json
{
  "success": true,
  "data": {
    "success": true,
    "status": "blocked",
    "reject_count": 3,
    "cooldown_until": null
  }
}
```

### 5.5 ブロック一覧

**`GET /api/capability/blocked`**

Response:
```json
{
  "success": true,
  "data": {
    "blocked": {
      "my_pack:fs_read_v1:fs_read_handler:abc123...": {
        "candidate_key": "my_pack:fs_read_v1:fs_read_handler:abc123...",
        "blocked_at": "2026-02-07T12:30:00Z",
        "reason": "Rejected 3 times",
        "reject_count": 3
      }
    },
    "count": 1
  }
}
```

### 5.6 ブロック解除

**`POST /api/capability/blocked/{candidate_key_urlencoded}/unblock`**

Request body (任意):
```json
{
  "reason": "Re-evaluation requested"
}
```

Response:
```json
{
  "success": true,
  "data": {
    "success": true,
    "status_after": "rejected"
  }
}
```

---

## 6. 承認・却下・ブロックの運用例

### 6.1 候補をスキャンする

```bash
curl -X POST http://127.0.0.1:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 6.2 pending 一覧を確認する

```bash
curl http://127.0.0.1:8765/api/capability/requests?status=pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6.3 候補を承認する

candidate_key に含まれる `:` は URL エンコードが必要です:

```bash
# candidate_key = "my_pack:fs_read_v1:fs_read_handler:abc123def456..."
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123def456..."

curl -X POST "http://127.0.0.1:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

### 6.4 候補を却下する

```bash
curl -X POST "http://127.0.0.1:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Unnecessary file system access"}'
```

### 6.5 ブロック一覧を確認する

```bash
curl http://127.0.0.1:8765/api/capability/blocked \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6.6 ブロックを解除する

```bash
curl -X POST "http://127.0.0.1:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Re-evaluation after pack update"}'
```

---

## 7. セキュリティ

### 7.1 パストラバーサル防止

entrypoint フィールドは 2 段階で検証される:

1. **文字列レベル**: パスコンポーネントに `..` が含まれていないことを確認
2. **resolve レベル**: `Path.resolve()` で実パスを解決し、slug ディレクトリ配下であることを `relative_to()` で確認（シンボリックリンク対策）

検証に失敗した候補はスキャン時にエラーとして記録され、pending には入らない。

### 7.2 SHA-256 検証（TOCTOU 対策）

approve 処理では以下の順序で sha256 を検証する:

1. スキャン時に handler.py の sha256 を計算し、candidate_key に含める
2. approve 時に handler.py の sha256 を **再計算** する
3. スキャン時の sha256 と一致しない場合、approve は失敗する

これにより、スキャンと approve の間に handler.py が改ざんされた場合を検知する。

### 7.3 上書き禁止

コピー先（`user_data/capabilities/handlers/<slug>/`）に既に handler が存在する場合:

- handler_id が同一 かつ sha256 が同一: OK（idempotent、何もしない）
- それ以外: **エラー**（自動上書きは安全上の理由から禁止）

既存の handler を更新したい場合は、手動で `user_data/capabilities/handlers/<slug>/` を削除してから再 approve する。

### 7.4 監査ログ

以下のイベントが AuditLogger に記録される:

| イベント | severity | 状況 |
|---------|----------|------|
| `capability_handler_installed` | info | approve + install 成功 |
| `capability_handler_rejected` | warning | reject |
| `capability_handler_blocked` | warning | 3回 reject でブロック |
| `capability_handler_unblocked` | warning | ブロック解除 |
| `capability_handler_install_failed` | error | install 失敗 |

details には pack_id, slug, handler_id, permission_id, sha256, source_dir, installed_to, reason, actor 等が含まれる。

### 7.5 認証

全 API エンドポイントは `Authorization: Bearer <token>` による内部トークン認証が必須。トークンは PackAPIServer の初期化時に生成または指定される。

---

## 8. トラブルシューティング

### 8.1 scan しても候補が見つからない

**原因**: 候補のディレクトリ構造が規約に合っていない。

**確認**:
- `ecosystem/<pack_id>/share/capability_handlers/<slug>/handler.json` が存在するか
- `handler.json` に `handler_id`, `permission_id`, `entrypoint` が含まれているか
- entrypoint で指定されたファイル（通常 `handler.py`）が存在するか

**対処**: scan のレスポンスの `errors` 配列を確認し、詳細なエラー情報を得る。

### 8.2 approve が "SHA-256 mismatch" で失敗する

**原因**: scan 後に handler.py の内容が変更された（TOCTOU）。

**対処**: 再度 scan を実行して新しい candidate_key で pending を作り直し、改めて approve する。

### 8.3 approve が "Destination already exists with different content" で失敗する

**原因**: 同じ slug で異なる内容の handler が既に `user_data/capabilities/handlers/<slug>/` にコピー済み。

**対処**:
1. 既存の handler が不要な場合: `user_data/capabilities/handlers/<slug>/` を手動で削除してから再 approve
2. 既存の handler が必要な場合: 候補の slug を変更する

### 8.4 blocked された候補を再度承認したい

**対処**:
1. `POST /api/capability/blocked/{key}/unblock` でブロックを解除
2. unblock 後は rejected（cooldown 1時間）状態になる
3. cooldown 後に再度 scan すると pending に戻る
4. 改めて approve する

### 8.5 requests.jsonl が肥大化した

**対処**: `requests.jsonl` は追記のみのイベントログ。安全に truncate またはアーカイブ可能（index.json と blocked.json が状態の正本）。

### 8.6 Trust は登録されたが Grant がない

approve は Trust（sha256 allowlist）のみを登録する。実際に Pack が capability を使用するには、別途 Grant（principal × permission）の付与が必要。

Trust と Grant の分離は意図的な設計であり、「handler のコードを信頼する」ことと「誰がそれを使えるか」を独立して管理するためのもの。
```