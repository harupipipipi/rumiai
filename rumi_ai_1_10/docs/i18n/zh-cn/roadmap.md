<!-- docs-i18n-links:start -->
[EN](../../roadmap.md) | [JP](../ja/roadmap.md) | [KR](../ko/roadmap.md) | [CN](./roadmap.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 路线图

## 🚀 第五阶段：Rumi Viewer + Pack 桌面应用程序【最重要/最高优先级】

> **此阶段优先于所有其他任务。**
> 最重要的里程碑是使 Rumi 能够作为“无终端桌面应用程序”进行分发。

### 架构概述

**安装程序的内容（分发给用户）：**

1. **Rumi Console**（rumi-launcher、Rust）—驻留在托盘中。内核进程管理。用户通常不知道这一点。
2. **Rumi Viewer** (Tauri) — 一个显示 Pack 前端的通用 WebView 应用程序。用户日常使用的主要应用程序。
3. **bundled/uv** — 用于构建Python环境。
4. **app/** (rumi_ai_1_10/) — 内核源代码。**什么是 Rumi Viewer：**
- 使用 Tauri 创建的通用 WebView 应用程序
- 显示`web_mount`中Pack声明的前端（HTML/CSS/JS）
- 只能连接到内核 API (localhost:8765)。我无法访问外部网站
- Pack 只传递前端文件。不碰宿主环境（沙盒WebView）
- Pack 后端在 Docker 容器中隔离运行
- 双重隔离，“前端=沙箱WebView”+“后端=Docker隔离”

**安全模型：**
- 需要`viewer:display`功能才能在查看器中显示某些内容（基于功能的权限管理）
- 只要您有权限，查看器就可以在任何包中使用
- `core_viewer_capability`与`core_docker_capability`和`core_communication_capability`具有相同的位置
- Packs 可以提供自己的桌面应用程序（Tauri/Electron 等），但这将被视为“有风险的权限”（`desktop_app.execute`），并且需要明确的用户批准。
- 大多数包应使用安全的查看器路径。

**用户体验：**
1. 用户使用安装程序（.dmg/.exe）安装
2.双击Rumi Viewer
3. Rumi Console自动启动→内核在后台启动
4. 控制面板显示在查看器中
5. 安装Pack → Pack的前端如AI聊天将显示在Viewer中。
6. 完全不要触摸终端

**启动流程：**
```
Rumi Viewer 起動
  → Kernel ヘルスチェック（localhost:8765/health）
  → 未起動なら Rumi Console を自動起動
  → Kernel ready を待機
  → Viewer が localhost:8765/panel/ を WebView に表示
  → ユーザーが Pack を選択 → Pack のフロントエンドに遷移
```

**冲突/错误处理：**
- 可以使用 Rumi Console（托盘图标）显示和处理冲突和启动错误
- 查看器仅用于显示

### TODO（按执行顺序）

**阶段 V-1：创建新的 Rumi 查看器（Tauri）** [最重要/最高优先级]
- [ ] `rumi_viewer/` 创建一个新的 Tauri 项目
- [ ] 内核健康检查 + 自动启动（通过 Rumi 控制台）
- [ ] 在 WebView 中显示 localhost:8765/panel/
- [ ] 包切换 UI（在查看器中导航）
- [ ] 仅允许对内核 API 的请求（外部 URL 块）
- [ ] 窗口管理（可同时打开多个包）

**阶段 V-2：core_viewer_capability 新创建**
- [ ]`core_runtime/core_pack/core_viewer_capability/`创建新的
- [ ]`viewer:display`能力定义
- [ ] 授予 Pack 管理权限以在查看器中显示前端
- [ ] 查看器的 pack_token 发行 API (`/api/viewer/token`)

**阶段 V-3：安装程序集成**
- [ ] 将 Rumi Viewer 添加到 Packager.toml
- [ ] 更新release.yml（添加查看器版本）
- [ ] 在安装程序中包含所有 Rumi Console + Rumi Viewer + 捆绑/uv + app/
- [ ] macOS：将这两个应用程序包含在 .dmg 中
- [ ] Windows：使用 NSIS + 开始菜单注册安装两者

**阶段 V-4：兼容桌面应用程序包（可选）**
- [ ] 将`desktop_app`部分添加到ecosystem.json
- [ ] 可以用`desktop_app.command`声明任意命令
- [ ]`desktop_app.execute`能力（危险权限，需要明确授权）
- [ ] pack-shell 二进制文件（内核自动启动+令牌获取+命令执行）
- [ ] .app / .lnk 生成 (PackAppRegistrar)

**阶段 V-5：文档 + 模板**
- [ ]`docs/pack_desktop_app_guide.md`创建新的
- [ ] Tauri Pack 模板项目
- [ ] 示例包（AI聊天前端）

---


最后更新: 2026-02-24

这是一个完整的路线图，包括设计理念和过去的计划。完整设计请参见[architecture.md](./architecture.md)。

---

## 0.北极星（愿景）

- **没有基础设施的基础**：正式版没有领域概念（聊天/工具/提示/UI等），仅提供“执行、审批、隔离、审计、权限”等类似OS的机制。
- 生态系统假设为第三方创建（恶意假设），核心是**需要审批**、**Docker隔离（严格推荐）**、**Fail-soft**、**审计日志**。

---

## 1. 设计原则

### 1.1 不偏袒

官方核心没有解释“API key”、“工具”、“聊天”等含义。官方提供的通用机制：流程执行、授权门（哈希验证）、隔离执行（Docker/UDS）、Trust + Grant（能力）、审计日志。

### 1.2 恶意前提（威胁模型）

Pack 始终假设作者有恶意的可能性。包执行基本上是 Docker `--network=none`。外部通信和主机权限被分配给能力（信任+授予）。

### 1.3 软故障

即使某一部分损坏，整个操作系统也不会停止。可视化并继续诊断和审核。

### 1.4 主机权限的单一入口点

主机上的危险事情（外部通信、文件访问、更新应用程序、终端等）不是Pack直接完成的，而是通过能力中介的，未经许可不能完成。

---

## 2.概念组织

### 2.1 包/主体/能力

- **校长**：权威决定的主体。 v1基于pack_id单元以简化操作。
- 通过`permission_id`请求能力并通过信任（sha256）和授予（主体×许可）授予能力。

### 2.2 包中包（分层）

如`parent__child`中，层次结构由pack_id表示，较高级别限制较低级别（较低级别不会移动，除非较高级别允许）。

目的：捆绑分发、运营一体化管理、父子权限约束。

> 注意：目录层次≠安全边界。执行力由“主机侧门（能力/执行装置）”来保证。

### 2.3 商店/单元（共享区域和重复使用单元）

用户/生态系统可以任意创建的共享区域（Store）以及该区域内的可重用单元（Unit）作为通用平台是有价值的。单位可以是`data / python / binary`等。执行单位基于Pack批准+单位信托（sha256白名单）。

可以根据权限选择（不更正）执行模式：包容器、主机功能、专用沙箱（将来）。

---

## 3.官方核心基金会列表

### 3.1 依赖（pip）介绍

套装包括`requirements.lock`。仅wheel 是默认值（sdist 被批准为例外）。在构建器容器中，下载→安装（离线安装）。在运行时，使用 RO mount + PYTHONPATH 显示站点包（容器维护 network=none）。

### 3.2 能力处理人候选介绍（审批流程）

候选人已包含在生态系统中。扫描→待处理→批准/拒绝→阻止（拒绝3次）。批准信托注册+复制+注册表重新加载。冷却时间1小时，被封锁直到解除封锁才会通知。

### 3.3 秘密（保存 API 密钥）

避免`.env`（降低事故率）。存储在`user_data/secrets/`中，不输出值到日志。不要向 Pack 展示您的秘密文件。获取基本上是通过能力（例如`secrets.get`）。

### 3.4 包分发格式

输入 3 格式：文件夹 / `.zip` / `.rumipack`（zip 兼容）。推荐：一包根在上面。将来可以扩展到多包存档（包中包）。

### 3.5 更新应用程序（禁止自动更新）

正式版不会自动更新。获取→分期→应用分离。由于 apply 很危险，我想将其移至功能 (`pack.update`)（v1 也可以用作操作 API）。首先应用单个 pack_id。

### 3.6 执行（Python/二进制）

Pack的正常执行是在Docker隔离中建立的，所以即使主机没有Python（只要有Docker）也可以。对于在主机上运行的东西（功能处理程序等），将来有必要使 Rumi 本身成为单个可执行文件（包括 Python）或使处理程序成为每个操作系统的二进制文件（两者都是可能的）。

---

## 4.实施情况

在此路线图中，每个项目都在以下状态下进行管理。

|符号|意义|
|------|------|
| ✅ |完成（实施/运行）|
| 🟡 |部分（已有基础/需要改进）|
| 🧩 |计划（计划/未实施）|
| 🧪 |实验性（稍后进行实验/确定规格）|

> 注意：此处不执行真实存储库状态的自动验证。如有必要，稍后制作一份清单。

---

## 5. v1（当前到最近）：完成可操作的操作系统（官方核心）

### 5.1 安全执行/批准/审核（基础）

- ✅ 包批准（哈希验证、修改检测、阻止）
- ✅ 审核日志（按类别分类的 jsonl）
- ✅ Docker 隔离（严格推荐，宽容是警告）

### 5.2 pip依赖介绍（requirements.lock）

- ✅ 扫描 → 批准 → 使用构建器下载/安装
- ✅ 站点包 RO 安装 + PYTHONPATH
- 🟡 sdist异常（allow_sdist）操作的审计澄清（持续改进）

### 5.3 能力（信任+授予+候选人介绍）

- ✅ 候选人介绍流程（待定/批准/拒绝/阻止/冷却）
- ✅ 信任存储/授权管理器/执行器/代理（UDS）
- ✅ 委托人的拨款管理（HMAC 签名）
- 🟡 多平台二进制文件（信任扩展）是中期

### 5.4 秘密（纯文本OK，事故率降低）

- ✅ user_data/secrets（1 key = 1 file、tombstone、journal）
- ✅ API仅是列表（掩码）/设置/删除（不重新显示）
- ✅ 不要将值输出到日志（审计和诊断）
- ✅`secrets.get`rate_limit=60（预防事故）
- ✅ get_secret() 辅助函数 (rumi_capability.py) — Wave 2 #32
- 🧩 v1.1：操作系统钥匙串（钥匙圈/DPAPI 等）将被推迟

### 5.5 包导入（文件夹/zip/rumipack）

- ✅ 导入文件夹/zip/rumipack
- ✅ Zip 结构需要“顶级单个目录”
- ✅ 防止拉链/尺寸限制等。
- ✅ 分期 → 应用（带备份）
- ✅防止pack_identity不匹配更换（预防事故）

### 5.6 分级权限（主机 > 父级 > 子级）

- ✅ 假设 pack_id `parent__child` 解析父链
- ✅ 即使孩子允许，如果父母不允许，也会被拒绝。
- ✅ 父配置与子配置的交集

### 5.7 流程执行对齐

- ✅ 统一解决异步路由和管道路由的`kernel:*`
- ✅ 更正了启动流程中 packs_dir 等的一致性
- ✅ _eval_condition 解析器改进（支持值中的 == / !=）— Wave 1 #16
- ✅ _resolve_value 递归深度限制 (MAX_RESOLVE_DEPTH=20) — Wave 1 #70
- ✅ 流链深度限制 (MAX_FLOW_CHAIN_DEPTH=10) — 第 1 波 #58

### 5.8 安全增强（第 1 波）

- ✅ 需要加密（删除 Base64 后备）— #1
- ✅ API 服务器绑定地址限制（默认 127.0.0.1） — #3
- ✅ 主机执行超时（ThreadPoolExecutor，120 秒）— #4
- ✅ 统一 pack_id 验证 (^[a-zA-Z0-9_-]{1,64}$) — #9
- ✅ 存储 root_path 路径遍历预防 — #5, #12
- ✅ 容器名称 UUID（避免碰撞）— #10
- ✅ Docker 标准输出大小限制 (4MB) — #14
- ✅ Docker 可用性缓存（60 秒 TTL）— #17
- ✅ DNS 重新绑定缓解 (egress_proxy) — #13
- ✅ egress_proxy 线程池 — #33
- ✅ HMAC 签名逻辑集成 (HMACSigner) — #65
- ✅ HMAC 密钥文件原子写入 — #34
- ✅ 通配符域名警告 — #31
- ✅ API 错误消息隐藏 — #35
- ✅ 文件名验证 (secure_executor) — #57
- ✅ pack_import 路径遍历预防 — #30
- ✅ 删除路由冲突解决方案 — #59

### 5.9 加强生态系统基础设施（第一波）

- ✅ 流量修改器通配符警告/空运行模式 — #7、#40
- ✅ 未指定修饰符阶段时的默认行为 — #8
- ✅ 检测到重复的 pack_id — #15
- ✅ 连接需要未满足的警告 — #20
- ✅ 通配符修饰符审核日志 — #61
- ✅ 无偏袒：删除无用代码 (initializer.py)，中和文档字符串 — NF1-3

### 5.10 内部质量/开发平台（第 12-14 波）

- ✅ 测试丰富：test_egress_proxy(91+)、test_capability_installer(44+)、test_flow_modifier_regression(32+)、test_pack_api_server(53+)、test_store_registry(49+) — 第 12 波
- ✅ egress_proxy 增强（速率限制/域控制/细粒度超时）——第 12 波
- ✅validation.py（通用验证平台）——第 12 波
- ✅logging_utils.py（结构化日志记录：StructuredFormatter、StructuredLogger、CorrelationContext、get_structured_logger、configure_logging）—第 12 波
- ✅ 出口模块划分：egress_ip.py、egress_protocol.py、egress_rate_limiter.py、egress_domain_controller.py — 第 13 波
- ✅ 能力/修饰符模块划分：capability_models.py、flow_modifier_models.py、flow_modifier_loader.py — 第 13 波
- ✅ health.py（HealthChecker：磁盘空间/内存/文件可写探针）—第13波
- ✅metrics.py（MetricsCollector：计数器/仪表/直方图/计时器）—第 13 波
- ✅ error_messages.py (ErrorCode, RumiError, 错误代码系统 RUMI-{CAT}-{NNN}) — 第 13 波
- ✅ egress_proxy.py 重复删除 + 测试补丁修复 — 第 14 波
- ✅ profiling.py（探查器：上下文管理器/装饰器、p50/p95/p99、内存限制）—第 14 波
- ✅ types.py + py.typed（新类型：PackId / FlowId / CapabilityName / HandlerKey / StoreKey，结果通用，严重性枚举，PEP 561）—第14波
- ✅ pack_scaffold.py（PackScaffold CLI：4 个模板最小/功能/流程/完整，validation.py 集成）- 第 14 波
- ✅ deprecation.py（已弃用的装饰器、DeprecationRegistry、deprecated_class、RUMI_DEPRECATION_LEVEL 环境变量）— 第 14 波

### 5.11 内核集成/DI 扩展（第 15 波）

- ✅ kernel_core.py：日志记录→get_structed_logger，已弃用，已应用 types.py
- ✅ kernel_flow_execution.py：logging→get_structed_logger，使用Profiler进行流量测量，使用MetricsCollector进行步骤测量
- ✅ kernel_handlers_system.py：logging→get_structed_logger，MetricsCollector测量添加
- ✅ kernel_handlers_runtime.py：logging→get_structed_logger，MetricsCollector测量添加
- ✅ di_container.py：health_checker /metrics_collector / profiler的工厂注册（共32个服务）
- ✅ app.py：configure_logging() 调用，添加了 --health 标志

> 新环境变量：RUMI_LOG_LEVEL、RUMI_LOG_FORMAT、RUMI_DEPRECATION_LEVEL。新的 CLI 标志：--health、--validate。

---

## 6. v1.5 到 v2（中期）：即使在扩展时也能防止损坏的开发

### 6.1 商店/单元（共享区域和重复使用单元）

- ✅ 商店注册（多个商店，无固定路径）—`core_runtime/store_registry.py`已实施
- ✅ 单位注册表（数据/Python/二进制）—`core_runtime/unit_registry.py`已实施
- ✅ 单位信托商店（sha256 许可名单）— `core_runtime/unit_trust_store.py` 已实施
- 🟡 单元执行门（仅实现了 host_capability 模式。未实现包容器/沙箱） — `core_runtime/unit_executor.py`
- ✅ 存储比较和交换 (store.cas) — 基于 fcntl.flock — Wave 2 #6
- ✅ store.list 分页（限制/光标/前缀）— Wave 2 #18
- ✅ store.batch_get（最多 100 个键，900KB 限制）— Wave 2 #19
- ✅ 声明式 Store 创建（在 Ecosystem.json 中存储字段）— Wave 2 #62
- ✅ 包之间的商店共享（SharedStoreManager，手动批准）— Wave 2 #21
- 🧩“需要包批准，单元单独批准取决于单元设置（可以请求包）”的运营维护

> 这里没有使用“资产”一词。如果一个生态系统创建了一个“兼容重用的商店”，那么它就会被建立。

### 6.2 增强二进制对能力的支持（实现无需Python的操作）

- 🧩 handler.json 支持工件（通过 OS/arch）
- 🧩 信任存储扩展（handler_id → 多个 sha256）
- 🧩 执行器直接二进制执行（stdin JSON / stdout JSON）
- 🧩 与“将 Rumi 本身转换为单个可执行文件”的比较研究（UX/操作）

### 6.3 全面更新应用能力

- 🧩`pack.update`许可标准化（虽然其含义没有正式解释，但作为“危险操作的框架”）
- 🧩 通过能力应用操作并尽量减少对 API 的直接访问
- 🧩 版本历史/回滚（暂存/备份标准操作）

### 6.4 能力扩展（第 2 波）

- ✅ flow.run 功能（同步 Flow-to-Flow 调用、循环检测、深度限制）— Wave 2 #5
- ✅ 批量能力授予（最多 50 个，尽力而为）— 第 2 波 #63
- ✅ 调度程序时区支持（zoneinfo、UTC 回退）— Wave 2 #60

### 6.5 使用 vocab 组件输出键标准化（Pack 兼容层）

- 🧩 按组件类型自动标准化输出键
- 🧩 将vocab_registry中的同义词组+转换器集成到Flow执行路径中
- 🧩 标准化时间的标准化（存储 ctx 之前与引用时）
- 🧩 在 Pack 端使用 vocab.txt 开发同义词声明的推荐模式

#### 背景

第三方包开发中发现的问题。 kernel_core 的 _execute_handler_step_async 将 Flow 步骤的返回值存储在 ctx[step["output"]] 中。换句话说，如果默认 Pack 具有返回 {"content": "...", "model": "gpt-4"} 的结构，并且 Flow 引用 ${ctx.ai_response.content}，则当您将其替换为像另一个 Pack 一样返回 {"text": "...", "model_name": "..."} 的 Pack 时，内容在所有 Flow 步骤中都会变为 null 并中断。

vocab_registry已经有解决这个问题的机制，但是缺少“Flow执行路径中的自动应用”。

#### 拟议的实施计划

**方法 A（存储期间标准化 - 推荐）**：在将 ctx 存储到 kernel_core 之前，转换为 vocab_registry 中的首选术语。可以通过改变几行来利用现有机制。**方法 B（参考标准化）**：使用 _resolve_value 进行同义词回退。存储的数据没有改变，但解析路径复杂。**方法 C（选择加入规范化）**：规范化：流程步骤中的 true 标志或在组件清单中声明 output_vocab_group。对现有产品没有影响，但 Pack 作者需要意识到这一点。

### 6.6 内部重构（P3待定）

- 🟡 全局单例 → DI 容器迁移（内核集成/注册 32 个服务）— 第 15 波
- 🧩 将后端存储到 SQLite（基于文件的迁移选项）
- 🧩 pack_api_server.py 的大规模处理程序拆分（目前约为 80KB）
- 🧩 Docker 执行逻辑通用性（python_file_executor / secure_executor 集成）

---

## 7. v3（长期）：在生态系统之外应该实现

> v3 中的项目不会在官方核心中实现，而是作为生态系统（Pack）实现。
> 必须由第三方提供。公式就是实现这些功能。
> 我们已经提供了通用机制（API服务器、Store、Capability等）。

### 7.1 管理界面
- 管理UI可以作为Pack实现（调用pack_api_server API的前端Pack）
- 官方提供HTTP API。 UI是一个生态系统区域

### 7.2 外部认证联动
- Supabase 等的身份验证可以通过 Pack via Secrets + 功能来实现
- 官方不强制执行身份验证机制

---

## 8. 插件（已过时）

`backend_core/ecosystem/addon_manager.py` 中存在的基于 JSON 补丁的插件机制已被删除。 Flow Modifier 接管了这个角色。

---

## 9. 规则/操作（操作手册要点）

- 建议在生产环境中严格（需要 Docker）
- 秘密从不记录值
- 能力是信任+授予的两层组合
- pip依赖基本上是仅限轮子的，sdist是例外批准
- 更新不会自动应用（需要用户交互）
- 通过审核+诊断来跟踪跳过/拒绝

---

## 10.未来的问题（澄清未决定的事项）

- 官方会在多大程度上规范Store/Unit的运营和维护（只是一个框架还是加厚一点）？
- 单位的单独审批用户体验（旨在避免太多待处理项目）
- Pack容器/沙盒模式实现Unit执行门
- 无需Python的最短分发路径（主体统一与处理程序二进制化）
- 配置层级权限上限（交集定义：列表为交集，端口为最小等）
- 使用词汇进行输出密钥标准化的范围（所有步骤与选择加入与仅组件类型）
- 词汇同义词冲突解决（包A是内容=正文，包B是内容=整个HTML）
- 转换器的执行安全性（任意Python运行是否需要设置Trust？）
- 提供模式的一致性（模式是 ^[a-z][a-z0-9_]*$，但 pack-development.md 示例是 ai.client 且点分隔 - 这是正确的吗？）
- defaults_pack 集成（另一个团队正在进行中）
- 编译→应用（单个可执行文件分发）
- 文档维护（第 16 波进行中）

---

## 附录：重要的反模式（不要这样做）

- 在容器上安装秘密并让 Pack 读取它（立即失败）
- 官方有工具/聊天等固定概念（违反无偏袒）
- 自动更新（无需用户显式操作即可重写生态系统）
- 在审核日志中发出秘密值和可解密信息
