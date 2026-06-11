<!-- docs-i18n-links:start -->
[EN](../../handoff_defaultspack_function_flow.md) | [JP](../ja/handoff_defaultspack_function_flow.md) | [KR](./handoff_defaultspack_function_flow.md) | [CN](../zh-cn/handoff_defaultspack_function_flow.md)
<!-- docs-i18n-links:end -->

# 핸드오프: defaultspack 함수/흐름 런타임

이 핸드오프는 독립적입니다. 다음 엔지니어가 다음 사항만 알고 있다고 가정합니다.
저장소 이름, `rumiai`, 이전 대화를 읽지 않았습니다.

## 저장소 및 지점

- 저장소: `rumiai`
- 이 체크포인트에 사용된 로컬 작업공간:
  `/Users/haru/Desktop/puroguramukei/rumi_ai_mac`
- 메인 패키지 디렉터리: `rumi_ai_1_10`
- 지점: `codex/defaultspack-function-flow`
- 원격: `origin`, `https://github.com/harupipipipi/rumiai.git`
- 이 핸드오프 파일 이전의 체크포인트 커밋:
  `776178f2 WIP: canonicalize defaultspack function flow runtime`

동일한 지점에서 작업을 계속하고 나머지 모든 작업을 하나의 PR에 넣습니다.
사용자가 명시적으로 범위를 변경하지 않는 한 이를 여러 PR로 분할하지 마세요.

## 사용자 목표

사용자는 `defaultspack`가 정식 런타임이 되기를 원하며
다음 아키텍처 규칙과 일치하도록 구현합니다.

- `defaultspack`은 표준 런타임입니다.
- `defaults`은 얇은 호환성 심으로만 남아 있습니다.
- 도구는 기능/능력 파사드로 구현됩니다.
- 도구 안전은 `write_action: true`에 의존해서는 안 됩니다.
- 신뢰할 수 없는 사용자/팩 코드는 Docker 격리 내에서 실행되어야 합니다.
- 호스트 접속, 네트워크 접속, 파일 편집, 터미널, Git, 브라우저 등
  컴퓨터 제어는 신뢰할 수 있는 기본 기능/능력 부여를 거쳐야 합니다.
- 일반 채팅 입력은 선언적 YAML 흐름과 Python 흐름을 거쳐야 합니다.
  엔진.
- 흐름은 오케스트레이션일 뿐입니다. 실제 논리는 함수에 속합니다.
- 프롬프트는 실행 가능한 도구 논리가 아닌 수동적 컨텍스트입니다.
- AI 공급자는 OpenAI 호환 공급자와 함께 매니페스트 우선이어야 합니다.
  가능한 경우 매니페스트/모델 정의를 통해 추가할 수 있습니다.
- 프론트엔드 HTTP/SSE/위젯 계약은 백엔드 동안에도 호환성을 유지해야 합니다.
  내부는 경로 레지스트리 + 흐름/기능으로 이동합니다.

최종적으로 원하는 결과는 이를 완벽하게 구현하고 검증하는 하나의 PR입니다.
방향.

## 보존을 위한 아키텍처 결정

- 표준 런타임: `ecosystem/defaultspack`.
- 레거시 호환성: `ecosystem/defaults`은 `defaultspack`에 위임됩니다.
- 흐름 구현: YAML 선언과 Python 엔진.
- 허용되는 승인 가능한 도구 실행 유형:
  - `rumi_function`
  - `capability`
  - `mcp`
- `local`, `handler`, `dynamic`, `prompt` 등의 레거시 실행 유형
  신뢰할 수 없는 도구에는 사용할 수 없습니다. 기존 자사 호환성
  경로는 일시적으로 유지될 수 있지만 신뢰할 수 없는 도구에 대해서는 장애 시 닫혀야 합니다.
- 현재 사용되는 기능 분류:
  - `file.read`
  - `file.write`
  - `terminal.exec`
  - `git.read`
  - `git.write`
  - `network.read`
  - `network.send`
  - `browser.control`
  - `computer.control`
- `write_action`은 메타데이터일 뿐입니다. 허가 및 위험 결정이 이루어져야 합니다.
  위험 등급, 승인 정책, 실행 유형, 신뢰할 수 있는 팩 ID 등
  능력 부여.
- 엄격한 Docker 정책은 Docker를 사용할 수 없는 경우 호스트 대체를 거부해야 합니다.

## 체크포인트에 이미 구현된 내용

### 도구 보안 및 기능화

- `ecosystem/defaultspack/domain/tool/security.py`을 추가했습니다.
- 위험을 정상화하기 위해 `ecosystem/defaultspack/domain/tool/registry.py`을 업데이트했습니다.
  지원되지 않는 신뢰할 수 없는 레거시 실행 유형을 거부하고 기능을 노출합니다.
  도구가 표시되는 UI/확장 호환성을 부여하고 유지합니다.
  하지만 여전히 보안 정책에 따라 실행할 수 없습니다.
- 시행을 위해 `ecosystem/defaultspack/domain/tool/executor.py` 업데이트
  기능/능력 우선 실행 및 지원되지 않는 신뢰할 수 없는 경로를 거부합니다.
- `ecosystem/rumi_default_tools_pack/tools/*/manifest.json`를 다음으로 마이그레이션했습니다.
  코딩/파일/git/터미널 및
  네트워크/브라우저/컴퓨터 도구.
- `tests/test_defaultspack_tool_security.py`에 테스트가 추가되었습니다.

### Docker / 기능 경계

- 엄격한 Docker 정책이 거부되도록 `core_runtime/capability_executor.py`을 업데이트했습니다.
  Docker를 사용할 수 없는 경우 호스트 대체.
- `tests/test_capability_executor_security.py`에 테스트가 추가되었습니다.

### 흐름 런타임 및 채팅 수신

- `ecosystem/defaultspack/domain/flow/engine.py` 확장.
- 다음에 대한 선언적 검증 및 실행 지원이 추가되었습니다.
  - `function`
  - `subflow`
  - `branch`
  - `parallel`
- `ecosystem/defaultspack/flows/chat_turn.flow.yaml`를 표준으로 업데이트했습니다.
  정상적인 채팅 진입.
- `ecosystem/defaultspack/flows/chat_stream_turn.flow.yaml`을 추가했습니다.
- `tests/test_defaultspack_chat_turn_flow_contract.py`의 테스트가 업데이트되었습니다.

### 채팅 지속성

- `ecosystem/defaultspack/blocks/chat/persist_turn.py`을 업데이트하여 지속성을 확보했습니다.
  JSONL이 아닌 정식 `ChatStore` 의미 체계를 따릅니다.
  경로를 추가합니다.
- JSONL 스타일 감사는 정식 메시지 지속성과 별도로 유지되어야 합니다.

### 운송/경로 등록

- 경로를 설명하기 위해 `ecosystem/defaultspack/transport/registry.py`를 업데이트했습니다.
  흐름/기능 사양을 통해.
- `ecosystem/defaultspack/transport/http.py`, `cli.py`, `stdio.py` 업데이트
  보존하면서 표준 흐름/기능 경로를 통해 일반 채팅을 라우팅합니다.
  가능한 경우 공공 계약.
- `ecosystem/defaults/transport/{http,cli,stdio,uds}.py`를 씬으로 변환했습니다.
  호환성 심.
- 경로 테스트를 추가/업데이트했습니다:
  - `tests/test_defaultspack_route_integration.py`
  - `tests/test_defaults_mcp_transport.py`

### 프롬프트

- `ecosystem/defaultspack/domain/prompt/effective.py`을 추가했습니다.
- 프롬프트 로딩/해결이 업데이트되어 효과적인 프롬프트가 소스 체인을 반환합니다.
  그리고 해결된 내용.
- 다음에 대한 발송자 항목이 추가되었습니다.
  - `prompt_validate_template`
  - `prompt_resolve_for_conversation`
- 실행 가능한 프롬프트 로직으로 프롬프트-도구 작성을 비활성화했습니다.
- 패시브/기능 생성을 위한 프롬프트 템플릿/통합 변환 업데이트
  실행 파일 `execution.type = prompt` 대신 Facade 메타데이터.
- 추가된 테스트:
  - `tests/test_defaultspack_prompt_effective.py`
  - `tests/test_defaultspack_prompt_passive.py`

### AI 클라이언트/공급자

- `ecosystem/defaultspack/domain/ai_client/gateway.py`을 추가/업데이트했습니다.
- 채팅/AI 블록을 직접 `AIClient` 대신 `LLMGateway` 방향으로 이동했습니다.
  레거시 Monkeypatch 호환성을 유지하면서 오케스트레이션
  `blocks/chat/send.py`는 게이트웨이 수준 재수출을 통해 이루어집니다.
- `ecosystem/defaultspack/domain/ai_client/providers/__init__.py` 업데이트됨
  매니페스트 우선 OpenAI 호환 공급자 메타데이터입니다.
- `tests/test_defaultspack_provider_manifest_first.py`을 추가했습니다.

### 브라우저 / 컴퓨터 안정성

- 업데이트됨
  `ecosystem/rumi_default_tools_pack/domain/tool/browser_computer.py`를 피하려면
  오래된 공유 선택 창 상태를 재사용하는 사용자 정의 테스트 아티팩트 루트
  `browser_sessions.json`.
- 전체 실행 중에 표시되는 브라우저/컴퓨터 상태 감지 오류가 수정되었습니다.
  파이 테스트 실행.

### 문서

다음에 관한 문서가 업데이트되었습니다.

- 흐름 사양
- 신속한 저작
- 공급자 저작
- 도구 저작
- 운송
- AI 제공자/클라이언트
- 프롬프트/도구 변환

변경된 중요 문서는 다음과 같습니다.

- `docs/flow_spec.md`
- `docs/prompt_authoring.md`
- `docs/provider_authoring.md`
- `ecosystem/defaultspack/docs/ai_client.md`
- `ecosystem/defaultspack/docs/prompt.md`
- `ecosystem/defaultspack/docs/tool-prompt-conversion.md`
- `ecosystem/defaultspack/docs/transport.md`
- `ecosystem/defaultspack/docs/writing-tools.md`

## 확인이 이미 실행되었습니다.

이는 체크포인트 커밋 전에 전달되었습니다.

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_chat_turn_flow_contract.py \
  tests/test_defaultspack_route_integration.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_tool_security.py -q
```

결과: 42명이 합격했습니다.

```bash
cd rumi_ai_1_10
python -m pytest tests/test_*flow*.py tests/test_*route*.py \
  tests/test_defaults_mcp_transport.py \
  tests/test_defaultspack_tool_security.py \
  tests/test_defaultspack_tool_policy.py \
  tests/test_defaultspack_tool_components.py \
  tests/test_defaultspack_tool_executor_rumi_function.py \
  tests/test_defaultspack_external_send_tool.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_prompt_components.py \
  tests/test_defaultspack_provider_expansion.py \
  tests/test_defaultspack_provider_foundation.py \
  tests/test_defaultspack_backend_foundation.py \
  tests/test_capability_executor_security.py -q
```

결과: 403 통과, 기존 경고 1개.

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_agent_service_plan.py -q
```

결과: 182명이 합격했습니다.

```bash
cd rumi_ai_1_10
python -m pytest tests/test_browser_computer_seat_delegation.py \
  tests/test_computer_desktop_action_delegation.py \
  tests/test_computer_move_drag_delegation.py \
  tests/test_defaultspack_agent_service_plan.py::test_computer_click_physical_true_operates_visible_action -q
```

브라우저/컴퓨터 상태 수정 후 결과: 18개를 통과했습니다.

```bash
git diff --check
```

결과: 합격했습니다.

## 전체 테스트 상태

전체 테스트 명령:

```bash
cd rumi_ai_1_10
python -m pytest -q
```

무슨 일이 일어났나요:

1. 브라우저/컴퓨터 상태 수정에 도달하기 전 전체 실행:
   `4373 passed, 19 skipped, 7 failed`.
2. 7번의 실패는 모두 브라우저/컴퓨터 물리적 행동 위임 테스트였습니다.
   오래된 선택 창 상태로 인해 작업이 `executed=False`을 반환했습니다.
3. 상태 수정 사항이 추가되었으며 관련 18개 테스트 하위 집합이 통과되었습니다.
4. 새로운 전체 실행이 시작되었으며 이전에 실패했던 단계를 통과했습니다.
   브라우저/컴퓨터 섹션에 있지만 사용자가 환경 이동을 요청했기 때문에
   완료되기 전에 의도적으로 중지되었습니다.

다음 엔지니어는 깨끗한 프로세스에서 전체 테스트 모음을 다시 실행해야 합니다.

## 즉시 다음 단계

1. 브랜치를 가져와서 체크아웃합니다.

```bash
git fetch origin
git checkout codex/defaultspack-function-flow
cd rumi_ai_1_10
```

2. 전체 테스트를 실행합니다.

```bash
python -m pytest -q
```

3. 오류가 나타나면 체크포인트 아키텍처를 되돌리지 않고 수정합니다.

4. 터치된 부분을 중심으로 집중 테스트를 다시 실행한 후 전체 테스트를 다시 실행합니다.

5. 설계 회귀를 검사합니다.

```bash
rg -n 'execution\\.type.*prompt|"type": "prompt"|type: prompt|execution.*dynamic|execution.*handler' \
  ecosystem/defaultspack docs ecosystem/rumi_default_tools_pack
```

합법적인 프롬프트 구성 요소 메타데이터를 별도로 처리합니다. 실행 가능한 프롬프트 도구
작성 경로로 반환되어서는 안 됩니다.

6. 직접 AI 클라이언트 가져오기를 검사합니다.

```bash
rg -n 'from domain\\.ai_client\\.client import AIClient|from ecosystem\\.defaultspack\\.domain\\.ai_client\\.client import AIClient' \
  ecosystem/defaultspack/blocks ecosystem/defaultspack/domain
```

허용된 레거시/가져오기 호환성 위치만 남아 있어야 합니다.

7. 완료되면 `codex/defaultspack-function-flow`에서 PR 하나를 생성하여
   `master`.

## 최종 PR 승인 기준

- 전체 `python -m pytest -q` 통과 또는 나머지 실패가 명확하게 표시됩니다.
  관련이 없고 문서화되어 있습니다.
- 일반 채팅은 `defaultspack.chat_turn`를 통해 진행됩니다.
- 스트리밍 채팅은 `defaultspack.chat_stream_turn` 또는 이에 상응하는 서비스를 통해 진행됩니다.
  경로 레지스트리 기능/흐름 경로.
- 기존 프런트엔드 HTTP 경로, JSON 셰이프, SSE 이벤트 이름 및 위젯
  모양은 계속 호환됩니다.
- `defaults`은 여전히 호환성 심으로 작동합니다.
- 신뢰할 수 없는 레거시 실행 유형은 작성/실행이 불가능합니다.
- 기능/능력 도구는 위험 노출, 승인 및 승인을 명시합니다.
- 호스트/네트워크/파일/git/브라우저/컴퓨터 액세스는 신뢰할 수 있는 기본값을 통과합니다.
  기능/능력.
- 프롬프트는 수동적으로 유지됩니다. 실행 가능한 프롬프트 도구 작성 경로가 복원되지 않습니다.
- 매니페스트 전용 OpenAI 호환 공급자 추가는 계속 적용됩니다.
- 문서는 런타임 동작과 일치합니다.

## 주의사항

- 교체하지 않는 한 대규모 `defaults` 수송 심 변경 사항을 되돌리지 마십시오.
  동등한 경로 등록 위임을 사용합니다.
- `execution.type = prompt`를 실행 가능한 도구 경로로 다시 도입하지 마십시오.
- `write_action`을 허가 결정으로 의존하지 마십시오. 메타데이터입니다.
- Docker 엄격 모드를 자동으로 호스트 실행으로 대체하지 마세요.
- macOS에서는 브라우저/컴퓨터 테스트에 주의하세요. 공유됨
  `browser_sessions.json`은 테스트 사이에 선택된 창 상태를 유지할 수 있습니다.
- 사용자가 명시적으로 분할을 요청하지 않는 한 이를 하나의 PR로 유지합니다.
