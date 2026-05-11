from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
import time
from typing import Any

from domain.webhook.url_provider import WebhookUrlProvider


_TRY_CLOUDFLARE_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
_TUNNELS: dict[str, subprocess.Popen[str]] = {}
_TUNNEL_META: dict[str, dict[str, Any]] = {}


def _read_pipe(pipe, output: "queue.Queue[str]") -> None:
    try:
        for line in iter(pipe.readline, ""):
            output.put(line)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _join_public_url(base_url: str, route_path: str) -> str:
    return base_url.rstrip("/") + "/" + str(route_path or "/").lstrip("/")


class CloudflareQuickTunnelProvider(WebhookUrlProvider):
    provider_id = "cloudflare_quick_tunnel"

    def create_url(self, *, local_url: str, route_path: str, ttl_seconds: int = 0, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del ttl_seconds
        context = context or {}
        if not shutil.which("cloudflared"):
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "cloudflared is not installed",
                "command": "cloudflared tunnel --url " + local_url,
                "route_path": route_path,
            }
        command = ["cloudflared", "tunnel", "--url", local_url]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": str(exc),
                "command": " ".join(command),
                "route_path": route_path,
            }

        output: "queue.Queue[str]" = queue.Queue()
        for pipe in (process.stdout, process.stderr):
            if pipe is None:
                continue
            threading.Thread(target=_read_pipe, args=(pipe, output), daemon=True).start()

        timeout_seconds = float(context.get("timeout_seconds") or 12)
        deadline = time.monotonic() + max(1.0, min(timeout_seconds, 30.0))
        log_lines: list[str] = []
        public_base_url = ""
        while time.monotonic() < deadline:
            if process.poll() is not None and output.empty():
                break
            try:
                line = output.get(timeout=0.2)
            except queue.Empty:
                continue
            cleaned = line.strip()
            if cleaned:
                log_lines.append(cleaned)
            match = _TRY_CLOUDFLARE_RE.search(line)
            if match:
                public_base_url = match.group(0)
                break

        if not public_base_url:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "cloudflared started but no trycloudflare URL was detected",
                "command": " ".join(command),
                "route_path": route_path,
                "logs": log_lines[-12:],
            }

        url_id = f"cfqt_{process.pid}"
        public_url = _join_public_url(public_base_url, route_path)
        _TUNNELS[url_id] = process
        _TUNNEL_META[url_id] = {
            "provider": self.provider_id,
            "url_id": url_id,
            "public_base_url": public_base_url,
            "public_url": public_url,
            "local_url": local_url,
            "route_path": route_path,
            "command": " ".join(command),
            "created_at": time.time(),
        }
        return {
            "ok": True,
            "provider": self.provider_id,
            "url_id": url_id,
            "public_base_url": public_base_url,
            "public_url": public_url,
            "local_url": local_url,
            "route_path": route_path,
        }

    def close_url(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        process = _TUNNELS.pop(url_id, None)
        meta = _TUNNEL_META.pop(url_id, {})
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        return {"ok": True, "provider": self.provider_id, "url_id": url_id, "closed": True, **meta}

    def status(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        process = _TUNNELS.get(url_id)
        if process is None:
            return {"ok": False, "provider": self.provider_id, "url_id": url_id, "error": "no cloudflared process is tracked"}
        meta = dict(_TUNNEL_META.get(url_id) or {})
        running = process.poll() is None
        return {"ok": running, "provider": self.provider_id, "url_id": url_id, "running": running, **meta}
