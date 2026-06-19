# Rumi LINE Webhook Relay

Cloudflare Pages Function that gives LINE a stable `*.pages.dev` webhook URL while forwarding requests to the current local defaultspack tunnel.

The relay preserves the LINE request body and `x-line-signature` header. Signature verification and reply/push behavior stay in defaultspack.

## One Command Setup

Start defaultspack locally, then run:

```bash
python scripts/setup_line_pages_relay.py --port 18766
```

The script will:

- Open Cloudflare login if Wrangler is not authenticated.
- Start a `localtunnel` origin for the local defaultspack port.
- Create or update the Cloudflare Pages project.
- Store the current origin in the Pages `ORIGIN_BASE_URL` secret.
- Deploy the relay.
- Set and verify the LINE webhook URL through the LINE Messaging API.

After that, send a message to the LINE bot manually to test the full chat flow.

## Stable LINE Webhook URL

```text
https://rumi-line-webhook-relay.pages.dev/api/integrations/line/webhook
```

## Existing Origin

If another process already created the public origin:

```bash
python scripts/setup_line_pages_relay.py --origin-url https://example.loca.lt --oneshot
```

## Relay Health

```bash
curl https://rumi-line-webhook-relay.pages.dev/api/relay-health
curl https://rumi-line-webhook-relay.pages.dev/api/health
```

`/api/relay-health` reports relay configuration. Other paths are forwarded to defaultspack.
