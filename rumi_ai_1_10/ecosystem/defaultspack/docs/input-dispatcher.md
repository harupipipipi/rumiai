# Input Dispatcher

`submit_input` remains the public compatibility entrypoint, but the canonical
path is now:

```text
RumiInputEnvelope
  -> dispatch_input
  -> action_registry
  -> delivery.action_id handler
```

## Envelope shape

Every inbound turn is normalized into `RumiInputEnvelope`.

- `source`: who or what produced the input
- `target`: conversation, route, or runtime target
- `delivery`: action selection metadata
- `input`: primary text payload
- `params`: action-specific structured data
- `tools`: optional explicit tool selection
- `attachments`: files or images carried with the turn
- `metadata`: audit and provider metadata

`delivery.action_id` defaults to `chat.message`.

## Built-in actions

- `chat.message`: normal user message flow
- `run.instruction`: enqueue a runtime steer/instruction
- `run.interrupt`: urgent runtime instruction with room for future pause/cancel/redirect semantics
- `agent.delegate`: start one delegated agent run from a structured payload
- `model.switch`: persist a conversation default model change
- `model.route`: set a turn-scoped route override

Unknown `delivery.action_id` values return a structured error instead of
falling through provider-specific logic.

## Compatibility

- Existing `submit_input(...)` callers still work.
- Existing chat send behavior still routes through the same stores and blocks.
- Legacy `subagent`-named call sites now use `agent.delegate` or
  `model.call`-style utility routing internally.
