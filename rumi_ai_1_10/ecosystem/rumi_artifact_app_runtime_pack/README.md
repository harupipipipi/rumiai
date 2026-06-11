# Rumi Artifact App Runtime Pack

Declarative runnable artifact app contracts for manifests, sandbox render policy, state snapshots, versioning, approval-gated tool calls, error boundaries, and export packages.

This setup pack makes Rumi more customizable by adding a domain contract that can be selected independently from defaultspack. It is intentionally local-first, declarative, and reviewable: it creates schemas, workflow packets, quality gates, and handoff records instead of executing adjacent runtime actions.

Artifact app manifests are package and renderer contracts only. They name a stable app ID, pinned artifact/version refs, checksums, sandbox tokens, approval prompt fields, and owner-pack handoffs. They do not create files, launch renderers, call MCP/API tools, transform media, or mint share links.

## Provides

- artifact_app_manifest
- sandbox_renderer_contract
- artifact_state_snapshot
- artifact_version_selector
- tool_mcp_approval_prompt
- runtime_error_boundary
- share_export_manifest
- artifact_runtime_ui_contract

## Does Not Provide

- frontend design generation
- file persistence
- sandbox isolation runtime
- MCP execution
- API execution
- media transforms
- browser automation

## Required Secrets

None. Network is denied by default and the pack contains no executable runtime code.

## Defaultspack Promotion

Not eligible by default. Promotion requires:

- no_renderer_registry_runtime
- no_per_artifact_storage_runtime
- sandbox_execution_owned_elsewhere
- mcp_api_execution_owned_elsewhere
- approval_receipts_required_for_tool_calls
- client_supplied_approved_never_trusted
- schema_contracts_only

## Overlap Rule

If another pack can perform a step, Rumi should prefer the narrower owner surface. This pack emits a Handoff packet whenever the request crosses into frontend review, runtime execution, connector IO, persistence, browser automation, or media transformation.

Existing defaultspack artifact stores, chat artifact serving, share links, tool execution, and MCP execution are never overridden. This pack can select or read existing records and draft package contracts, then hand execution back to the owner pack.
