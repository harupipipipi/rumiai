# Startup Capability Bridge

Startup Profiles remain the launch-time source of truth for Rumi modes such as
desktop, CLI, and work profiles. Capability Profiles remain graph compile
presets. The startup capability bridge connects them without replacing either
model.

## Opt-in fields

Startup Profiles can opt in to graph compilation with these fields:

```json
{
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "launch_capability_graph": true,
  "last_runtime_profile_key": null
}
```

- `default_graph` selects the Capability Graph to compile.
- `capability_profile_id` selects the Capability Profile used for graph policy,
  node settings, and enabled or disabled nodes.
- `launch_capability_graph` controls whether launch compiles the graph.
- `last_runtime_profile_key` records the last registered runtime profile key
  after a successful launch compile.

Profiles that omit `launch_capability_graph`, or set it to `false`, keep the
previous startup launch behavior. Their launch result includes
`capability_graph.skipped: true` with reason
`launch_capability_graph_disabled`; this is non-fatal.

## Launch behavior

When `launch_capability_graph` is true, `StartupProfileManager.launch_profile()`
launches the startup profile and then calls the bridge. The bridge:

1. Resolves `default_graph` and `capability_profile_id`.
2. Registers defaultspack Capability Graph binding handlers.
3. Loads approved Capability Profiles, Capability Graphs, and node definitions.
4. Applies `node_overrides` to matching graph edge targets.
5. Extends the launch-only Capability Profile copy with only the nodes added by
   `node_overrides`, and only when their packs are listed in the Startup Profile.
6. Compiles the graph with `CapabilityGraphCompiler`.
7. Extracts the selected frontend surface launch target.
8. Registers the compiled runtime profile in `InterfaceRegistry`.
9. Returns `capability_graph` metadata in the launch result.

Compile failures are soft failures. Startup launch still succeeds, and the
launch result includes `capability_graph.ok: false` plus diagnostics.

## Launch result

Successful graph compilation adds a result like:

```json
{
  "capability_graph": {
    "ok": true,
    "graph_id": "defaultspack.startup",
    "capability_profile_id": "defaultspack.startup",
    "runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup",
    "surface_launch_target": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "node_id": "frontendpack.web_surface"
    }
  }
}
```

Consumers should use `runtime_profile_key` to retrieve the registered runtime
profile from `InterfaceRegistry`. Existing explicit flow steps that compile
graphs still work as before.

`StartupProfileManager` also persists `startup_surface_launch_target` in active
ecosystem metadata. After restart, `startup_surface_launcher` reads that target
and launches its `pack_id` instead of always launching the startup base pack. If
no graph launch target exists, startup launch falls back to the previous
`startup_base_pack` behavior.

## Compile preview

The control panel can preview the exact Startup Profile compile path without
launching or saving state:

```http
POST /api/panel/startup/profiles/{id}/compile-preview
```

The optional body can include a draft profile:

```json
{
  "profile": {
    "profile_id": "custom",
    "packs": ["defaultspack", "frontendpack"],
    "node_overrides": {
      "frontend.surface": "frontendpack.web_surface"
    }
  }
}
```

The response mirrors the launch compile result and includes
`surface_launch_target`, so the Startup Profile editor can show the frontend
pack that will be opened after restart.
