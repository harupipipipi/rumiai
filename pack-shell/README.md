# pack-shell

Pack デスクトップアプリを起動するためのヘルパーバイナリ。

## 概要

pack-shell は以下のフローを自動化します:

1. Kernel の /health エンドポイントを確認
2. Kernel が起動していなければ自動起動
3. /api/desktop/token で認証トークンを取得
4. 環境変数 (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) を設定してアプリを起動

## ビルド

```bash
cd pack-shell
cargo build --release
```

ビルド成果物: `target/release/pack-shell`

## 使い方

```bash
# 基本的な使い方
pack-shell run <PACK_ID> --command "python app.py" --api-token "$TOKEN"

# 全オプション指定
pack-shell run my-pack-123 \
  --command "python app.py" \
  --api-token "your-api-token" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --timeout 60 \
  --working-dir /path/to/workdir

# バージョン表示
pack-shell version
```

## 起動フロー

```
pack-shell run
    │
    ▼
GET /health ──── OK ───────────────┐
    │                              │
    │ (timeout/error)              │
    ▼                              │
Start Kernel subprocess            │
    │                              │
    ▼                              │
Poll /health (1s interval)         │
    │                              │
    ▼ (healthy)                    │
    ◄──────────────────────────────┘
    │
    ▼
POST /api/desktop/token
    │
    ▼
Set env vars (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID)
    │
    ▼
Spawn app subprocess (--command)
    │
    ▼
Wait for app exit → return exit code
```

## 環境変数

### 入力（pack-shell が読む）

| 変数 | 説明 | 備考 |
|------|------|------|
| RUMI_API_TOKEN | API 認証トークン | --api-token の代替 |

`DesktopAppManager` から起動される desktop app は `RUMI_API_TOKEN` を環境変数で受け取る契約です。

### 出力（アプリに渡す）

| 変数 | 説明 |
|------|------|
| RUMI_TOKEN | デスクトップ用一時トークン |
| RUMI_PORT | Kernel API ポート |
| RUMI_PACK_ID | 対象 Pack ID |

## クロスビルド

```bash
# macOS (Apple Silicon)
cargo build --release --target aarch64-apple-darwin

# macOS (Intel)
cargo build --release --target x86_64-apple-darwin

# Windows
cargo build --release --target x86_64-pc-windows-msvc

# Linux
cargo build --release --target x86_64-unknown-linux-gnu
```
