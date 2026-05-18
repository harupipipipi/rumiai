# Flow Spec

A flow document has `flow_id`, optional `version` and `description`, `inputs`, `outputs`, and ordered `steps`.

Supported step fields:

- `id`: stable step identifier.
- `type`: `function`, `handler`, `tool`, `prompt`, or `permission_filter`.
- `function`: callable alias for function steps, such as `defaults.ai.complete`.
- `input`: literal values or template references.
- `when`: optional condition expression.
- `output`: variable name written by the step.
- `on_error`: optional error handling policy.

Profile-scoped chat flows should load the active profile and workspace before prompt, tool, permission, routing, completion, persistence, or audit steps. Permission filters must run before tool-enabled AI calls.
