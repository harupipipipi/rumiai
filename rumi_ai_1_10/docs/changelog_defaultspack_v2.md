<!-- docs-i18n-links:start -->
[EN](./changelog_defaultspack_v2.md) | [JP](./i18n/ja/changelog_defaultspack_v2.md) | [KR](./i18n/ko/changelog_defaultspack_v2.md) | [CN](./i18n/zh-cn/changelog_defaultspack_v2.md)
<!-- docs-i18n-links:end -->

# Changelog: defaultspack v2

## Added

- Tracked `ecosystem/defaultspack` pack with canonical API route definitions
- `setup_pack` discovery and setup-pack based all-OK permission gating
- Function-first defaultspack operation surface
- Module catalog, persisted module state, dependency degradation, and recovery events
- Legacy `user.csv` to `user.json` migration helper
- setup UI integration for setup-pack selection and migration visibility
- approval-backed `request_extension` / `forced_patch` request flow with rollback support

## Operational notes

- `all OK` is granted to selected setup packs during setup-pack install.
- Setup-pack install and all-OK permission operations are audit logged.
