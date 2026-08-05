# Profile Workspace v4

Profile workspaces live under `<RUMI_USER_DATA>/workspaces/<profile_id>/`.
They are state containers, not Profile authorities.

```text
workspaces/<profile_id>/
  activation/          # digest-bound ActivationStore envelopes
  state/
    workspace.json     # state-only marker
    rumi.sqlite
  artifacts/
  snapshots/
  audit/events.jsonl
```

The verified `Profile v4 -> ProfileLock v4 -> ResolvedPlan -> ActivationStore`
chain is the only source of active identity, Pack membership, providers,
permissions, policy, Shell, and resource bindings. Files inside a workspace may
store application state and audit evidence, but runtime code must not interpret
them as authority.

The retired layout is not read or generated:

- `profiles/<id>/profile.yaml`
- `profiles/active_profile.json`
- `settings/startup_profiles.json`
- per-Profile startup, surface, policy, permission, or approval YAML

There is no in-process compatibility migration from those files. Importing old
configuration, when provided by an offline tool, must produce canonical v4
artifacts and pass normal verification before activation.

## Runtime state scope

`resolve_runtime_database_path()` returns
`workspaces/<profile_id>/state/rumi.sqlite`.
`resolve_runtime_user_data_dir()` returns the active Profile workspace. The
workspace manager exposes the `state/` child to stateful Pack services and
creates only state, artifact, snapshot, and audit locations.

ChatStore, MemoryStore, Attachments, and other runtime stores must resolve their
paths from the verified active Profile. They must never fall back to a shared
database or infer a Profile from environment variables, a mutable marker, or a
legacy Profile document.
