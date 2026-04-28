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
