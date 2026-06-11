<!-- docs-i18n-links:start -->
[EN](../../changelog_defaultspack_v2.md) | [JP](../ja/changelog_defaultspack_v2.md) | [KR](./changelog_defaultspack_v2.md) | [CN](../zh-cn/changelog_defaultspack_v2.md)
<!-- docs-i18n-links:end -->

# 변경 내역: defaultspack v2

## 추가됨

- 정식 API 경로 정의가 포함된 추적된 `ecosystem/defaultspack` 팩
- `setup_pack` 검색 및 설치 팩 기반 All-OK 권한 게이팅
- 기능 우선 defaultspack 작업 표면
- 모듈 카탈로그, 지속된 모듈 상태, 종속성 저하 및 복구 이벤트
- 레거시 `user.csv` ~ `user.json` 마이그레이션 도우미
- 설정 팩 선택 및 마이그레이션 가시성을 위한 설정 UI 통합
- 롤백 지원이 포함된 승인 지원 `request_extension` / `forced_patch` 요청 흐름

## 운영 참고사항

- `all OK`은 설치 팩 설치 중에 선택한 설치 팩에 부여됩니다.
- 설치 팩 설치 및 모든 확인 권한 작업이 감사 기록됩니다.
