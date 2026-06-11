<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 鲁米人工智能操作系统

**“无基础的基础”**——模块化的人工智能框架，没有“身体”可以修改

---

## 有目的的指导

首先放置每个目的的阅读目的地，这样您就可以找到入口点，而不必遵循所有代码。

|我想做什么|首先从哪里阅读 |我能明白多少|
|---|---|---|
|我想按目的追踪文档 | [`docs/README.md`](./docs/README.md)|我可以在一页上追踪“我想要做什么→哪个文档” |
|我想调整术语的含义 | [`docs/terminology.md`](./docs/terminology.md)|我可以检查`rule`、`skill`、`team workspace`、`delegation`的用法 |
|我想先开始|根 [`README.md`](../README.md) |最短的启动命令和repo入口|
|我想先尝试一下| [`docs/tutorials/runtime-quickstart.md`](./docs/tutorials/runtime-quickstart.md)|从`--health`到`/panel/`的最短教程 |
|想不看代码就了解运行时机制 | [`docs/concepts/system-mechanism.md`](./docs/concepts/system-mechanism.md)|启动、流程、审批、授权、观众协作的执行路径 |
|我想看看`rumi_viewer`的启动过程以及它是如何卡住的 | [`docs/rumi_viewer_start.md`](./docs/rumi_viewer_start.md)| `401`、黑屏、面板与默认包的关系 |
|我想扩展defaultspack的前端 | [`ecosystem/defaultspack/docs/frontend_extensions.md`](./ecosystem/defaultspack/docs/frontend_extensions.md)|如何增加右侧栏、设置、聊天渲染器和预览提要 |
|我想知道这个运行时的想法 |本自述文件中的`Thoughts` |以流程为中心、Pack前提、Fail-Soft理念|
|我想知道目录的作用| `Project structure` 的作用 |本自述文件中的`core_runtime/`、`ecosystem/`、`user_data/` |
|创建/修复包 | [`docs/pack-development.md`](./docs/pack-development.md)| `ecosystem.json`、`routes.json`、`permissions.json`，使用秘密 |
|我想关注defaultspack的聊天/ai | [`ecosystem/defaultspack/README.md`](./ecosystem/defaultspack/README.md)| defaultspack 的实现端 |
|我想看看defaultspack前端的未来工作 | [`ecosystem/defaultspack/docs/frontend_todo.md`](./ecosystem/defaultspack/docs/frontend_todo.md)|登记进展及下一步工作|
|我想设置 API 密钥和机密 | [`docs/operations.md`](./docs/operations.md) 的秘密部分 | `user_data/secrets/`和API路线|
|我想通过查看器修复启动路径 | [`../rumi_viewer/src-tauri/src/config.rs`](../rumi_viewer/src-tauri/src/config.rs) 和 [`../rumi_viewer/src-tauri/src/kernel_manager.rs`](../rumi_viewer/src-tauri/src/kernel_manager.rs) |查看器应该启动哪个内核以及它应该通过哪个环境 |
|安装包/想查看授权| [`core_runtime/setup_pack.py`](./core_runtime/setup_pack.py) 和 [`core_runtime/approval_manager.py`](./core_runtime/approval_manager.py) |安装包选择、一切正常授予、重新授权 |
|我想了解运营和审计 | [`docs/operations.md`](./docs/operations.md) 和 [`docs/roadmap.md`](./docs/roadmap.md) |操作API、秘密、未来政策|

## 最短平面图

1.`app.py`启动内核
2.`core_runtime/`拥有流程、打包、批准和执行基础设施
3.`ecosystem/<pack_id>/`提供主体功能
4.`user_data/`具有授权状态、秘密、存储、审计
5.`rumi_viewer/`成为启动内核并连接面板的shell

## 常用入口

### 启动确认

```bash
python -m rumi_ai --health
python -m rumi_ai
```

### 查看器开发启动

```bash
cd ../rumi_viewer/src-tauri
cargo tauri dev
```

### 典型测试

```bash
python -m pytest tests/test_defaultspack_google_provider.py
python -m pytest tests/test_defaultspack_modules.py
```

---

## 想法

### 没有偏袒

Rumi AI 的官方代码对“聊天”、“工具”、“提示”、“AI 客户端”和“前端”等领域概念一无所知。所有这些都是由生态系统内的 Pack 定义的。官方只提供了**执行机制**。

### 没有基础的基础

Minecraft mods 修改了《Minecraft》的基础。但是，Rumi AI 没有可以修改的“身体”。所有应用程序功能均以 Pack 的形式实现，并使用 Flow 进行连接。

### 以流为中心的架构

使用 Flow 定义 Pack 之间的连接、顺序和安装后。无需修改现有包即可添加新功能。

```
          +---------------------------+
          |       Flow Definition     |
          +---------------------------+
                      |
          +---------------------------+
          |    python_file_call       |
          +---------------------------+
            /         |         \
    +--------+  +--------+  +--------+
    | Pack A |  | Pack B |  | Pack C |
    +--------+  +--------+  +--------+
            \         |         /
          +---------------------------+
          |         Kernel            |
          +---------------------------+
```

> **流导入源**：`flows/`、`user_data/shared/flows/`、`ecosystem/<pack_id>/backend/flows/`

### 故障软化

发生错误时系统不会停止。发生故障的组件将被禁用并记录在诊断信息中以继续。

### 基于恶意Pack的安全性

该生态系统的设计前提是它可以由第三方创建，也可能存在恶意作者。

- **需要批准**：未经批准的包中的任何代码都不会被执行。
- **哈希验证**：如果文件在批准后被修改，则自动失效（需要重新批准）
- **Docker 隔离**：批准的包在容器中运行（严格模式）
- **出口代理**：仅代理通过 UDS 套接字允许外部通信
- **能力（信任+授予）**：通过两步审批控制主机权限

要在现有环境中重新签名没有 HMAC 签名的配置文件：

```bash
python -m rumi_ai migrate-hmac
```

---

## 项目结构

<details>
<summary>目录树（点击展开）</summary>

<pre><code>
项目根目录/
├── 应用程序.py
├── bootstrap.py
├── 需求.txt
├── 需求-dev.txt
│
├── 流动/
│ └── 00_startup.flow.yaml
│
├── core_runtime/
│ ├── 内核.py
│ ├── kernel_core.py
│ ├── kernel_handlers_system.py
│ ├── kernel_handlers_runtime.py
│ ├── 路径.py
│ ├── 诊断.py
│ ├── 接口_registry.py
│ ├── event_bus.py
│ ├──audit_logger.py
│ ├── install_journal.py
│ ├── 审批管理器.py
│ ├── network_grant_manager.py
│ ├── egress_proxy.py
│ ├── rumi_syscall.py
│ ├── 系统调用.py
│ ├── Capability_proxy.py
│ ├──capability_executor.py
│ ├── Capability_trust_store.py
│ ├── Capability_grant_manager.py
│ ├──capability_installer.py
│ ├── rumi_capability.py
│ ├── python_file_executor.py
│ ├── secure_executor.py
│ ├──container_orchestrator.py
│ ├── component_lifecycle.py
│ ├── host_privilege_manager.py
│ ├── pack_api_server.py
│ ├── flow_loader.py
│ ├── flow_modifier.py
│ ├── flow_composer.py
│ ├── flow_scheduler.py
│ ├── function_alias.py
│ ├── vocab_registry.py
│ ├── 共享字典/
│ │ ├── 快照.py
│ │ ├── 日记.py
│ │ └── 解析器.py
│ ├── core_pack/
│ │ ├── core_store_capability/
│ │ ├── core_secrets_capability/
│ │ ├── core_flow_capability/
│ │ ├── core_communication_capability/
│ │ └── core_docker_capability/
│ ├── function_registry.py
│ ├── crypto_utils.py
│ ├── lib_executor.py
│ ├── pip_installer.py
│ ├── pack_importer.py
│ ├── pack_applier.py
│ ├── Secrets_store.py
│ ├── store_registry.py
│ ├── unit_registry.py
│ ├── unit_executor.py
│ ├── unit_trust_store.py
│ ├── hierarchy_grant.py
│ ├── lang.py
│ └── 权限管理器.py
│
├── backend_core/
│ └── 生态系统/
│ ├── 兼容.py
│ ├── 坐骑.py
│ ├── 注册表.py
│ ├── active_ecosystem.py
│ ├── 初始化器.py
│ ├── uuid_utils.py
│ └── json_patch.py
│
├── 生态系统/
│ ├── <pack_id>/
│ │ └── 后端/
│ │ ├── 生态系统.json
│ │ ├── 权限.json
│ │ ├── 需求.lock
│ │ ├──routes.json
│ │ ├── 块/
│ │ ├── 流动/
│ │ ├── 组件/
│ │ ├── 库/
│ │ ├── 分享/
│ │ ├── vocab.txt
│ │ └── 转换器/
│ └── 包/
│ └── <pack_id>/...
│
├── 用户数据/
│ ├── 审核/
│ ├── 权限/
│ │ ├── 审批/
│ │ ├── 网络/
│ │ ├── 能力/
│ │ └── .secret_key
│ ├── 秘密/
│ ├── 包/
│ ├── 能力/
│ │ ├── 处理程序/
│ │ ├── 信任/
│ │ └── 请求/
│ ├── 点/
│ ├── pack_staging/
│ ├── pack_backups/
│ ├── 共享/
│ │ └── 流动/
│ │ └── 修饰符/
│ ├──待定/
│ │ └── 摘要.json
│ ├── 店铺/
│ └── 设置/
│ ├── 共享字典/
│ └── lib_execution_records.json
│
├── rumi_setup/
│ ├── 核心/
│ ├── cli/
│ ├── 网页/
│ ├── 指南/
│ └── 默认值/
│
├── 郎/
│ ├── en.txt
│ └── ja.txt
│
├── 测试/
│ ├── test_capability_installer.py
│ ├── test_capability_system.py
│ ├── test_ecosystem_phase1.py
│ ├── test_ecosystem_phase2.py
│ ├── test_ecosystem_phase3.py
│ ├── test_ecosystem_phase4.py
│ ├── test_ecosystem_phase5.py
│ ├── test_ecosystem_phase6.py
│ ├── test_egress_audit.py
│ ├── test_flow_resolution.py
│ ├── test_inbox_and_patches.py
│ ├── test_pip_installer.py
│ ├── test_secure_execution.py
│ └── test_shared_dict.py
│
└── 文档/
    ├── 建筑.md
    ├── pack-development.md
    ├── 操作.md
    └── 路线图.md
</code></pre>

</details>

### 主目录

|目录 |角色 |
|---|---|
| `core_runtime/`|内核——流程执行引擎、安全性和权限管理|
| `core_runtime/shared_dict/`|共享词典系统（快照日志）|
| `core_runtime/core_pack/`|官方能力实施（Store、Secrets、Flow、Communication、Docker）|
| `backend_core/ecosystem/`|生态系统基础——包/组件加载/初始化|
| `ecosystem/`|包装存储（外部供应）|
| `user_data/`|运行时持久数据（审核日志、批准、机密、存储）|
| `rumi_setup/`|设置帮助（CLI / Web / 指南）|
| `flows/`|官方流程（启动/基础）|
| `lang/`|多语言消息 |
| `tests/`|测试|
| `docs/`|文件|

### 主要文件

|文件|角色 |
|---|---|
| `app.py`|操作系统入口点|
| `bootstrap.py`|设置入口点 |
| `kernel.py`| Mixin 组装/处理程序注册 |
| `kernel_core.py`|流程执行引擎本体 |
| `python_file_executor.py`| `python_file_call` 执行 |
| `secure_executor.py`| Docker隔离执行 |
| `approval_manager.py`|包审批管理 |
| `capability_proxy.py`|能力代理服务器（UDS）|
| `egress_proxy.py`|外部通信代理（UDS） |
| `flow_loader.py`|流 YAML 加载器 |
| `flow_modifier.py`|流动改性剂应用|
| `pack_importer.py`|打包导入（zip/文件夹→暂存）|
| `pack_applier.py`|打包申请（暂存→生态系统） |

## 查看器图表编辑器

控制面板的规范前端源位于`../rumi_viewer/frontend`。
`core_runtime/core_pack/core_control_panel/web` 包含由 `/panel/` 处的内核提供服务的内置静态工件。

及时行为存在于`ecosystem/defaultspack/domain/prompt/`和`ecosystem/defaultspack/blocks/prompt/`中。工具行为位于`ecosystem/defaultspack/domain/tool/`和`ecosystem/defaultspack/blocks/tool/`中。旧的顶级`prompt/`、`tool/`和`supporter/`导入垫片已被删除；新的类似支持者的行为应该作为默认包函数、代理、提示、内存或扩展来实现。

`../rumi_viewer/frontend/src/pages/Flows.tsx` 中的图形编辑器被视为具有可扩展图形元数据的编辑器，而不是专门用于包的固定 UI。

- 起始节点为`rumi_start`
- 节点可以有多个端口
- 一个端口可以容纳多个`contracts`
- 与`contracts`不匹配的端口不能相互连接。
- 将`rumi_graph`保存在YAML中并在查看器端恢复结构

这种设计使得可以通过在 Pack 端定义具有不同输入/输出契约的节点来表达转换角色，而无需添加专用于转换的特殊功能。

## 基础包

添加`ecosystem/setup_pack/basepack/pack.json`以允许Rumi AI选择`basepack`作为图优先的基本启动配置文件。目前，我们将现有的`defaultspack`视为要启动的精简引导程序配置文件，并安全地部署它，而无需增加巨大的重复包。

---

## 快速开始

### 要求

-Python 3.10+
- Docker（生产环境所需）
- git

### 安装

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10
python bootstrap.py --cli init
```

### 开始

```bash
# 本番（Docker 必須）
python app.py

# 開発（Docker 不要）
python app.py --permissive
```

### 包批准

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 文件

|文件|内容 |
|---|---|
| [docs/architecture.md](./docs/architecture.md)|设计及机构整体图|
| [docs/pack-development.md](./docs/pack-development.md)|包开发指南 |
| [docs/pack-development-guide.md](./docs/pack-development-guide.md)| Pack开发快速入门|
| [docs/operations.md](./docs/operations.md)|操作指南|
| [docs/roadmap.md](./docs/roadmap.md)|路线图 |
| [docs/quality_pack/philosophy_memo.md](docs/quality_pack/philosophy_memo.md)|用于开发决策的思考笔记|
| [docs/quality_pack/claude_desktop_quality_pack.md](./docs/quality_pack/claude_desktop_quality_pack.md)|质量保证/审核/回归验证包|

---

## 许可证

麻省理工学院许可证
有关详细信息，请参阅存储库根目录中的 LICENSE。
## defaultspack 真相来源

此存储库中规范的 defaultspack 实现是
`ecosystem/defaultspack/`。旧的`ecosystem/defaults/`路径和单独的路径
`harupipipipi/rumiai_defaults`存储库是兼容性或快照源。
新的本地优先运行时行为应该与旧版本一起出现在默认包中
在需要时将别名委托给它。

defaultspack 运行时设计为无需云 API 密钥或外部启动即可启动
网络访问。其保证默认模型为`stub/default`；云提供商
是可选的，必须明确选择/配置。本地文件、终端、
并且 git 突变受到本地请求保护的保护，一次性签名
批准令牌和编辑的审计记录。
