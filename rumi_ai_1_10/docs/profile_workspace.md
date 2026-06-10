<!-- docs-i18n-links:start -->
[EN](./profile_workspace.md) | [JP](./i18n/ja/profile_workspace.md) | [KR](./i18n/ko/profile_workspace.md) | [CN](./i18n/zh-cn/profile_workspace.md)
<!-- docs-i18n-links:end -->

# Profile Workspace

Profile workspaces live under `<RUMI_USER_DATA>/profiles/<profile_id>/` and isolate per-profile runtime data without removing legacy `settings/startup_profiles.json`.

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

`profile.yaml` mirrors the startup profile's core fields: identity, pack and graph selection, runtime profile fields, policy, permissions defaults, node overrides, and timestamps.

`user_data/` is the future per-profile runtime data root. `database/rumi.sqlite` is the profile-scoped database path returned by the resolver APIs. `startup/` stores launch and surface configuration. `flows/` and `prompts/` hold profile overrides. `ecosystem/snapshots/` contains lockfiles for copied defaultspack resources. `permissions/` is a source of defaults, not a grant bypass. `audit/events.jsonl` records profile-scoped events.

Migration reads `<RUMI_USER_DATA>/settings/startup_profiles.json`, creates missing `profile.yaml` files, writes `profiles/active_profile.json`, and records `profiles/.migration_state.json`. The legacy file remains the compatibility source for StartupProfileManager state until stores are fully moved.

## Runtime Database Scope

This PR introduces profile database path resolution through `resolve_runtime_database_path()` and profile user-data root resolution through `resolve_runtime_user_data_dir()`. Creating or launching a profile initializes `<RUMI_USER_DATA>/profiles/<profile_id>/database/rumi.sqlite` and exposes that path in launch payloads and active ecosystem metadata.

This PR does not migrate every runtime store to the profile-scoped database yet. Full migration of runtime stores to profile-scoped DB and profile-scoped user data remains a follow-up unless a store is already explicitly wired.

Follow-up TODOs:

- ChatStore: use `resolve_runtime_database_path()` before opening chat persistence.
- MemoryStore: use `resolve_runtime_database_path()` for SQLite-backed memory.
- Settings managers and settings files: use `resolve_runtime_user_data_dir()` instead of the legacy global user-data root.
- Attachments and uploaded files: use `resolve_runtime_user_data_dir()` for profile-scoped storage.
