<!-- docs-i18n-links:start -->
[EN](../../defaultspack_extension_migration_plan.md) | [JP](../ja/defaultspack_extension_migration_plan.md) | [KR](./defaultspack_extension_migration_plan.md) | [CN](../zh-cn/defaultspack_extension_migration_plan.md)
<!-- docs-i18n-links:end -->

# defaultspack Extension Migration Plan (PR 통합 버전)

## 배경 및 목적

defaultspack 에는, 이하의 집중 구현이 남아 있다.

- LLM 공급자 / 모델의 중앙 정의 (`domain/ai_client/providers/__init__.py` 및 `model_profiles.py`)
- prompt / tool / knowledge / transport 중복 관리 경로
- `transport/http.py`의 거대한 fallback 루트 테이블

본 변경에서는 **manifest 구동 + 파일 드롭 확장**을 기반으로 하여 호환성을 유지한 채 단계 이행할 수 있는 토대를 만든다.

## 구현 정책 (이 PR에서 완료 할 범위)

1. 확장 범주를 고정 문자열로 정의하고 범주별 discovery 규칙을 명시합니다.
2. manifest 검증과 extension registry 를 추가해 중앙 하드 코드로부터의 탈각을 개시한다.
3. LLM 공급자 / 모델은 extension manifest 우선으로로드되고 기존 로직은 호환 fallback으로 남아 있습니다.
4. OpenRouter에는 정적 목록이 없으며 API 동기화 + 캐시 + fallback으로 처리합니다.
5. prompt / tool / knowledge / transport는 기존 manager를 깨지 않고 extension registry 측을 1차 소스에 옮긴다.
6. 기존 API/호출 시그니처(`AIClient.complete(model, messages, tools, params)`)는 유지한다.

## 확장 카테고리(foundation)

- `llm_provider`
- `llm_model`
- `prompt`
- `tool`
- `chat_mode`
- `agent_mode`
- `knowledge_backend`
- `transport`
- `ui_surface`
- `policy`

## 디렉토리 약관

```text
ecosystem/defaultspack/extensions/
  llm/providers/<provider_id>/manifest.json
  llm/providers/<provider_id>/models/*.json
  prompts/<prompt_id>/manifest.json
  tools/<tool_id>/manifest.json
  chat_modes/<mode_id>/manifest.json
  agent_modes/<mode_id>/manifest.json
  knowledge_backends/<backend_id>/manifest.json
  transports/<transport_id>/manifest.json
  ui/<surface_id>/manifest.json
  policies/<policy_id>/manifest.json
```

## Detailed TODO(수락 기준 포함)

### A. Foundation

- [x] A1: 작업 브랜치 만들기
  - 수락: `codex/defaultspack-extension-refactor`에서 작업하기
- [x] A2: defaultspack 주요 테스트 기준선 확인
  - 수락: extension 추가 후에도 phase5 테스트는 유지된다
- [x] A3: 이 migration plan 추가
  - 수락 : 목적, 범위, 카테고리, 호환 정책, TODO가 명시됩니다.
- [x] A4: Extension discovery / manifest validation / registry 구현
  - 수락 : 카테고리별로 manifest를 감지하고 유효성 검사 오류를 얻을 수 있습니다.
- [ ] A5: legacy import path 와 canonical package path 의 이중화를 해소
  - 수락 : manifest entrypoint 읽기에서 `domain.*`와 `ecosystem.defaultspack.*`이 충돌하지 않음

### B. LLM / Provider 마이그레이션 (호환 유지)

- [] B1 : `domain.ai_client.providers.__init__`을 extension manifest 구동으로 대체
  - 수락: 중앙 `_PROVIDER_REGISTRY` 의존성이 제거됨
- [ ] B2: OpenAI 호환 generic adapter 추가
  - 수락 : manifest의 env / base_url 설정만으로 provider를 추가 할 수 있습니다.
- [ ] B3: OpenRouter provider 추가(동적 모델 동기화)
  - 수락 : 하드 코드 모델 목록 없음, `GET /api/v1/models` 동기화 + 캐시 + fallback 이동
- [ ] B4 : 기본 모델 선택을 manifest / model metadata 기반으로 마이그레이션
  - 수락 : stale 고정 값에 의존하지 않습니다 (예 : OpenAI는 `gpt-5.4`, Anthropic은 Claude 4.6 계, Google은 Gemini 2.5 계)
- [ ] B5 : OpenAI / Anthropic / Google의 modern catalog를 manifest 쪽으로 옮기기
  - 수락 : `ProfileLoader`의 default / fast / large / embedding이 registry 시작점에서 결정됩니다.
- [ ] B6: OpenRouter와 generic OpenAI-compatible 분리
  - 수락 : OpenRouter 고유 동기 로직과 generic endpoint adapter가 별도 구현

### C. Prompt / Tool / Knowledge / Transport 연결

- [] C1 : prompt registry를 PromptManager에 연결
  - 수락 : extension prompt가 list / get / render 할 수 있으며 user_data prompt 편집은 계속됩니다.
- [] C2 : tool registry를 ToolRegistry에 연결
  - 수락 : built-in tool은 manifest 시작점에서 읽히고 dynamic tool CRUD는 계속됩니다.
- [ ] C3: knowledge backend manifest를 backend registry에 연결
  - 수락 : entrypoint에서 backend를 생성 할 수 있습니다.
- [] C4 : chat_mode / agent_mode runner를 entrypoint 해결 가능하게 만들기
  - 수락 : mode manifest가 runner 호출의 시작점이됩니다.
- [] C5 : transport / http.py의 fallback 라우트 테이블 외출
- 수락 : 루트 정의가 transport registry module 쪽으로 향하고 `http.py`는 dispatcher 중심입니다.
- [ ] C6: prompt / tool / chat_mode / agent_mode / knowledge_backend / transport / ui / policy 의 manifest 병아리 완성
  - 수락 : discovery 결과에 모든 카테고리가 나타난다

### D. 테스트

- [ ] D1: manifest validation 테스트
  - 수락 : 필수 항목 누락 및 카테고리 불일치 감지
- [ ] D2: extension discovery 테스트
  - 수락: 모든 카테고리가 감지됨
- [ ] D3: provider/model loading 테스트
  - 수락: manifest 구동의 provider 검출·model 우선 해결이 움직인다
- [ ] D4: OpenRouter 동기화/캐시 테스트
  - 수락: API 성공 시 캐시 업데이트, API 실패 시 캐시 fallback
- [ ] D5: PromptManager / ToolRegistry extension 연결 테스트
  - 수락 : extension의 prompt / tool이 기존 API에서 보입니다.
- [ ] D6: transport route registration 테스트
  - 수락: fallback route 정의가 registry module 로부터 구축된다
- [ ] D7: legacy shim removal 테스트
  - 수락: `prompt.prompt_loader` / `tool.tool_loader` 호환 import가 불가능

## 호환 정책

- API surface는 유지한다 (`AIClient` 호출 시그니처는 변경하지 않는다).
- extension 미배치시는 fail-soft 로 기존 거동으로 폴백한다.
- `transport/http.py`의 fallback 라우트 테이블은 호환 용도로 남겨두지만, 정의 그 자체는 registry module측에 향한다.
- top-level `prompt.*` / `tool.*` legacy shims have been removed; use defaultspack registries and functions.

## 전제와 가정

- `ecosystem/defaultspack`를 refactor 대상으로 하고 `ecosystem/defaults`은 이 PR에서는 비대상.
- OpenRouter의 모델 취득은 `/models` 엔드포인트를 1차 소스로 해, 네트워크 불가시는 로컬 캐쉬를 사용한다.
- provider 추가는 「manifest 추가 + 필요하면 adapter 지정」으로 성립하도록 한다.

## Current Status

- discovery / registry / basic manifests 추가됨
- provider migration 은 도중에 package import path 의 정규화와 model metadata 의 목적지 정리가 필요
- prompt / tool / transport는 병아리가 추가되었지만 기존 manager / route table에 대한 연결이 완료되지 않았습니다.
- setup pack selection이 있는 환경에서는 backend/frontend extension discovery
  `defaultspack` 및 선택된 target pack으로 좁혀진다. selection이 없는 개발 환경에서는
  호환을 위해 모든 sibling pack 로드
- Copilot 변경에는 호환 shim 삭제가 포함되어 있었으므로, 이 PR에서는 shim 을 되돌려서 호환 우선으로 한다
## Local-first completion status

This PR fixes the local-first runtime baseline without moving Cloudflare,
Supabase, login, account creation, or user management into defaultspack scope.

Completed in this slice:

- canonical implementation is `rumi_ai_1_10/ecosystem/defaultspack/`;
- old `defaults.*` compatibility should delegate to defaultspack behavior rather
  than becoming a second source of truth;
- `stub/default` is the guaranteed no-key model default;
- cloud provider auto-registration is opt-in through
  `RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS`;
- local providers are treated as no-key providers in backend and frontend
  catalogs;
- sensitive coding HTTP routes pass the local guard;
- write/delete/patch/restore, terminal medium/high-risk execution, git commit,
  and git push require signed one-time approval tokens;
- 승인 토큰은 작업 및 인수 해시에 바인딩됩니다.
- 로컬 작업 시도 및 결과는 수정된 JSONL 감사 로그에 기록됩니다.
- 프런트엔드 모델 폴백 및 선택적 작업 - 회사 호출은 카탈로그입니다.
  구동;
- `scripts/quality/scan_defaultspack_integrity.py --strict`는 경로/블록을 확인합니다.
  패리티, 프런트엔드/백엔드 경로 패리티, 로컬 우선 기본값, 민감한 경로
  가드 배선 및 새로운 안전 모듈의 구문.

남은 확장 작업은 매니페스트 중심으로 유지되어야 하며 추가를 피해야 합니다.
클라우드는 기본적으로 새로운 로컬 런타임으로 다시 돌아갑니다.
