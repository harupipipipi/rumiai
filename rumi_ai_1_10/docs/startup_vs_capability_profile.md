# Startup Profiles vs Capability Profiles

Startup Profiles remain the launch-time source of truth. They select packs,
slots, startup handoff behavior, and whether a Capability Graph should compile
at launch.

Capability Profiles are graph/runtime presets. They select graph defaults,
enabled and disabled nodes, node settings, and runtime policy.

Bridge fields on Startup Profiles:

```json
{
  "launch_capability_graph": true,
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "last_runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup"
}
```

When `launch_capability_graph` is enabled, startup launch compiles the graph and
registers the runtime profile in `InterfaceRegistry`. Flows, agents, and panel
APIs can resolve `runtime_profile_key` back to the compiled runtime profile.

Startup Profile `node_overrides` are applied before launch compile. For example,
`{"frontend.surface": "frontendpack.web_surface"}` rewrites the graph edge that
feeds `frontend.surface` so the selected surface node becomes part of the
compiled runtime profile. Override nodes are enabled only when their pack is
included in the Startup Profile `packs` list.

The bridge persists the selected `surface_launch_target` in active metadata so
restart handoff can open the frontend selected by graph wiring. Without a launch
target, restart handoff continues to open the Startup Profile base pack.
