# RumiTemplate Platform

RumiTemplate is the defaultspack composition layer. It lets a pack declare the
pieces that make up a feature, then lets the template kernel validate,
activate, merge, and project those pieces into the catalog.

Template controls composition metadata. Kernel/runtime controls execution
authority.

## 1. Purpose

RumiTemplate makes defaultspack features composable without turning templates
into arbitrary code. A template can describe settings fields, AI inputs, tool
policies, commands, context policies, backend function bindings, route bindings,
permissions, lifecycle metadata, backend service metadata, and machine-readable
test contracts. The runtime then decides what is executable and what remains
metadata.

The shipped model selector, API key setup, composer, external IO, calendar, and
prompt compaction bundles are expressed this way so they can be combined with
other model or frontend templates.

## 2. Template vs Kernel

Template metadata may describe:

- UI composition
- settings schema
- command binding
- function binding
- route binding
- AI input
- tool/context policy
- capability/dependency requirements
- setup metadata
- permission requirements
- test contracts
- lifecycle metadata

Kernel/runtime keeps:

- trust assignment
- secret storage
- approval enforcement
- sandboxing
- model provider execution
- arbitrary tool execution
- persistence implementation
- audit enforcement
- resource limits
- signature verification

## 3. Schema Version And Template Version

`schema_version` is the template document format version. The current version is
`1`. Missing `schema_version` is accepted as legacy v1 and emits
`template.schema_version.implicit_v1`.

`version` is the semantic version of that template's feature contract. It is
used for dependency checks such as `>=1.2,<2`.

Future `schema_version` values are rejected with
`template.schema_version.unsupported`. Data-only migrations are registered in
`domain/templates/migration.py`; they may normalize known aliases but may not
import modules, run shell, call handlers, eval, or exec.

## 4. Trust Model

Trust is authoritative loader state, not JSON state. Builtin templates come from
the trusted `templates/` root. User templates come from
`user_data/shared/templates/`. A template cannot promote itself with
`trust_level: builtin`, patches cannot change `id` or `trust_level`, and nested
payload metadata is overwritten from the outer projection.

USER and UNTRUSTED templates cannot execute Python, shell, React modules,
`pack_block`, `rumi_function`, backend service entrypoints, or HTTP route
handlers.

## 5. Status And Runtime Projection

Only `status: "active"` templates with no error diagnostics project into
runtime buckets. `draft`, `deprecated`, and `disabled` templates remain visible
in summary/catalog diagnostics but do not register commands, routes, functions,
tool policies, services, or settings fields.

## 6. Piece Kinds

Supported piece kinds include:

- `settings_section`
- `settings_field`
- `field_renderer`
- `frontend_component`
- `sidebar_item`
- `chat_renderer`
- `composer_command`
- `composer_input`
- `composer_widget`
- `ai_input`
- `tool_policy`
- `shell_region`
- `shell_renderer`
- `context_policy`
- `external_io_template`
- `function`
- `backend_service`
- `api_route`
- `permission`
- `test_contract`

The catalog also contains read-only `source_adapter_contributions` for legacy
manifests. Those contributions are metadata-only and do not create duplicate
execution registrations.

## 7. Extends vs Dependencies

`extends` composes template content. It merges pieces and applies patches under
protected identity and trust rules.

`dependencies` affect activation order and capability closure. They do not
merge pieces. A dependency can provide capabilities that satisfy the consumer,
but it does not alter the consumer's JSON.

## 8. Dependency Versions And Activation Graph

Dependencies may be strings or objects:

```json
{
  "dependencies": [
    "rumi.composer.default",
    {"id": "rumi.model_selector.default", "version": ">=1.0,<2", "optional": false}
  ]
}
```

The activation planner uses `extends` plus required dependencies to build a
deterministic graph. Missing required dependencies, inactive dependencies,
version mismatch, dependency cycles, and extends cycles block runtime
projection. Optional dependencies emit warnings but do not block.

## 9. Capability Resolution

Capabilities are declared under:

```json
{
  "capabilities": {
    "provides": ["rumi.model_selector"],
    "requires": ["rumi.provider_credentials"],
    "permissions": ["model.invoke"]
  }
}
```

The planner collects capabilities from the active dependency closure,
transitive dependency closure, extends closure, and the template itself. If a
required capability is not available, the template is not projectable.

## 10. Tool Policy Merge

Multiple template tool policies are merged in the backend. The frontend may
preview the same result, but backend authority is final.

Rules:

- explicit allowlists are restrictive; multiple allowlists intersect
- an explicit empty allowlist disables all tools
- denylists and disabled tools union
- request `disabled_tools` is a turn-level override and joins the denylist
- default enabled and selected tools are filtered by allow/deny
- `parallel_tool_calls: false` wins
- `toggleable: false` wins
- `tool_choice: none` wins; other conflicts fall back to `auto` with warning
- conflicting `params` keys are removed with warning
- missing requested template policy IDs fail closed with `tool_choice: "none"`

The frontend sends IDs, not authority fields:

```json
{
  "params": {
    "tool_policy": {
      "template_ai_input_ids": ["default_ai_input"],
      "template_tool_policy_ids": ["default_tools"],
      "disabled_tools": ["web_search"]
    }
  }
}
```

## 11. Prompt Workspace Template

`rumi.prompt_workspace.default` declares the visible prompt management surface.
It projects Prompt Studio, the Prompt Command Center, sidebar/shell metadata,
prompt trace functions, prompt toggle/save/override/version/rollback
functions, and machine-readable route contracts.

The Prompt Workspace template depends optionally on:

- `rumi.model_selector.default` for the Studio model selector surface
- `rumi.backend.prompt_compaction.default` for prompt compaction capability

Prompt Studio sends template source IDs into its Test Bench:

```json
{
  "template_policy": {
    "template_ai_input_ids": ["default_ai_input"],
    "template_tool_policy_ids": ["default_tools"]
  }
}
```

The backend resolves those IDs with `resolve_template_tool_policy()`. Missing
or conflicting template tool policy IDs fail closed, and the result is returned
as `template_tool_policy_resolution` so the UI can show requested IDs, resolved
IDs, projected IDs, diagnostics, allow/deny rules, and the effective
`tool_choice`.

Prompt text remains passive. A prompt can make a tool look relevant in Studio,
but only the tool registry, model/provider support, profile policy, template
tool policy, and approval path can make that tool callable.

## 12. Collision And Override

Every projected item has an internal `projected_id` in the form:

```text
template_id:piece_id
```

Public identity is bucket-specific: route identity is `METHOD path`, command
identity is `command_id/id/name`, permission identity is `permission_id/id`, and
so on. If two different projected items claim the same public ID, the default
is no winner. Both are excluded and
`template.catalog.public_id_collision` is emitted.

Explicit replace is allowed:

```json
{
  "override": {
    "mode": "replace",
    "target_projected_id": "rumi.base.template:piece_id"
  }
}
```

The replacer must have trust rank greater than or equal to the target. USER and
UNTRUSTED templates cannot replace BUILTIN or LOCAL executable contributions.

## 13. Ordering

`order` is a stable sort hint. `insert_before` and `insert_after` are explicit
merge anchors and take precedence over `order`.

`slot` is semantic UI/runtime placement. It is not a merge anchor. Legacy
templates that use `slot` exactly matching a base piece ID are still accepted as
an insert-after anchor and emit `template.piece.legacy_slot_anchor`.

Unknown anchors warn. Ordering cycles error and block the affected template from
runtime projection.

## 14. Cache Generation And Reload

`domain/templates/catalog_runtime.py` exposes:

- `get_template_catalog_snapshot()`
- `invalidate_template_catalog()`
- `current_template_catalog_generation()`

Generation is a content hash over normalized roots, schema version, relative
template paths, and each `template.json` SHA-256. It does not rely on mtime.

Tool policy resolution and template function/route specs read from this
provider so template edits do not leave stale function, route, or policy cache.
Malformed edits drop the previous runtime contribution and return diagnostics.

## 15. Lifecycle

Lifecycle is declarative and data-only. State is stored at:

```text
user_data/shared/templates/template-state.json
```

The lifecycle API plans and applies idempotent operations with rollback:

- `set_default_if_missing`
- `rename_setting`
- `move_setting`
- `archive_setting`
- `delete_setting`
- `rename_external_io_config`

Secret-looking fields, path escape, arbitrary Python, shell, network, and pack
install/remove are rejected.

## 16. Backend Service Lifecycle

`backend_service` pieces are executable only from BUILTIN templates. The service
registry validates that entrypoints are allowlisted modules under the
defaultspack root.

Supported lifecycle values:

- `singleton`
- `startup`
- `request`

Compatibility aliases:

- `local` -> `singleton`
- `local_secret_store` -> `singleton`

Service start order follows declared dependencies. Cycles are errors. A failed
service does not stop the OS; dependents are marked blocked.

## 17. Test Contract

`test_contract` pieces use data-only assertion objects. Legacy strings are
accepted as documentation-only warnings.

Supported assertion types:

- `catalog_contains`
- `catalog_excludes`
- `route_resolves`
- `route_absent`
- `function_registered`
- `function_absent`
- `permission_declared`
- `setting_field_exists`
- `tool_policy_resolves`
- `diagnostic_absent`
- `template_projectable`
- `template_not_projectable`

Run shipped contracts with:

```bash
python scripts/quality/check_template_contracts.py
```

## 18. Frontend Renderer Security

Templates reference renderer IDs. They do not introduce arbitrary React module
URLs. Builtin settings renderer IDs such as `model_select`, `provider_select`,
`api_key_setup`, and `model_api_routes` are registered in the frontend renderer
registry. USER templates can bind fields to registered renderers but cannot
ship a new executable renderer module through template JSON.

Approved frontend extension packs remain a separate mechanism with pack
approval, local containment, integrity data, same-origin loading, CSP, lazy load
error boundaries, and builtin fallback.

## 19. Source Adapters

Source adapters expose legacy harnesses in the template catalog without moving
their source of truth:

- domain component manifests
- extension manifests
- legacy command manifests
- external IO templates
- flow route metadata

Adapter contributions include authoritative `source_kind`, `source_id`,
`source_path`, `source_pack_id`, and `trust_level`. They are metadata-only and
do not double-register commands, routes, functions, or handlers.

## 20. Legacy Relationships

Existing manifests, flows, profiles, components, and external IO YAML remain
valid. Native RumiTemplate files own the new composable pieces. Source adapters
make legacy material visible to diagnostics and catalog UIs while preserving
the original runtime paths.

## 21. Security Anti-Patterns

Do not:

- trust `trust_level` from template JSON
- copy template authority fields from frontend requests
- let USER templates define `pack_block`, `rumi_function`, shell handlers, or backend services
- keep stale last-known-good runtime pieces after malformed edits
- silently pick a winner for public ID collisions
- put secrets in lifecycle operations
- load React modules from template JSON
- run arbitrary migration or test code from templates

## 22. Complete Sample

```json
{
  "schema_version": 1,
  "id": "example.model.bundle",
  "kind": "composite",
  "version": "1.0.0",
  "status": "active",
  "capabilities": {
    "provides": ["example.model.bundle"],
    "requires": ["rumi.provider_credentials"],
    "permissions": ["model.invoke"]
  },
  "dependencies": [
    {"id": "rumi.composer.default", "version": ">=1,<2"},
    {"id": "rumi.api_keys.default", "optional": true}
  ],
  "pieces": [
    {
      "id": "model_field",
      "kind": "settings_field",
      "section_id": "models",
      "field_id": "preferred_model",
      "type": "model_select",
      "renderer": "model_select",
      "label": "Preferred Model",
      "data_source": "selectable_model_profiles"
    },
    {
      "id": "tools",
      "kind": "tool_policy",
      "policy": {
        "id": "example_tools",
        "allowed_tools": ["web_search"],
        "toggleable": true,
        "tool_choice": "auto"
      }
    },
    {
      "id": "ai_input",
      "kind": "ai_input",
      "input": {
        "id": "example_ai_input",
        "composer_input": "default_composer",
        "tool_policy": "example_tools"
      }
    },
    {
      "id": "contract",
      "kind": "test_contract",
      "contract_id": "example.model.bundle.catalog",
      "assertions": [
        {
          "type": "setting_field_exists",
          "section_id": "models",
          "field_id": "preferred_model",
          "field_type": "model_select"
        },
        {"type": "tool_policy_resolves", "policy_id": "example_tools"},
        {"type": "template_projectable", "template_id": "example.model.bundle"}
      ]
    }
  ]
}
```

## 23. Migration Guide

For metadata-only composition, add a template under `templates/<area>/<name>/`.
Keep existing blocks, flows, manifests, and stores in place until a native
template piece truly owns that surface.

When converting legacy declarations:

1. Add `schema_version: 1`.
2. Move UI/settings/composer/tool-policy metadata into pieces.
3. Keep execution handlers in existing builtin modules.
4. Add object test contracts.
5. Run focused template tests and `check_template_contracts.py`.
6. Use source adapters to inspect legacy manifests without double execution.

## 24. Diagnostics

Common diagnostic codes:

- `template.schema_version.implicit_v1`
- `template.schema_version.unsupported`
- `template.version.invalid`
- `template.dependency.version_mismatch`
- `template.dependency.missing`
- `template.dependency.inactive`
- `template.activation.cycle`
- `template.piece.legacy_slot_anchor`
- `template.piece.ordering_cycle`
- `template.catalog.public_id_collision`
- `template.catalog.invalid_override`
- `template.security.shell_like_handler`
- `template.lifecycle.secret_operation_rejected`
- `template.service.non_builtin_rejected`
- `template.service.module_escape_rejected`
- `template.source_adapter.invalid_json`
- `template.tool_policy.conflicting_tool_choice`
- `template.tool_policy.conflicting_param`

Troubleshooting path:

1. Check `catalog["template_diagnostics"]`.
2. Confirm the template summary is `projectable: true`.
3. Confirm the public ID did not collide.
4. Confirm requested tool policy IDs resolve in backend.
5. Run `python scripts/quality/check_template_contracts.py`.
