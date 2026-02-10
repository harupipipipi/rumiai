# Dependency Workflow 運用手順

Pack の pip 依存を scan → approve → 確認する運用手順です。

---

## 1. 候補をスキャン

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

レスポンス例:
```json
{
  "success": true,
  "data": {
    "scanned_count": 5,
    "pending_created": 2,
    "skipped_blocked": 0,
    "skipped_cooldown": 1,
    "skipped_installed": 2,
    "errors": []
  }
}
```

---

## 2. 承認待ち一覧を確認

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3. 承認（インストール実行）

candidate_key は URL エンコードが必要です。

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123def456', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

wheel のみで失敗する場合:
```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": true}'
```

---

## 4. 却下

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

- 1回目・2回目: `rejected`（1時間 cooldown）
- 3回目: `blocked`

---

## 5. ブロック一覧確認

```bash
curl "http://localhost:8765/api/pip/blocked" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. ブロック解除

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## トラブル対応

### インストールが failed になった

1. `GET /api/pip/requests?status=failed` で `last_error` を確認
2. wheel が無い場合は `allow_sdist: true` で再 approve
3. ネットワークエラーの場合は Docker のネットワーク設定を確認
4. 再 scan すると `failed` → `pending` に戻る

### Docker が利用できない

pip 依存インストールには Docker が必須です。`RUMI_SECURITY_MODE=permissive` でも Docker が必要です（ホスト環境を汚さないため）。

### requirements.lock を更新した

ファイル内容が変わると SHA-256 が変わり、新しい candidate_key になります。再度 scan → approve が必要です。古い候補はそのまま残ります。
