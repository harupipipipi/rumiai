<!-- docs-i18n-links:start -->
[EN](../../ai_agent_services_feature_catalog.md) | [JP](../ja/ai_agent_services_feature_catalog.md) | [KR](./ai_agent_services_feature_catalog.md) | [CN](../zh-cn/ai_agent_services_feature_catalog.md)
<!-- docs-i18n-links:end -->

# AI Agent Services Feature Catalog

defaultspack의 표준 어휘로서 현대 AI agent 계 서비스의 기능을 로컬 우선으로 정리한다.

|id | category | inspired_by | local | api | priority | status | defaultspack target |
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

규칙:

- 핵심 기능은 클라우드 API 키 없이도 작동해야 합니다.
- 네트워크 및 외부 SaaS 공급자는 선택적 어댑터입니다.
- 파일 쓰기, 삭제, 터미널 및 git push에는 정책 게이트가 필요합니다.
- UI는 하드 코딩된 가정이 아닌 카탈로그 API로부터 기능 및 구성 요소 계약을 받습니다.
