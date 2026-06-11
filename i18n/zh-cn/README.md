<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 鲁米艾

Rumi AI 是一个模块化的 AI 运行时和工具工作区。

存储库将运行时实现保留在`rumi_ai_1_10/`下，而`rumi_ai/`提供了版本稳定的Python入口点。规范的控制面板前端源位于`rumi_viewer/frontend`；内核在 `/panel/` 处提供其构建的工件。

## 阅读此内容时...

|我想做什么|首先从哪里阅读 |补充剂 |
|---|---|---|
|我想按目的关注该文档 | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) |我们将从“你想做的事”开始引导你按阅读顺序 |
|我想调整术语的含义 | [`rumi_ai_1_10/docs/terminology.md`](./rumi_ai_1_10/docs/terminology.md) | `rule`、`skill`、`team workspace`、`subagent` 组织兼容名称 |
|无论如何我都想开始 | [`README.md`](./README.md) 的`Start` |只列出最短的启动命令 |
|我想了解runtime/kernel的整体情况 | [`rumi_ai_1_10/README.md`](./rumi_ai_1_10/README.md) |有架构和主要目录的解释 |
|想了解机制，不看代码 | [`rumi_ai_1_10/docs/concepts/system-mechanism.md`](./rumi_ai_1_10/docs/concepts/system-mechanism.md) |可以通过文字了解启动、流程、审批、授权流程 |
|我想先检查一下操作（教程） | [`rumi_ai_1_10/docs/tutorials/runtime-quickstart.md`](./rumi_ai_1_10/docs/tutorials/runtime-quickstart.md) |从`--health`到`/panel/`的最短步骤 |
|我想开始`rumi_viewer`/我想看看观众是如何被卡住的 | [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) |启动流程、`401`、黑屏以及与`defaultspack`的关系总结 |
|我想修复查看器端 | [`rumi_viewer/src-tauri/src/config.rs`](./rumi_viewer/src-tauri/src/config.rs) 和[`rumi_viewer/src-tauri/src/kernel_manager.rs`](./rumi_viewer/src-tauri/src/kernel_manager.rs) |查看器是Tauri shell，Rust端负责启动内核 |
|我想使用 pack / defaultspack | [`rumi_ai_1_10/ecosystem/defaultspack/README.md`](./rumi_ai_1_10/ecosystem/defaultspack/README.md) |这是chat、ai_client、tool等的pack端实现 |
|我想知道如何扩展defaultspack的前端 | [`rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md`](./rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md) |这是添加右栏、添加设置、扩展聊天渲染器和添加预览提要的网关 |
|我想知道如何处理 API 密钥和机密 | [`rumi_ai_1_10/docs/operations.md`](./rumi_ai_1_10/docs/operations.md) | 的秘密部分有`user_data/secrets/`和API路线的解释 |
|我想知道如何创建包 | [`rumi_ai_1_10/docs/pack-development.md`](./rumi_ai_1_10/docs/pack-development.md) |我们总结了ecosystem.json、路由、权限的方式 |
|我想了解运营和审计的概念 | [`rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`](./rumi_ai_1_10/docs/quality_pack/philosophy_memo.md) |我正在组织持续发展和回归确认的假设|

## 存储库布局

- `rumi_ai_1_10/`：内核/运行时/API/后端源代码树
- `rumi_ai/`：版本稳定的Python入口点包
- `pack-shell/`：桌面包启动器
- `rumi_viewer/`：桌面外壳和控制面板前端源代码
- `rumi_mobile/`：Flutter iOS/Android 应用程序用于可信 LAN 默认包访问
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/`：与 defaultspack 捆绑在一起的浏览器配套资源

## 设置

### 先决条件

-Python 3.10+
- Node.js 18+
- npm
- 生锈/货物（接触`rumi_viewer`时）
- Flutter SDK（使用`rumi_mobile`时）

### 克隆并安装

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

cd rumi_viewer/frontend
npm install
cd ../..
```

## 开始

```bash
source .venv/bin/activate
python -m rumi_ai --health
python -m rumi_ai
```

`--health` 还检查系统卷的使用情况。如果 `disk` 探测为 `DEGRADED` / `DOWN`，则可能是由于缺乏可用空间而不是代码问题。

## 常见任务

### 只是快捷方式

如果您安装了`just`，则可以从存储库根目录进行常见检查：

```bash
just -l
just tooling-test
just integrity
```

### 后端健康检查

```bash
python -m rumi_ai --health
```

### 运行时启动

```bash
python -m rumi_ai
```

### 观众发展

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

从第二次开始，如果您还剩`rumi_viewer/frontend/node_modules`，则只需执行以下操作即可开始：

```bash
cd rumi_viewer
cargo tauri dev
```

开发查看器会自动检测存储库中的`rumi_ai_1_10/`并启动内核。
开始开发时，`Open Defaultspack` 优先于包含在存储库中的`defaultspack` 打开。
请参阅[`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md)获取指南，包括如何在启动时卡住。

## 发展

```bash
source .venv/bin/activate
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## 品质包

有关持续开发、审计和回归确认的操作包，请参阅下文：

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`

## HMAC 迁移

```bash
python -m rumi_ai migrate-hmac
```

## 组件

- `rumi_ai`：稳定的 CLI 和模块入口点
- `rumi_ai_1_10`：内核、运行时、API、后端和文档
- `pack-shell`：推出桌面包和代理令牌/引导程序流程
- `rumi_viewer`：查看器端应用程序外壳和规范面板前端源
- `rumi_mobile`：用于承载身份验证内核包 API 的移动远程客户端
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`：defaultspack `browser_companion`工具的解压Chromium扩展

有关架构和运行时的详细信息，请参阅[rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md)。

有关受 Codex OSS 启发的编码工具约定，请参阅 [AGENTS.md](./AGENTS.md) 和
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md)。
