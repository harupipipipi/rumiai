```markdown
# Tool Module

## 1. 設計思想

Tool モジュールは Rumi AI OS において LLM がユーザーの代わりに外部操作を行うための仕組みである。

設計原則:
- **データ駆動**: ツール定義は JSON/YAML ファイル。ロジックは handler.py。ディレクトリ追加だけでツールを拡張できる。
- **汎用プリミティブのみ**: handler.py に注入される context API は汎用プリミティブのみで構成される。チャット操作、エージェント起動、メモリ読み書き等のドメイン操作は全て汎用プリミティブの組み合わせで実現する。特定のドメインに特化した API は存在しない。
- **段階的開示**: ツール数が多い場合、LLM にはまずカタログ（名前・要約）だけ渡し、選択後に詳細スキーマを渡す。トークンを節約し選択精度を上げる。
- **最小権限**: handler.py が使える context API は permission.json の宣言に基づいて注入される。宣言していない API は使えない。
- **外部依存解決**: ツールが必要とする capability や Pack が未導入の場合、GitHub リポジトリから git なしで自動取得できる。

---

## 2. ディレクトリ構成

### ツール配置

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

Pack 提供のツールは `user_data/packs/*/tools/` に配置される。

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

### Pack 管理コード

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

### 3.1 tool.json（必須）

ツールのメタ情報。段階的開示の Stage 1 で LLM に渡される。

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

**execution.type の種類:**

| type | 説明 | 動作場所 |
|------|------|----------|
| `local` | handler.py を直接実行 | Docker 内 |
| `capability` | Capability Handler 経由 | ホスト側 |
| `mcp` | MCP サーバー経由 | 外部プロセス |
| `http` | HTTP リクエスト | llm_network 経由 |

### 3.2 schema.json（必須）

入出力の JSON Schema 定義。段階的開示の Stage 2 で LLM に渡される。

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

使い方の詳細。段階的開示の Stage 2 で LLM に description に注入される。

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

モデルの能力に応じた動作分岐。

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

**`pack_dependencies`**: このツールが必要とする外部 Pack。指定した Pack が未導入の場合、`repo` から自動取得を提案する。

**`capabilities_required`**: handler.py の context に注入される capability の宣言。ここに宣言した capability のみが context に注入される。

`llm_call` を使う場合は `llm_call_allowed: true` に設定し、制限を記述できる:

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

連携ツール・チェーンパターン・依存。

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

### 3.7 handler.py（必須）

ツールの実行ロジック。

#### context API

handler.py に注入される context は汎用プリミティブのみで構成される。特定のドメイン（チャット、エージェント等）に特化した API は存在しない。全てのドメイン操作は汎用プリミティブの組み合わせで実現する。

**常に注入される（宣言不要）:**

| context キー | 説明 |
|---|---|
| `context["call_handler"]` | 任意の handler を呼び出す。Grant で許可された権限の範囲内でのみ実行可能 |
| `context["emit_event"]` | イベントを発行する。handler、Flow、フロントエンドが受信可能 |
| `context["wait_event"]` | イベントを待つ。タイムアウト指定可能 |
| `context["emit_widget"]` | Widget JSON を UI に送出する |
| `context["cancel_check"]` | キャンセル確認 |
| `context["handler_config"]` | conditions.json の behavior_variants から注入された設定 |
| `context["session"]` | セッション情報（session_id、workspace 等） |

**permission.json の `capabilities_required` で宣言して注入されるもの:**

| capability_id | 説明 | context キー | リスク |
|---|---|---|---|
| `data_read` | user_data 配下のファイル読み取り | `context["data_read"](path) → str` | 低 |
| `data_write` | user_data 配下のファイル書き込み | `context["data_write"](path, content)` | 中 |
| `execute_flow` | Flow を起動する | `context["execute_flow"](flow_id, input) → FlowResult` | 中 |
| `shell_exec` | シェルコマンド実行 | `context["capability"]("shell_exec", {...})` | 高 |
| `browser_control` | ブラウザ操作 | `context["capability"]("browser_control", {...})` | 高 |
| `container_exec` | Docker コンテナの起動・操作・破棄 | `context["capability"]("container_exec", {...})` | 高 |
| `app_control` | ホストアプリ操作 | `context["capability"]("app_control", {...})` | 高 |
| `http_request` | 外部 HTTP 通信 | `context["capability"]("http_request", {...})` | 中 |
| `llm_call` | ツール内 LLM 呼び出し | `context["capability"]("llm_call", {...})` | 中 |
| `session_state` | セッション状態読み書き | `context["capability"]("session_state", {...})` | 低 |

#### call_handler

任意の handler を呼び出す汎用ゲートウェイ。defaults や Pack が登録した全ての handler を呼べる。handler は README.md の handler 体系に定義されている。

```python
result = context["call_handler"](
    "defaults.chat.send",
    {
        "conversation_id": "conv-1",
        "content": "hello"
    }
)
```

call_handler は以下の順序で処理する。呼び出し元 tool の permission.json に宣言された権限を確認する。呼び出し先 handler が要求する権限が呼び出し元の権限に含まれるか検証する。含まれなければ PermissionError で拒否する。含まれていれば handler を実行し結果を返す。

これにより tool は自分が持つ権限の範囲内でシステム上の任意の handler を呼び出せる。チャット操作、エージェント起動、メモリ読み書き、プロンプトレンダリング、全てが call_handler 経由で行える。

#### emit_event / wait_event

イベントはシステム全体の汎用通信メカニズムである。

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

イベントの受信者は handler、Flow のイベントトリガー、フロントエンドの Asset のいずれでもよい。emit_event はイベントバスに発行するだけであり誰が受け取るかは発行側の関知するところではない。

#### data_read / data_write

user_data 配下の任意のファイルを読み書きする汎用ファイル I/O。

```python
content = context["data_read"]("chat/conversations/conv-1.json")
context["data_write"]("knowledge/sources/notes.md", content)
```

パスは user_data/ からの相対パス。user_data の外へのアクセスは拒否される。

#### execute_flow

任意の Flow を起動する。Flow Engine 経由で実行される。

```python
result = context["execute_flow"](
    "my_custom_flow",
    {"query": "search this"}
)
```

#### container_exec capability

Docker コンテナのライフサイクルを操作する汎用 capability。

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

display オプションが true の場合、コンテナ内に Xvfb（仮想フレームバッファ）が起動し、screenshot アクションと input アクション（click, type, key, scroll）が使用可能になる。

container_exec のアクション一覧:

| action | 説明 | 必須パラメータ |
|---|---|---|
| `create` | コンテナ作成・起動 | image, options |
| `exec` | コンテナ内コマンド実行 | container_id, command |
| `screenshot` | ディスプレイのスクリーンショット取得 | container_id |
| `input` | ディスプレイへの入力 | container_id, input_type, (x, y / text / key) |
| `upload` | ファイルをコンテナに送る | container_id, host_path, container_path |
| `download` | ファイルをコンテナから取得 | container_id, container_path |
| `destroy` | コンテナ破棄 | container_id |
| `list` | 実行中コンテナ一覧 | なし |

input_type の種類:

| input_type | 説明 | パラメータ |
|---|---|---|
| `click` | 座標クリック | x, y, button(left/right/middle) |
| `double_click` | ダブルクリック | x, y |
| `type` | テキスト入力 | text |
| `key` | キー送信 | key (例: "Enter", "Ctrl+C") |
| `scroll` | スクロール | x, y, delta |
| `drag` | ドラッグ | from_x, from_y, to_x, to_y |

#### handler.py の返り値

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

Widget JSON は widget.md で定義された統一形式に従う。rumi_widgets Python ヘルパーライブラリを使用してもよいし、直接 dict で返してもよい。

#### handler.py 使用例

**例1: ファイル読み取り（data_read のみ）**

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

**例2: チャットのメッセージを操作する（call_handler）**

```python
def run(params, context):
    context["call_handler"]("defaults.chat.delete_message", {
        "conversation_id": params["conversation_id"],
        "message_id": params["message_id"]
    })
    return {"result": "Message deleted"}
```

**例3: ユーザーに確認ポップアップを出す（emit_event + wait_event）**

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

**例4: 別のエージェントにタスクを依頼する（call_handler）**

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

**例5: Docker コンテナ内で GUI 操作する（capability）**

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

**例6: 定期実行を Flow 経由で登録する（execute_flow）**

```python
def run(params, context):
    context["execute_flow"]("user_scheduled_task", {
        "task": params["task"],
        "agent_id": params.get("agent_id", "general"),
        "schedule": params["cron"]
    })
    return {"result": f"Scheduled: {params['cron']}"}
```

**例7: ナレッジを検索して結果を返す（call_handler + data_read）**

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

**例8: 新しいツールを生成する（data_write）**

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

全てが call_handler、emit_event、wait_event、data_read、data_write、capability、execute_flow、emit_widget の汎用プリミティブで構成されている。新しい handler や Flow が追加されれば、tool はそれらを同じプリミティブで呼び出せる。

### 3.8 capability/ ディレクトリ（任意）

ツールがホスト側 Capability Handler を同梱する場合。

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

`scope`: `"public"` は他のツールも `capabilities_required` で使える。`"private"` はこのツール専用。

ホスト側 handler.py はユーザーの明示承認 + ハッシュ記録 + 改変検知の対象となる。

---

## 4. defaults.json

全ツール共通のグローバル設定。

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
      "path": "tobkiri_runtime/ecosystem/default/share/tools"
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

| キー | 説明 |
|------|------|
| `stage_threshold` | この数以上のツールがある場合、段階的開示を使う |
| `approval.global_approval_mode` | `per_call` / `per_session` / `auto` |
| `approval.auto_approve_verified_packs` | marketplace 検証済み Pack のツールを自動承認するか |
| `rate_limit.max_total_calls_per_minute` | 全ツール合計の1分あたり呼び出し上限 |
| `cache.ttl_seconds` | idempotent ツールの結果キャッシュ時間 |
| `shell.*` | 永続シェルセッションの設定 |
| `container.*` | Docker コンテナの設定 |
| `llm_call.*` | ツール内 LLM 呼び出しのデフォルト制限 |
| `agent.*` | サブエージェント（Task ツール）の制限 |
| `display.max_images_in_context` | LLM に渡す画像の最大数 |
| `display.max_output_chars` | ツール出力の切り詰め閾値 |
| `disabled_tools` | 無効化するツール ID のリスト |
| `sync.*` | ツール定義の同期元 GitHub リポジトリ |
| `pack_install.*` | Pack 導入関連の設定 |

---

## 5. 外部依存とPack連携

### 5.1 ツールが Pack を要求する

permission.json の `pack_dependencies` で、ツールが外部 Pack を要求できる。

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

executor.py がツール実行前にチェックし、未導入の Pack があればユーザーに導入を提案する:

```
⚠️ ツール「browser_navigate」は以下の Pack が必要です:

  ✅ rumi-browser-runtime v1.2.0 (Rumi 検証済み)
     ブラウザ制御の Capability Handler を提供

[導入して続行] [キャンセル]
```

### 5.2 Pack の依存解決

Pack 自体も他の Pack に依存できる（pack.json の `dependencies`）。

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

### 5.3 ダウンロード（git なし）

GitHub API の zipball を使用。git コマンド不要。

```
GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
```

ダウンロード後、`path` で指定されたディレクトリだけ解凍・抽出して `user_data/packs/` に配置する。認証が必要な private リポジトリは `GITHUB_TOKEN` 環境変数を使用。

### 5.4 Marketplace レジストリ

`harupipipipi/rumi-marketplace` リポジトリの `registry.json`:

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

ステータス: `"verified"` は Rumi チームが検証済み。`"unverified"` は未検証。`"blacklisted"` は危険と判定。

### 5.5 .pack_meta.json

ダウンロードした Pack に自動生成される管理ファイル。

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

### 5.6 導入フロー

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

### 5.7 capability の探索優先順位

executor.py がツールの `capabilities_required` を解決する順序:

1. システム組み込み（`ecosystem/default/backend/capabilities/`）
2. 共有 capability（`user_data/shared/capabilities/`）
3. ツール同梱（`tools/xxx/capability/`）
4. Pack 提供（`user_data/packs/xxx/capabilities/`）
5. `pack_dependencies` から自動取得 → 4 に配置

---

## 6. 段階的開示

### Stage 1: カタログ（ツール数 > stage_threshold の場合）

LLM の system prompt に軽量なツールカタログを注入:

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

各ツールから `tool.json` の `name`, `summary`, `tags`, `use_cases` のみを抽出。

### Stage 2: 詳細（選択されたツール or ツール数 ≤ stage_threshold）

LLM の `tools` パラメータに完全なスキーマを渡す。`guide.json` の `usage_guide` と `tips` を description に注入する。

### Stage 3: 実行時

`conditions.json` の評価 → `handler_config` 注入 → `handler.py` 実行。

---

## 7. Widget 統合

handler.py が返す `widget` フィールドは widget.md で定義された統一 Widget 体系に従う。全てのドメイン（tool、prompt、ai_client、chat、agent）が同じ Widget 形式で UI 表示を宣言する。

handler.py からの Widget 送出方法は 2 つある。

返り値の `widget` フィールドに最終結果の Widget を含める。これはツール実行完了後に表示される。

`context["emit_widget"]` で実行中にリアルタイムで Widget を送出する。進捗表示やストリーミング表示に使う。

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

Widget の型一覧、JSON 形式、テーマ連携については widget.md を参照。rumi_widgets Python ヘルパーライブラリ（`ecosystem/defaults/lib/rumi_widgets/`）を import すればクラスベースで Widget を構築できるが、直接 dict で返しても等価である。

---

## 8. バックエンド処理

### 8.1 executor.py のフロー

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

### 8.2 converter.py の4方向変換

1. **ツール定義 → LLM 形式**: tool.json + schema.json → OpenAI function / Anthropic tool 形式
2. **LLM tool_calls → Rumi 統一形式**: プロバイダーごとの tool_call 形式を統一
3. **実行結果 → LLM メッセージ形式**: result / llm_content → プロバイダーごとのメッセージ形式
4. **prompt_based 対応**: tool_calls 非対応モデル用にプロンプト埋め込み + 応答パース

画像対応は `capabilities.json` の `tool_result_image_support` で分岐: `true`（Anthropic）は tool_result 内に画像を含められる。`false`（OpenAI）は次の user メッセージとして画像を送信。

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

### 8.4 loader.py の走査順序

1. `user_data/shared/tools/`（ユーザー管理）
2. `user_data/packs/*/tools/`（Pack 提供）
3. MCP サーバーから動的取得

同名ツールは shared が優先。

### 8.5 mcp_client.py

MCP の全機能に対応:

| MCP 機能 | 実装 |
|----------|------|
| Tools (tools/list, tools/call) | ツールとして登録、execution.type = "mcp" |
| Resources (resources/list, resources/read, resources/subscribe) | Flow の context に注入 |
| Prompts (prompts/list, prompts/get) | テンプレートとして利用可能に |
| Sampling (sampling/createMessage) | ai_client 経由で LLM 呼び出し |
| Roots (roots/list) | workspace パスを通知 |
| Elicitation (elicitation/create) | emit_event でユーザーに問い合わせ |

mcp.json 設定例:

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

MCP 設定の登録はサーバーを起動しない。接続と再接続は、共有承認キューで
構成と影響を確認したユーザーによる Tobkiri Launcher の権威ある決定を毎回要求する。
`auto_connect` / `autostart` および `approval_mode: "auto"` はサポートされず、
指定された接続要求は fail closed で拒否される。

---

## 9. Flow 連携

### 基本チャット + ツール

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

### カスタムフロー（user_data）

ユーザーやPackが `user_data/shared/flows/` にフローを追加する。ツールの handler.py から `context["execute_flow"]` で起動可能。Flow のイベントトリガーを使えば、user_input 到着時にナレッジ検索ツールを自動実行する等のフックも実現できる。

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

ツールに `readiness/check.py` を配置すると、実行前に環境検知を行える。

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

実行タイミング: Pack 承認時、アプリ起動時（並列）、リソース使用直前（キャッシュ優先）、ユーザー手動。キャッシュ TTL はデフォルト 300 秒。readiness が False のリソースは UI 上で警告マークが付くが、ユーザーが意図的に使うことは可能。
```
