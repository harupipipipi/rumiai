# Prompt Workspace

Prompt Workspace is the user-facing surface for inspecting and managing the
passive prompt text that shaped an AI response.

## Chat Inspection

Every stored assistant response may include `metadata.prompt_usage`. The chat UI
renders this as **Prompt used**. Expanding it shows the prompt segments that were
active, disabled, gated, dropped by budget, or added at runtime.

Each segment records:

- `id`, `edge_id`, `prompt_id`, label, kind, port, and status.
- token estimate and provider input port.
- source, source type, source chain, and reason included.
- whether it can be disabled with `allow_disable`.
- whether it is editable, read-only, or override-only.
- preview text when the compact message metadata was captured.

Chat metadata intentionally does not duplicate full prompt bodies or tool
schemas. If a response has a `trace_id`, trace detail can be loaded later from
trace storage with `defaults.prompt.trace_get` or
`GET /api/prompts/traces/{trace_id}`. Trace detail is redacted by default and
does not return raw `effective_input`. Full segment text is returned only when
the caller explicitly passes `include_text=true`.

All `/api/prompts/*` HTTP routes are sensitive local routes. Reads require the
local bearer token when local auth is configured. Mutations with a browser
Origin also require the `X-Rumi-CSRF` header.

## Command Center

The compact Prompt Command Center shows the active prompt graph for the selected
profile/chat. Toggling a segment updates the active profile's AI Input Graph
configuration at:

```yaml
metadata:
  ai_input:
    disabled_edges:
      - edge:prompt:example->model_input:default.system
```

There is no parallel prompt toggle store. If `allow_disable` is `false`, the UI
and backend refuse to disable the edge.

## Prompt Studio

`/prompts` opens Prompt Studio. It has a navigator,
editor/test/preview/diff/usage workspace, and an inspector with source chain,
activation state, safety boundary, token cost, versions, and usage.

User-owned prompt files and profile overrides can be edited directly. Pack,
component, snapshot, and extension prompts are read-only. Saving a read-only
prompt creates a profile override instead of modifying the original.

Prompt Studio saves include the loaded `body_hash` as `expected_body_hash`.
The backend takes a per-prompt lock, verifies the expected hash or expected
missing override state, writes the version entry and prompt body with atomic
file replacement, and rejects stale saves with a prompt write conflict.
Rollbacks are also versioned so restoring a user prompt or removing a first
override leaves an audit trail.

The Test tab runs a local Studio test without calling a model. It accepts test
input text and selected tool ids, then shows:

- prompt segments that would be active for the test context.
- skill prompt segments matched by input triggers, explicit skill mentions, or
  selected tool scope.
- tool-schema segments for selected or locally recommended tools.
- deterministic prompt-to-tool candidates from prompt text and test input.
- the passive safety boundary proving prompt text did not attach or execute a
  tool.

Effective prompt priority is:

1. Profile override in `profiles/<profile_id>/prompts/`.
2. Profile snapshot in `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`.
3. Pack/component/extension default.

Profile overrides win over snapshots and pack defaults.

## Safety Model

Prompts remain passive text. They cannot grant permissions, call tools, select
providers, mutate chat state, or bypass approval. Tools, functions, providers,
permission grants, and authority checks remain separate runtime capabilities.
