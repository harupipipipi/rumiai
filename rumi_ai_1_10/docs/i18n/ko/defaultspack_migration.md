<!-- docs-i18n-links:start -->
[EN](../../defaultspack_migration.md) | [JP](../ja/defaultspack_migration.md) | [KR](./defaultspack_migration.md) | [CN](../zh-cn/defaultspack_migration.md)
<!-- docs-i18n-links:end -->

# defaultspack 마이그레이션 참고 사항

## 레거시 호환성

- 레거시 `ecosystem/defaults`은 참조/호환성 데이터로 계속 존재할 수 있습니다.
- 새 팩의 생산 라우팅은 정식 `/api/defaultspack/*` 네임스페이스입니다.
- `user_data/user.csv`는 필요할 때 설치 팩 설치 시 `user_data/user.json`로 마이그레이션됩니다.

## 롤백

- 오류가 있는 모듈을 격리하려면 `rollback` 또는 `disable` 모듈을 사용하세요.
- `POST /api/setup/packs/{setup_pack_id}/revoke-all-ok`로 `all OK`를 취소합니다.
- 수동 복구가 필요한 경우 `user_data/settings/setup_pack_selection.json`를 제거하여 설치 팩 선택을 취소합니다.

## 지원 중단 경로

- 새로운 기능이 `ecosystem/defaultspack/functions/*`에 추가됩니다.
- 새로운 프로덕션 코드는 기본 동작에 대한 직접 `blocks.*.run` 가져오기를 추가해서는 안 됩니다.
