from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .api_key_store import provider_key_status
from .providers import get_provider_catalog


CONTRACT_VERSION = "provider-health.v1"


def provider_health_report(
    *,
    pack_root: Path | None = None,
    active_provider_ids: Iterable[str] | None = None,
    provider_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return sanitized provider health and credential-source diagnostics."""

    allowed_ids = {str(item).strip() for item in provider_ids or [] if str(item).strip()}
    catalog = get_provider_catalog(active_provider_ids=active_provider_ids)
    catalog_by_id = {str(item.get("provider_id") or ""): item for item in catalog}
    key_rows = {
        str(item.get("provider_id") or ""): item
        for item in provider_key_status(pack_root=pack_root)
    }

    providers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in catalog:
        provider_id = str(entry.get("provider_id") or "").strip()
        if not provider_id or (allowed_ids and provider_id not in allowed_ids):
            continue
        seen_ids.add(provider_id)
        providers.append(_provider_health(entry, key_rows.get(provider_id, {})))

    for provider_id in sorted(set(key_rows) - seen_ids):
        if allowed_ids and provider_id not in allowed_ids:
            continue
        providers.append(_provider_health(_synthetic_catalog_entry(key_rows[provider_id]), key_rows[provider_id]))

    summary = _summary(providers)
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": _utc_now(),
        "summary": summary,
        "providers": providers,
    }


def _provider_health(
    catalog_entry: dict[str, Any],
    key_row: dict[str, Any],
) -> dict[str, Any]:
    provider_id = str(catalog_entry.get("provider_id") or key_row.get("provider_id") or "")
    availability = dict(catalog_entry.get("availability") or {})
    credential = _credential_status(provider_id, catalog_entry, key_row)
    runtime = {
        "configured": bool(availability.get("configured")),
        "status": str(availability.get("status") or "unknown"),
        "configuration_source": str(availability.get("configuration_source") or ""),
        "supports_invoke": bool(availability.get("supports_invoke")),
        "catalog_only": bool(availability.get("catalog_only")),
        "active": bool(availability.get("active")),
    }
    diagnostics = _diagnostics(provider_id, runtime, credential)
    return {
        "provider_id": provider_id,
        "display_name": str(catalog_entry.get("display_name") or catalog_entry.get("name") or provider_id),
        "kind": str(catalog_entry.get("kind") or key_row.get("kind") or ""),
        "status": _health_status(runtime, credential),
        "health_code": _health_code(runtime, credential),
        "runtime": runtime,
        "credential": credential,
        "models": {
            "default_model": str(catalog_entry.get("default_model") or ""),
            "default_model_for": dict(catalog_entry.get("default_model_for") or {}),
        },
        "diagnostics": diagnostics,
    }


def _credential_status(
    provider_id: str,
    catalog_entry: dict[str, Any],
    key_row: dict[str, Any],
) -> dict[str, Any]:
    env_keys = _unique_strings(
        [
            *list(catalog_entry.get("env_vars") or []),
            *list(key_row.get("keys") or []),
            str(key_row.get("key") or ""),
        ]
    )
    oauth = _oauth_status(catalog_entry, key_row)
    named_keys = [
        item
        for item in list(key_row.get("apis") or [])
        if isinstance(item, dict) and item.get("configured")
    ]
    source = "none"
    source_detail = ""
    configured = False
    masked = False

    if _oauth_connected(oauth):
        source = "oauth"
        source_detail = str(oauth.get("status") or "connected")
        configured = True
        masked = True
    else:
        env_key = next((key for key in env_keys if _truthy_env(key)), "")
        if env_key:
            source = "env"
            source_detail = env_key
            configured = True
            masked = True
        elif named_keys:
            source = "named_api_key"
            source_detail = str(named_keys[0].get("api_id") or named_keys[0].get("name") or "")
            configured = True
            masked = True
        elif key_row.get("configured"):
            source = "defaultspack_secret"
            source_detail = str(key_row.get("key") or (env_keys[0] if env_keys else ""))
            configured = True
            masked = True
        elif provider_id == "stub":
            source = "builtin"
            source_detail = "stub"
            configured = True

    return {
        "configured": configured,
        "source": source,
        "source_detail": source_detail,
        "masked": masked,
        "env_keys": env_keys,
        "named_api_key_count": len(named_keys),
        "oauth": _compact_oauth_status(oauth),
    }


def _diagnostics(
    provider_id: str,
    runtime: dict[str, Any],
    credential: dict[str, Any],
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    runtime_source = str(runtime.get("configuration_source") or "")
    source = str(credential.get("source") or "none")
    source_detail = str(credential.get("source_detail") or "")
    runtime_configured = bool(runtime.get("configured"))
    credential_configured = bool(credential.get("configured"))

    if source == "env" and runtime_source and runtime_source != source_detail:
        diagnostics.append(
            _diagnostic(
                "warning",
                "provider_key_source_mismatch",
                "Provider runtime source does not match the detected environment key.",
            )
        )
    elif source == "defaultspack_secret" and runtime_source not in {"", "defaultspack_secret"}:
        diagnostics.append(
            _diagnostic(
                "warning",
                "provider_key_source_mismatch",
                "Provider runtime source does not match the detected secret-store key.",
            )
        )

    local_sources = {"builtin", "builtin_local_provider", "default_local_endpoint", "no_key_gateway"}
    if (
        runtime_configured != credential_configured
        and runtime_source not in local_sources
        and source not in local_sources
    ):
        diagnostics.append(
            _diagnostic(
                "warning",
                "provider_configured_state_mismatch",
                "Provider runtime and key-source status disagree.",
            )
        )

    if _health_code(runtime, credential) == "auth_missing":
        diagnostics.append(
            _diagnostic(
                "error",
                "auth_missing",
                "Provider has no configured API key, OAuth connection, or local no-key route.",
            )
        )
    elif bool(runtime.get("catalog_only")):
        diagnostics.append(
            _diagnostic(
                "info",
                "catalog_only",
                "Provider is catalog-only until a runtime adapter is available.",
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "info",
                "provider_key_source_consistent",
                f"{provider_id} credential source is {source}.",
            )
        )
    return diagnostics


def _health_status(runtime: dict[str, Any], credential: dict[str, Any]) -> str:
    code = _health_code(runtime, credential)
    if code == "ok":
        return "configured"
    if code == "catalog_only":
        return "catalog_only"
    if code == "auth_missing":
        return "missing_credentials"
    return code


def _health_code(runtime: dict[str, Any], credential: dict[str, Any]) -> str:
    source = str(credential.get("source") or "")
    runtime_source = str(runtime.get("configuration_source") or "")
    if bool(runtime.get("catalog_only")):
        return "catalog_only"
    if bool(credential.get("configured")) or bool(runtime.get("configured")):
        return "ok"
    if source in {"builtin", "no_key_gateway"} or runtime_source in {
        "builtin",
        "builtin_local_provider",
        "default_local_endpoint",
        "no_key_gateway",
    }:
        return "ok"
    if bool(runtime.get("supports_invoke")):
        return "auth_missing"
    return "unknown"


def _synthetic_catalog_entry(key_row: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(key_row.get("provider_id") or "")
    configured = bool(key_row.get("configured"))
    return {
        "provider_id": provider_id,
        "display_name": str(key_row.get("label") or provider_id),
        "kind": str(key_row.get("kind") or ""),
        "env_vars": list(key_row.get("keys") or []),
        "default_model": "",
        "default_model_for": {},
        "availability": {
            "configured": configured,
            "status": "configured" if configured else "unconfigured",
            "configuration_source": "defaultspack_secret" if configured else "",
            "supports_invoke": True,
            "catalog_only": False,
            "active": False,
        },
        "metadata": {"oauth": key_row.get("oauth") or {}},
    }


def _summary(providers: list[dict[str, Any]]) -> dict[str, int]:
    warnings = 0
    errors = 0
    for provider in providers:
        for diagnostic in list(provider.get("diagnostics") or []):
            severity = str(diagnostic.get("severity") or "")
            if severity == "warning":
                warnings += 1
            elif severity == "error":
                errors += 1
    return {
        "total": len(providers),
        "configured": sum(1 for item in providers if item.get("status") == "configured"),
        "missing_credentials": sum(1 for item in providers if item.get("status") == "missing_credentials"),
        "catalog_only": sum(1 for item in providers if item.get("status") == "catalog_only"),
        "warnings": warnings,
        "errors": errors,
    }


def _oauth_status(catalog_entry: dict[str, Any], key_row: dict[str, Any]) -> dict[str, Any]:
    oauth = key_row.get("oauth")
    if isinstance(oauth, dict):
        return oauth
    metadata = catalog_entry.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("oauth"), dict):
        return metadata["oauth"]
    return {}


def _compact_oauth_status(oauth: dict[str, Any]) -> dict[str, Any]:
    return {
        "supported": bool(oauth.get("supported")),
        "connected": _oauth_connected(oauth),
        "status": str(oauth.get("status") or oauth.get("connection_status") or ""),
        "display_label": str(oauth.get("display_label") or oauth.get("display_name") or ""),
    }


def _oauth_connected(oauth: dict[str, Any]) -> bool:
    return bool(oauth.get("connected")) or str(oauth.get("status") or "") == "connected"


def _diagnostic(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _truthy_env(name: str) -> bool:
    return bool(str(os.environ.get(str(name or ""), "") or "").strip())


def _unique_strings(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
