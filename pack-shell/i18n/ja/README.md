<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# パックシェル

Pack デスクトップ アプリを起動するためのヘルパー バイナリ。

## 概要

Pack-Shell は次のフローを自動化します。

1. カーネルの /health エンドポイントを確認します。
2. カーネルが起動していない場合は、自動的に起動します。
3. /api/desktop/token で認証トークンを取得します。
4. 環境変数（RUMI_TOKEN、RUMI_PORT、RUMI_PACK_ID）を設定し、アプリを起動します

## ビルドする

```bash
cd pack-shell
cargo build --release
```

ビルドアーティファクト: `target/release/pack-shell`

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

## 起動の流れ

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

### 入力 (pack-shell による読み取り)

|変数 |説明 |メモ |
|------|------|------|
| RUMI_API_TOKEN | API認証トークン | --api-token の代替 |

`DesktopAppManager` から起動されるデスクトップ アプリは、環境変数として `RUMI_API_TOKEN` を受け取るコントラクトです。

### 出力 (アプリに渡す)

|変数 |説明 |
|------|------|
| RUMI_TOKEN |デスクトップ用の一時トークン |
|ルミポート |カーネル API ポート |
| RUMI_パック_ID |ターゲット パック ID |

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
