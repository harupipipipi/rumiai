<!-- docs-i18n-links:start -->
[EN](../../artifact_generation_design.md) | [JP](../ja/artifact_generation_design.md) | [KR](./artifact_generation_design.md) | [CN](../zh-cn/artifact_generation_design.md)
<!-- docs-i18n-links:end -->

# 아티팩트 생성 디자인

아티팩트는 메타데이터가 포함된 로컬 결과물입니다.

- 마크다운, 텍스트, 코드
- json, yaml, html, csv
- 보고서, 변경 내역, 실행 계획

각 유물에는 `artifact_id`, `type`, `title`, `path`, `content_ref`, `created_by`, `source_task`, `version`이 있습니다. 아티팩트 저장은 로컬 파일 기능을 사용하며 나중에 선택적 어댑터를 통해 내보낼 수 있습니다.
