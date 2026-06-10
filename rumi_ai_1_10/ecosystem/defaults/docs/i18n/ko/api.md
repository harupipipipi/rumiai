<!-- docs-i18n-links:start -->
[EN](../../api.md) | [JP](../ja/api.md) | [KR](./api.md) | [CN](../zh-cn/api.md)
<!-- docs-i18n-links:end -->

# api.md — Rumi AI OS API 및 전송 설계 문서

## 1. 개요

기본값은 외부로부터의 통신을 허용하는 "메커니즘"을 제공합니다. 특정 엔드포인트(채팅, 모델 목록 등)는 Flow의 API 트리거에 의해 등록됩니다. 기본값은 라우팅, 인증, 스트리밍 및 오류 형식의 기본만 정의하며 수행할 수 있는 작업은 user_data 측의 흐름 정의에 따라 결정됩니다.

Tauri 프런트엔드, CLI, 외부 스크립트, 웹훅은 모두 동일한 흐름에 도달합니다. 유일한 차이점은 전송(메시지가 전달되는 방식)입니다.


## 2. 디자인 철학

**전송 독립적**: 모든 통신은 궁극적으로 `FlowEngine.execute(flow_id, trigger_input)`에 대한 호출로 이어집니다. HTTP, stdin/stdout 또는 UDS를 통해 Flow에 도달하는 Trigger_input의 형식은 동일합니다.

**엔드포인트는 흐름입니다**: HTTP의 `/v1/chat/completions` 및 CLI의 `rumi chat`는 모두 동일한 `default.chat` 흐름을 시작합니다. 엔드포인트 추가는 흐름 정의에 추가되며 코드 변경을 포함하지 않습니다.

**인증은 전송 계층에서 수행됩니다**: HTTP용 API 키, stdio용 상위 프로세스 신뢰, UDS용 소켓 권한. Flow 레이어는 인증된 요청만 허용합니다.

**스트리밍은 전송에 의해 흡수됩니다**: 흐름은 `ctx.emit()`에서만 이벤트를 발행합니다. HTTP 전송은 SSE로 변환되고, stdio 전송은 JSON 라인으로 변환되며, Tauri 전송은 IPC 채널로 변환됩니다. Flow는 어떤 전송 수단으로 배달될지 모릅니다.


## 3. 아키텍처

```
外部            transport 層               Flow Engine
───────────    ───────────────────        ─────────────
HTTP Client ─→ http transport ─┐
                               ├──→ router ──→ FlowEngine.execute()
CLI         ─→ stdio transport ┤                    ↓
                               │              Flow handler.py
Tauri       ─→ stdin/stdout ───┤                    ↓
                               │              ctx.emit() ──→ transport が配信
UDS Client  ─→ uds transport ──┘
```

전송 계층은 기본 처리기로 구현됩니다.

| 핸들러 | 운송 | 권한 |
|---|---|---|
| §루미§0§ | HTTP 서버 | §루미§1§, §루미§2§ |
| §루미§0§ | 표준 입력/출력 | §루미§1§ |
| §루미§0§ | 유닉스 도메인 소켓 | §루미§1§, §루미§2§ |

각 전송 핸들러는 부여된 권한으로만 작동하며 전체 커널 개체에 액세스하지 않습니다(io.http.server 문제 방지).


## 4. 일반적인 메시지 형식

모든 전송에 공통되는 JSON 형식입니다. Transport는 이 형식을 그대로 전달하거나 자체 프로토콜로 변환합니다.

### 4.1 요청

```json
{
  "id": "req_01JXYZ",
  "flow_id": "default.chat",
  "input": {
    "model": "anthropic/claude-sonnet-4",
    "messages": [
      {"role": "user", "content": "hello"}
    ],
    "stream": true
  },
  "config": {}
}
```

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| 아이디 | 문자열 | 선택사항 | 요청 식별자. 생략시 자동생성 |
| 흐름_ID | 문자열 | 필수 | 시작할 흐름의 ID |
| 입력 | 개체 | 필수 | 흐름 Trigger_input |
| 구성 | 개체 | 선택사항 | Flow에 대한 flow_config 재정의 |

### 4.2 응답(비스트리밍)

```json
{
  "id": "req_01JXYZ",
  "status": "completed",
  "output": {
    "content": "Hello! How can I help you?",
    "model": "claude-sonnet-4-20250514",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 8,
      "total_tokens": 20
    },
    "finish_reason": "stop"
  },
  "metadata": {
    "flow_id": "default.chat",
    "duration_ms": 1200
  }
}
```

| 필드 | 유형 | 설명 |
|---|---|---|
| 아이디 | 문자열 | 요청 식별자 |
| 상태 | 문자열 | §루미§0§, §루미§1§, §루미§2§, §루미§3§ |
| 출력 | 개체 | 흐름 출력(FlowResult.output) |
| 메타데이터 | 개체 | 실행 메타데이터 |

### 4.3 응답(스트리밍)

스트리밍하는 동안 전송에 따라 여러 이벤트가 배포됩니다. 각 이벤트의 형식은 동일합니다.

```json
{"event": "stream.start", "id": "req_01JXYZ", "data": {}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "Hello"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "!"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_start", "id": "tc_01", "name": "file_read"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_delta", "arguments_chunk": "{\"path\":"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_end", "id": "tc_01"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "thinking_delta", "content": "Let me think..."}}
{"event": "stream.end", "id": "req_01JXYZ", "data": {"status": "completed", "output": {...}, "metadata": {...}}}
```

stream.delta의 `data.type`은 ai_client.md 섹션 11.3의 정규화된 이벤트 목록과 동일합니다. 전송 계층은 이 이벤트 시퀀스를 프로토콜별 형식으로 변환합니다.

### 4.4 오류

```json
{
  "id": "req_01JXYZ",
  "status": "error",
  "error": {
    "type": "flow_not_found",
    "message": "Flow 'nonexistent' is not registered",
    "code": "FLOW_NOT_FOUND",
    "details": {}
  }
}
```

오류 코드 시스템.

| 코드 | 설명 |
|---|---|
| §루미§0§ | 인증 필요 |
| §루미§0§ | API 키가 잘못되었습니다 |
| §루미§0§ | 지정된 flow_id가 존재하지 않습니다 |
| §루미§0§ | Flow 실행 중 오류 |
| §루미§0§ | 흐름 시간이 초과되었습니다 |
| §루미§0§ | 사용자 또는 시스템에 의해 취소됨 |
| §루미§0§ | 잘못된 입력 형식 |
| §루미§0§ | 권한이 부족함 |
| §루미§0§ | 비율 제한 |
| §루미§0§ | 내부 오류 |


## 5. HTTP 전송

### 5.1 시작

`defaults.transport.http` 핸들러는 HTTP 서버를 시작합니다. 설정은 user_data에서 수행됩니다.

```json
// user_data/config/transport.json
{
  "http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 3000,
    "cors": {
      "enabled": false,
      "origins": []
    }
  }
}
```

### 5.2 인증

HTTP 전송은 각 요청에 대해 인증을 수행합니다.

```
Authorization: Bearer rumi_xxxxxxxxxxxx
```

API 키는 `user_data/secrets/api_keys.json`에서 관리됩니다.

```json
{
  "keys": [
    {
      "id": "key_01",
      "key_hash": "sha256:abc...",
      "name": "My API Key",
      "created_at": "2026-02-14T10:00:00Z",
      "permissions": ["*"],
      "rate_limit": {
        "requests_per_minute": 60
      }
    }
  ]
}
```

`permissions`은 흐름 수준 권한입니다. `["*"]`은 모든 흐름에 접근할 수 있습니다. `["default.chat", "default.model_list"]`와 같이 제한될 수 있습니다.

### 5.3 라우팅

HTTP 끝점에서 flow_id로의 매핑은 `user_data/config/routes.json`에 정의되어 있습니다.

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools"
      },
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "description": "モデル一覧"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    }
  ]
}
```

`input_mapping`은 HTTP 요청에서 일반 메시지 형식 `input`으로 매핑되는 필드입니다. `body.model`는 요청 본문의 `model` 필드를 의미합니다. `"*": "body"`는 전체 본문을 입력으로 만듭니다. `{flow_id}`는 경로 매개변수입니다.

Routes.json을 편집하여 모든 HTTP 엔드포인트를 추가할 수 있습니다. Flow 측에서는 코드 변경이 필요하지 않습니다. 팩은 Routes.json에 항목을 추가할 수도 있습니다.

### 5.4 요청 처리 흐름

```
HTTP リクエスト受信
  ↓
認証（Authorization ヘッダー → api_keys.json 照合）
  → 失敗: 401 AUTH_REQUIRED / AUTH_INVALID
  ↓
ルーティング（method + path → routes.json 照合）
  → 失敗: 404 FLOW_NOT_FOUND
  ↓
input_mapping でリクエストボディを共通形式に変換
  ↓
APIキーの permissions で flow_id へのアクセス権を確認
  → 失敗: 403 PERMISSION_DENIED
  ↓
レート制限チェック
  → 超過: 429 RATE_LIMITED
  ↓
FlowEngine.execute(flow_id, input)
  ↓
stream == false:
  → Flow 完了まで待機 → JSON レスポンス返却
  → Content-Type: application/json

stream == true:
  → SSE ストリーム開始
  → Content-Type: text/event-stream
  → Flow の ctx.emit() イベントを SSE イベントに変換して逐次送信
  → Flow 完了時に stream.end を送信して接続を閉じる
```

### 5.5 SSE 스트리밍

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: stream.start
data: {"id":"req_01JXYZ","data":{}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"Hello"}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"!"}}

event: stream.end
data: {"id":"req_01JXYZ","data":{"status":"completed","output":{...}}}

```

### 5.6 OpenAI 호환 모드

Routes.json의 `/v1/chat/completions` 엔드포인트에 `response_format: "openai"`을 추가하면 응답이 OpenAI API 호환 형식으로 변환되어 반환됩니다.

```json
{
  "method": "POST",
  "path": "/v1/chat/completions",
  "flow_id": "default.chat",
  "input_mapping": {
    "model": "body.model",
    "messages": "body.messages",
    "stream": "body.stream",
    "temperature": "body.temperature",
    "max_tokens": "body.max_tokens",
    "tools": "body.tools"
  },
  "response_format": "openai"
}
```

변환은 전송 계층에서 수행됩니다. Flow 출력(공통 형식)을 OpenAI 응답 형식으로 매핑합니다.

```json
// 共通形式からの変換
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "created": 1709000000,
  "model": "claude-sonnet-4-20250514",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

스트리밍 중에도 OpenAI 호환 SSE 형식으로 변환됩니다. 이를 통해 기존 OpenAI SDK 및 라이브러리를 그대로 rumi에 연결할 수 있습니다.


## 6. stdio 전송

### 6.1 개요

stdin/stdout에서 JSON 라인을 보내고 받습니다. Tauri 프런트엔드와 rumiai 프로세스, CLI 간의 통신은 이 전송을 사용합니다.

### 6.2 형식

stdin (클라이언트 → rumiai):

```jsonl
{"id":"req_01","flow_id":"default.chat","input":{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}],"stream":false}}
{"id":"req_02","flow_id":"default.model_list","input":{}}
```

stdout(rumiai → 클라이언트):

```jsonl
{"id":"req_01","status":"completed","output":{"content":"Hello!","model":"gpt-4o","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"finish_reason":"stop"},"metadata":{"flow_id":"default.chat","duration_ms":800}}
{"id":"req_02","status":"completed","output":{"models":[...]},"metadata":{"flow_id":"default.model_list","duration_ms":50}}
```

스트리밍할 때:

```jsonl
{"event":"stream.start","id":"req_03","data":{}}
{"event":"stream.delta","id":"req_03","data":{"type":"content_delta","content":"Hello"}}
{"event":"stream.end","id":"req_03","data":{"status":"completed","output":{...}}}
```

### 6.3 인증

stdio 전송은 인증을 수행하지 않습니다. 상위 프로세스(Tauri의 Rust 레이어 또는 CLI를 시작한 셸)만 stdin/stdout에 연결할 수 있으므로 프로세스 간 신뢰가 충분합니다.

### 6.4 프런트엔드 메시지와의 통합

frontend.md에 정의된 `component.register`, `render.mount`, `message.send`와 같은 프런트엔드 관련 메시지도 동일한 stdin/stdout을 공유합니다. `type` 필드의 유무에 따라 구별됩니다.

```jsonl
// Flow 呼び出し（type フィールドなし、flow_id フィールドあり）
{"id":"req_01","flow_id":"default.chat","input":{...}}

// フロントエンドメッセージ（type フィールドあり）
{"type":"asset.register","data":{"asset_id":"defaults.chat","entry":"ui/chat.html",...}}
{"type":"message.send","component":"defaults.chat","data":{...}}
```

전송 핸들러는 메시지를 배포합니다. `flow_id`이 있는 경우 FlowEngine으로 전달합니다. `type`이 있는 경우 프런트엔드 처리기로 전달합니다.


## 7. UDS 전송

### 7.1 개요

Unix 도메인 소켓을 사용하여 통신합니다. 다른 로컬 프로세스(다른 애플리케이션, 스크립트, 편집기 플러그인 등)가 rumiai와 통신할 때 사용됩니다.

### 7.2 설정

```json
// user_data/config/transport.json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock"
  }
}
```

### 7.3 프로토콜

JSON 라인. stdio 전송과 동일한 형식입니다.

### 7.4 인증

소켓 파일 권한(`0600`, 소유자만 읽고 쓸 수 있음)에 의해 제어됩니다. API Key 인증을 추가로 요구하도록 설정하는 것도 가능합니다.

```json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock",
    "require_auth": true
  }
}
```

`require_auth: true`의 경우 연결 후 첫 번째 메시지에서 인증을 수행한다.

```jsonl
{"type":"auth","key":"rumi_xxxxxxxxxxxx"}
{"type":"auth.result","status":"ok"}
```


## 8. CLI 통합

### 8.1 개요

CLI는 stdio 전송 위에 구축된 씬 클라이언트입니다. rumiai 프로세스를 시작하고 stdin/stdout에서 공통 메시지 형식을 보내고 받습니다. CLI 자체에는 도메인 지식이 없습니다.

### 8.2 명령 시스템

CLI 명령은 flow_id의 별칭입니다.

```
rumi chat "hello"
  → {"flow_id": "default.chat", "input": {"messages": [{"role": "user", "content": "hello"}], "stream": true}}

rumi models
  → {"flow_id": "default.model_list", "input": {}}

rumi run my_custom_flow --input '{"key": "value"}'
  → {"flow_id": "my_custom_flow", "input": {"key": "value"}}
```

command와 flow_id 간의 매핑은 `user_data/config/cli.json`에 정의되어 있습니다.

```json
{
  "commands": {
    "chat": {
      "flow_id": "default.chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "model": "{flags.model}",
        "stream": true
      },
      "flags": {
        "model": {"short": "m", "default": null},
        "no-stream": {"type": "bool", "default": false}
      }
    },
    "models": {
      "flow_id": "default.model_list",
      "input_template": {}
    },
    "agent": {
      "flow_id": "default.agent_chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "agent_id": "{flags.agent}",
        "stream": true
      },
      "flags": {
        "agent": {"short": "a", "default": "coding_assistant"}
      }
    }
  },
  "aliases": {
    "c": "chat",
    "m": "models",
    "a": "agent"
  }
}
```

팩이 cli.json에 명령을 추가하는 경우 CLI에서 해당 팩의 흐름을 호출할 수 있습니다. CLI 코드를 변경할 필요가 없습니다.

### 8.3 출력 형식

CLI는 전송에서 수신된 일반 형식 응답을 사람이 읽을 수 있는 형식으로 변환합니다.

비스트리밍:

```
$ rumi chat "hello" --no-stream
Hello! How can I help you today?

[gpt-4o | 20 tokens | 1.2s]
```

스트리밍:

```
$ rumi chat "hello"
Hello! How can I help you today?█
```

스트리밍 시 stream.delta의 텍스트 청크가 순차적으로 출력됩니다. 커서가 끝에 나타납니다. stream.end 수신이 완료되었습니다.

### 8.4 위젯 텍스트 대체

흐름이나 도구가 Emit_widget과 함께 위젯 JSON을 보내는 경우 CLI는 위젯의 텍스트 표현으로 대체됩니다.

| 위젯 유형 | CLI 디스플레이 |
|---|---|
| 텍스트 | 텍스트로 출력 |
| 코드블록 | ```` 엔클로저 + 언어 이름 |
| 차이점 | 통합 diff 형식 |
| 이미지 | §루미§0§ |
| 스크린샷 | §루미§0§ |
| 터미널 | 명령 및 출력을 있는 그대로 |
| 진행 | §루미§0§ |
| 테이블 | ASCII 테이블 |
| 파일트리 | 들여쓰기된 텍스트 |
| 마크다운 | 있는 그대로 출력 |
| 차트 | 수치 요약 |
| 오디오 | §루미§0§ |
| 비디오 | §루미§0§ |
| 지도 | §루미§0§ |
| 지표 | §루미§0§ |
| 카드 | 머리글 + 본문의 텍스트 조합 |


## 9. 엔드포인트 등록 메커니즘

### 9.1 Flow API 트리거

HTTP 엔드포인트는 Flow 정의의 `trigger.type: api`에 등록되어 있습니다. flow.md의 트리거 시스템과 함께 작동합니다.

```yaml
# user_data/shared/flows/my_api/flow.yaml
flow_id: my_custom_api
trigger:
  type: api
  config:
    endpoint: "/v1/my/endpoint"
    method: POST
    auth_required: true

handler: handler.py
```

흐름이 배포되면 Transport.http 처리기가 경로를 다시 로드하고 이 끝점이 활성화됩니다.

### 9.2 Routes.json과의 관계

Routes.json은 정적 라우팅 정의입니다. Flow API 트리거는 동적으로 등록됩니다. 해결 순서는 다음과 같습니다.

1. Routes.json의 정적 경로(가장 높은 우선순위)
2. Flow API 트리거에 등록된 동적 경로

동일한 경로가 충돌하면 Routes.json이 우선합니다.

### 9.3 팩에 엔드포인트 추가

팩은 두 가지 방법으로 엔드포인트를 추가할 수 있습니다.

방법 1: Flow에 대한 API 트리거를 정의합니다.

```yaml
# user_data/packs/my_pack/flows/webhook_receiver/flow.yaml
flow_id: my_pack.webhook
trigger:
  type: api
  config:
    endpoint: "/hooks/my_pack"
    method: POST
    auth_required: false
handler: handler.py
```

방법 2: Routes.json에 항목을 추가합니다(Pack의 설치 스크립트를 통해).

두 방법 모두 기본값 측에서 코드를 변경할 필요가 없습니다.


## 10. 보안

### 10.1 전송 계층 격리

각 전송 핸들러는 Grant가 부여한 권한으로만 작동합니다. `io.http.server`처럼 전체 커널 객체를 전달하는 문제는 발생하지 않습니다.

### 10.2 인증 계층

| 운송 | 인증방법 | 기초 |
|---|---|---|
| HTTP | API 키(베어러 토큰) | 네트워크를 통한 접근에는 항상 인증이 필요합니다 |
| 스튜디오 | 없음 | 상위 프로세스 신뢰 |
| UDS | 소켓 권한 + 선택적 API 키 | 로컬 프로세스 신뢰 + 구성 가능 |

### 10.3 흐름 수준 권한

API 키의 `permissions` 필드를 사용하여 각 키에 대해 액세스 가능한 흐름을 제한할 수 있습니다. 강력한 관리 권한이 있는 키는 제한된 사용을 위해 키와 분리될 수 있습니다.

### 10.4 속도 제한

전송 계층에서 구현됩니다. `requests_per_minute`은 API 키별로 설정할 수 있습니다. 초과하면 `429 RATE_LIMITED`이 반환됩니다.

### 10.5 입력 유효성 검사

Flow의 `config_schema`(flow.md 섹션 6.1)에 따른 입력 검증은 FlowEngine에 의해 수행됩니다. 전송 계층은 형식 확인만 수행합니다(JSON으로 유효한가요?).


## 11. 기본 경로

기본 경로는 Routes.json에 등록됩니다. user_data의 Routes.json에서 모두 덮어쓰거나 삭제할 수 있습니다.

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools",
        "tool_choice": "body.tool_choice"
      },
      "response_format": "openai",
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "response_format": "openai",
      "description": "OpenAI 互換モデル一覧"
    },
    {
      "method": "GET",
      "path": "/v1/models/{model_id}",
      "flow_id": "default.model_info",
      "input_mapping": {
        "model_id": "path.model_id"
      },
      "response_format": "openai",
      "description": "OpenAI 互換モデル情報"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    },
    {
      "method": "GET",
      "path": "/v1/flows",
      "flow_id": "default.flow_list",
      "input_mapping": {},
      "description": "登録済み Flow の一覧"
    },
    {
      "method": "GET",
      "path": "/health",
      "flow_id": "default.health",
      "input_mapping": {},
      "description": "ヘルスチェック"
    }
  ]
}
```

### 11.1 input_mapping 표기법

| 표기법 | 설명 | 예 |
|---|---|---|
| §루미§0§ | 요청 본문 필드 | §루미§1§ |
| §루미§0§ | URL 경로 매개변수 | §루미§1§ |
| §루미§0§ | 쿼리 매개변수 | §루미§1§ |
| §루미§0§ | 요청 헤더 | §루미§1§ |
| §루미§0§ | 전신입력 | — |

### 11.2 응답_형식

| 가치 | 설명 |
|---|---|
| 생략 / `"default"` | 일반적인 메시지 형식으로 있는 그대로 반환 |
| §루미§0§ | OpenAI API 호환 형식으로 변환 및 반환 |

`"anthropic"` 등은 향후 추가될 수 있습니다. 변환 논리를 전송 계층에 배치합니다.


## 12. 다른 문서와의 관계

| 문서 | 관계 |
|---|---|
| 프론트엔드.md | stdio 전송의 메시지 형식은 frontend.md의 통신 흐름과 공존합니다. `flow_id`이 있으면 FlowEngine으로 이동하고, `type`이 있으면 프런트 엔드 |
| flow.md | 엔드포인트는 Flow의 API 트리거에 등록됩니다. FlowEngine이 요청을 처리합니다 |
| ai_client.md | 스트리밍 이벤트 유형은 ai_client.md 섹션 11.3 |
| 도구.md | 전송은 도구의 컨텍스트 API(call_handler, Emit_event 등)를 사용하여 조작되지 않습니다. 전송은 상위 계층이며 도구에 직접 닿지 않습니다 |
