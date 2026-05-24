# Defaultspack Update Lifecycle

`defaultspack` is no longer run from bundled app resources during normal runtime.

## Startup

1. Viewer starts the Python kernel with `RUMI_USER_DATA`.
2. `app.py` calls `ensure_managed_defaultspack_installed()`.
3. If `user_data/packs/defaultspack/current.json` points to a valid version, startup keeps it.
4. If missing, Rumi copies `pack_seeds/defaultspack` into `user_data/packs/defaultspack/versions/<version>`.
5. If `pack_seeds/defaultspack` is unavailable, Rumi migrates from legacy `ecosystem/defaultspack`.

The seed copy never deletes `state`, `staging`, `backups`, `secrets`, or other user-owned pack data.

## Update

`PackUpdateManager` verifies the signed pack index, downloads a `.rumi-pack`, checks its sha256, verifies the Ed25519 bundle signature, extracts into staging, validates metadata, copies into `versions/<version>`, writes an install record, and only then swaps `current.json`.

## Rollback

Rollback updates `current.json` back to a previous valid version under `versions/`. The previous files remain available because updates install immutable version directories instead of overlaying the active pack.

## Legacy Location

`ecosystem/defaultspack` remains useful for source development and release seeding. It must not be the normal runtime source once the managed defaultspack exists.
