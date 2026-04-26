# Capability Graph

Capability Graph is a capability wiring layer that sits beside the existing Execution Flow system.

Execution Flow remains responsible for ordered runtime procedures: startup, setup, handler execution, subflows, function calls, `python_file_call`, `universal_call`, scheduler integration, and explicit pipelines.

Capability Graph is responsible for declaring which runtime capabilities may be connected: AI clients, agents, tool bundles, memory, prompts, credentials, policies, frontend surfaces, CLI surfaces, and future pack-defined capabilities.

## Core Boundary

Core must stay domain-neutral. It may understand these generic concepts only:

- node
- port
- standard
- edge
- graph
- profile
- binding handler id
- validation result
- diagnostics

Core must not branch on domain meanings such as `agent`, `tool`, `ai_client`, `frontend`, `cli`, `memory`, or `prompt`. Domain-specific connection behavior belongs in ecosystem pack binding handlers.

Allowed core behavior:

- validate edge compatibility
- resolve an approved binding handler
- call that binding handler
- record diagnostics
- register graph/profile/runtime profile values in `InterfaceRegistry`

Forbidden core behavior:

```python
if target_node.kind == "agent" and source_node.kind == "tool":
    profile["agents"][target]["tools"].append(source)
```

## Files

Capability Graph files use `.graph.yaml`.

Initial discovery candidates:

1. `user_data/shared/graphs/*.graph.yaml`
2. `ecosystem/<pack_id>/graphs/*.graph.yaml`
3. `graphs/*.graph.yaml`

If duplicate `graph_id` values are discovered, Phase 1 treats that as a diagnostic error.

## Schema

Version: `rumi.graph.v1`

```yaml
graph_id: coding_workspace
version: rumi.graph.v1
display_name:
  en: Coding Workspace
  ja: コーディングワークスペース
nodes:
  - id: start
    ref: rumi.start
  - id: agent
    ref: defaultspack.agent
edges:
  - id: start_to_agent
    from: start.out
    to: agent.start
    kind: binding
```

`nodes[].id` is the graph-local instance id. `nodes[].ref` points to a node definition id. The same node definition may be instantiated multiple times in one graph.

Endpoint format:

```text
<graph_node_instance_id>.<port_id>
```

Phase 1 edge kind:

- `binding`

Reserved future edge kinds:

- `data`
- `event`
- `control`

Unknown edge kinds are errors in Phase 1.

## Validation

Graph validation checks:

- graph schema is valid
- all node refs exist in the global node registry
- all node refs are enabled by the selected profile when profile-aware validation is requested
- all edge endpoints parse correctly
- all referenced ports exist
- source port is `output`
- target port is `input`
- source and target standards intersect
- `multiple: false` input ports have at most one incoming edge
- `required: true` input ports have an incoming edge

Phase 1 required-port failures are validation errors. A future draft mode may downgrade them to warnings.

## Compile

Graph compile must be profile-aware from its first implementation.

Input:

```json
{
  "graph_id": "coding_workspace",
  "profile_id": "coding"
}
```

Compiler responsibilities:

- load graph and profile
- validate graph using the selected profile
- resolve node definitions
- call approved binding handlers
- produce a runtime profile dict
- register `runtime_profile.<profile_id>.<graph_id>` in `InterfaceRegistry`
- return diagnostics

Compiler non-goals:

- no viewer UI
- no provider-specific tool schema conversion in the core compiler
- no domain-specific `agent/tool/ai_client` branching in core

## InterfaceRegistry Keys

Capability Graph related objects are registered using these key shapes:

```text
node.<node_id>
graph.<graph_id>
profile.<profile_id>
runtime_profile.<profile_id>.<graph_id>
```

## Core Node

`rumi.start` is the only special node owned by core. All other nodes are discovered from ecosystem packs.
