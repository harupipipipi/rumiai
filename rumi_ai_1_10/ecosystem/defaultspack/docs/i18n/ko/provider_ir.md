<!-- docs-i18n-links:start -->
[EN](../../provider_ir.md) | [JP](../ja/provider_ir.md) | [KR](./provider_ir.md) | [CN](../zh-cn/provider_ir.md)
<!-- docs-i18n-links:end -->

# 제공자 IR

Rumi Chat IR v2는 ChatStore와 공급자 간의 공급자 중립적 계약입니다.
어댑터. 이를 통해 defaultspack은 레거시보다 풍부한 채팅 상태를 유지할 수 있습니다.
기존 공개 API를 안정적으로 유지하면서 OpenAI 같은 StandardMessage 형식입니다.

## 저장소 경계

ChatStore는 공급자에 구애받지 않습니다. Rumi 메시지와 작업 공간을 저장합니다.
공급자 페이로드가 아닌 아티팩트. 저장된 메시지는 다음을 통해 변환됩니다.

```text
stored_messages_to_ir(conversation_id, messages)
ir_to_legacy_standard_messages(ir)
legacy_standard_messages_to_ir(messages)
ir_to_stored_messages(ir)
```

`convert_to_standard()`은 여전히 존재하며 IR을 통해 위임하므로 기존 발신자가 볼 수 있습니다.
동일한 StandardMessage 출력.

## 루미채팅 IR v2

IR 객체는 명시적인 `schema_version` 필드를 전달합니다. 핵심 모델에는 다음이 포함됩니다.
§루미§0§, §루미§1§, §루미§2§, §루미§3§,
§루미§0§, §루미§1§, §루미§2§, §루미§3§,
`ProviderWarning`, `DroppedFeature`, `BridgeAction`.

지원되는 블록 유형에는 텍스트, 이미지, 오디오, 비디오, 파일, PDF, 도구 호출,
도구 결과, 추론, 인용, 사건, 거부 및 알 수 없음. 알 수 없는 블록
보존됩니다. 추론 블록은 기본적으로 내부적이며 삽입되지 않습니다.
모델 표시로 표시되지 않는 한 프롬프트로 표시됩니다.

## 기능 및 계획

공급자 매니페스트는 `domain/ai_client/capabilities/manifests/`에 게시되어 있습니다. 는
레지스트리는 매니페스트 기본값, 런타임 모델 메타데이터 및 다음과 같은 특징을 병합합니다.
토큰 매개변수 이름, 추론 동작, 도구 이름 규칙, 시스템 역할 매핑,
스트림 사용 지원, 공급자 파일 ID, 내장 도구 및 MCP 도구.

요청 플래너는 자동으로 기능을 삭제하는 대신 성능 저하를 기록합니다.

- 지원되지 않는 개발자 역할: 레이블이 지정된 섹션을 사용하여 시스템에 병합합니다.
- 지원되지 않는 시스템 역할: 첫 번째 사용자 메시지에 보호된 접두사를 삽입합니다.
- 지원되지 않는 추론: 추론 매개변수를 비활성화하고 삭제된 기능을 기록합니다.
- 지원되지 않는 이미지/PDF/오디오/파일 업로드: 브리지 작업 또는 경고 생성
- 지원되지 않는 제공자 도구: 제공자 도구를 생략하고 요청된 도구를 기록합니다.
- 지원되지 않는 병렬 도구 호출: 도구 루프를 직렬화합니다.
- 지원되지 않는 엄격한 JSON 스키마: 최선의 JSON으로 다운그레이드합니다.
- 잘못된 공급자 도구 이름: 도구 프로토콜 v2를 통한 별칭입니다.

## 공급자 컴파일러

Provider Compiler v2는 계획된 요청을 공급자 페이로드로 컴파일하고 구문 분석합니다.
Rumi 응답 IR로 다시 응답합니다. 구현된 컴파일러 제품군은 다음과 같습니다.

- OpenAI 채팅;
- OpenAI 응답;
- OpenAI 호환;
- Google OpenAI 호환;
- Google 네이티브 생성 API;
- 인류학적 메시지;
- 베드락 컨버스;
- 로컬 OpenAI와 호환됩니다.

컴파일러 경로는 보호됩니다. `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`를 사용하여
선택하세요. 강제 롤백하려면 `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`를 사용하세요.

## 도구 프로토콜 v2

Rumi 도구 정의와 공급자 도구 정의는 별개입니다. 프로토콜
원래 이름과 공급자 별칭을 추적하고 공급자 도구 호출을 다시 디코딩합니다.
Rumi 도구는 도구 결과를 IR 블록으로 호출하고 인코딩합니다. 도구 결과에는 다음이 포함될 수 있습니다.
텍스트, JSON, 이미지, 파일, 아티팩트, 승인이 필요한 상태 및 잘림
대규모 출력을 위한 메타데이터.

## 첨부파일/파일 v2

첨부 파일은 레거시 `workspace_attachments` 메타데이터 형태를 유지하는 동시에
대화 작업 영역 아래에 첨부 파일 v2 매니페스트를 작성합니다. 첨부파일
레코드에는 ID, 이름, MIME 유형, 크기, 작업공간 경로, 소스 필드,
표현, 제공자 참조 및 생성 시간. 원시 거대 데이터 URL은 그렇지 않습니다.
피할 수 있는 경우 기록 메타데이터에 저장됩니다.

## 공급자 추적

추적 아티팩트는 다음 위치에 기록됩니다.

```text
user_data/shared/chat/conversations/<conversation_id>/workspace/provider_traces/
```

여기에는 스키마 버전, 요청 ID, 공급자, 모델, API 제품군, IR 스키마,
기능 요약, 메타데이터 계획, 삭제된 기능, 브리지 작업,
경고, 삭제된 페이로드, 응답 요약 및 타임스탬프. API 키,
인증 헤더, 토큰, 자격 증명, 비밀번호, 비밀 및 이미지 base64
페이로드가 수정되었습니다.
