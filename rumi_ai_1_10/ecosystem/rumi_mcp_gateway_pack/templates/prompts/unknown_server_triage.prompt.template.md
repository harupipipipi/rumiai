# Unknown MCP Server Triage

Review the proposed MCP server before any connection attempt.

## Inputs

- Server ID: `{{server_id}}`
- Display name: `{{display_name}}`
- Claimed transport: `{{transport}}`
- Claimed capabilities: `{{claimed_capabilities}}`
- Requested filesystem scope: `{{requested_filesystem_scope}}`
- Requested network scope: `{{requested_network_scope}}`
- Requested credential types: `{{requested_credential_types}}`
- Proposed namespace: `{{proposed_namespace}}`

## Required Output

Return:

- `review_status`: one of `needs_more_info`, `blocked`, `ready_for_user_approval`.
- `risk_level`: one of `low`, `medium`, `high`.
- `namespace`: explicit namespace beginning with `mcp_gateway.`.
- `defaultspack_route`: `defaultspack.tool.mcp_connect` or `defaultspack.tool.mcp_list`.
- `approval_reason`: concise reason the user should approve or reject the connection.
- `blocked_reasons`: list of safety blockers, if any.

Do not produce executable install commands, secrets, credentials, or network connector code.
