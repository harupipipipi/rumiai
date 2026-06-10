<!-- docs-i18n-links:start -->
[EN](../../migration-guide.md) | [JP](../ja/migration-guide.md) | [KR](./migration-guide.md) | [CN](../zh-cn/migration-guide.md)
<!-- docs-i18n-links:end -->

# 마이그레이션 가이드

## 요약

중단을 최소화하면서 레거시 기본 워크플로를 defaultspack v2로 이동합니다.

## 메모

- 가능한 경우 기존 파일 기반 데이터를 보존합니다.
- 직접 모듈 탐색 대신 새로운 로더를 사용하십시오.
- 광범위한 리팩터링보다 호환성 심을 선호합니다.
