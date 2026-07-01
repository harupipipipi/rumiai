# Rumi Cloudflare PC Tool Bridge

This Worker exposes a narrow HTTPS bridge for tools that must still run on the
user's PC. It does not upload PC-local tools to Cloudflare and does not bypass
defaultspack approval, policy, or audit. The Worker authenticates bridge clients,
then forwards only allowlisted tool and authority routes to the PC runtime through
a named Cloudflare Tunnel hostname.

## Why this exists

Cloudflare Sandbox can run managed Linux sandbox tools, but many defaultspack
tools are PC-bound: browser/computer control, local files, git, terminal, secrets,
viewer APIs, and pack approval flows. Those tools need the PC runtime to remain
the authority. This bridge makes them reachable from Cloudflare without making
Cloudflare the tool execution authority.

## Required setup

1. Create a named Cloudflare Tunnel for the PC runtime. Do not use `pages.dev` as
   a tunnel hostname; a Pages deployment is not a permanent tunnel to a Mac. Do
   not use random `trycloudflare.com` quick tunnel URLs for production tool
   access.
2. Route a public hostname on your Cloudflare zone to the PC runtime, for example
   `rumi-pc.example.com -> http://127.0.0.1:8765`.
3. Deploy this Worker with:

   ```sh
   npm install
   npx wrangler secret put RUMI_PC_TOOL_BRIDGE_TOKEN
   npx wrangler secret put RUMI_PC_RUNTIME_BEARER
   npx wrangler deploy
   ```

4. Set `RUMI_PC_ORIGIN` to the named Tunnel HTTPS origin, such as
   `https://rumi-pc.example.com`.
5. If a browser frontend calls this Worker directly, set
   `RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN` to that exact frontend origin. Leave it
   unset for server-to-server/mobile calls; the Worker does not reflect arbitrary
   `Origin` headers.

## Routes

- `GET /health` returns redacted readiness.
- `GET /v1/catalog` proxies `GET /api/tools/catalog` on the PC.
- `GET /v1/tools/names` proxies `GET /api/tools/names` on the PC.
- `POST /v1/tools/invoke` proxies `POST /api/tools/invoke` on the PC.
- `GET /v1/authority/requests` proxies pending authority requests.
- `GET /v1/authority/requests/:id` proxies one authority request.
- `POST /v1/authority/requests/:id/challenge` proxies challenge creation.
- `POST /v1/authority/requests/:id/approve` proxies approval.
- `POST /v1/authority/requests/:id/deny` proxies denial.

All `/v1/*` routes require:

```http
Authorization: Bearer <RUMI_PC_TOOL_BRIDGE_TOKEN>
```

The Worker uses `RUMI_PC_RUNTIME_BEARER` only for the PC-bound upstream request.
Never put either secret in `wrangler.jsonc`, README files, or source code.
`RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN` is not a secret, but it should be a single
explicit origin rather than `*` because `/v1/*` routes carry Bearer auth.

## Non-goals

- This is not a Cloudflare-native implementation of every defaultspack tool.
- This does not make Pages a stable PC tunnel.
- This does not allow arbitrary proxying to PC routes.
- This does not replace named Cloudflare Tunnel DNS.
