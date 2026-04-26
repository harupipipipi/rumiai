# Capability Graph PR Plan

This roadmap keeps Capability Graph work reviewable. Each PR should be small, should preserve existing `.flow.yaml` behavior, and should avoid viewer UI until backend foundations are stable.

## PR 0: Docs And Spec

Scope:

- `docs/capability_graph.md`
- `docs/node_spec.md`
- `docs/profile_spec.md`
- `docs/port_standards.md`
- `docs/capability_graph_pr_plan.md`

Acceptance:

- docs only
- no runtime implementation
- no viewer UI
- existing tests should be unaffected

## PR 1: NodeDefinition And NodeDiscovery

Scope:

- `core_runtime/node_models.py`
- `core_runtime/ecosystem_nodes.py`
- `kernel:node.load_all`
- `kernel:node.list`
- `kernel:node.get`
- minimal defaultspack `node.json`
- tests

Required behavior:

- register core-owned `rumi.start` before ecosystem node discovery
- define `rumi.start` with output port `out` and standard `rumi.flow.start`
- prevent ecosystem packs from overriding core-owned built-in node ids
- load pack-provided node files only from packs that pass existing approval and hash verification
- parse `rumi.node.v1`
- normalize `contract` to `standards`
- normalize `name` to `display_name.en`
- detect duplicate `node_id`
- detect invalid port direction
- detect invalid standards
- register `node.<node_id>` in `InterfaceRegistry`

Non-goals:

- graph loader
- graph compiler
- viewer UI

## PR 2: Profile Loader And Profile-Aware Node Registry

Scope:

- `core_runtime/profile_models.py`
- `core_runtime/profile_loader.py`
- `core_runtime/profile_node_registry.py`
- `core_runtime/node_state.py`
- `kernel:profile.load_all`
- `kernel:profile.list`
- `kernel:profile.get`
- `kernel:profile.node_state`
- sample profiles
- tests

Required behavior:

- load `*.profile.yaml`
- load pack-provided profile files only from packs that pass existing approval and hash verification
- parse `enabled_nodes` and `disabled_nodes`
- parse profile permissions without making them security source of truth
- parse locale and `node_settings`
- compute profile node state
- register `profile.<profile_id>` in `InterfaceRegistry`
- adapt by coexisting with `StartupProfileManager`; PR 2 does not bridge or supersede launch-time startup profiles

Non-goals:

- graph compiler
- viewer UI
- superseding the existing startup profile model

## PR 3: GraphLoader And PortStandardsValidator

Scope:

- `core_runtime/graph_models.py`
- `core_runtime/capability_graph_loader.py`
- `core_runtime/port_standards.py`
- `kernel:graph.load_all`
- `kernel:graph.get`
- `kernel:graph.validate`
- `.graph.yaml` fixtures
- tests

Required behavior:

- load `.graph.yaml`
- load pack-provided graph files only from packs that pass existing approval and hash verification
- validate graph schema
- check node refs
- check profile-aware node availability
- parse endpoints
- detect missing ports
- validate source and target directions
- validate standards intersection
- enforce `multiple: false` on input ports
- enforce required input ports

Non-goals:

- compile
- binding handler execution

## PR 4: AgentEngine Tools Injection Minimal

Scope:

- pass execution tools into AgentEngine AI completion
- maintain tools through approve/reject loop
- reject unconnected tool calls as groundwork for graph enforcement
- tests

Non-goals:

- graph compiler
- full provider-specific schema adapter

## PR 5: GraphCompiler And BindingHandlerResolver

Scope:

- `core_runtime/capability_graph_compiler.py`
- `core_runtime/binding_handlers.py`
- `kernel:graph.compile`
- tests

Required behavior:

- profile-aware compile
- validate before compile
- safe binding handler resolution
- no direct arbitrary imports
- return runtime profile dict
- register `runtime_profile.<profile_id>.<graph_id>` in `InterfaceRegistry`
- return diagnostics
- regression test that compiler core has no AI/tool/agent-specific branch logic

## PR 6: defaultspack Nodes And Minimal Bindings

Scope:

- defaultspack agent, AI client, tool, frontend node definitions
- defaultspack binding handlers
- binding handler registration
- sample graph
- tests

Required behavior:

- `tool -> agent.tools` adds tool ids to runtime profile through pack binding
- `ai_client -> agent.ai` adds AI client ref through pack binding
- `cli surface -> frontend.surface` adds frontend surface ref through pack binding

## PR 7: Flow Uses Explicit Graph Compile Step

Scope:

- fixture flow that calls `kernel:graph.compile` as an explicit step
- tests

Required behavior:

- flow step can call graph compile
- compiled runtime profile is available through the output key
- flows without graph compile remain unchanged

Non-goal:

- automatic `capability_graph` field on `FlowDefinition`

## PR 8: Connected Tool Enforcement And Schema Adapter

Scope:

- defaultspack tool schema adapter
- pass graph/profile/principal context into tool execution
- connected-tool enforcement
- groundwork for profile policy such as `max_tool_calls`

## PR 9: Backend API Integration

Scope:

- profiles API
- graphs API
- profile node state API
- document and expose the relationship between Capability Graph profiles and existing startup profiles

Required behavior:

- keep `StartupProfileManager` as the launch-time source of truth
- expose Capability Graph profiles as graph/runtime presets
- choose an explicit API bridge between the two systems
- do not silently supersede the existing startup profile model
- tests

Implemented API surface:

- `GET /api/nodes` and `GET /api/nodes/{node_id}`
- `GET /api/profiles` and `GET /api/profiles/{profile_id}`
- `GET /api/profiles/{profile_id}/nodes`
- `GET /api/graphs` and `GET /api/graphs/{graph_id}`
- `POST /api/graphs/{graph_id}/validate`
- `POST /api/graphs/{graph_id}/compile`
- `/api/panel/*` aliases for the control panel viewer session

The profile API returns a startup-profile relationship object that states `StartupProfileManager` remains the launch-time source of truth. Capability Graph profiles are exposed as graph/runtime presets and palette filters, not as a silent replacement for startup profiles.

## PR 10: Viewer Node Manager

Scope:

- profile switch UI
- profile-scoped node palette
- enabled/disabled display
- profile create/clone UI only where permissions allow

Implemented viewer surface:

- `/panel/nodes` Node Manager route
- profile switcher
- profile-scoped node catalog and palette counts
- enabled, disabled, ready, missing-config, missing-node, and unapproved state display
- node port, standards, binding, and metadata detail
- graph validate and compile preview controls
- profile clone action shown only when `permissions.can_create_profile` is true

## Guardrails For Every PR

- Keep `.flow.yaml` behavior compatible.
- Do not add domain meaning to core.
- Use `standards` as the canonical port compatibility field.
- Keep `contract` and `name` as loader compatibility only.
- Keep defaults/defaultspack responsibilities explicit.
- Return diagnostics from loaders, validators, and compilers.
- Avoid combining node, profile, graph, compiler, AgentEngine, and viewer work in one PR.
