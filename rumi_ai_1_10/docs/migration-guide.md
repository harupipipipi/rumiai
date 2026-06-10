<!-- docs-i18n-links:start -->
[EN](./migration-guide.md) | [JP](./i18n/ja/migration-guide.md) | [KR](./i18n/ko/migration-guide.md) | [CN](./i18n/zh-cn/migration-guide.md)
<!-- docs-i18n-links:end -->

# Migration Guide

## Summary

Move legacy defaults workflows to defaultspack v2 with minimal disruption.

## Notes

- Preserve existing file-backed data where possible.
- Use the new loaders instead of direct module traversal.
- Prefer compatibility shims over broad refactors.
