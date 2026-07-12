# Rumi LINE Webhook Relay

Cloudflare Pages Function that gives LINE a stable `*.pages.dev` webhook URL while forwarding requests to the current local defaultspack tunnel.

The relay validates the LINE `x-line-signature` header with the raw request body before forwarding. Defaultspack repeats provider-signature validation and keeps reply/push behavior local.

This relay is opt-in operational tooling. It is not imported by defaultspack startup and does not create network connections unless you run the setup script manually.

## One Command Setup

Start defaultspack locally, then run:

```bash
python scripts/setup_line_pages_relay.py --port 18766
```

The script will:

- Open a Cloudflare login page if Wrangler is not authenticated.
- Start a `localtunnel` origin for the local defaultspack port.
- Create the Cloudflare Pages project if it does not already exist.
- Overwrite the Pages `ORIGIN_BASE_URL` secret with the current origin.
- Overwrite the Pages `LINE_CHANNEL_SECRET` secret from defaultspack's configured LINE channel secret.
- Deploy the relay.
- Set and verify the LINE webhook URL through the LINE Messaging API.

The setup reads `LINE_CHANNEL_SECRET` and `LINE_CHANNEL_ACCESS_TOKEN` from defaultspack secrets. It sends the channel secret only to `wrangler pages secret put` stdin and uses the access token only in the LINE Messaging API `Authorization` header; neither value is printed by the script.

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

Use `--skip-deploy` only when the Pages project already has current `ORIGIN_BASE_URL` and `LINE_CHANNEL_SECRET` secrets. That mode only updates LINE to the existing Pages URL.

## Relay Health

```bash
curl https://rumi-line-webhook-relay.pages.dev/api/relay-health
curl https://rumi-line-webhook-relay.pages.dev/api/health
```

`/api/relay-health` reports booleans only and does not reveal the origin URL. `/api/health` is forwarded to defaultspack. The only other exposed path is `POST /api/integrations/line/webhook`; invalid or missing LINE signatures are rejected before forwarding.
