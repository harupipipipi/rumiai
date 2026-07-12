# Pack Architecture Wave 5 — AI Runtime Ownership

Wave 5 separates AI routing, model/provider catalog, saved model profiles,
provider connections, credentials, and protocol execution. It does not add a
provider or change a catalog entry.

## Authoritative boundaries

- `rumi_ai_gateway_pack`: provider-neutral generate/stream routing, capability
  matching, cost/health policy, normalized results, diagnostics, and replay-safe
  failover.
- `rumi_model_catalog_pack`: immutable provider/model descriptors. Catalog
  resources are digest verified and never import execution code.
- `rumi_model_registry_pack`: saved model profiles and finite aliases with
  revision-guarded atomic writes.
- `rumi_provider_registry_pack`: configured provider instances and conservative
  verified health evidence. Remote state is `unknown` until verified.
- `rumi_credential_broker_pack`: encrypted opaque handles bound to consumer,
  provider instance, scope, and expiry.
- `rumi_provider_adapters_pack`: registry-selected protocol execution only. It
  owns no catalog, connection, or credential state.

Defaultspack retains finite response-shape and HTTP/function adapters. Catalog,
completion, stream, provider status, health, and approved provider-key writes
are forwarded through selected global contracts. Provider-key approval binds a
SHA-256 digest rather than persisting or replaying secret material.

## Contracts

- `rumi.service.ai.generate.v1`
- `rumi.service.ai.stream.v1`
- `rumi.resource.ai.routing.diagnostics.v1`
- `rumi.resource.ai.model.catalog.v1`
- `rumi.resource.ai.model.profile.v1`
- `rumi.action.ai.model.profile.manage.v1`
- `rumi.action.ai.model.registry.migrate.v1`
- `rumi.resource.ai.provider.registry.v1`
- `rumi.action.ai.provider.registry.manage.v1`
- `rumi.resource.ai.provider.health.v1`
- `rumi.service.ai.provider.generate.v1`
- `rumi.service.ai.provider.stream.v1`
- `rumi.service.credential.resolve.v1`
- `rumi.action.credential.manage.v1`
- `rumi.action.credential.migrate.v1`
- `rumi.resource.credential.status.v1`

Catalog selection and adapter execution use independent artifact revisions.
The gateway contains no concrete provider or provider-pack-ID branch. Cost
policy rejects unknown costs when a maximum is requested. Health evidence older
than the request policy becomes `unknown`. Unsafe failover is disabled unless
the caller opts in, supplies an idempotency key, uses no tools, and receives a
retryable provider-neutral error.

## Migration and rollback

Model profiles, aliases, and provider connections accept normalized explicit
source payloads only when their deterministic source hashes match. Each owner
retains a mode-`0700` backup and mode-`0600` state, records the migration ID,
and exposes marker-bound rollback.

Credential migration encrypts the complete import in one owner-store write.
Only redacted handles are returned. Rollback restores the exact encrypted
pre-migration snapshot. New connection writes create the handle first and
revoke it if the revision-guarded registry write fails.

Legacy defaultspack AI modules remain migration/compatibility source until the
Wave 10 facade cleanup. They must not be used as authoritative operational
writers; the active compatibility routes use the new owners.

## Data ownership matrix

| Resource | Authoritative pack | Schema version | Storage | Backup | Migration | Rollback | Retention | Export/import |
|---|---|---:|---|---|---|---|---|---|
| profiles | core profile owner | resolved-profile v1 | existing profile store | exact copy | Wave 2 | Wave 2 | existing | JSON |
| settings | feature owner through settings contract | contribution v1 | owner storage | owner policy | per feature | owner rollback | owner policy | contract-defined |
| secrets | `rumi_credential_broker_pack` | credential store v1 | encrypted pack namespace | encrypted owner-only snapshot | source-hash explicit import | exact encrypted restore | until revoke/rollback | secret export prohibited |
| conversations | existing conversation owner | existing | unchanged | unchanged | Wave 7 | Wave 7 | unchanged | unchanged |
| messages | existing conversation owner | existing | unchanged | unchanged | Wave 7 | Wave 7 | unchanged | unchanged |
| prompts | `rumi_prompt_studio_pack` | prompt-studio store v1 | pack/profile namespace | owner-only | Wave 4 | Wave 4 | profile lifetime | contract JSON |
| tools | defaultspack pending Wave 6 | existing | unchanged | unchanged | Wave 6 | Wave 6 | unchanged | unchanged |
| provider connections | `rumi_provider_registry_pack` | provider-registry v1 | pack/profile namespace | owner-only | source-hash explicit import | marker-bound | until delete/rollback | contract JSON |
| model profiles/aliases | `rumi_model_registry_pack` | model-registry v1 | pack/profile namespace | owner-only | source-hash explicit import | marker-bound | until delete/rollback | contract JSON |
| provider/model catalog | `rumi_model_catalog_pack` | catalog v2 | signed/digest-pinned pack resources | git/artifact revision | mechanical ownership relocation | pinned pack revision | pack version | declarative JSON |
| AI routing diagnostics | `rumi_ai_gateway_pack` | diagnostics v1 | bounded in-memory projection | none | none | restart/remove pack | process lifetime | redacted read-only |
| artifacts | existing artifact owner | existing | unchanged | unchanged | later Wave | later Wave | unchanged | unchanged |
| schedules | defaultspack pending Wave 9 | existing | unchanged | unchanged | Wave 9 | Wave 9 | unchanged | unchanged |
| memory | defaultspack pending Wave 7 | existing | unchanged | unchanged | Wave 7 | Wave 7 | unchanged | unchanged |
| knowledge | defaultspack pending Wave 7 | existing | unchanged | unchanged | Wave 7 | Wave 7 | unchanged | unchanged |
| Company data | defaultspack pending Wave 9 | existing | unchanged | unchanged | Wave 9 | Wave 9 | unchanged | unchanged |
| approvals | core authority boundary | existing | unchanged | unchanged | none | unchanged | unchanged | unchanged |
| audit records | core authority boundary | existing | unchanged | unchanged | unchanged | unchanged | unchanged | unchanged |

Validation was not executed by the implementation agent.
Independent testing is required before merge.
