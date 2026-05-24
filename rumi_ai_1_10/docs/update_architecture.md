# Layered Update Architecture

Rumi uses three update layers with separate ownership and rollback boundaries.

## Layers

- Viewer: the Tauri desktop shell, installer, launcher, tray, and window lifecycle. It is updated only by the Tauri updater and does not write pack files.
- Core: the Python kernel, `core_runtime`, core packs, `app.py`, and requirements. Core updates stage into `user_data/update_state/core`, validate protected paths, back up core files, and require a kernel restart.
- Packs: `defaultspack` and future packs. Runtime pack source lives under `user_data/packs`, not under app resources.

## Invariants

- Viewer updates never modify packs or core runtime files.
- Pack updates never modify Viewer or core runtime files.
- Core updates never write `user_data/packs`, `pack_state`, settings, logs, or secrets.
- Pack activation is atomic: `current.json` is updated only after signed index verification, download, checksum, Ed25519 bundle signature verification, extraction, manifest validation, compatibility checks, and copy into `versions/<version>` succeed.
- Core updates also require signed indexes and signed bundles before extraction. Clients only ship public keys; release CI holds the private signing key.
- Broken pack updates leave the active `current.json` unchanged.
- The source-tree `core_runtime/update/official_trust_roots.json` is empty by design. Official update verification in dev/source builds can fail until release CI injects `RUMI_UPDATE_ED25519_PUBLIC_KEY_B64`; the matching private key must remain only in release secrets.

## Runtime Defaultspack

Bundled `ecosystem/defaultspack` is treated as a legacy fallback. Bundled release resources also stage a seed at `pack_seeds/defaultspack`. On startup, `ensure_managed_defaultspack_installed()` copies the seed into:

```text
user_data/packs/defaultspack/versions/<version>/
user_data/packs/defaultspack/current.json
```

Discovery then prefers the managed current pointer over seeds and legacy bundled locations.
