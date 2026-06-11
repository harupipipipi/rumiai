<!-- docs-i18n-links:start -->
[EN](./gateway.md) | [JP](./i18n/ja/gateway.md) | [KR](./i18n/ko/gateway.md) | [CN](./i18n/zh-cn/gateway.md)
<!-- docs-i18n-links:end -->

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

## External Input Relationship

Gateway is a local intake shell, not the external input framework itself. Public
or provider-specific events should be normalized into `ExternalEvent`, checked by
`AudiencePolicy`, mapped through `InputProfile`, and submitted through
`submit_input`. Gateway messages can be one source of those events.

Response delivery should go through `ResponsePlanner` and `ResponseAdapter` so
chat and agent code do not learn Slack, Discord, LINE, webhook, or tunnel
details.

Cloudflare Quick Tunnel, if used, is only a swappable URL provider in front of a
local endpoint. It must not be treated as the canonical gateway, auth system, or
external input runtime.
