<!-- docs-i18n-links:start -->
[EN](../../external-inputs.md) | [JP](../ja/external-inputs.md) | [KR](./external-inputs.md) | [CN](../zh-cn/external-inputs.md)
<!-- docs-i18n-links:end -->

# 외부 입력

외부 입력은 로컬 UI 외부의 시스템에서 Rumi로 들어오는 메시지입니다.
웹후크, 채팅 플랫폼, 자동화 콜백, 터널, 로컬 스크립트 또는
미래의 커넥터. 모두 동일한 프레임워크 경계를 사용합니다.

```text
provider payload
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> dispatch_input / submit_input
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponseAdapter
```

목표는 공급자 세부 정보를 엣지에 유지하는 것입니다. 채팅, 에이전트 및 흐름 논리
Slack, Discord, LINE 또는 터널별 입력이 아닌 정규화된 입력을 받아야 합니다.
페이로드.

## 핵심 유형

`ExternalEvent`은 정규화된 인바운드 레코드입니다. 여기에는 안정적인 필드가 포함되어 있습니다.
§루미§0§, §루미§1§, §루미§2§, §루미§3§, §루미§4§, §루미§5§, §루미§6§,
`verified`, `metadata` 수정. 공급자별 식별자가 흡수됩니다.
그 교장들에게. 원시 요청 본문은 서명 확인에 사용될 수 있지만
원시 비밀과 토큰 값은 반환된 이벤트 객체에 노출되지 않습니다.
UI, 로그 또는 문서.

`AudiencePolicy`는 이벤트에 대한 루미 입장 허용 여부를 결정합니다. 정책은
제공자별 게이트, 팀, 채널, 사용자, 멘션 스타일, 다이렉트 메시지 상태,
속도 제한 또는 필수 확인이 필요합니다. 정책 출력이 명시적입니다: `allow`,
`ignore`, `deny` 또는 `needs_approval`.

`InputProfile`는 허용된 이벤트를 `RumiInputEnvelope`에 매핑합니다: 역할, 입력 텍스트,
외부 키/제목/모델, 소스 메타데이터, 매개변수 및 도구를 채팅합니다. 수행합니다
변신만;; 이벤트가 허용되는지 여부는 결정되지 않습니다.

입력과 출력 구성은 별개입니다. 입력 프로필은 "무슨 일이 있었나요?"라고 대답합니다.
어떻게 채팅에 들어가야 하나요?". 출력 프로필은 "어디서 응답할 수 있나요?"라고 대답합니다.
어떤 교통수단을 통해 가나요?". LINE용 내장 입력 템플릿이 있습니다.
Discord, Slack 및 일반 웹훅; 사용자 정의 템플릿은 다음을 통해 등록할 수 있습니다.
`/api/external/templates` 또는 `user_data/shared/external_io_templates`에 배치됩니다.
내장 템플릿은 `setup_mode: copy_paste_select`을 노출합니다: UI 렌더링
템플릿/프로필/공급자 선택과 복사 가능한 경로 경로 및 붙여넣기 전용 토큰
또는 대상 필드. 자유 형식 YAML/프로필 편집은 Custom에 속합니다.
LINE, Slack, Discord 상호작용과 같은 웹훅 제공업체의 경우
외부 입력 패널에는 임시 공개 URL 실행 프로그램이 포함되어 있습니다. 클라우드플레어
빠른 터널 버튼은 선택한 경로 경로에 대한 임시 공개 URL을 생성합니다.
예를 들어 `/api/integrations/line/webhook`이므로 사용자는 전체 URL을 붙여넣을 수 있습니다.
공급자 대시보드로 이동합니다.

`submit_input`은 프로필 변환 후의 호환성 진입점입니다.
내부적으로는 이제 `dispatch_input`로 전달됩니다.
`RumiInputEnvelope` by `delivery.action_id`.

`ResponsePlanner`은 런타임 결과를 공급자 중립적 응답으로 변환합니다.
계획. 응답할 것인지, 승인만 할 것인지, 연기할 것인지, 분할할 것인지, 잘라낼 것인지를 결정합니다.
건너 뛰십시오.

`ResponsePromptPolicy`은 플래너 이전의 선택적 계획 전용 레이어입니다.
`reply_text`, `store_only`, `run_browser_use`와 같은 작업을 선택할 수 있습니다.
`run_python` 또는 `ask_for_approval`이지만 결정 개체만 반환합니다.
도구 실행은 여전히 일반적인 도구 정책, 승인 및 차례를 거칩니다.
주자 경로.

`ResponseAdapter`는 특정 제공업체를 통해 해당 계획을 렌더링하고 전달합니다.
Slack 스레드, LINE 응답 토큰, Discord 상호작용 응답,
또는 일반 웹훅 응답.

기본 입력 템플릿은 `include_source_context: true`으로 설정됩니다. 루미가 차례를 알려준다
이전에 LINE, Discord, Slack 또는 다른 제공업체로부터 입력이 제공된 러너
프롬프트에서 원시 토큰과 요청 비밀을 유지하면서 사용자의 텍스트를 삭제합니다.

## 이벤트 계약

정규화된 이벤트 예:

```json
{
  "provider": "line",
  "workspace": {
    "type": "line_destination",
    "id": "destination-id"
  },
  "scope": {
    "type": "group",
    "id": "C123"
  },
  "actor": {
    "type": "user",
    "id": "U123"
  },
  "conversation": {
    "type": "external",
    "id": "line:group:C123"
  },
  "event": {
    "id": "evt_01",
    "message_id": "msg_01",
    "type": "message",
    "message_type": "text"
  },
  "payload": {
    "type": "message"
  },
  "verified": true,
  "metadata": {
    "reply_token": "short-lived-provider-handle"
  }
}
```

단기 공급자 응답 핸들은 어댑터 사용을 위해 메타데이터에 보관됩니다. 그들은
오랫동안 구성된 토큰으로 처리되거나 UI에 다시 표시되어서는 안 됩니다.

## 처리 규칙

1. 신뢰에 민감한 필드를 구문 분석하기 전에 요청을 확인하십시오.
2. 공급자 페이로드를 `ExternalEvent`으로 정규화합니다.
3. `provider + event_id`을 사용하여 중복 항목을 삭제합니다.
4. `AudiencePolicy`를 평가합니다.
5. `InputProfile`를 선택합니다.
6. `submit_input`에 전화하세요.
7. 선택적으로 `ResponsePromptPolicy`을 실행하여 안전한 조치 결정을 내립니다.
8. `ResponsePlanner`을 실행합니다.
9. `ResponseAdapter`을 통해 배송하세요.

어떤 단계에서든 이벤트를 거부하면 어댑터는 공급자가 예상한 결과를 반환해야 합니다.
채팅 메시지를 작성하지 않고 승인합니다.

즉각적인 대응 조치는 계획 전용입니다. `response_prompt`가 반환될 수 있습니다.
`ResponsePlan` 결정이 내려졌지만 외부 전달은 여전히
작업, 민감도, 기능 및 승인이 허용되는 어댑터 경로
요구사항을 다시 확인합니다.

## 로컬 첫 번째 경계

외부 입력 지원은 기본적으로 로컬 런타임을 공개하지 않습니다. 는
명시적으로 구성하지 않는 한 게이트웨이 및 HTTP 전송이 루프백에 바인딩됩니다.
그렇지 않으면 허용됩니다. 공개 URL 제공자는 교체 가능한 엣지 구성요소일 뿐입니다.
Cloudflare Quick Tunnel은 개발 중에 사용할 수 있지만 개발의 일부는 아닙니다.
핵심 아키텍처이며 다른 터널과 교체 가능한 상태로 유지되어야 합니다.
프록시 또는 플랫폼 수신.

## 내장 설정 형태

기본 제공 UI는 의도적으로 YAML 편집기가 아닌 안내 설정입니다.

- `External Input`: 공급자/템플릿/프로필을 선택하고, 생성하거나 복사합니다.
  웹훅 URL을 선택한 다음 기본 응답 동작을 선택하세요.
- `External Output`: 전송 모드 및 출력 템플릿을 선택하고 마스크 붙여넣기
  외부 토큰을 사용하고 Discord `channel_id`와 같은 비밀이 아닌 대상 ID를 붙여넣습니다.
- `External Custom`: 사용자 정의 템플릿/프로필을 등록하거나 삭제하고 유지합니다.
  컴퓨터 사용 브라우저 워크플로와 같은 자유 형식 응답 프롬프트.

LINE은 공급자가 생성한 웹훅 URL과 `Channel Secret` 확인을 사용하고
`Channel Access Token`가 답변합니다. Discord에는 두 가지 아웃바운드 모드가 있습니다: `Bot + Channel`
봇 토큰과 `channel_id`를 사용하고 `Webhook URL`은 채널 웹훅을 사용합니다.
마스킹된 외부 토큰인 URL입니다. Slack은 이벤트 요청 URL, 서명을 사용합니다.
비밀, 봇 토큰 및 스레드 인식 `chat.postMessage`.

## 안전 참고사항

- Webhook 엔드포인트 관리 및 공개 URL 생성 경로는 다음과 같이 처리됩니다.
  로컬 관리자의 민감한 경로이며 로컬 인증 가드가 필요합니다.
- 외부 인바운드 웹훅 경로는 외부에서 연결 가능한 상태로 유지되지만 각 엔드포인트는
  공급자 서명 또는 공유 비밀 확인을 시행할 것으로 예상됩니다.
- 새로 생성된 일반 웹훅 엔드포인트는 기본적으로 비활성화 + shared_secret으로 설정됩니다.
  달리 명시적으로 구성하지 않는 한.
- Cloudflare Quick Tunnel은 교체 가능한 공용 URL 공급자일 뿐입니다. 그것은 아니다
  보안 경계; 엔드포인트 보안 및 로컬 관리자 경로 가드는 그대로 유지됩니다.
  필수.

## 알려진 제한 사항

- 이 PR에 사용된 LINE 및 Discord 어댑터는 MVP 텍스트 응답 어댑터입니다.
  완전한 생산 봇 구현.
- LINE 비문자 메시지는 현재 자리 표시자 텍스트로 정규화됩니다.
- Discord 상호작용 처리는 의도적으로 최소화됩니다. 완전 연기/후속 조치
  상호 작용 행동은 후속 PR에서 처리되어야 합니다.
- Cloudflare Quick Tunnel은 교체 가능한 공용 URL 공급자일 뿐입니다. 그러면 안된다
  보안 경계로 간주됩니다. 엔드포인트 보안 및 로컬 관리자 경로
  경비원은 여전히 ​​필요합니다.

## 현재 Defaultspack 경로

현재 통합 경로는 수렴해야 하는 공급자별 어댑터입니다.
위의 프레임워크 경계에서:

| 경로 | 목적 |
|---|---|
| §루미§0§ | Slack 이벤트 API 섭취 |
| §루미§0§ | LINE Messaging API 웹훅 수신 |
| §루미§0§ | Discord 상호작용 섭취 |
| §루미§0§ | 디스코드 메시지 이벤트 접수 |
| §루미§0§ | 비밀 상태만 |
| §루미§0§ | 쓰기 전용 비밀 설정 또는 지우기 |
| §루미§0§ | API 키와 유사한 외부 토큰 상태 |
| §루미§0§ | 명명된 외부 토큰 업데이트, 이름 바꾸기 또는 삭제 |
| §루미§0§ | 기본 제공 및 사용자 정의 입력/출력 템플릿 나열 |
| §루미§0§ | 사용자 정의 입력 또는 출력 템플릿 등록 |
| §루미§0§ | 일반 웹훅 섭취 |
| §루미§0§ | 웹훅 엔드포인트 구성 나열 |

## 로컬호스트 입력 엔드포인트

AI가 생성한 인바운드 엔드포인트는 `input_endpoint_create`을 사용하고 반환만 수행합니다.
로컬호스트 URL:

```text
http://localhost:{port}/api/webhooks/inbound/{endpoint_id}
```

이러한 엔드포인트에는 공유 비밀 및 기본 TTL 보호가 필요합니다. 공개
Cloudflare 또는 터널 URL은 별도의 문제로 남아 있습니다.
