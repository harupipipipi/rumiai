<!-- docs-i18n-links:start -->
[EN](../../domain_component_convention.md) | [JP](../ja/domain_component_convention.md) | [KR](./domain_component_convention.md) | [CN](../zh-cn/domain_component_convention.md)
<!-- docs-i18n-links:end -->

# Defaultspack 도메인 구성 요소 규칙

Defaultspack은 확장과 유사한 도메인 구성 요소로 이동하고 있습니다. 기능은 다음과 같습니다.
`domain/<category>/<component_id>/` 아래에 폴더를 놓으면 추가됩니다.
매니페스트 및 소유한 작은 규칙, 어댑터 또는 처리기. 기존 공개 ID,
경로, 수입 및 행동은 안정적으로 유지되는 반면 중앙 레지스트리는
검색 및 호환성 레이어.

## 폴더 레이아웃

정식 구성 요소 폴더는 다음 모양을 사용합니다.

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md
  tests/
```

구성 요소 ID는 안정적이고 소문자여야 하며 파일 시스템에 안전해야 합니다. 공개 ID
매니페스트 내부에는 점, 슬래시 및 과거 이름이 유지될 수 있습니다.
이미 API의 일부입니다.

## 카테고리 이름 지정

복수의 도메인 중심 카테고리를 사용하세요.

- `webhooks`
- `integrations`
- `gateway_channels`
- `webhook_url_providers`
- `tools`
- `providers`
- `prompts`
- `templates`
- `input_profiles`
- `output_profiles`
- `audience_policies`
- `transports`
- `ui_surfaces`

카테고리 이름은 구현 세부 사항이 아닌 소유권을 설명해야 합니다. 에 대한
예를 들어 LINE 웹훅 기본값은 `webhooks/line`에 속하지만 LINE 인바운드는
보안 및 정규화 코드는 `integrations/line`에 속합니다.

## 매니페스트 필드

모든 구성 요소 매니페스트에는 다음이 포함되어야 합니다.

- `id`: 안정적인 구성 요소 ID 또는 공개 ID입니다.
- `category`: 폴더 카테고리.
- `kind`: 카테고리 내 구성요소 종류입니다.
- `version`: 구성 요소 계약의 문자열 버전입니다.
- `status`: `experimental`, `stable`, 또는 `legacy`.

추천 분야:

- `entrypoints`: 런타임 코드에 대한 경로 또는 파일 관련 진입점을 가져옵니다.
- `routes`: 공개 HTTP 경로 메타데이터, 메서드 및 경로 ID.
- `profiles`: 구성 요소가 소유하거나 노출하는 입력/출력 프로필 ID입니다.
- `security`: 서명, 공유 비밀, 승인, 자격 증명 또는 샌드박스 정책.
- `ui`: 프런트엔드 그룹화, 아이콘, 명령, 패널 또는 카탈로그 메타데이터.
- `policy`: 청중, 응답, 도구 또는 라우팅 규칙.
- `capabilities`: 공급자, 도구, 미디어, 전송 및 모드 기능.
- `aliases`: 이 구성 요소를 해결하는 안정적인 호환성 별칭입니다.
- `compatibility`: 남아 있어야 하는 레거시 가져오기, ID, 기본값 및 심.
- `conversion_targets`: 이 구성 요소를 변환하거나 내보낼 수 있는 ID입니다.
- `owner`: 모듈, 팀 또는 관리자 힌트를 소유하고 있습니다.
- `source_pack_id`: 구성요소를 공급하는 팩.

매니페스트는 데이터입니다. 검색 시 핸들러 코드를 가져오거나 임의 실행하면 안 됩니다.
파이썬. 런타임 레이어는 구성 요소를 선택한 후에만 진입점을 가져올 수 있습니다.
사용하기 위해.

## 진입점

진입점은 런타임 동작을 가리키는 가져오기 문자열 또는 파일 로컬 이름입니다.

```json
{
  "entrypoints": {
    "handler": "domain.integrations.line.inbound:handle_line_webhook",
    "security": "domain.integrations.line.security:verify_signature",
    "adapter": "domain.providers.google.adapter:GoogleProvider"
  }
}
```

호환성 심은 이전 블록 모듈을 계속 가져올 수 있지만 새 코드는
선택한 구성 요소에 대한 구성 요소 레지스트리를 요청한 다음 특정 구성 요소를 로드합니다.
진입점이 필요합니다.

## 규칙 파일

규칙은 선언적일 경우 `rules.json`에,
규칙에는 작은 도우미 기능이 필요합니다. 규칙 파일은 구성 요소에 로컬로 유지되어야 합니다.
두 번째 중앙 레지스트리가 되어서는 안 됩니다.

예:

- 웹훅 엔드포인트 기본값
- 입력 및 출력 프로필 사양
- 청중 정책
- 도구 승인/위험 힌트
- 공급자 모델 기본값
- 프롬프트 렌더링 옵션
- 경로 메타데이터
- UI 명령 그룹화

## 호환성 별칭

별칭은 역사적 공개 이름을 보존합니다. 여기에는 엔드포인트 ID, 프로필이 포함될 수 있습니다.
ID, 도구 ID, 공급자 별칭, 모델 별칭, 경로 이름 및 레거시 가져오기
경로. 별칭 확인은 명시적이고 결정적이어야 합니다.

예:

- 엔드포인트 ID: `line-main`, `discord-main`, `slack-main`, `test-webhook`
- 프로필 ID: `line.default`, `discord.default`, `slack.default`,
  `generic.webhook.default`
- 제공자 ID: `gitlawb-opengateway`
- 모델 ID: `gitlawb-opengateway/mimo-v2.5-pro`,
  `gitlawb-opengateway/mimo-v2-flash`,
  `gitlawb-opengateway/mimo-v2-omni`

## 경로 메타데이터

경로 메타데이터는 안전할 때마다 동작을 소유하는 구성 요소에 속합니다.

```json
{
  "routes": [
    {
      "id": "webhook.line.inbound",
      "path": "/webhooks/line",
      "methods": ["POST"],
      "entrypoint": "domain.integrations.line.inbound:handle_line_webhook"
    }
  ]
}
```

마이그레이션 중에 공개 경로가 변경되어서는 안 됩니다. 기존 라우팅 테이블은 다음과 같이 유지됩니다.
매니페스트 지원 경로가 완전한 적용 범위와 테스트를 갖출 때까지 대체합니다.

## 공급자 및 모델 메타데이터

공급자 구성 요소는 공급자 메타데이터, 인증 규칙, 어댑터 진입점 및
모델 기본값. 모델 카탈로그는 매니페스트 지원 형제 팩에서 도착할 수도 있습니다.
`rumi_model_catalog_pack` 등; defaultspack은 이들과 상호 운용되어야 합니다.
복사하거나 접는 대신 팩으로 만듭니다.

공급자 구성 요소는 도구 레지스트리 또는 도구 정책 모듈을 가져오면 안 됩니다.
공급자 도구 브리징은 다음을 알고 있는 오케스트레이션 또는 브로커 계층에 속합니다.
공급자 기능과 도구 실행 모두.

## 프롬프트, 프로필 및 정책 메타데이터

프롬프트 구성 요소는 프롬프트 ID, 프롬프트 텍스트/템플릿, 렌더링 규칙 및
프롬프트 호환성 별칭. 입력/출력 프로필 및 대상 정책은 다음과 같습니다.
기존 레지스트리 API를 유지하면서 매니페스트 또는 규칙 지원 구성 요소가 됩니다.

레지스트리는 구성 요소 데이터를 로드하고, 사용자 정의 영구 데이터를 병합해야 하며,
호환성 조회를 제공합니다. 새로운 하드코딩된 기본값이 늘어나서는 안 됩니다.

## 마이그레이션 규칙

- 공개 ID, 경로, 별칭, 엔드포인트 ID, 프로필 ID 및 도구 ID를 유지합니다.
  안정.
- 호출자가 이동할 때까지 오래된 가져오기를 얇은 심으로 유지합니다.
- 이전 코드를 삭제하기 전에 이전 코드 옆에 매니페스트 지원 검색을 추가하는 것을 선호합니다.
  코드.
- 런타임을 변경하기 전에 기본값을 구성 요소 매니페스트 또는 규칙 파일로 이동합니다.
  행동.
- 보안 및 승인 행위를 최소한 이전만큼 엄격하게 유지하세요.
- 유효하지 않은 구성 요소 매니페스트에 대한 소프트 실패 및 진단 노출.
- 검색 시 여러 생태계 팩을 지원합니다.
- 검색 중에 핸들러 코드를 가져오지 마십시오.
- `rumi_model_catalog_pack`를 defaultspack으로 축소하지 마십시오.

## 중앙 레지스트리에 있으면 안 되는 것

중앙 레지스트리는 다음의 기본 홈이 되어서는 안 됩니다.

- 공급자의 엔드포인트 기본값
- 공급자별 입력/출력 프로필 기본값
- 대상 정책 기본값
- 공급자 허용 목록 및 모델 기능 메타데이터
- 도구 스키마 및 위험 정책
- 통합별 서명 또는 응답 규칙
- 프롬프트 텍스트 및 프롬프트 호환성 별칭
- 구성 요소가 소유한 경로 및 UI 메타데이터

중앙 파일은 호환성 별칭, 삭제, 지속성, 병합을 유지할 수 있습니다.
마이그레이션이 완료되지 않은 동안 논리, 진단 및 대체 동작이 수행됩니다.
