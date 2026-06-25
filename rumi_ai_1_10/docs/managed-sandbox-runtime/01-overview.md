# Managed runtime overview

This PR evolves the existing defaultspack `SandboxManager` into one runtime
foundation for pack isolation, coding sandboxes, and desktop seats. It does not
complete every end-state provider promise in the original handoff plan.

## Required providers

- Linux uses a native hidden Xvfb/Openbox desktop and does not require Docker.
- Windows uses a Rumi-owned Ubuntu environment through WSL2 when `wsl.exe` is
  already available. WSL feature enablement, elevation, and reboot resume remain
  follow-up work.
- macOS uses a Rumi-owned headless Lima Ubuntu VM when `limactl` is already
  available. Bundled Lima installation remains follow-up work.
- An existing Docker-compatible runtime is optional.

Users are not asked to install Docker Desktop as a prerequisite. In this
foundation PR, missing Lima/WSL launchers produce fail-closed diagnostics; once
the launcher is present, Rumi can create and provision the managed Ubuntu guest
from its UI while leaving operating-system consent explicit.

## Existing ownership

- Extend `ecosystem/defaultspack/backend/sandbox/`; do not create a second manager.
- Keep `ecosystem/rumi_sandbox_runtime_pack/` declarative for policies, templates, evidence, and handoff contracts.
- Route existing `sandbox_exec`, `python_exec`, and `node_exec` through the managed manager instead of direct Docker ownership.
- Keep `GUISandbox` as a test fake only.
- Port only relevant Linux virtual-desktop code from draft PR 221; exclude unrelated changes.

## Shared stack

All consumers use the same provider registry, template resolution, policy evaluation, state store, audit, guest protocol, resource limits, and cleanup.

The implementation supports runtime health/setup/update/removal, sandbox
lifecycle and execution, workspace overlays, controlled network and secrets,
desktop frames and input, and a server-side human-control lease within the
provider scope above.

## Isolation claims in this PR

Docker-backed sandboxes provide container-level workspace/process/network
separation. Managed Ubuntu providers run all instances inside one Rumi-owned
Lima/WSL guest with separate work directories but a shared guest Unix identity
and shared guest kernel namespaces. They do not claim per-sandbox filesystem
isolation, immutable read-only mounts, or process namespace isolation; use Docker
for those boundaries until stronger managed guest isolation lands.

Continuity handoff UI is planning/checkpoint only in this PR. It records a
portable handoff plan while the source remains primary; automatic primary-device
cutover is follow-up work.
