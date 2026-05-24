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
          "signature": "hmac-sha256:key-id:...",
          "min_core_version": "1.10.0",
          "max_core_version": "<2.0.0"
        }
      }
    }
  }
}
```

Validation rejects absolute paths, traversal, null bytes, symlinks, missing checksums, checksum mismatches, signature mismatches, pack id mismatches, missing `ecosystem.json`, invalid stable semver, and incompatible core/viewer versions.

Release scripts:

- `scripts/build_pack_bundle.py`
- `scripts/verify_pack_bundle.py`
- `scripts/generate_pack_index.py`

Signatures currently support `hmac-sha256` trust roots in `pack_state/trust_roots.json`. The format is intentionally isolated so asymmetric signatures can be added without changing the pack store.
