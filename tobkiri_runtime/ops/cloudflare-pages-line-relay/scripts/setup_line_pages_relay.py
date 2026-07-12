#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PAGES_ROOT = Path(__file__).resolve().parents[1]
RUMI_ROOT = PAGES_ROOT.parents[1]
DEFAULTSPACK_ROOT = RUMI_ROOT / "ecosystem" / "defaultspack"
DEFAULT_PROJECT = "rumi-line-webhook-relay"
DEFAULT_PATH = "/api/integrations/line/webhook"
HTTP_USER_AGENT = "rumi-line-relay-setup/1.0"


def run(
    args: list[str],
    *,
    cwd: Path = PAGES_ROOT,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    printable = " ".join(args)
    print(f"+ {printable}")
    result = subprocess.run(
        args,
        cwd=str(cwd),
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if check and result.returncode:
        raise SystemExit(result.returncode)
    return result


def http_json(method: str, url: str, *, token: str | None = None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": HTTP_USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(text or "{}")
            except json.JSONDecodeError:
                return response.status, text
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(text or "{}")
        except json.JSONDecodeError:
            return error.code, text


def ensure_wrangler_login() -> None:
    result = run(["npx", "--yes", "wrangler", "whoami", "--install-skills=false"], check=False)
    if result.returncode == 0:
        return
    print("Wrangler is not logged in. A Cloudflare login page will open; approve it and return here.")
    run(["npx", "--yes", "wrangler", "login", "--install-skills=false"])


def ensure_project(project: str, branch: str, compatibility_date: str) -> None:
    result = run(
        [
            "npx",
            "--yes",
            "wrangler",
            "pages",
            "project",
            "create",
            project,
            "--production-branch",
            branch,
            "--compatibility-date",
            compatibility_date,
            "--install-skills=false",
        ],
        check=False,
    )
    output = result.stdout.lower()
    if result.returncode == 0 or "already exists" in output or "8000002" in output:
        return
    raise SystemExit(result.returncode)


def wait_for_pages_health(pages_url: str) -> Any:
    last_status: int | None = None
    last_payload: Any = None
    for attempt in range(1, 9):
        status, payload = http_json("GET", f"{pages_url.rstrip('/')}/api/relay-health")
        if status == 200:
            return payload
        last_status = status
        last_payload = payload
        print(f"Pages relay health not ready yet ({status}); retrying {attempt}/8...")
        time.sleep(min(2 * attempt, 10))
    raise SystemExit(f"Pages relay health failed: {last_status} {last_payload}")


def start_localtunnel(port: int) -> tuple[str, subprocess.Popen[str]]:
    proc = subprocess.Popen(
        ["npx", "--yes", "localtunnel", "--port", str(port)],
        cwd=str(RUMI_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    deadline = time.time() + 45
    url = ""
    pattern = re.compile(r"https://[a-z0-9-]+\.loca\.lt", re.IGNORECASE)
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            print(f"[localtunnel] {line}", end="")
            match = pattern.search(line)
            if match:
                url = match.group(0)
                break
        if proc.poll() is not None:
            raise SystemExit(proc.returncode or 1)
    if not url:
        proc.terminate()
        raise SystemExit("Could not read localtunnel URL from output.")
    return url, proc


def verify_origin(origin: str) -> None:
    status, payload = http_json("GET", f"{origin.rstrip('/')}/api/health")
    if status != 200:
        raise SystemExit(f"Origin health failed: {status} {payload}")
    print(f"Origin health ok: {origin}")


def set_pages_secret(project: str, name: str, value: str) -> None:
    run(
        [
            "npx",
            "--yes",
            "wrangler",
            "pages",
            "secret",
            "put",
            name,
            "--project-name",
            project,
            "--install-skills=false",
        ],
        input_text=f"{value}\n",
    )


def set_pages_origin(project: str, origin: str) -> None:
    set_pages_secret(project, "ORIGIN_BASE_URL", origin)


def line_secret_value(key: str) -> str:
    sys.path.insert(0, str(RUMI_ROOT))
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))
    from domain.integrations.secrets import get_integration_secret

    value = get_integration_secret("line", key, pack_root=DEFAULTSPACK_ROOT)
    if not value:
        raise SystemExit(f"{key} is not configured in defaultspack secrets.")
    return value


def set_pages_line_secret(project: str) -> None:
    set_pages_secret(project, "LINE_CHANNEL_SECRET", line_secret_value("LINE_CHANNEL_SECRET"))


def deploy_pages(project: str, branch: str) -> str:
    run(
        [
            "npx",
            "--yes",
            "wrangler",
            "pages",
            "deploy",
            "./public",
            "--project-name",
            project,
            "--branch",
            branch,
            "--commit-dirty=true",
            "--install-skills=false",
        ]
    )
    return f"https://{project}.pages.dev"


def line_token() -> str:
    return line_secret_value("LINE_CHANNEL_ACCESS_TOKEN")


def set_line_webhook(endpoint: str) -> None:
    token = line_token()
    set_status, set_payload = http_json(
        "PUT",
        "https://api.line.me/v2/bot/channel/webhook/endpoint",
        token=token,
        body={"endpoint": endpoint},
    )
    if set_status != 200:
        raise SystemExit(f"LINE webhook set failed: {set_status} {set_payload}")

    get_status, get_payload = http_json(
        "GET",
        "https://api.line.me/v2/bot/channel/webhook/endpoint",
        token=token,
    )
    if get_status != 200 or not isinstance(get_payload, dict) or get_payload.get("endpoint") != endpoint:
        raise SystemExit(f"LINE webhook readback failed: {get_status} {get_payload}")

    test_status, test_payload = http_json(
        "POST",
        "https://api.line.me/v2/bot/channel/webhook/test",
        token=token,
        body={"endpoint": endpoint},
    )
    if test_status != 200 or not isinstance(test_payload, dict) or not test_payload.get("success"):
        raise SystemExit(f"LINE webhook test failed: {test_status} {test_payload}")
    print(f"LINE webhook active: {get_payload.get('active')} test: {test_payload.get('success')}")


def update_local_endpoint_record(endpoint: str) -> None:
    path = DEFAULTSPACK_ROOT / "user_data" / "shared" / "webhooks" / "endpoints.json"
    if not path.exists():
        return
    data = json.loads(path.read_text())
    line_main = data.get("endpoints", {}).get("line-main")
    if not isinstance(line_main, dict):
        return
    public_url = line_main.setdefault("public_url", {})
    public_url["provider_id"] = "cloudflare_pages_relay"
    public_url["public_url"] = endpoint
    public_url["route_path"] = DEFAULT_PATH
    data["updated_at"] = int(time.time() * 1000)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"Updated local endpoint record: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create/update the Cloudflare Pages LINE webhook relay.")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT)
    parser.add_argument("--production-branch", default="master")
    parser.add_argument("--compatibility-date", default="2026-06-16")
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--origin-url", default="", help="Use an existing public origin instead of starting localtunnel.")
    parser.add_argument("--webhook-path", default=DEFAULT_PATH)
    parser.add_argument("--skip-line", action="store_true", help="Deploy relay but do not update LINE webhook settings.")
    parser.add_argument("--skip-deploy", action="store_true", help="Only update LINE to the existing Pages URL.")
    parser.add_argument("--oneshot", action="store_true", help="Exit after setup. Without this, keep localtunnel alive.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    localtunnel_proc: subprocess.Popen[str] | None = None
    origin = args.origin_url.strip().rstrip("/")

    if not origin and not args.skip_deploy:
        verify_origin(f"http://127.0.0.1:{args.port}")
        origin, localtunnel_proc = start_localtunnel(args.port)
    elif origin:
        verify_origin(origin)

    ensure_wrangler_login()
    if not args.skip_deploy:
        ensure_project(args.project_name, args.production_branch, args.compatibility_date)
        set_pages_origin(args.project_name, origin)
        set_pages_line_secret(args.project_name)
        pages_url = deploy_pages(args.project_name, args.production_branch)
    else:
        pages_url = f"https://{args.project_name}.pages.dev"

    endpoint = f"{pages_url.rstrip('/')}{args.webhook_path}"
    wait_for_pages_health(pages_url)
    print(f"Pages relay health ok: {pages_url}")

    if not args.skip_line:
        set_line_webhook(endpoint)
        update_local_endpoint_record(endpoint)

    print(f"Ready: {endpoint}")
    print("Send a message to the LINE bot manually to test the full chat path.")

    if localtunnel_proc and not args.oneshot:
        print("Keeping localtunnel alive. Press Ctrl-C to stop.")
        try:
            while localtunnel_proc.poll() is None:
                time.sleep(2)
        except KeyboardInterrupt:
            localtunnel_proc.send_signal(signal.SIGINT)
            localtunnel_proc.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
