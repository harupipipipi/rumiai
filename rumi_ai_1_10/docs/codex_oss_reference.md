<!-- docs-i18n-links:start -->
[EN](./codex_oss_reference.md) | [JP](./i18n/ja/codex_oss_reference.md) | [KR](./i18n/ko/codex_oss_reference.md) | [CN](./i18n/zh-cn/codex_oss_reference.md)
<!-- docs-i18n-links:end -->

# Codex OSS Reference Notes

OpenAI Codex OSS was reviewed as a reference for Rumi's coding-tool surface.
The useful parts are mostly architectural and workflow-oriented rather than a
direct code port, because Rumi is a Python pack runtime with a local-first
approval model while Codex is a Rust terminal coding agent.

## Adopted in this repository

- Agent-local repository instructions are captured in the root `AGENTS.md`.
  This follows Codex's pattern of making coding-agent conventions explicit and
  close to the source tree.
- Common development commands are grouped in the root `justfile`, mirroring
  Codex's single command entrypoint for tests, linting, and focused workflows.
- Provider tool schemas are normalized before they are sent to model providers.
  The adapter now lowers malformed or legacy JSON Schema fragments into a
  provider-safe subset, prunes unreachable local definitions, preserves usable
  refs, compacts very large schemas, and keeps tool registration resilient.
- Terminal command risk classification recognizes common read-only discovery
  and test commands such as `rg`, `git ls-files`, `ruff check`, and
  `cargo check` as low risk while preserving shell-escape and outside-workspace
  checks.

## Already present before this pass

- Approval-aware file, terminal, git, GitHub-read, and workspace APIs.
- Signed server-side approval tokens for sensitive coding operations.
- Workspace-root confinement and registered trusted workspace checks.
- A Codex-style app-server backend scaffold under
  `ecosystem/defaultspack/domain/coding_backends/codex-app-server/`.
- Static, security, package, frontend, Rust, Windows, and installer CI lanes.
- Tool discovery, recommendation, policy filtering, and model-provider
  adaptation.

## Not ported directly

- Codex's Rust crate split, Bazel/RBE release pipeline, and TUI snapshot
  workflow are not transplanted. Rumi's boundaries are packs, Python runtime
  modules, Tauri viewer crates, and webapp tests.
- Codex-specific release packaging, code signing, stale-PR automation, and
  CLA workflows do not map cleanly onto this repository's current lifecycle.
- Codex's hosted tool/plugin installation flow is represented in Rumi by
  defaultspack component manifests, function manifests, and capability policy
  rather than a one-to-one connector installer.

## Future candidates

- Add a blob-size non-regression gate if large generated assets start landing
  in PRs unintentionally.
- Add snapshot-style frontend coverage for dense UI panels where textual DOM
  tests miss visual regressions.
- Promote the codex-app-server backend scaffold from experimental once Rumi has
  a real bidirectional app-server transport.
