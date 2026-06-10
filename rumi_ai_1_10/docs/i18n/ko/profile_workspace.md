<!-- docs-i18n-links:start -->
[EN](../../profile_workspace.md) | [JP](../ja/profile_workspace.md) | [KR](./profile_workspace.md) | [CN](../zh-cn/profile_workspace.md)
<!-- docs-i18n-links:end -->

# 프로필 작업공간

프로필 작업 공간은 `<RUMI_USER_DATA>/profiles/<profile_id>/` 아래에 있으며 레거시 `settings/startup_profiles.json`을 제거하지 않고 프로필별 런타임 데이터를 격리합니다.

```text
profiles/<profile_id>/
  profile.yaml
  user_data/
  database/rumi.sqlite
  startup/launch.yaml
  startup/surface.yaml
  flows/
  prompts/
  ecosystem/snapshots/
  permissions/grants.yaml
  permissions/tool_policy.yaml
  permissions/approvals.yaml
  audit/events.jsonl
```

`profile.yaml`은 시작 프로필의 핵심 필드인 ID, 팩 및 그래프 선택, 런타임 프로필 필드, 정책, 권한 기본값, 노드 재정의 및 타임스탬프를 미러링합니다.

`user_data/`은 미래의 프로필별 런타임 데이터 루트입니다. `database/rumi.sqlite`은 확인자 API가 반환한 프로필 범위 데이터베이스 경로입니다. `startup/`는 발사 및 표면 구성을 저장합니다. `flows/` 및 `prompts/`는 프로필 재정의를 보유합니다. `ecosystem/snapshots/`에는 복사된 defaultspack 리소스에 대한 잠금 파일이 포함되어 있습니다. `permissions/`은 보조금 우회가 아닌 기본값의 원인입니다. `audit/events.jsonl`은 프로필 범위의 이벤트를 기록합니다.

마이그레이션에서는 `<RUMI_USER_DATA>/settings/startup_profiles.json`을 읽고, 누락된 `profile.yaml` 파일을 생성하고, `profiles/active_profile.json`를 쓰고, `profiles/.migration_state.json`을 기록합니다. 레거시 파일은 저장소가 완전히 이동될 때까지 StartupProfileManager 상태에 대한 호환성 소스로 유지됩니다.

## 런타임 데이터베이스 범위

이 PR에서는 `resolve_runtime_database_path()`을 통한 프로필 데이터베이스 경로 확인과 `resolve_runtime_user_data_dir()`을 통한 프로필 사용자 데이터 루트 확인을 소개합니다. 프로필을 생성하거나 실행하면 `<RUMI_USER_DATA>/profiles/<profile_id>/database/rumi.sqlite`가 초기화되고 실행 페이로드 및 활성 생태계 메타데이터에 해당 경로가 노출됩니다.

이 PR은 아직 모든 런타임 저장소를 프로필 범위 데이터베이스로 마이그레이션하지 않습니다. 프로필 범위 DB 및 프로필 범위 사용자 데이터로의 런타임 저장소 전체 마이그레이션은 저장소가 이미 명시적으로 연결되지 않은 한 후속 작업으로 유지됩니다.

후속 TODO:

- ChatStore: 채팅 지속성을 열기 전에 `resolve_runtime_database_path()`를 사용하세요.
- MemoryStore: SQLite 지원 메모리에는 `resolve_runtime_database_path()`를 사용합니다.
- 설정 관리자 및 설정 파일: 레거시 전역 사용자 데이터 루트 대신 `resolve_runtime_user_data_dir()`을 사용합니다.
- 첨부 파일 및 업로드된 파일: 프로필 범위 저장을 위해 `resolve_runtime_user_data_dir()`을 사용하세요.
