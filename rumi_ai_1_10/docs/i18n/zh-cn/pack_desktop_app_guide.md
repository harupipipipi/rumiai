<!-- docs-i18n-links:start -->
[EN](../../pack_desktop_app_guide.md) | [JP](../ja/pack_desktop_app_guide.md) | [KR](../ko/pack_desktop_app_guide.md) | [CN](./pack_desktop_app_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Pack 桌面应用开发指南

最后更新: 2026-03-28

本文档是开发人员将**桌面应用程序**（在单独的桌面窗口中运行的应用程序）集成到 Rumi AI OS Pack 中的指南。它涵盖了如何设置 Ecosystem.json、如何使用 pack-shell 二进制文件、安全模型和快捷方式生成。

---

## 1.什么是桌面应用程序包？

### 1.1 概述

Pack桌面应用程序允许应用程序通过Rumi AI OS的**基于能力的权限系统**在单独的桌面窗口中运行。

与`viewer:display`功能不同，`viewer:display`功能在Rumi Viewer（基于Tauri的WebView UI）内显示前端，`desktop_app.execute`功能在**操作系统本机窗口**中启动应用程序。您可以使用任何 GUI 框架，例如 tkinter、Qt、Electron、Tauri 等。

### 1.2 架构

```
ユーザー
  │
  ├── ショートカット / CLI
  │       │
  │       ▼
  │   pack-shell (Rust バイナリ)
  │       │
  │       ├─ 1. Kernel /health チェック
  │       ├─ 2. Kernel 未起動なら自動起動
  │       ├─ 3. POST /api/desktop/token でトークン取得
  │       ├─ 4. 環境変数 (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) を設定
  │       └─ 5. アプリプロセスを起動
  │               │
  │               ▼
  │           デスクトップアプリ (Python, Node.js, etc.)
  │               │
  │               ▼
  │           Kernel API (localhost:8765) と通信
  │
  └── Rumi AI OS Kernel
          │
          ├── CapabilityGrantManager (Grant 検証)
          ├── DesktopAppManager (登録・ショートカット生成)
          └── POST /api/desktop/token (トークン発行)
```

### 1.3 不偏袒原则

桌面应用程序支持也使用与其他功能相同的模式来实现。 `core_desktop_capability` 作为 core_pack 包含在内核中并管理 `desktop_app.execute` 权限。与任何其他功能一样，第三方包需要授权才能使用此功能。

---

## 2.先决条件

要开发和运行桌面应用程序包，您将需要：

- **Rumi AI OS**可以安装和启动的环境
- **pack-shell 二进制文件** 已构建（请参阅下面的构建说明）
- **Python 3.11 或更高版本**（用于示例应用程序。应用程序本身可以用任何语言实现）

---

## 3.ecosystem.json 的desktop_app 部分

要将桌面应用程序功能添加到您的包中，请将`desktop_app`部分添加到`ecosystem.json`中。

### 3.1 设置示例

```json
{
  "pack_id": "my_desktop_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Desktop App",
    "description": "デスクトップアプリのサンプル Pack"
  },
  "desktop_app": {
    "command": "python app.py",
    "working_dir": "",
    "env": {},
    "capabilities": ["desktop_app.execute"],
    "window": {
      "title": "My Desktop App",
      "width": 800,
      "height": 600
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

### 3.2 字段列表

|领域 |类型 |必填 |描述 |
|-----------|-----|------|------|
| §鲁米§0§|字符串| ✅ |启动命令。作为 pack-shell 的 `--command` 参数传递给应用程序 |
| §鲁米§0§|字符串| — |应用程序的工作目录。如果为空字符串，将使用 Pack 目录 |
| §鲁米§0§|字典 | — |要传递给应用程序的其他环境变量。 `RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID` 不是必需的，因为 pack-shell 会自动配置它们 |
| §鲁米§0§|列表 | — |请求的功能列表 |
| §鲁米§0§|字典 | — |窗口设置。使用`title`（字符串）指定应用程序名称，并使用`width`/`height`（整数）指定大小。也用于快捷方式名称 |
| §鲁米§0§|列表 | — |支持的平台。 `"darwin"`、`"win32"`、`"linux"`的组合|

### 3.3 模式验证

内核的`PackImporter`使用以下规则验证`desktop_app`部分：

- 如果存在`desktop_app`，它必须是一个字典
- `desktop_app.command` 为必填项且必须是非空字符串
- `working_dir`必须是字符串，`env`必须是字典，`capabilities`必须是列表，`window`必须是字典，`platforms`必须是列表（都可以省略）

如果验证失败，导入Pack时会打印警告，并且Pack不会被注册。

---

## 4.desktop_app.execute 能力

### 4.1 概述

`desktop_app.execute` 是`core_desktop_capability` Pack 提供的功能。控制桌面应用程序的启动、停止和检查状态。

### 4.2 清单.json

```json
{
  "function_id": "execute",
  "description": "デスクトップアプリケーションを起動・管理する",
  "requires": ["desktop_app.execute"],
  "grant_config": {
    "permission_id": "desktop_app.execute",
    "dangerous": true,
    "allowed_packs": ["my_desktop_pack"],
    "max_token_lifetime": 3600
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "pack_id": {
        "type": "string",
        "description": "Pack ID whose desktop app to execute"
      },
      "action": {
        "type": "string",
        "description": "Action to perform: launch, stop, status",
        "default": "launch",
        "enum": ["launch", "stop", "status"]
      }
    },
    "required": ["pack_id"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "token": { "type": "string" },
      "port": { "type": "integer" },
      "expires_in": { "type": "integer" }
    },
    "required": ["token", "port", "expires_in"]
  },
  "calling_convention": "block"
}
```

### 4.3 危险标志

`desktop_app.execute` 设置为`dangerous: true`。这意味着桌面应用程序具有高权限，因为它可以在主机操作系统上启动任意进程。与 Docker 隔离的 Python 函数不同，桌面应用程序可以直接访问主机的文件系统和网络。

因此，用户在安装该包时必须明确授权`desktop_app.execute`授权。

### 4.4 行动

|行动|描述 |
|--------|------|
| §鲁米§0§|启动应用程序并颁发令牌（默认）|
| §鲁米§0§|停止运行应用程序 |
| §鲁米§0§|返回应用程序的运行状态 |

---

## 5. 如何使用 pack-shell

### 5.1 构建

```bash
cd pack-shell
cargo build --release
```

构建工件：`target/release/pack-shell`

交叉编译：

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

### 5.2 CLI 参考

pack-shell 具有子命令`run` 和`version`。

#### 运行子命令

```
pack-shell run <PACK_ID> --command <COMMAND> [OPTIONS]
```

|论点|类型 |必填 |默认 |描述 |
|------|-----|------|-----------|------|
| §鲁米§0§|位置论证 | ✅ | — |要启动的包的 ID |
| §鲁米§0§|字符串| ✅ | — |要执行的命令（例如`"python app.py"`）|
| §鲁米§0§|字符串| ✅ |环境变量`RUMI_API_TOKEN` |内核 API 身份验证令牌 |
| §鲁米§0§| u16 | 16 — | §鲁米§1§ |内核API端口号|
| §鲁米§0§|字符串| — | §鲁米§1§ |内核未启动时启动的命令 |
| §鲁米§0§| u64 | 64 — | §鲁米§1§ |等待内核启动超时时间（秒）|
| §鲁米§0§|字符串| — |无 |应用程序工作目录 |

#### 版本子命令

```bash
pack-shell version
# 出力: pack-shell 0.1.0
```

### 5.3 执行示例

```bash
# 基本的な使い方
pack-shell run my_desktop_pack --command "python app.py" --working-dir /path/to/my_desktop_pack --api-token "$TOKEN"

# 全オプション指定
pack-shell run my_desktop_pack \
  --command "python app.py" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --api-token "your-api-token" \
  --timeout 60 \
  --working-dir /path/to/workdir
```

### 5.4 执行流程

pack-shell 启动桌面应用程序，如下所示：

1. 使用`GET /health`检查内核运行状态
2. 如果内核没有响应，则使用`--kernel-cmd`启动内核并轮询运行状况检查（1秒间隔，最多`--timeout`）
3. 在`POST /api/desktop/token`获取临时代币
4. 设置环境变量`RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID`并启动应用程序进程
5.等待app进程结束并返回退出码

### 5.5 环境变量

pack-shell 读取的环境变量：

|变量|描述 |
|------|------|
| §鲁米§0§|更换`--api-token`。 CLI 参数优先 |

通过`DesktopAppManager`启动被固定到提供`RUMI_API_TOKEN`作为环境变量的合约。

pack-shell 传递给应用程序的环境变量：

|变量|描述 |
|------|------|
| §鲁米§0§|内核颁发的临时令牌 |
| §鲁米§0§|内核API端口号|
| §鲁米§0§|目标包 ID |

---

## 6. API 参考

### 6.1 POST /api/desktop/token

为桌面应用程序颁发临时令牌。 Pack提供的`core_desktop_capability` API路线。

#### 请求

```json
{
  "pack_id": "my_desktop_pack"
}
```

|领域 |类型 |必填 |描述 |
|-----------|-----|------|------|
| §鲁米§0§|字符串| ✅ |为其颁发令牌的包 ID |

#### 响应（成功）

```json
{
  "token": "abc-123-xyz",
  "port": 8765,
  "expires_in": 3600
}
```

|领域 |类型 |描述 |
|-----------|-----|------|
| §鲁米§0§|字符串|短期访问令牌 |
| §鲁米§0§|整数 |内核API端口号（默认：8765）|
| §鲁米§0§|整数 |令牌过期时间（秒；默认值：3600）|

#### 响应（错误）

```json
{
  "error": "desktop_app.execute not granted for pack: my_desktop_pack",
  "status_code": 403
}
```

|状态代码 |描述 |
|------------|------|
| 400 | `pack_id` 未指定或无效 |
| 403 | 403没有资助`desktop_app.execute` |
| 500 | 500内部错误 |
| 503 | 503桌面功能处理程序不可用 |

---

## 7. 快捷方式生成

### 7.1 桌面应用程序管理器

`desktop_app_manager.py` 中的`DesktopAppManager` 类管理 Pack 桌面应用程序的生命周期。

#### 主要方法

|方法|描述 |
|--------|------|
| §鲁米§0§|注册 Pack 桌面应用程序并生成特定于平台的快捷方式 |
| §鲁米§0§|取消订阅并删除快捷方式 |
| §鲁米§0§|启动已注册的应用程序 |
| §鲁米§0§|使用 SIGTERM 停止正在运行的应用程序 |
| §鲁米§0§|返回已注册应用程序列表 |

#### register_app的返回值

```json
{
  "success": true,
  "shortcut_path": "/Users/user/Applications/MyApp.app"
}
```

### 7.2 平台快捷键

`register_app`自动生成特定于平台的快捷方式：

|平台|格式|地点 |
|---------------|------|--------|
| macOS（`darwin`）| `.app` 捆绑包（Info.plist + 启动脚本）| §鲁米§2§ |
| Windows (`win32`) | `.lnk` 快捷方式（使用 PowerShell 生成）| §鲁米§2§ |
| Linux | §鲁米§0§文件| §鲁米§1§ |

快捷方式`AppName`取自`desktop_app.window.title`（或`pack_id`，如果未指定）。

### 7.3 搜索 pack-shell 二进制文件

`DesktopAppManager` 按以下顺序搜索 pack-shell 二进制文件：

1.环境变量`RUMI_PACK_SHELL_PATH`中指定的路径
2. 在系统中从`PATH`中搜索`pack-shell`

如果未找到，`register_app` 将返回错误。

---

## 8. 安全性

### 8.1 为什么它很危险？

`desktop_app.execute` 设置为 `dangerous: true` 的原因如下：

- 桌面应用程序直接在主机操作系统上运行（无 Docker 隔离）
- 可以访问文件系统、网络和其他进程
- 执行`command`字段中指定的任何命令。

### 8.2 用户批准的重要性

Pack 的设计带有恶意。用户应确保在批准授权之前检查桌面应用程序`command`启动了哪些程序。

### 8.3 令牌过期时间

使用`POST /api/desktop/token`发行的代币会在短时间内（默认 3600 秒 = 1 小时）过期。 `max_token_lifetime` 由`grant_config` 控制。

`allowed_packs` 失败关闭。任何 Pack 都不允许使用空数组`[]`、未指定或非法类型。您可以指定`["*"]`用于验证目的，您需要明确允许所有包，但通常您应该列出要启动的包ID。

### 8.4 建议

- 仅安装来自可信来源的包
- 在批准拨款之前检查`desktop_app.command`的内容
- 对于不再需要的包，请使用`unregister_app`删除快捷方式
- 设置`allowed_packs`以仅允许授予特定包

---

## 9. 开发流程

### 9.1 一步一步

1. **开发应用程序**：使用任何框架（如 tkinter、Qt、Electron 等）创建桌面应用程序。
2. **支持环境变量**：实现代码来读取`RUMI_TOKEN`、`RUMI_PORT`、`RUMI_PACK_ID`并与应用程序内的内核API进行通信。
3. **使用 pack-shell 进行测试**：使用`pack-shell run <PACK_ID> --command "python app.py" --working-dir <DIR> --api-token <TOKEN>`确认操作
4. **将desktop_app添加到ecosystem.json**：设置`command`、`window`、`platforms`等。
5. **安装包**：将其放入`ecosystem/`中或使用 PackImporter 导入
6. **批准拨款**：在 GrantManager 中设置`desktop_app.execute`的拨款
7. **生成快捷方式**：使用DesktopAppManager的`register_app`自动生成特定于平台的快捷方式

### 9.2 本地开发技巧

您还可以手动设置环境变量并直接启动应用程序，而无需使用 pack-shell：

```bash
export RUMI_TOKEN="dev-token-for-testing"
export RUMI_PORT="8765"
export RUMI_PACK_ID="my_desktop_pack"
python app.py
```

内核运行后，您可以使用`GET /health`检查连接：

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## 10. 故障排除

### pack-shell 无法连接到内核

- 检查内核是否正在运行：`curl http://localhost:8765/health`
- 检查端口号是否正确：默认为`8765`
- 检查`--kernel-cmd`中是否指定了正确的内核启动命令

### 获取token时出现403错误

- 检查是否设置了`desktop_app.execute`的授予。
- 检查`pack_id`是否正确
- 检查 API 令牌（`--api-token` 或 `RUMI_API_TOKEN`）是否有效

### 未生成快捷方式

- 检查是否找到 pack-shell 二进制文件：设置`RUMI_PACK_SHELL_PATH`或添加到`PATH`
- 检查`register_app`的返回值：`{"success": false, "error": "..."}`包含错误消息

### 应用程序无法启动

- 检查`desktop_app.command`是否是正确的命令：尝试直接在 shell 中执行它
- 检查`working_dir`指向正确的目录
- 检查所需的依赖库是否安装

### 无法在 macOS 上打开 .app

- 如果被网守阻止：从“系统偏好设置 > 安全和隐私”允许
- 检查启动脚本是否有执行权限：`chmod +x ~/Applications/MyApp.app/Contents/MacOS/launch`

---

## 相关文档

- [包开发指南](./pack-development.md) — 包概述
- [多语言包开发指南](./multilang_pack_guide.md) — 如何用Python以外的语言开发包
- [示例代码：桌面应用程序包](examples/desktop_app_pack/) — 桌面应用程序包模板
- [pack-shell 自述文件](../../../../pack-shell/i18n/zh-cn/README.md) — pack-shell 二进制详细信息
