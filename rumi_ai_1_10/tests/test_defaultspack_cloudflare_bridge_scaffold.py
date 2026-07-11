from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "ecosystem" / "defaultspack" / "cloudflare" / "sandbox_bridge"


def test_cloudflare_sandbox_bridge_scaffold_has_expected_files() -> None:
    expected = {
        "package.json",
        "tsconfig.json",
        "wrangler.jsonc",
        "Dockerfile",
        "src/index.ts",
        ".dev.vars.example",
        ".gitignore",
        "README.md",
    }

    assert expected <= {
        str(path.relative_to(SCAFFOLD))
        for path in SCAFFOLD.rglob("*")
        if path.is_file()
    }


def test_cloudflare_sandbox_bridge_wrangler_config_matches_bridge_requirements() -> None:
    config = _load_jsonc(SCAFFOLD / "wrangler.jsonc")

    assert config["name"] == "rumi-cloudflare-sandbox-bridge"
    assert config["main"] == "src/index.ts"
    assert config["compatibility_date"] == "2026-07-01"
    assert config["compatibility_flags"] == ["nodejs_compat"]
    assert config["containers"] == [
        {
            "class_name": "Sandbox",
            "image": "./Dockerfile",
            "instance_type": "lite",
            "max_instances": 1,
        }
    ]
    assert config["durable_objects"]["bindings"] == [
        {"class_name": "Sandbox", "name": "Sandbox"},
        {"class_name": "WarmPool", "name": "WarmPool"},
    ]
    assert config["migrations"] == [
        {"tag": "v1", "new_sqlite_classes": ["Sandbox", "WarmPool"]}
    ]
    assert "SANDBOX_API_KEY" not in json.dumps(config)
    assert config["vars"]["WARM_POOL_TARGET"] == "0"


def test_cloudflare_sandbox_bridge_worker_uses_official_bridge_wrapper() -> None:
    source = (SCAFFOLD / "src" / "index.ts").read_text(encoding="utf-8")

    assert 'import { bridge } from "@cloudflare/sandbox/bridge";' in source
    assert 'export { Sandbox } from "@cloudflare/sandbox";' in source
    assert 'export { WarmPool } from "@cloudflare/sandbox/bridge";' in source
    assert 'apiRoutePrefix: "/v1"' in source
    assert 'healthRoute: "/health"' in source
    assert "SANDBOX_API_KEY=" not in source
    assert "<your-token>" not in source


def test_cloudflare_sandbox_bridge_package_pins_known_bridge_runtime() -> None:
    package = json.loads((SCAFFOLD / "package.json").read_text(encoding="utf-8"))

    assert package["private"] is True
    assert package["dependencies"]["@cloudflare/sandbox"] == "0.12.3"
    assert package["devDependencies"]["wrangler"] == "4.107.0"
    assert package["scripts"]["deploy"] == "wrangler deploy"


def test_cloudflare_sandbox_bridge_dockerfile_uses_matching_base_image() -> None:
    dockerfile = (SCAFFOLD / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM docker.io/cloudflare/sandbox:0.12.3" in dockerfile
    assert "COPY " not in dockerfile


def test_cloudflare_sandbox_bridge_readme_states_pages_and_tool_limits() -> None:
    readme = (SCAFFOLD / "README.md").read_text(encoding="utf-8")

    assert "pages.dev" in readme
    assert "permanent tunnel to a Mac" in readme
    assert "named Cloudflare Tunnel plus a DNS hostname" in readme
    assert "does not upload or replace PC-local browser" in readme
    assert "Workers Paid plan" in readme


def _load_jsonc(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    return json.loads(_strip_jsonc_comments(text))


def _strip_jsonc_comments(text: str) -> str:
    result: list[str] = []
    i = 0
    in_string = False
    quote = ""
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                in_string = False
            i += 1
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
            result.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)
