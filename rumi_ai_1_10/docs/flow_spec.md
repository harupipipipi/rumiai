# Flow Spec

A flow document has `flow_id`, optional `version` and `description`, `inputs`, `outputs`, and ordered `steps`.

Canonical step types are `function`, `subflow`, `branch`, and `parallel`.
Legacy handler/tool/prompt steps are compatibility paths and must not be the
authoring surface for new defaultspack flows.

Supported function step fields:

- `id`: stable step identifier.
- `type`: `function`.
- `function`: callable alias for function steps, such as `defaults.ai.complete`.
- `input`: literal values or template references.
- `when`: optional condition expression.
- `output`: variable name written by the step.
- `on_error`: optional error handling policy.

Profile-scoped chat flows should load the active profile and workspace before prompt, tool, permission, routing, completion, persistence, or audit steps. Permission filters must run before tool-enabled AI calls.

Prompt resolution is a function step, not a prompt execution step. The standard
chat turn calls `defaults.prompt.load_effective` or
`defaults.prompt.resolve_for_conversation` after the profile workspace is
available, then passes that text into AI request construction. Effective prompt
resolution uses profile override, profile snapshot, then pack default priority.
