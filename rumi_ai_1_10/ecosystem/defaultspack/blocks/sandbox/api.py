from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

try:
    from blocks._common import error, ok, timestamp
except ModuleNotFoundError:
    from ecosystem.defaultspack.blocks._common import error, ok, timestamp


RUNTIME_NOT_READY = "MANAGED_RUNTIME_NOT_READY"


def run(input_data: dict[str, Any] | None, context: dict[str, Any] | None = None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    handler = str(payload.get("_handler") or "runtime_providers")
    if handler == "runtime_providers":
        return ok(_runtime_providers())
    if handler == "runtime_doctor":
        return ok(_runtime_doctor())
    if handler == "runtime_ensure":
        return ok(_runtime_operation("failed", provider_id=payload.get("provider_id")))
    if handler == "runtime_update":
        return ok(_runtime_operation("failed", provider_id=payload.get("provider_id"), operation_id="managed-runtime-update"))
    if handler == "runtime_uninstall":
        return ok(_runtime_operation("failed", provider_id=payload.get("provider_id"), operation_id="managed-runtime-uninstall"))
    if handler == "runtime_operations":
        return ok({"operations": []})
    if handler in {"runtime_operation", "runtime_operation_get"}:
        return ok(_runtime_operation("failed", operation_id=str(payload.get("operation_id") or "runtime-operation")))
    if handler in {"runtime_cancel", "runtime_operation_cancel"}:
        return ok(_runtime_operation("cancelled", operation_id=str(payload.get("operation_id") or "runtime-operation")))
    if handler == "sandbox_templates":
        return ok({"templates": _template_summaries()})
    if handler == "sandboxes_list":
        return ok({"sandboxes": []})
    if handler == "sandboxes_create":
        return error("Managed sandbox runtime is not ready.", RUNTIME_NOT_READY)
    if handler == "desktops_list":
        return ok({"desktops": []})
    if handler == "desktops_create":
        return error("Managed desktop runtime is not ready.", RUNTIME_NOT_READY)
    if handler.startswith("desktop_") or handler.startswith("sandbox_"):
        return error("Managed sandbox runtime is not ready.", RUNTIME_NOT_READY)
    return error(f"Unknown sandbox API handler: {handler}", "UNKNOWN_SANDBOX_API_HANDLER")


def _runtime_providers() -> dict[str, Any]:
    provider = _selected_provider()
    providers = [provider, _docker_provider()]
    return {
        "providers": providers,
        "selected_provider_id": provider["provider_id"],
        "default_provider_id": provider["provider_id"],
        "runtime_version": None,
        "guest_protocol": 1,
    }


def _runtime_doctor() -> dict[str, Any]:
    provider = _selected_provider()
    return {
        "status": "needs_setup",
        "providers": [provider, _docker_provider()],
        "selected_provider_id": provider["provider_id"],
        "missing": provider["missing"],
        "message": "Rumi Managed Runtime needs bundled provider setup before desktops can start.",
        "diagnostics": {
            "runtime_api": "available",
            "execution_provider": "not_bundled",
            "generated_at": timestamp(),
        },
        "generated_at": timestamp(),
    }


def _runtime_operation(status: str, *, provider_id: Any = None, operation_id: str = "managed-runtime-setup") -> dict[str, Any]:
    selected = _selected_provider()
    return {
        "operation_id": operation_id,
        "status": status,
        "step": "provider_setup_unavailable",
        "message": "This build exposes the managed runtime API, but the OS provider setup helper is not bundled yet.",
        "progress": 0,
        "reboot_required": False,
        "provider_id": str(provider_id or selected["provider_id"]),
        "updated_at": timestamp(),
        "error": {
            "code": RUNTIME_NOT_READY,
            "message": "Managed runtime provider setup is not available in this build.",
        } if status == "failed" else None,
    }


def _selected_provider() -> dict[str, Any]:
    system = platform.system().lower()
    if system == "darwin":
        provider_id = "mac_lima"
        label = "Rumi-managed Lima Ubuntu"
        missing_code = "lima_provider_not_bundled"
        isolation = {
            "mode": "vm_pending",
            "vm": True,
            "container": False,
            "summary": "macOS desktops require a Rumi-managed Lima Ubuntu VM after explicit setup consent.",
        }
    elif system == "windows":
        provider_id = "windows_wsl"
        label = "RumiUbuntu WSL2"
        missing_code = "wsl_provider_not_bundled"
        isolation = {
            "mode": "wsl2_pending",
            "vm": True,
            "container": False,
            "summary": "Windows desktops require a Rumi-owned RumiUbuntu WSL2 distribution after explicit setup consent.",
        }
    else:
        provider_id = "linux_native"
        label = "Linux native Xvfb/Openbox"
        missing_code = "linux_native_provider_not_bundled"
        isolation = {
            "mode": "native_pending",
            "vm": False,
            "container": False,
            "host_process_namespace": True,
            "host_filesystem_shared": True,
            "host_network_shared": True,
            "summary": "Linux native provider is not active; native Xvfb alone is not VM isolation.",
            "warnings": ["Linux native isolation depends on bubblewrap/systemd capabilities when implemented."],
        }
    return {
        "provider_id": provider_id,
        "label": label,
        "status": "needs_setup",
        "available": False,
        "selected": True,
        "managed": True,
        "platform": platform.system().lower() or "unknown",
        "version": None,
        "guest_protocol": 1,
        "missing": [{
            "code": missing_code,
            "severity": "warning",
            "message": "Managed provider setup helper is not bundled in this build.",
            "remediation": "Use the managed runtime diagnostics bundle when continuing provider implementation.",
        }],
        "isolation": isolation,
        "message": "Setup is required before managed desktops can start.",
    }


def _docker_provider() -> dict[str, Any]:
    return {
        "provider_id": "docker",
        "label": "Docker-compatible runtime",
        "status": "unavailable",
        "available": False,
        "selected": False,
        "managed": False,
        "platform": platform.system().lower() or "unknown",
        "version": None,
        "guest_protocol": 1,
        "missing": [{
            "code": "docker_optional_not_selected",
            "severity": "info",
            "message": "Docker-compatible providers are optional and are not installed or selected by Rumi automatically.",
        }],
        "isolation": {
            "mode": "container_optional",
            "container": True,
            "summary": "Optional provider only; Docker Desktop is never installed silently.",
        },
        "message": "Optional provider only.",
    }


def _template_summaries() -> list[dict[str, Any]]:
    templates_dir = _repo_root() / "rumi_ai_1_10" / "ecosystem" / "rumi_sandbox_runtime_pack" / "templates"
    summaries: list[dict[str, Any]] = []
    for path in sorted(templates_dir.glob("*/template.json")):
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        template_id = str(template.get("id") or path.parent.name)
        policy = template.get("policy") if isinstance(template.get("policy"), dict) else {}
        runtime = template.get("runtime") if isinstance(template.get("runtime"), dict) else {}
        filesystem = policy.get("filesystem") if isinstance(policy.get("filesystem"), dict) else {}
        workspace = filesystem.get("workspace") if isinstance(filesystem.get("workspace"), dict) else {}
        network = policy.get("network") if isinstance(policy.get("network"), dict) else {}
        desktop = policy.get("desktop") if isinstance(policy.get("desktop"), dict) else {}
        summaries.append({
            "template_id": template_id,
            "name": template.get("display_name") or template_id,
            "description": template.get("summary") or "",
            "kind": template_id.split(".", 1)[0],
            "default_provider_id": runtime.get("provider") or "auto",
            "provider_requirements": runtime.get("provider_requirements") or [],
            "capabilities": runtime.get("capabilities") or [],
            "network_policy": {
                "summary": str(network.get("mode") or "off"),
                "default": str(network.get("mode") or "off"),
                "allowed": network.get("allowlist") or [],
            },
            "workspace_access": {
                "summary": str(workspace.get("access") or "none"),
                "mode": str(workspace.get("access") or "none"),
            },
            "isolation": {
                "mode": "desktop" if desktop.get("enabled") else "sandbox",
                "vm": None,
                "container": None,
                "summary": "Runtime isolation is reported by the selected provider at creation time.",
            },
        })
    return summaries


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]
