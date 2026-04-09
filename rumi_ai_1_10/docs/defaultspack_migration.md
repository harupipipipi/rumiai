# defaultspack migration notes

## Legacy compatibility

- Legacy `ecosystem/defaults` can remain present as reference/compatibility data.
- Production routing for the new pack is the canonical `/api/defaultspack/*` namespace.
- `user_data/user.csv` is migrated to `user_data/user.json` on setup-pack install when needed.

## Rollback

- Use module `rollback` or `disable` to isolate a failing module.
- Revoke `all OK` with `POST /api/defaultspack/setup/packs/defaultspack/revoke-all-ok`.
- Remove `user_data/settings/setup_pack_selection.json` to clear setup-pack selection if manual recovery is required.

## Deprecation path

- New features should land in `ecosystem/defaultspack/functions/*`.
- New production code should not add direct `blocks.*.run` imports for default behavior.
