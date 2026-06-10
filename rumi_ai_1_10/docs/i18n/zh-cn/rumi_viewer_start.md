<!-- docs-i18n-links:start -->
[EN](../../rumi_viewer_start.md) | [JP](../ja/rumi_viewer_start.md) | [KR](../ko/rumi_viewer_start.md) | [CN](./rumi_viewer_start.md)
<!-- docs-i18n-links:end -->

#rumi_viewer 入门指南

`rumi_viewer` 是 Tauri 制作的桌面外壳。在开发启动期间，它会自动检测存储库中的`rumi_ai_1_10/`，启动Python内核，并连接到面板UI。
控制面板前端源代码由`rumi_viewer/frontend`所有，内核提供构建工件作为`rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`至`/panel/`。

## 何时阅读本文

- 我想尽快启动查看器
- 查看器找不到内核并停止
- 面板打开，但屏幕转换被破坏。
- 我想遵循`defaultspack`前端/面板的启动路径

## 最短的启动过程

在存储库根目录中运行以下命令：

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

从第二次开始，如果您还剩下`rumi_viewer/frontend/node_modules`，您可以通过简单地执行以下操作来启动它：

```bash
cd rumi_viewer
cargo tauri dev
```

在开发启动期间，查看器会自动执行以下操作：

1. 检测仓库中的`rumi_ai_1_10/`
2. 准备`~/Library/Application Support/dev.rumiai.app/venv`
3. 使用`python -m app`启动内核
4. 引导至`http://127.0.0.1:8765/panel/`
5. 从查看器中按`Open Defaultspack`打开`defaultspack`的独立UI

## 开发过程中的审批流程

- 检测回购结账并不能单独启用包自动批准
- `RUMI_ENVIRONMENT=development`被传递到内核作为开发环境
- 仅当查看器以指定的`RUMI_AUTO_APPROVE_LOCAL=true`启动时，才会启用自动开发批准。

示例：

```bash
cd rumi_viewer
RUMI_AUTO_APPROVE_LOCAL=true cargo tauri dev
```

在没有此选择的正常开发启动中，修改后的包仍等待重新批准。

## 启动时的样子

- Tauri窗口将在正常启动后打开
- 在初始状态下，`/health`可能返回`needs_setup: true`，在这种情况下，它从设置屏幕开始
- 设置完成后，您将被重定向到面板 UI
- 如果您从面板上的主页按`Open Defaultspack`，查看器将启动`defaultspack`的浏览器用户界面

## 与defaultspack的关系

- 查看器直接在内核控制面板中打开（`/panel/`）
- 前端源位于查看器端，但传递路线仍然是内核的`/panel/`
- `defaultspack`本身作为组件从内核加载
- `defaultspack` 的独立 HTTP 前端为 `DEFAULTS_HTTP_PORT` 默认值 `8766`，但与查看器的初始管道分开
- 开始开发时（`cargo tauri dev`），存储库中包含的`rumi_ai_1_10/ecosystem/defaultspack/`将首先打开。
- 发行版/捆绑包发布请参阅`rumi_home/user_data/packs/defaultspack/current.json`，另请参阅`app_data_dir/user_data/packs/defaultspack/current.json`以了解迁移兼容性
- 因此，如果安装/更新的`Defaultspack v2`切换到托管包，您可以从分布式查看器打开该实体。

## 常见木鞋

### §鲁米§0§

查看器只能在捆绑包中看到`app/`，或者无法检测到回购结账。请在 repo 根目录下开始开发。

### §鲁米§0§

引导程序机密可能未对齐，或者旧内核可能正在占用端口`8765`。检查下面的占用情况。

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

### 当你按Home等键时，它会变成一片漆黑。

面板前端假定`basename="/panel"`。如果您在链接中添加两次`/panel/...`或`navigate()`，它将跳转到`/panel/panel`并导致路由不匹配。前端侧的路由应该是相对于基本名称的，如`/`、`/packs`、`/flows`、`/settings`。

## 确认命令

检查内核是否正在运行：

```bash
curl http://127.0.0.1:8765/health
```

检查defaultspack独立前端是否正在运行：

```bash
curl http://127.0.0.1:8766/api/health
```

## 相关文件

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
