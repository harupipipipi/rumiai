# Architecture

## Responsibility

`rumi_mcp_gateway_pack` describes how Rumi should discover, classify, route, and document MCP servers that do not yet have direct first-party support. It is useful as a marketplace/catalog profile for "support every MCP that is not directly supported yet" while preserving local approval and namespace boundaries.

## Non-Responsibility

The pack does not implement MCP transports, subprocess management, SSE clients, tool execution, credential handling, stores, HTTP routes, handlers, or approval enforcement. Those remain owned by `defaultspack` and the host runtime.

## Directory Layout

- `ecosystem.json`: pack identity, dependencies, asset index, and declarative-only boundary.
- `catalog/connector_catalog.yaml`: local catalog of MCP server categories and discovery hints.
- `catalog/namespace_routes.yaml`: explicit namespace and tool naming route policy.
- `catalog/marketplace_registry.yaml`: marketplace and registry metadata for discovery surfaces.
- `policies/unsupported_server_safety.yaml`: fail-closed policy for unsupported and unknown MCP servers.
- `profiles/`: runtime profile metadata for gateway-style MCP use.
- `prompts/`: system prompt layer for safe MCP routing decisions.
- `templates/`: prompt and resource templates for server review and documentation.
- `examples/`: example descriptor for an unknown server awaiting approval.
- `docs/`: pack-specific documentation.

## Execution Path

1. A user installs or selects the pack through setup-pack metadata.
2. A Rumi surface can read the catalog and prompt/resource templates to guide MCP discovery.
3. Unknown MCP servers are represented as descriptors with a proposed namespace such as `mcp_gateway.<server_slug>`.
4. The actual connection, listing, approval, and execution path remains `defaultspack` MCP tooling.
5. Discovered tools are routed only through explicit MCP tool names such as `mcp__<server_id>__<tool_name>` or a pack-qualified alias that maps back to that defaultspack-owned tool.

## Runtime Contact Points

- Uses `defaults.tool.mcp_connect` / `defaultspack.tool.mcp_connect` for approved MCP connection.
- Uses `defaults.tool.mcp_list` / `defaultspack.tool.mcp_list` for listing connected servers and tools.
- Uses the runtime approval system for high-risk connection and execution decisions.
- Uses defaultspack MCP registry persistence as the source of truth for connected server state.

No pack-owned Python modules are imported during normal use.
