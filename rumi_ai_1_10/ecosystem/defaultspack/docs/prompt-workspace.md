# Prompt Workspace API

Defaultspack exposes prompt visibility, toggles, editing, versions, and trace
inspection through Rumi functions and matching HTTP routes.

## Chat Response Prompt Usage

During a chat turn, defaultspack builds an AI Input Graph trace before provider
payload assembly. The trace is saved through `AiInputTraceStore`, and a compact
prompt usage payload is attached to the final assistant message at
`metadata.prompt_usage`. Message metadata keeps trace identifiers, counts, token
estimates, segment previews, and source/status metadata. It does not duplicate
full prompt text or tool schemas into every chat message.

The chat disclosure reads the message metadata first. If text is missing and the
metadata has a `trace_id`, it loads detail from
`GET /api/prompts/traces/{trace_id}`. Trace detail is redacted by default:
raw `effective_input` is not returned, and full prompt/conversation-derived
segment text appears only when the caller explicitly passes `include_text=true`.

## Functions

Read/inspect:

- `defaultspack:prompt_active` / `defaults.prompt.active`
- `defaultspack:prompt_trace_list` / `defaults.prompt.trace_list`
- `defaultspack:prompt_trace_get` / `defaults.prompt.trace_get`
- `defaultspack:prompt_editor_load` / `defaults.prompt.editor_load`
- `defaultspack:prompt_preview_toggle` / `defaults.prompt.preview_toggle`
- `defaultspack:prompt_versions` / `defaults.prompt.versions`
- `defaultspack:prompt_diff` / `defaults.prompt.diff`
- `defaultspack:prompt_lint_prompt` / `defaults.prompt.lint_prompt`
- `defaultspack:prompt_compact_prompt` / `defaults.prompt.compact_prompt`

Mutate:

- `defaultspack:prompt_toggle` / `defaults.prompt.toggle`
- `defaultspack:prompt_editor_save` / `defaults.prompt.editor_save`
- `defaultspack:prompt_create_override` / `defaults.prompt.create_override`
- `defaultspack:prompt_test` / `defaults.prompt.test`
- `defaultspack:prompt_rollback` / `defaults.prompt.rollback`

Mutating functions require prompt-specific caller capabilities. They do not
grant tool, terminal, browser, provider, or filesystem authority.

## HTTP Routes

All `/api/prompts/*` routes are marked sensitive. Local HTTP access therefore
goes through the same bearer-token guard as other sensitive defaultspack routes,
and browser-origin mutations require `X-Rumi-CSRF`.

- `GET /api/prompts/active`
- `GET /api/prompts/traces`
- `GET /api/prompts/traces/{trace_id}`
- `POST /api/prompts/toggle`
- `POST /api/prompts/preview-toggle`
- `GET /api/prompts/editor`
- `POST /api/prompts/editor/save`
- `POST /api/prompts/override`
- `POST /api/prompts/diff`
- `POST /api/prompts/test`
- `POST /api/prompts/{name}/rollback`
- Existing prompt routes remain available: update, delete, convert, lint,
  compact, build, context vars, conditional, inherit, versions, preview.

## Toggle Semantics

Prompt toggles write only to the selected profile's AI Input Graph:

```yaml
metadata:
  ai_input:
    disabled_edges: []
```

`prompt_toggle` removes the edge from `disabled_edges` when enabling and appends
the edge when disabling. `prompt_preview_toggle` compiles the patched graph but
does not save it.

`allow_disable: false` is enforced from prompt segment metadata. Disable
attempts for protected segments fail even if a client supplies an edited payload.

## Editing And Versions

Prompt Studio loads all prompt sources plus profile overrides. Editable
user-owned prompts are saved in place. Read-only pack, component, snapshot, and
extension prompts are saved as profile overrides under:

```text
profiles/<profile_id>/prompts/<prompt_id>.system.md
```

Each save records a version entry. Rollback restores the selected version's
previous body and records a new rollback version.

Prompt Studio sends the loaded `body_hash` as `expected_body_hash` for editable
prompts. First-time overrides assert that the override file is still missing.
The backend serializes writes with a per-prompt lock, checks the expected state,
uses collision-resistant version IDs, and writes both version records and prompt
files by atomic replacement. Stale saves fail with `PROMPT_WRITE_CONFLICT`
instead of overwriting newer prompt text.

## Studio Test Bench

`prompt_test` and `POST /api/prompts/test` run the same local inspection used by
the Prompt Studio Test tab. Inputs include `profile_id`, `prompt_id`, `draft`,
`user_text`, and `selected_tools`.

The response includes the active prompt usage summary, matched skill prompts,
selected tool-schema segments, prompt-to-tool candidates, and verdict cards. It
does not call a provider and does not execute tools. Prompt-to-tool candidates
mean the prompt or input made a tool look relevant; they are not permission,
provider attachment, or execution.

## Safety Boundary

Prompt text is not executable. It can be inspected, linted, compacted, edited,
diffed, overridden, and rolled back. It cannot call tools, mutate chat state,
grant permissions, choose providers, or bypass local approval and audit paths.
