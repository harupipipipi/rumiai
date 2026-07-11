# Provider Completion Acceptance Contract

A provider is **not complete** until every applicable gate below passes.

## Identity

- [ ] one canonical provider ID;
- [ ] aliases resolve one way to the canonical ID;
- [ ] no duplicate manifest/runtime/compatibility owner;
- [ ] provider-qualified model IDs preserve the complete upstream ID;
- [ ] outbound model IDs remove the provider prefix exactly once.

## Inventory

- [ ] authoritative source documented and date-verified;
- [ ] all pages/cursors consumed;
- [ ] inventory authentication separated from invocation authentication;
- [ ] account/project/region/plan/server/connection visibility represented;
- [ ] exact IDs, variants, tags, case and namespaces preserved;
- [ ] non-chat model types retained;
- [ ] unknown capability values carry provenance;
- [ ] zero-model and disconnected states distinguished;
- [ ] last-known-good cache bounded and marked stale;
- [ ] discovery causes no load, download, warmup or inference;
- [ ] defaults resolve against the visible inventory.

## Invocation

- [ ] provider-specific request compiler selected;
- [ ] all supported task endpoints implemented;
- [ ] reasoning mapping verified;
- [ ] tool-call and parallel-tool behavior verified;
- [ ] structured-output behavior verified;
- [ ] multimodal block mapping verified;
- [ ] stream and non-stream usage normalized;
- [ ] explicit request options override settings without mutating them;
- [ ] inventory is not refreshed on the critical inference path;
- [ ] stable typed errors exist for auth, quota, retirement, task, schema, timeout and network failures.

## Settings and UI

- [ ] provider connection appears in the correct Settings section;
- [ ] credential state exposes no secret;
- [ ] inventory status, count and freshness visible;
- [ ] refresh is explicit and side-effect free;
- [ ] picker, search and recommendation use the same catalog;
- [ ] model type filters prevent non-chat models entering chat pickers;
- [ ] regional/plan routes are visible without being collapsed into false global availability;
- [ ] gateway upstream selection is separate from rumiai provider selection;
- [ ] saved values migrate idempotently.

## `/provider` and `/fast`

- [ ] `/provider` status has no side effects;
- [ ] canonical command and typo aliases resolve consistently;
- [ ] invalid/ambiguous inputs return typed errors;
- [ ] gateway Auto sends no restrictive object;
- [ ] OpenRouter and Vercel retain separate upstream slugs;
- [ ] gateway fast maps to official throughput/TPS routing;
- [ ] direct fast uses measured successful samples only;
- [ ] sample threshold, capability and context filters are applied;
- [ ] no safe candidate means no model switch.

## Privacy and security

- [ ] cache key includes every visibility dimension;
- [ ] two-account fixture proves isolation;
- [ ] API keys, tokens and auth headers never enter logs/caches;
- [ ] prompts, responses, reasoning, tools, images and files never enter performance telemetry;
- [ ] account scope uses an opaque ID or keyed HMAC, not a raw reversible identifier;
- [ ] corrupted cache fails closed or uses a validated backup;
- [ ] user-provided endpoints cannot escape allowed URL/network policy;
- [ ] provider discovery cannot bypass Authority, local guard, workspace jail or capability trust.

## Tests

- [ ] unit tests use fixtures/fake servers only;
- [ ] pagination and schema evolution;
- [ ] punctuation-heavy IDs;
- [ ] duplicate merge;
- [ ] default disappearance;
- [ ] stale cache;
- [ ] auth states;
- [ ] quota and retirement;
- [ ] non-chat typing;
- [ ] stream tool calls and usage;
- [ ] Windows paths, locks and process behavior;
- [ ] Linux/macOS behavior where applicable;
- [ ] frontend persistence and rendering;
- [ ] contract markers and bundle synchronization.

## Coverage

After a successful authoritative fixture refresh:

```text
missing = authoritative visible IDs - unified rumiai IDs
stale   = invokable rumiai IDs - authoritative visible IDs
```

- [ ] `missing` is empty;
- [ ] any `stale` entry has an explicit lifecycle/compatibility reason;
- [ ] duplicate canonical IDs are empty;
- [ ] invalid defaults are empty;
- [ ] cross-account leakage is empty;
- [ ] secret scan is empty;
- [ ] coverage JSON and Markdown artifacts are generated.

## Merge

- [ ] focused tests green;
- [ ] package tests green for all supported Python versions;
- [ ] contract/security checks green;
- [ ] frontend test/typecheck/build green when affected;
- [ ] Windows and Linux smoke green;
- [ ] PR body lists official sources and verification date;
- [ ] issue comment records exact validation;
- [ ] no unchecked acceptance item is hidden behind “follow-up” when it is part of the changed contract.
