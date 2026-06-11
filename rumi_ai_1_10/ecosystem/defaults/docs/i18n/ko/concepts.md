<!-- docs-i18n-links:start -->
[EN](../../concepts.md) | [JP](../ja/concepts.md) | [KR](./concepts.md) | [CN](../zh-cn/concepts.md)
<!-- docs-i18n-links:end -->

# 개념

rumiai 기본 팩의 핵심 개념을 설명합니다.

## 팩이란 무엇인가요?

팩은 루미아이 생태계의 응용 단위입니다. 디폴트 팩은 루미아이가 기본으로 제공되는 팩으로, 채팅, 에이전트, 코딩, AI 클라이언트, 도구, 프롬프트, 메모리, 미디어, 프런트 엔드 기능을 제공합니다.

각 팩은 `ecosystem.json`에서 해당 구조(구성 요소, 처리기 목록, 로딩 순서)를 선언합니다. 커널은 이 파일을 읽어 팩을 인식하고 핸들러 이름 확인을 수행합니다.

팩 이름은 핸들러 이름의 시작 부분에 사용됩니다. 기본 팩의 모든 핸들러는 `defaults.`(예: `defaults.chat.send`, `defaults.agent.execute`)으로 시작합니다.

## 블록/핸들러란 무엇인가요?

block은 `blocks/` 디렉터리 아래의 모듈 그룹이며 각 파일은 하나의 핸들러에 해당합니다. handler는 요청의 진입점이며 다음 시그니처를 사용하여 `run` 함수로 구현됩니다.

```python
def run(input_data: dict, context: dict) -> dict:
```

**`input_data`**은 요청 매개변수의 사전입니다. HTTP 요청의 본문은 JSON으로 구문 분석되고 URL 경로 매개변수(예: `conversation_id`)도 추가되어 전달됩니다.**`context`**는 흐름 정보와 종속 기능을 포함하는 사전입니다. `transport/http.py`의 `_build_context()`은 다음 필드를 사용하여 컨텍스트를 구성합니다.

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Flow ID. `"transport_direct"` for direct HTTP calls |
| `step_id` | `str` | Step ID. `"http_request"` for direct HTTP calls |
| `phase` | `str` | Phase. `"execute"` |
| `ts` | `str` | ISO 8601 timestamp |
| `owner_pack` | `str` | Pack ID of the caller. `"defaults"` |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Functions that call other handlers (injected via kernel) |

**반환 값**은 `blocks/_common.py`에 정의된 다음 두 가지 형식 중 하나일 수 있습니다.

```python
# 成功
def ok(data=None):
    return {"status": "ok", "data": data}

# エラー
def error(message, code="ERROR"):
    return {"status": "error", "error": {"code": code, "message": message}}
```

## 흐름이란 무엇인가요?

흐름은 여러 핸들러를 단계로 주문하는 실행 정의입니다. `flows/` 디렉토리 아래에 `flow.yaml` 및 `handler.py` 쌍으로 배치됩니다.

### flow.yaml의 구조

```yaml
flow_id: simple_chat            # フロー ID（一意）
name: "Simple Chat"             # 表示名
description: "シンプルなチャットフロー"  # 説明
version: "1.0.0"                # バージョン
trigger:                        # トリガー定義
  type: user_input              #   トリガー種別
  config:                       #   トリガー設定
    require_conversation: true  #     会話が必要か
handler: handler.py             # フロー handler ファイル
config_schema:                  # 設定スキーマ
  model:                        #   設定キー
    type: string                #     型
    default: "stub/default"     #     デフォルト値
metadata:                       # メタデータ
  author: "defaults"
  tags: ["chat", "default"]
```

기본 팩에는 다음 세 가지 흐름이 포함되어 있습니다.

- **`simple_chat`**: 간단한 채팅 흐름(도구 없음). `config_schema`에는 `model` 및 `system_prompt_id`이 있습니다.
- **`agent_chat`**: 도구 기반 에이전트 채팅 루프. `config_schema`에는 `agent_id` 및 `max_iterations`이 있습니다.
- **`planning_agent`**: 작업 분해 → 승인 → 순차적 실행의 흐름. `config_schema`에는 `agent_id` 및 `planning_model`이 있습니다.

## 도메인이란 무엇인가요?

domain은 핸들러가 호출하는 비즈니스 로직 계층입니다. 이는 `domain/` 디렉터리 아래 각 도메인의 하위 디렉터리로 배치됩니다.

핸들러는 유효성 검사만 수행하고, 도메인을 호출하고, 결과 형식을 지정하는 간단한 진입점입니다. 실제 로직(데이터 저장, AI 호출, 검색 등)은 도메인 계층의 클래스에서 처리됩니다.

주요 도메인 클래스는 다음과 같습니다:

- **`domain/chat/store.py`** — `ChatStore`: 대화 및 메시지용 인메모리 CRUD. 하나씩 일어나는 것.
- **`domain/agent/engine.py`** — `AgentEngine`: 에이전트 실행 루프(생각 → tool_call → 승인 → 응답).
- **`domain/agent/multi.py`** — `MultiAgentOrchestrator`: 다중 에이전트 오케스트레이션.
- **`domain/tool/registry.py`** — `ToolRegistry`: 도구 정의 등록 및 관리. 하나씩 일어나는 것. 메모리 내 지속성 + `user_data/shared/tools/`.
- **`domain/prompt/manager.py`** — `PromptManager`: 프롬프트 CRUD. 메모리 내 지속성 + `user_data/shared/prompts/`.
- **`domain/prompt/template.py`** — `PromptTemplate`: 도구 및 프롬프트를 위한 통합 템플릿 시스템입니다.
- **`domain/prompt/renderer.py`** — `render()`: `{{variable}}`를 템플릿 변수로 바꿉니다.
- **`domain/ai_client/client.py`** — `AIClient`: AI 공급자 추상화.

## 교통이란 무엇입니까?

Transport는 외부로부터의 요청을 받아 처리자에게 배포하는 계층입니다.

- **HTTP** (`transport/http.py`): `DefaultsHttpServer`는 Python 표준 `http.server`을 사용하여 HTTP 서버를 시작합니다. URL 경로 및 메소드 라우팅, JSON 구문 분석, CORS 헤더 및 정적 파일 전달을 처리합니다.
- **stdio** (`transport/stdio.py`): 표준 입력/출력 전송입니다. CLI 및 파이프를 통한 통신에 사용됩니다.
- **UDS**(`transport/uds.py`): Unix 도메인 소켓 전송. 로컬 IPC에 사용됩니다.

## 위젯이란 무엇인가요?

위젯은 `lib/rumi_widgets/`에 정의된 UI 구성 요소를 Python으로 표현한 것입니다. 위젯은 핸들러에서 프런트엔드로 전송되어 UI에 렌더링됩니다. 다음 모듈이 포함되어 있습니다:

- `display.py` — 텍스트, CodeBlock, 이미지 등과 같은 위젯을 표시합니다.
- `controls.py` — 입력, 버튼, 선택 등과 같은 위젯을 제어합니다.
- `layout.py` — 컨테이너, 행, 열 등과 같은 레이아웃 위젯.
- `stream.py` — 스트림, 표시기 등과 같은 스트림 위젯.
- `custom.py` — 맞춤 위젯

핸들러는 `context["emit_widget"](widget_json)`을 사용하여 UI에 위젯을 보낼 수 있습니다.

## 컨텍스트란 무엇인가요?

context는 핸들러에 전달된 실행 컨텍스트의 사전입니다. 주요 필드는 다음과 같습니다.

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Running flow ID. `"transport_direct"` for direct call |
| `step_id` | `str` | Current step ID. `"http_request"` for direct call |
| `phase` | `str` | Execution phase. `"execute"` |
| `ts` | `str` | Timestamp (ISO 8601) |
| `owner_pack` | `str` | Caller's Pack ID |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Function that calls other handlers |
| `emit_event` | `function` | Function that fires an event |
| `wait_event` | `function` | Function that waits for an event |
| `emit_widget` | `function` | Function to send Widget to UI |
| `cancel_check` | `function` | Function to check if canceled |
| `handler_config` | `dict` | Handler settings (conditions.json, etc.) |
| `session` | `dict` | Session information (session_id, workspace, etc.) |

## InterfaceRegistry / EventBus와의 관계

**InterfaceRegistry**는 커널이 관리하는 인터페이스의 레지스트리입니다. 각 Pack에서 제공하는 인터페이스(핸들러)는 `call_handler`에 의해 이름 확인을 위해 등록되어 사용됩니다. `/api/context` 엔드포인트에서 `facade.list_interfaces()`을 호출하여 등록된 인터페이스 목록을 얻을 수 있습니다.**EventBus**는 커널 관리 이벤트 버스입니다. `context["emit_event"](event_type, data)`로 이벤트를 시작하고 `context["wait_event"](event_type, timeout, filter)`으로 이벤트를 기다릴 수 있습니다. 핸들러와 흐름 간의 비동기 통신에 사용됩니다.
