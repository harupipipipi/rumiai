# Rumi Cloudflare PC Tunnel

Use this when a phone should reach the Mac/PC defaultspack runtime without scanning a new LAN QR every time.

Cloudflare Pages and `pages.dev` are for deployed frontend sites. They are not a permanent tunnel to a Mac. For stable phone-to-PC access, use a named Cloudflare Tunnel with a hostname on a domain managed by Cloudflare.

Quick `trycloudflare.com` tunnels are useful for smoke tests, but they generate random hostnames and do not support Server-Sent Events. Rumi chat streaming and tool progress should use a named tunnel instead. Do not put `trycloudflare.com`, `localhost`, or `192.168.x.x` in `RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME` for stable mobile access.

## Local Setup

```bash
cloudflared tunnel login
cloudflared tunnel create rumi-pc
cloudflared tunnel route dns rumi-pc rumi-pc.example.com
```

Wrangler OAuth can also create and list the named Tunnel:

```bash
npx wrangler tunnel create rumi-pc
npx wrangler tunnel list
```

That does not remove the DNS requirement. A stable phone-to-PC URL still needs a
public hostname on a Cloudflare-managed zone, such as `rumi-pc.example.com`.
Existing `*.pages.dev` project domains cannot be reused as tunnel hostnames. If
the account has no Cloudflare zone, add or buy a domain in Cloudflare first, then
create the tunnel public hostname from the Cloudflare dashboard or with
`cloudflared tunnel route dns`.

Copy `config.example.yml` to your cloudflared config directory, replace placeholders, and run:

```bash
cloudflared tunnel --config ~/.cloudflared/rumi-pc.yml run rumi-pc
```

Then set these values for defaultspack:

```bash
export RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME=rumi-pc.example.com
export RUMI_CLOUDFLARE_PC_TUNNEL_ORIGIN_URL=http://127.0.0.1:8765
export RUMI_CLOUDFLARE_PC_TUNNEL_CONFIG=~/.cloudflared/rumi-pc.yml
```

`RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME` must be a hostname only, not a full URL. Use `rumi-pc.example.com`, not `https://rumi-pc.example.com/path`.

## Requirements

- Cloudflare account
- A domain on Cloudflare for the stable hostname
- `cloudflared` installed on the PC
- defaultspack listening on the local origin URL

## Notes

- The DNS record points to `<TUNNEL_ID>.cfargotunnel.com`.
- The tunnel and DNS record are independent. If the tunnel is stopped, the hostname can exist but traffic will fail.
- Keep tunnel credentials and `cert.pem` out of git.
