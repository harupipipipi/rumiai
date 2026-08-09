# Shell v4 release packaging

The checked-in presentation catalog is a declaration, not proof that a Shell
binary is installed. Unbuilt variants intentionally have no artifact path. A
production Launcher is built only from this post-build contract. The normal
local/macOS entrypoint performs the Shell build and sealing automatically:

```bash
../scripts/build-and-sign.sh --bundles app
```

The lower-level release steps are:

1. Build the Shell with `src-tauri/tauri.shell.conf.json`.
2. Run `scripts/write_shell_build_output.py` with the exact release output,
   target platform/architecture, source identity, and source revision.
3. Run `scripts/package_presentation_artifact.py` with that manifest and a
   32-byte raw Ed25519 release key.
4. Set `TOBKIRI_PRESENTATION_RELEASE_ROOT` only for the outer Launcher build.
   A `PROFILE=release` build fails when this input is missing; only an explicit
   `cargo tauri dev` debug build may use the uninstalled declaration.

The materializer verifies the declared variant, executable, macOS bundle
identifier, and code signature. It emits an exact catalog plus
`shell_artifact_index.v4.json`, `shell_profile_lock.v4.json`,
`presentation_release.v4.json`, and the artifact under the fixed
`bundled/presentation-artifacts/<artifact-id>/` path. Path, tree SHA-256,
payload size, platform, architecture, source identity, and source revision are
bound together. The detached Ed25519 signature binds the exact catalog, index,
and lock bytes.

`build.rs` stages those fixed files and embeds that build's signer public key
and key id in the Launcher binary. The environment variable above is strictly
a build input; the running Launcher never reads it. Each CI target may describe
only the artifact it actually built and must not populate another platform.

At runtime, installed metadata is rejected unless the signature matches the
compile-time signer and every binding agrees. Symlinks, path escape, missing or
duplicate records, stale saved selections, digest/size changes, wrong platform,
and unapproved providers fail closed. Restart revalidates the catalog revision
and exact Base, Shell, platform artifact, and digest before launch. There is no
direct-command, `PATH`, environment, or development fallback.

Focused verification:

```text
python -m pytest scripts/tests/test_package_presentation_artifact.py \
  scripts/tests/test_verify_presentation_release.py -q
cargo test --locked --manifest-path src-tauri/Cargo.toml \
  presentation::tests --no-fail-fast
cargo test --locked --manifest-path src-tauri/Cargo.toml \
  --test build_script --no-fail-fast
```
