# Gateway

`domain/gateway` provides a local control-plane shell with session routing and
channel adapters. The first implementation starts a lightweight local HTTP
server for status and authenticated event intake; WebSocket protocol helpers are
represented as typed request/event envelopes in `domain/gateway/ws.py`.
Gateway binds to `127.0.0.1` by default, rejects external bind addresses unless
runtime config explicitly enables them, and requires a bearer or
`x-rumi-gateway-token` token for POST intake.

Session keys follow:

- `agent:{agent_id}:main`
- `agent:{agent_id}:chat:{conversation_id}`
- `agent:{agent_id}:line:user:{line_user_id}`
- `agent:{agent_id}:discord:channel:{channel_id}`
- `cron:{job_id}`
- `webhook:{webhook_id}`
