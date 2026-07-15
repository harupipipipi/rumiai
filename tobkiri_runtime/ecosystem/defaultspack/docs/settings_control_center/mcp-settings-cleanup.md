# MCP Settings Cleanup

## Problem

MCP is currently easy to confuse with accounts and tools because all three appear as “things Rumi can use.” They must be separate in data model and UI.

## Final split

```txt
MCPServerDefinition
  The server transport/config.

Connection
  The account or credential the MCP server needs.

MCPToolDefinition
  Tools discovered from the server.

ToolPermissionPolicy
  Risk level, approval policy, visibility.
```

## UI placement

### Tools & MCP

- MCP servers
- Discovered tools
- Tool permissions
- Enable/disable tools

### Accounts & Connections

- OAuth/API key connections required by MCP servers

## Example

```txt
Airtable MCP
Status: Needs Airtable connection
Tools: 12 discovered
Required connection: Airtable

[Connect Airtable]
[View tools]
[Disable MCP server]
```

## Rules

- A remote HTTP MCP server with user data should use authorization.
- A local stdio MCP server may use local/env credentials.
- Rumi must still represent the credential as a Connection where possible.
- Tool execution policy is not the same as server login.
- Write/destructive tools need explicit approval policy.
