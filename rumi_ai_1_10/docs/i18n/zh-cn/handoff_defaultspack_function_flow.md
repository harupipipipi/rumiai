<!-- docs-i18n-links:start -->
[EN](../../handoff_defaultspack_function_flow.md) | [JP](../ja/handoff_defaultspack_function_flow.md) | [KR](../ko/handoff_defaultspack_function_flow.md) | [CN](./handoff_defaultspack_function_flow.md)
<!-- docs-i18n-links:end -->

# 切换：defaultspack 函数/流程运行时

这种切换是独立的。假设下一个工程师只知道
存储库名称，`rumiai`，并且尚未阅读之前的对话。

## 存储库和分支

- 存储库：`rumiai`
- 用于此检查点的本地工作区：
  `/Users/haru/Desktop/puroguramukei/rumi_ai_mac`
- 主包目录：`rumi_ai_1_10`
- 分支机构：`codex/defaultspack-function-flow`
- 远程：`origin`，`https://github.com/harupipipipi/rumiai.git`
- 在此切换文件之前检查点提交：
  `776178f2 WIP: canonicalize defaultspack function flow runtime`

继续在同一个分支上工作，并将所有剩余的工作放入一个 PR 中。
除非用户明确更改范围，否则请勿将其拆分为多个 PR。

## 用户目标

用户希望`defaultspack`成为规范运行时并希望
匹配这些架构规则的实现：

- `defaultspack` 是规范的运行时。
- `defaults` 仅保留为薄兼容性垫片。
- 工具被实现为功能/能力外观。
- 工具安全不得依赖于`write_action: true`。
- 不受信任的用户/包代码必须在 Docker 隔离内运行。
- 主机访问、网络访问、文件编辑、终端、git、浏览器等
  计算机控制必须经过受信任的默认功能/能力授予。
- 正常的聊天输入应经过声明性 YAML 流程加上 Python 流程
  发动机。
- 流程仅是编排；真正的逻辑属于函数。
- 提示是被动上下文，不是可执行的工具逻辑。
- AI 提供商应该是清单优先的，并且具有与 OpenAI 兼容的提供商
  如果可能的话，可以通过清单/模型定义添加。
- 前端 HTTP/SSE/小部件合约应在后端保持兼容
  内部结构转向路由注册表+流程/功能。

最终期望的结果是一个完全实现并验证这一点的 PR
方向。

## 需要保留的架构决策

- 规范运行时间：`ecosystem/defaultspack`。
- 旧版兼容性：`ecosystem/defaults` 代表`defaultspack`。
- 流程实现：YAML 声明加 Python 引擎。
- 允许的可创作工具执行类型：
  - `rumi_function`
  - `capability`
  - `mcp`
- 旧执行类型，例如`local`、`handler`、`dynamic`和`prompt`
  不可授权给不受信任的工具。现有的第一方兼容性
  路径可能会暂时保留，但对于不受信任的工具应该无法关闭。
- 当前使用的能力分类：
  - `file.read`
  - `file.write`
  - `terminal.exec`
  - `git.read`
  - `git.write`
  - `network.read`
  - `network.send`
  - `browser.control`
  - `computer.control`
- `write_action` 仅是元数据。必须做出许可和风险决策
  从风险类别、审批策略、执行类型、可信包身份以及
  能力补助金。
- 如果 Docker 不可用，严格的 Docker 策略应拒绝主机回退。

## 检查点中已经实现了什么

### 工具安全性和功能化

- 添加了`ecosystem/defaultspack/domain/tool/security.py`。
- 更新了`ecosystem/defaultspack/domain/tool/registry.py`以使风险正常化，
  拒绝不受支持的不受信任的遗留执行类型，公开功能
  授予，并在工具可见的情况下保持 UI/扩展兼容性
  但仍然无法通过安全策略执行。
- 更新了`ecosystem/defaultspack/domain/tool/executor.py`以强制执行
  功能/能力优先执行并拒绝不支持的不可信路径。
- 将`ecosystem/rumi_default_tools_pack/tools/*/manifest.json`迁移至
  功能/能力门面元数据，包括编码/文件/git/终端和
  网络/浏览器/计算机工具。
- 在`tests/test_defaultspack_tool_security.py`中添加了测试。

### Docker / 能力边界

- 更新了`core_runtime/capability_executor.py`，如此严格的 Docker 政策否认
  当 Docker 不可用时主机回退。
- 在`tests/test_capability_executor_security.py`中添加了测试。

### Flow 运行时和聊天入口

- 扩展`ecosystem/defaultspack/domain/flow/engine.py`。
- 添加了声明性验证和执行支持：
  - `function`
  - `subflow`
  - `branch`
  - `parallel`
- 将`ecosystem/defaultspack/flows/chat_turn.flow.yaml`更新为规范
  正常聊天入口。
- 添加了`ecosystem/defaultspack/flows/chat_stream_turn.flow.yaml`。
- 更新了`tests/test_defaultspack_chat_turn_flow_contract.py`中的测试。

### 聊天持久性

- 更新了`ecosystem/defaultspack/blocks/chat/persist_turn.py`所以坚持
  经过规范的`ChatStore`语义而不仅仅是一个JSONL
  追加路径。
- JSONL 风格的审计应与规范消息持久性保持分离。

### 运输/路线登记

- 更新了`ecosystem/defaultspack/transport/registry.py`来描述路线
  通过流程/功能规格。
- 更新了`ecosystem/defaultspack/transport/http.py`、`cli.py`和`stdio.py`
  通过规范流程/功能路径路由正常聊天，同时保留
  尽可能的公共合同。
- 将`ecosystem/defaults/transport/{http,cli,stdio,uds}.py`转换为薄
  兼容性垫片。
- 添加/更新了路线测试：
  - `tests/test_defaultspack_route_integration.py`
  - `tests/test_defaults_mcp_transport.py`

### 提示

- 添加了`ecosystem/defaultspack/domain/prompt/effective.py`。
- 更新了提示加载/解析，以便有效的提示返回源链
  并解决了内容。
- 添加了调度程序条目：
  - `prompt_validate_template`
  - `prompt_resolve_for_conversation`
- 禁用提示工具创作作为可执行提示逻辑。
- 更新了提示模板/统一转换生成被动/函数
  外观元数据而不是可执行文件`execution.type = prompt`。
- 添加了测试：
  - `tests/test_defaultspack_prompt_effective.py`
  - `tests/test_defaultspack_prompt_passive.py`

### AI 客户/提供商

- 添加/更新了`ecosystem/defaultspack/domain/ai_client/gateway.py`。
- 将聊天/人工智能块移向`LLMGateway`，而不是直接`AIClient`
  编排，同时保留遗留的monkeypatch兼容性
  `blocks/chat/send.py` 通过网关级再导出。
- 更新了`ecosystem/defaultspack/domain/ai_client/providers/__init__.py`
  清单优先 OpenAI 兼容提供者元数据。
- 添加了`tests/test_defaultspack_provider_manifest_first.py`。

### 浏览器/计算机稳定性

- 更新
  `ecosystem/rumi_default_tools_pack/domain/tool/browser_computer.py`要避免
  自定义测试工件根重用旧的共享选定窗口状态
  `browser_sessions.json`。
- 这修复了在完整的浏览器/计算机状态敏感故障中出现的问题
  pytest 运行。

### 文档

更新了相关文档：

- 流量规格
- 提示创作
- 提供商创作
- 工具创作
- 运输
- 人工智能提供商/客户
- 提示/工具转换

重要的文档更改包括：

- `docs/flow_spec.md`
- `docs/prompt_authoring.md`
- `docs/provider_authoring.md`
- `ecosystem/defaultspack/docs/ai_client.md`
- `ecosystem/defaultspack/docs/prompt.md`
- `ecosystem/defaultspack/docs/tool-prompt-conversion.md`
- `ecosystem/defaultspack/docs/transport.md`
- `ecosystem/defaultspack/docs/writing-tools.md`

## 验证已运行

这些在检查点提交之前通过：

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_chat_turn_flow_contract.py \
  tests/test_defaultspack_route_integration.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_tool_security.py -q
```

结果：42通过。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_*flow*.py tests/test_*route*.py \
  tests/test_defaults_mcp_transport.py \
  tests/test_defaultspack_tool_security.py \
  tests/test_defaultspack_tool_policy.py \
  tests/test_defaultspack_tool_components.py \
  tests/test_defaultspack_tool_executor_rumi_function.py \
  tests/test_defaultspack_external_send_tool.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_prompt_components.py \
  tests/test_defaultspack_provider_expansion.py \
  tests/test_defaultspack_provider_foundation.py \
  tests/test_defaultspack_backend_foundation.py \
  tests/test_capability_executor_security.py -q
```

结果：403 项通过，1 项现有警告。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_agent_service_plan.py -q
```

结果：182通过。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_browser_computer_seat_delegation.py \
  tests/test_computer_desktop_action_delegation.py \
  tests/test_computer_move_drag_delegation.py \
  tests/test_defaultspack_agent_service_plan.py::test_computer_click_physical_true_operates_visible_action -q
```

浏览器/计算机状态修复后的结果：18 通过。

```bash
git diff --check
```

结果：通过。

## 完整测试状态

完整测试命令：

```bash
cd rumi_ai_1_10
python -m pytest -q
```

发生了什么：

1. 在浏览器/计算机状态修复达到之前完整运行：
   `4373 passed, 19 skipped, 7 failed`。
2. 所有 7 次失败都是浏览器/计算机物理动作委托测试，其中
   过时的选定窗口状态使操作返回`executed=False`。
3. 添加了状态修复并通过了相关的 18 测试子集。
4. 开始新的完整运行并通过了先前失败的运行
   浏览器/计算机部分，但用户要求移动环境，所以
   在完成之前故意停止。

下一位工程师必须从干净的流程中再次运行完整的测试套件。

## 立即采取的后续步骤

1. 获取并签出分支：

```bash
git fetch origin
git checkout codex/defaultspack-function-flow
cd rumi_ai_1_10
```

2. 运行完整测试：

```bash
python -m pytest -q
```

3. 如果出现故障，请修复它们而不恢复检查点架构。

4. 在触摸区域周围重新运行集中测试，然后再次运行完整测试。

5. 检查设计回归：

```bash
rg -n 'execution\\.type.*prompt|"type": "prompt"|type: prompt|execution.*dynamic|execution.*handler' \
  ecosystem/defaultspack docs ecosystem/rumi_default_tools_pack
```

单独对待合法的提示组件元数据；可执行提示工具
不应作为创作路径返回。

6.检查直接AI客户端导入：

```bash
rg -n 'from domain\\.ai_client\\.client import AIClient|from ecosystem\\.defaultspack\\.domain\\.ai_client\\.client import AIClient' \
  ecosystem/defaultspack/blocks ecosystem/defaultspack/domain
```

仅应保留允许的旧版/导入兼容性位置。

7. 完成后，从 `codex/defaultspack-function-flow` 创建一个 PR 到
   `master`。

## 最终 PR 的接受标准

- 完全`python -m pytest -q`通过或任何剩余的失败都清楚
  不相关且有记录。
- 正常聊天流程通过`defaultspack.chat_turn`。
- 通过`defaultspack.chat_stream_turn`或同等方式流式传输聊天流
  路由注册功能/流路径。
- 现有前端 HTTP 路径、JSON 形状、SSE 事件名称和小部件
  形状保持兼容。
- `defaults` 仍可用作兼容性垫片。
- 不受信任的遗留执行类型不可创作/可执行。
- 功能/能力工具清单揭示风险、批准和拨款。
- 主机/网络/文件/git/浏览器/计算机访问经过受信任的默认设置
  功能/能力。
- 提示仍然是被动的；没有恢复可执行提示工具创作路径。
- 仍涵盖仅清单 OpenAI 兼容的提供程序添加。
- 文档匹配运行时行为。

## 注意事项

- 除非更换，否则请勿恢复较大的`defaults` 运输垫片更改
  他们具有等效的路由注册委派。
- 不要将`execution.type = prompt`重新引入作为可执行工具路径。
- 不要依赖`write_action`作为许可决定。它是元数据。
- 不要让 Docker 严格模式默默地回退到主机执行。
- 小心 macOS 上的浏览器/计算机测试。共享
  `browser_sessions.json` 可以在测试之间保留选定的窗口状态。
- 将其保留为一个 PR，除非用户明确要求将其拆分。
