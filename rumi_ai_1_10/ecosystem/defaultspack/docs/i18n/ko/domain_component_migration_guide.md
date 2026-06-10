<!-- docs-i18n-links:start -->
[EN](../../domain_component_migration_guide.md) | [JP](../ja/domain_component_migration_guide.md) | [KR](./domain_component_migration_guide.md) | [CN](../zh-cn/domain_component_migration_guide.md)
<!-- docs-i18n-links:end -->

# Defaultspack 도메인 구성 요소 마이그레이션 가이드

이 가이드에서는 중앙 레지스트리를 늘리지 않고 도메인 표면을 추가하거나 마이그레이션하는 방법을 설명합니다.

## 호환성 우선

마이그레이션 중에 공개 ID, 경로 또는 가져오기의 이름을 바꾸지 마세요. 코드가 구성 요소 폴더로 이동할 때 이전 가져오기 경로를 shim으로 유지합니다. 기존 경로 경로, 끝점 ID, 프로필 ID, 프롬프트 ID, 공급자 별칭 및 도구 ID를 안정적으로 유지합니다.

## 웹훅 또는 통합 추가

생성:

```text
domain/webhooks/<provider>/manifest.json
domain/integrations/<provider>/manifest.json
domain/integrations/<provider>/inbound.py
domain/integrations/<provider>/security.py
domain/integrations/<provider>/normalizer.py
domain/integrations/<provider>/output.py
domain/integrations/<provider>/rules.json
```

`domain/webhooks/<provider>/manifest.json`에서 엔드포인트 기본값을 선언합니다. `domain/integrations/<provider>/manifest.json`에 런타임 동작 및 경로 메타데이터를 넣습니다. `blocks/integrations/<provider>.py`를 심으로 남겨둡니다.

## 공급자 또는 모델 추가

생성:

```text
domain/providers/<provider_id>/manifest.json
domain/providers/<provider_id>/models.json
```

공급자 구성 요소는 런타임 메타데이터를 확장합니다. `rumi_model_catalog_pack`과 같은 매니페스트 지원 카탈로그 팩은 별도로 유지되며 계속해서 공급자/모델 카탈로그 매니페스트를 소유합니다. 공급자 어댑터는 도구 레지스트리 또는 도구 정책 모듈을 가져오면 안 됩니다.

## 도구 추가

생성:

```text
domain/tools/<tool_id>/manifest.json
```

구성 요소 매니페스트는 `entrypoints.tool_manifest`을 사용하여 기존 `tools/<tool_id>/manifest.json`를 가리킬 수 있습니다. 승인 및 실행은 여전히 ​​`ToolRegistry`, `ToolOrchestrator`, `ToolExecutor` 및 기존 정책 확인을 통해 진행되어야 합니다.

## 브라우저 또는 컴퓨터 드라이버 표면 추가

소유 팩 아래에 구성 요소 메타데이터를 만듭니다. 예를 들면 다음과 같습니다.

```text
rumi_default_tools_pack/domain/browser/<driver_id>/manifest.json
rumi_default_tools_pack/domain/computer/<driver_id>/manifest.json
```

보이는 화면 전용 동작, 전경 가드, 명시적인 물리적 동작 승인 및 기존 대체 순서를 유지합니다.

## 프롬프트 또는 템플릿 추가

생성:

```text
domain/prompts/<prompt_id>/manifest.json
domain/prompts/<prompt_id>/prompt.md
domain/prompts/<prompt_id>/rules.json
domain/templates/<template_id>/manifest.json
```

프롬프트 구성 요소는 공급자/도구에 독립적입니다. 사용자가 저장한 프롬프트는 여전히 `user_data/shared/prompts`에 있습니다.

## 경로 또는 UI 메타데이터 추가

구성 요소는 `routes`에서 경로 레코드를 선언할 수 있습니다. 기존 경로 테이블은 대체 호환성을 유지합니다. UI 표면은 다음 위치에 있습니다.

```text
domain/ui_surfaces/<surface_id>/manifest.json
```

매니페스트의 `ui`을 통해 UI 메타데이터를 노출하고 프런트엔드 카탈로그 형태를 안정적으로 유지합니다.

## 검토 체크리스트

- 구성요소 매니페스트는 진단 없이 검증됩니다.
- 이전 가져오기 경로는 여전히 가져옵니다.
- 이전 ID와 경로는 여전히 해결됩니다.
- 테스트에서는 이동된 기본값과 심을 다룹니다.
- 보안 기본값이 약화되지 않았습니다.
- 중앙 레지스트리는 새로운 기본값을 소유하는 대신 구성 요소를 로드하거나 검색합니다.
