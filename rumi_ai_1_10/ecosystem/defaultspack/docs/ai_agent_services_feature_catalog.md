<!-- docs-i18n-links:start -->
[EN](./ai_agent_services_feature_catalog.md) | [JP](./i18n/ja/ai_agent_services_feature_catalog.md) | [KR](./i18n/ko/ai_agent_services_feature_catalog.md) | [CN](./i18n/zh-cn/ai_agent_services_feature_catalog.md)
<!-- docs-i18n-links:end -->

# AI Agent Services Feature Catalog

As defaultspack's standard vocabulary, functions of modern AI agent-based services are organized with local priority.

| id | category | inspired_by | local | api | priority | status | defaultspack target |
|---|---|---|---:|---:|---|---|---|
| plan_mode | agent_core | Codex, Claude Code, Manus | yes | no | P0 | implemented | `schemas/agent_plan.schema.yaml`, `prompts/planner.system.md` |
| step_execution | agent_core | Codex, Manus | yes | no | P0 | implemented | `schemas/agent_step.schema.yaml`, `blocks/agent/*` |
| approval_workflow | safety | Codex, Claude Code | yes | no | P0 | implemented | `schemas/tool_call.schema.yaml`, `capabilities/safety.capability.yaml` |
| local_file_workspace | workspace | Codex, Claude Code, Cursor | yes | no | P0 | implemented | `capabilities/local_file.capability.yaml`, `blocks/coding/*` |
| terminal_shell | terminal | Codex, Claude Code | yes | no | P0 | implemented | `capabilities/terminal.capability.yaml` |
| git_integration | git | Codex, Claude Code, Cursor | yes | partial | P0 | implemented | `capabilities/git.capability.yaml` |
| memory | personalization | ChatGPT, Claude Projects | yes | no | P1 | implemented | `capabilities/memory.capability.yaml` |
| project_workspace | project | ChatGPT Projects, Cursor | yes | no | P1 | implemented | `schemas/project.schema.yaml` |
| compact_context | context | Claude Code, ChatGPT | yes | no | P1 | implemented | `capabilities/compact.capability.yaml` |
| artifacts | artifacts | Claude, ChatGPT, Genspark | yes | no | P1 | implemented | `schemas/artifact.schema.yaml` |
| local_research | research | Genspark, Manus | partial | no | P2 | implemented | `schemas/research_result.schema.yaml` |
| browser_optional | optional_browser | Manus, OpenClaw | partial | optional | P3 | planned | `capabilities/browser_optional.capability.yaml` |
| local_model_provider | model | OpenClaw, Ollama apps | yes | no | P0 | implemented | `capabilities/local_model.capability.yaml` |

Rules:

- core features must work without a cloud API key.
- network and external SaaS providers are optional adapters.
- file write, delete, terminal, and git push require a policy gate.
- UI receives capabilities and component contracts from catalog APIs, not hard-coded assumptions.
