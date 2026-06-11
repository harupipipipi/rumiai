<!-- docs-i18n-links:start -->
[EN](../../gateway.md) | [JP](../ja/gateway.md) | [KR](./gateway.md) | [CN](../zh-cn/gateway.md)
<!-- docs-i18n-links:end -->

# 게이트웨이

`domain/gateway`은 세션 라우팅과 함께 로컬 제어 평면 셸을 제공합니다.
채널 어댑터. 첫 번째 구현은 경량 로컬 HTTP를 시작합니다.
상태 및 인증된 이벤트 수신을 위한 서버; WebSocket 프로토콜 도우미는 다음과 같습니다.
`domain/gateway/ws.py`에 입력된 요청/이벤트 봉투로 표시됩니다.
게이트웨이는 기본적으로 `127.0.0.1`에 바인딩되며, 그렇지 않은 경우 외부 바인딩 주소를 거부합니다.
런타임 구성은 이를 명시적으로 활성화하고 베어러 또는
POST 섭취를 위한 `x-rumi-gateway-token` 토큰.

세션 키는 다음과 같습니다.

- `agent:{agent_id}:main`
- `agent:{agent_id}:chat:{conversation_id}`
- `agent:{agent_id}:line:user:{line_user_id}`
- `agent:{agent_id}:discord:channel:{channel_id}`
- `cron:{job_id}`
- `webhook:{webhook_id}`

## 외부 입력 관계

게이트웨이는 외부 입력 프레임워크 자체가 아닌 로컬 흡입 셸입니다. 공개
또는 공급자별 이벤트는 `ExternalEvent`로 정규화되어야 하며 다음을 통해 확인되어야 합니다.
`AudiencePolicy`, `InputProfile`을 통해 매핑되고 다음을 통해 제출됨
`submit_input`. 게이트웨이 메시지는 해당 이벤트의 소스 중 하나일 수 있습니다.

응답 전달은 `ResponsePlanner` 및 `ResponseAdapter`을 거쳐야 하므로
채팅 및 에이전트 코드는 Slack, Discord, LINE, 웹훅 또는 터널을 학습하지 않습니다.
세부 사항.

Cloudflare Quick Tunnel을 사용하는 경우 Cloudflare는 단지 교체 가능한 URL 공급자일 뿐입니다.
로컬 엔드포인트. 정식 게이트웨이, 인증 시스템 또는
외부 입력 런타임.
