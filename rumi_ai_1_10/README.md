<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS

**“Foundation without a foundation”** — a modular AI framework where there is no “body” to be modified

---

## Purposeful guide

Place the reading destinations for each purpose first so that you can find the entry point without having to follow all the code.

| What I want to do | Where to read first | How much can I understand |
|---|---|---|
| I want to trace documents by purpose | [`docs/README.md`](./docs/README.md) | I can trace "what I want to do → which document" on one page |
| I want to align the meanings of terms | [`docs/terminology.md`](./docs/terminology.md) | I can check the usage of `rule`, `skill`, `team workspace`, `delegation` |
| I want to start it first | Root [`README.md`](../README.md) | Shortest startup command and repo entrance |
| I want to try it out first | [`docs/tutorials/runtime-quickstart.md`](./docs/tutorials/runtime-quickstart.md) | The shortest tutorial from `--health` to `/panel/` |
| I want to understand the runtime mechanism without reading the code | [`docs/concepts/system-mechanism.md`](./docs/concepts/system-mechanism.md) | Execution path of startup, flow, approval, grant, viewer collaboration |
| I want to see the startup procedure of `rumi_viewer` and how it gets stuck | [`docs/rumi_viewer_start.md`](./docs/rumi_viewer_start.md) | `401`, black screen, relationship between panel and defaultspack |
| I want to extend the frontend of defaultspack | [`ecosystem/defaultspack/docs/frontend_extensions.md`](./ecosystem/defaultspack/docs/frontend_extensions.md) | How to increase the right bar, settings, chat renderer, and preview feed |
| I want to know the idea of this runtime | `Thoughts` in this README | Flow-centered, Pack premise, Fail-Soft idea |
| I want to know the role of the directory | Role of `Project structure` | `core_runtime/`, `ecosystem/`, `user_data/` in this README |
| Creating/Repairing a Pack | [`docs/pack-development.md`](./docs/pack-development.md) | `ecosystem.json`, `routes.json`, `permissions.json`, Using secrets |
| I want to follow chat / ai of defaultspack | [`ecosystem/defaultspack/README.md`](./ecosystem/defaultspack/README.md) | Implementation side of defaultspack |
| I would like to see the future work of defaultspack frontend | [`ecosystem/defaultspack/docs/frontend_todo.md`](./ecosystem/defaultspack/docs/frontend_todo.md) | Registry progress and next work |
| I want to set API keys and secrets | Secrets section of [`docs/operations.md`](./docs/operations.md) | `user_data/secrets/` and API route |
| I want to fix the boot path via viewer | [`../rumi_viewer/src-tauri/src/config.rs`](../rumi_viewer/src-tauri/src/config.rs) and [`../rumi_viewer/src-tauri/src/kernel_manager.rs`](../rumi_viewer/src-tauri/src/kernel_manager.rs) | Which kernel should viewer start and which env should it pass |
| setup pack / want to see authorization | [`core_runtime/setup_pack.py`](./core_runtime/setup_pack.py) and [`core_runtime/approval_manager.py`](./core_runtime/approval_manager.py) | setup pack selection, all-ok grant, reauthorization |
| I want to know about operations and auditing | [`docs/operations.md`](./docs/operations.md) and [`docs/roadmap.md`](./docs/roadmap.md) | Operational API, secrets, future policy |

## Shortest floor plan

1. `app.py` starts the kernel
2. `core_runtime/` has Flow, Pack, Approval, and Execution infrastructure
3. `ecosystem/<pack_id>/` provides the main body of functionality
4. `user_data/` has authorization state, secrets, stores, audit
5. `rumi_viewer/` becomes a shell that starts the kernel and connects to the panel

## Frequently used entrances

### Startup confirmation

```bash
python -m rumi_ai --health
python -m rumi_ai
```

### viewer development startup

```bash
cd ../rumi_viewer/src-tauri
cargo tauri dev
```

### Typical tests

```bash
python -m pytest tests/test_defaultspack_google_provider.py
python -m pytest tests/test_defaultspack_modules.py
```

---

## Thoughts

### No Favoritism

Rumi AI's official code knows nothing about domain concepts such as "chat," "tool," "prompt," "AI client," and "frontend." All of these are defined by Packs within the ecosystem. The official only provides the **execution mechanism**.

### Foundation without foundation

Minecraft mods modify the foundation of ``Minecraft.'' However, Rumi AI does not have a "body" that can be modified. All application functions are implemented as Packs and wired using Flows.

### Flow-centric architecture

Define the connections, order, and post-installation between Packs using Flow. New features can be added without modifying existing packs.

```
          +---------------------------+
          |       Flow Definition     |
          +---------------------------+
                      |
          +---------------------------+
          |    python_file_call       |
          +---------------------------+
            /         |         \
    +--------+  +--------+  +--------+
    | Pack A |  | Pack B |  | Pack C |
    +--------+  +--------+  +--------+
            \         |         /
          +---------------------------+
          |         Kernel            |
          +---------------------------+
```

> **Flow import source**: `flows/`, `user_data/shared/flows/`, `ecosystem/<pack_id>/backend/flows/`

### Fail-Soft

The system does not stop when an error occurs. Failed components are disabled and logged in the diagnostic information to continue.

### Security based on malicious Pack

The ecosystem is designed on the premise that it can be created by third parties, and that there can also be malicious authors.

- **Approval Required**: No code in unapproved Packs will be executed.
- **Hash verification**: Automatic invalidation if file is modified after approval (requires re-approval)
- **Docker isolation**: Approved packs run in containers (strict mode)
- **Egress Proxy**: External communication is only allowed by proxy via UDS socket
- **Capability (Trust + Grant)**: Host authority is controlled with two-step approval

To re-sign configuration files without HMAC signatures in an existing environment:

```bash
python -m rumi_ai migrate-hmac
```

---

## Project structure

<details>
<summary>Directory tree (click to expand)</summary>

<pre><code>
project_root/
├── app.py
├── bootstrap.py
├── requirements.txt
├── requirements-dev.txt
│
├── flows/
│   └── 00_startup.flow.yaml
│
├── core_runtime/
│   ├── kernel.py
│   ├── kernel_core.py
│   ├── kernel_handlers_system.py
│   ├── kernel_handlers_runtime.py
│   ├── paths.py
│   ├── diagnostics.py
│   ├── interface_registry.py
│   ├── event_bus.py
│   ├── audit_logger.py
│   ├── install_journal.py
│   ├── approval_manager.py
│   ├── network_grant_manager.py
│   ├── egress_proxy.py
│   ├── rumi_syscall.py
│   ├── syscall.py
│   ├── capability_proxy.py
│   ├── capability_executor.py
│   ├── capability_trust_store.py
│   ├── capability_grant_manager.py
│   ├── capability_installer.py
│   ├── rumi_capability.py
│   ├── python_file_executor.py
│   ├── secure_executor.py
│   ├── container_orchestrator.py
│   ├── component_lifecycle.py
│   ├── host_privilege_manager.py
│   ├── pack_api_server.py
│   ├── flow_loader.py
│   ├── flow_modifier.py
│   ├── flow_composer.py
│   ├── flow_scheduler.py
│   ├── function_alias.py
│   ├── vocab_registry.py
│   ├── shared_dict/
│   │   ├── snapshot.py
│   │   ├── journal.py
│   │   └── resolver.py
│   ├── core_pack/
│   │   ├── core_store_capability/
│   │   ├── core_secrets_capability/
│   │   ├── core_flow_capability/
│   │   ├── core_communication_capability/
│   │   └── core_docker_capability/
│   ├── function_registry.py
│   ├── crypto_utils.py
│   ├── lib_executor.py
│   ├── pip_installer.py
│   ├── pack_importer.py
│   ├── pack_applier.py
│   ├── secrets_store.py
│   ├── store_registry.py
│   ├── unit_registry.py
│   ├── unit_executor.py
│   ├── unit_trust_store.py
│   ├── hierarchical_grant.py
│   ├── lang.py
│   └── permission_manager.py
│
├── backend_core/
│   └── ecosystem/
│       ├── compat.py
│       ├── mounts.py
│       ├── registry.py
│       ├── active_ecosystem.py
│       ├── initializer.py
│       ├── uuid_utils.py
│       └── json_patch.py
│
├── ecosystem/
│   ├── <pack_id>/
│   │   └── backend/
│   │       ├── ecosystem.json
│   │       ├── permissions.json
│   │       ├── requirements.lock
│   │       ├── routes.json
│   │       ├── blocks/
│   │       ├── flows/
│   │       ├── components/
│   │       ├── lib/
│   │       ├── share/
│   │       ├── vocab.txt
│   │       └── converters/
│   └── packs/
│       └── <pack_id>/...
│
├── user_data/
│   ├── audit/
│   ├── permissions/
│   │   ├── approvals/
│   │   ├── network/
│   │   ├── capabilities/
│   │   └── .secret_key
│   ├── secrets/
│   ├── packs/
│   ├── capabilities/
│   │   ├── handlers/
│   │   ├── trust/
│   │   └── requests/
│   ├── pip/
│   ├── pack_staging/
│   ├── pack_backups/
│   ├── shared/
│   │   └── flows/
│   │       └── modifiers/
│   ├── pending/
│   │   └── summary.json
│   ├── stores/
│   └── settings/
│       ├── shared_dict/
│       └── lib_execution_records.json
│
├── rumi_setup/
│   ├── core/
│   ├── cli/
│   ├── web/
│   ├── guide/
│   └── defaults/
│
├── lang/
│   ├── en.txt
│   └── ja.txt
│
├── tests/
│   ├── test_capability_installer.py
│   ├── test_capability_system.py
│   ├── test_ecosystem_phase1.py
│   ├── test_ecosystem_phase2.py
│   ├── test_ecosystem_phase3.py
│   ├── test_ecosystem_phase4.py
│   ├── test_ecosystem_phase5.py
│   ├── test_ecosystem_phase6.py
│   ├── test_egress_audit.py
│   ├── test_flow_resolution.py
│   ├── test_inbox_and_patches.py
│   ├── test_pip_installer.py
│   ├── test_secure_execution.py
│   └── test_shared_dict.py
│
└── docs/
    ├── architecture.md
    ├── pack-development.md
    ├── operations.md
    └── roadmap.md
</code></pre>

</details>

### Main directory

| Directory | Role |
|---|---|
| `core_runtime/` | Kernel — Flow execution engine, security, and privilege management |
| `core_runtime/shared_dict/` | Shared dictionary system (snapshot journal) |
| `core_runtime/core_pack/` | Official Capability implementation (Store, Secrets, Flow, Communication, Docker) |
| `backend_core/ecosystem/` | Ecosystem foundation — Pack/Component loading/initialization |
| `ecosystem/` | Pack storage (external supplies) |
| `user_data/` | Runtime persistent data (audit log, approval, Secrets, Store) |
| `rumi_setup/` | Setup assistance (CLI / Web / Guide) |
| `flows/` | Official Flow (startup/base) |
| `lang/` | Multilingual messages |
| `tests/` | Test |
| `docs/` | Document |

### Main files

| File | Role |
|---|---|
| `app.py` | OS entry point |
| `bootstrap.py` | Setup entry point |
| `kernel.py` | Mixin assembly/handler registration |
| `kernel_core.py` | Flow execution engine body |
| `python_file_executor.py` | `python_file_call` Execution |
| `secure_executor.py` | Docker isolation execution |
| `approval_manager.py` | Pack approval management |
| `capability_proxy.py` | Capability Proxy Server (UDS) |
| `egress_proxy.py` | External communication proxy (UDS) |
| `flow_loader.py` | Flow YAML loader |
| `flow_modifier.py` | Flow modifier application |
| `pack_importer.py` | Pack import（zip/folder → staging） |
| `pack_applier.py` | Pack apply（staging → ecosystem） |

## Viewer Graph Editor

The canonical frontend source for the control panel lives in `../rumi_viewer/frontend`.
`core_runtime/core_pack/core_control_panel/web` contains the built static artifact served by the kernel at `/panel/`.

Prompt behavior lives in `ecosystem/defaultspack/domain/prompt/` and `ecosystem/defaultspack/blocks/prompt/`. Tool behavior lives in `ecosystem/defaultspack/domain/tool/` and `ecosystem/defaultspack/blocks/tool/`. The old top-level `prompt/`, `tool/`, and `supporter/` import shims have been removed; new supporter-like behavior should be implemented as defaultspack functions, agents, prompts, memory, or extensions.

The graph editor in `../rumi_viewer/frontend/src/pages/Flows.tsx` is treated as an editor with extensible graph metadata, rather than a fixed UI specialized for Packs.

- The starting node is `rumi_start`
- Nodes can have multiple ports
- A port can hold multiple `contracts`
- Ports that do not match `contracts` cannot be connected to each other.
- Save `rumi_graph` in YAML and restore the structure on the viewer side

This design makes it possible to express transformational roles by defining nodes with different input/output contracts on the Pack side, without having to add special functionality dedicated to transformations.

## Basepack

Added `ecosystem/setup_pack/basepack/pack.json` to allow Rumi AI to choose `basepack` as the base launch profile for graph-first. At the moment, we are treating the existing `defaultspack` as a thin bootstrap profile to launch, and safely deploying it without increasing huge duplicate packs.

---

## Quick start

### Requirements

- Python 3.10+
- Docker (required for production environments)
- Git

### Installation

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10
python bootstrap.py --cli init
```

### Start

```bash
# 本番（Docker 必須）
python app.py

# 開発（Docker 不要）
python app.py --permissive
```

### Pack Approval

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Document

| Document | Contents |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | Overall picture of design and mechanism |
| [docs/pack-development.md](./docs/pack-development.md) | Pack Development Guide |
| [docs/pack-development-guide.md](./docs/pack-development-guide.md) | Pack development quick start |
| [docs/operations.md](./docs/operations.md) | Operation guide |
| [docs/roadmap.md](./docs/roadmap.md) | Roadmap |
| [docs/quality_pack/philosophy_memo.md](docs/quality_pack/philosophy_memo.md) | Thought notes used for development decisions |
| [docs/quality_pack/claude_desktop_quality_pack.md](./docs/quality_pack/claude_desktop_quality_pack.md) | Quality Assurance/Audit/Regression Verification Pack |

---

## License

MIT License
See LICENSE in the repository root for details.
## defaultspack source of truth

The canonical defaultspack implementation in this repository is
`ecosystem/defaultspack/`. The older `ecosystem/defaults/` path and the separate
`harupipipipi/rumiai_defaults` repository are compatibility or snapshot sources.
New local-first runtime behavior should land in defaultspack, with legacy
aliases delegating back to it where needed.

The defaultspack runtime is designed to start without cloud API keys or external
network access. Its guaranteed default model is `stub/default`; cloud providers
are optional and must be selected/configured explicitly. Local file, terminal,
and git mutations are protected with local request guards, one-time signed
approval tokens, and redacted audit records.
