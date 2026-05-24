# Pack Distribution

Rumi packs are distributed as `.rumi-pack` zip files.

Required files:

- `rumi-pack.json`
- `ecosystem.json`
- `manifest.json` or `manifest.sha256`
- `signature` or an index-provided signature

The pack index points to signed bundles:

```json
{
  "schema": "rumi.pack_index.v1",
  "channel": "stable",
  "packs": {
    "defaultspack": {
      "latest": "2.5.0",
      "versions": {
        "2.5.0": {
          "url": "https://example/defaultspack-2.5.0.rumi-pack",
          "sha256": "...",
          "signature_scheme": "ed25519",
          "key_id": "official-2026-05",
          "signature": "ed25519:official-2026-05:...",
          "min_core_version": "1.10.0",
          "max_core_version": "<2.0.0"
        }
      }
    }
  },
  "signatures": [
    {
      "scheme": "ed25519",
      "key_id": "official-2026-05",
      "signature": "..."
    }
  ]
}
```

Validation rejects absolute paths, traversal, null bytes, symlinks, missing checksums, checksum mismatches, missing index signatures, signature mismatches, pack id mismatches, missing `ecosystem.json`, invalid stable semver, and incompatible core/viewer versions.

Release scripts:

- `scripts/build_pack_bundle.py`
- `scripts/verify_pack_bundle.py`
- `scripts/generate_pack_index.py`

Signatures use Ed25519. Clients receive only public keys through the bundled `core_runtime/update/official_trust_roots.json`; release CI uses `RUMI_UPDATE_ED25519_PRIVATE_KEY_B64` to sign bundles and indexes. Core updates and official packs such as `defaultspack` verify only against bundled official keys. User-data `pack_state/trust_roots.json` may add third-party pack keys for manually configured pack sources, but those keys cannot authorize core updates or replace bundled official key ids.
