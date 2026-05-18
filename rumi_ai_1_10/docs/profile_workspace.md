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
