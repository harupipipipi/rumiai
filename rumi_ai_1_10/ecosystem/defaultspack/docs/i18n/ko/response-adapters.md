<!-- docs-i18n-links:start -->
[EN](../../response-adapters.md) | [JP](../ja/response-adapters.md) | [KR](./response-adapters.md) | [CN](../zh-cn/response-adapters.md)
<!-- docs-i18n-links:end -->

# 응답 어댑터

응답 어댑터는 Rumi 출력을 공급자별 응답으로 변환합니다. 그들은
외부 입력 프레임워크의 아웃바운드 절반입니다.

```text
runtime result
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponsePlan
  -> ResponseAdapter
  -> provider API or HTTP response
```

런타임은 Slack에 게시하는 방법, LINE 응답 토큰을 사용하는 방법, 또는
Discord 상호작용 응답 형식을 지정하세요. 공급자 중립을 반환해야 합니다.
결과적으로 기획자가 적응할 수 있습니다.

## 응답 플래너

`ResponsePlanner`은 런타임 결과에 어떤 일이 발생해야 하는지 결정합니다.

- `reply_text`: 보조 텍스트를 소스로 다시 보냅니다.
- `store_only`: 외부 응답 없이 채팅 결과를 유지합니다.
- `summarize_then_reply`: 짧은 요약을 보냅니다.
- `run_browser_use`, `run_computer_use`, `run_python`, `run_tool`: 생성
  직접적인 실행이 아닌 후속 조치 계획;
- `send_file_if_allowed`: 기능 검사 후 정상적인 파일 계획을 허용합니다.
- `ask_for_approval`: 승인이 필요한 계획에서 중지합니다.

기획자는 신속한 결정, 공급자 제한, 이벤트 대상 및
런타임 출력 메타데이터. 공급자 길이 제한, 파일 제한 및 민감도
신속한 결정 후에도 점검이 계속 이루어집니다.

출력 프로필은 입력 프로필에 대응하는 아웃바운드 프로필입니다. 내장
프로필에는 LINE 답장/푸시, Discord 봇 채널 메시지, Discord 웹훅이 포함됩니다.
URL, Slack 채널/스레드 메시지, 일반 웹훅 콜백 및 로컬 웹
출력. 사용자 정의 프로필은 `user_data/shared/output_profiles`에 배치할 수 있습니다.
내장된 LINE/Discord/Slack 출력의 경우 의도적으로 복사-붙여넣기 플러스로 설정됩니다.
선택: 출력 템플릿/프로필을 선택하고 비밀이 아닌 대상 ID를 붙여넣습니다.
UI를 사용하고 봇 토큰 또는 웹훅 URL을 마스크된 외부 토큰으로 저장합니다. 임의
발신자 및 자유 형식 프롬프트 지침은 사용자 정의 아래에 있습니다.

Discord는 운영 모델이 다음과 같기 때문에 두 개의 내장 출력 템플릿을 노출합니다.
다르다:

- `discord.output.bot_channel`: 로컬 Rumi 런타임은 Discord Bot 토큰을 사용합니다.
  그리고 목표 `channel_id`.
- `discord.output.webhook`: Rumi는 채널 Webhook URL을 통해 게시하고
  해당 출력 경로에는 봇 토큰이 필요하지 않습니다.

두 경로 모두 여전히 대응 계획을 통과하고 `allowed_mentions`를 안전하게 유지합니다.
기본적으로.

## 응답 프롬프트 정책

`response_prompt`은 신속한 전달 계획 정책입니다. 이벤트를 검사할 수도 있고,
텍스트와 런타임 결과를 입력한 다음 다음에 대한 `plan_only` 결정을 반환합니다.
`ResponsePlanner`. 그러나 도구를 실행하거나 공급자 API를 직접 호출해서는 안 됩니다.
실행 가능한 단계는 추후 기존 도구 정책을 통해 생성되며,
승인, 턴 러너 및 응답 어댑터 경로.

정책 필드는 `schemas/response_prompt_policy.schema.yaml`에 정의되어 있습니다.

- `allowed_actions`: 프롬프트가 표시할 수 있는 유일한 `ResponsePlan.action` 값
  반환;
- `tools`: 계획 컨텍스트에 대한 도구 가시성 및 승인 요구 사항;
- `output_schema`: 즉각적인 결정의 예상되는 구조화된 형태;
- `allowed_outputs`: 프롬프트가 표시할 수 있는 선택적 출력 프로필 ID 또는 공급자
  목표;
- `fallback`: 프롬프트 출력이 유효하지 않거나 유효하지 않을 때 사용할 안전한 조치
  거부됨;
- `sensitivity`: 가시성 기본값 및 외부 전달 제약.

`allowed_actions`에 나열되지 않은 조치에 대한 결정은 거부되어야 합니다.
`fallback`를 통해 처리됩니다.

예:

```yaml
response_prompt:
  enabled: true
  model: inherit
  mode: plan_only
  allowed_actions:
    - reply_text
    - store_only
    - run_browser_use
    - run_python
  tools:
    browser_use:
      enabled: true
      requires_approval: false
    python:
      enabled: true
      requires_approval: false
      sandbox: true
    external_send:
      enabled: true
      requires_approval: true
  system_prompt: |
    Decide how Rumi should respond. Use browser_use only when current
    external information is needed. Return strict JSON.
  user_prompt: |
    Provider: ${event.provider}
    Scope: ${event.scope.type}:${event.scope.id}
    Actor: ${event.actor.id}
    User input: ${input.text}
    Assistant result: ${response.text}
```

공급자 간 작업의 경우 프롬프트는 다음과 같은 계획을 반환해야 합니다.
`run_tool`와 `tool: external_send`. 해당 도구는 승인이 필요하며 다음을 사용합니다.
일반 응답과 동일한 LINE, Discord, Slack 및 일반 웹훅 어댑터
배달. 프롬프트는 원시 봇 토큰이나 웹훅 비밀을 수신하지 않습니다.

## 대응 계획

계획 예시:

```json
{
  "provider": "discord",
  "messages": [
    {
      "type": "text",
      "text": "Here is the summary..."
    }
  ],
  "metadata": {
    "response_prompt_decision": {
      "action": "reply_text",
      "sensitivity": "public"
    },
    "response_action_plan": {
      "type": "reply",
      "external_reply": true
    }
  }
}
```

대상에는 공급자 식별자가 포함될 수 있지만 원시 인증 값은 포함될 수 없습니다. 모두
단기 응답 핸들은 내부 참조로 전달되어 해결되어야 합니다.
어댑터 내부.

## 어댑터 책임

`ResponseAdapter`는 다음을 담당합니다.

- 제공자별 메시지 모양을 렌더링합니다.
- 공급자 길이 제한을 시행합니다.
- 정책이 허용하지 않는 한 대량 언급을 피합니다.
- 활성 응답 프롬프트 정책 이외의 작업을 거부합니다.
- 외부 응답 전에 민감도와 기능을 다시 확인합니다.
- 비밀 저장소의 비밀 참조를 해결합니다.
- 호출 제공자 API;
- 수정된 배송 상태를 반환합니다.
- 공급자 오류를 안정적인 프레임워크 오류로 매핑합니다.

어댑터는 동기식이거나 비동기식일 수 있습니다. 공급자가 빠른 HTTP 응답을 요구하는 경우
웹후크 핸들러는 어댑터가 나중에 보내는 동안 ack를 반환할 수 있습니다.

## 내장 어댑터 대상

| 어댑터 | 납품대상 |
|---|---|
| §루미§0§ | 옵션 `thread_ts`가 포함된 Slack `chat.postMessage` |
| §루미§0§ | 단기 응답 토큰 참조를 사용하는 LINE 응답 API |
| §루미§0§ | Discord 상호작용 응답 본문 |
| §루미§0§ | Discord 채널 메시지 API |
| §루미§0§ | Discord 웹훅 URL |
| §루미§0§ | 일반 JSON 응답 또는 콜백 URL |
| §루미§0§ | 도구 지원 LINE/Discord/Slack/일반 승인 후 보내기 |

어댑터 ID는 채팅 핸들러가 아닌 `InputProfile`에 의해 선택됩니다.

## 오류 동작

공개 채널은 프로필이 허용하는 경우에만 안전하고 짧은 오류를 수신해야 합니다.
그 행동. 자세한 공급자 오류는 수정된 로그 또는 전달에 속합니다.
상태이며 채널 응답에는 없습니다.

예:

| 조건 | 권장 조치 |
|---|---|
| 아웃바운드 토큰 누락 | 원시 비밀 없이 수정된 배달 오류 |
| 공급자 비율 제한 | `store_only` 또는 제공업체별 지연 처리 |
| 메시지가 너무 깁니다 | 일반 플래너 청킹 |
| 계획 이후 거부된 정책 | §루미§0§ |

## 안전 규칙

응답 프롬프트 정책은 작업 경계에서 기본적으로 거부됩니다.

- `computer_use`은 기본적으로 명시적인 승인이 필요합니다.
계획 맥락.
- `allowed_actions` 이외의 계획은 어댑터 배송 전에 거부됩니다.
- `browser_use`은 활성 네트워크 정책을 존중해야 합니다.
- `python` 후속 계획은 샌드박스/로컬 전용 기대치를 선언해야 합니다.
- 외부 응답 전에 어댑터 경로는 `sensitivity` 및 현재를 다시 확인합니다.
  오래된 프롬프트 출력이 로컬 전용 또는 비밀 콘텐츠를 유출할 수 없도록 하는 기능입니다.
