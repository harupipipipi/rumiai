# Local First Policy

Core defaultspack behavior must work without API keys. Workspace file access stays inside the configured root. Network access is denied by default. External web, SaaS, cloud model, Reddit, browser-network, and GitHub API integrations are optional providers.

Writes, deletes, terminal execution, network access, git push, memory deletion, and policy changes require approval. Audit logs must redact secrets, mask environment variables, and include risk labels.
