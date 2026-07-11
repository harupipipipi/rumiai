# Provider Completion Program

Issue: #1171  
Target branch: `soon`  
Primary active implementation PR: #1155

## What “complete” means

The provider system is complete when every provider registered in rumiai has one canonical owner and passes the same machine-enforced contract:

- authoritative inventory;
- exact provider/model identity;
- account, project, region, plan, endpoint and server isolation;
- capability provenance;
- correct task typing;
- provider-specific request compilation;
- explicit Settings connection;
- stable errors;
- privacy-safe caching and performance measurements;
- Windows, macOS and Linux tests;
- unified picker, search, recommendation, routing and invocation behavior;
- required coverage CI.

Completeness does **not** mean maintaining a permanent hard-coded list of every vendor and model. The market changes too quickly. It means:

1. all registered IDs and all `tier=required` entries in `provider_completion_matrix.json` are complete;
2. generic connection families cover future compatible endpoints honestly;
3. adding a provider requires a machine-readable record and tests before it can be enabled.

## Current blockers

The `soon` branch still contains multiple compatibility sources:

- component manifests under `domain/providers`;
- extension manifests and model files;
- `_CURATED_PROVIDER_METADATA`;
- `_CURATED_PROVIDER_MODELS`;
- generated OpenAI-compatible classes;
- dedicated provider classes;
- runtime-discovered catalogs.

These sources may disagree about ownership, defaults, capability support and whether a provider can invoke. A provider is not complete merely because its name appears in a dropdown.

The current compatibility table still contains invented static defaults for dynamic local providers. Dynamic inventory work must remove these claims rather than hiding them behind a higher-priority runtime layer.

## Program order

```text
#1155 gateway routing and live catalogs
  -> direct-provider performance telemetry
  -> Ollama native inventory
  -> vLLM served inventory
  -> llama.cpp native/router inventory
  -> generic OpenAI-compatible connections
  -> direct hosted provider completion
  -> enterprise provider completion
  -> hosted expansion
  -> self-hosted expansion
  -> provider coverage gate
```

Coding backends remain separate:

```text
#1140 Codex App Server
#1141 Claude Agent SDK
```

They are not `llm_provider` implementations.

## Required provider record

Every provider must have one matrix record declaring:

- canonical ID and aliases;
- family;
- inventory strategy;
- inventory authentication and scope;
- invocation authentication;
- supported task families;
- dedicated or shared adapter;
- cache scope;
- official sources and verification date;
- implementation branch and issue;
- completion status.

See `provider_completion_matrix.json`.

## Canonical ownership

A provider has one canonical owner:

```text
provider identity/configuration -> provider component manifest
runtime model inventory         -> provider/native/control-plane API or generated official snapshot
verified exceptions/defaults    -> small curated overlay
user policy                     -> Settings
performance facts               -> dedicated privacy-safe telemetry store
```

Hard-coded compatibility tables are migration aids only. They must not remain authoritative after the canonical provider component is complete.

## Inventory contract

A complete provider:

- consumes every page/cursor;
- preserves exact IDs, case, namespace, tag, variant, region and plan;
- types chat, embedding, rerank, moderation, image, video, transcription and TTS separately;
- represents unknown support as unknown with provenance;
- never downloads, loads, warms or invokes a model during discovery;
- isolates cache entries by every visibility dimension;
- exposes fresh, stale, disconnected and connected-empty states;
- retains a bounded last-known-good cache;
- resolves defaults against the current visible inventory;
- never publishes one account’s catalog as a universal catalog.

## Invocation contract

A complete provider:

- strips the rumiai provider prefix exactly once;
- uses a dedicated compiler whenever semantics diverge;
- maps reasoning, tool calls, structured output, multimodal blocks and task endpoints explicitly;
- does not refresh inventory on the critical inference path;
- normalizes auth, quota, retirement, unsupported-task, schema, timeout and network failures;
- preserves explicit per-request options over persisted defaults;
- does not silently coerce an unknown task into chat.

## Gateway contract

- Auto remains the default.
- Auto emits no restrictive upstream routing object.
- rumiai provider selection and gateway upstream-provider selection are separate.
- OpenRouter and Vercel keep separate slug namespaces.
- Settings and `/provider` use the same versioned persistence model.
- gateway `/fast` uses official throughput/TPS routing.
- direct `/fast` uses measured successful samples only.

## Performance telemetry

Telemetry may store aggregate timing and token counts only. It may not store:

- prompt or response text;
- reasoning text;
- tool arguments/results;
- images/files;
- API keys or auth headers;
- raw account IDs.

Measurements are isolated by provider, endpoint and opaque/HMAC connection scope. Failed, cancelled, replayed and incomplete requests are not samples.

## Testing and CI

Required tests never contact real external services.

Each provider fixture covers:

- pagination;
- schema evolution;
- punctuation-heavy IDs;
- non-chat tasks;
- auth states;
- stale cache;
- default removal;
- two-account isolation;
- error normalization;
- Windows-safe paths and concurrency.

The final coverage job calculates, after a successful authoritative fixture refresh:

```text
missing = authoritative visible IDs - unified rumiai IDs
stale   = invokable rumiai IDs - authoritative visible IDs
```

Missing IDs, duplicate canonical IDs, invalid defaults, cross-account leaks and secret-bearing caches are hard failures.

## PR policy

- one responsibility per PR;
- base every new branch on the latest `soon`;
- port stale branches file-by-file;
- include official source links and verification dates;
- keep PRs Draft while required CI is red;
- never call a provider complete based only on unit tests for one model;
- update #1171 with the branch, PR, validation and remaining blockers.

## Closure

Do not close #1171 when this document lands. Close it only when all required matrix providers are complete and the provider coverage gate is required and green on `soon`.
