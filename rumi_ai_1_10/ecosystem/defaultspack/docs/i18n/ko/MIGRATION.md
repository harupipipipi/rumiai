<!-- docs-i18n-links:start -->
[EN](../../MIGRATION.md) | [JP](../ja/MIGRATION.md) | [KR](./MIGRATION.md) | [CN](../zh-cn/MIGRATION.md)
<!-- docs-i18n-links:end -->

# 마이그레이션

이 문서에는 레거시 기본값에서 defaultspack v2까지의 호환성 경로가 요약되어 있습니다.

- `user.csv` 데이터를 `user.json`로 마이그레이션해야 합니다.
- 레거시 모듈 가져오기는 새로운 백엔드/프론트엔드 로더 진입점을 사용해야 합니다.
- 기존 런타임 동작은 얇은 호환성 레이어를 통해 유지됩니다.
