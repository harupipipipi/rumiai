<!-- docs-i18n-links:start -->
[EN](./ai_client.md) | [JP](./i18n/ja/ai_client.md) | [KR](./i18n/ko/ai_client.md) | [CN](./i18n/zh-cn/ai_client.md)
<!-- docs-i18n-links:end -->

# AI Client Design

The defaultspack AI client is the boundary between flows and model providers. It
normalizes model selection, provider credentials, request construction,
streaming events, and provider responses. It does not own prompts, tools, memory,
or UI behavior; those are supplied by the calling flow and profile workspace.

## Responsibilities

- Resolve a requested model profile into provider, model id, capability metadata,
  and runtime settings.
- Build provider requests from normalized messages, tool schemas, attachments,
  and parameters supplied by upstream blocks.
- Route calls to provider adapters and return normalized completion results.
- Normalize streaming deltas into stable event names that chat and UI layers can
  consume.
- Keep API keys in the existing provider key store. Model profiles and docs must
  not embed secrets.

## Non-Responsibilities

- Prompt authoring and prompt mutation belong to the prompt layer.
- Tool discovery, permission filtering, and approval handling belong to tool and
  permission blocks before an AI request is built.
- Flow orchestration belongs to the flow engine.
- UI widgets and animations belong to model/profile UI metadata or frontend
  renderers. The AI client may pass metadata through; it should not define the
  product experience.

## Request Contract

`defaults.ai.build_request` produces the normalized request consumed by
`defaults.ai.complete`:

```json
{
  "conversation_id": "c1",
  "model": "stub/default",
  "messages": [
    {"role": "system", "content": "profile-scoped prompt"},
    {"role": "user", "content": "hello"}
  ],
  "tools": [],
  "params": {}
}
```

The caller is responsible for passing an effective system prompt and already
filtered tools. The AI client should treat those inputs as data, not as a reason
to read or mutate prompt/tool stores.

## Model Profiles

Model profiles identify provider-specific models and capabilities such as
vision, tool calling, thinking support, context limits, and routing hints.
Routing may recommend a different model profile when the input requires
capabilities the selected profile lacks. Provider keys remain outside profile
documents.

## Provider Discovery

Provider discovery is manifest-first. OpenAI-compatible providers can be added
with `extensions/llm/providers/<provider_id>/manifest.json` plus
`models/*.json`; the runtime instantiates `OpenAICompatibleProvider` from that
manifest when credentials are configured. Custom provider protocols may still
use an explicit Python entrypoint.

Curated provider metadata is fallback compatibility data. It may fill in legacy
display names or defaults, but manifests and model definitions are the canonical
source for new providers.

## Streaming Events

Provider-specific streaming chunks are normalized before they reach chat/UI
consumers. Common event names include:

- `message_start`
- `thinking_start`
- `thinking_delta`
- `thinking_end`
- `content_start`
- `content_delta`
- `tool_call_start`
- `tool_call_delta`
- `tool_call_end`
- `message_end`
- `error`

Event payloads should preserve provider details under metadata when useful, but
the top-level event name and text/tool fields should stay provider-neutral.

## Profile UI Metadata

If a model profile supplies optional UI metadata such as `ui/events.ui.yaml`, the
streaming layer may attach resolved widget hints to normalized event payloads.
This is a pass-through contract:

- the file is optional;
- missing metadata must preserve existing streaming behavior;
- templates may be resolved from the current event data;
- frontend renderers decide whether to use or ignore widget hints.

The AI client must not ship hardcoded animations like "Thinking..." as provider
logic. Profiles can describe those hints; the AI client only carries them.

## Failure Behavior

Provider errors should be normalized into structured error results that include
the provider id, model/profile id, retryability when known, and a user-safe
message. Missing credentials should fail closed before a network call. Unsupported
features should be reported as capability errors rather than silently dropping
tools, images, or thinking parameters.
