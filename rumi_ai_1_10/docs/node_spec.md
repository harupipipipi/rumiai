<!-- docs-i18n-links:start -->
[EN](./node_spec.md) | [JP](./i18n/ja/node_spec.md) | [KR](./i18n/ko/node_spec.md) | [CN](./i18n/zh-cn/node_spec.md)
<!-- docs-i18n-links:end -->

# Node Definition Spec

Node definitions describe static capability nodes exposed by ecosystem packs.

Version: `rumi.node.v1`

## Discovery

Core registers built-in nodes before ecosystem node discovery. Phase 1 has exactly one core-owned built-in node:

```json
{
  "node_id": "rumi.start",
  "kind": "core.builtin",
  "display_name": {
    "en": "Start",
    "ja": "開始"
  },
  "ports": [
    {
      "id": "out",
      "direction": "output",
      "standards": ["rumi.flow.start"],
      "multiple": true,
      "required": false
    }
  ],
  "metadata": {
    "owner": "core"
  }
}
```

`rumi.start` is registered in the global node registry before scanning packs, so graphs can reference it without requiring an ecosystem pack. Ecosystem packs must not override core-owned built-in node ids.

Phase 1 discovery paths:

1. `ecosystem/<pack_id>/nodes/*.node.json`
2. `ecosystem/<pack_id>/components/*/node.json`

Recursive `**/node.json` discovery is intentionally deferred.

Pack-provided node definition files are loaded only from packs that pass the existing pack approval and hash verification flow. This mirrors pack-provided Flow loading. User shared files, when supported by a future loader, still require schema validation and diagnostics but are not treated as pack-approved content.

## File Shape

A file may define one or more nodes.

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "defaultspack.agent",
      "kind": "ecosystem.component",
      "display_name": {
        "en": "Agent",
        "ja": "エージェント"
      },
      "description": {
        "en": "Runtime node that combines AI, tools, memory, and prompts.",
        "ja": "AI・ツール・メモリ・プロンプトを束ねて実行するノード。"
      },
      "ports": [
        {
          "id": "start",
          "direction": "input",
          "display_name": {
            "en": "Start",
            "ja": "開始"
          },
          "standards": ["rumi.flow.start"],
          "aliases": ["start", "entry"],
          "multiple": false,
          "required": true
        },
        {
          "id": "tools",
          "direction": "input",
          "display_name": {
            "en": "Tools",
            "ja": "ツール"
          },
          "standards": [
            "rumi.tool.bundle",
            "defaultspack.tool.bundle.v1",
            "openai.function_tools.compat"
          ],
          "aliases": ["tools", "tool_bundle", "functions"],
          "multiple": true,
          "required": false
        },
        {
          "id": "result",
          "direction": "output",
          "display_name": {
            "en": "Result",
            "ja": "結果"
          },
          "standards": ["rumi.agent.result"],
          "aliases": ["result", "output"],
          "multiple": true,
          "required": false
        }
      ],
      "bindings": {
        "compile": "defaultspack.agent.compile_node",
        "on_input": {
          "tools": "defaultspack.agent.bind_tools"
        }
      },
      "requirements": {
        "configured_by": ["defaultspack.agent.configured"]
      },
      "metadata": {
        "pack_id": "defaultspack",
        "component": "agent",
        "icon": "bot",
        "category": "runtime"
      }
    }
  ]
}
```

## Required Fields

Node:

- `node_id`
- `kind`
- `display_name`
- `ports`

Port:

- `id`
- `direction`
- `standards`

## Port Direction

Allowed values:

- `input`
- `output`
- `bidirectional`

Phase 1 requires support for `input` and `output`. `bidirectional` is reserved by schema and may be rejected by validators until implemented.

## Standards

`standards` is the canonical compatibility field. It is always a list of strings.

Ports are connectable when:

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

Core compares standard strings but does not interpret domain meaning.

## Surface Launch Metadata

A surface node can advertise the desktop app that should open when a Startup
Capability Graph selects it as the active frontend surface. The node must still
expose a compatible output port; launch metadata only describes the handoff
payload after graph compile.

```json
{
  "node_id": "frontendpack.web_surface",
  "kind": "ecosystem.surface",
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
```

For safety, `metadata.launch.pack_id` must match the node's own pack id. A node
from one pack cannot point startup launch at another pack.

## Legacy Input Compatibility

Legacy files may use:

```json
{
  "node_id": "defaultspack.agent",
  "name": "Agent",
  "ports": [
    {
      "id": "tools",
      "direction": "input",
      "contract": "rumi.tool.bundle"
    }
  ]
}
```

Loaders normalize this to the v1 model:

- `name` becomes `display_name.en` when `display_name` is absent
- `contract` becomes `standards: [contract]` when `standards` is absent

Internal models should use only `display_name` and `standards`.

## Display Name Fallback

Display text resolution:

1. `display_name[user_locale]`
2. `display_name.en`
3. legacy `name`
4. `node_id` or port `id`

## Bindings

Bindings name pack-owned handlers. Core stores and resolves handler ids but does not assign domain meaning to them.

Common binding slots:

- `compile`
- `on_input.<port_id>`

Binding handlers must be resolved through approved registries or kernel handler infrastructure. Direct arbitrary imports are not allowed.
