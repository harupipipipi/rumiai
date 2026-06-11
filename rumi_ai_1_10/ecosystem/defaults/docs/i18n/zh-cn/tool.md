<!-- docs-i18n-links:start -->
[EN](../../tool.md) | [JP](../ja/tool.md) | [KR](../ko/tool.md) | [CN](./tool.md)
<!-- docs-i18n-links:end -->

# 工具模块

## 1.设计理念

Tool模块是LLM在Rumi AI OS中代表用户执行外部操作的机制。

设计原则：
- **数据驱动**：工具定义是一个 JSON/YAML 文件。逻辑是handler.py。您只需添加目录即可扩展该工具。
- **仅限通用原语**：注入 handler.py 的上下文 API 仅包含通用原语。聊天操作、代理激活、内存读写等所有领域操作都是通过通用原语的组合来实现的。没有特定于域的 API。
- **逐步披露**：如果有很多工具，首先仅将目录（名称/摘要）传递给LLM，然后在选择后传递详细架构。节省令牌并提高选择准确性。
- **最低权限**：handler.py可以使用的上下文API是根据permission.json中的声明注入的。不能使用未声明的API。
- **外部依赖解析**：如果工具所需的功能或包尚未安装，则可以自动从 GitHub 存储库获取它们，而无需使用 git。

---

## 2.目录结构

### 工具放置

```
user_data/shared/tools/
├── defaults.json              # グローバル設定
├── manifest.json              # ハッシュ・同期管理
├── mcp.json                   # MCP サーバー定義
│
├── file_read/                 # ツールごとに1ディレクトリ
│   ├── tool.json              # メタ情報（必須）
│   ├── schema.json            # 入出力スキーマ（必須）
│   ├── guide.json             # 用途・手順・例
│   ├── conditions.json        # モデル条件・動作分岐
│   ├── permission.json        # 権限・承認
│   ├── relations.json         # 連携・チェーン・依存
│   ├── handler.py             # 実行ロジック（必須）
│   └── readiness/
│       └── check.py           # 環境検知（任意）
│
├── bash/
│   ├── tool.json
│   ├── schema.json
│   ├── guide.json
│   ├── conditions.json
│   ├── permission.json
│   ├── relations.json
│   ├── handler.py
│   └── capability/            # ホスト側 capability 同梱（任意）
│       ├── capability.json
│       └── handler.py
│
└── browser_navigate/
    └── ...
```

包提供的工具放置在`user_data/packs/*/tools/`中。

### 后端代码

```
ecosystem/default/backend/blocks/tool/
├── loader.py                  # ツール定義の走査・マージ・キャッシュ
├── converter.py               # 4方向変換（定義↔LLM, 結果↔LLM）
├── executor.py                # 実行エンジン
├── permission_checker.py      # 権限検証
├── session_manager.py         # シェルセッション・状態管理
└── mcp_client.py              # MCP サーバー接続
```

### 包管理代码

```
ecosystem/default/backend/blocks/pack/
├── downloader.py              # GitHub API で zipball ダウンロード
├── resolver.py                # 依存解決・バージョンマッチング
├── installer.py               # 配置・ハッシュ記録
├── verifier.py                # marketplace レジストリ照合
└── updater.py                 # アップデートチェック
```

---

## 3.工具定义文件

### 3.1 tool.json（必填）

工具元信息。在分阶段披露的第一阶段通过了法学硕士。

```json
{
  "tool_id": "browser_navigate",
  "name": "Browser Navigate",
  "summary": "Web ページを開いてスクリーンショットを取得する",
  "version": "1.2.0",
  "status": "stable",
  "author": "default",
  "tags": ["browser", "web", "screenshot", "navigation"],
  "use_cases": [
    "URL の内容を視覚的に確認したいとき",
    "ページの見た目やレイアウトを確認したいとき",
    "ブラウザ操作の起点としてページを開くとき"
  ],
  "side_effects": ["network_access", "screenshot_capture"],
  "idempotent": true,
  "estimated_duration": "slow",
  "output_size": "large",
  "cost": "free",
  "priority": 80,
  "execution": {
    "type": "capability",
    "capability_id": "browser_control",
    "timeout": 60,
    "parallel": false
  }
}
```

**execution.type 类型：**

| type | Description | Operating location |
|------|------|----------|
| `local` | Run handler.py directly | In Docker |
| `capability` | Via Capability Handler | Host side |
| `mcp` | Via MCP server | External process |
| `http` | HTTP request | via llm_network |

### 3.2 schema.json（必需）

输入和输出的 JSON 架构定义。在分阶段披露的第二阶段通过了法学硕士。

```json
{
  "parameters": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "移動先の URL",
        "format": "uri"
      },
      "wait_for": {
        "type": "string",
        "description": "待機する CSS セレクタ",
        "default": null
      },
      "viewport": {
        "type": "object",
        "properties": {
          "width": { "type": "integer", "default": 1280 },
          "height": { "type": "integer", "default": 720 }
        }
      }
    },
    "required": ["url"]
  },
  "returns": {
    "type": "object",
    "properties": {
      "title": { "type": "string" },
      "url": { "type": "string" },
      "status_code": { "type": "integer" },
      "screenshot": { "type": "string", "format": "base64_png" },
      "interactive_elements": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "selector": { "type": "string" },
            "text": { "type": "string" },
            "type": { "type": "string" }
          }
        }
      }
    }
  }
}
```

### 3.3 指南.json

详细介绍如何使用。该描述在逐步披露的第二阶段被注入到法学硕士中。

```json
{
  "purpose": "Web ページを開いてスクリーンショットと要素情報を取得する",
  "when_to_use": [
    "URL の内容を視覚的に確認したいとき",
    "ページの見た目やレイアウトを確認したいとき",
    "ブラウザ操作シーケンスの起点としてページを開くとき"
  ],
  "when_not_to_use": [
    "API で直接データ取得できる場合",
    "HTML ソースだけ必要な場合（web_fetch を使う）",
    "大量 URL のバッチ処理"
  ],
  "usage_guide": "url を指定して呼び出す。動的コンテンツがある場合は wait_for で CSS セレクタを指定する。結果にスクリーンショットが含まれるため Vision モデルで直接解析可能。",
  "tips": [
    "SPA では wait_for が必須になることが多い",
    "viewport でモバイル表示テストが可能",
    "連続操作は browser_click, browser_type と組み合わせる"
  ],
  "examples": [
    {
      "description": "基本的なページ表示",
      "input": { "url": "https://example.com" },
      "output_summary": "タイトル、URL、スクリーンショットが返る",
      "test_mode": true
    },
    {
      "description": "動的コンテンツの待機",
      "input": { "url": "https://app.example.com", "wait_for": ".main-content" },
      "output_summary": ".main-content が表示されてからキャプチャされる"
    }
  ],
  "common_mistakes": [
    "SPA で wait_for を指定しないと初期ローディング画面がキャプチャされる",
    "viewport を指定しないとデフォルトの 1280x720 になる"
  ],
  "error_recovery": {
    "timeout": "wait_for を外すか、セレクタをより具体的にする",
    "navigation_error": "URL が正しいか確認する。HTTPS が必要な場合がある",
    "screenshot_failed": "ページ読み込み完了を待つため wait_for を追加する"
  },
  "changelog": [
    { "version": "1.2.0", "date": "2026-02-10", "changes": "viewport パラメータ追加" },
    { "version": "1.1.0", "date": "2026-01-15", "changes": "wait_for パラメータ追加" },
    { "version": "1.0.0", "date": "2025-12-01", "changes": "初版" }
  ]
}
```

### 3.4 条件.json

根据模型功能进行行为分支。

```json
{
  "requirements": {
    "tool_calls": { "required": true },
    "vision": {
      "required": false,
      "fallback_variant": "vision_disabled"
    }
  },
  "recommendations": {
    "capabilities": ["thinking", "vision"],
    "min_context_length": 32000,
    "preferred_models": ["gpt-5.2", "claude-sonnet-4"],
    "reason": "スクリーンショット解析に vision、複雑な操作計画に thinking が有効"
  },
  "behavior_variants": [
    {
      "id": "vision_enabled",
      "when": "model.capabilities.vision == true",
      "handler_config": {
        "result_format": "image",
        "include_screenshot": true
      }
    },
    {
      "id": "vision_disabled",
      "when": "model.capabilities.vision == false",
      "handler_config": {
        "result_format": "text_description",
        "include_screenshot": false,
        "include_accessibility_tree": true
      }
    },
    {
      "id": "thinking_boost",
      "when": "model.capabilities.thinking == true",
      "auto_params": {
        "thinking_budget": 2048
      }
    }
  ],
  "incompatible": {
    "max_output_tokens": { "less_than": 1024, "reason": "出力が大きいため" },
    "context_length": { "less_than": 8000, "reason": "画像データが大きいため" }
  }
}
```

### 3.5 权限.json

权威/批准/限制。

```json
{
  "requires_approval": true,
  "approval_mode": "per_session",
  "risk_level": "high",
  "capabilities_required": ["browser_control"],
  "pack_dependencies": {
    "rumi-browser-runtime": {
      "repo": "harupipipipi/rumi-browser-runtime",
      "path": ".",
      "version": ">=1.0.0",
      "reason": "ブラウザ制御の Capability Handler を提供"
    }
  },
  "parameter_restrictions": {
    "url": {
      "allowed_patterns": ["https://*", "http://localhost:*"],
      "denied_patterns": ["file://*", "javascript:*"]
    }
  },
  "max_calls_per_session": 50,
  "cooldown_seconds": 1,
  "audit": true,
  "llm_call_allowed": false
}
```

**`pack_dependencies`**：此工具所需的外部包。如果指定的 Pack 尚未安装，则会建议自动获取 `repo`.**`capabilities_required`**：注入到 handler.py 上下文中的功能声明。只有此处声明的功能才会注入到上下文中。

使用`llm_call`时，可以将其设置为`llm_call_allowed: true`并写入限制：

```json
{
  "llm_call_allowed": true,
  "llm_call_limits": {
    "max_calls_per_execution": 3,
    "max_input_tokens": 10000,
    "max_output_tokens": 2000
  }
}
```

### 3.6 关系.json

合作工具、链模式和依赖关系。

```json
{
  "related_tools": {
    "chain_next": ["browser_click", "browser_type", "browser_scroll", "browser_back"],
    "alternatives": ["web_fetch"]
  },
  "chain_patterns": [
    {
      "name": "ページ操作フロー",
      "sequence": ["browser_navigate", "browser_click", "browser_type", "browser_navigate"],
      "description": "ページを開く → 要素クリック → テキスト入力 → 次ページへ遷移"
    },
    {
      "name": "ログイン → 操作",
      "sequence": ["browser_navigate", "browser_type", "browser_click", "browser_navigate"],
      "description": "ログインページ → ID/PW 入力 → ログインボタン → ダッシュボード"
    }
  ],
  "dependencies": {
    "capabilities": ["browser_control"],
    "services": ["chromium"]
  }
}
```

### 3.7 handler.py（必需）

工具执行逻辑。

#### 上下文 API

注入 handler.py 的上下文仅包含通用原语。没有特定于特定领域（聊天、代理等）的 API。所有域操作都是通过通用原语的组合来实现的。

**始终注入（无需声明）：**

| context key | description |
|---|---|
| `context["call_handler"]` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `context["emit_event"]` | Publish an event. handler, flow, front end can receive |
| `context["wait_event"]` | Wait for an event. Timeout can be specified |
| `context["emit_widget"]` | Send Widget JSON to the UI |
| `context["cancel_check"]` | Cancellation confirmation |
| `context["handler_config"]` | Settings injected from behavior_variants in conditions.json |
| `context["session"]` | Session information (session_id, workspace, etc.) |

**在permission.json的`capabilities_required`中声明并注入：**

| capability_id | description | context key | risk |
|---|---|---|---|
| `data_read` | Read file under user_data | `context["data_read"](path) → str` | Low |
| `data_write` | Writing files under user_data | `context["data_write"](path, content)` | Medium |
| `execute_flow` | Start Flow | `context["execute_flow"](flow_id, input) → FlowResult` | Medium |
| `shell_exec` | Shell command execution | `context["capability"]("shell_exec", {...})` | High |
| `browser_control` | Browser operation | `context["capability"]("browser_control", {...})` | High |
| `container_exec` | Starting, operating, and destroying Docker containers | `context["capability"]("container_exec", {...})` | High |
| `app_control` | Host application operation | `context["capability"]("app_control", {...})` | High |
| `http_request` | External HTTP communication | `context["capability"]("http_request", {...})` | Medium |
| `llm_call` | In-tool LLM call | `context["capability"]("llm_call", {...})` | Medium |
| `session_state` | Session state read/write | `context["capability"]("session_state", {...})` | Low |

#### 调用处理程序

调用任何处理程序的通用网关。默认注册的所有处理程序和 Pack 都可以调用。 handler 在 README.md 的处理程序系统中定义。

```python
result = context["call_handler"](
    "defaults.chat.send",
    {
        "conversation_id": "conv-1",
        "content": "hello"
    }
)
```

call_handler 按以下顺序处理。检查调用工具的permission.json中声明的权限。验证调用者的权限是否包括被调用处理程序请求的权限。如果不包含，则会因 PermissionError 被拒绝。如果包含，则执行handler并返回结果。

这允许工具在其权限范围内调用系统上的任何处理程序。聊天操作、代理激活、内存读写、提示渲染，都可以通过call_handler来完成。

#### 发出事件/等待事件

事件是整个系统中的通用通信机制。

```python
context["emit_event"]("my_tool.task_complete", {
    "result": "success",
    "data": {...}
})

response = context["wait_event"](
    "ui.user_response",
    timeout=30,
    filter={"popup_id": "consent_1"}
)
```

事件的接收者可以是处理程序、Flow 事件触发器或前端资产。 emit_event只是将其发布到事件总线，发布者并不关心谁接收到它。

#### 数据读取/数据写入

通用文件 I/O，用于读取和写入 user_data 下的任何文件。

```python
content = context["data_read"]("chat/conversations/conv-1.json")
context["data_write"]("knowledge/sources/notes.md", content)
```

该路径是相对于 user_data/ 的。 user_data 外部的访问被拒绝。

#### 执行流程

启动任何流程。通过 Flow Engine 执行。

```python
result = context["execute_flow"](
    "my_custom_flow",
    {"query": "search this"}
)
```

#### container_exec 能力

操纵 Docker 容器生命周期的通用功能。

```python
container = context["capability"]("container_exec", {
    "action": "create",
    "image": "ubuntu:22.04",
    "options": {
        "network": "none",
        "cap_drop": ["ALL"],
        "memory_limit": "512m",
        "display": true
    }
})

result = context["capability"]("container_exec", {
    "action": "exec",
    "container_id": container["id"],
    "command": "ls -la"
})

screenshot = context["capability"]("container_exec", {
    "action": "screenshot",
    "container_id": container["id"]
})

context["capability"]("container_exec", {
    "action": "input",
    "container_id": container["id"],
    "input_type": "click",
    "x": 500, "y": 300
})

context["capability"]("container_exec", {
    "action": "destroy",
    "container_id": container["id"]
})
```

如果显示选项为 true，则会在容器中启动 Xvfb（虚拟帧缓冲区），并且屏幕截图和输入操作（单击、键入、按键、滚动）可用。

container_exec 操作列表：

| action | description | required parameters |
|---|---|---|
| `create` | Container creation/startup | image, options |
| `exec` | Command execution in container | container_id, command |
| `screenshot` | Get display screenshot | container_id |
| `input` | Input to display | container_id, input_type, (x, y / text / key) |
| `upload` | Send file to container | container_id, host_path, container_path |
| `download` | Get file from container | container_id, container_path |
| `destroy` | Container destruction | container_id |
| `list` | List of running containers | None |

input_type 的类型：

| input_type | description | parameters |
|---|---|---|
| `click` | Coordinate click | x, y, button(left/right/middle) |
| `double_click` | Double click | x, y |
| `type` | Text input | text |
| `key` | Key transmission | key (e.g. "Enter", "Ctrl+C") |
| `scroll` | Scroll | x, y, delta |
| `drag` | Drag | from_x, from_y, to_x, to_y |

#### handler.py的返回值

```python
def run(params: dict, context: dict) -> dict:
    """
    params: schema.json で定義されたパラメータ（バリデーション済み）
    context: 汎用プリミティブ群

    返り値:
    {
        "result": str,              # LLM 向けテキスト（必須）
        "widget": dict,             # Widget JSON（任意。widget.md 参照）
        "llm_content": list[dict]   # マルチモーダル LLM コンテンツ（任意）
    }

    エラー時:
    {
        "error": True,
        "error_type": "timeout",
        "message": "ページ読み込みがタイムアウトしました",
        "recoverable": True
    }
    """
```

Widget JSON 遵循 widget.md 中定义的统一格式。您可以使用 rumi_widgets Python 帮助程序库或直接将其作为字典返回。

#### handler.py使用示例

**示例 1：文件读取（仅 data_read）**

```python
def run(params, context):
    content = context["data_read"](params["path"])
    return {
        "result": content,
        "widget": {
            "type": "code_block",
            "language": detect_language(params["path"]),
            "content": content,
            "filename": params["path"]
        }
    }
```

**示例 2：处理聊天消息 (call_handler)**

```python
def run(params, context):
    context["call_handler"]("defaults.chat.delete_message", {
        "conversation_id": params["conversation_id"],
        "message_id": params["message_id"]
    })
    return {"result": "Message deleted"}
```

**示例 3：向用户显示确认弹出窗口（emit_event + wait_event）**

```python
def run(params, context):
    popup_id = generate_id()

    context["emit_event"]("ui.popup.show", {
        "popup_id": popup_id,
        "title": "確認",
        "message": "この操作を実行しますか？",
        "buttons": ["OK", "キャンセル"]
    })

    response = context["wait_event"](
        "ui.popup.response",
        timeout=60,
        filter={"popup_id": popup_id}
    )

    if response["button"] == "OK":
        return {"result": "Executed"}
    else:
        return {"result": "Cancelled"}
```

**示例 4：向另一个代理请求任务 (call_handler)**

```python
def run(params, context):
    conv = context["call_handler"]("defaults.chat.create_conversation", {
        "model": "anthropic/claude-sonnet-4",
        "agent_id": "research_agent"
    })

    result = context["call_handler"]("defaults.agent.execute", {
        "agent_id": "research_agent",
        "conversation_id": conv["id"],
        "input": params["task"]
    })

    return {"result": result["final_text"]}
```

**示例 5：Docker 容器内的 GUI 操作（功能）**

```python
def run(params, context):
    container = context["capability"]("container_exec", {
        "action": "create",
        "image": "ubuntu:22.04",
        "options": {"display": True, "memory_limit": "1g"}
    })

    context["capability"]("container_exec", {
        "action": "exec",
        "container_id": container["id"],
        "command": f"firefox {params['url']} &"
    })

    import time; time.sleep(3)

    screenshot = context["capability"]("container_exec", {
        "action": "screenshot",
        "container_id": container["id"]
    })

    context["capability"]("container_exec", {
        "action": "input",
        "container_id": container["id"],
        "input_type": "click",
        "x": params["x"], "y": params["y"]
    })

    context["capability"]("container_exec", {
        "action": "destroy",
        "container_id": container["id"]
    })

    return {
        "result": "Operation complete",
        "widget": {
            "type": "screenshot",
            "src": screenshot["data"],
            "title": "Container screen"
        }
    }
```

**示例 6：通过 Flow 注册周期性执行（execute_flow）**

```python
def run(params, context):
    context["execute_flow"]("user_scheduled_task", {
        "task": params["task"],
        "agent_id": params.get("agent_id", "general"),
        "schedule": params["cron"]
    })
    return {"result": f"Scheduled: {params['cron']}"}
```

**示例7：搜索知识并返回结果（call_handler + data_read）**

```python
def run(params, context):
    results = context["call_handler"]("defaults.memory.vector_query", {
        "query": params["query"],
        "top_k": 5
    })

    return {
        "result": "\n---\n".join([r["content"] for r in results["matches"]]),
        "widget": {
            "type": "collapsible",
            "label": f"{len(results['matches'])} results found",
            "children": [
                {"type": "markdown", "content": r["content"]}
                for r in results["matches"]
            ]
        }
    }
```

**示例 8：生成新工具（data_write）**

```python
import json

def run(params, context):
    tool_id = params["tool_id"]
    base_path = f"shared/tools/{tool_id}"

    context["data_write"](f"{base_path}/tool.json", json.dumps({
        "tool_id": tool_id,
        "name": params["name"],
        "summary": params["summary"],
        "version": "1.0.0",
        "status": "draft",
        "author": "user",
        "tags": params.get("tags", []),
        "execution": {"type": "local", "timeout": 30}
    }, indent=2))

    context["data_write"](f"{base_path}/schema.json", json.dumps(
        params["schema"], indent=2
    ))

    context["data_write"](f"{base_path}/handler.py",
        params.get("handler_code", 'def run(params, context):\n    return {"result": "not implemented"}')
    )

    return {"result": f"Tool '{tool_id}' created at user_data/{base_path}/"}
```

一切都由以下通用原语组成：call_handler、emit_event、wait_event、data_read、data_write、capability、execute_flow 和emit_widget。如果添加新的处理程序或流，该工具可以在同一原语上调用它们。

### 3.8 能力/目录（可选）

如果该工具附带主机端功能处理程序。

```
bash/capability/
├── capability.json
└── handler.py
```

**能力.json：**

```json
{
  "capability_id": "shell_exec",
  "name": "Shell Execution",
  "description": "永続シェルセッションでコマンドを実行する",
  "version": "1.0.0",
  "risk_level": "critical",
  "scope": "public",
  "host_requirements": [],
  "interface": {
    "actions": ["execute", "read_output", "kill"],
    "input_schema": {
      "execute": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "command": { "type": "string" },
          "timeout": { "type": "integer", "default": 120000 },
          "run_in_background": { "type": "boolean", "default": false }
        },
        "required": ["command"]
      }
    }
  }
}
```

`scope`：`"public"`还可以与`capabilities_required`一起使用其他工具。 `"private"` 是该工具独有的。

主机端handler.py需经过用户显式批准+哈希记录+修改检测。

---

## 4.defaults.json

所有工具通用的全局设置。

```json
{
  "stage_threshold": 15,

  "approval": {
    "global_approval_mode": "per_session",
    "auto_approve_verified_packs": true
  },

  "rate_limit": {
    "max_total_calls_per_minute": 30,
    "max_total_calls_per_session": 500
  },

  "cache": {
    "enabled": true,
    "ttl_seconds": 60,
    "max_entries": 100
  },

  "session": {
    "default_timeout_seconds": 300,
    "max_concurrent_sessions": 10
  },

  "shell": {
    "session_timeout_seconds": 600,
    "max_output_buffer_bytes": 1048576,
    "max_concurrent_shells": 5,
    "default_command_timeout_ms": 120000
  },

  "container": {
    "max_concurrent": 3,
    "default_memory_limit": "512m",
    "default_timeout_seconds": 300,
    "allowed_images": ["ubuntu:*", "debian:*", "alpine:*", "node:*", "python:*"]
  },

  "llm_call": {
    "default_model": "fast",
    "max_calls_per_execution": 3,
    "max_input_tokens": 10000,
    "max_output_tokens": 2000
  },

  "agent": {
    "max_parallel_agents": 5,
    "max_iterations_per_agent": 15,
    "max_tokens_per_agent": 50000
  },

  "display": {
    "max_images_in_context": 3,
    "max_output_chars": 30000
  },

  "disabled_tools": [],

  "sync": {
    "source": {
      "repo": "harupipipipi/rumiai",
      "path": "rumi_ai_1_10/ecosystem/default/share/tools"
    },
    "auto_check_interval_hours": 24
  },

  "pack_install": {
    "marketplace_registry": {
      "repo": "harupipipipi/rumi-marketplace",
      "path": "registry.json",
      "cache_ttl_hours": 6
    },
    "auto_approve_verified": true,
    "block_blacklisted": true
  }
}
```

| Key | Description |
|------|------|
| `stage_threshold` | If you have more than this number of tools, use gradual disclosure |
| `approval.global_approval_mode` | `per_call` / `per_session` / `auto` |
| `approval.auto_approve_verified_packs` | Auto-approve tools for marketplace verified packs |
| `rate_limit.max_total_calls_per_minute` | Total call limit for all tools per minute |
| `cache.ttl_seconds` | idempotent tool result cache time |
| `shell.*` | Configuring a persistent shell session |
| `container.*` | Configuring Docker containers |
| `llm_call.*` | Default limits for in-tool LLM calls |
| `agent.*` | Subagent (Task tool) limitations |
| `display.max_images_in_context` | Maximum number of images to pass to LLM |
| `display.max_output_chars` | Tool output truncation threshold |
| `disabled_tools` | List of tool IDs to disable |
| `sync.*` | GitHub repository from which tool definitions are synchronized |
| `pack_install.*` | Pack installation related settings |

---

## 5. 外部依赖和 Pack 协调

### 5.1 工具要求包

Permission.json 中的 `pack_dependencies` 允许工具请求外部包。

```json
{
  "capabilities_required": ["browser_control"],
  "pack_dependencies": {
    "rumi-browser-runtime": {
      "repo": "harupipipipi/rumi-browser-runtime",
      "path": ".",
      "version": ">=1.0.0",
      "reason": "browser_control capability を提供する Pack"
    }
  }
}
```

在运行该工具之前，executor.py 会检查并建议用户安装任何已卸载的包：

```
⚠️ ツール「browser_navigate」は以下の Pack が必要です:

  ✅ rumi-browser-runtime v1.2.0 (Rumi 検証済み)
     ブラウザ制御の Capability Handler を提供

[導入して続行] [キャンセル]
```

### 5.2 包依赖解析

包本身也可以依赖于其他包（pack.json 中的`dependencies`）。

```json
{
  "pack_id": "my_coding_assistant",
  "version": "1.0.0",
  "dependencies": {
    "rumi-shell-capability": {
      "repo": "harupipipipi/rumi-shell-capability",
      "path": ".",
      "version": ">=1.0.0"
    },
    "rumi-browser-tools": {
      "repo": "someone/rumi-browser-tools",
      "path": "packs/browser",
      "version": "^2.0.0"
    }
  },
  "provides": {
    "tools": ["file_read", "file_edit", "bash", "grep", "glob"],
    "capabilities": [],
    "flows": ["coding_agent"]
  }
}
```

### 5.3 下载（无需 git）

使用 GitHub API 的 zipball。不需要 git 命令。

```
GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
```

下载后，解压并仅提取`path`中指定的目录，并将其放置在`user_data/packs/`中。需要身份验证的私有存储库使用 `GITHUB_TOKEN` 环境变量。

### 5.4 市场注册

`harupipipipi/rumi-marketplace`存储库`registry.json`：

```json
{
  "registry_version": "1.0.0",
  "updated_at": "2026-02-14",
  "packs": {
    "harupipipipi/rumi-shell-capability": {
      "status": "verified",
      "verified_versions": ["1.0.0", "1.1.0", "1.2.0"],
      "latest_verified": "1.2.0",
      "categories": ["capability", "shell"],
      "risk_level": "high",
      "description": "永続シェルセッション capability",
      "verified_hashes": {
        "1.2.0": "sha256:abc123..."
      }
    }
  }
}
```

状态：`"verified"`已由Rumi团队验证。 `"unverified"`尚未得到验证。 `"blacklisted"`被确定为危险的。

### 5.5 .pack_meta.json

下载的Pack中自动生成的管理文件。

```json
{
  "source": {
    "repo": "harupipipipi/rumi-shell-capability",
    "path": ".",
    "ref": "v1.2.0",
    "downloaded_at": "2026-02-14T10:00:00Z"
  },
  "hash": "sha256:abc123...",
  "installed_by": ["my_coding_assistant"],
  "approval": {
    "approved": true,
    "approved_at": "2026-02-14T10:01:00Z",
    "approved_capabilities": ["shell_exec"]
  },
  "verification": {
    "status": "verified",
    "verified_by": "rumi-marketplace",
    "checked_at": "2026-02-14T10:00:30Z"
  }
}
```

### 5.6 实现流程

```
ユーザーまたはツールが Pack を要求
  │
  ├─ pack.json を先読み（zipball から pack.json だけ取得）
  │
  ├─ dependencies を再帰的に解決
  │   ├─ 既にインストール済み → スキップ
  │   ├─ バージョン衝突 → 報告
  │   └─ 未導入 → ダウンロード対象に追加
  │
  ├─ marketplace レジストリと照合
  │   ├─ verified → ✅
  │   ├─ unverified → ❓ + 警告
  │   └─ blacklisted → 🚫 ブロック
  │
  ├─ ユーザーに承認画面を表示
  │
  ├─ 承認後ダウンロード
  │   ├─ zipball 取得 → 解凍 → user_data/packs/ に配置
  │   ├─ ハッシュ記録
  │   └─ .pack_meta.json 生成
  │
  └─ ロード
      ├─ capability → ホスト側に登録
      ├─ tool → loader に登録
      └─ flow → 利用可能に
```

### 5.7 能力搜索优先级

executor.py 解析工具的 `capabilities_required` 的顺序：

1. 系统集成（`ecosystem/default/backend/capabilities/`）
2. 共享能力 (`user_data/shared/capabilities/`)
3. 包含工具 (`tools/xxx/capability/`)
4. 提供包装 (`user_data/packs/xxx/capabilities/`)
5.自动从`pack_dependencies`获得→放置在4中

---

## 6. 逐步披露

### 第 1 阶段：目录（如果工具数量 > stage_threshold）

将轻量级工具目录注入LLM的系统提示符中：

```
利用可能なツール:
- file_read: ファイルの内容を読み取る [filesystem, read]
- file_edit: ファイルの内容を部分的に編集する [filesystem, write]
- bash: シェルコマンドを実行する [shell, execution]
- browser_navigate: Web ページを開く [browser, web]
- web_search: Web 検索を実行する [web, search]
...

使用したいツールの名前を返してください。
```

从每个工具中仅提取 `name`、`summary`、`tags`、`use_cases` 或 `tool.json`。

### 第 2 阶段：详细信息（所选工具或工具数量 ≤ stage_threshold）

将完整架构传递给 LLM 的 `tools` 参数。将 `guide.json` 的 `usage_guide` 和 `tips` 插入描述中。

### 第 3 阶段：运行时

`conditions.json` 评估 → `handler_config` 注入 → `handler.py` 执行。

---

## 7. 小部件集成

handler.py 返回的 `widget` 字段遵循 widget.md 中定义的统一小部件方案。所有域（工具、提示、ai_client、聊天、代理）都以相同的小部件格式声明 UI 显示。

从 handler.py 发送 Widget 有两种方法。

将最终结果 Widget 包含在返回值的`widget`字段中。该工具运行完毕后将显示此信息。

使用 `context["emit_widget"]` 在执行期间实时发送小部件。用于进度显示和流式显示。

```python
def run(params, context):
    # 実行中の進捗表示
    context["emit_widget"]({"type": "progress", "label": "Reading...", "current": 0, "total": 1})

    content = context["data_read"](params["path"])

    context["emit_widget"]({"type": "progress", "label": "Done", "current": 1, "total": 1})

    # 最終結果の Widget
    return {
        "result": content,
        "widget": {
            "type": "card",
            "header": {"type": "indicator", "label": "file_read", "state": "success"},
            "body": {
                "type": "code_block",
                "language": detect_language(params["path"]),
                "content": content,
                "filename": params["path"]
            },
            "footer": {"type": "text", "text": f"{len(content)} bytes"}
        }
    }
```

有关小组件类型、JSON 格式和主题集成的列表，请参阅 widget.md。您可以通过导入 rumi_widgets Python 帮助程序库（`ecosystem/defaults/lib/rumi_widgets/`）来基于类构建小部件，但它相当于直接将其作为字典返回。

---

## 8.后端处理

### 8.1 Executor.py流程

```
tool_call 受信
  │
  ├─ loader.py でツール定義を取得
  │
  ├─ モデルプロファイルを取得（ai_client/loader）
  │
  ├─ conditions.json を評価
  │   ├─ incompatible → エラー返却
  │   ├─ requirements → 未達なら fallback_variant 適用 or エラー
  │   ├─ behavior_variants → handler_config を選択
  │   └─ recommendations → ログのみ
  │
  ├─ permission_checker.py
  │   ├─ capabilities_required のチェック
  │   ├─ pack_dependencies の充足確認
  │   │   └─ 未充足 → ユーザーに Pack 導入を提案
  │   ├─ parameter_restrictions のバリデーション
  │   ├─ rate_limit チェック
  │   └─ requires_approval → 承認要求
  │
  ├─ readiness check（readiness/check.py がある場合）
  │
  ├─ キャッシュ確認（idempotent && cache hit）
  │
  ├─ context 構築
  │   ├─ 常に注入: call_handler, emit_event, wait_event, emit_widget,
  │   │            cancel_check, handler_config, session
  │   └─ capabilities_required に基づいて注入:
  │        data_read, data_write, execute_flow, capability(*)
  │
  ├─ handler.py 実行
  │   ├─ local → Docker 内で直接実行
  │   ├─ capability → Capability Handler 経由
  │   ├─ mcp → mcp_client 経由
  │   └─ http → llm_network 経由
  │
  ├─ 結果正規化
  │   ├─ 成功 → { result, widget, llm_content }
  │   └─ エラー → { error, error_type, message, recoverable }
  │
  ├─ 監査ログ（audit: true の場合）
  │
  └─ 結果返却
```

### 8.2 converter.py 中的 4 路转换

1. **工具定义→LLM格式**：tool.json + schema.json→OpenAI函数/Anthropic工具格式
2. **LLM tool_calls → Rumi统一格式**：统一每个提供商的tool_call格式
3. **执行结果→LLM消息格式**：result/llm_content→各provider的消息格式
4. **prompt_based support**：针对不支持tool_calls的模型进行提示嵌入+响应解析

`capabilities.json` 的 `tool_result_image_support` 处的图像支持分支：`true`（人择）可以在 tool_result 中包含图像。 `false` (OpenAI) 将图像作为以下用户消息发送。

### 8.3 会话管理器.py

```python
class SessionManager:
    """セッション内の状態とシェルを管理"""

    def create_shell(self) -> ShellSession: ...
    def get_shell(self, session_id: str) -> ShellSession: ...
    def kill_shell(self, session_id: str): ...
    def list_shells(self) -> list[ShellSession]: ...

    def get_state(self, session_id: str) -> SessionState: ...

    def cleanup_expired(self): ...


class ShellSession:
    """永続シェルセッション"""
    session_id: str
    process: ...
    output_buffer: list
    last_read_position: int
    background: bool
    created_at: datetime

    def execute(self, command: str, timeout: int) -> dict: ...
    def read_output(self, filter_pattern: str = None) -> str: ...
    def kill(self): ...


class SessionState:
    """セッション内の key-value 状態"""
    def get(self, key, default=None): ...
    def set(self, key, value): ...
    def delete(self, key): ...
```

### 8.4 loader.py遍历顺序

1. `user_data/shared/tools/`（用户管理）
2. `user_data/packs/*/tools/`（Pack提供）
3.从MCP服务器动态获取

对于同名的工具，共享优先。

### 8.5 mcp_client.py

与所有 MCP 功能兼容：

| MCP Features | Implementation |
|----------|------|
| Tools (tools/list, tools/call) | Register as a tool, execution.type = "mcp" |
| Resources (resources/list, resources/read, resources/subscribe) | Injected into Flow context |
| Prompts (prompts/list, prompts/get) | Available as a template |
| Sampling (sampling/createMessage) | LLM call via ai_client |
| Roots (roots/list) | Notify workspace path |
| Elicitation (elicitation/create) | Contact user with emit_event |

mcp.json配置示例：

```json
{
  "servers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${env.GITHUB_TOKEN}" },
      "capabilities": {
        "tools": true,
        "resources": true,
        "prompts": false
      },
      "auto_connect": true,
      "max_reconnect_attempts": 3
    }
  },
  "client_capabilities": {
    "sampling": true,
    "roots": true,
    "elicitation": true
  }
}
```

---

## 9. 流程整合

### 基本聊天+工具

```yaml
# flows/simple_chat/flow.yaml
flow_id: simple_chat
trigger:
  type: user_input
handler: handler.py
blocks_used:
  - chat.save_message
  - context.build
  - ai_client.completion
  - tool.execute
```

```python
# flows/simple_chat/handler.py
async def run(ctx):
    messages = await ctx.call_block("context.build", ...)
    response = await ctx.call_block("ai_client.completion",
        model=ctx.flow_config["model"],
        messages=messages,
        tools=load_tools())

    if response.get("tool_calls"):
        for tc in response["tool_calls"]:
            result = await ctx.call_block("tool.execute",
                tool_name=tc["name"],
                arguments=tc["arguments"],
                session=ctx.session)
            # tool 結果をメッセージに追加してループ
    ...
```

### 代理聊天

```yaml
# flows/agent_chat/flow.yaml
flow_id: agent_chat
trigger:
  type: user_input
handler: handler.py
blocks_used:
  - agent.run
  - chat.save_message
  - chat.load_conversation
  - memory.save
```

### 自定义流程（用户数据）

用户或包将流添加到`user_data/shared/flows/`。可以使用 `context["execute_flow"]` 从工具的 handler.py 启动。通过使用 Flow 的事件触发器，您还可以实现钩子，例如当 user_input 到达时自动运行知识搜索工具。

```yaml
# user_data/shared/flows/knowledge_hook/flow.yaml
flow_id: knowledge_hook
trigger:
  type: event
  config:
    source: "chat"
    events: ["user_input"]
nodes:
  - id: search
    type: tool
    tool_name: knowledge_search
    arguments:
      query: "{{ start.message }}"
  - id: inject
    type: variable
    set:
      context_extra: "{{ search.result }}"
```

---

## 10. 准备情况检查

通过将`readiness/check.py`放入工具中，您可以在执行前检测环境。

```python
# readiness/check.py
def check(context: dict) -> dict:
    """
    context: which, env, run, secrets, http
    返り値: ready, message, details, fixable, fix_instructions
    """
    if not context["which"]("chromium"):
        return {
            "ready": False,
            "message": "Chromium が見つかりません",
            "fixable": True,
            "fix_instructions": "apt install chromium-browser"
        }
    return {"ready": True, "message": "OK"}
```

执行时间：包批准后、应用程序启动时（并行）、资源使用前（缓存优先级）、由用户手动执行。缓存 TTL 默认为 300 秒。准备就绪设置为False的资源将在UI上标有警告标记，但用户可以有意使用它们。
