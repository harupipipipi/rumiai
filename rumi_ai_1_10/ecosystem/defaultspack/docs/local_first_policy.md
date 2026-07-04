# Local First Policy

defaultspack core is usable without cloud API keys.

The canonical implementation for this repository is
`rumi_ai_1_10/ecosystem/defaultspack/`. The older `ecosystem/defaults/` package
and the separate `harupipipipi/rumiai_defaults` repository are compatibility or
snapshot sources. New runtime behavior, safety rules, route contracts, and UI
defaults should be implemented in defaultspack first, with legacy aliases kept
only where existing callers still need them.

Policy:

- workspace files only unless a pack explicitly grants a broader capability.
- network is denied by default.
- cloud model providers are optional adapters.
- file write, overwrite, delete, terminal execution, and git push require approval metadata.
- secrets are stored in the Rumi secret store and are never exposed in UI catalogs.
- audit records contain action, risk, decision, and redacted arguments.

Core may include local file, terminal, git, local model provider interface, memory, project, compact, artifacts, safety, permission, and audit. External search, Reddit, browser network, GitHub API, SaaS integrations, and cloud schedules stay optional.

## Cloudflare provider boundary

Cloudflare account connection is optional and does not weaken local-first
startup. A missing Cloudflare SDK, token, or account id must render as provider
status, not as startup failure. Dry-run runner plans are side-effect free.
Cloudflare deploy/update/delete operations are write-like cloud mutations and
must require both provider capability resolution and an explicit local approval
context. The runtime must not trust request-body flags such as `approved`.

Cloudflare runner provisioning uses Rumi-owned names, normally a `rumi-*`
prefix, and stores only non-secret resource metadata. Teardown is constrained to
stored resources or resources matching that prefix. API tokens, OAuth tokens,
Worker secret values, callback bearer values, and Cloudflare error payloads are
redacted before they enter UI payloads, metadata, audit records, docs examples,
or test snapshots.

## Runtime defaults

- The guaranteed startup model is `stub/default`.
- Local providers such as Ollama, LM Studio, vLLM, llama.cpp, and local
  OpenAI-compatible endpoints may be detected without making an external network
  request.
- Cloud providers are catalog entries and configuration targets, but they are
  not selected as the fresh-runtime default.
- Automatic cloud provider registration in the runtime is disabled unless the
  process explicitly opts in with `RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS`.
- Local providers do not require API keys. API key prompts should appear only
  after a cloud provider or cloud model is selected.

## Local operation protection

Sensitive local operations are protected independently from user accounts. This
protects a local HTTP runtime from cross-site or stale-tab mutation attempts
without adding login, account creation, Supabase, or Cloudflare dependencies.

Sensitive mutations include file write/create/delete/patch/restore, terminal
execution/streaming, git commit/push, integration secrets, and browser
screenshots. They must pass these checks before execution:

- the client address is loopback;
- an Origin header, when present, is local;
- sensitive mutations with an Origin include `X-Rumi-CSRF`;
- the block receives a signed one-time approval token bound to the operation and
  argument hash;
- the attempt, approval decision, execution, denial, or failure is written to the
  JSONL audit log with secrets redacted.
