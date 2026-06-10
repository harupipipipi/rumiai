<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 包壳

用于启动 Pack 桌面应用程序的帮助程序二进制文件。

## 概述

pack-shell 自动执行以下流程：

1.检查内核的/health端点
2. 如果内核没有启动，它将自动启动。
3. 在 /api/desktop/token 获取身份验证令牌
4. 设置环境变量（RUMI_TOKEN、RUMI_PORT、RUMI_PACK_ID）并启动应用程序

## 构建

```bash
cd pack-shell
cargo build --release
```

构建工件：`target/release/pack-shell`

## 如何使用

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

## 启动流程

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

## 环境变量

### 输入（由 pack-shell 读取）

|变量|描述 |笔记|
|------|------|------|
| RUMI_API_TOKEN | RUMI_API_TOKEN | API 身份验证令牌 | --api-token 替代方案 |

从`DesktopAppManager`启动的桌面应用程序是一个接收`RUMI_API_TOKEN`作为环境变量的合约。

### 输出（传递给应用程序）

|变量|描述 |
|------|------|
| RUMI_TOKEN |桌面临时令牌 |
|鲁米_端口 |内核API端口|
| RUMI_PACK_ID |目标包 ID |

## 交叉构建

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
