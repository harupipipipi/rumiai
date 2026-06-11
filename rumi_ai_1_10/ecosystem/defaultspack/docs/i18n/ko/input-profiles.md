<!-- docs-i18n-links:start -->
[EN](../../input-profiles.md) | [JP](../ja/input-profiles.md) | [KR](./input-profiles.md) | [CN](../zh-cn/input-profiles.md)
<!-- docs-i18n-links:end -->

# 입력 프로필

`InputProfile`은 허용된 `ExternalEvent`이 런타임 입력이 되는 방법을 설명합니다.
이는 외부 청중의 맥락과 루미 행동 사이의 다리 역할을 합니다.

프로필은 공급자 에지 코드를 작게 유지합니다. 웹훅 핸들러는 이벤트를 정규화합니다.
프로필은 Rumi가 해당 이벤트에 대해 무엇을 해야 하는지를 선택합니다.

## 책임

입력 프로필은 다음을 선택합니다.

- 대상 유형: 채팅, 상담원, 흐름 또는 무시
- 대화 핵심 전략;
- 모델 및 프롬프트 기본값
- 메모리 및 컨텍스트 정책
- 응답 어댑터
- 허용되는 이벤트 종류
- 텍스트 변환 및 첨부 파일 처리
- 이벤트에 응답할 수 없는 경우 대체 동작입니다.

프로필은 원시 비밀 값을 저장하지 않습니다. 비밀 이름을 참조하거나
자격 증명 ID.

## 예

```json
{
  "id": "slack-support-thread",
  "enabled": true,
  "provider": "slack",
  "match": {
    "team_id": "T123",
    "channel_id": "C_SUPPORT",
    "event_kinds": ["message", "app_mention"]
  },
  "audience_policy_id": "support-channel-policy",
  "destination": {
    "type": "chat",
    "conversation_kind": "external",
    "session_key": "slack:{team_id}:{channel_id}:{thread_id}"
  },
  "runtime": {
    "model": "stub/default",
    "system_prompt_id": "support_assistant"
  },
  "response": {
    "adapter_id": "slack-thread",
    "mode": "reply"
  }
}
```

## 잠재고객 정책 링크

`AudiencePolicy`는 "이 이벤트가 루미에 들어갈 수 있을까요?"라고 대답합니다.
`InputProfile`는 "루미는 어떻게 해야 할까요?"라고 대답합니다.

프로필은 광범위한 허용 규칙을 포함하기보다는 정책을 참조해야 합니다.
이를 통해 중재, 속도 제한 및 청중 게이트를 여러 환경에서 재사용할 수 있습니다.
프로필.

## 세션 키

프로필은 외부 대화가 다시 매핑되도록 안정적인 세션 키를 생성해야 합니다.
기존 Rumi 대화에:

| 공급자 | 세션 키 예시 |
|---|---|
| 슬랙 스레드 | `slack:{team_id}:{channel_id}:{thread_id}` |
| 슬랙 DM | `slack:{team_id}:dm:{user_id}` |
| 라인 소스 | `line:{source_type}:{source_id}` |
| 디스코드 채널 | `discord:{guild_id}:{channel_id}` |
| 일반 웹훅 | `webhook:{profile_id}:{external_subject}` |

세션 키는 자격 증명이 아닙니다. 비밀이 포함되어 있지 않으면 기록될 수 있습니다.
또는 민감한 메시지 내용.

## submit_input 페이로드

`submit_input`은 정규화된 이벤트와 선택된 프로필을 수신해야 합니다:

```json
{
  "event": {
    "event_id": "evt_01",
    "provider": "slack",
    "text": "summarize the thread"
  },
  "profile": {
    "id": "slack-support-thread",
    "destination": {"type": "chat"}
  },
  "policy": {
    "decision": "allow"
  }
}
```

이 함수는 공급자 중립적인 런타임 결과를 반환합니다. 제공업체 배송은
나중에 `ResponsePlanner` 및 `ResponseAdapter`에 의해 처리됩니다.

## 프로필 안전 기본값

- 명시적으로 활성화될 때까지 기본적으로 비활성화됩니다.
- 로컬 개발 플래그가 활성화되지 않은 경우 확인된 이벤트가 필요합니다.
- 기본적으로 봇/셀프 메시지를 무시합니다.
- 최소 권한 모델, 도구 및 에이전트 설정을 사용합니다.
- 안전하지 않은 공개 응답보다 응답 없음을 선호합니다.
- 감사 또는 UI 표시 전에 메타데이터를 수정합니다.
