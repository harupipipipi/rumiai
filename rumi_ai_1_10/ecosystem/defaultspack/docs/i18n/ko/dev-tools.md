<!-- docs-i18n-links:start -->
[EN](../../dev-tools.md) | [JP](../ja/dev-tools.md) | [KR](./dev-tools.md) | [CN](../zh-cn/dev-tools.md)
<!-- docs-i18n-links:end -->

# 개발 도구 가이드

## 1. 컨셉

Dev Tools는 기본적으로 제공되는 개발자용 검사 및 디버깅 기능 그룹입니다. AI 요청 내역, 신속한 사용 내역, 실시간 편집, 요청 재생 기능을 제공합니다.

개발자 도구 핸들러는 `blocks/dev/` 디렉터리에 위치하며 `ecosystem.json`의 `dev` 구성 요소로 선언됩니다. 특정 UI 패널은 user_data 측의 자산으로 제공되지만 기본 팩에는 `ui/dev_panel.js`의 참조 구현이 포함되어 있습니다.

`blocks/dev/`에는 다음 파일이 포함되어 있습니다.

| file | handler name |
|---|---|
| `inspect.py` | `defaults.dev.inspect` |
| `prompt_history.py` | `defaults.dev.prompt_history` |
| `edit_prompt_live.py` | `defaults.dev.edit_prompt_live` |
| `replay.py` | `defaults.dev.replay` |


## 2. 검사(요청정보 확인)

LLM에 제출된 요청의 전체 세부 정보를 확인하세요.

**처리자**: `defaults.dev.inspect`(`blocks/dev/inspect.py`)**HTTP**: `GET /api/dev/inspect`

```python
# handler 経由で直前のリクエスト情報を取得
info = context["call_handler"]("defaults.dev.inspect", {
    "conversation_id": "conv-1",
    "message_id": "msg-latest"
})
```

반환 값:
```json
{
  "request": {
    "model": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "messages": [ "...StandardMessage 配列..." ],
    "tools": [ "...ツール定義..." ],
    "params": { "temperature": 0.7, "max_tokens": 8192 },
    "system_prompt": "...レンダリング済みシステムプロンプト...",
    "total_input_tokens": 12500
  },
  "response": {
    "content": [ "...Content Block 配列..." ],
    "finish_reason": "tool_calls",
    "usage": { "input_tokens": 12500, "output_tokens": 350 },
    "latency_ms": 2800,
    "time_to_first_token_ms": 650
  },
  "context_breakdown": {
    "system_prompt_tokens": 1500,
    "project_memory_tokens": 800,
    "user_memory_tokens": 200,
    "tools_tokens": 3000,
    "history_tokens": 7000,
    "reserve_tokens": 0
  }
}
```


## 3. 프롬프트 기록

세션 중에 렌더링된 프롬프트 기록을 확인하세요.

**처리자**: `defaults.dev.prompt_history`(`blocks/dev/prompt_history.py`)**HTTP**: `GET /api/dev/prompt-history`

```python
history = context["call_handler"]("defaults.dev.prompt_history", {
    "session_id": "sess-123",
    "limit": 20
})
```

반환 값:
```json
[
  {
    "timestamp": 1771056800000,
    "prompt_id": "coding_system",
    "variables_used": ["agent_name", "tools", "project_memory"],
    "rendered_length": 3200,
    "source": "user_data/shared/prompts/coding_system"
  }
]
```


## 4. 프롬프트 실시간 편집

즉시 프롬프트를 편집하고 재정의합니다. 지정된 `prompt_name` 프롬프트가 존재하는 경우 `content`이 업데이트됩니다. 존재하지 않는 경우 새 항목이 생성됩니다. `prompt_name`에 `"system"`를 지정하면 시스템 프롬프트가 다시 작성됩니다.

**처리자**: `defaults.dev.edit_prompt_live`(`blocks/dev/edit_prompt_live.py`)**HTTP**: `POST /api/dev/edit-prompt`

```python
context["call_handler"]("defaults.dev.edit_prompt_live", {
    "prompt_name": "coding_system",
    "new_body": "あなたは関数型プログラミングの専門家です。..."
})
```

반환 값:
```json
{
  "status": "ok",
  "data": {
    "prompt_name": "coding_system",
    "updated": true,
    "content": "あなたは関数型プログラミングの専門家です。...",
    "prompt_id": "a1b2c3d4"
  }
}
```

복원하려면 `new_body`에 원본 템플릿 본문을 지정하고 다시 호출하세요.


## 5. replay (과거 요청 재생)

동일한 매개변수를 사용하여 이전 LLM 요청을 다시 실행합니다. 모델과 매개변수를 변경하는 것도 가능합니다.

**처리자**: `defaults.dev.replay`(`blocks/dev/replay.py`)**HTTP**: `POST /api/dev/replay`

```python
result = context["call_handler"]("defaults.dev.replay", {
    "conversation_id": "conv-1",
    "message_id": "msg-005",
    "override": {
        "model": "openai/gpt-4o",
        "params": {"temperature": 0.0}
    }
})
```

반환 값은 `defaults.ai.complete`과 동일한 형식을 갖습니다. 원래 요청의 메시지 배열과 도구 정의를 재사용하고 모델과 매개변수만 교체한 후 다시 실행하세요.


## 6. Ctrl+Shift+D를 사용한 디스플레이 패널

프런트 엔드의 자산은 `Ctrl+Shift+D` 키 바인딩을 감지하고 개발자 도구 패널의 표시/숨기기를 전환합니다.

패널 자산은 user_data 팩으로 제공됩니다. 기본값은 개발자 도구 처리기(`defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`)를 제공합니다. 참조 구현은 기본 팩의 `ui/dev_panel.js`에 포함되어 있습니다.

패널 자산 배치 슬롯에는 `panel.bottom` 또는 `floating`이 권장됩니다.


## 7. API 엔드포인트

| handler | HTTP route | input_data | return value |
|---|---|---|---|
| `defaults.dev.inspect` | `GET /api/dev/inspect` | `{conversation_id, message_id}` | Request/Response Details |
| `defaults.dev.prompt_history` | `GET /api/dev/prompt-history` | `{session_id, limit}` | Prompt usage history array |
| `defaults.dev.edit_prompt_live` | `POST /api/dev/edit-prompt` | `{prompt_name, new_body}` | `{prompt_name, updated, content, prompt_id}` |
| `defaults.dev.replay` | `POST /api/dev/replay` | `{conversation_id, message_id, override}` | StandardResponse |
