# Managed runtime overview

This PR evolves the existing defaultspack `SandboxManager` into one runtime for pack isolation, coding sandboxes, and desktop seats.

## Required providers

- Linux uses a native hidden Xvfb/Openbox desktop and does not require Docker.
- Windows uses a Rumi-owned Ubuntu environment through WSL2. Rumi guides any one-time operating-system approval and resumes after a required restart.
- macOS uses a Rumi-managed headless Lima Ubuntu VM and does not require Docker Desktop or Homebrew.
- An existing Docker-compatible runtime is optional.

Users are not asked to manually install Ubuntu, Docker Desktop, Lima, Colima, or a WSL distribution. Rumi performs setup from its UI while leaving operating-system consent explicit.

## Existing ownership

- Extend `ecosystem/defaultspack/backend/sandbox/`; do not create a second manager.
- Keep `ecosystem/rumi_sandbox_runtime_pack/` declarative for policies, templates, evidence, and handoff contracts.
- Route existing `sandbox_exec`, `python_exec`, and `node_exec` through the managed manager instead of direct Docker ownership.
- Keep `GUISandbox` as a test fake only.
- Port only relevant Linux virtual-desktop code from draft PR 221; exclude unrelated changes.

## Shared stack

All consumers use the same provider registry, template resolution, policy evaluation, state store, audit, guest protocol, resource limits, and cleanup.

The implementation must support runtime health/setup/update/removal, sandbox lifecycle and execution, workspace overlays, controlled network and secrets, desktop frames and input, and a server-side human-control lease.
