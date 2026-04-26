# Profile Spec

Profiles are runtime or workspace presets. They describe which nodes are available and how a selected graph should run in a particular environment.

Version: `rumi.profile.v1`

Profiles are not security source-of-truth documents. Parsed profile permissions may guide UI and runtime defaults, but privileged operations must still be enforced by existing trust, grant, approval, and capability systems.

## Files

Initial discovery candidates:

1. `user_data/shared/profiles/*.profile.yaml`
2. `ecosystem/<pack_id>/profiles/*.profile.yaml`

## Relationship To Graphs

Graph and profile are separate:

- Graph is the capability wiring diagram.
- Profile is the runtime preset, environment, permissions, defaults, and node availability for that wiring diagram.

The graph compiler always receives both `graph_id` and `profile_id`.

## Schema

```yaml
profile_id: coding
version: rumi.profile.v1
kind: runtime_profile
display_name:
  en: Coding
  ja: コーディング
locale: en
default_graph: coding_workspace
default_flow: coding_startup
enabled_nodes:
  - rumi.start
  - defaultspack.agent
  - defaultspack.tool.registry
disabled_nodes:
  - defaultspack.experimental.remote_shell
viewer:
  palette:
    include:
      - defaultspack.agent
      - defaultspack.tool.registry
permissions:
  can_install_packs: false
  can_create_profile: true
  can_update_profile: true
  can_delete_profile: false
policy:
  max_tool_calls: 8
  require_approval_for_tools: true
node_settings:
  defaultspack.agent:
    model_profile: default
```

## Required Fields

- `profile_id`
- `version`
- `kind`

## Common Fields

- `enabled_nodes`
- `disabled_nodes`
- `default_graph`
- `default_flow`
- `viewer.palette`
- `permissions`
- `policy`
- `node_settings`
- `locale`

## Node Availability

The profile-aware node registry is derived from:

```text
global node registry + selected profile
```

Phase 1 behavior:

- nodes listed in `disabled_nodes` are unavailable
- if `enabled_nodes` is non-empty, only listed nodes are available
- if `enabled_nodes` is empty or absent, all global nodes are available except disabled nodes

Graph validation and compile must reject graphs that use unavailable nodes.

## Node State

Profile node state should be computed separately from node definitions.

Expected state categories:

- enabled
- disabled
- missing_definition
- missing_configuration
- unavailable

The first profile PR only needs enough structure to support profile-aware graph validation and viewer palette filtering later.

## InterfaceRegistry

Loaded profiles are registered as:

```text
profile.<profile_id>
```
