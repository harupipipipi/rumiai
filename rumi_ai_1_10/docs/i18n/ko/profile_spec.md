<!-- docs-i18n-links:start -->
[EN](../../profile_spec.md) | [JP](../ja/profile_spec.md) | [KR](./profile_spec.md) | [CN](../zh-cn/profile_spec.md)
<!-- docs-i18n-links:end -->

# 기능 프로필 사양

기능 프로필은 기능 그래프 컴파일을 위한 런타임 또는 작업 공간 사전 설정입니다. 사용 가능한 노드와 선택한 그래프가 특정 환경에서 실행되는 방법을 설명합니다.

버전: `rumi.profile.v1`

프로필은 보안 진실 문서가 아닙니다. 구문 분석된 프로필 권한은 UI 및 런타임 기본값을 안내할 수 있지만 권한 있는 작업은 여전히 ​​기존 신뢰, 부여, 승인 및 기능 시스템에 의해 시행되어야 합니다.

## 파일

초기 발견 후보:

1. `user_data/shared/profiles/*.profile.yaml`
2. `ecosystem/<pack_id>/profiles/*.profile.yaml`

팩 제공 프로필 파일은 기존 팩 승인 및 해시 확인 흐름을 통과한 팩에서만 로드되며, 팩 제공 흐름 로딩에 사용되는 신뢰 경계와 일치합니다. 사용자 공유 프로필 파일은 사용자 소유 구성이지만 등록 또는 사용 전에 여전히 스키마 유효성 검사 및 진단이 필요합니다.

## 시작 프로필과의 관계

기능 그래프 프로필은 초기 PR의 기존 `StartupProfileManager` 또는 시작 시간 시작 프로필 시스템을 대체하지 않습니다.

명시적인 브리지 또는 마이그레이션 PR이 전달될 때까지 기존 시작 프로필은 시작 동작, 설정 및 런타임 시작 기본값을 선택하기 위한 시작 시간 정보 소스로 유지됩니다. `rumi.profile.v1`은 기능 그래프 로딩, 검증, 컴파일 및 뷰어/노드 관리자 필터링에 사용되는 그래프/런타임 사전 설정입니다.

프로파일 로더는 기존 시스템과 공존하여 적응합니다. 명시적으로 연결된 경우에만 디스플레이 또는 진단을 위한 시작 관련 기본값을 읽을 수 있지만 시작 프로필 선택을 대체해서는 안 됩니다.

백엔드 API는 이 관계를 나란히 노출합니다.

```json
{
  "launch_time_source_of_truth": "StartupProfileManager",
  "capability_graph_profiles_role": "graph_runtime_presets",
  "startup_profile_api": "/api/panel/startup/profiles"
}
```

이는 뷰어를 위한 명시적인 브리지 계약입니다. 시작 프로필은 계속해서 시작 시 시작 동작을 소유하는 반면 `rumi.profile.v1`은 기능 그래프 로드, 팔레트 필터링, 유효성 검사 및 컴파일 미리 보기를 제어합니다. `StartupProfileManager`을 교체하려면 여전히 전용 마이그레이션 결정과 PR이 필요합니다.

용어:

- `StartupProfileManager`은 `rumi_cli`, `rumi_desktopapp` 및 `rumi_work`와 같은 실행 시간 시작 프로필을 소유합니다.
- `CapabilityProfileDefinition`은 `defaultspack.coding`와 같은 `rumi.profile.v1` 그래프/런타임 사전 설정을 소유합니다.
- 기능 프로필의 `default_graph`은 컴파일 입력 전용입니다. 시작 프로필 실행은 이 PR에서 해당 그래프를 자동으로 컴파일하지 않습니다.
- 시작 프로필 시작을 기능 그래프 컴파일/런타임 등록으로 연결하는 것은 시작 계약이 명시적으로 설계될 때까지 의도적으로 범위를 벗어납니다.

## 그래프와의 관계

그래프와 프로필은 별개입니다.

- 그래프는 기능 배선도입니다.
- 프로필은 해당 배선 다이어그램에 대한 런타임 사전 설정, 환경, 권한, 기본값 및 노드 가용성입니다.

그래프 컴파일러는 항상 `graph_id` 및 `profile_id`을 모두 받습니다.

## 스키마

```yaml
profile_id: coding
version: rumi.profile.v1
kind: runtime_profile
display_name:
  en: Coding
  ja: コーディング
locale: en
default_graph: coding_workspace
default_flow: coding_startup
enabled_nodes:
  - rumi.start
  - defaultspack.agent
  - defaultspack.tool.registry
disabled_nodes:
  - defaultspack.experimental.remote_shell
viewer:
  palette:
    include:
      - defaultspack.agent
      - defaultspack.tool.registry
permissions:
  can_install_packs: false
  can_create_profile: true
  can_update_profile: true
  can_delete_profile: false
policy:
  max_tool_calls: 8
  require_approval_for_tools: true
node_settings:
  defaultspack.agent:
    model_profile: default
```

## 필수 입력사항

- `profile_id`
- `version`
- `kind`

## 공통 필드

- `enabled_nodes`
- `disabled_nodes`
- `default_graph`
- `default_flow`
- `viewer.palette`
- `permissions`
- `policy`
- `node_settings`
- `locale`

## 노드 가용성

프로필 인식 노드 레지스트리는 다음에서 파생됩니다.

```text
global node registry + selected profile
```

1단계 동작:

- `disabled_nodes`에 나열된 노드를 사용할 수 없습니다.
- `enabled_nodes`이 비어 있지 않으면 나열된 노드만 사용할 수 있습니다.
- `enabled_nodes`이 비어 있거나 없으면 비활성화된 노드를 제외한 모든 전역 노드를 사용할 수 있습니다.

그래프 검증 및 컴파일에서는 사용할 수 없는 노드를 사용하는 그래프를 거부해야 합니다.

## 노드 상태

프로필 노드 상태는 노드 정의와 별도로 계산되어야 합니다.

예상되는 상태 카테고리:

- 활성화됨
- 장애인
-missing_definition
-missing_configuration
- 이용 불가

첫 번째 프로필 PR에는 나중에 프로필 인식 그래프 유효성 검사 및 뷰어 팔레트 필터링을 지원하는 데 충분한 구조만 필요합니다.

## 인터페이스 레지스트리

로드된 프로필은 다음과 같이 등록됩니다.

```text
profile.<profile_id>
```
