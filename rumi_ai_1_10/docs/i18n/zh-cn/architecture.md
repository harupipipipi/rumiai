<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](../ja/architecture.md) | [KR](../ko/architecture.md) | [CN](./architecture.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 架构

这是一份解释总体设计和机制的文档。另请参阅[pack-development.md](./pack-development.md)（有关包开发者）和[operations.md](./operations.md)（有关运营商）。

---

## 目录

1.【设计原则】(#设计原则)
2. [流程系统](#流程系统)
3. [python_file_call](#python_file_call)
4. [流量调节剂](#流量调节剂)
5. [安全模型](#安全模型)
6. [包装批准](#包装批准)
7. [网络权限和出口代理](#网络权限和出口代理)
8. [能力体系（信任+授予）](#能力体系（信任授予）)
9. [UDS 套接字权限](#uds套接字权限)
10. [等级权限](#hierarchy-authority)
11. [秘密](#秘密)
12. [共享词典](#共享字典)
13. [库系统](#库系统)
14.【pip依赖库介绍】(#pip-dependency-library-installation)
15.[Pack Import / Apply](#pack-import--apply)
16. [组件概念](#组件概念)
17.[vocab / converter](#vocab--converter)
18. [审核日志](#审核日志)
19. [待导出](#待导出)
20. [DI容器和服务清单](#di-container-and-service-list)
21. [内核Mixin配置](#内核混入配置)
22. [可观察性](#可观察性)
23. [通用基础设施模块](#通用基础模块)
24. [开发工具包](#包开发工具)
25. [已弃用的功能](#已弃用的功能)

---

## 设计原则

### 没有偏袒

官方核心没有领域概念（聊天、工具、提示、AI 客户端、前端等）。官方提供的是一个通用的执行平台。

官方提供的机制仅限于：流程执行、授权门（哈希验证）、隔离执行（Docker/UDS）、Trust + Grant（能力）和审计日志。

### 恶意假设（威胁模型）

Pack 始终假设作者有恶意的可能性。包执行通常在 Docker `--network=none` 中被隔离。外部通信和主机权限由能力（信任+授予）调节，未经明确许可将无法工作。

### 故障软化

即使某一部分损坏，整个操作系统也不会停止。失败的组件将被禁用并记录在诊断和审核中以继续。

### 主机权限的单一入口点

主机上的危险事情（外部通信、文件访问、更新应用程序等）不是直接从 Pack 执行的，而是通过能力进行调解。除非您允许，否则它不会移动。

---

## 流程系统

### 概述

Flow 是一个 YAML 文件，定义 Pack 之间的连接和执行顺序。每个流程由阶段和步骤组成。

### 流文件格式

```yaml
flow_id: ai_response
inputs:
  user_input: string
  context: object
outputs:
  response: string

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true
  on_missing_step: skip

steps:
  - id: load_context
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"

  - id: call_ai
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_response
```

### 流量来源

流按以下顺序加载：在相同`flow_id`的情况下，具有较高优先级的获胜（较低的源不能覆盖较高源的流）。

|优先|路径|用途 |批准 |
|--------|------|------|------|
| 1 | `flows/`|官方流程（启动/基础）|不需要|
| 2 | `user_data/shared/flows/`|由用户/外部工具放置的共享流程 |不需要|
| 3 | `ecosystem/<pack_id>/backend/flows/`| Pack | 提供的流程需要包装批准 |
| 4 | `ecosystem/flows/`（已弃用）| local_pack 兼容流程 |仅当`RUMI_LOCAL_PACK_MODE=require_approval`时有效。需要批准 |

覆盖规则：官方流程不能被任何人覆盖。共享流不能覆盖官方流，但它们优先于 Pack 提供的流。包提供的流程不能被覆盖，无论是官方的还是共享的。 local_pack 具有最低优先级，不能覆盖任何其他源。

### 步骤类型

|类型 |描述 |
|------|------|
| `handler`|调用内核处理程序 |
| `python_file_call`|运行 Pack 中的 Python 文件 |
| `set`|在上下文中设置值 |
| `if`|条件分支（简化版）|
| `function`|执行在FunctionRegistry中注册的函数（第27波） |
| `flow`|调用另一个流作为子流 |

### 执行顺序

步骤按以下顺序确定性排序：

1.`phase`（`phases`数组中的排序顺序）
2.`priority`（升序；较小的先执行）
3. `id`（按字母顺序排列。抢七）

### 变量引用

```yaml
input:
  user_id: "${ctx.user.id}"     # ネスト参照
  settings: "${ctx.config}"      # オブジェクト全体
```

如果参考目标不存在，它将被视为`null`（软失败）。

---

## python_file_call

### 概述

将包中的 Python 文件作为流程中的步骤运行。接受输入并返回 JSON 兼容输出的“块”。

### 块文件格式

```python
# ecosystem/<pack_id>/backend/blocks/my_block.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ
        context: 実行コンテキスト
            - flow_id, step_id, phase, ts
            - owner_pack
            - inputs
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> ProxyResponse

    Returns:
        JSON 互換の出力データ
    """
    return {"message": "Hello from my_block!"}
```

### 路径解析

`python_file_call`中的`file`字段是相对于pack_subdir解析的。按顺序搜索以下候选人：

1.`<pack_subdir>/blocks/`
2.`<pack_subdir>/backend/blocks/`
3.`<pack_subdir>/backend/components/`（兼容）
4.`<pack_subdir>/backend/`（兼容：直接安装）
5.`<pack_subdir>/<file>`（最终后备）

所有候选者都被限制在 pack_subdir 边界内。超出边界的文件将被拒绝执行。

### 安全检查（执行前）

1.`owner_pack`获得批准
2.`owner_pack`的哈希值必须匹配（未修改）
3. 文件路径必须在pack_subdir边界内

### 处理principal_id (v1)

在 v1 中，`principal_id` 总是被迫被`owner_pack` 覆盖。即使您在流定义中指定`principal_id`，`owner_pack`也将在运行时使用。这是防止滥用职权的措施。警告在审核日志中记录为`principal_id_overridden`。

---

## 流量调节器

### 概述

这是一种允许您稍后将步骤注入、替换或删除到现有流程的机制。即使包彼此不认识，修饰符也允许您插入功能。

### 修改器文件格式

```yaml
modifier_id: tool_inject
target_flow_id: ai_response
phase: prepare
priority: 50
action: inject_after
target_step_id: load_context

requires:
  capabilities:
    - tool_support
  interfaces:
    - tool.registry

step:
  id: inject_tools
  type: python_file_call
  owner_pack: capability_provider
  file: blocks/capability_selector.py
  input:
    context: "${ctx.context}"
  output: selected_capabilities
```

### 修饰符放置路径

修改器应放置在下面，文件名为 `*.modifier.yaml`：

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`（如果包提供）

### 行动

|行动|描述 |目标步骤 ID |步骤|
|--------|------|----------------|------|
| `inject_before`|在指定步骤之前插入 |必填 |必填 |
| `inject_after`|在指定步骤后插入 |必填 |必填 |
| `append`|添加到阶段结束 |不需要|必填 |
| `replace`|替换指定步骤 |必填 |必填 |
| `remove`|删除指定步​​骤 |必填 |不需要|

### 需要条件

```yaml
requires:
  interfaces:
    - "ai.client"           # InterfaceRegistry に登録されているか
  capabilities:
    - "tool_support"        # capability が有効か
```

如果不满足条件，则跳过修改器（软失败）。

### 申请顺序

1.`phase`顺序
2.`priority`升序
3.`modifier_id`升序

### resolve_target（使用共享字典解析）

```yaml
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

如果指定了`resolve_target: true`，则`target_flow_id`将在应用之前在共享字典中解析。

---

## 安全模型

### 安全模式

使用环境变量`RUMI_SECURITY_MODE`进行设置。

|模式|码头工人 |行为 |
|--------|--------|------|
| `strict`（默认）|必填 |如果 Docker 不可用则拒绝执行 |
| `permissive`|不需要|允许主机执行并发出警告（用于开发） |

### 保护机制列表

|机制|描述 |
|------|------|
|审批门|未经批准的包中的任何代码都不会被执行 |
|哈希验证 |文件批准后修改自动失效|
| HMAC 签名 |检测到授予文件篡改 |
|路径限制|拒绝在 pack_subdir 边界之外执行文件 |
| Docker 隔离 | `--network=none`、`--cap-drop=ALL`、`--read-only`|
|出口代理 (UDS) |使用特定于包的白名单控制外部通信 |
| UDS 组添加 |使用专用 GID 管理套接字权限 |
|审核日志|记录所有操作 |
|要求.锁验证 |供应链攻击预防|
|包身份验证 |更新包时防止混淆 |
| DNS 重新绑定措施 | DNS解析结果内部IP检查|

### 威胁与对策

|威胁|对策|
|------|------|
|恶意代码执行 |需要授权+Docker隔离 |
|文件篡改 | SHA-256 哈希验证 |
|设置篡改 | HMAC 签名 |
|无效的外部通信 |出口代理 + 白名单 |
|权限提升 | Pack 显式授予 |
|供应链攻击| requirements.lock 语法限制 + 仅滚轮 |
|包装混淆|被 pack_identity 比较拒绝 |
| DNS 重新绑定 |内部IP检查解析结果|

---

## 包批准

### 审批流程

```
Pack 配置 (ecosystem/<pack_id>/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
ユーザー承認
    ↓
全ファイルの SHA-256 ハッシュを記録
    ↓
初めてコード実行可能に
```

### 批准状态

|状态 |代码执行 |描述 |
|------|-----------|------|
| `installed`| ❌ |已放置，未经批准 |
| `pending`| ❌ |等待审批|
| `approved`| ✅ |已批准 |
| `running`| ✅ |已批准并运行 |
| `modified`| ❌ |批准后检测文件更改 |
| `blocked`| ❌ |被拒绝 |
| `error`| ❌ |发生错误（审批过程失败等）|

当文件修改导致`modified`状态时，代码执行和网络权限将自动禁用。需要重新授权。

### 包存放路径

包可以放置在以下路径之一：

|路径|类型 |描述 |
|------|------|------|
| `ecosystem/<pack_id>/`| **推荐** | `paths.py`是探索的重中之重|
| `ecosystem/packs/<pack_id>/`|遗产|如果与推荐路径重叠则忽略 |

`paths.py` 中的`discover_pack_locations()` 首先搜索`ecosystem/*`，然后搜索`ecosystem/packs/*` 作为兼容路由。如果两者中存在相同的`pack_id`，则`ecosystem/<pack_id>/`优先。

---

## 网络权限和出口代理

### 设计

包无法直接与外部通信（Docker `--network=none`）。所有外部通信均通过 UDS 套接字通过 Egress 代理。

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部 API
                                        ↓
                                  network grant 確認
                                        ↓
                                    監査ログ記録
```

### 基于 UDS 的包识别

为每个包创建一个 UDS 套接字，并根据套接字路径确定`pack_id`。请求负载中的`owner_pack`字段被忽略（安全措施）。

### 网络资助

```json
{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": ["api.openai.com", "*.anthropic.com"],
  "allowed_ports": [443],
  "granted_at": "2024-01-01T00:00:00Z",
  "granted_by": "user",
  "_hmac_signature": "..."
}
```
域匹配支持精确匹配（`api.openai.com`）和通配符（`*.anthropic.com`）。如果您想允许子域，请使用通配符格式明确指定它们。

### Egress Proxy防御机制

内部IP禁止（localhost/private/link-local/CGNAT/multicast等）、DNS重新绑定措施（如果解析结果是内部IP则拒绝）、重定向限制（3跳，每跳重新检查授权）、请求/响应大小限制（1MB/4MB）、超时限制（最长120秒）、标头数量/大小限制、方法限制（GET、HEAD、POST、PUT、DELETE、PATCH）。

### 第 12-14 波扩展

#### 速率限制 (egress_rate_limiter.py)

在第 12 波中添加。通过每包令牌桶提供请求速率限制。在出口代理接受请求之前，它会检查存储桶并在存储桶耗尽时返回`429`。

#### 域控制（egress_domain_controller.py）

在第 12 波中添加。除了许可名单之外，它还提供基于每个域的细粒度控制（阻止列表、通配符模式）。

#### 细粒度超时

在第 12 波中添加。现在可以为每个域设置连接超时和读取超时。保留旧的全局上限（120 秒）作为后备。

#### 模块划分（第 13 波）

在第 13 波中，我们将出口代理实现分为以下模块。安全检查的执行顺序也按照以下顺序组织和评估：IP检查→协议检查→域检查→速率限制。

|模块|职责|
|-----------|------|
| `egress_ip.py`|内部IP检查、DNS重新绑定措施|
| `egress_protocol.py`|协议方法头检查|
| `egress_rate_limiter.py`|包单位速率限制 |
| `egress_domain_controller.py`|域白名单/黑名单控制 |

#### 重复代码删除 (W14-FIX)

在第14波中，我们删除了拆分后模块之间残留的冗余代码（IP检查逻辑等），并确保单一责任。

---

## 能力体系（信任+授予）

### 概述

这是一种用于批准 Pack 提供的功能处理程序并将其投入生产，并向主体授予使用权（授权）的机制。信托和赠款是独立管理的。

- **信任**：`handler_id` + `sha256` 的白名单。判断handler.py的内容是否可信
- **拨款**：`principal_id` × `permission_id` 拨款。管理谁可以使用哪些功能

### 整体流程

```
候補配置 (ecosystem/<pack_id>/share/capability_handlers/<slug>/)
    ↓
scan（候補検出）
    ↓
pending（承認待ち）
    ↓
approve（Trust 登録 + コピー + Registry reload）
    ↓
Grant 付与（principal × permission）
    ↓
使用可能
```

批准仅注册信任。实际使用需要单独拨款。

### 候选状态转换

|状况 |描述 |
|------|------|
| `pending`|候选人被发现并等待批准 |
| `installed`|得到正式认可的。信托登记+副本完成 |
| `rejected`|拒绝了。冷却后可以小睡（1 小时）|
| `blocked`|有 3 次拒绝的静默块。解锁之前不会收到通知 |
| `failed`|批准过程中发生错误 |

### 候选键

候选人身份在`candidate_key`中管理：

```
{pack_id}:{slug}:{handler_id}:{sha256}
```

通过包含 sha256，如果 handler.py 的内容发生更改，它将被视为不同的候选者。

### TOCTOU 措施

在批准时重新计算handler.py的sha256，并与扫描时的值进行比较。如果不匹配，批准将失败。

### 复制并覆盖

批准时，`ecosystem/`方的候选人将被复制到`user_data/capabilities/handlers/<slug>/`。生态系统方面仍然作为分布并且没有移动。如果复制目的地已经存在handler，并且handler_id或sha256不同，则会发生错误（禁止自动覆盖）。

### 模块划分（第 13 波）

在 Wave 13 中，与能力相关的模型和加载器已分为以下模块。

|模块|职责|
|-----------|------|
| `capability_models.py`|能力相关数据模型定义|
| `flow_modifier_models.py`| Flow Modifier相关数据模型定义|
| `flow_modifier_loader.py`|修改器文件加载/解析 |

### 与功能系统集成（A-D 阶段）

在 A 至 D 阶段，旧的`capability_handler_registry.py`被废除并并入`function_registry.py`（`FunctionRegistry`）。所有函数（内核处理程序、core_pack函数、Pack提供的函数）都在`FunctionRegistry`中注册，`capability_executor.py`统一执行它们。

#### 主要变化

`capability_handler_registry.py` 已被删除。或者，`core_runtime/function_registry.py`定义`FunctionRegistry`和`FunctionEntry`数据类。 `ManifestRegistry` 是`FunctionRegistry`（设计决策 D-6）的别名。

#### FunctionEntry 的关键字段

|领域 |类型 |描述 |
|-----------|-----|------|
| `function_id`| `str` |功能 ID |
| `pack_id`| `str` |联盟包 ID |
| `qualified_name`| `str`（属性）| `{pack_id}:{function_id}`（冒号分隔）|
| `calling_convention`| `Optional[str]` |执行方法。 7 种中的任何一种 |
| `permission_id`| `Optional[str]` |授权 ID（用于授权验证）|
| `entrypoint`| `Optional[str]` |入口点（例如`main.py:run`）|
| `risk`| `Optional[str]` |风险等级|
| `is_builtin`| `bool` |它是一个内置函数吗？ |
| `runtime`| `str` | `python` / `binary` / `command` |
| `handler_py_sha256`| `Optional[str]` | handler.py 中的 SHA-256（用于信任验证）|
| `vocab_aliases`| `Optional[List[str]]` |词汇别名（可在`resolve_by_alias()`中搜索）|
| `grant_config`| `Optional[Dict]` | Grant设置（非None时执行Grant验证） |

#### 调用约定（7 种）

|调用约定 |描述 |
|-------------------|------|
| `kernel`|直接作为内核处理程序运行。无法通过`capability_executor`执行 |
| `subprocess`|在子进程中执行（指定入口点） |
| `block`|通过 core_pack 的 DI 服务运行 |
| `python_host`|在主机 Python 中运行（需要`RUMI_ALLOW_HOST_EXECUTION=1`）|
| `python_docker`|在 Docker 容器中运行（默认）|
| `binary`|直接运行二进制文件 |
| `command`|执行任意命令 |

#### 内核函数

`kernel.py` 定义`_KERNEL_HANDLER_MANIFESTS`。 70 个（系统 29 + 运行时 41）处理程序在`register_kernel_function()`、`pack_id="kernel"`、`calling_convention="kernel"`和`FunctionRegistry`中注册。

#### 执行流程

```
capability_executor.execute(principal_id, request)
    ↓
FunctionRegistry で permission_id を解決（resolve_by_alias）
    ↓
_unified_execute(entry, principal_id, request)
    ↓
Trust チェック（sha256 検証）
    ↓
Grant チェック（grant_config が非 None のとき）
    ↓
calling_convention で分岐実行
```

---

## UDS套接字权限

### 问题

在严格模式下，Pack 执行容器以`--user=65534:65534`（无人）运行。如果 UDS 套接字保留默认的`0660` (root:root)，容器将无法连接到该套接字。

### 解决方案

通过设置专用 GID，您可以安全连接，同时保持`0660`。

|环境变量|描述 |默认 |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID`|出口套接字 GID |无 |
| `RUMI_CAPABILITY_SOCKET_GID`|功能套接字 GID |无 |
| `RUMI_EGRESS_SOCKET_MODE`|出口套接字权限 | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE`|能力 Socket 权限 | `0660` |

如果设置了 GID，则在 `docker run` 时将自动授予`--group-add=<GID>`。

这可以通过`RUMI_EGRESS_SOCKET_MODE=0666`/`RUMI_CAPABILITY_SOCKET_MODE=0666`来缓解，但已被弃用，因为它允许任意用户连接到套接字。

---

## 权限分级

### 概述

通过将`pack_id`更改为`parent__child`，您可以表达具有父子关系的Pack。如果允许子级但不允许父级，则执行将被拒绝。

父级的配置为子级设置上限（交集）。即使只允许下级，如果上级不允许的话也是不行的。

---

## 秘密

安全地管理 API 密钥等秘密值。

- 未使用`.env`（降低事故率）
- 存储在`user_data/secrets/`中（1个密钥= 1个文件、墓碑、日志）
- 不要在日志中显示任何秘密值（审计和诊断）
- 不要直接向 Pack 显示秘密文件
- 通过能力获得（例如`secrets.get`）
- API仅是列表（带掩码）/设置/删除（不重新显示）

---

## 共享字典

### 概述

这是一种允许您重写任何`namespace`/`token`的机制。官方不解释命名空间的含义（生态系统可以自由决定）。

### 安全功能

- **循环检测**：自动拒绝A→B→A等循环
- **冲突检测**：为同一令牌注册不同值的尝试将被拒绝
- **跳数限制**：默认 10 跳后中止解析
- **审核日志**：记录所有操作

### 坚持

`snapshot.json`（快照）和`journal.jsonl`（日志）保存在`user_data/settings/shared_dict/`中。

---

## 库系统

### 概述

管理包初始化和更新处理。它不是常驻的，仅在需要时执行。

### 执行时序

|状况 |要执行的文件 |
|------|-------------------|
|第一次介绍（无记录）| `lib/install.py`|
|更改哈希 | `lib/update.py`（如果不是`install.py`）|
|没有变化|别跑|

### Docker 隔离

在严格模式下，它在 Docker 容器内隔离运行。 `--network=none`、`--cap-drop=ALL`、`--read-only`、`--memory=256m`。 RW 安装仅限`user_data/packs/{pack_id}/`（在容器中：`/data`）。

---

## pip依赖库安装

### 概述

包可以通过包含`requirements.lock`来声明对 PyPI 包的依赖关系。一旦用户通过 API 授权，它就会被安全地下载并安装到构建器的 Docker 容器中。宿主Python环境不脏。

### requirements.lock约定

仅允许`NAME==VERSION`行（允许注释/空行）。禁止使用以下内容：`-e`（可编辑）、`git+`/`http://`/`https://`（URL/VCS 引用）、`file:`/`../`/`/`（本地引用）、`--`可选行、`@`直接引用。

### 状态转换

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### 安全

仅轮子是默认设置（`--only-binary=:all:`）。如果需要 sdist，请在批准时指定`allow_sdist: true`。构建器容器（下载）在`--network=bridge` + `--cap-drop=ALL`中运行，构建器容器（安装）在`--network=none`中运行（完全离线）。从执行容器，站点包以只读方式安装（`/pip-packages:ro`）并添加到`PYTHONPATH`。

### index_url 约束

`https` 仅允许方案。如果主机名是 localhost / 127.0.0.1 / ::1 / private IP / link-local，则被拒绝。

---

## 打包导入/应用

### 导入

将包从文件夹 /`.zip` / `.rumipack`（zip 兼容）放入暂存。诸如“需要单个顶级目录”和拉链/大小限制之类的保护适用于 zip 结构。

### 申请

适用于从分期到生态系统。将自动创建备份。申请时，会对`pack_id`和`pack_identity`（`ecosystem.json`的`pack_identity`字段）进行比较，如果与现有包不匹配，则会被拒绝。

---

## 组件概念

### 概述

`backend_core/ecosystem/registry.py` 读取`pack_subdir/components/*/manifest.json` 并构建`ComponentInfo`。组件是生命周期管理（例如设置）的单元。

### 与 python_file_call 的关系

`python_file_call`没有特殊对待组件和自动搜索块的功能。如果要运行位于`components/{component_id}/blocks/`中的文件，请在`file`字段中指定相对路径。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

---

## 词汇/转换器

> **注意**：该功能是兼容性吸收的高级功能。正常Pack开发中不需要使用它。

### vocab.txt（同义词组）

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

写在同一行上的单词被视为同义词。

### 转换器

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

### 转换器安全检查

#### 问题

`ConverterASTChecker` 对转换器脚本执行 AST 解析，并检测并拒绝`blocked_imports`（`os`、`subprocess`、`socket`等）的使用。但是，当前检查仅针对转换器文件。如果转换器导入诸如`from .helper import func`或`import local_module`之类的本地模块，则即使导入的文件包含阻止的导入，它也将无法检测阻止的导入。

```
converter.py          ← 検査される（Level 0）
 └─ import helper     ← helper.py は検査されない
     └─ import os     ← blocked import が素通り
```

#### 检验级别定义

|水平|检验范围|优势 |缺点 |实施成本|
|--------|---------|----------|-----------|-----------|
| 0 级（当前）|单个转换器文件 |实施了，速度快，无副作用|可以通过本地导入绕过被阻止的导入 |无 |
| 1 级（推荐）|转换器+递归遍历同一目录中的`.py` |防止最常见的旁路模式。简单的实现 |不检查同一目录之外的依赖关系 |低（约50行）|
| 2 级 |跨 pack_subdir 递归遍历导入图 |可以检查完整的依赖树 |实施起来很复杂。必须考虑递归深度管理、循环检测和路径解析。与性能成本|中到高（约 150 行）|

#### 推荐：1 级

我们建议在下一波实施级别 1。

- 转换器的本地依赖项通常放置在同一目录中（将助手放置在`converters/`下的模式）
- 仅限于同一目录，路径解析简单，误报风险低。
- 2 级假设转换器被设计为跨多个目录，但在当前转换器规则下这种情况很少见。

一旦用例得到确认，将考虑级别 2。

#### 1 级伪代码

```python
def check_converter_with_locals(
    converter_path: Path,
    blocked: set[str],
) -> list[str]:
    """converter と同一ディレクトリのローカル .py を再帰的に AST 検査する。"""
    violations: list[str] = []
    converter_dir = converter_path.parent
    visited: set[Path] = set()

    def _check(target: Path) -> None:
        if target in visited:
            return                          # 循環 import 防止
        visited.add(target)
        tree = ast.parse(target.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # ast.Import      → [alias.name for alias in node.names]
            # ast.ImportFrom   → node.module（相対 import の場合 None あり）
            for name in _extract_module_names(node):
                if name in blocked:
                    violations.append(f"{target.name}: blocked import '{name}'")
                # 同一ディレクトリに .py があればローカル依存として再帰検査
                local = converter_dir / f"{name.split('.')[0]}.py"
                if local.exists() and local != target:
                    _check(local)

    _check(converter_path)
    return violations
```

> `_extract_module_names()` 是一个帮助器，它从 `ast.Import` / `ast.ImportFrom` 节点返回模块名称字符串列表。您可以重用现有的`ConverterASTChecker`逻辑。

#### 测试计划（1 级）

| ＃|场景 |预期结果 |
|---|---------|---------|
| 1 |单独转换器`import subprocess` |拒绝 |
| 2 |转换器 → `from .helper import x` → `helper.py` 至 `import os` |拒绝（通过本地依赖项阻止导入检测）|
| 3 |转换器 → `from .helper import x` → `helper.py` 是干净的 |允许 |
| 4 |转换器 → `import requests`（外部封装，本地无`.py`）|允许（由于没有本地文件而跳过）|
| 5 |转换器 → `helper.py` → `from .utils import y` → `utils.py` 至 `import socket` |拒绝（通过递归扫描检测）|
| 6 |循环导入：转换器→助手→转换器|正常结束，没有无限循环（被访问集阻止） |
| 7 |在转换器目录外部导入 (`from ..other import z`) |跳过（在Level 1的检查范围之外。Level 2支持）|

---

## 审核日志

### 概述

所有重要操作均以 JSON Lines 格式记录在`user_data/audit/`中。

### 类别

|类别 |内容 |
|----------|------|
| `flow_execution`|流程执行 |
| `modifier_application`|应用修改器 |
| `python_file_call`|块执行 |
| `approval`|包审批操作|
| `permission`|权限运营（包括网络授权、能力授权）|
| `network`|网络通讯|
| `security`|安全事件|
| `system`|系统事件（lib、pip、待导出等）|

### 文件命名

`{category}_{YYYY-MM-DD}.jsonl`

文件名中的日期由条目的`ts`（时间戳）确定。即使过了午夜，也会被分类到该条目的`ts`对应的文件中。如果`ts`无效，它将回退到撰写本文时的日期。

### 条目结构

```json
{
  "ts": "2024-01-01T00:00:00Z",
  "category": "python_file_call",
  "severity": "info",
  "action": "execute_python_file",
  "success": true,
  "flow_id": "ai_response",
  "step_id": "generate",
  "phase": "generate",
  "owner_pack": "ai_client",
  "execution_mode": "container",
  "details": {
    "file": "blocks/generate.py",
    "execution_time_ms": 150.5
  }
}
```

---

## 待导出

### 概述

`user_data/pending/summary.json` 在启动时自动生成。外部工具只需读取该文件即可了解审批状态。官方不会对该文件的消费者给予特殊待遇（No Favoritism）。

### 输出格式

```json
{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 1,
    "modified_ids": ["pack_c"],
    "blocked_count": 0,
    "blocked_ids": []
  },
  "capability": {
    "pending_count": 1,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 3
  },
  "pip": {
    "pending_count": 0,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 2
  }
}
```

如果每个模块无法导入，其部分将包含`"error"`键（软失败）。

---

## DI 容器和服务列表

### 概述

`backend_core/di_container.py` 是整个 Rumi AI OS 中使用的轻量级 DI（依赖注入）容器。所有服务都向容器注册并按名称检索。通过 `get_container()` 作为全局单例进行访问。

### DIContainer 类

|方法|描述 |
|---------|------|
| `register(name, factory)`|按名称注册工厂函数。首先实例化`get`（延迟生成）|
| `get(name)`|获取实例。如果未注册`KeyError` |
| `get_or_none(name)`|获取实例。如果未注册`None` |
| `has(name)`|判断是否已注册|
| `reset()`|清除所有注册 |
| `set_instance(name, instance)`|直接注册现有实例（用于测试）|

### 全球访问

|功能|描述 |
|------|------|
| `get_container()`|获取全局容器（单例）|
| `reset_container()`|重置全局容器（用于测试）|

### 注册服务列表（32个服务）

|波|服务名称|
|------|-----------|
|第 1 波 | `audit_logger`，`hmac_key_manager`|
|第 2 波 | `vocab_registry`、`network_grant_manager`、`store_registry`|
|第 3 波 | `approval_manager`，`permission_manager`|
|第 4 波 | `container_orchestrator`、`host_privilege_manager`、`flow_composer`、`function_alias_registry`、`secrets_store`、`secrets_grant_manager`、`modifier_loader`、`modifier_applier`|
|第 5 波 | `pack_api_server`、`egress_proxy_manager`、`python_file_executor`、`secure_executor`、`lib_executor`、`unit_executor`、`capability_executor`|
|第 8 波 | `diagnostics`、`install_journal`、`interface_registry`、`event_bus`、`component_lifecycle`|
|第 15 波 | `health_checker`、`metrics_collector`、`profiler`|
|第 22 波 | `docker_capability_handler`|
|第 24 波 | `function_registry`|

---

## 内核混入配置

### 概述

`backend_core/kernel.py` 通过组合四个 Mixin 类来构造一个 Kernel。它按兴趣分离实现，同时避免单个文件膨胀。

### 混合列表

| Mixin 类 |文件|职责|
|-------------|---------|------|
| `KernelCore`| `kernel_core.py` |发动机本体。流程加载、上下文构建、关闭 |
| `KernelFlowExecutionMixin`| `kernel_flow_execution.py` |流程执行、`depends_on`分辨率、条件评估 |
| `KernelSystemHandlersMixin`| `kernel_handlers_system.py` |启动/系统处理程序（初始化、扫描、批准等）|
| `KernelRuntimeHandlersMixin`| `kernel_handlers_runtime.py` |操作/执行处理程序（流程执行、能力调用等）|

### 合成

```python
# kernel.py
class Kernel(
    KernelRuntimeHandlersMixin,
    KernelSystemHandlersMixin,
    KernelFlowExecutionMixin,
    KernelCore,
):
    pass
```

MRO（方法解析顺序）按照运行时→系统→流程执行→核心的顺序进行解析。每个 mixin 取决于`KernelCore`（`self.container`、`self.context`等）的属性。

---

## 可观察性

### 概述

Wave 15 中添加的四个模块提供结构化日志、运行状况检查、指标和分析。

### 结构化日志记录 (logging_utils.py)

`backend_core/logging_utils.py` 包装了标准`logging` 并提供结构化输出和上下文传播。

|类/函数 |描述 |
|--------------|------|
| `StructuredFormatter`|将日志格式化为 JSON 或文本格式 |
| `StructuredLogger`| `logging.Logger`包装。在`bind()` 中给出键值上下文 |
| `CorrelationContext`|线程安全`correlation_id`管理。用于每个请求跟踪 |
| `get_structured_logger(name)`|带缓存的工厂。使用相同的名称调用返回相同的实例 |
| `configure_logging()`|立即应用全局日志设置（级别、格式） |

环境变量`RUMI_LOG_LEVEL`（默认`INFO`）和`RUMI_LOG_FORMAT`（`json`或`text`，默认`text`）控制行为。

### 健康检查（health.py）

`backend_core/health.py`提供了基于探针的健康检查机制。用于`app.py --health`。

|类/函数 |描述 |
|--------------|------|
| `HealthChecker`|注册探针、超时并行运行并聚合结果 |
| `HealthStatus`| `UP` / `DOWN` / `DEGRADED` / `UNKNOWN` 4 个州 |
| `probe_disk_space`|检查可用磁盘空间（内置探测器）|
| `probe_memory`|检查内存使用情况（内置探针）|
| `probe_file_writable`|检查文件是否可以写入（内置探针） |

如果所有探针都是`UP`，则所有探针也被判定为`UP`，如果其中任何一个是`DOWN`，则判定为`DEGRADED`，如果所有探针都是`DOWN`，则判定为`DOWN`。

### 指标 (metrics.py)

`backend_core/metrics.py` 为收集应用程序指标提供了基础。

|方法|描述 |
|---------|------|
| `increment(name, labels, value)`|增量计数器|
| `set_gauge(name, labels, value)`|设置仪表|
| `observe(name, labels, value)`|在直方图中记录值 |
| `timer(name, labels)`|上下文管理器。自动记录区块执行时间 |
| `snapshot()`|返回字典中所有指标的当前值 |

标签（字典）允许您将指标分类为多个维度。在 Wave 15 中，它已集成到`kernel_flow_execution.py`（步骤执行时间）、`kernel_handlers_system.py`/`kernel_handlers_runtime.py`（处理程序调用计数/时间）中。

### 分析（profiling.py）

`backend_core/profiling.py` 提供函数和块的执行时间分析。

|方法/装饰器 |描述 |
|--------------------|------|
| `profile(name)`|上下文管理器。记录区块执行时间 |
| `profile_func(name)`|同步函数的装饰器 |
| `profile_async(name)`|异步函数的装饰器 |
| `summary()`|返回带有 p50 / p95 / p99 百分位数的摘要 |

您可以将`max_samples`设置为内存限制，一旦超过限制，较旧的样本将被丢弃。它已被集成到 Wave 15 中的`kernel_flow_execution.py`（流程执行时间、步骤执行时间）中。

---

## 公共基础模块

### 概述

第 12-15 波中添加的一组实用程序，可在包之间共享。

### 通用验证（validation.py）

`backend_core/validation.py` 提供了 Pack / Flow / Modifier 的验证实用程序（添加了 Wave 12）。集中通用逻辑，例如架构验证、必填字段验证和值范围验证，以消除每个模块中的重复。

### 统一错误系统（error_messages.py）

`backend_core/error_messages.py`定义了跨Rumi AI OS的统一错误代码系统。

|元素|描述 |
|------|------|
| `ErrorCode`|冻结数据类。 `RUMI-{CAT}-{NNN}` 格式（例如`RUMI-AUTH-001`）|
|类别 | `AUTH`（身份验证）、`NET`（网络）、`FLOW`（流程）、`PACK`（包）、`CAP`（能力）、`VAL`（验证）、`SYS`（系统）|
| `RumiError`|统一异常类。保留`code`、`message`、`details`、`suggestion`|
| `format_error()`|模板扩展助手。动态填充消息中的占位符 |

错误代码在自动收集注册表中进行管理，并在模块加载时自动注册到注册表中。

### 类型定义（types.py + py.typed）

`backend_core/types.py` 聚合了整个包中使用的类型定义。

|类型 |定义 |
|------|------|
|新类型 | `PackId`、`FlowId`、`CapabilityName`、`HandlerKey`、`StoreKey`|
|输入别名 | `JsonValue`，`JsonDict`|
|通用| `Result[T]`（保留成功值或错误）|
|枚举 | `Severity`（`info`，`warn`，`error`，`critical`）|

包含`py.typed` 标记文件 (PEP 561)，以启用使用外部工具（mypy 等）进行类型检查。

### 弃用管理（deprecation.py）

`backend_core/deprecation.py` 为已弃用的 API 提供管理和警告。

|元素|描述 |
|------|------|
| `DeprecationInfo`|冻结数据类。保留已弃用的目标、版本和替代方案 |
| `DeprecationRegistry`|辛格尔顿。线程安全地管理弃用信息 |
| `deprecated()`|函数/方法的装饰器（异步兼容）。调用时输出警告 |
| `deprecated_class()`|类的装饰器。创建实例时输出警告 |

环境变量`RUMI_DEPRECATION_LEVEL`控制行为：`warn`（默认，打印警告），`error`（引发异常），`silent`（忽略），`log`（仅记录）。

---

## 打包开发工具

### 概述

`backend_core/pack_scaffold.py` 是一个生成 Pack 模板的 CLI 工具。

### PackScaffold 类

从四种类型的模板自动生成 Pack 目录结构和文件。

|模板|描述 |
|------------|------|
| `minimal`|最低配置。仅`ecosystem.json` + 空`backend/` |
| `capability`|具有能力处理程序。包含`share/capability_handlers/` |
| `flow`|随着流量。包含`backend/flows/`和`backend/blocks/`|
| `full`|全套包括所有元素。包括`lib/`、`converters/`、`modifiers/`等|

生成的文件使用`validation.py`进行验证，以防止结构错误。

### CLI 入口点

```bash
python -m backend_core.pack_scaffold --template full --pack-id my_pack --output ecosystem/my_pack
```

指定`--template`（模板名称）、`--pack-id`（包 ID）和`--output`（输出路径）。

---

## 已弃用的功能

### 生态系统/流程/（local_pack）

这是一种兼容模式，将直接放置在`ecosystem/flows/`中的流程/修改器视为虚拟包。默认情况下它被禁用（`RUMI_LOCAL_PACK_MODE=off`）。可以使用`RUMI_LOCAL_PACK_MODE=require_approval`启用，但不推荐。

弃用计划：在 v2.0 中保持带有警告的兼容性模式，计划在 v3.0 中删除。

迁移目的地：将其打包并放置在`ecosystem/<pack_id>/backend/`中或放置在`user_data/shared/flows/`中。

### 插件管理器

基于 JSON 补丁的插件机制存在于`backend_core/ecosystem/addon_manager.py`中，但在第 2 阶段被删除。它目前不存在于代码库中。

### 流/目录

旧的`flow/`目录已被弃用。请移至包中的`flows/`、`user_data/shared/flows/`或`flows/`。

### 已删除的文件

以下文件/目录已被删除。

|删除目标 |更换|原因 |
|---------|------|------|
| `capability_handler_registry.py`| `function_registry.py` |集成到 FunctionRegistry（A 到 D 阶段）|
| `builtin_capability_handlers/`| `core_pack/` |迁移到 core_pack |

# Defaultspack 函数边界

Defaultspack 现在将函数清单视为公共操作边界。 HTTP 路由是兼容性适配器，AI 工具是可选外观，Flow/function.call 调用在到达域服务之前都汇聚到相同的 defaultspack 函数上。
