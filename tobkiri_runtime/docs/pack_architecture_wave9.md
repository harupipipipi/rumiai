# Pack Architecture Wave 9

Wave 9 separates scheduler, connector, Company, agent, and product-facing
surfaces behind profile-scoped global contracts. Every selected provider is
explicit; boundary packs do not import a vendor's chat, Company, scheduler, or
host implementation.

## Implemented boundaries

| Area | Authoritative owner | Contract-only consumers and projections |
|---|---|---|
| schedules and job receipts | `rumi_schedule_store_pack`, `rumi_job_action_broker_pack`, `rumi_scheduler_runtime_pack` | scheduler UI and tool adapter |
| connector settings and delivery | connector registry, inbound/outbound broker, and transport gateway packs | vendor adapters, Turn adapter, Company adapter, secret-free Connections UI |
| connector OAuth pending flow | `rumi_connector_oauth_broker_pack` | exact vendor OAuth provider; Slack supplies a PKCE provider |
| Company organizations, roles, members, channels, tasks, routes, inbound, messages | `rumi_company_state_store_pack` | coordinator, agent adapter, connector adapter, read-only Companies UI |
| Company coordination | `rumi_company_coordinator_pack` | state/action, exact agent-work provider, global supervisor job adapter |
| product content | the selected product pack that declares it | profile-scoped host contribution projection only; no product pack receives broad host authority |

The scheduler UI reads `rumi.resource.schedule.v1` and
`rumi.resource.scheduler.v1`; mutations remain in receipt-aware tools/actions.
The Connections UI reads only the transport gateway's redacted public resource.
The Companies UI reads only `rumi.resource.company.v1` and
`rumi.resource.company.runtime.v1`. None of those isolated UIs can approve or
redeem an authority receipt.

## Connector and OAuth boundaries

Vendor adapters expose only protocol verification, normalization, delivery, or
their exact OAuth-provider contract. They do not import chat, turn, Company,
or scheduler source. The connector-to-Turn and connector-to-Company mappings
are separate adapters with deterministic inbound identifiers and their own
receipt paths.

OAuth begins only after a `connector.oauth.manage` receipt. The broker stores a
hashed one-shot state and a short-lived PKCE verifier per profile, never an
authorization code or secret material. Slack token exchange is bounded and
uses a credential-bound client secret. Resulting bot token and signing secret
are created only as an opaque credential owned by the Slack connector pack;
they are not returned to the UI or connector settings projection.

## Company migration and legacy compatibility

`migration.operations.import` on `rumi.action.company.state.v1` accepts a
caller-supplied legacy Operations Company snapshot after the normal state
authority receipt is redeemed. It accepts only non-secret `org_id`, conversation
identifiers, and schedule references. The state owner records an immutable
source hash. Repeating the exact source is a no-write deduplication; a changed
source or a pre-existing destination Company fails closed.

The old `rumi_operations_company_pack` remains a temporary legacy source and
its defaultspack route bindings remain compatibility work for Wave 10. It is
not a fallback writer for the new Company state store. Existing schedule IDs
are preserved as references only: schedule migration must choose the global
scheduler owner rather than duplicate scheduling work.

## Product-pack boundary

Artifact, project/Kanban, office-authoring, research, customer-research, and
data-analysis features are vertical content-first packs. They must contribute
workflows, UI declarations, prompts, and resources through the selected
profile's manifest projection; they may not edit shared host/runtime cores or
gain authority merely by being installed. Product UI removal is therefore a
profile pack-set change, not a host route exception.

The pre-v3 asset-only product manifests and any direct defaultspack feature UI
are a Wave 10 facade-cleanup target. They are recorded here instead of being
silently treated as new authoritative runtime owners.

## Data ownership matrix

| Resource | Authoritative pack | Schema version | Storage | Backup | Migration | Rollback | Retention | Export/import |
|---|---|---:|---|---|---|---|---|---|
| schedules | `rumi_schedule_store_pack` | 1.0.0 | profile atomic JSON | owner snapshot | explicit scheduler migration | select prior owner; no dual write | profile lifetime | owner contract |
| job action receipts | `rumi_job_action_broker_pack` | 1.0.0 | receipt state | bounded | none | expire/revoke | short-lived | no |
| connector registry | `rumi_connector_registry_service_pack` | 1.0.0 | profile registry state | owner snapshot | one-way registry import | select prior owner | profile lifetime | redacted contract |
| connector credentials | `rumi_credential_broker_pack` | 1.0.0 | encrypted broker store | encrypted owner backup | opaque handles only | revoke/select prior binding | credential policy | redacted status only |
| OAuth pending flows | `rumi_connector_oauth_broker_pack` | 1.0.0 | profile pending-flow state | none | none | cancel state/revoke failed binding | ten minutes | no |
| Company state | `rumi_company_state_store_pack` | 1.0.0 | profile atomic JSON | owner snapshot | one-shot legacy snapshot import | stop new coordinator; never dual-write | profile lifetime | owner contract |
| Company coordination | no persistent coordinator owner | 1.0.0 | bounded in-process active-task set | none | none | cancel through exact work provider | process lifetime | event projection |
| agent state | `rumi_agent_state_store_pack` | 1.0.0 | profile owner storage | owner snapshot | owner migration | owner rollback | profile policy | owner contract |
| product workflows and feature UI content | selected product pack | pack-defined | pack-owned declarative assets | pack release/source backup | manifest cutover | remove selected pack projection | pack lifecycle | pack-defined |

## Required external validation

Focused test files and QA instructions are prepared in
`docs/qa/pack_architecture_wave9_qa.md`. They are not evidence of execution.

テスト、lint、build、起動確認、実環境確認は実装担当のCodexでは実行していません。
マージ前に独立した実環境QAが必要です。
