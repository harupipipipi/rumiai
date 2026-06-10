<!-- docs-i18n-links:start -->
[EN](../../getting-started.md) | [JP](../ja/getting-started.md) | [KR](./getting-started.md) | [CN](../zh-cn/getting-started.md)
<!-- docs-i18n-links:end -->

# 시작하기

rumiai 기본 팩 설정부터 첫 번째 대화 보내기까지의 안내입니다.

## 전제조건

- **Python 3.11 이상** 설치
- **rumiai 커널**이 설정되었습니다(`https://github.com/harupipipipi/rumiai`의 `rumi_ai_1_10/` 아래).
- **git**이 설치되었습니다.

## 설치

### 1. 클론 기본값 팩

```bash
git clone https://github.com/harupipipipi/rumiai_defaults.git
```

### 2. 커널에 등록

기본 팩 경로를 rumiai 커널의 팩 등록 디렉터리로 설정합니다. 커널의 `ecosystem/` 디렉터리 또는 구성 파일에 기본 팩의 루트 경로를 지정합니다. 기본 팩의 루트에는 커널이 팩을 인식하기 위해 읽는 `ecosystem.json`이 포함되어 있습니다.

```
ecosystem.json   ← カーネルが読み取る Pack 構造定義
blocks/          ← handler（ビジネスロジックの入口）
domain/          ← ドメインロジック
transport/       ← HTTP / stdio / UDS サーバー
flows/           ← Flow 定義
ui/              ← フロントエンド（shell.html, dev_panel.js）
```

### 3. 환경변수 설정하기

기본 팩의 HTTP 서버는 다음 환경 변수를 참조합니다. `transport/http.py`의 `DefaultsHttpServer.__init__`을 읽어보세요.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | HTTP 서버 바인드 주소 |
| §루미§0§ | §루미§1§ | HTTP 서버 포트 번호 |

AI 공급자를 사용하는 경우 각 공급자에 대한 API 키도 설정합니다(예: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등). API 키가 설정되지 않은 경우 AI 호출은 스텁 응답(`[stub] AI response placeholder`)을 반환합니다.

```bash
export DEFAULTS_HTTP_HOST=127.0.0.1
export DEFAULTS_HTTP_PORT=8766
export OPENAI_API_KEY=sk-...
```

## 시작하는 방법

기본 팩은 커널에서 시작됩니다. 커널이 `defaults.frontend.start` 핸들러를 호출하면 `blocks/frontend/start.py`의 `run()`이 실행됩니다. `run()`은 `input_data`에서 `facade`를 가져오고 `transport.http.start_http_server(facade)`을 호출하여 HTTP 서버를 시작합니다. `facade`이 `None`인 경우 오류를 반환합니다.

```python
# blocks/frontend/start.py の動作概要
def run(input_data, context):
    from transport.http import start_http_server
    facade = input_data.get("facade")
    if facade is None:
        return error("facade is required")
    server = start_http_server(facade)
    return ok({
        "message": "HTTP server started",
        "host": server.host,
        "port": server.port,
    })
```

성공적으로 시작되면 콘솔에 다음과 같은 메시지가 표시됩니다.

```
[defaults] HTTP server started on 127.0.0.1:8766
```

## 첫 번째 대화를 보내는 단계

### 브라우저에서 열기

브라우저에서 `http://127.0.0.1:8766/`에 액세스하면 `ui/shell.html`이 반환됩니다. UI가 표시되면 시동에 성공한 것입니다.

HTTP 서버 루트 `/`는 `transport/http.py`의 `_handle_static()`에 의해 처리되며, 이는 Pack 루트에 상대적인 경로 `ui/shell.html`를 읽고 반환합니다. 추가 정적 파일(CSS, JS, 이미지 등)은 `/static/{path}`에서 액세스할 수 있으며 `_handle_static_file()`는 `ui/{path}`에서 파일을 로드합니다. 예를 들어 `/static/dev_panel.js`은 `ui/dev_panel.js`을 반환합니다.

### 대화를 만들고 컬을 사용하여 메시지 보내기

#### 1. 대화 만들기

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'
```

응답(`blocks/chat/create_conversation.py` → `domain/chat/store.py`의 `create_conversation()`):

```json
{
  "status": "ok",
  "data": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "New Conversation",
    "model": "stub/default",
    "messages": [],
    "current_node_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "created_at": 1700000000000,
    "updated_at": 1700000000000
  }
}
```

#### 2. 메시지 보내기

반환된 `id`를 `{conversation_id}`로 사용하세요.

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{conversation_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "content": "Hello, world!"
    }
  }'
```

이 요청은 `blocks/chat/send.py`의 `run()`을 호출합니다. 사용자 메시지를 저장하고, 대화 내용을 AI에 보내고, AI 응답을 보조 메시지로 저장하고 반환합니다.

```json
{
  "status": "ok",
  "data": {
    "id": "...",
    "role": "assistant",
    "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
    "conversation_id": "...",
    "parent_id": "...",
    "sequence_number": 2,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  }
}
```

## 문제 해결

### 서버가 시작되지 않습니다

- `DEFAULTS_HTTP_PORT`이 다른 프로세스에서 사용되고 있는지 확인하시기 바랍니다.
- `input_data`에 `facade`이 포함되어 있지 않으면 `blocks/frontend/start.py`는 `error("facade is required")`을 반환합니다. 파사드가 커널에서 올바르게 전달되었는지 확인하세요.

### `[stub] AI response placeholder`이 반환됩니다.

- AI 제공자의 API 키가 설정되지 않았거나 `call_handler`가 `None`인 경우 스텁 응답이 반환됩니다.
- `blocks/chat/send.py`의 `_stub_response()`가 대체 수단으로 사용됩니다.
- 실제 AI 응답을 얻으려면 환경 변수에 API 키를 설정하고 대화의 `model`에 유효한 모델 이름(예: `openai/gpt-4o`)을 지정하세요.

### 대화를 찾을 수 없음(NOT_FOUND)

- `ChatStore`은 메모리 내 싱글톤(`domain/chat/store.py`)입니다. 서버를 다시 시작하면 모든 대화 데이터가 손실됩니다.
- 대화 생성 시 반환된 `id`이 올바른지 확인해주세요.

### CORS 오류

- HTTP 서버는 모든 출처로부터의 접근을 허용합니다(`Access-Control-Allow-Origin: *`). CORS가 문제인 경우 브라우저 확장 프로그램 및 프록시의 영향을 확인하세요.

### 건강검진

아래에서 서버 운영 현황을 확인하실 수 있습니다.

```bash
curl http://127.0.0.1:8766/api/health
```

```json
{
  "status": "ok",
  "data": {
    "status": "healthy",
    "pack": "defaults",
    "ts": "2025-01-01T00:00:00Z"
  }
}
```
