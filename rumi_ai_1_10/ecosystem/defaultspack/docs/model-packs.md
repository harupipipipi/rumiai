# Model Packs And `model.call`

Model routing now supports `modelpack/<id>` in addition to plain model ids and
legacy composite models.

## Model pack shape

`ModelPack` is a small routing manifest:

- `id`
- `display_name`
- `members`
- `rules`
- `fallback`
- optional budget, safety, and metadata

The first implementation focuses on fallback-chain style selection, while
keeping room for ensemble or review-chain modes.

## Resolution

`ModelRouter` and `AIClient` resolve `modelpack/<id>` using the current turn:

- image input / vision needs
- tool calling needs
- requested thinking level
- task hints
- custom pack rules
- fallback members

Legacy `composite_models` stay compatible and can be treated as an internal
pack-like structure.

## `model.call`

`model.call` is the bounded utility path for "ask another model a question."

- no tool access by default
- accepts `required_capabilities`, `model_hint`, `output_schema`, `max_tokens`
  and `attachments`
- strips hidden metadata and secrets before forwarding
- enforces recursion depth limits

Use the boundaries this way:

- `model.call`: bounded question to another model
- `agent.delegate`: delegated tool-capable work
- `model.switch`: persistent conversation default change
- `model.route`: turn-scoped routing override
