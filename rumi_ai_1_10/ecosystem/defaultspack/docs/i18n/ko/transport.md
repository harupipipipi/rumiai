<!-- docs-i18n-links:start -->
[EN](../../transport.md) | [JP](../ja/transport.md) | [KR](./transport.md) | [CN](../zh-cn/transport.md)
<!-- docs-i18n-links:end -->

# 전송 계층

defaultspack은 프런트 엔드 및 클라이언트와의 통신 수단으로 세 가지 유형의 전송을 제공합니다. 둘 다 `transport/` 디렉터리에 있습니다.

---

## 개요

전송 계층은 클라이언트로부터 요청을 받아 `transport/registry.py`에서 엔드포인트 -> 흐름/함수 선언을 해결하고 응답을 반환하는 중간 계층입니다. 일반적으로 채팅의 메인 라인은 `defaultspack.chat_turn` / `defaultspack.chat_stream_turn`를 거치며, 기존 프런트엔드의 HTTP 경로, JSON 형태, SSE 이벤트 형태는 fallback 블록과 하위 호환성을 유지합니다. `ecosystem/defaults/transport/*`은 defaultspack 전송과의 호환성 심입니다.

전송 선택은 시작 시 결정됩니다. `defaults.frontend.start` 핸들러는 `transport` 매개변수를 기반으로 적절한 전송을 시작합니다.

---

## HTTP 서버(`transport/http.py`)

### DefaultsHttpServer

`DefaultsHttpServer`은 Python 표준 라이브러리의 `http.server.HTTPServer`을 기반으로 하는 HTTP 서버입니다.

```python
from transport.http import start_http_server

server = start_http_server(facade)  # KernelFacade or None
```

**생성자 인수:**

`facade` — 커널의 KernelFacade 인스턴스입니다. `/api/context` 엔드포인트에서 `list_interfaces()`를 호출하는 데 사용됩니다. 아무 것도 가능하지 않습니다.

**환경 변수:**

`DEFAULTS_HTTP_HOST` — 호스트 바인딩. 기본 `127.0.0.1`.
`DEFAULTS_HTTP_PORT` — 포트 바인딩. 기본 `8766`.

**스레딩 모델:** 데몬 스레드에서 `serve_forever()`를 실행합니다. 메인 스레드를 차단하지 마세요.

### 라우팅 작동 방식

`_setup_routes()` 메서드는 `transport/registry.py`에서 표준 경로 사양을 읽습니다. flow YAML의 `transport.http.routes`가 최우선 순위이며 누락된 엔드포인트는 호환 가능한 폴백 사양 및 구성 요소 경로 사양으로 보완됩니다. 패턴의 `{param}`는 정규식 `(?P<param>[^/]+)`로 변환되어 컴파일된 정규식으로 유지됩니다.

요청이 도착하면 `_match_route(method, path)`는 모든 경로를 순서대로 검색하고 일치하는 메서드와 경로가 있는 첫 번째 경로에 대한 핸들러를 호출합니다. 경로 매개변수는 `groupdict()`에서 추출되어 각 핸들러에 전달됩니다.

각 핸들러 내에서 경로 매개변수는 `request_data` 딕셔너리에 주입됩니다. 예를 들어 `/api/chat/conversations/{id}`의 경우 `request_data["conversation_id"] = path_params.get("id", "")`로 설정된다.

### HTTP 경로 목록

| 방법 | 경로 | 핸들러(블록) |
|---|---|---|
| §루미§0§ | §루미§1§ | `defaultspack.chat_turn`(`blocks/chat/send.py` 대체) |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | `defaultspack.chat_turn`(`blocks/chat/send.py` 대체) |
| §루미§0§ | §루미§1§ | `defaultspack.chat_stream_turn`(`blocks/chat/stream.py` 대체) |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | §루미§2§ |
| §루미§0§ | §루미§1§ | (인라인: 상태 점검) |
| §루미§0§ | §루미§1§ | (인라인: 팩 정보 + 인터페이스) |
| §루미§0§ | §루미§1§ | (정적: `ui/shell.html`) |
| §루미§0§ | §루미§1§ | (정적: `ui/{path}`) |

### CORS 설정

모든 응답에는 다음 헤더가 있습니다.

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

`OPTIONS` 요청은 204 콘텐츠 없음 응답으로 사전 전달됩니다.

### 요청 처리 흐름

1. `_RequestHandler`이 HTTP 요청을 받습니다.
2. 경로의 쿼리 문자열 부분을 제거합니다(`?` 잘라냄).
3. `_match_route()`와 일치하는 경로
4. POST/PUT의 경우 본문을 JSON으로 구문 분석합니다.
5. `(request_data, path_params)`으로 핸들러 함수를 호출합니다.
6. 결과에 `_static` 플래그가 있으면 이를 정적 파일로 반환합니다.
7. 그렇지 않은 경우 JSON 응답으로 반환합니다(오류인 경우 400, 성공인 경우 200).
8. 처리기의 예외는 500 내부 서버 오류입니다.

### 컨텍스트 구성

`_build_context()`의 각 처리기에 의해 생성된 컨텍스트는 다음과 같은 구조를 갖습니다.

```python
{
    "flow_id": "transport_direct",
    "step_id": "http_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",  # ISO 8601
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

### 커널파사드

`DefaultsHttpServer` 생성자에 전달된 `facade`는 커널의 `io.http.server` 모듈에서 제공하는 `KernelFacade` 인스턴스입니다. 기본 팩이 커널 없이 독립형으로 실행되는 경우 `None`를 전달합니다. Facade가 설정된 경우 `/api/context` 엔드포인트는 `facade.list_interfaces()`을 호출하고 인터페이스 정보를 반환합니다.

---

## stdio 전송(`transport/stdio.py`)

### DefaultsStdioTransport

stdin/stdout을 사용하여 JSONL(JSON Lines) 형식 전송. CLI 도구 및 파이프라인 통합용.

**시작 방법:**

```python
from transport.stdio import DefaultsStdioTransport

transport = DefaultsStdioTransport()
transport.start()  # ブロッキング（stdin を読み続ける）
```

### JSONL 프로토콜

**요청 형식(JSON 1줄):**

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {"model": "openai/gpt-4o"}}
```

| 필드 | 필수 | 유형 | 설명 |
|---|---|---|---|
| §루미§0§ | 선택사항 | §루미§1§ | HTTP 메서드. 기본 `"GET"` |
| §루미§0§ | 필수 | §루미§1§ | 엔드포인트 경로 |
| §루미§0§ | 선택사항 | §루미§1§ | 요청 본문 |

**응답 형식(JSON 한 줄을 표준 출력으로 출력):**

```json
{"status": "ok", "data": {...}}
```

### stdio 경로 목록

stdio 전송은 `transport/registry.py`의 표준 경로 사양을 사용합니다. 정적 파일을 제외하면 HTTP와 동일한 엔드포인트 -> 흐름/함수 메인 라인을 통과합니다. `_ROUTE_MAP` 및 `_ID_INJECT_MAP`는 기존 코드와 호환되는 내보내기입니다.

| 방법 | 경로 | 블록 모듈 | ID 주입 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | §루미§2§ | — |
| §루미§0§ | §루미§1§ | §루미§2§ | — |
| §루미§0§ | §루미§1§ | §루미§2§ | — |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | — |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | §루미§2§ | §루미§3§ ← §루미§4§ |
| §루미§0§ | §루미§1§ | (인라인) | — |
| §루미§0§ | §루미§1§ | (인라인) | — |

정적 파일 전달(`/`, `/chat`, `/static/{path}`)은 HTTP 전송에만 적용됩니다.

### 라우팅

경로 일치는 `_match_route()` 기능에 의해 수행됩니다. HTTP 전송과 유사하게 `{param}`을 정규식으로 변환하고 일치시킵니다. 경로 매개변수 주입은 `_ID_INJECT_MAP` dict를 참조하여 수행됩니다.

### 컨텍스트 구성

`_build_context()`에서 stdio Transport가 생성하는 컨텍스트:

```python
{
    "flow_id": "stdio_direct",
    "step_id": "stdio_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

---

## UDS 전송(`transport/uds.py`)

### DefaultsUdsTransport

Unix 도메인 소켓을 사용하여 전송합니다. 로컬 프로세스 간 통신용.

**시작 방법:**

```python
from transport.uds import DefaultsUdsTransport

transport = DefaultsUdsTransport(socket_path="/tmp/rumi_defaults.sock")
transport.start()  # ブロッキング
```

**환경 변수:**

`DEFAULTS_UDS_PATH` — 소켓 경로. 기본 `/tmp/rumi_defaults.sock`.

### 프로토콜

길이 접두사 방법: 4바이트(빅엔디안) 메시지 길이 + JSON 바이트 문자열.

**요청:**

```
[4 bytes: length][JSON bytes]
```

JSON의 구조는 stdio와 동일합니다.

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {...}}
```

**응답:**

```
[4 bytes: length][JSON bytes]
```

### 메시지 크기 제한

최대 10MB(10 * 1024 * 1024바이트). 한도를 초과하면 오류 응답이 반환됩니다.

### 스레딩 모델

승인 루프는 메인 스레드에서 실행되며 각 클라이언트 연결은 데몬 스레드에 의해 처리됩니다. `listen(8)`이 포함된 백로그 8. 소켓 시간 초과는 1초입니다.

### 라우팅

stdio 전송과 동일한 `_ROUTE_MAP` 및 `_ID_INJECT_MAP`을 사용합니다. 이용 가능한 경로는 stdio Transport와 동일합니다.

### 컨텍스트 구성

`_build_context()`에서 UDS 전송에 의해 생성된 컨텍스트:

```python
{
    "flow_id": "uds_direct",
    "step_id": "uds_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}
```

### 수명주기

`start()` `unlink` 호출 시 기존 소켓 파일이 있는 경우. `stop()` 호출 시 소켓 파일도 삭제합니다.
