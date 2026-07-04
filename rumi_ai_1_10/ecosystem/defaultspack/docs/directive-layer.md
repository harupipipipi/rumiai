# Directive Layer slash commands

Directive Layer is a conversation-scoped instruction layer set from chat:

- `/directive <instruction>`
- `/developer <instruction>`
- `/system <instruction>`
- `/sytem <instruction>`

The aliases all update the same `metadata.directive_layer` record on the
current conversation. The directive is not stored as an ordinary chat message.
This keeps request ordering explicit and avoids making user text look like a
runtime/controller instruction.

Clear the active directive with `/directive clear` or `/directive --clear`.
Aliases accept the same clear arguments.

## Request ordering

Model request materialization uses this order:

1. Rumi/controller directive
2. Conversation directive
3. Normal user content

The conversation directive is materialized as a developer/instructions-equivalent
message when the selected provider supports that role. Providers that only
support system messages receive a safe fallback where developer instructions are
merged into system-role text. The directive does not grant tool, file, network,
approval, or security bypass privileges.

## UI state

When a directive is active, the chat UI shows a Directive Layer card with the
current scope, the directive preview, and edit/clear controls. The copy calls it
a Rumi conversation directive rather than a provider-level hidden instruction.
