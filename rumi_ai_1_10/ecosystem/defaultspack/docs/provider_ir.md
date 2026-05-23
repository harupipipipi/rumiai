# Provider IR

Rumi Chat IR v2 is the provider-neutral contract between ChatStore and provider
adapters. It lets defaultspack preserve richer chat state than the legacy
OpenAI-ish StandardMessage format while keeping existing public APIs stable.

## Storage Boundary

ChatStore remains provider-agnostic. It stores Rumi messages and workspace
artifacts, not provider payloads. Stored messages are converted with:

```text
stored_messages_to_ir(conversation_id, messages)
ir_to_legacy_standard_messages(ir)
legacy_standard_messages_to_ir(messages)
ir_to_stored_messages(ir)
```

`convert_to_standard()` still exists and delegates through IR so old callers see
the same StandardMessage output.

## Rumi Chat IR v2

IR objects carry explicit `schema_version` fields. Core models include
`RumiChatIR`, `RumiIRMessage`, `RumiIRBlock`, `RumiToolCallIR`,
`RumiToolResultIR`, `RumiUsageIR`, `RumiResponseIR`, `RumiStreamEventIR`,
`ProviderWarning`, `DroppedFeature`, and `BridgeAction`.

Supported block types include text, image, audio, video, file, PDF, tool call,
tool result, reasoning, citation, event, refusal, and unknown. Unknown blocks
are preserved. Reasoning blocks are internal by default and are not injected
into prompts unless marked model-visible.

## Capabilities And Planning

Provider manifests live in `domain/ai_client/capabilities/manifests/`. The
registry merges manifest defaults, runtime model metadata, and quirks such as
token parameter names, reasoning behavior, tool-name rules, system-role mapping,
stream usage support, provider file IDs, built-in tools, and MCP tools.

The request planner records degradation instead of silently dropping features:

- unsupported developer role: merge into system with a labelled section;
- unsupported system role: inject a guarded prefix into the first user message;
- unsupported reasoning: disable reasoning params and record a dropped feature;
- unsupported image/PDF/audio/file upload: create bridge actions or warnings;
- unsupported provider tools: omit provider tools and record requested tools;
- unsupported parallel tool calls: serialize the tool loop;
- unsupported strict JSON schema: downgrade to best-effort JSON;
- invalid provider tool names: alias through Tool Protocol v2.

## Provider Compiler

Provider Compiler v2 compiles planned requests into provider payloads and parses
responses back into Rumi response IR. Implemented compiler families are:

- OpenAI Chat;
- OpenAI Responses;
- OpenAI-compatible;
- Google OpenAI-compatible;
- Google native Generative API;
- Anthropic Messages;
- Bedrock Converse;
- local OpenAI-compatible.

The compiler path is guarded. Use `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1` to
opt in. Use `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1` to force rollback.

## Tool Protocol v2

Rumi tool definitions and provider tool definitions are separate. The protocol
tracks original names and provider aliases, decodes provider tool calls back to
Rumi tool calls, and encodes tool results as IR blocks. Tool results may include
text, JSON, images, files, artifacts, approval-required state, and truncation
metadata for large outputs.

## Attachment/File v2

Attachments retain the legacy `workspace_attachments` metadata shape while also
writing an attachment v2 manifest under the conversation workspace. Attachment
records include ID, name, MIME type, size, workspace path, source fields,
representations, provider refs, and creation time. Raw huge data URLs are not
stored in history metadata when avoidable.

## Provider Traces

Trace artifacts are written under:

```text
user_data/shared/chat/conversations/<conversation_id>/workspace/provider_traces/
```

They include schema version, request ID, provider, model, API family, IR schema,
capability summary, planning metadata, dropped features, bridge actions,
warnings, sanitized payload, response summary, and timestamps. API keys,
authorization headers, tokens, credentials, passwords, secrets, and image base64
payloads are redacted.
