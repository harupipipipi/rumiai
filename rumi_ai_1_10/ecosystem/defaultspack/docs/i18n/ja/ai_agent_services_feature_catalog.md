<!-- docs-i18n-links:start -->
[EN](../../ai_agent_services_feature_catalog.md) | [JP](./ai_agent_services_feature_catalog.md) | [KR](../ko/ai_agent_services_feature_catalog.md) | [CN](../zh-cn/ai_agent_services_feature_catalog.md)
<!-- docs-i18n-links:end -->

# AI Agent Services Feature Catalog

defaultspack の標準語彙として、現代 AI agent 系サービスの機能をローカル優先で整理する。

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

ルール:

- コア機能はクラウド API キーなしで動作する必要があります。
- ネットワークおよび外部 SaaS プロバイダーはオプションのアダプターです。
- ファイルの書き込み、削除、ターミナル、および git プッシュにはポリシー ゲートが必要です。
- UI は、ハードコーディングされた前提ではなく、カタログ API から機能とコンポーネント コントラクトを受け取ります。
