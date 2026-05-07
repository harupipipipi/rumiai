from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
WEBAPP_ROOT = DEFAULTSPACK_ROOT / "webapp"


def _failures() -> list[str]:
    return []


def _route_specs() -> list[tuple[str, str, str]]:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))
    from transport.registry import _ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS, _FALLBACK_HTTP_ROUTE_SPECS

    specs = [*_FALLBACK_HTTP_ROUTE_SPECS, *_ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS]
    return [(spec.method, spec.pattern, spec.block_module) for spec in specs]


def _module_path(block_module: str) -> Path:
    return DEFAULTSPACK_ROOT / Path(block_module.replace(".", "/") + ".py")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_api_endpoints() -> set[str]:
    api_ts = WEBAPP_ROOT / "src" / "lib" / "api.ts"
    text = api_ts.read_text(encoding="utf-8")
    endpoints: set[str] = set()
    for match in re.finditer(r"([\"'`])(/api/[^\"'`]+)\1", text):
        endpoint = match.group(2)
        if "${" in endpoint:
            continue
        endpoint = re.sub(r"\$\{[^}]+\}", "{id}", endpoint)
        endpoint = endpoint.split("?", 1)[0]
        endpoints.add(endpoint)
    return endpoints


def _normalize_route(pattern: str) -> str:
    return re.sub(r"\{[^}]+\}", "{id}", pattern)


def check_ecosystem_manifest(errors: list[str]) -> None:
    manifest = _read_json(DEFAULTSPACK_ROOT / "ecosystem.json")
    if manifest.get("pack_id") != "defaultspack":
        errors.append("ecosystem.json pack_id must be defaultspack")
    if manifest.get("pack_identity") != "rumi:ecosystem/defaultspack":
        errors.append("ecosystem.json pack_identity must be rumi:ecosystem/defaultspack")
    for route in manifest.get("api_routes", []):
        function_id = route.get("function_id")
        if not function_id:
            continue
        if not (DEFAULTSPACK_ROOT / "functions" / function_id / "manifest.json").is_file():
            errors.append(f"api route references missing function manifest: {function_id}")
        if not (DEFAULTSPACK_ROOT / "functions" / function_id / "main.py").is_file():
            errors.append(f"api route references missing function main.py: {function_id}")


def check_routes(errors: list[str]) -> None:
    seen: set[tuple[str, str]] = set()
    for method, pattern, block_module in _route_specs():
        key = (method, pattern)
        if key in seen:
            errors.append(f"duplicate fallback route: {method} {pattern}")
        seen.add(key)
        if block_module and not _module_path(block_module).is_file():
            errors.append(f"route references missing block module: {method} {pattern} -> {block_module}")


def check_frontend_route_parity(errors: list[str]) -> None:
    backend = {_normalize_route(pattern) for _, pattern, _ in _route_specs()}
    optional_prefixes = ("/api/agent/company/",)
    for endpoint in sorted(_extract_api_endpoints()):
        if endpoint in backend:
            continue
        if any(endpoint.startswith(prefix) for prefix in optional_prefixes):
            continue
        errors.append(f"frontend endpoint has no fallback route: {endpoint}")


def check_function_aliases(errors: list[str]) -> None:
    alias_owner: dict[str, str] = {}
    for manifest_path in sorted((DEFAULTSPACK_ROOT / "functions").glob("*/manifest.json")):
        manifest = _read_json(manifest_path)
        function_id = manifest.get("function_id") or manifest.get("name")
        if function_id != manifest_path.parent.name:
            errors.append(f"function_id mismatch in {manifest_path}")
        aliases = manifest.get("vocab_aliases") or []
        if not any(str(alias).startswith("defaultspack.") for alias in aliases):
            errors.append(f"missing defaultspack.* alias for {function_id}")
        if manifest.get("calling_convention") == "subprocess" and not any(
            str(alias).startswith("defaults.") for alias in aliases
        ):
            errors.append(f"missing defaults.* alias for generated function {function_id}")
        for alias in aliases:
            if alias in alias_owner:
                errors.append(f"duplicate function alias {alias}: {alias_owner[alias]} and {function_id}")
            alias_owner[str(alias)] = str(function_id)


def check_local_first_defaults(errors: list[str]) -> None:
    critical_files = [
        DEFAULTSPACK_ROOT / "domain" / "ai_client" / "model_runtime_settings.py",
        DEFAULTSPACK_ROOT / "domain" / "chat" / "store.py",
        DEFAULTSPACK_ROOT / "domain" / "frontend" / "registry.py",
        WEBAPP_ROOT / "src" / "App.tsx",
    ]
    forbidden_defaults = [
        "DEFAULT_CHAT_MODEL = \"openrouter/",
        "preferred_model ?? \"openrouter/",
        "\"default\": \"openrouter/",
        "model_api_routes\": \"openrouter/",
    ]
    for path in critical_files:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_defaults:
            if needle in text:
                errors.append(f"cloud model remains in local default path: {path.relative_to(ROOT)} contains {needle}")


def check_sensitive_guard(errors: list[str]) -> None:
    http_text = (DEFAULTSPACK_ROOT / "transport" / "http.py").read_text(encoding="utf-8")
    if "require_local_guard(" not in http_text:
        errors.append("transport/http.py does not call require_local_guard for sensitive coding paths")
    approval_text = (DEFAULTSPACK_ROOT / "blocks" / "coding" / "_approval.py").read_text(encoding="utf-8")
    for needle in ("hash_arguments", "verify_execution_token", "create_approval_request"):
        if needle not in approval_text:
            errors.append(f"coding approval helper missing {needle}")


def check_python_syntax(errors: list[str], paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"syntax error in {path.relative_to(ROOT)}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.parse_args()
    errors = _failures()
    check_ecosystem_manifest(errors)
    check_routes(errors)
    check_frontend_route_parity(errors)
    check_function_aliases(errors)
    check_local_first_defaults(errors)
    check_sensitive_guard(errors)
    check_python_syntax(
        errors,
        [
            DEFAULTSPACK_ROOT / "domain" / "safety" / "approval.py",
            DEFAULTSPACK_ROOT / "domain" / "safety" / "audit.py",
            DEFAULTSPACK_ROOT / "domain" / "safety" / "local_guard.py",
            DEFAULTSPACK_ROOT / "blocks" / "coding" / "_approval.py",
        ],
    )
    if errors:
        print("defaultspack integrity scan failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("defaultspack integrity scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
