# Defaultspack Domain Component Convention

Defaultspack is moving toward extension-like domain components: a feature should
be added by dropping a folder under `domain/<category>/<component_id>/` with a
manifest and any small rules, adapters, or handlers it owns. Existing public ids,
routes, imports, and behavior remain stable while central registries become
discovery and compatibility layers.

## Folder Layout

Canonical component folders use this shape:

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md
  tests/
```

The component id should be stable, lowercase, and filesystem-safe. Public ids
inside the manifest may keep dots, slashes, and historical names when those names
are already part of the API.

## Category Naming

Use plural, domain-oriented categories:

- `webhooks`
- `integrations`
- `gateway_channels`
- `webhook_url_providers`
- `tools`
- `providers`
- `prompts`
- `templates`
- `input_profiles`
- `output_profiles`
- `audience_policies`
- `transports`
- `ui_surfaces`

Category names should describe ownership, not implementation detail. For
example, LINE webhook defaults belong in `webhooks/line`, while LINE inbound
security and normalization code belongs in `integrations/line`.

## Manifest Fields

Every component manifest must include:

- `id`: stable component id or public id.
- `category`: the folder category.
- `kind`: component kind within the category.
- `version`: string version for the component contract.
- `status`: `experimental`, `stable`, or `legacy`.

Recommended fields:

- `entrypoints`: import paths or file-relative entrypoints for runtime code.
- `routes`: public HTTP route metadata, methods, and route ids.
- `profiles`: input/output profile ids owned or exposed by the component.
- `security`: signature, shared-secret, approval, credential, or sandbox policy.
- `ui`: frontend grouping, icon, command, panel, or catalog metadata.
- `policy`: audience, response, tool, or routing rules.
- `capabilities`: provider, tool, media, transport, and mode capabilities.
- `aliases`: stable compatibility aliases that resolve to this component.
- `compatibility`: legacy imports, ids, defaults, and shims that must remain.
- `conversion_targets`: ids this component can convert or export to.
- `owner`: owning module, team, or maintainer hint.
- `source_pack_id`: pack that supplied the component.

Manifests are data. Discovery must not import handler code or execute arbitrary
Python. Runtime layers may import an entrypoint only after a component is selected
for use.

## Entrypoints

Entrypoints are import strings or file-local names that point to runtime behavior:

```json
{
  "entrypoints": {
    "handler": "domain.integrations.line.inbound:handle_line_webhook",
    "security": "domain.integrations.line.security:verify_signature",
    "adapter": "domain.providers.google.adapter:GoogleProvider"
  }
}
```

Compatibility shims may continue to import old block modules, but new code should
ask the component registry for the selected component and then load the specific
entrypoint needed.

## Rules Files

Rules may live in `rules.json` when they are declarative or `rules.py` when the
rules need small helper functions. Rules files should stay local to the component
and should not become second central registries.

Examples:

- webhook endpoint defaults
- input and output profile specs
- audience policies
- tool approval/risk hints
- provider model defaults
- prompt rendering options
- route metadata
- UI command grouping

## Compatibility Aliases

Aliases preserve historical public names. They may include endpoint ids, profile
ids, tool ids, provider aliases, model aliases, route names, and legacy import
paths. Alias resolution must be explicit and deterministic.

Examples:

- endpoint ids: `line-main`, `discord-main`, `slack-main`, `test-webhook`
- profile ids: `line.default`, `discord.default`, `slack.default`,
  `generic.webhook.default`
- provider id: `gitlawb-opengateway`
- model ids: `gitlawb-opengateway/mimo-v2.5-pro`,
  `gitlawb-opengateway/mimo-v2-flash`,
  `gitlawb-opengateway/google/gemini-3.1-flash-lite-preview`

## Route Metadata

Route metadata belongs with the component that owns the behavior whenever safe:

```json
{
  "routes": [
    {
      "id": "webhook.line.inbound",
      "path": "/webhooks/line",
      "methods": ["POST"],
      "entrypoint": "domain.integrations.line.inbound:handle_line_webhook"
    }
  ]
}
```

Public paths must not change during migration. Existing route tables remain as
fallbacks until manifest-backed routes have complete coverage and tests.

## Provider And Model Metadata

Provider components own provider metadata, auth rules, adapter entrypoints, and
model defaults. Model catalogs may also arrive from manifest-backed sibling packs
such as `rumi_model_catalog_pack`; defaultspack must interoperate with those
packs rather than copying or collapsing them.

Provider components should not import tool registries or tool policy modules.
Provider-tool bridging belongs in an orchestration or broker layer that knows
both provider capabilities and tool execution.

## Prompt, Profile, And Policy Metadata

Prompt components own prompt ids, prompt text/templates, rendering rules, and
prompt compatibility aliases. Input/output profiles and audience policies should
be manifest- or rules-backed components while preserving existing registry APIs.

Registries should load component data, merge user-defined persistent data, and
provide compatibility lookup. They should not grow new hardcoded defaults.

## Migration Rules

- Keep public ids, routes, aliases, endpoint ids, profile ids, and tool ids
  stable.
- Keep old imports as thin shims until callers move.
- Prefer adding manifest-backed discovery next to old code before deleting old
  code.
- Move defaults into component manifests or rules files before changing runtime
  behavior.
- Keep security and approval behavior at least as strict as before.
- Fail soft on invalid component manifests and expose diagnostics.
- Support multiple ecosystem packs in discovery.
- Do not import handler code during discovery.
- Do not collapse `rumi_model_catalog_pack` into defaultspack.

## What Must Not Live In Central Registries

Central registries should not be the primary home for:

- endpoint defaults for a provider
- provider-specific input/output profile defaults
- audience policy defaults
- provider allowlists and model capability metadata
- tool schemas and risk policies
- integration-specific signature or response rules
- prompt text and prompt compatibility aliases
- route and UI metadata owned by a component

Central files may keep compatibility aliases, sanitization, persistence, merge
logic, diagnostics, and fallback behavior while the migration is incomplete.
