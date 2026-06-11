<!-- docs-i18n-links:start -->
[EN](../../tool.md) | [JP](../ja/tool.md) | [KR](./tool.md) | [CN](../zh-cn/tool.md)
<!-- docs-i18n-links:end -->

# 도구 모듈

## 1. 디자인 철학

도구 모듈은 LLM이 Rumi AI OS에서 사용자를 대신하여 외부 작업을 수행하는 메커니즘입니다.

디자인 원칙:
- **데이터 기반**: 도구 정의는 JSON/YAML 파일입니다. 논리는 handler.py입니다. 간단히 디렉토리를 추가하여 도구를 확장할 수 있습니다.
- **범용 프리미티브만**: handler.py에 삽입된 컨텍스트 API는 범용 프리미티브로만 구성됩니다. 채팅 작업, 에이전트 활성화, 메모리 읽기 및 쓰기 등 모든 도메인 작업은 범용 기본 요소의 조합으로 구현됩니다. 도메인별 API는 없습니다.
- **단계별 공개**: 도구가 많은 경우 먼저 카탈로그(이름/요약)만 LLM에 전달한 다음 선택 후 세부 스키마를 전달합니다. 토큰을 저장하고 선택 정확도를 높이세요.
- **최소 권한**: handler.py가 사용할 수 있는 컨텍스트 API는 허가.json의 선언을 기반으로 주입됩니다. 선언되지 않은 API는 사용할 수 없습니다.
- **외부 종속성 해결**: 도구에 필요한 기능이나 팩이 설치되지 않은 경우 git을 사용하지 않고도 GitHub 저장소에서 자동으로 얻을 수 있습니다.

---

## 2. 디렉토리 구조

### 도구 배치

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

팩에서 제공하는 도구는 `user_data/packs/*/tools/`에 있습니다.

### 백엔드 코드

```
ecosystem/default/backend/blocks/tool/
├── loader.py                  # ツール定義の走査・マージ・キャッシュ
├── converter.py               # 4方向変換（定義↔LLM, 結果↔LLM）
├── executor.py                # 実行エンジン
├── permission_checker.py      # 権限検証
├── session_manager.py         # シェルセッション・状態管理
└── mcp_client.py              # MCP サーバー接続
```

### 팩 관리 코드

```
ecosystem/default/backend/blocks/pack/
├── downloader.py              # GitHub API で zipball ダウンロード
├── resolver.py                # 依存解決・バージョンマッチング
├── installer.py               # 配置・ハッシュ記録
├── verifier.py                # marketplace レジストリ照合
└── updater.py                 # アップデートチェック
```

---

## 3. 도구 정의 파일

### 3.1 tool.json (필수)

도구 메타 정보. 단계적 공개의 1단계에서 LLM에 전달되었습니다.

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

**execution.type 유형:**

| type | Description | Operating location |
|------|------|----------|
| `local` | Run handler.py directly | In Docker |
| `capability` | Via Capability Handler | Host side |
| `mcp` | Via MCP server | External process |
| `http` | HTTP request | via llm_network |

### 3.2 스키마.json(필수)

입력 및 출력에 대한 JSON 스키마 정의입니다. 단계적 공개의 2단계에서 LLM으로 전달되었습니다.

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

### 3.3 가이드.json

사용방법에 대한 자세한 내용입니다. 설명은 점진적 공개의 2단계에서 LLM에 주입됩니다.

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

### 3.4 조건.json

모델 기능에 따른 동작 분기.

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

### 3.5 허가.json

권한/승인/제한.

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

**`pack_dependencies`**: 이 도구에는 외부 팩이 필요합니다. 지정된 팩이 설치되지 않은 경우 `repo`.**`capabilities_required`**에서 자동 획득이 제안됩니다: handler.py의 컨텍스트에 주입된 기능 선언. 여기에 선언된 기능만 컨텍스트에 주입됩니다.

`llm_call`을 사용할 때 이를 `llm_call_allowed: true`으로 설정하고 제한 사항을 작성할 수 있습니다.

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

### 3.6 관계.json

협력 도구, 체인 패턴 및 종속성.

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

### 3.7 handler.py (필수)

도구 실행 논리.

#### 컨텍스트 API

handler.py에 주입된 컨텍스트는 범용 프리미티브로만 구성됩니다. 특정 도메인(채팅, 상담원 등)과 관련된 API는 없습니다. 모든 도메인 작업은 범용 기본 요소의 조합으로 구현됩니다.

**항상 주입됨(선언 필요 없음):**

| context key | description |
|---|---|
| `context["call_handler"]` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `context["emit_event"]` | Publish an event. handler, flow, front end can receive |
| `context["wait_event"]` | Wait for an event. Timeout can be specified |
| `context["emit_widget"]` | Send Widget JSON to the UI |
| `context["cancel_check"]` | Cancellation confirmation |
| `context["handler_config"]` | Settings injected from behavior_variants in conditions.json |
| `context["session"]` | Session information (session_id, workspace, etc.) |

**permission.json의 `capabilities_required`에 선언 및 삽입됨:**

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

#### call_handler

모든 핸들러를 호출하는 일반 게이트웨이입니다. 기본적으로 등록된 모든 핸들러와 Pack을 호출할 수 있습니다. handler는 README.md의 핸들러 시스템에 정의되어 있습니다.

```python
result = context["call_handler"](
    "defaults.chat.send",
    {
        "conversation_id": "conv-1",
        "content": "hello"
    }
)
```

call_handler는 다음 순서로 처리합니다. 호출 도구의Permission.json에 선언된 권한을 확인하세요. 호출자의 권한에 호출된 핸들러가 요청한 권한이 포함되어 있는지 확인하십시오. 포함되지 않은 경우 PermissionError와 함께 거부됩니다. 포함되어 있으면 핸들러를 실행하고 결과를 반환합니다.

이를 통해 도구는 해당 권한 내에서 시스템의 모든 핸들러를 호출할 수 있습니다. 채팅 작업, 에이전트 활성화, 메모리 읽기/쓰기, 프롬프트 렌더링 등은 모두 call_handler를 통해 수행할 수 있습니다.

#### Emit_event / wait_event

이벤트는 시스템 전반에 걸친 범용 통신 메커니즘입니다.

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

이벤트 수신자는 핸들러, Flow 이벤트 트리거 또는 프런트엔드 자산일 수 있습니다. Emit_event는 이벤트 버스에만 이를 발행하며, 발행자는 이를 누가 수신하는지에 관심이 없습니다.

#### 데이터_읽기 / 데이터_쓰기

user_data 아래의 모든 파일을 읽고 쓰기 위한 범용 파일 I/O입니다.

```python
content = context["data_read"]("chat/conversations/conv-1.json")
context["data_write"]("knowledge/sources/notes.md", content)
```

경로는 user_data/를 기준으로 합니다. user_data 외부의 액세스는 거부됩니다.

#### 실행_흐름

흐름을 시작합니다. Flow Engine을 통해 실행됩니다.

```python
result = context["execute_flow"](
    "my_custom_flow",
    {"query": "search this"}
)
```

#### 컨테이너_실행 기능

Docker 컨테이너 수명주기를 조작하는 범용 기능입니다.

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

표시 옵션이 true이면 컨테이너에서 Xvfb(가상 프레임 버퍼)가 시작되고 스크린샷 및 입력 동작(클릭, 타이핑, 키, 스크롤)이 가능합니다.

Container_exec 작업 목록:

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

input_type 유형:

| input_type | description | parameters |
|---|---|---|
| `click` | Coordinate click | x, y, button(left/right/middle) |
| `double_click` | Double click | x, y |
| `type` | Text input | text |
| `key` | Key transmission | key (e.g. "Enter", "Ctrl+C") |
| `scroll` | Scroll | x, y, delta |
| `drag` | Drag | from_x, from_y, to_x, to_y |

#### handler.py의 반환 값

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

위젯 JSON은 widget.md에 정의된 통일된 형식을 따릅니다. rumi_widgets Python 도우미 라이브러리를 사용하거나 사전으로 직접 반환할 수 있습니다.

#### handler.py 사용 예

**예제 1: 파일 읽기(data_read 전용)**

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

**예 2: 채팅 메시지 처리(call_handler)**

```python
def run(params, context):
    context["call_handler"]("defaults.chat.delete_message", {
        "conversation_id": params["conversation_id"],
        "message_id": params["message_id"]
    })
    return {"result": "Message deleted"}
```

**예 3: 사용자에게 확인 팝업 표시(emit_event + wait_event)**

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

**예시 4: 다른 에이전트에게 작업 요청(call_handler)**

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

**예 5: Docker 컨테이너 내 GUI 작업(기능)**

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

**예 6: Flow를 통한 주기적 실행 등록(execute_flow)**

```python
def run(params, context):
    context["execute_flow"]("user_scheduled_task", {
        "task": params["task"],
        "agent_id": params.get("agent_id", "general"),
        "schedule": params["cron"]
    })
    return {"result": f"Scheduled: {params['cron']}"}
```

**예 7: 지식 검색 및 결과 반환(call_handler + data_read)**

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

**예 8: 새 도구 생성(data_write)**

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

모든 것은 call_handler, Emit_event, wait_event, data_read, data_write, Capability, Execution_flow 및 Emit_widget과 같은 일반 프리미티브로 구성됩니다. 새로운 핸들러나 흐름이 추가되면 도구는 동일한 기본 요소에서 이를 호출할 수 있습니다.

### 3.8 기능/디렉토리(선택 사항)

도구가 호스트 측 기능 처리기와 함께 제공되는 경우.

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

`scope`: `"public"`은 `capabilities_required`와 함께 다른 도구를 사용할 수도 있습니다. `"private"`은 이 도구에만 적용됩니다.

호스트 측 handler.py는 사용자 명시적 승인 + 해시 레코드 + 수정 감지의 대상입니다.

---

## 4. defaults.json

모든 도구에 공통되는 전역 설정입니다.

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

## 5. 외부 종속성과 팩 조정

### 5.1 도구에서 팩 요청

Permission.json의 `pack_dependencies`을 사용하면 도구에서 외부 팩을 요청할 수 있습니다.

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

도구를 실행하기 전에 executor.py는 제거된 팩을 설치하도록 사용자에게 확인하고 제안합니다.

```
⚠️ ツール「browser_navigate」は以下の Pack が必要です:

  ✅ rumi-browser-runtime v1.2.0 (Rumi 検証済み)
     ブラウザ制御の Capability Handler を提供

[導入して続行] [キャンセル]
```

### 5.2 팩 종속성 해결

팩 자체도 다른 팩에 종속될 수 있습니다(pack.json의 `dependencies`).

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

### 5.3 다운로드(git 없이)

GitHub API의 zipball을 사용합니다. git 명령이 필요하지 않습니다.

```
GET https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
```

다운로드 후 `path`에 지정된 디렉토리만 압축을 풀고 추출하여 `user_data/packs/`에 넣습니다. 인증이 필요한 개인 저장소는 `GITHUB_TOKEN` 환경 변수를 사용합니다.

### 5.4 마켓플레이스 레지스트리

`harupipipipi/rumi-marketplace` 저장소 `registry.json`:

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

상태: `"verified"`이 루미 팀에 의해 확인되었습니다. `"unverified"`은 확인되지 않았습니다. `"blacklisted"`은 위험하다고 판단됩니다.

### 5.5 .pack_meta.json

다운로드한 Pack에 자동으로 생성되는 관리 파일입니다.

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

### 5.6 구현 흐름

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

### 5.7 능력 검색 우선순위

executor.py가 도구에 대한 `capabilities_required`을 해결하는 순서는 다음과 같습니다.

1. 시스템 통합(`ecosystem/default/backend/capabilities/`)
2. 공유 기능(`user_data/shared/capabilities/`)
3. 도구 포함(`tools/xxx/capability/`)
4. 팩 제공(`user_data/packs/xxx/capabilities/`)
5. `pack_dependencies`에서 자동 획득 → 4에 배치

---

## 6. 점진적 공개

### 1단계: 카탈로그(도구 개수 > stage_threshold인 경우)

LLM의 시스템 프롬프트에 경량 도구 카탈로그를 삽입합니다.

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

각 도구에서 `tool.json` 중 `name`, `summary`, `tags`, `use_cases`만 추출합니다.

### 2단계: 세부정보(선택한 도구 또는 도구 수 ≤ stage_threshold)

전체 스키마를 LLM의 `tools` 매개변수에 전달합니다. 설명에 `guide.json`의 `usage_guide` 및 `tips`를 삽입합니다.

### 3단계: 런타임

`conditions.json` → `handler_config` 주입 → `handler.py` 실행 평가.

---

## 7. 위젯 통합

handler.py에서 반환된 `widget` 필드는 widget.md에 정의된 통합 위젯 구성표를 따릅니다. 모든 도메인(tool, 프롬프트, ai_client, chat, 에이전트)은 동일한 위젯 형식으로 UI 표시를 선언합니다.

handler.py에서 위젯을 보내는 방법에는 두 가지가 있습니다.

반환 값의 `widget` 필드에 최종 결과 위젯을 포함합니다. 이는 도구 실행이 완료된 후에 표시됩니다.

`context["emit_widget"]`을 사용하여 실행 중에 실시간으로 위젯을 보냅니다. 진행률 표시 및 스트리밍 표시에 사용됩니다.

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

위젯 유형, JSON 형식 및 테마 통합 목록은 widget.md를 참조하세요. rumi_widgets Python 도우미 라이브러리(`ecosystem/defaults/lib/rumi_widgets/`)를 가져와 클래스 기반으로 위젯을 구축할 수 있지만 이를 dict로 직접 반환하는 것과 동일합니다.

---

## 8. 백엔드 처리

### 8.1 Executor.py 흐름

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

### 8.2 Converter.py의 4방향 변환

1. **도구 정의 → LLM 형식**: tool.json +schema.json → OpenAI 함수 / Anthropic 도구 형식
2. **LLM tool_calls → Rumi 통합 형식**: 각 제공자에 대한 tool_call 형식 통합
3. **실행 결과 → LLM 메시지 형식**: 결과 / llm_content → 공급자별 메시지 형식
4. **prompt_based 지원**: tool_calls를 지원하지 않는 모델에 대한 프롬프트 임베딩 + 응답 구문 분석

`capabilities.json`의 `tool_result_image_support`에 있는 이미지 지원 분기: `true`(인류)는 tool_result에 이미지를 포함할 수 있습니다. `false`(OpenAI)은 다음과 같은 사용자 메시지로 이미지를 보냅니다.

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

### 8.4 loader.py 순회 순서

1. `user_data/shared/tools/` (이용자 관리)
2. `user_data/packs/*/tools/`(팩 제공)
3. MCP 서버에서 동적 획득

동일한 이름을 가진 도구의 경우 공유가 우선합니다.

### 8.5 mcp_client.py

모든 MCP 기능과 호환:

| MCP Features | Implementation |
|----------|------|
| Tools (tools/list, tools/call) | Register as a tool, execution.type = "mcp" |
| Resources (resources/list, resources/read, resources/subscribe) | Injected into Flow context |
| Prompts (prompts/list, prompts/get) | Available as a template |
| Sampling (sampling/createMessage) | LLM call via ai_client |
| Roots (roots/list) | Notify workspace path |
| Elicitation (elicitation/create) | Contact user with emit_event |

mcp.json 구성 예:

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

## 9. 흐름 통합

### 기본 채팅 + 도구

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

### 상담원 채팅

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

### 사용자 정의 흐름(user_data)

사용자 또는 팩은 `user_data/shared/flows/`에 흐름을 추가합니다. `context["execute_flow"]`을 사용하여 도구의 handler.py에서 시작할 수 있습니다. Flow의 이벤트 트리거를 사용하면 user_input이 도착할 때 지식 검색 도구를 자동으로 실행하는 등의 후크를 구현할 수도 있습니다.

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

## 10. 준비 상태 확인

도구에 `readiness/check.py`을 배치하면 실행 전에 환경을 감지할 수 있습니다.

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

실행 시점: 팩 승인 시, 앱 시작 시(병렬), 리소스 사용 직전(캐시 우선순위), 사용자가 수동으로 수행합니다. 캐시 TTL의 기본값은 300초입니다. 준비 상태가 False로 설정된 리소스는 UI에 경고 표시가 표시되지만 사용자가 의도적으로 사용할 수 있습니다.
