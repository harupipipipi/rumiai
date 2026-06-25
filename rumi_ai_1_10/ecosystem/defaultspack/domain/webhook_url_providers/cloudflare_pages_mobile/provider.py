from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from domain.webhook.url_provider import WebhookUrlProvider


_LOGIN_PROCESS: subprocess.Popen[str] | None = None
_PROJECT_RE = re.compile(r"[^a-z0-9-]+")
_DEFAULT_ROUTE_PATH = "/"


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _user_data_root() -> Path:
    configured = os.environ.get("RUMI_USER_DATA", "").strip()
    return Path(configured).expanduser() if configured else _pack_root() / "user_data"


def _state_dir() -> Path:
    root = _user_data_root() / "shared" / "cloudflare_pages_mobile"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path() -> Path:
    return _state_dir() / "status.json"


def _project_dir() -> Path:
    root = _state_dir() / "project"
    (root / "functions" / "api").mkdir(parents=True, exist_ok=True)
    (root / "public").mkdir(parents=True, exist_ok=True)
    return root


def _join_public_url(base_url: str, route_path: str) -> str:
    return base_url.rstrip("/") + "/" + str(route_path or _DEFAULT_ROUTE_PATH).lstrip("/")


def _safe_output(text: str, limit: int = 4000) -> str:
    value = text[-limit:]
    value = re.sub(r"(?i)(api[_-]?token|authorization|secret|password)(\s*[:=]\s*)\S+", r"\1\2[redacted]", value)
    return value


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd or _project_dir()),
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _wrangler_args(*args: str) -> list[str]:
    return ["npx", "--yes", "wrangler", *args, "--install-skills=false"]


def _default_project_name() -> str:
    seed = f"{platform.node()}:{_user_data_root()}".encode("utf-8", "replace")
    suffix = hashlib.sha256(seed).hexdigest()[:8]
    return f"rumi-mobile-{suffix}"


def _sanitize_project_name(value: str | None) -> str:
    raw = (value or _default_project_name()).strip().lower()
    cleaned = _PROJECT_RE.sub("-", raw).strip("-")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"rumi-mobile-{cleaned or hashlib.sha256(raw.encode()).hexdigest()[:8]}"
    return cleaned[:58].rstrip("-") or _default_project_name()


def _is_private_or_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def _write_project_files(project_name: str) -> None:
    root = _project_dir()
    compatibility_date = "2026-06-25"
    (root / "wrangler.jsonc").write_text(
        json.dumps(
            {
                "name": project_name,
                "compatibility_date": compatibility_date,
                "pages_build_output_dir": "./public",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "public" / "index.html").write_text(
        """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Rumi Mobile</title>
    <style>
      body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #09090b; color: #e4e4e7; }
      main { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
      section { max-width: 560px; border: 1px solid #27272a; border-radius: 16px; background: #111113; padding: 24px; }
      h1 { margin: 0 0 8px; font-size: 22px; }
      p { margin: 8px 0; color: #a1a1aa; line-height: 1.7; }
      code { color: #fafafa; }
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>Rumi Mobile relay</h1>
        <p>このURLはRumi Mobile用のCloudflare Pagesエントリポイントです。</p>
        <p>PC側の設定画面で表示されるQRから、承認済みのmobile APIへ接続してください。</p>
        <p>Health: <code>/api/relay-health</code></p>
      </section>
    </main>
  </body>
</html>
""",
        encoding="utf-8",
    )
    (root / "functions" / "api" / "[[path]].js").write_text(
        """const ALLOWED_PREFIXES = [
  "/api/health",
  "/api/mobile/v1/",
  "/api/p2p/pairing/"
];

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function normalizedPath(context) {
  const raw = context.params.path;
  const path = Array.isArray(raw) ? raw.join("/") : String(raw || "");
  return `/api/${path}`.replace(/\\/+/g, "/");
}

export async function onRequest(context) {
  const path = normalizedPath(context);
  if (path === "/api/relay-health") {
    return json({
      ok: true,
      provider: "cloudflare_pages_mobile",
      origin_configured: Boolean(context.env.ORIGIN_BASE_URL),
      allowed_prefixes: ALLOWED_PREFIXES
    });
  }

  const allowed = ALLOWED_PREFIXES.some((prefix) => path === prefix || path.startsWith(prefix));
  if (!allowed) {
    return json({ ok: false, error: "route not exposed by mobile relay" }, 404);
  }

  const origin = String(context.env.ORIGIN_BASE_URL || "").replace(/\\/+$/, "");
  if (!origin) {
    return json({ ok: false, error: "ORIGIN_BASE_URL is not configured" }, 503);
  }

  const inputUrl = new URL(context.request.url);
  const target = `${origin}${path}${inputUrl.search}`;
  const headers = new Headers(context.request.headers);
  headers.set("x-rumi-cloudflare-relay", "pages-mobile");
  headers.delete("host");

  return fetch(target, {
    method: context.request.method,
    headers,
    body: ["GET", "HEAD"].includes(context.request.method) ? undefined : context.request.body,
    redirect: "manual"
  });
}
""",
        encoding="utf-8",
    )


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(payload: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _whoami() -> dict[str, Any]:
    result = _run(_wrangler_args("whoami"), timeout=45)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "output": _safe_output(result.stdout or ""),
    }


def _login_status() -> dict[str, Any]:
    global _LOGIN_PROCESS
    if _LOGIN_PROCESS is None:
        auth = _whoami()
        return {"logged_in": bool(auth["ok"]), "login_running": False, "auth": auth}
    returncode = _LOGIN_PROCESS.poll()
    if returncode is None:
        return {"logged_in": False, "login_running": True}
    _LOGIN_PROCESS = None
    auth = _whoami()
    return {"logged_in": bool(auth["ok"]), "login_running": False, "auth": auth}


class CloudflarePagesMobileProvider(WebhookUrlProvider):
    provider_id = "cloudflare_pages_mobile"

    def create_url(self, *, local_url: str, route_path: str, ttl_seconds: int = 0, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del ttl_seconds
        request_data = (context or {}).get("request_data") or {}
        action = str(request_data.get("action") or "deploy").strip().lower()
        if action == "login":
            return self._start_login()
        if action == "status":
            return self.status("default", context=context)
        return self._deploy(local_url=local_url, route_path=route_path, request_data=request_data)

    def _start_login(self) -> dict[str, Any]:
        global _LOGIN_PROCESS
        status = _login_status()
        if status.get("logged_in"):
            return {"ok": True, "provider": self.provider_id, "logged_in": True, "login_running": False}
        if _LOGIN_PROCESS is not None and _LOGIN_PROCESS.poll() is None:
            return {"ok": True, "provider": self.provider_id, "logged_in": False, "login_running": True}
        try:
            _LOGIN_PROCESS = subprocess.Popen(
                _wrangler_args("login"),
                cwd=str(_project_dir()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            return {"ok": False, "provider": self.provider_id, "error": str(exc), "needs_login": True}
        return {
            "ok": True,
            "provider": self.provider_id,
            "logged_in": False,
            "login_running": True,
            "message": "Cloudflare login started. Approve the browser prompt, then deploy again.",
        }

    def _deploy(self, *, local_url: str, route_path: str, request_data: dict[str, Any]) -> dict[str, Any]:
        project_name = _sanitize_project_name(str(request_data.get("project_name") or ""))
        local_url = str(local_url or "").strip().rstrip("/")
        if not local_url:
            return {"ok": False, "provider": self.provider_id, "error": "local_url is required"}
        auth = _whoami()
        if not auth["ok"]:
            return {
                "ok": False,
                "provider": self.provider_id,
                "needs_login": True,
                "error": "Cloudflare login is required",
                "auth": auth,
            }

        _write_project_files(project_name)
        create = _run(
            _wrangler_args(
                "pages",
                "project",
                "create",
                project_name,
                "--production-branch",
                "production",
                "--compatibility-date",
                "2026-06-25",
            ),
            timeout=90,
        )
        create_output = (create.stdout or "").lower()
        if create.returncode != 0 and "already exists" not in create_output and "8000002" not in create_output:
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "failed to create Cloudflare Pages project",
                "output": _safe_output(create.stdout or ""),
            }

        secret = _run(
            _wrangler_args("pages", "secret", "put", "ORIGIN_BASE_URL", "--project-name", project_name),
            input_text=f"{local_url}\n",
            timeout=90,
        )
        if secret.returncode != 0:
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "failed to set ORIGIN_BASE_URL secret",
                "output": _safe_output(secret.stdout or ""),
            }

        deploy = _run(
            _wrangler_args(
                "pages",
                "deploy",
                "./public",
                "--project-name",
                project_name,
                "--branch",
                "production",
                "--commit-dirty=true",
            ),
            timeout=180,
        )
        if deploy.returncode != 0:
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "failed to deploy Cloudflare Pages project",
                "output": _safe_output(deploy.stdout or ""),
            }

        public_base_url = f"https://{project_name}.pages.dev"
        public_url = _join_public_url(public_base_url, route_path)
        state = {
            "ok": True,
            "provider": self.provider_id,
            "url_id": project_name,
            "project_name": project_name,
            "public_base_url": public_base_url,
            "public_url": public_url,
            "local_url": local_url,
            "route_path": route_path,
            "private_origin_warning": _is_private_or_loopback_url(local_url),
            "updated_at": time.time(),
        }
        _save_state(state)
        return state

    def close_url(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        state = _load_state()
        if state.get("url_id") == url_id or not url_id:
            _save_state({**state, "closed": True, "closed_at": time.time()})
        return {"ok": True, "provider": self.provider_id, "url_id": url_id, "closed": True}

    def status(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del url_id, context
        state = _load_state()
        return {
            "ok": True,
            "provider": self.provider_id,
            "state": state,
            **_login_status(),
        }
