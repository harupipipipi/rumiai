<!-- docs-i18n-links:start -->
[EN](../../tool.md) | [JP](./tool.md) | [KR](../ko/tool.md) | [CN](../zh-cn/tool.md)
<!-- docs-i18n-links:end -->

# ツールモジュール

## 1. 設計思想

Tool モジュールは、LLM が Rumi AI OS でユーザーに代わって外部操作を実行するためのメカニズムです。

設計原則:
- **データドリブン**: ツール定義は JSON/YAML ファイルです。ロジックは handler.py です。ディレクトリを追加するだけでツールを拡張できます。
- **汎用プリミティブのみ**: handler.py に挿入されるコンテキスト API は、汎用プリミティブのみで構成されます。チャット操作、エージェントの起動、メモリの読み書きなどのドメイン操作はすべて汎用プリミティブの組み合わせで実現します。ドメイン固有の API はありません。
- **段階的な公開**: ツールが多い場合は、最初にカタログ (名前/概要) のみを LLM に渡し、選択後に詳細なスキーマを渡します。トークンを節約し、選択の精度を高めます。
- **最小権限**: handler.py が使用できるコンテキスト API は、permission.json の宣言に基づいて挿入されます。宣言されていないAPIは使用できません。
- **外部依存関係の解決**: ツールに必要な機能またはパックがインストールされていない場合は、git を使用せずに GitHub リポジトリから自動的に取得できます。

---

## 2. ディレクトリ構造

### ツールの配置

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

パックが提供するツールは `user_data/packs/*/tools/` に配置されます。

### バックエンドコード

```
ecosystem/default/backend/blocks/tool/
├── loader.py                  # ツール定義の走査・マージ・キャッシュ
├── converter.py               # 4方向変換（定義↔LLM, 結果↔LLM）
├── executor.py                # 実行エンジン
├── permission_checker.py      # 権限検証
├── session_manager.py         # シェルセッション・状態管理
└── mcp_client.py              # MCP サーバー接続
```

### パック管理コード

```
ecosystem/default/backend/blocks/pack/
├── downloader.py              # GitHub API で zipball ダウンロード
├── resolver.py                # 依存解決・バージョンマッチング
├── installer.py               # 配置・ハッシュ記録
├── verifier.py                # marketplace レジストリ照合
└── updater.py                 # アップデートチェック
```

---

## 3. ツール定義ファイル

### 3.1 tools.json (必須)

ツールのメタ情報。段階的開示のステージ 1 で LLM に渡されます。

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

**execution.type タイプ:**

| type | Description | Operating location |
|------|------|----------|
| `local` | Run handler.py directly | In Docker |
| `capability` | Via Capability Handler | Host side |
| `mcp` | Via MCP server | External process |
| `http` | HTTP request | via llm_network |

### 3.2 schema.json (必須)

入力と出力の JSON スキーマ定義。段階的開示のステージ 2 で LLM に渡されます。

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

使用方法の詳細。説明は、段階的な開示のステージ 2 で LLM に挿入されます。

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

モデルの機能に応じて動作が分岐します。

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

### 3.5 許可.json

権限・承認・制限。

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

**`pack_dependencies`**: このツールに必要な外部パック。指定された Pack がインストールされていない場合は、`repo`.**`capabilities_required`**: handler.py のコンテキストに挿入された Capability 宣言から自動取得が提案されます。ここで宣言された機能のみがコンテキストに挿入されます。

`llm_call` を使用する場合、これを `llm_call_allowed: true` に設定し、制限を記述することができます。

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

### 3.6 関係.json

連携ツール、チェーン パターン、依存関係。

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

### 3.7 handler.py (必須)

ツールの実行ロジック。

#### コンテキスト API

handler.py に注入されるコンテキストは、汎用プリミティブのみで構成されます。特定のドメイン (チャット、エージェントなど) に固有の API はありません。すべてのドメイン操作は汎用プリミティブの組み合わせによって実現されます。

**常に注入されます (宣言は必要ありません):**

| context key | description |
|---|---|
| `context["call_handler"]` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `context["emit_event"]` | Publish an event. handler, flow, front end can receive |
| `context["wait_event"]` | Wait for an event. Timeout can be specified |
| `context["emit_widget"]` | Send Widget JSON to the UI |
| `context["cancel_check"]` | Cancellation confirmation |
| `context["handler_config"]` | Settings injected from behavior_variants in conditions.json |
| `context["session"]` | Session information (session_id, workspace, etc.) |

**permission.json の `capabilities_required` で宣言および挿入されます:**

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

#### コールハンドラー

任意のハンドラーを呼び出す汎用ゲートウェイ。デフォルトで登録されているすべてのハンドラーと Pack を呼び出すことができます。ハンドラーは、README.md のハンドラー システムで定義されています。

```python
result = context["call_handler"](
    "defaults.chat.send",
    {
        "conversation_id": "conv-1",
        "content": "hello"
    }
)
```

call_handler は次の順序で処理します。呼び出しツールのpermission.jsonで宣言されている権限を確認してください。呼び出し元のアクセス許可に、呼び出されたハンドラーによって要求されたアクセス許可が含まれていることを確認します。含まれていない場合は、PermissionError で拒否されます。含まれている場合はハンドラを実行し、結果を返します。

これにより、ツールはその権限内でシステム上の任意のハンドラーを呼び出すことができます。チャット操作、エージェントのアクティブ化、メモリの読み取り/書き込み、プロンプトのレンダリングはすべて call_handler 経由で実行できます。

#### エミットイベント / 待機イベント

イベントは、システム全体にわたる汎用の通信メカニズムです。

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

イベントの受信者は、ハンドラー、フロー イベント トリガー、またはフロントエンド アセットにすることができます。 Emit_event はそれをイベント バスに発行するだけであり、発行者はそれを誰が受け取るかには関係ありません。

#### データ読み取り / データ書き込み

user_data の下にある任意のファイルを読み書きするための汎用ファイル I/O。

```python
content = context["data_read"]("chat/conversations/conv-1.json")
context["data_write"]("knowledge/sources/notes.md", content)
```

パスは user_data/ に対する相対パスです。 user_data 外部のアクセスは拒否されます。

#### 実行フロー

任意のフローを起動します。フローエンジン経由で実行されます。

```python
result = context["execute_flow"](
    "my_custom_flow",
    {"query": "search this"}
)
```

#### container_exec 機能

Docker コンテナのライフサイクルを操作するための汎用機能。

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

表示オプションが true の場合、Xvfb (仮想フレームバッファ) がコンテナ内で開始され、スクリーンショットと入力アクション (クリック、タイプ、キー、スクロール) が使用可能になります。

Container_exec アクションのリスト:

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

input_type のタイプ:

| input_type | description | parameters |
|---|---|---|
| `click` | Coordinate click | x, y, button(left/right/middle) |
| `double_click` | Double click | x, y |
| `type` | Text input | text |
| `key` | Key transmission | key (e.g. "Enter", "Ctrl+C") |
| `scroll` | Scroll | x, y, delta |
| `drag` | Drag | from_x, from_y, to_x, to_y |

#### handler.py の戻り値

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

ウィジェット JSON は、widget.md で定義された統一形式に従います。 rumi_widgets Python ヘルパー ライブラリを使用することも、辞書として直接返すこともできます。

#### handler.py の使用例

**例 1: ファイルの読み取り (data_read のみ)**

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

**例 2: チャット メッセージの処理 (call_handler)**

```python
def run(params, context):
    context["call_handler"]("defaults.chat.delete_message", {
        "conversation_id": params["conversation_id"],
        "message_id": params["message_id"]
    })
    return {"result": "Message deleted"}
```

**例 3: ユーザーに確認ポップアップを表示する (emit_event + wait_event)**

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

**例 4: 別のエージェントにタスクをリクエストする (call_handler)**

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

**例 5: Docker コンテナ内での GUI 操作 (機能)**

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

**例 6: フローによる定期実行の登録 (execute_flow)**

```python
def run(params, context):
    context["execute_flow"]("user_scheduled_task", {
        "task": params["task"],
        "agent_id": params.get("agent_id", "general"),
        "schedule": params["cron"]
    })
    return {"result": f"Scheduled: {params['cron']}"}
```

**例 7: ナレッジを検索して結果を返す (call_handler + data_read)**

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

**例 8: 新しいツールの生成 (data_write)**

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

すべては次の汎用プリミティブで構成されます: call_handler、emit_event、wait_event、data_read、data_write、capability、execute_flow、および Emit_widget。新しいハンドラーまたはフローが追加された場合、ツールは同じプリミティブでそれらを呼び出すことができます。

### 3.8 機能/ディレクトリ (オプション)

ツールにホスト側の機能ハンドラーが付属している場合。

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

`scope`: `"public"`は、`capabilities_required`で他のツールも使用できます。 `"private"` はこのツール専用です。

ホスト側の handler.py はユーザーの明示的な承認 + ハッシュ レコード + 変更検出の対象となります。

---

## 4.defaults.json

すべてのツールに共通のグローバル設定。

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

## 5. 外部依存関係とパックの調整

### 5.1 ツールはパックを要求します

Permission.json の `pack_dependencies` により、ツールが外部パックをリクエストできるようになります。

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

ツールを実行する前に、executor.py は以下を確認し、アンインストールされたパックをインストールするようユーザーに提案します。

```
⚠️ ツール「browser_navigate」は以下の Pack が必要です:

  ✅ rumi-browser-runtime v1.2.0 (Rumi 検証済み)
     ブラウザ制御の Capability Handler を提供

[導入して続行] [キャンセル]
```

### 5.2 パックの依存関係の解決

パック自体は他のパックに依存することもできます (pack.json の `dependencies`)。

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

### 5.3 ダウンロード (git なし)

GitHub APIのzipballを使用します。 git コマンドは必要ありません。

```
GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
```

ダウンロード後、`path`で指定したディレクトリのみを解凍し、`user_data/packs/`に配置してください。認証が必要なプライベート リポジトリでは、`GITHUB_TOKEN` 環境変数を使用します。

### 5.4 マーケットプレイス レジストリ

`harupipipipi/rumi-marketplace` リポジトリ `registry.json`:

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

ステータス: `"verified"` は Rumi チームによって検証されました。 `"unverified"`は未検証です。 `"blacklisted"`は危険と判断されます。

### 5.5 .pack_meta.json

ダウンロードしたパック内に自動生成される管理ファイル。

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

### 5.6 実装フロー

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

### 5.7 機能検索の優先順位

executor.py がツールの `capabilities_required` を解決する順序:

1. システム統合 (`ecosystem/default/backend/capabilities/`)
2. 共有機能 (`user_data/shared/capabilities/`)
3. 付属ツール (`tools/xxx/capability/`)
4. パック提供 (`user_data/packs/xxx/capabilities/`)
5.`pack_dependencies`から自動取得→4に配置

---

## 6. 段階的な開示

### ステージ 1: カタログ (ツールの数 > stage_threshold の場合)

軽量ツール カタログを LLM のシステム プロンプトに挿入します。

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

各ツールから`name`、`summary`、`tags`、`tool.json`の`use_cases`のみを抽出します。

### ステージ 2: 詳細 (選択したツールまたはツールの数 ≤ stage_threshold)

完全なスキーマを LLM の `tools` パラメータに渡します。 `guide.json`の`usage_guide`と`tips`を説明に挿入します。

### ステージ 3: ランタイム

`conditions.json` → `handler_config` インジェクション → `handler.py` 実行の評価。

---

## 7. ウィジェットの統合

handler.py によって返される `widget` フィールドは、widget.md で定義された統合ウィジェット スキームに従います。すべてのドメイン (ツール、プロンプト、ai_client、チャット、エージェント) は、同じウィジェット形式で UI 表示を宣言します。

handler.py からウィジェットを送信するには 2 つの方法があります。

最終結果ウィジェットを戻り値の `widget` フィールドに含めます。これは、ツールの実行が終了した後に表示されます。

`context["emit_widget"]` を使用して、実行中にリアルタイムでウィジェットを送信します。進捗表示やストリーミング表示に使用します。

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

ウィジェットの種類、JSON 形式、テーマの統合のリストについては、widget.md を参照してください。 rumi_widgets Python ヘルパー ライブラリ (`ecosystem/defaults/lib/rumi_widgets/`) をインポートすることで、クラス ベースでウィジェットを構築できますが、これは辞書として直接返すのと同等です。

---

## 8. バックエンド処理

### 8.1 Executor.py フロー

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

### 8.2 Converter.py での 4 方向変換

1. **ツール定義 → LLM 形式**:tool.json + schema.json → OpenAI 関数 / Anthropic ツール形式
2. **LLM tool_calls → Rumi 統一フォーマット**: 各プロバイダーの tools_call フォーマットを統一
3. **実行結果 → LLM メッセージ形式**: result / llm_content → 各プロバイダのメッセージ形式
4. **prompt_based サポート**:tool_calls をサポートしないモデルのプロンプト埋め込み + 応答解析

`capabilities.json` の `tool_result_image_support` での画像サポート分岐: `true` (Anthropic) は、tool_result に画像を含めることができます。 `false` (OpenAI) は、次のユーザー メッセージとして画像を送信します。

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

### 8.4loader.pyの走査順序

1. `user_data/shared/tools/` (ユーザー管理)
2. `user_data/packs/*/tools/` (パック提供)
3. MCPサーバーからの動的取得

同じ名前のツールの場合は、共有が優先されます。

### 8.5 mcp_client.py

すべての MCP 機能と互換性があります。

| MCP Features | Implementation |
|----------|------|
| Tools (tools/list, tools/call) | Register as a tool, execution.type = "mcp" |
| Resources (resources/list, resources/read, resources/subscribe) | Injected into Flow context |
| Prompts (prompts/list, prompts/get) | Available as a template |
| Sampling (sampling/createMessage) | LLM call via ai_client |
| Roots (roots/list) | Notify workspace path |
| Elicitation (elicitation/create) | Contact user with emit_event |

mcp.json の設定例:

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

## 9. フローの統合

### 基本的なチャット + ツール

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

### エージェントチャット

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

### カスタム フロー (user_data)

ユーザーまたはパックは、`user_data/shared/flows/` にフローを追加します。ツールの handler.py から `context["execute_flow"]` で起動できます。 Flowのイベントトリガーを利用することで、user_inputが届いた際にナレッジ検索ツールを自動実行するなどのフックも実装できます。

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

## 10. 準備状況のチェック

`readiness/check.py`をツール内に配置することで、実行前に環境を検出することができます。

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

実行タイミング: パック承認時、アプリ起動時 (並列)、リソース使用直前 (キャッシュ優先)、ユーザーによる手動。キャッシュ TTL のデフォルトは 300 秒です。 readiness が False に設定されているリソースには UI 上で警告マークが表示されますが、ユーザーは意図的に使用することができます。
