# Tobkiri Base/Shell pack architecture

This directory is the defaultspack-owned conformance boundary for ADR-016. It
does not import or replace Runtime Core or the Tobkiri Launcher. The catalog is
read-only: profile resolution validates exact pack/provider bindings and never
executes pack code, installs dependencies, or builds source.

## Composition

`defaults-basepack` owns the defaultspack backend graph, state owners, and Shell
requirements. A v4 profile then selects exactly one `app.shell.v1` provider:

- `shell.tauri.default` for graphical Tauri presentation;
- `shell.electron.default` for graphical Electron presentation;
- `shell.cli.default` for structured `cli.io.v1` stdio presentation.

The Base Pack has no UI technology or launch command. Graphical and terminal
contributions are separate descriptors. The resolver selects only contributions
consumed by the chosen Shell, and the materializer keeps unselected artifacts
unmaterialized. All three modern profiles use the local `stub/default` model and
require no cloud keys or network access to start.

Tauri and Electron application runtimes and development toolchains are separate
pack kinds. Production Shell/Application variants are pinned prebuilt metadata;
the development packs may describe `npm run dev` or `cargo tauri dev`, but those
operations are not production launch fallbacks.

## Asset layout

- `assets/packs/` contains pack manifests and OS/architecture variant descriptors.
- `assets/contributions/` contains graphical and structured CLI contribution data.
- `assets/schemas/` contains the v4 boundary schemas and migration input schema.
- `assets/examples/` contains standalone-application and shell-composition examples.
- `assets/legacy/` contains inventory-only legacy migration fixtures.
- `../../profiles/defaults-modern*.profile.yaml` are ready-to-resolve local-first profiles.

Variant descriptors are checked-in conformance fixtures. A production installer
must still verify the signed bundle or binary supplied by its distribution
pipeline before launch; these descriptors are not a development-command escape
hatch or a substitute for signature verification.

The checked-in Launcher projection is generated from these manifests and the
protocol revision registry. Check or regenerate it from the repository root:

```bash
python scripts/quality/generate_presentation_catalog.py --check
python scripts/quality/generate_presentation_catalog.py
```

The generated variants intentionally have no installed path or executable
digest. The Launcher may select them, but materialization and launch remain
blocked until an installer supplies a safe path and verifies its pinned digest.
The CLI Shell's local structured-protocol smoke path is:

```bash
cd tobkiri_runtime
python -m tobkiri.cli_shell --structured-stdio
```

Legacy `desktop_app.command` values are retained only as classified migration
inventory. Migration never turns an arbitrary command string into a Shell or
production launch target.
