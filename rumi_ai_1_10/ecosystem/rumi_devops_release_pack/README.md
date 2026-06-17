# Rumi DevOps Release Pack

`rumi_devops_release_pack` is an optional, declarative, local-first pack for DevOps and release operations. It helps Rumi-native agents reason about CI failures, logs, release notes, deployment runbooks, rollback plans, GitHub Actions, and Cloudflare Workers-aware operations without adding executable code or new runtime powers.

## What It Provides

- Profiles for CI triage, release management, and rollback planning.
- Prompts for evidence-first operations work.
- Presets for GitHub Actions triage, Cloudflare Workers releases, local release gates, and incident rollback.
- Catalog files for release gate checklists, runbook sections, evidence classes, and operational task types.
- Examples for CI failure triage, release notes with evidence, and rollback planning.
- Setup-pack metadata for dependency, overlap, and defaultspack promotion policy.

## What It Does Not Provide

- No executable code, functions, handlers, routes, stores, or flows.
- No secrets, credentials, tokens, deploy keys, or environment values.
- No automatic network access; network is none by default.
- No ownership of code edits. `rumi_code_ide_pack` owns code-edit workflows.
- No ownership of service topology. `rumi_agent_services_pack` owns service-agent composition.

## Docs

Start with [docs/README.md](docs/README.md). The interface contract is in [docs/interfaces.md](docs/interfaces.md), and day-to-day maintenance notes are in [docs/operations.md](docs/operations.md).
