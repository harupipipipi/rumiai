# Architecture

## Responsibility

`rumi_devops_release_pack` owns declarative guidance for release and operations workflows:

- CI failure triage.
- Log and artifact evidence summaries.
- Release note drafting from local evidence.
- Deployment runbook structure.
- Rollback plan structure.
- GitHub Actions and Cloudflare Workers-aware operational checklists.

## Boundaries

The pack is intentionally not a code-editing pack and not a deployment runtime.

- `rumi_code_ide_pack` owns code edits, patch loops, and IDE or CLI pair-programming behavior.
- `rumi_agent_services_pack` owns service-agent topology and long-running service behaviors.
- `defaultspack` owns runtime primitives, approvals, profile loading, audit events, and core tool routing.
- `rumi_default_tools_pack` owns concrete tool implementations.

## Directory Layout

- `ecosystem.json`: pack identity, dependencies, assets, and local-first network policy.
- `catalog/`: structured release gate and operations catalog data.
- `profiles/`: runtime profile metadata for CI, release, and rollback sessions.
- `prompts/`: system prompts for evidence-first operations behavior.
- `presets/`: named workflow bundles for common operational surfaces.
- `examples/`: example task records.
- `metadata/`: overlap and defaultspack promotion notes.
- `docs/`: pack-specific documentation.

## Execution Path

1. The setup-pack selector discovers `ecosystem/setup_pack/rumi_devops_release_pack/pack.json`.
2. The runtime discovers the pack assets listed in `ecosystem.json`.
3. A selected profile references existing defaultspack graph and flow primitives.
4. Prompts, presets, and catalogs guide how an agent gathers local evidence, asks for approval, and prepares release or rollback outputs.

## Runtime Contact Points

- Existing profile and prompt conventions from `defaultspack`.
- Existing local file, git, terminal, and optional browser/research tools from `rumi_default_tools_pack`.
- Existing runtime approval and audit policies.

No pack-owned Python modules are imported during normal use.
