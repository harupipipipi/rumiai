from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "ecosystem" / "defaultspack" / "cloudflare" / "pc_tunnel"


def test_cloudflare_pc_tunnel_scaffold_documents_named_tunnel_not_pages() -> None:
    readme = (SCAFFOLD / "README.md").read_text(encoding="utf-8")
    config = (SCAFFOLD / "config.example.yml").read_text(encoding="utf-8")
    ignore = (SCAFFOLD / ".gitignore").read_text(encoding="utf-8")

    assert "pages.dev" in readme
    assert "not a permanent tunnel to a Mac" in readme
    assert "named Cloudflare Tunnel" in readme
    assert "do not support Server-Sent Events" in readme
    assert "cloudflared tunnel route dns rumi-pc rumi-pc.example.com" in readme
    assert "explicitly installed Wrangler binary" in readme
    assert "npx wrangler" not in readme
    assert "RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME" in readme
    assert "hostname: rumi-pc.example.com" in config
    assert "service: http://127.0.0.1:8765" in config
    assert "service: http_status:404" in config
    assert "cert.pem" in ignore
