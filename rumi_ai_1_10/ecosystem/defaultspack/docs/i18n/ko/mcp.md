<!-- docs-i18n-links:start -->
[EN](../../mcp.md) | [JP](../ja/mcp.md) | [KR](./mcp.md) | [CN](../zh-cn/mcp.md)
<!-- docs-i18n-links:end -->

# MCP(Model Context Protocol) 가이드

## 1. MCP란 무엇인가요?

MCP(Model Context Protocol)는 LLM 응용 프로그램이 외부 도구 서버와 통신하기 위한 표준 프로토콜입니다. 기본 도구 모듈에는 MCP 서버에서 제공하는 도구를 rumiai의 도구 시스템에 통합할 수 있는 MCP 클라이언트가 내장되어 있습니다.

MCP 서버에 의해 노출된 도구는 rumiai의 기본 도구(user_data/shared/tools/에 있음)와 동일한 방식으로 LLM에서 호출됩니다. LLM은 도구가 MCP를 통해 사용되는지 아니면 기본으로 사용되는지 여부를 알 필요가 없습니다.


## 2. 서버 접속 방법

### stdio 연결

MCP 서버를 하위 프로세스로 시작하고 stdin/stdout을 통해 통신합니다.

```json
{
  "server_id": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
  "env": {}
}
```

### SSE 연결

HTTP 서버에서 보낸 이벤트를 사용하여 이미 실행 중인 MCP 서버에 연결합니다.

```json
{
  "server_id": "remote_db",
  "transport": "sse",
  "url": "http://localhost:3001/sse",
  "headers": {
    "Authorization": "Bearer ${MCP_DB_TOKEN}"
  }
}
```


## 3. 설정 작성 방법

MCP 서버의 정의는 `user_data/shared/tools/mcp.json`에 설명되어 있습니다.

```json
{
  "servers": [
    {
      "server_id": "filesystem",
      "name": "File System Server",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "env": {},
      "auto_connect": true,
      "tool_prefix": "mcp_fs",
      "approval_mode": "per_session"
    },
    {
      "server_id": "github",
      "name": "GitHub Server",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "auto_connect": false,
      "tool_prefix": "mcp_gh",
      "approval_mode": "per_call"
    },
    {
      "server_id": "remote_api",
      "name": "Remote API Server",
      "transport": "sse",
      "url": "https://mcp.example.com/sse",
      "headers": {
        "Authorization": "Bearer ${MCP_API_TOKEN}"
      },
      "auto_connect": false,
      "tool_prefix": "mcp_api",
      "approval_mode": "per_session"
    }
  ]
}
```

`server_id`은 시스템 내의 고유 식별자입니다. `auto_connect`이 true인 경우 rumiai가 시작될 때 자동으로 연결됩니다. `tool_prefix`는 MCP 도구 이름에 추가되는 접두사입니다(기본 도구와의 이름 충돌을 방지하기 위해). `approval_mode`의 경우 `per_call`(매회 승인), `per_session`(세션당 한 번), `auto`(자동 승인) 중에서 선택합니다.

환경 변수는 `${VAR_NAME}` 구문을 사용하여 참조할 수 있습니다.


## 4. 도구 목록 가져오기

연결된 MCP 서버용 도구 목록을 가져옵니다.

```python
# handler 経由
tools = context["call_handler"]("defaults.tool.mcp_list", {
    "server_id": "filesystem"
})
# 戻り値:
# [
#   {
#     "tool_id": "mcp_fs_read_file",
#     "name": "read_file",
#     "description": "Read the contents of a file",
#     "parameters": { ... JSON Schema ... },
#     "server_id": "filesystem",
#     "source": "mcp"
#   },
#   ...
# ]
```

모든 서버에 대한 도구를 한 번에 얻으려면 `server_id`를 생략하세요.

```python
all_mcp_tools = context["call_handler"]("defaults.tool.mcp_list", {})
```


## 5. 도구 호출

MCP 도구를 호출하면 기본 도구와 동일한 `defaults.tool.invoke` 처리기가 사용됩니다.

```python
result = context["call_handler"]("defaults.tool.invoke", {
    "tool_name": "mcp_fs_read_file",
    "arguments": {"path": "/workspace/README.md"}
})
```

내부적으로 도구 모듈의 executor.py는 `tool_id` 접두사에서 MCP 도구인지 확인하고 `mcp_client.py`를 통해 MCP 서버에 `tools/call` 요청을 보냅니다.

LLM이 tool_call을 사용하여 MCP 도구를 호출할 때 동일한 경로가 사용됩니다. LLM에는 기본 도구나 MCP 도구에 관계없이 통합된 도구 목록이 제공됩니다.


## 6. 서버 연결 끊기

```python
context["call_handler"]("defaults.tool.mcp_disconnect", {
    "server_id": "filesystem"
})
```

연결을 끊으면 해당 서버의 도구가 LLM 도구 목록에서 제거됩니다. 재연결은 `defaults.tool.mcp_connect`을 통해 이루어집니다.


## 7. API 엔드포인트

| 핸들러 | 허가 | 설명 |
|---|---|---|
| §루미§0§ | §루미§1§ | MCP 서버에 연결 |
| §루미§0§ | §루미§1§ | 연결된 서버용 도구 목록 가져오기 |
| §루미§0§ | §루미§1§ | MCP 서버 연결 끊기 |
| §루미§0§ | §루미§1§ | 호출 도구(MCP/네이티브 공통) |
| §루미§0§ | §루미§1§ | 모든 도구 목록 가져오기(MCP 포함) |
| §루미§0§ | §루미§1§ | 도구 스키마 가져오기 |

### input_data / 반환 값

**defaults.tool.mcp_connect**

입력_데이터:
```json
{
  "server_id": "filesystem",
  "config": {}
}
```
`config`을 생략하면 mcp.json 정의가 사용됩니다. `config`을 전달하면 임시 연결 설정으로 사용됩니다.

반환 값:
```json
{
  "server_id": "filesystem",
  "status": "connected",
  "tools_count": 5,
  "tools": ["mcp_fs_read_file", "mcp_fs_write_file", "..."]
}
```

**defaults.tool.mcp_list**

입력_데이터:
```json
{
  "server_id": "filesystem"
}
```
`server_id` 모든 서버를 생략합니다.

반환 값:
```json
[
  {
    "tool_id": "mcp_fs_read_file",
    "name": "read_file",
    "description": "Read the contents of a file",
    "parameters": {},
    "server_id": "filesystem",
    "source": "mcp"
  }
]
```

**defaults.tool.mcp_disconnect**

입력_데이터:
```json
{
  "server_id": "filesystem"
}
```

반환 값:
```json
{
  "server_id": "filesystem",
  "status": "disconnected"
}
```
