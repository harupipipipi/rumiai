# Local Agent Implementation Plan

P0 is now represented by `profiles/local_agent.profile.yaml`, local-first prompts, schemas, and capability manifests. Existing blocks provide chat, agent, coding, tool, memory, knowledge, prompt, media, frontend, and dev behavior.

## Phases

1. Catalog: load `capabilities/*.capability.yaml` through `domain/capability/catalog.py`.
2. Profile: enable `defaultspack.local_agent` with local_file, terminal, git, memory, project, artifact, compact, local_model, and safety.
3. Plan and step: use `schemas/agent_plan.schema.yaml`, `schemas/agent_step.schema.yaml`, and existing `blocks/agent`.
4. File authoring: use existing coding blocks, artifact schemas, diff previews, and rollback-oriented prompts.
5. Terminal and git: use coding terminal/git blocks with safety policy.
6. Memory and project: use memory blocks plus project profile metadata.
7. Compact: use chat summarize/auto_trim and compact prompt.
8. Research and artifact: keep local search in knowledge and optional providers behind approval.
9. UI: expose tools, widgets, capabilities, settings, and previews through the frontend registry.
