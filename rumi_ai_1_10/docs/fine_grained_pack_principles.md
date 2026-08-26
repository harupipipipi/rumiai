# Global Pack Architecture Principles

Tracking: #1145

## Decision

Rumi will replace feature-heavy `defaultspack` ownership with independently installable packs connected through versioned global contracts.

```text
Kernel
  manifest loading, verification, typed contract registry, IPC,
  capability-token authority, storage namespaces, lifecycle supervision

Packs
  service, adapter, runtime, policy, UI, content, provider, compatibility

Profiles
  capability intent -> contract resolution -> version/hash lockfile
```

The kernel does not know what AI, tools, prompts, chat, memory, or frontend mean. It knows contracts, providers, operations, schemas, callers, resources, events, trust, and capability tokens.

## Invariants

1. Runtime code must not import another pack's source tree.
2. Runtime consumers must not branch on another pack's `pack_id`.
3. Discovery reads manifests and schemas only; it must not execute provider code.
4. Only manifests, bundles, lockfiles, migration maps, compatibility shims, and repository tests may name implementation packs.
5. Domain services do not know whether they are projected as tools, UI, HTTP routes, CLI commands, or agent capabilities.
6. Adapter packs own contract-to-contract projections.
7. Frontend modules use global UI/action/data-source contracts and do not know backend implementation packs.
8. AI routing consumes provider descriptors, health, capabilities, cost, and policy—not provider packages.
9. Tool routing consumes definitions, guard decisions, authority tokens, and executor contracts—not domain packages.
10. Read/write and observe/control authorities are split when their risk differs.
11. Every loader uses one `ResolvedProfile.effective_pack_set`; no active profile scans every installed sibling pack.
12. Snapshots include every resolved route, UI module, tool, prompt, provider, model catalog, resource, version, and hash.
13. Secrets use scoped handles rather than broad environment injection.
14. Storage uses pack namespaces and service APIs rather than sibling file reads.
15. Compatibility preserves public IDs and data without preserving hidden feature ownership.

## Contract IDs

Canonical form:

```text
rumi.<contract-kind>.<domain>.<capability>.v<major>
```

Examples:

```text
rumi.action.ai.generate.v1
rumi.service.ai.provider.v1
rumi.event.ai.stream.v1
rumi.action.tool.invoke.v1
rumi.resource.prompt.definition.v1
rumi.ui.route.v1
rumi.storage.conversation.v1
rumi.policy.tool.guard.v1
rumi.transport.http.route.v1
```

Older global names may exist only as explicit compatibility aliases.

## Cardinality

- `one`: exactly one selected provider
- `many`: all matching providers
- `keyed`: selected by stable instance key
- `chain`: ordered middleware, guards, transforms, or contributors
- `fanout`: all matching event sinks
- `optional`: absence does not invalidate the parent capability

Ambiguous required `one` contracts are errors. Optional gaps remain visible in diagnostics.

## Pack boundaries

A pack is the install, signature, permission, storage, isolation, release, ownership, and failure boundary. Small implementation units with identical boundaries remain components in one pack.

- **Service:** owns state or domain execution.
- **Adapter:** translates global contracts without owning domain state.
- **Runtime:** owns orchestration or execution lifecycle.
- **Policy:** contributes policy or guard-chain entries.
- **UI:** contributes routes, renderers, commands, settings, or data sources.
- **Content:** owns prompts, profiles, workflows, schemas, examples, and catalogs; no broad authority.
- **Provider:** implements an interchangeable provider contract.
- **Compatibility:** aliases and migrates legacy IDs, files, routes, and imports.

## Manifest and handles

`rumi.pack.v3` declares identity, version, kind, trust, isolation, provided/required contracts, entrypoint metadata, schemas/resources, permissions, compatibility aliases, UI modules, and storage ownership.

Discovery validates data only. Code loads after profile resolution, verification, and authority establishment.

Vocabulary-neutral clients:

```text
ServiceHandle
ActionClient
EventClient
ResourceClient
```

Calls carry caller identity, profile, operation, argument hash, resource scope, deadline, cancellation token, and capability token where required.

## Completion bar

The migration is incomplete while any of the following remain:

- cross-pack runtime imports
- foreign pack-ID branches in consumers
- product imports in the frontend host
- direct implementation URLs in feature UI
- provider-specific branches in AI gateway/router core
- concrete-service branches in tool broker core
- runtime service imports of UI/tool registries
- implicit all-installed-pack discovery
- broad secret environment injection
- sibling storage reads

Every final Wave PR must include startup evidence.

**起動テストを必ず行ってください。**