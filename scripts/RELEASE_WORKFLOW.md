# Release workflow controls

The release workflow has two explicit modes:

- `production` is the only mode that can create a release package. It requires
  synchronized application versions and the exact `v<version>` tag.
- `local-dev` is an explicit debug-only path in `build-and-sign.sh`. Its
  unsigned or ad-hoc output is written under the debug build target and is not
  sealed, inventoried, attested, or eligible for upload.

The current production publication policy is one single active target: macOS ARM
(`aarch64-apple-darwin`, `arm64`) with one `.dmg` asset. The
`ACTIVE_RELEASE_TARGETS` constant in `scripts/release_inventory.py` is the
single active target authority. Both workflow matrices, target manifests, the
final inventory, this document, and the release-control tests must agree with
it. Other platform builds may remain useful for compatibility or CI, but are
not production publication targets.

`release_gate.py` is the canonical version and signing-policy gate used by the
workflow and `build-and-sign.sh`. It validates secret presence and tool
availability without printing secret values. The production macOS path uses a
Developer ID Application identity, notarization, stapling, and Gatekeeper
assessment.

Each active matrix target writes one immutable `release-target.json` containing
the actual checked-out source SHA, target triple, platform, architecture, and
SHA-256/byte-size records. The `gather` job requires exactly the single active
target manifest, rejects missing, duplicate, replaced, or unexpected assets,
and writes one sorted `release-inventory.json`. GitHub artifact provenance
attests that single inventory subject exactly once. Only after the inventory is
verified and attested does the workflow create the reviewable draft release.

The production packaging gate explicitly runs the packaging and production
integration tests. After notarization, the final DMG is attached read-only, its
application is copied to a temporary canonical directory, and that copied app
is launched through LaunchServices. The gate requires a visible application
window before it quits the smoke-test process. A post-build Git inspection also
rejects tracked index/worktree changes and non-ignored untracked paths.

Required production credentials are supplied through GitHub Actions secrets and
are never hard-coded:

- macOS: `APPLE_CERTIFICATE_BASE64`, `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and
  `APPLE_TEAM_ID`.

Local production runs need the same credentials and platform tools. No actual
credential-backed signing is performed by the repository tests; tests use
mocked tool calls and synthetic target artifacts.
