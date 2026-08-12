# Sealed Python environment packaging

Release builds create one native, relocatable Python environment per supported
Tauri target before packaging:

* `aarch64-apple-darwin` and `x86_64-apple-darwin` (macOS)
The generator retains Linux/Windows fixture coverage, but current production
installer and release workflows intentionally build and publish macOS only.
Non-macOS production requests are rejected by the local release helper.

The exact locked runtime export is
`tobkiri_runtime/requirements.txt`; CI installs both that export and
`requirements-dev.txt` through
`.github/scripts/install_locked_python_test_dependencies.py`.
The pinned `uv` archive is staged by the existing resource preparer. Python
3.13.13 is installed and dependency wheels are synchronized at build time;
the packaged application never downloads on first launch.
Before generation, the pinned uv executable must report the structured official
0.11.14 identity with a valid revision/date and the exact requested target
triple; arbitrary prefixes, suffixes, versions, and architectures are rejected.
Production Rust packaging callers receive Python and Git through the formal
`TOBKIRI_PACKAGING_PYTHON`/`TOBKIRI_PACKAGING_GIT` absolute-path bindings and
their lowercase raw `*_SHA256` values. They re-hash and re-check file identity
before each use; `PYTHON`, `PATH`, and ambient tool discovery are not accepted
by the build script or its authoritative-source fixtures.

## Resource contract

Tauri maps `tobkiri_launcher/src-tauri/gen/app` to the stable packaged
`{resource_dir}/app`. The sealed subtree is exactly:

```text
{resource_dir}/app/python-runtime/
├── sealed-environment.v1.json
├── lease.v1
├── runtime/                 # native CPython runtime
├── venv/                    # copied, relocatable environment
├── app/
│   ├── app.py               # packaged application closure
│   ├── kernel_entry.py
│   ├── defaultspack_entry.py
│   ├── host_helper_entry.py
│   ├── core_runtime/        # lazy-import closure
│   └── ecosystem/           # lazy-import closure
├── sentinels/
│   ├── stdlib.sha256
│   ├── site-packages.sha256
│   └── native.sha256
└── venv/*/site-packages/tobkiri_sealed/bootstrap.py
```

The manifest has only the fixed top-level fields and fixed nested field sets
defined in `.github/schemas/sealed-python-environment.v1.schema.json`.
Its provenance `kind` is `apple-code-signature-v1` on macOS,
`windows-authenticode-v1` on Windows, and `linux-immutable-package-v1` on
Linux; `package_id` is always `dev.tobkiri.launcher`.
`files` is a sorted, link-free inventory of regular files and excludes only
the manifest itself. All sealed digest fields, including `environment_digest`,
the three sentinels, the raw manifest binding, and attestation digests, are
lowercase 64-hex raw SHA-256 values; the `sha256:` prefix is not part of this
domain. `environment_digest` is SHA-256 over the compact serde-compatible JSON
bytes of that exact array. `lease.v1` is included in the inventory and is
opened under a shared OS lock by bootstrap for the lifetime of the process.

The launcher invokes the fixed boundary:

```text
python -I -B -m tobkiri_sealed.bootstrap \
  --role typed --nonce <parent-nonce> \
  --attestation <new-attestation-path> \
  --manifest <sealed-environment.v1.json> \
  --environment-root <python-runtime> -- <role-argv...>
```

The launch wire schema is `io.tobkiri.sealed-python-launch.v1`; the startup
attestation schema is `io.tobkiri.sealed-python-attestation.v1`.
The wire role values are `typed`, `defaultspack`, and `host_helper`; `typed`
dispatches the packaged kernel wrapper. Bootstrap
rejects unknown boundary arguments, binds every supplied path to the sealed
snapshot, recomputes the stdlib/site-packages/native sentinel groups, and
publishes an attestation through a new temporary file, `fsync`, and atomic
no-replace publication. The role receives only the arguments after `--`.
`typed` directly runs `app.py`, `defaultspack` directly runs the long-lived
`ecosystem/defaultspack/defaultspack/desktop_app.py`, and `host_helper`
directly runs the stdin/stdout JSON
`core_runtime/host_broker/computer_host_helper.py`; wrappers preserve the
process environment, standard streams, and exit status. These targets and
their tracked lazy-import closure are copied under the sealed `app/` root and
are covered by the same manifest inventory. Bootstrap preloads the wrapper and
target, normalizes and validates prefixes, executable, native import roots,
and `sys.path` before publishing attestation. After that point dispatch uses
the preloaded target; the path guard rejects additions outside the snapshot.
In the packaged Defaultspack path, import roots come only from the sealed
`__file__`/`app/` layout. `REPO`, `RUMI_CORE_DIR`, `PYTHONPATH`, `PYTHONHOME`,
and `DYLD_`/`LD_` loader injection are rejected; the legacy environment
fallback remains a separate unpackaged-development behavior.

The sealed wrapper receives a process-private, bootstrap-issued scope bound to
the verified manifest and role target. Defaultspack accepts the sealed import
root only when that scope proves an exact target-file match; a snapshot
basename or client environment variable cannot select the packaged path.
After attestation, the import path object is frozen and dispatch must preserve
its exact contents.

Bootstrap emits only the fields in
`.github/schemas/sealed-python-attestation.v1.schema.json`. The native build
script binds the raw manifest SHA-256 as
`TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256`; this binding is separate from the
outer Tauri resource provenance manifest.

## Threat boundary

The sealed snapshot and lease protocol are designed to fail closed against a
corrupt or non-cooperating updater, cross-UID replacement, symlink/reparse
substitution, hardlinks, special files, and path escapes. The generator emits a
non-writable snapshot and bootstrap restricts its attested `sys.path` to
canonical paths inside that snapshot before loading the sealed application
closure. This is an integrity boundary, not a claim of OS-enforced
immutability against an already-running malicious process with the same UID:
ordinary user-owned snapshots cannot provide that guarantee.

Windows/Linux installer and release publication is intentionally disabled until
their platform signing and native runtime validation are explicitly re-enabled.

The packaging lane owns the generator, resource assembly, and Python boundary;
the core Rust `sealed_python.rs` implementation remains the owner of launcher
binding/launch validation. Integration must keep the two implementations
aligned through the protocol drift test and must not add a competing Rust
schema validator in this lane.

Use the local, network-free validator with a prepared tree:

```bash
python .github/scripts/build_sealed_python_environment.py \
  --check --target x86_64-unknown-linux-gnu
```

Local contract tests use tiny synthetic trees and cover link materialization,
tamper, missing/extra inventory, path escape, permissions, role-wire, and
snapshot-`sys.path` behavior. Full CPython/native-extension construction is
deferred to the integration lane while the shared Cargo target is being
cleaned; it must cover native macOS relocation and all three role smokes before
the macOS release workflow is considered green.
