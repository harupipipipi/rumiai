<!-- docs-i18n-links:start -->
[EN](../../pr_componentization_notes.md) | [JP](../ja/pr_componentization_notes.md) | [KR](./pr_componentization_notes.md) | [CN](../zh-cn/pr_componentization_notes.md)
<!-- docs-i18n-links:end -->

# PR 노트: Defaultspack 구성 요소화

## 요약

이 PR은 기존 공개 동작을 유지하면서 defaultspack을 확장과 유사한 구성 요소 폴더로 이동합니다. 이제 구성 요소 매니페스트에는 웹훅 기본값, 외부 프로필, 통합, 게이트웨이 채널, URL 공급자, 도구, 공급자, 프롬프트, 경로 및 UI 표면이 포함됩니다.

## 아키텍처 목표

표면 추가는 파일 드롭 작업 흐름이 되어야 합니다.

```text
domain/<category>/<component_id>/manifest.json
```

중앙 레지스트리는 호환성 및 검색 계층으로 유지됩니다. 하드코딩된 커넥터/프로필/공급자/도구/프롬프트 기본값을 다시 가져오면 안 됩니다.

## 새로운 구성 요소 폴더 규칙

새로운 도메인 표면은 파일 드롭 구성 요소로 추가되어야 합니다.

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md optional
  tests optional
```

매니페스트는 검색 계약입니다. 유용한 경우 ID, 카테고리/종류, 버전/상태, 진입점, 경로, 프로필, 보안, UI, 정책, 기능, 별칭, 호환성 메타데이터, 변환 대상 및 소스 팩 소유권을 전달합니다.

## PR #92 호환성

- Gitlawb OpenGateway 공급자 ID는 `gitlawb-opengateway`로 유지됩니다.
- Gitlawb OpenGateway 모델 ID는 그대로 유지됩니다.
  - §루미§0§
  - §루미§0§
  - §루미§0§
- 키 없음 동작, 기본 기본 URL 동작, 브라우저 사용자 에이전트 동작 및 고정 모델 허용 목록 동작이 유지됩니다.
- MiMo Omni는 검증된 이미지 메타데이터를 유지합니다.
- `rumi_model_catalog_pack` 공급자/모델 매니페스트가 보존되고 매니페스트 지원 상태로 유지됩니다.
- 승인 텍스트, 응답 토큰 재사용 억제, 현재 회전 채팅 기록 모드, 물리적 클릭 프롬프트 동작, 원본/소스 녹음, 서명 확인, 대상 정책 동작을 포함한 LINE Biz 웹훅 승인/백그라운드 처리가 유지됩니다.
- 보이는 화면 전용 동작, 전경 가드, 승인이 필요한 물리적 동작, URL 구성표 제한 및 대체 순서를 포함하여 브라우저/컴퓨터 드라이버 안전이 `rumi_default_tools_pack`에서 유지됩니다.

## 단계별 변화

1. 도메인 구성 요소 폴더 규칙을 문서화했습니다.
2. 공유 매니페스트 검색, 유효성 검사, 레지스트리, 별칭, 진단 및 멀티팩 루트를 추가했습니다.
3. 웹훅 엔드포인트/보안 기본값을 구성 요소 매니페스트로 이동했습니다.
4. 입력 프로필, 출력 프로필 및 대상 정책을 구성 요소 지원 매니페스트로 이동했습니다.
5. 블록 심을 유지하면서 구성 요소 진입점 뒤에서 LINE, Discord 및 Slack 통합을 분할합니다.
6. 레거시 가져오기 shim이 포함된 구성 요소화된 게이트웨이 채널 및 웹후크 URL 공급자.
7. `rumi_default_tools_pack`을 포함하여 매니페스트 기반 도구/브라우저/컴퓨터 구성 요소 메타데이터를 추가했습니다.
8. 공급자/모델 메타데이터를 Gitlawb OpenGateway를 포함한 공급자 구성 요소로 이동했습니다.
9. 구성요소화된 프롬프트 및 템플릿 표면.
10. 구성 요소 매니페스트에서 경로 및 UI 표면 메타데이터를 로드했습니다.
11. 구성 요소 기본값이 다시 중앙 집중화되는 것을 방지하기 위해 가드레일 및 호환성 테스트가 추가되었습니다.
12. 마이그레이션 문서, PR 노트 및 최종 품질 검사를 추가했습니다.

## 호환성 보장

- 기존 엔드포인트 ID는 안정적으로 유지됩니다: `line-main`, `discord-main`, `slack-main`, `test-webhook`.
- 기존 프로필 ID는 안정적으로 유지됩니다: `line.default`, `discord.default`, `slack.default`, `generic.webhook.default`.
- 기존 공급자 별칭, 경로 경로, 도구 ID, 프롬프트 ID 및 이전 가져오기 경로는 호환성 레이어를 통해 계속 사용할 수 있습니다.
- 잘못된 매니페스트에서 구성 요소 검색이 소프트하게 실패하고 임의 코드를 실행하는 대신 진단을 보고합니다.
- 승인 및 보안 동작은 기존 정책/실행자 경로에 유지됩니다.

## 기존 ID 및 경로가 보존됩니다.

- 끝점 ID는 `line-main`, `discord-main`, `slack-main` 및 `test-webhook`로 유지됩니다.
- 프로필 ID는 `line.default`, `discord.default`, `slack.default`, `generic.webhook.default`로 유지됩니다.
- 공용 웹훅, 설정, UI, 공급자, 프롬프트 및 도구 경로 경로는 기존 경로 테이블의 지원을 유지하며, 공용 경로를 대체하는 대신 메타데이터/검색으로 추가된 매니페스트 지원 경로를 사용합니다.
- 공급자 별칭, 도구 ID, 프롬프트 ID, 끝점 ID 및 이전 차단/가져오기 경로는 호환성 심을 통해 보존됩니다.

## 테스트 실행

- `python -m pytest rumi_ai_1_10/tests/test_defaultspack_webhook_endpoints.py rumi_ai_1_10/tests/test_defaultspack_external_send_tool.py rumi_ai_1_10/tests/test_defaultspack_tool_policy.py rumi_ai_1_10/tests/test_defaultspack_ui_registry.py rumi_ai_1_10/tests/test_defaultspack_mcp_registry.py rumi_ai_1_10/tests/test_defaultspack_agent_service_plan.py rumi_ai_1_10/tests/test_defaultspack_opengateway_provider.py rumi_ai_1_10/tests/test_defaultspack_google_provider.py rumi_ai_1_10/tests/test_defaultspack_line_origin_regression.py rumi_ai_1_10/tests/test_browser_cdp_driver.py rumi_ai_1_10/tests/test_browser_computer_security_windows.py rumi_ai_1_10/tests/test_computer_fallback_order.py rumi_ai_1_10/tests/test_defaultspack_domain_components.py rumi_ai_1_10/tests/test_defaultspack_external_components.py rumi_ai_1_10/tests/test_defaultspack_integration_components.py rumi_ai_1_10/tests/test_defaultspack_gateway_url_components.py rumi_ai_1_10/tests/test_defaultspack_tool_components.py rumi_ai_1_10/tests/test_defaultspack_provider_components.py rumi_ai_1_10/tests/test_defaultspack_prompt_components.py rumi_ai_1_10/tests/test_defaultspack_route_ui_components.py rumi_ai_1_10/tests/test_defaultspack_component_guardrails.py -q`: 373이 통과되었습니다.
- `python -m compileall rumi_ai_1_10/ecosystem/defaultspack`: 통과했습니다.
- `python .github/scripts/quality_gate_nonregression.py --base-ref origin/master`: 통과되었으며 Ruff는 변경되지 않고 mypy 부채는 감소했습니다.
- `python -m pytest rumi_ai_1_10/tests -q`: 4339개 통과, 20개 건너뛰기.

## 알려진 위험

- PR은 의도적으로 호환성 심을 유지하므로 다운스트림 가져오기 및 호출 사이트가 마이그레이션될 때까지 일부 대체 테이블이 유지됩니다.
- 구성 요소 메타데이터와 레거시 레지스트리가 공존합니다. 향후 정리에서는 적용 범위가 더 넓어진 후에만 중복된 대체 선언을 폐기해야 합니다.
- 검색은 이제 여러 에코시스템 팩에 걸쳐 있으므로 런타임 동작이 계속되는 경우에도 잘못된 형식의 타사 매니페스트가 진단을 표면화할 수 있습니다.

## 롤백 참고사항

각 단계는 일관된 커밋입니다. 필요한 경우 이후 문서/테스트를 지침으로 유지하면서 관련 단계 커밋을 되돌립니다. 이전 가져오기 및 경로 경로가 여전히 존재하기 때문에 호환성 심은 롤백을 지역화합니다.

## 후속 정리

- 적용 범위가 확대됨에 따라 레거시 대체 테이블을 매니페스트로 계속 이동합니다.
- 나머지 공급자/카탈로그 메타데이터에 대한 구성 요소 매니페스트를 확장합니다.
- 경로/구성요소 진단을 위해 더욱 풍부한 UI를 추가합니다.
- 다운스트림 가져오기가 마이그레이션된 후에만 호환성 심을 점차적으로 폐기합니다.
