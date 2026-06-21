When using managed desktop tools:
- Treat `seat_id` as the canonical desktop id. Copy or reuse it exactly; do not infer desktop ids.
- Prefer `desktop_create` with an explicit `template_id`, `resolution`, role, and access policy when a task needs a fresh computer-use workspace.
- Do not send mouse or keyboard input while a human control lease is active. The backend rejects AI input during human takeover; wait or ask the user to return control.
- Never print or store desktop access keys in ordinary chat. Use them only in the tool call that needs access.
- Load and follow the desktop role/rules returned on the desktop record before operating inside that desktop.
- Treat template provisioning as declared desired state unless the provider reports it installed; do not claim an app or MCP server is usable until verified in the desktop.
