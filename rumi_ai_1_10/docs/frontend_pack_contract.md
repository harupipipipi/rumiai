# Frontend Pack Contract

A frontend pack can participate in Startup Capability Graph launch by exposing a
node with a `rumi.surface` output and `metadata.launch`.

Required:

- approved pack
- Startup Profile includes the pack in `packs`
- node port with `standards: ["rumi.surface"]`
- node metadata `pack_id`
- node metadata `launch.kind: desktop_app`
- node metadata `launch.pack_id` matching the node pack id
- `ecosystem.json` `desktop_app.command` so the Desktop App Manager can launch it

Example node:

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "frontendpack.web_surface",
      "kind": "ecosystem.surface",
      "display_name": {
        "en": "Frontendpack Web Surface",
        "ja": "Frontendpack Web Surface"
      },
      "ports": [
        {
          "id": "surface",
          "direction": "output",
          "standards": ["rumi.surface"],
          "multiple": true
        }
      ],
      "metadata": {
        "pack_id": "frontendpack",
        "component_type": "frontend",
        "component_id": "web",
        "category": "surface",
        "launch": {
          "kind": "desktop_app",
          "pack_id": "frontendpack",
          "surface": "browser",
          "default": true,
          "env": {
            "FRONTENDPACK_SURFACE": "web"
          }
        }
      }
    }
  ]
}
```

Example `ecosystem.json` desktop app section:

```json
{
  "pack_id": "frontendpack",
  "desktop_app": {
    "command": "python desktop_app.py",
    "working_dir": "",
    "env": {
      "FRONTENDPACK_PORT": "8770"
    },
    "window": {
      "title": "Frontendpack",
      "width": 1280,
      "height": 800
    }
  }
}
```

When a Startup Profile overrides `frontend.surface` to this node, graph compile
stores the canonical target in `runtime_profile.launch.surface` and active
metadata stores `startup_surface_launch_target`. After restart, the startup
surface launcher opens `frontendpack` instead of the base pack.

The launch target is intentionally pack-local. A node from `frontendpack` cannot
claim `launch.pack_id: otherpack` or `principal_id: otherpack`; compile and
startup launch normalization reject that target and fall back to the Startup
Profile base pack when needed.
