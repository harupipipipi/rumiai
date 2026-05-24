# Managed Pack Store

Managed packs live in `RUMI_USER_DATA/packs`.

```text
packs/
  defaultspack/
    current.json
    versions/
      2.5.0/
        rumi-pack.json
        ecosystem.json
    staging/
    backups/
    state/
pack_state/
  trust_roots.json
  update_preferences.json
```

`current.json` is the only active-version pointer. Rumi does not use symlinks, so activation works reliably on Windows.

```json
{
  "schema": "rumi.pack_current.v1",
  "pack_id": "defaultspack",
  "version": "2.5.0",
  "path": "versions/2.5.0",
  "updated_at": "2026-05-24T00:00:00Z"
}
```

Discovery priority is:

1. `user_data/packs/*/current.json`
2. `user_data/packs/*/ecosystem.json` direct fallback
3. `BASE_DIR/pack_seeds/*`
4. `BASE_DIR/ecosystem/*`
5. `BASE_DIR/ecosystem/packs/*`

Managed locations are mutable. Seed and legacy locations are read-only fallback sources.
