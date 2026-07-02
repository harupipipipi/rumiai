# Rumi Cloudflare Sandbox Bridge

This Worker exposes the official Cloudflare Sandbox Bridge HTTP API for defaultspack managed sandbox workloads. Rumi talks to it through:

- `RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL`
- `RUMI_CLOUDFLARE_SANDBOX_API_KEY`

The bridge can run sandbox-compatible argv/file workloads in Cloudflare Containers. It does not upload or replace PC-local browser, desktop, host workspace, MCP, or approval-sensitive tools; those still need the connected PC runtime or a separate PC bridge.

## Deploy

Prerequisites:

- Cloudflare account with Containers/Sandbox access
- Workers Paid plan when Containers are not enabled on the account
- Node.js and npm
- Docker daemon running locally
- Wrangler logged in

```bash
cd rumi_ai_1_10/ecosystem/defaultspack/cloudflare/sandbox_bridge
npm install
npm run check
npx wrangler deploy --dry-run --containers-rollout=none
openssl rand -hex 32 | tee /dev/stderr | npx wrangler secret put SANDBOX_API_KEY
npm run deploy
curl https://rumi-cloudflare-sandbox-bridge.<your-subdomain>.workers.dev/health
```

`--containers-rollout=none` validates the Worker bundle when Docker is not running, but it does not build or update the Sandbox container image. A real deploy still needs Docker and Cloudflare Containers access.

After deploy, set these values in defaultspack or the runtime environment:

```bash
export RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL=https://rumi-cloudflare-sandbox-bridge.<your-subdomain>.workers.dev
export RUMI_CLOUDFLARE_SANDBOX_API_KEY=<the secret generated above>
```

## Test the Bridge

```bash
SANDBOX_ID=$(curl -s -X POST "$RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL/v1/sandbox" \
  -H "Authorization: Bearer $RUMI_CLOUDFLARE_SANDBOX_API_KEY" | jq -r '.id')

curl -N -X POST "$RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL/v1/sandbox/$SANDBOX_ID/exec" \
  -H "Authorization: Bearer $RUMI_CLOUDFLARE_SANDBOX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"argv":["sh","-lc","python3 --version && node --version"],"timeout_ms":10000,"cwd":"/workspace"}'

curl -X DELETE "$RUMI_CLOUDFLARE_SANDBOX_BRIDGE_URL/v1/sandbox/$SANDBOX_ID" \
  -H "Authorization: Bearer $RUMI_CLOUDFLARE_SANDBOX_API_KEY"
```

## Pages, Tunnels, and Permanent URLs

Cloudflare Pages is for static sites and app frontends. A `pages.dev` project is not a permanent tunnel to a Mac.

For a stable public URL to a local PC runtime, use a named Cloudflare Tunnel plus a DNS hostname on a Cloudflare-managed zone. Quick `trycloudflare.com` tunnels are useful for temporary testing, but they are not stable product URLs.

For sandbox preview URLs created by `exposePort()`, `.workers.dev` is not enough for wildcard preview subdomains. Production preview URLs need a custom domain with wildcard DNS routing. This bridge provider currently supports lifecycle, exec, and file writes; stable preview-port routing should be enabled only after the domain and TLS pieces are configured.
