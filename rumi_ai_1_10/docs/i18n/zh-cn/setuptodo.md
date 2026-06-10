<!-- docs-i18n-links:start -->
[EN](../../setuptodo.md) | [JP](../ja/setuptodo.md) | [KR](../ko/setuptodo.md) | [CN](./setuptodo.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 设置和桌面分发 TODO

> **遗留规划备忘录**：实施计划的历史。请参阅[roadmap.md](./roadmap.md) 和[docs/README.md](./README.md) 了解当前政策。

最后更新: 2026-03-17

基于模式 C 架构的路线图。 Rust启动器（thin）管理Kernel进程，设置UI、控制面板、Flow编辑器等都是Pack提供的Web UI（React）。您负责实现 React UI。

---

## 1. 设计决策

### 1.1 采用模式C

三层架构：Rust Launcher + Kernel + Pack。

- **Rust Launcher**：只有 5 个职责：PBS 构建、内核进程管理、健康检查、托盘图标、浏览器打开
- **内核**：Python 运行时。流程执行、包管理、API 服务器
- **Pack**：将所有 UI 功能作为一个包提供（React Web UI）

### 1.2 身份验证/数据存储

- **身份验证**：Supabase Auth（仅限 OAuth：Google / GitHub）。没有电子邮件/密码验证
- **保存配置文件数据**：Cloudflare KV（不保存在 Supabase 上）
- **本地配置文件**：user_data/settings/profile.json

### 1.3 进程间通信

使用现有的 pack_api_server (HTTP localhost:8765)。无需新的 IPC。

### 1.4 用户界面政策

- 所有 Web UI 使用 React + TSX 创建
- React UI 掌握在用户手中。 Agent只是Python后端+Flow+API+Rust
- 启动器的前端（控制面板）也是React

### 1.5 图标政策

- 仅预设图标（不支持用户原始图标上传）
- 图标字段存储预设的ID字符串（例如“cat”，“avatar_03”）
- 图像文件保存在本地。从站点接收ID并显示相应的图像

---

## 2. 架构概述

```
┌──────────────────────────────────────────────────────────┐
│                    Rust ランチャー                         │
│  (PBS構築 / Kernel起動 / ヘルスチェック / トレイ / open)      │
└───────┬──────────────────────────────────┬────────────────┘
        │ spawn                            │ open browser
        ▼                                  ▼
┌──────────────────────┐        ┌──────────────────────┐
│       Kernel         │        │    ブラウザ (Web UI)    │
│  (Python runtime)    │◄──────►│   React SPA           │
│                      │  HTTP  │   localhost:8765      │
│  ┌────────────────┐  │        └──────────────────────┘
│  │ pack_api_server │  │
│  │ :8765           │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Flow Engine    │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Pack Manager   │  │
│  └────────────────┘  │
└──────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                         Packs                             │
│  ┌──────────────┐ ┌──────────────────┐                   │
│  │ core_setup   │ │ core_control_panel│                   │
│  │ (Phase B)    │ │ (Phase C)         │                   │
│  └──────────────┘ └──────────────────┘                   │
└──────────────────────────────────────────────────────────┘
```

---

## 3. profile.json 架构

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-17T12:00:00Z",
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer",
  "setup_completed": true
}
```

|领域 |类型 |描述 |
|-----------|-----|------|
|架构版本 |整数 |架构版本 |
|初始化_at |字符串（ISO 8601）|设置完成日期和时间 |
|用户名 |字符串|用户名（必填，最多 100 个字符）|
|语言 |字符串|语言代码（ja、en、zh、ko、es、fr、de、pt、ru、ar）|
|图标|字符串或空 |预设图标ID |
|职业 |字符串或空 |职业 |
|设置完成 |布尔 |设置完成标志 |

---

## 4. 进展

### 已完成

|任务|内容 |
|--------|------|
|代码审查 | C+等级。识别安全架构问题 |
| SEC-1 | secure_executor.py：Docker 镜像摘要固定 + _sanitize_context 增强 |
| SEC-2 | python_file_executor.py：Docker 镜像摘要已修复 |
| APP-1 | app.py：许可式防护增强（白名单方法）|
|调查1 | Python 打包：使用 PBS + uv 进行 CONDITIONAL GO |
|调查 2 |控制面板+启动器+市场概念|
|调查3 |是否可以使用 Pack + Flow 进行设置？ → 采用模式C |
| B 期 | core_setup 打包 Python 后端 + 流程定义 |
| A 期 |内核API扩展：/health、/api/setup/status、/api/setup/complete、静态文件传递 |
|站点部署| Cloudflare 页面 (rumi-setup.pages.dev) |
|网站认证| Supabase Auth OAuth（Google / GitHub）操作已确认 |

### 进行中

|任务|责任|内容 |
|--------|------|------|
|网站整理|用户|删除虚拟表单、更改为10种语言、添加职业、实现KV存储 |
|应用程序协作审批屏幕 |用户| /授权页面（设计完成，等待实施）|
|预设图标创建|用户| ID命名+形象创作 |

### 未开始

|任务|责任|内容 |
|--------|------|------|
| R相|代理 (Rust) + 用户 (React) | Rust 启动器 + 更新机制 |
| C期|代理 (Python) + 用户 (React) | core_control_panel 包 |
| U相|代理|更新机制 |
| D/E 阶段 |代理+用户|市场（最后一轮）|
| F期 |代理|包开发者 CLI |
| G期 |代理|安全增强|

---

## 5. 阶段配置

### R阶段：Rust Launcher（负责：代理+用户）

用 Rust 制作的瘦启动器二进制文件。

**负责人：**

- R-1：Cargo项目初始化+跨平台构建设置
- R-2：PBS 下载/解压（macOS / Windows / Linux）
- R-3：venv 创建 + uv pip 安装
- R-4：内核进程生成 + stdout/stderr 管道
- R-5：健康检查循环（localhost：8765 / health，超时30秒）
- R-6：系统托盘（托盘图标箱）
- R-7：浏览器打开（打开箱子）
- R-8：正常关闭（SIGTERM → 内核停止 → 进程结束）

**用户负责人：**

- 无（启动器本身没有 UI。UI 是 core_control_panel React）

### A阶段：内核API扩展★完成

- GET /health — 健康检查（无需身份验证）
- GET /api/setup/status — 设置状态（无需身份验证）
- POST /api/setup/complete — 设置完成（无需身份验证）
- 静态文件分发中间件
- 应用程序生命周期管理器

### B阶段：core_setup Pack ★Python后端完成

**完成：**

- Ecosystem.json、check_profile.py、save_profile.py、launch_setup_ui.py
- 修复了 setup_wizard.flow.yaml、00_startup.flow.yaml

**剩余任务（用户责任）：**

- B-1：网站整理（删除虚拟表单，添加10种语言，添加职业）
- B-2：Cloudflare KV 配置文件存储实现
- B-3：应用程序合作批准屏幕（/授权）
- B-4：预设图标创建

### C阶段：core_control_panel包（负责：代理+用户）

仪表板 + 包管理 + 流程编辑器 + 设置屏幕 + 更新确认。

**负责代理（Python后端）：**

- C-1：创建生态系统.json
- C-2：仪表板 API（包列表、流列表、系统状态）
- C-3：包管理 API（安装、卸载、启用/禁用）
- C-4：流程编辑器 API（流程 CRUD、步骤编辑、执行）
- C-5：设置 API（编辑 profile.json、环境设置）
- C-6：更新确认API

**用户负责（React UI）：**

- C-7：仪表板屏幕
- C-8：包管理屏幕（Steam库风格）
- C-9：流程编辑器屏幕（React Flow）
- C-10：设置屏幕
- C-11：更新屏幕

### U阶段：更新机制（负责人：代理）

- U-1：版本控制（当前版本，获取最新版本）
- U-2：更新检查 API（Cloudflare Workers 或 R2 版本文件）
- U-3：Rust 启动器自我更新
- U-4：内核（Python）更新（源代码替换）
- U-5：包更新

### D阶段：市场BE（最后回合）

Cloudflare Workers + R2 + D1 + Supabase Auth

### E阶段：市场FE（最后回合）

Cloudflare Pages + 启动器内集成

### F 阶段：Pack Developer CLI

rumi-pack 初始化/验证/构建/发布/测试

### G 阶段：增强安全性

包签名验证、代码签名、CSP 标头

---

## 6. 依赖关系

```
R Phase ──────┐
              ▼
Phase A ★完了  Phase B ★Python完了（React残り）
  │               │
  ▼               ▼
Phase C ──── Phase U
  │
  ▼
Phase F ──── Phase G
  │
  ▼
Phase D ──── Phase E（最後）
```

---

## 7. MVP 定义

MVP=R相+A相+B相+C相最低配置+U相（更新）。没有市场。

---

## 8. App联动流程

### 设置流程

1. 桌面应用程序在浏览器中打开`https://rumi-setup.pages.dev/authorize?callback=http://localhost:8765/api/setup/complete`
2. 检查您是否已登录网站 → /login 如果未登录 → 批准屏幕如果已登录
3. 批准屏幕：“您想将您的个人资料信息发送到此应用程序吗？”
4. 授权 → POST 到 localhost:8765/api/setup/complete with fetch
5.在app端保存profile.json→设置完成

### POST /api/setup/complete 的 JSON

```json
{
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer"
}
```

---

## 9. 启动顺序

### 首次启动

1. 启动 Rust 启动器
2. PBS检查→如果没有，下载、解压、创建venv、安装依赖
3. 内核生成→健康检查→准备就绪
4.启动流程：setup_check→needs_setup: true
5. 在浏览器中打开rumi-setup.pages.dev/authorize
6. 用户批准 → POST 到 localhost:8765 → 保存 profile.json
7. 设置完成 → 控制面板显示

### 正常启动

1. 启动 Rust 启动器
2. PBS检查→存在→跳过
3. 内核生成→健康检查→准备就绪
4.启动流程：setup_check→needs_setup: false
5. 在浏览器中显示控制面板

---

## 10.基础设施配置

|服务 |应用 |
|----------|------|
| Cloudflare 页面 |网站 (rumi-setup.pages.dev) |
| Cloudflare KV |保存个人资料数据 |
| Cloudflare 工人 |更新检查API、未来市场API |
| Cloudflare R2 | PBS/uv 发行版，未来 Pack 发行版 |
| Cloudflare D1 |未来市场数据库 |
| Supabase 授权 |用户身份验证（OAuth：Google / GitHub）|

---

## 11. 分发配置

### macOS

```
RumiAI.app/Contents/
├── MacOS/rumi-launcher
├── Resources/
│   ├── python/          # PBS
│   ├── rumi_ai_1_10/   # ソースコード
│   └── user_data/       # 初回起動時作成
└── Info.plist
```

### 窗口

```
RumiAI/
├── rumi-launcher.exe
├── python/
├── rumi_ai_1_10/
└── user_data/
```

### Linux

```
rumi-ai/
├── rumi-launcher
├── python/
├── rumi_ai_1_10/
└── user_data/
```

---

## 12. 未决定的项目

- 设置收集项目的最终列表
- 语言包分发方式
- 设置“撤消”功能
- Windows 上的 user_data 路径
- 构建CI/CD管道
- Python版本固定策略
- macOS 协同设计/公证
- Windows 代码签名
- core_control_panel的Web UI交付方法
- Rust 启动器箱选择
- 包开发者CLI语言
- 更新版本文件格式和分发方式
