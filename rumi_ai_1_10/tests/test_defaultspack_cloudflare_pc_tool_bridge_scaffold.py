from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "ecosystem" / "defaultspack" / "cloudflare" / "pc_tool_bridge"


def test_cloudflare_pc_tool_bridge_scaffold_has_expected_files() -> None:
    expected = {
        "package.json",
        "tsconfig.json",
        "wrangler.jsonc",
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


def test_cloudflare_pc_tool_bridge_wrangler_config_is_worker_only() -> None:
    config = _load_jsonc(SCAFFOLD / "wrangler.jsonc")

    assert config["name"] == "rumi-cloudflare-pc-tool-bridge"
    assert config["main"] == "src/index.ts"
    assert config["compatibility_date"] == "2026-07-01"
    assert config["compatibility_flags"] == ["nodejs_compat"]
    assert config["observability"]["enabled"] is True
    assert "containers" not in config
    assert "durable_objects" not in config
    assert "RUMI_PC_TOOL_BRIDGE_TOKEN" not in json.dumps(config)
    assert "RUMI_PC_RUNTIME_BEARER" not in json.dumps(config)


def test_cloudflare_pc_tool_bridge_worker_only_proxies_allowlisted_routes() -> None:
    source = (SCAFFOLD / "src" / "index.ts").read_text(encoding="utf-8")

    assert "const PROXY_ROUTES" in source
    assert 'target: "/api/tools/catalog"' in source
    assert 'target: "/api/tools/names"' in source
    assert 'target: "/api/tools/invoke"' in source
    assert 'target: "/api/authority/requests"' in source
    assert "new URL(path, pcOrigin)" in source
    assert "requestUrl.pathname" not in source
    assert "RUMI_PC_RUNTIME_BEARER" in source
    assert "RUMI_PC_TOOL_BRIDGE_TOKEN" in source
    assert "RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN" in source
    assert "timingSafeTokenEqual" in source
    assert "Access-Control-Allow-Origin\", origin" in source
    assert "pages_dev_is_not_a_pc_tunnel_hostname" in source
    assert "trycloudflare_is_not_stable" in source
    assert "pc_origin_must_be_public_tunnel_hostname" in source


def test_cloudflare_pc_tool_bridge_readme_states_non_goals_and_cors() -> None:
    readme = (SCAFFOLD / "README.md").read_text(encoding="utf-8")
    dev_vars = (SCAFFOLD / ".dev.vars.example").read_text(encoding="utf-8")

    assert "does not upload PC-local tools to Cloudflare" in readme
    assert "does not bypass" in readme
    assert "named Cloudflare Tunnel" in readme
    assert "pages.dev" in readme
    assert "trycloudflare.com" in readme
    assert "does not allow arbitrary proxying" in readme
    assert "RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN" in readme
    assert "does not reflect arbitrary" in readme
    assert "RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN=https://app.example.com" in dev_vars


def test_cloudflare_pc_tool_bridge_package_uses_workers_types_and_wrangler() -> None:
    package = json.loads((SCAFFOLD / "package.json").read_text(encoding="utf-8"))
    tsconfig = json.loads((SCAFFOLD / "tsconfig.json").read_text(encoding="utf-8"))

    assert package["private"] is True
    assert package["scripts"]["check"] == "tsc --noEmit"
    assert package["scripts"]["types"] == "wrangler types"
    assert package["devDependencies"]["wrangler"] == "4.106.0"
    assert "@cloudflare/workers-types" in package["devDependencies"]
    assert tsconfig["compilerOptions"]["strict"] is True
    assert tsconfig["compilerOptions"]["types"] == ["@cloudflare/workers-types"]


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
