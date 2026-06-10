<!-- docs-i18n-links:start -->
[EN](./tool.md) | [JP](./i18n/ja/tool.md) | [KR](./i18n/ko/tool.md) | [CN](./i18n/zh-cn/tool.md)
<!-- docs-i18n-links:end -->

# Tool Module

## 1. Design philosophy

The Tool module is a mechanism for LLM to perform external operations on behalf of the user in Rumi AI OS.

Design principles:
- **Data-driven**: Tool definition is a JSON/YAML file. The logic is handler.py. You can extend the tool by simply adding directories.
- **General-purpose primitives only**: The context API injected into handler.py consists only of general-purpose primitives. All domain operations such as chat operations, agent activation, memory reading and writing are realized by a combination of general-purpose primitives. There are no domain-specific APIs.
- **Step-by-step disclosure**: If there are many tools, first pass only the catalog (name/summary) to LLM, then pass the detailed schema after selection. Save tokens and increase selection accuracy.
- **Minimum privilege**: The context API that handler.py can use is injected based on the declaration in permission.json. APIs that are not declared cannot be used.
- **External dependency resolution**: If the capabilities or packs required by a tool have not been installed, they can be automatically acquired from the GitHub repository without using git.

---

## 2. Directory structure

### Tool placement

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

Pack-provided tools are placed in `user_data/packs/*/tools/`.

### Backend code

```
ecosystem/default/backend/blocks/tool/
├── loader.py                  # ツール定義の走査・マージ・キャッシュ
├── converter.py               # 4方向変換（定義↔LLM, 結果↔LLM）
├── executor.py                # 実行エンジン
├── permission_checker.py      # 権限検証
├── session_manager.py         # シェルセッション・状態管理
└── mcp_client.py              # MCP サーバー接続
```

### Pack management code

```
ecosystem/default/backend/blocks/pack/
├── downloader.py              # GitHub API で zipball ダウンロード
├── resolver.py                # 依存解決・バージョンマッチング
├── installer.py               # 配置・ハッシュ記録
├── verifier.py                # marketplace レジストリ照合
└── updater.py                 # アップデートチェック
```

---

## 3. Tool definition file

### 3.1 tool.json (required)

Tool meta information. Passed to LLM at Stage 1 of the staged disclosure.

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

**execution.type type:**

| type | Description | Operating location |
|------|------|----------|
| `local` | Run handler.py directly | In Docker |
| `capability` | Via Capability Handler | Host side |
| `mcp` | Via MCP server | External process |
| `http` | HTTP request | via llm_network |

### 3.2 schema.json (required)

JSON Schema definition for input and output. Passed to LLM at Stage 2 of the staged disclosure.

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

### 3.3 guide.json

Details on how to use. The description is injected into the LLM at Stage 2 of gradual disclosure.

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

### 3.4 conditions.json

Behavior branching according to model capabilities.

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

### 3.5 permission.json

Authority/approval/restriction.

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

**`pack_dependencies`**: External Packs required by this tool. If the specified Pack has not been installed, automatic acquisition will be suggested from `repo`.

**`capabilities_required`**: Capability declaration injected into handler.py's context. Only the capabilities declared here are injected into the context.

When using `llm_call`, you can set it to `llm_call_allowed: true` and write the restrictions:

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

### 3.6 relations.json

Cooperation tools, chain patterns, and dependencies.

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

### 3.7 handler.py (required)

Tool execution logic.

#### context API

The context injected into handler.py consists only of general-purpose primitives. There are no APIs specific to specific domains (chat, agents, etc.). All domain operations are realized by combinations of general-purpose primitives.

**Always injected (no declaration required):**

| context key | description |
|---|---|
| `context["call_handler"]` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `context["emit_event"]` | Publish an event. handler, flow, front end can receive |
| `context["wait_event"]` | Wait for an event. Timeout can be specified |
| `context["emit_widget"]` | Send Widget JSON to the UI |
| `context["cancel_check"]` | Cancellation confirmation |
| `context["handler_config"]` | Settings injected from behavior_variants in conditions.json |
| `context["session"]` | Session information (session_id, workspace, etc.) |

**Declared and injected in `capabilities_required` of permission.json:**

| capability_id | description | context key | risk |
|---|---|---|---|
| `data_read` | Read file under user_data | `context["data_read"](§RUMI§0§) → str` | Low |
| `data_write` | Writing files under user_data | `context["data_write"](§RUMI§0§)` | Medium |
| `execute_flow` | Start Flow | `context["execute_flow"](§RUMI§0§) → FlowResult` | Medium |
| `shell_exec` | Shell command execution | `context["capability"](§RUMI§0§)` | High |
| `browser_control` | Browser operation | `context["capability"](§RUMI§0§)` | High |
| `container_exec` | Starting, operating, and destroying Docker containers | `context["capability"](§RUMI§0§)` | High |
| `app_control` | Host application operation | `context["capability"](§RUMI§0§)` | High |
| `http_request` | External HTTP communication | `context["capability"](§RUMI§0§)` | Medium |
| `llm_call` | In-tool LLM call | `context["capability"](§RUMI§0§)` | Medium |
| `session_state` | Session state read/write | `context["capability"](§RUMI§0§)` | Low |

#### call_handler

Generic gateway that calls any handler. All handlers registered by defaults and Pack can be called. handler is defined in the handler system in README.md.

```python
result = context["call_handler"](
    "defaults.chat.send",
    {
        "conversation_id": "conv-1",
        "content": "hello"
    }
)
```

call_handler processes in the following order. Check the permissions declared in permission.json of the calling tool. Verify that the caller's permissions include the permissions requested by the called handler. If it is not included, it will be rejected with PermissionError. If it is included, execute handler and return the result.

This allows tool to call any handler on the system within its authority. Chat operations, agent activation, memory read/write, prompt rendering, all can be done via call_handler.

#### emit_event / wait_event

Events are a general purpose communication mechanism throughout the system.

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

The recipient of the event can be a handler, a Flow event trigger, or a front-end Asset. emit_event only issues it to the event bus, and the issuer is not concerned with who receives it.

#### data_read / data_write

General purpose file I/O to read and write any file under user_data.

```python
content = context["data_read"]("chat/conversations/conv-1.json")
context["data_write"]("knowledge/sources/notes.md", content)
```

The path is relative to user_data/. Access outside user_data is denied.

#### execute_flow

Launch any Flow. Executed via Flow Engine.

```python
result = context["execute_flow"](
    "my_custom_flow",
    {"query": "search this"}
)
```

#### container_exec capability

A general-purpose capability to manipulate the Docker container lifecycle.

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

If the display option is true, Xvfb (virtual framebuffer) is started in the container and screenshot and input actions (click, type, key, scroll) are available.

List of container_exec actions:

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

Type of input_type:

| input_type | description | parameters |
|---|---|---|
| `click` | Coordinate click | x, y, button(left/right/middle) |
| `double_click` | Double click | x, y |
| `type` | Text input | text |
| `key` | Key transmission | key (e.g. "Enter", "Ctrl+C") |
| `scroll` | Scroll | x, y, delta |
| `drag` | Drag | from_x, from_y, to_x, to_y |

#### Return value of handler.py

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

Widget JSON follows a uniform format defined in widget.md. You can use the rumi_widgets Python helper library or return it directly as a dict.

#### handler.py usage example

**Example 1: File read (data_read only)**

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

**Example 2: Handling chat messages (call_handler)**

```python
def run(params, context):
    context["call_handler"]("defaults.chat.delete_message", {
        "conversation_id": params["conversation_id"],
        "message_id": params["message_id"]
    })
    return {"result": "Message deleted"}
```

**Example 3: Show confirmation popup to user (emit_event + wait_event)**

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

**Example 4: Request a task to another agent (call_handler)**

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

**Example 5: GUI operation within a Docker container (capability)**

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

**Example 6: Register periodic execution via Flow (execute_flow)**

```python
def run(params, context):
    context["execute_flow"]("user_scheduled_task", {
        "task": params["task"],
        "agent_id": params.get("agent_id", "general"),
        "schedule": params["cron"]
    })
    return {"result": f"Scheduled: {params['cron']}"}
```

**Example 7: Search knowledge and return results (call_handler + data_read)**

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

**Example 8: Generate a new tool (data_write)**

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

Everything consists of the following generic primitives: call_handler, emit_event, wait_event, data_read, data_write, capability, execute_flow, and emit_widget. If new handlers or Flows are added, the tool can call them on the same primitive.

### 3.8 capability/ directory (optional)

If the tool ships with a host-side Capability Handler.

```
bash/capability/
├── capability.json
└── handler.py
```

**capability.json:**

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

`scope`: `"public"` can also use other tools with `capabilities_required`. `"private"` is exclusive to this tool.

The host side handler.py is subject to user explicit approval + hash record + modification detection.

---

## 4. defaults.json

Global settings common to all tools.

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

## 5. External dependencies and Pack coordination

### 5.1 Tools ask for Packs

`pack_dependencies` in permission.json allows tools to request external Packs.

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

Before running the tool, executor.py checks and suggests to the user to install any uninstalled packs:

```
⚠️ ツール「browser_navigate」は以下の Pack が必要です:

  ✅ rumi-browser-runtime v1.2.0 (Rumi 検証済み)
     ブラウザ制御の Capability Handler を提供

[導入して続行] [キャンセル]
```

### 5.2 Pack dependency resolution

Packs themselves can also depend on other Packs (`dependencies` in pack.json).

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

### 5.3 Download (without git)

Uses GitHub API's zipball. No git command required.

```
GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
```

After downloading, unzip and extract only the directory specified in `path` and place it in `user_data/packs/`. Private repositories that require authentication use the `GITHUB_TOKEN` environment variable.

### 5.4 Marketplace Registry

`harupipipipi/rumi-marketplace` Repository `registry.json`:

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

Status: `"verified"` has been verified by the Rumi team. `"unverified"` has not been verified. `"blacklisted"` is determined to be dangerous.

### 5.5 .pack_meta.json

Management file that is automatically generated in the downloaded Pack.

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

### 5.6 Implementation flow

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

### 5.7 Capability search priority

The order in which executor.py resolves `capabilities_required` for tools:

1. System integration (`ecosystem/default/backend/capabilities/`)
2. Shared capability (`user_data/shared/capabilities/`)
3. Tool included (`tools/xxx/capability/`)
4. Pack provided (`user_data/packs/xxx/capabilities/`)
5. Automatically obtained from `pack_dependencies` → placed in 4

---

## 6. Gradual disclosure

### Stage 1: Catalog (if number of tools > stage_threshold)

Inject a lightweight tool catalog into LLM's system prompt:

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

Extract only `name`, `summary`, `tags`, `use_cases` of `tool.json` from each tool.

### Stage 2: Details (selected tools or number of tools ≤ stage_threshold)

Pass the complete schema to the LLM's `tools` parameter. Inject `usage_guide` and `tips` of `guide.json` into description.

### Stage 3: Runtime

Evaluation of `conditions.json` → `handler_config` Injection → `handler.py` Execution.

---

## 7. Widget integration

The `widget` fields returned by handler.py follow the unified widget scheme defined in widget.md. All domains (tool, prompt, ai_client, chat, agent) declare UI display in the same widget format.

There are two ways to send Widgets from handler.py.

Include the final result Widget in the `widget` field of the return value. This will be displayed after the tool has finished running.

Send a widget in real time during execution with `context["emit_widget"]`. Used for progress display and streaming display.

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

For a list of widget types, JSON format, and theme integration, see widget.md. You can build a widget on a class basis by importing the rumi_widgets Python helper library (`ecosystem/defaults/lib/rumi_widgets/`), but it is equivalent to return it directly as a dict.

---

## 8. Backend processing

### 8.1 Executor.py flow

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

### 8.2 4-way conversion in converter.py

1. **Tool definition → LLM format**: tool.json + schema.json → OpenAI function / Anthropic tool format
2. **LLM tool_calls → Rumi unified format**: Unify tool_call format for each provider
3. **Execution result → LLM message format**: result / llm_content → message format for each provider
4. **prompt_based support**: prompt embedding + response parsing for models that do not support tool_calls

Image support branches at `tool_result_image_support` of `capabilities.json`: `true` (Anthropic) can include images in tool_result. `false` (OpenAI) sends the image as the following user message.

### 8.3 session_manager.py

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

### 8.4 loader.py traversal order

1. `user_data/shared/tools/` (User management)
2. `user_data/packs/*/tools/` (provided by Pack)
3. Dynamic acquisition from MCP server

For tools with the same name, shared takes precedence.

### 8.5 mcp_client.py

Compatible with all MCP features:

| MCP Features | Implementation |
|----------|------|
| Tools (tools/list, tools/call) | Register as a tool, execution.type = "mcp" |
| Resources (resources/list, resources/read, resources/subscribe) | Injected into Flow context |
| Prompts (prompts/list, prompts/get) | Available as a template |
| Sampling (sampling/createMessage) | LLM call via ai_client |
| Roots (roots/list) | Notify workspace path |
| Elicitation (elicitation/create) | Contact user with emit_event |

mcp.json configuration example:

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

## 9. Flow integration

### Basic Chat + Tools

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

### Agent chat

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

### Custom flow (user_data)

Users or Packs add flows to `user_data/shared/flows/`. Can be started from the tool's handler.py with `context["execute_flow"]`. By using Flow's event trigger, you can also implement hooks such as automatically running a knowledge search tool when user_input arrives.

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

## 10. Readiness Check

By placing `readiness/check.py` in the tool, you can detect the environment before execution.

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

Execution timing: Upon pack approval, at app startup (parallel), immediately before resource usage (cache priority), manually by user. Cache TTL defaults to 300 seconds. Resources with readiness set to False will be marked with a warning mark on the UI, but users can use them intentionally.
