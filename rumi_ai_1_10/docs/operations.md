<!-- docs-i18n-links:start -->
[EN](./operations.md) | [JP](./i18n/ja/operations.md) | [KR](./i18n/ko/operations.md) | [CN](./i18n/zh-cn/operations.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Operations Guide

A guide for operators. Please refer to [architecture.md](./architecture.md) for the overall design and [pack-development.md](./pack-development.md) for Pack development.

---

## Table of Contents

1. [Setup](#setup)
2. [Start](#start)
3. [Security Mode](#security-mode)
4. [HTTP API Overview](#http-api-overview)
5. [Pack approval management](#pack-approval-management)
6. [Network privilege management](#network-privilege-management)
7. [Capability Handler Approval](#capability-handler-approval)
8. [Capability Grant Management](#capability-grant-management)
9. [pip dependent library management](#pip-dependency-library-management)
10. [Secrets Management](#secrets-management)
11. [Pack Import / Apply](#pack-import--apply)
12. [Shared Store Management](#shared-store-management)
13. [Docker / Container management](#docker--container-management)
14. [Flow execution](#flow-execution)
15. [Privileges management](#privileges-management)
16. [UDS Socket Settings](#uds-socket-settings)
17. [How to read the audit log](#how-to-read-audit-logs)
18. [Pending Export](#pending-export)
19. [Authentication token](#authentication-token)
20. [Structured log settings](#structured-log-settings)
21. [Deprecated warning level control](#deprecation-warning-level-control)
22. [Health check operation](#health-check-operation)
23. [Metrics confirmation](#check-metrics)
24. [Pack template generation (scaffold)](#pack-template-generation-scaffold)
25. [Error code reference](#error-code-reference)
26. [Environment variable reference](#environment-variable-reference)
27. [Troubleshooting](#troubleshooting)

---

## Setup

### Requirements

- Python 3.10+
- Docker (required for production environments)
- Git

### Installation

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10

# セットアップ（CLI）
python bootstrap.py --cli init

# または手動
pip install -r requirements.txt
```

### Setup Tool

The setup tool provides two interfaces: CLI and web.

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

The setup tool automates the following: checks for Python / Git / Docker, creates a virtual environment (.venv), installs dependencies, initializes the user_data directory, and installs the default pack (optional).

---

## Start

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

`--health` performs a health check, prints the results in JSON to stdout, and exits. If status is `"UP"`, exit code is 0, otherwise exit code is 1. Built-in probes include disk (disk free space) and writable_tmp (`/tmp` writability). It can be used for health checks of CI/CD and container orchestration.

`--validate` executes Pack validation, prints the results, and exits.

---

## Security mode

Set with the environment variable `RUMI_SECURITY_MODE`.

| Mode | Docker | Behavior |
|--------|--------|------|
| `strict` (default) | Required | Reject execution if Docker is not available |
| `permissive` | Not required | Allow host execution with warnings |

```bash
# 本番
export RUMI_SECURITY_MODE=strict

# 開発
export RUMI_SECURITY_MODE=permissive
```

---

## HTTP API Overview

All endpoints require `Authorization: Bearer YOUR_TOKEN`.

### Pack management

| Method | Path | Description |
|----------|------|------|
| GET | `/api/packs` | List of all Packs |
| GET | `/api/packs/pending` | List of packs waiting for approval |
| GET | `/api/packs/{pack_id}/status` | Get Pack status |
| POST | `/api/packs/scan` | Pack Scan |
| POST | `/api/packs/{pack_id}/approve` | Pack approval |
| POST | `/api/packs/{pack_id}/reject` | Pack Rejected |
| POST | `/api/packs/import` | Pack import |
| POST | `/api/packs/apply` | Pack apply |
| DELETE | `/api/packs/{pack_id}` | Pack uninstall |

### Network permissions

| Method | Path | Description |
|----------|------|------|
| GET | `/api/network/list` | List of all grants |
| POST | `/api/network/grant` | Grant network privileges |
| POST | `/api/network/revoke` | Revoke network privileges |
| POST | `/api/network/check` | Check access |

### Capability Handler candidate

| Method | Path | Description |
|----------|------|------|
| POST | `/api/capability/candidates/scan` | Candidate scan |
| GET | `/api/capability/requests?status=pending` | Application list |
| POST | `/api/capability/requests/{key}/approve` | Authorization (Trust + copy) |
| POST | `/api/capability/requests/{key}/reject` | Rejected |
| GET | `/api/capability/blocked` | Block list |
| POST | `/api/capability/blocked/{key}/unblock` | Unblock |

### Capability Grant

| Method | Path | Description |
|----------|------|------|
| GET | `/api/capability/grants?principal_id=xxx` | Grant list |
| POST | `/api/capability/grants/grant` | Grant |
| POST | `/api/capability/grants/revoke` | Revoke Grant |
| POST | `/api/capability/grants/batch` | Bulk grant (up to 50) |

### pip dependent library

| Method | Path | Description |
|----------|------|------|
| POST | `/api/pip/candidates/scan` | Candidate scan |
| GET | `/api/pip/requests?status=pending` | Application list |
| POST | `/api/pip/requests/{key}/approve` | Approval + Installation |
| POST | `/api/pip/requests/{key}/reject` | Rejected |
| GET | `/api/pip/blocked` | Block list |
| POST | `/api/pip/blocked/{key}/unblock` | Unblock |

### Secrets

| Method | Path | Description |
|----------|------|------|
| GET | `/api/secrets` | Key list (value is masked) |
| POST | `/api/secrets/set` | Set secret value |
| POST | `/api/secrets/delete` | Delete secret value |

### Flow execution

| Method | Path | Description |
|----------|------|------|
| GET | `/api/flows` | Registered Flow list |
| POST | `/api/flows/{flow_id}/run` | Run Flow |

### Store

| Method | Path | Description |
|----------|------|------|
| GET | `/api/stores` | Store list |
| POST | `/api/stores/create` | Create Store |
| GET | `/api/stores/shared` | Shared store list |
| POST | `/api/stores/shared/approve` | Shared Store Authorization |
| POST | `/api/stores/shared/revoke` | Shared store cancellation |

### Unit

| Method | Path | Description |
|----------|------|------|
| GET | `/api/units?store_id=xxx` | Unit list |
| POST | `/api/units/publish` | Publish Unit |
| POST | `/api/units/execute` | Run Unit |

### Privileges

| Method | Path | Description |
|----------|------|------|
| GET | `/api/privileges` | Privilege list |
| POST | `/api/privileges/{pack_id}/grant/{privilege_id}` | Privilege grant |
| POST | `/api/privileges/{pack_id}/execute/{privilege_id}` | Privileged execution |

### Pack original route

| Method | Path | Description |
|----------|------|------|
| GET | `/api/routes` | List of registered routes |
| POST | `/api/routes/reload` | Reload route table |

### Docker / Container

| Method | Path | Description |
|----------|------|------|
| GET | `/api/docker/status` | Docker availability |
| GET | `/api/containers` | Container list |
| POST | `/api/containers/{pack_id}/start` | Starting container |
| POST | `/api/containers/{pack_id}/stop` | Stop container |
| DELETE | `/api/containers/{pack_id}` | Container deletion |

---

## Pack Approval Management

### Check pending approval

```bash
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack Approval

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack Rejection

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'
```

### Reauthorization (Pack in Modified state)

If a file change results in a hash mismatch, it will enter the `modified` state and be automatically disabled.

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Network permission management

### Grant Grant

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

### List of Grants

```bash
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Access check

```bash
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.openai.com", "port": 443}'
```

### Grant Revocation

```bash
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'
```

---

## Capability Handler Authorization

> **Note**: Functions provided by core_pack (store / secrets / flow / communication / docker) do not go through this candidate introduction workflow and are automatically registered in FunctionRegistry when the kernel starts. The following candidate introduction workflow (scan → approve → grant) is applied to the custom capability handler included in the user pack.

The Capability handler becomes available in a two-step operation.

1. **Trust registration** (handler approval): Approve the candidates detected by scan and register the handler code (sha256) as trusted.
2. **Grant** (permission grant): Grant permission of approved handler to Pack.

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

Candidates follow the state transition: scan → pending → approve/reject → blocked.

### Scan for candidates

```bash
curl -X POST http://localhost:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### Approval waiting list

```bash
curl "http://localhost:8765/api/capability/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### scan response

Example response after candidate scan:

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

The format of `candidate_key` is `{pack_id}:{slug}:{handler_id}:{sha256}`. If the contents of handler.py change by including sha256, it will be treated as a different candidate.

### Candidate approval

`:` contained in `candidate_key` requires URL encoding.

```bash
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123..."

curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

approve registers Trust (sha256 allowlist) + copies to `user_data/capabilities/handlers/` + reloads Registry. A separate grant is required for actual use.

### Candidate Rejection

```bash
curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なファイルシステムアクセス"}'
```

The first and second uses have a `rejected` (1 hour cooldown), and the third time has a `blocked`.

### Unblock

```bash
curl -X POST "http://localhost:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## Capability Grant Management

After the capability handler is approved, a Grant (principal × permission) is required for the Pack to actually use the capability.

### Grant Grant

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### List of Grants

```bash
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Grant Revocation

```bash
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### Grant in bulk (batch)

Grant up to 50 grants at once. Processing is best-effort (individual failures do not prevent other grants).

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

| Parameter | Required | Description |
|-----------|------|------|
| `grants` | ✅ | Array of Grant objects (up to 50) |
| `grants[].principal_id` | ✅ | Target Pack ID |
| `grants[].permission_id` | ✅ | Authorization ID |
| `grants[].config` | Optional | Grant settings (`allowed_keys` etc.) |

Example response:

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

### Overall flow

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

## pip dependent library management

This is a workflow to scan → approve → install pip dependencies of a pack.

### Scan for candidates

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### Approval waiting list

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Approval (installation execution)

`candidate_key` requires URL encoding.

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123...', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

The default is wheel only (`--only-binary=:all:`). If wheel includes a package that does not exist, please specify `"allow_sdist": true`.

### Rejected

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

The first and second uses have a `rejected` (1 hour cooldown), and the third time has a `blocked`.

### Unblock

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

### Prerequisites

It is assumed that the Pack is in an approved state. Dependent deployments of unapproved Packs are rejected in strict mode.

---

## Secrets management

### Key list (value is masked)

```bash
curl http://localhost:8765/api/secrets \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Setting secret value

```bash
curl -X POST http://localhost:8765/api/secrets/set \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY", "value": "sk-..."}'
```

### Delete secret value

```bash
curl -X POST http://localhost:8765/api/secrets/delete \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY"}'
```

The secret value is stored in `user_data/secrets/` with 1 key = 1 file. It cannot be redisplayed using the API (set and delete only). No secret values ​​are output to the log.

### Encryption

The secret value is stored encrypted using Fernet (AES-128-CBC + HMAC-SHA256). Encryption keys are obtained in the following priority order:

1. Environment variable `RUMI_SECRETS_KEY` (Base64 encoded Fernet key)
2. `user_data/settings/.secrets_key` File
3. If none of the above exist, automatically generate a key and save it in `.secrets_key`

### Key Backup

If the encryption key is lost, the existing secret value cannot be decrypted. Please back up `user_data/settings/.secrets_key` to a safe location. A backup is also required when managing keys externally using the environment variable `RUMI_SECRETS_KEY`.

### Plaintext mode

You can control unencrypted storage with `RUMI_SECRETS_ALLOW_PLAINTEXT`.

| Value | Behavior |
|-----|------|
| `auto` (default) | Encrypt if encryption key is available, otherwise save as plain text |
| `true` | Always allow storage in plain text |
| `false` | Encryption key required. Refuse to store secret value if key is missing |

`RUMI_SECRETS_ALLOW_PLAINTEXT=false` is recommended for production environments.

---

## Pack Import / Apply

### Import (into staging)

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

Supports folders / `.zip` / `.rumipack` (zip compatible).

### Apply (apply from staging to ecosystem)

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

A backup is automatically created during apply. If `pack_id` and `pack_identity` do not match the existing Pack, it will be rejected.

---

## Shared store management

A management API for sharing Stores between Packs. Share requests require manual approval (SharedStoreManager).

### List of shared stores

```bash
curl http://localhost:8765/api/stores/shared \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Example response:

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

### Shared Store Authorization

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

| Parameter | Required | Description |
|-----------|------|------|
| `store_id` | ✅ | Store ID to share |
| `owner_pack` | ✅ | Store Owned Pack ID |
| `target_pack` | ✅ | Pack ID to share |

Example response:

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

### Shared Store Cancellation

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

| Parameter | Required | Description |
|-----------|------|------|
| `store_id` | ✅ | Target Store ID |
| `owner_pack` | ✅ | Store Owned Pack ID |
| `target_pack` | ✅ | Cancel sharing Pack ID |

Example response:

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

## Docker / Container management

### Check Docker status

```bash
curl http://localhost:8765/api/docker/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Container list

```bash
curl http://localhost:8765/api/containers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Container start/stop

```bash
# 起動
curl -X POST http://localhost:8765/api/containers/{pack_id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# 停止
curl -X POST http://localhost:8765/api/containers/{pack_id}/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Flow execution

### Get flow list

```bash
curl http://localhost:8765/api/flows \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Running a Flow

```bash
curl -X POST http://localhost:8765/api/flows/hello/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"name": "World"}, "timeout": 300}'
```

`inputs` is the Flow input data (dict), `timeout` is the maximum execution time (seconds, default 300, maximum 600).

The number of concurrent runs is limited by the `RUMI_MAX_CONCURRENT_FLOWS` environment variable (default 10). If the limit is reached, status code `429` will be returned.

### Successful response

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

`result` stores Flow outputs. However, keys starting with the `_` prefix (internal keys such as `_kernel_step_status`) are automatically excluded.

### Error response

```json
{
  "success": false,
  "error": "Flow not found: nonexistent_flow",
  "flow_id": "nonexistent_flow",
  "status_code": 404
}
```

| status_code | description |
|-------------|------|
| `404` | Specified `flow_id` does not exist |
| `408` | Flow execution timed out |
| `429` | Concurrent execution limit (`RUMI_MAX_CONCURRENT_FLOWS`) reached |
| `500` | An unexpected error occurred while running Flow |
| `503` | System temporarily unavailable (startup, etc.) |

### Response size limit

Flow execution results will be truncated if they exceed `RUMI_MAX_RESPONSE_BYTES` (default 4MB). If truncation occurs, the response will be marked with `"truncated": true`.

---

## Privileges management

This is an API for allowing and executing privileged operations (e.g. `pack.update`, `system.restart`, etc.) on Pack. It is a mechanism independent of the Capability Grant, and is used to explicitly permit dangerous operations on the host side.

### Privilege list

```bash
curl http://localhost:8765/api/privileges \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Example response:

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

### Privilege Grant

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/grant/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

| Parameter | Required | Description |
|-----------|------|------|
| `pack_id` (Path parameter) | ✅ | Target Pack ID |
| `privilege_id` (Path parameter) | ✅ | Privilege ID to be granted |

Example response:

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

### Privileged execution

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/execute/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"target_pack": "my_pack", "staging_id": "abc123"}}'
```

| Parameter | Required | Description |
|-----------|------|------|
| `pack_id` (path parameter) | ✅ | Execution source Pack ID |
| `privilege_id` (path parameter) | ✅ | Privilege ID to execute |
| `args` (body) | Optional | Arguments to be passed to privileged operations |

Example response:

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

Execution requests from unprivileged Packs are rejected with `403 Forbidden`.

---

## UDS socket settings

Settings for accessing the UDS socket from the Pack execution container in strict mode.

### Environment variables

| Environment variables | Description | Default |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | Egress socket GID | None |
| `RUMI_CAPABILITY_SOCKET_GID` | Capability Socket GID | None |
| `RUMI_EGRESS_SOCKET_MODE` | Egress socket permissions | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | Capability Socket permissions | `0660` |
| `RUMI_EGRESS_SOCK_DIR` | Egress socket base directory | `/run/rumi/egress/packs` |
| `RUMI_CAPABILITY_SOCK_DIR` | Capability Socket base directory | `/run/rumi/capability/principals` |

### Configuration steps

1. Determine your dedicated GID (e.g. 1099)
2. Set environment variables:
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3. The group of the specified GID is automatically set when creating the socket.
4. `--group-add=1099` will be automatically granted when `docker run`

If the GID is not set, the socket cannot be accessed from the container (nobody:65534).

---

## How to read audit logs

Audit logs are stored in `user_data/audit/` in `{category}_{YYYY-MM-DD}.jsonl` format.

### Basic reading

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

### Category list

| Category | Contents |
|----------|------|
| `flow_execution` | Flow execution |
| `modifier_application` | Apply Modifier |
| `python_file_call` | Block execution |
| `approval` | Pack approval operation |
| `permission` | Authority operations |
| `network` | Network communication |
| `security` | Security event |
| `system` | System events |

---

## Pending Export

`user_data/pending/summary.json` is automatically generated at startup. External tools can understand the approval status just by reading this file.

```bash
cat user_data/pending/summary.json | jq .
```

---

## Authentication token

All HTTP API endpoints require authentication using the `Authorization: Bearer YOUR_TOKEN` header. The token is derived from the HMAC key.

### Verify token

The token will be displayed in the console at startup. Additionally, since it is derived from the HMAC key file (`user_data/settings/.hmac_key`), the token is immutable as long as the same key file exists.

If the key file does not exist, it will be automatically generated at the first startup.

### Token rotation

The token changes by rotating (regenerating) the HMAC key.

```bash
# HMAC 鍵ローテーションを有効にして起動
export RUMI_HMAC_ROTATE=true
python app.py
```

Setting `RUMI_HMAC_ROTATE=true` will replace the existing HMAC key with the new key on next boot. After rotation, the previous tokens will no longer be valid, so please update the configuration of all API clients.

Rotation is performed only once. After the rotation is complete, return `RUMI_HMAC_ROTATE` to `false` or delete the environment variable.

---

## Structured log settings

### Environment variables

| Environment variables | Description | Default |
|----------|------|-----------|
| `RUMI_LOG_LEVEL` | Log level. DEBUG / INFO / WARNING / ERROR / CRITICAL | `INFO` |
| `RUMI_LOG_FORMAT` | Output format. json/text | `json` |

### How to set up

```bash
export RUMI_LOG_LEVEL=DEBUG
export RUMI_LOG_FORMAT=text
python app.py --headless
```

`configure_logging()` is automatically called when app.py starts and applies to loggers in the `rumi.*` namespace.

### JSON format output example

```json
{"timestamp": "2026-02-24T12:00:00.000000Z", "level": "INFO", "module": "rumi.kernel.core", "message": "Flow loaded", "correlation_id": "req-123"}
```

### Text format output example

```
2026-02-24T12:00:00.000000Z [INFO] rumi.kernel.core - Flow loaded (correlation_id=req-123)
```

---

## Deprecation warning level control

### Environment variables

| Environment variables | Description | Default |
|----------|------|-----------|
| `RUMI_DEPRECATION_LEVEL` | Behavior when calling deprecated API | `warn` |

| Value | Behavior |
|-----|------|
| `warn` | `DeprecationWarning` published as `warnings.warn` |
| `error` | `DeprecationWarning` Raise exception |
| `silent` | Do nothing |
| `log` | WARNING level output at `logging` |

### Setting example

```bash
export RUMI_DEPRECATION_LEVEL=error
python app.py --headless
```

---

## Health check operation

### Check with CLI

```bash
python app.py --health
```

If status is `"UP"`, exit code 0 is returned, otherwise exit code 1 is returned.

### Programmatic usage

```python
from core_runtime.health import get_health_checker, probe_disk_space
checker = get_health_checker()
checker.register_probe("disk", lambda: probe_disk_space("/"))
result = checker.aggregate_health()
# result["status"]: "UP" / "DOWN" / "DEGRADED" / "UNKNOWN"
```

### Adding a custom probe

```python
from core_runtime.health import HealthStatus
def my_probe() -> HealthStatus:
    # カスタムチェックロジック
    return HealthStatus.UP
checker.register_probe("my_service", my_probe)
```

---

## Check metrics

### Taking a snapshot

```python
from core_runtime.metrics import get_metrics_collector
collector = get_metrics_collector()
snapshot = collector.snapshot()
# snapshot["counters"], snapshot["gauges"], snapshot["histograms"]
```

### Automatically collected metrics

The following metrics are automatically collected in Wave 15:

| Metric name | Type | Description | labels |
|-------------|------|------|--------|
| `flow.step.success` | counter | Step execution success count | handler |
| `flow.step.error` | counter | Step execution failure count | handler |
| `flow.execution.complete` | counter | Flow execution completion count | flow_id |
| `docker.available` | gauge | Docker availability | — |
| `container.start.success` | counter | Container startup success count | — |
| `container.start.failed` | counter | Container startup failure count | — |
| `flows.registered` | gauge | Number of registered flows | — |
| `python_file_call.duration_ms` | histogram | Python file execution time (ms) | — |

---

## Pack template generation (scaffold)

A command line tool that generates a new Pack template.

### How to use

```bash
python -m core_runtime.pack_scaffold <pack_id> [--template TEMPLATE] [--output-dir DIR]
```

### Template list

| Template | Description |
|-------------|------|
| `minimal` (default) | Minimal configuration (ecosystem.json + run.py) |
| `capability` | With Capability Handler |
| `flow` | With Flow definition |
| `full` | All included |

### Execution example

```bash
python -m core_runtime.pack_scaffold my-pack --template full --output-dir ecosystem/
```

---

## Error code reference

Error codes are organized in the format `RUMI-{CATEGORY}-{3_DIGIT_NUMBER}`. Each error comes with a suggestion.

### Category list

| Categories | Description | Examples |
|---------|------|-----|
| `AUTH` | Authentication/Authorization | `RUMI-AUTH-001` (Token invalid) |
| `NET` | Network | `RUMI-NET-001` (Connection failure) |
| `FLOW` | Flow execution | `RUMI-FLOW-001` (Flow not discovered) |
| `PACK` | Pack management | `RUMI-PACK-001` (pack_id invalid) |
| `CAP` | Capability | `RUMI-CAP-001` (Capability not discovered) |
| `VAL` | Validation | `RUMI-VAL-001` (empty value) |
| `SYS` | System general | `RUMI-SYS-001` (internal error) |

---

## Environment variable reference

A list of environment variables that control Rumi AI OS behavior.

| Variable name | Default | Description |
|--------|-----------|------|
| `RUMI_SECURITY_MODE` | `strict` | Security mode. `strict` (Docker required) or `permissive` (Docker not required, for development) |
| `RUMI_LOG_LEVEL` | `INFO` | Log level. `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `RUMI_LOG_FORMAT` | `json` | Log output format. `json` (Structured JSON) or `text` (Human Text) |
| `RUMI_DEPRECATION_LEVEL` | `warn` | Behavior when calling deprecated APIs. `warn` / `error` / `silent` / `log` |
| `RUMI_SECRETS_KEY` | None | Key used for Fernet encryption of Secrets (Base64 encoded). If not set, fallback to `.secrets_key` file or auto-generation |
| `RUMI_SECRETS_ALLOW_PLAINTEXT` | `auto` | Allowing plaintext secrets. `auto` (Save as plain text if encryption key is not available), `true` (Always allow plain text), `false` (Encryption key required, storage denied without key) |
| `RUMI_MAX_RESPONSE_BYTES` | `4194304` (4MB) | Maximum size of Flow execution results and Egress Proxy response (bytes) |
| `RUMI_MAX_CONCURRENT_FLOWS` | `10` | Upper limit on the number of simultaneous Flow executions |
| `RUMI_MAX_REQUEST_BODY_BYTES` | `1048576` (1MB) | Maximum size of request body accepted by HTTP API (bytes) |
| `RUMI_API_BIND_ADDRESS` | `127.0.0.1` | API server bind address. If publishing externally, change to `0.0.0.0` (not recommended) |
| `RUMI_CORS_ORIGINS` | None | Comma-separated list of CORS allowed origins (e.g. `http://localhost:3000,http://localhost:8080`) |
| `RUMI_HMAC_ROTATE` | `false` | If set to `true`, the HMAC key will be rotated at the next startup |
| `RUMI_DIAGNOSTICS_VERBOSE` | `false` | Set to `true` to include detailed information in the diagnostic log |
| `RUMI_EGRESS_SOCKET_GID` | None | GID of the Egress UDS socket. | `RUMI_EGRESS_SOCKET_GID` | None | GID of the Egress UDS socket. Required to access sockets from containers in strict mode |
| `RUMI_CAPABILITY_SOCKET_GID` | None | Capability UDS socket GID. Required to access sockets from containers in strict mode |
| `RUMI_EGRESS_SOCKET_MODE` | `0660` | Egress UDS socket permissions |
| `RUMI_CAPABILITY_SOCKET_MODE` | `0660` | Capability UDS socket permissions |
| `RUMI_EGRESS_SOCK_DIR` | `/run/rumi/egress/packs` | Egress UDS socket base directory |
| `RUMI_CAPABILITY_SOCK_DIR` | `/run/rumi/capability/principals` | Capability UDS socket base directory |
| `RUMI_SECRET_GET_RATE_LIMIT` | `60` | `secrets.get` rate limit (times/min/Pack, sliding window) |
| `RUMI_LOCAL_PACK_MODE` | `off` | local_pack compatibility mode. `off` (disabled) or `require_approval` (valid with approval required, not recommended) |

---

## Troubleshooting

### Docker not available

```
Error: Docker is required but not available
```

When developing, please use the `--permissive` flag or set the environment variable `RUMI_SECURITY_MODE=permissive`.

### Pack not approved

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Pack Modified

It will be automatically disabled if the hash mismatch occurs due to file changes. Please re-authorize.

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Network access is denied

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

### Capability cannot be used

You cannot use just approve (Trust + copy). Grant is required.

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### Capability Handler approval fails with SHA-256 mismatch

The contents of handler.py have changed after the scan. Please run scan again, recreate pending with the new candidate_key, and approve again.

### Installation of pip dependencies is refused

1. Check if the pack is approved (required in strict mode)
2. Check that the syntax of `requirements.lock` is correct (only `NAME==VERSION` is allowed)
3. Check if `index_url` is an external host with https

### Unable to access UDS socket

1. Check if `RUMI_EGRESS_SOCKET_GID` / `RUMI_CAPABILITY_SOCKET_GID` are set
2. Check socket file permissions: `ls -la /run/rumi/egress/packs/`
3. Last resort: `RUMI_EGRESS_SOCKET_MODE=0666` (not recommended)

### Identity error when updating pack

```
Error: pack_identity mismatch
```

You are trying to overwrite an existing Pack with a Pack that has a different `pack_identity`. If it is an intentional replacement, first delete the existing Pack and then apply it again.

### lib is not executed

```bash
# 監査ログで確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# 記録を確認（Kernel ハンドラ kernel:lib.list_records）
# 記録をクリアして再実行を強制（Kernel ハンドラ kernel:lib.clear_record）
```

### Modifier not applied

1. Check if `target_flow_id` is correct
2. Check if `phase` exists in the target Flow
3. Check if the conditions of `requires` are met
4. Check in audit log:
   ```bash
   cat user_data/audit/modifier_application_$(date +%Y-%m-%d).jsonl | jq .
   ```

### Old directory warning

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

Migrate from `flow/` or `ecosystem/flows/` to `flows/`, `user_data/shared/flows/`, or `flows/` in a pack.
