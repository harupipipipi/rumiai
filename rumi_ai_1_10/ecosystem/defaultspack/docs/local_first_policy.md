# Local First Policy

defaultspack core is usable without cloud API keys.

Policy:

- workspace files only unless a pack explicitly grants a broader capability.
- network is denied by default.
- cloud model providers are optional adapters.
- file write, overwrite, delete, terminal execution, and git push require approval metadata.
- secrets are stored in the Rumi secret store and are never exposed in UI catalogs.
- audit records contain action, risk, decision, and redacted arguments.

Core may include local file, terminal, git, local model provider interface, memory, project, compact, artifacts, safety, permission, and audit. External search, Reddit, browser network, GitHub API, SaaS integrations, and cloud schedules stay optional.
