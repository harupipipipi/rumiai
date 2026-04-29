# AI Agent Services Feature Catalog

This catalog maps modern agent-service features into defaultspack targets. Core features stay local-first; network, SaaS, and API-key features are optional providers.

| id | category | local | api | priority | status | defaultspack target |
| --- | --- | --- | --- | --- | --- | --- |
| plan_mode | agent_core | yes | no | P0 | implemented | schemas/agent_plan.schema.yaml, prompts/planner.system.md |
| step_execution | agent_core | yes | no | P0 | implemented | blocks/agent, domain/agent |
| approve_reject_retry | safety | yes | no | P0 | implemented | blocks/agent, blocks/tool |
| workspace_files | file_workspace | yes | no | P0 | implemented | blocks/coding, capabilities/local_file.capability.yaml |
| terminal_exec | terminal | yes | no | P0 | implemented | blocks/coding/terminal_exec.py |
| git_status_diff_commit | git | yes | no | P0 | implemented | blocks/coding/git_*.py |
| memory | memory | yes | no | P1 | implemented | blocks/memory, capabilities/memory.capability.yaml |
| project_workspace | project | yes | no | P1 | cataloged | profiles/local_agent.profile.yaml |
| context_compact | compact | yes | no | P0 | implemented | blocks/chat/summarize_and_trim.py |
| artifacts | artifact | yes | no | P1 | cataloged | schemas/artifact.schema.yaml |
| local_research | research | yes | no | P2 | partial | blocks/knowledge, capabilities/research.capability.yaml |
| browser_use | browser_optional | partial | optional | P3 | optional | capabilities/browser_optional.capability.yaml |
| local_model | model | yes | no | P0 | implemented | extensions/llm/providers/* |
| safety_audit | safety | yes | no | P0 | implemented | blocks/tool, user_data/audit |
