<!-- docs-i18n-links:start -->
[EN](../../webhooks.md) | [JP](../ja/webhooks.md) | [KR](./webhooks.md) | [CN](../zh-cn/webhooks.md)
<!-- docs-i18n-links:end -->

# 웹훅

웹후크는 외부 입력 프레임워크를 위한 하나의 전송입니다. 웹훅 핸들러
공급자 요청을 인증하고 `ExternalEvent`을 추출한 다음
정책 및 프로필 선택에 대한 이벤트입니다. 웹훅 코드는 얇아야 합니다.

## 핸들러 모양

```text
HTTP request
  -> signature or token check
  -> provider parser
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> RumiInputEnvelope
  -> dispatch_input / submit_input
  -> ResponsePlanner
  -> ResponseAdapter
```

핸들러는 공급자별 작업만 수행해야 합니다.

- 서명, 타임스탬프 또는 공유 토큰을 확인합니다.
- 공급자 질문 요청에 응답합니다.
- 페이로드 필드를 `ExternalEvent`에 매핑합니다.
- 공급자가 요구하는 승인 형태를 반환합니다.
- 선택한 `ResponseAdapter`을 호출합니다.

모델 행동, 대화 기억 전략, 프롬프트를 결정해서는 안 됩니다.
선택 또는 상담원 라우팅. 그것들은 `InputProfile`에 속합니다.

## 확인 요청

페이로드 필드를 신뢰하기 전에 공급자 확인이 이루어져야 합니다.

| 공급자 | 검증 |
|---|---|
| 슬랙 | `x-slack-signature` 및 `x-slack-request-timestamp` |
| 라인 | §루미§0§ |
| 불화 | `x-signature-ed25519` 및 `x-signature-timestamp` |
| 일반 웹훅 | 베어러 토큰, HMAC 서명 또는 기타 구성된 검증자 |

로컬 테스트를 위해 서명되지 않은 개발 모드가 존재할 수 있지만 프로덕션 프로필은
확인이 필요해야 합니다. 검증 결과는 부울 또는
상태 문자열. 원시 서명 비밀 및 인바운드 토큰 값은 절대
표시됩니다.

## 멱등성

모든 웹훅 이벤트에는 안정적인 `event_id`이 있어야 합니다. 프레임워크가 삭제되어야 합니다.
다음을 사용하여 복제합니다.

```text
dedupe_key = provider + ":" + event_id
```

공급자가 이벤트 ID를 제공하지 않으면 핸들러는
타임스탬프와 메시지 ID 또는 안정적인 페이로드 필드의 해시에서 가져옵니다. 해시하지 않음
원시 비밀을 ID로 변환합니다.

## 챌린지 및 승인 응답

일부 제공업체는 정상적인 처리 전에 특별한 응답을 요구합니다.

- Slack `url_verification`은 제공된 챌린지를 반환합니다.
- Discord ping은 ping 응답 유형을 반환합니다.
- LINE은 일반적으로 일반적인 HTTP 200 승인을 허용합니다.

처리가 비동기식으로 계속되면 공급자 확인을 먼저 반환하고
`ResponseAdapter`가 최종 응답을 전달합니다.

LINE `computer_use_line_biz` 엔드포인트는 다음과 같은 빠른 승인 동작을 선택할 수 있습니다.
§루미§0§. 이렇게 하면 웹훅 처리만 다음으로 이동됩니다.
공급자가 HTTP 200을 즉시 수신하도록 처리 중인 작업자 그렇지 않다
실험적인 배경 데스크톱 드라이버를 활성화합니다. 눈에 보이는 컴퓨터 사용 잔존물
`RUMI_ENABLE_EXPERIMENTAL_BACKGROUND_COMPUTER_USE=1`이 설정되지 않은 경우 기본값입니다.
LINE Biz 컴퓨터 사용은 기본적으로 현재 채팅 컨텍스트로 전환되어 너무 오래되었습니다.
실패한 도구 로그와 스크린샷은 다음 외부 응답 프롬프트를 부풀리지 않습니다.

## 일반 웹훅 프로필

일반 웹훅은 동일한 외부 입력 경로를 사용해야 합니다.

```json
{
  "provider": "webhook",
  "event_id": "build_123",
  "kind": "event",
  "text": "Build failed on main",
  "metadata": {
    "repository": "example/repo",
    "status": "failed"
  }
}
```

프로필은 이것이 채팅 메시지, 상담원 작업, 흐름이 될지 여부를 결정합니다.
트리거 또는 무시된 이벤트입니다.

이제 웹훅 엔드포인트는 다음을 정의할 수 있습니다.

- `target`
- `default_delivery`
- `allowed_delivery_actions`
- `ttl_seconds` 또는 `expires_at`

인바운드 일반 웹후크는 엔드포인트 기본값을 먼저 적용한 다음 요청만 허용합니다.
명시적으로 허용된 게재 재정의.

## 공개 URL

웹후크에는 연결 가능한 URL이 필요하지만 URL 공급자는 프레임워크 외부에 있습니다.
Cloudflare Quick Tunnel은 임시 개발 URL을 제공할 수 있지만
런타임은 이를 교체 가능한 공급자로 처리해야 합니다. 동일한 웹훅 계약은 다음과 같아야 합니다.
localhost, 역방향 프록시, 플랫폼 경로 또는 기타 터널 뒤에서 작업합니다.
