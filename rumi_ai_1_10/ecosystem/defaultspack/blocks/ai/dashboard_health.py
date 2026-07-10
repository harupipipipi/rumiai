"""Sanitized dashboard health primitives for defaultspack."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blocks._common import ok


PROVIDER_FAILURE_AUTH_MISSING = "PROVIDER_AUTH_MISSING"
PROVIDER_FAILURE_RUNTIME_UNREGISTERED = "PROVIDER_RUNTIME_UNREGISTERED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any, *, max_length: int = 80) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _catalog_age_seconds(provider_id: str) -> int | None:
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return None
    models_path = Path(__file__).resolve().parents[2] / "domain" / "providers" / provider_id / "models.json"
    try:
        mtime = models_path.stat().st_mtime
    except OSError:
        return None
    return max(0, int(datetime.now(timezone.utc).timestamp() - mtime))


def classify_provider_failure(provider: dict[str, Any]) -> dict[str, str] | None:
    """Return a stable, sanitized provider failure classification."""
    configured = bool(provider.get("configured"))
    requires_auth = str(provider.get("auth_mode") or "").lower() in {"api_key", "oauth"}
    if requires_auth and not configured:
        return {
            "code": PROVIDER_FAILURE_AUTH_MISSING,
            "message": "Provider credentials are not configured.",
        }
    if configured and not provider.get("registered"):
        return {
            "code": PROVIDER_FAILURE_RUNTIME_UNREGISTERED,
            "message": "Provider is configured but not active in the runtime registry.",
        }
    return None


def _provider_health() -> dict[str, Any]:
    from domain.ai_client.api_key_store import provider_key_status
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_provider_catalog
    from ecosystem.defaultspack.domain.ai_client.client import AIClient

    key_rows = {
        str(row.get("provider_id") or ""): row
        for row in provider_key_status()
        if isinstance(row, dict) and row.get("provider_id")
    }
    runtime_rows = {
        str(row.get("provider_id") or row.get("id") or ""): row
        for row in AIClient().list_providers()
        if isinstance(row, dict) and (row.get("provider_id") or row.get("id"))
    }
    providers: list[dict[str, Any]] = []
    for catalog_row in list_provider_catalog():
        if not isinstance(catalog_row, dict):
            continue
        provider_id = str(catalog_row.get("provider_id") or "").strip()
        if not provider_id:
            continue
        key_row = key_rows.get(provider_id, {})
        oauth = key_row.get("oauth") if isinstance(key_row.get("oauth"), dict) else {}
        apis = key_row.get("apis") if isinstance(key_row.get("apis"), list) else []
        has_oauth = bool(oauth.get("connected") or oauth.get("configured"))
        configured = bool(key_row.get("configured") or has_oauth)
        auth_mode = "oauth" if has_oauth else "api_key" if key_row.get("key") else "none"
        key_source = "oauth" if has_oauth else "named_api_key" if apis else "legacy_secret" if configured else "missing"
        runtime = runtime_rows.get(provider_id)
        item = {
            "provider_id": provider_id,
            "label": _safe_text(catalog_row.get("display_name") or catalog_row.get("label") or provider_id),
            "kind": _safe_text(catalog_row.get("kind") or key_row.get("kind") or ""),
            "registered": bool(runtime),
            "configured": configured,
            "auth_mode": auth_mode,
            "key_source": key_source,
            "model_catalog_age_seconds": _catalog_age_seconds(provider_id),
            "quota_classification": _safe_text(
                next(
                    (
                        api.get("quota_label")
                        for api in apis
                        if isinstance(api, dict) and api.get("quota_label")
                    ),
                    "",
                )
            )
            or "unknown",
            "last_error": None,
        }
        item["failure"] = classify_provider_failure(item)
        providers.append(item)
    failing = [item for item in providers if item.get("failure")]
    return {
        "providers": providers,
        "count": len(providers),
        "configured_count": sum(1 for item in providers if item.get("configured")),
        "failure_count": len(failing),
        "failure_codes": sorted({item["failure"]["code"] for item in failing if item.get("failure")}),
    }


def _env_status(name: str) -> str:
    return "configured" if str(os.environ.get(name) or "").strip() else "missing"


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(str(value or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _gateway_health() -> dict[str, Any]:
    return {
        "local_url": _safe_text(os.environ.get("RUMI_DEFAULTSPACK_LOCAL_URL") or os.environ.get("RUMI_DEFAULTSPACK_BASE_URL") or "http://127.0.0.1"),
        "tunnel_url": _env_status("RUMI_TUNNEL_URL"),
        "webhook_url": _env_status("RUMI_WEBHOOK_URL"),
        "active_devices": _safe_int(os.environ.get("RUMI_ACTIVE_DEVICE_COUNT")),
        "token_expires_at": _safe_text(os.environ.get("RUMI_GATEWAY_TOKEN_EXPIRES_AT") or ""),
    }


def _authority_requests() -> list[dict[str, Any]]:
    try:
        from core_runtime.authority import get_authority_service

        result = get_authority_service().list_requests("all")
    except Exception:
        return []
    requests = result.get("requests") if isinstance(result, dict) else []
    return [item for item in requests if isinstance(item, dict)]


def _approval_summary(item: dict[str, Any]) -> str:
    permission_id = _safe_text(item.get("permission_id"), max_length=96) or "approval"
    status = _safe_text(item.get("status"), max_length=24) or "unknown"
    risk_level = _safe_text(item.get("risk_level"), max_length=24) or "unknown"
    return f"{permission_id}: {status} / {risk_level}"


def _approval_health() -> dict[str, Any]:
    requests = _authority_requests()
    counts = {"pending": 0, "approved": 0, "denied": 0, "expired": 0}
    risky = 0
    replayed = 0
    for item in requests:
        status = str(item.get("status") or "").lower()
        if status in counts:
            counts[status] += 1
        risk = str(item.get("risk_level") or "").lower()
        if risk in {"high", "critical"}:
            risky += 1
        resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
        if resource.get("replayed") or resource.get("replay"):
            replayed += 1
    recent = [
        {
            "request_id": _safe_text(item.get("request_id"), max_length=64),
            "status": _safe_text(item.get("status"), max_length=24),
            "permission_id": _safe_text(item.get("permission_id"), max_length=96),
            "risk_level": _safe_text(item.get("risk_level"), max_length=24),
            "created_at": _safe_text(item.get("created_at"), max_length=40),
            "expires_at": _safe_text(item.get("expires_at"), max_length=40),
            "summary": _approval_summary(item),
        }
        for item in requests[:5]
    ]
    return {
        "pending": counts["pending"],
        "recent": recent,
        "denied": counts["denied"],
        "risky": risky,
        "replayed": replayed,
        "counts": counts,
    }


def _runtime_health() -> dict[str, Any]:
    try:
        from core_runtime.health import get_health_checker

        aggregate = get_health_checker().aggregate_health(timeout=0.2)
    except Exception:
        aggregate = {"status": "UNKNOWN", "probes": {}}
    return {
        "status": _safe_text(aggregate.get("status") if isinstance(aggregate, dict) else "UNKNOWN"),
        "probe_count": len(aggregate.get("probes") or {}) if isinstance(aggregate, dict) else 0,
        "last_smoke_run": _safe_text(os.environ.get("RUMI_LAST_SMOKE_RUN_AT") or ""),
        "failed_scenario": _safe_text(os.environ.get("RUMI_LAST_SMOKE_FAILED_SCENARIO") or ""),
        "open_regression_issues": [],
    }


def _tool_risk_map() -> dict[str, Any]:
    return {
        "items": [],
        "contract": {
            "tool": "tool id",
            "capability": "capability id",
            "approval_requirement": "none | required | high_risk",
            "recent_usage": "count or last-used summary",
        },
    }


def _pack_integrity() -> dict[str, Any]:
    return {
        "approved_hash": "",
        "changed_files": [],
        "pending_reapproval": False,
        "status": "not_connected",
    }


def build_dashboard_health() -> dict[str, Any]:
    """Build a dashboard-safe health payload without secret material."""
    return {
        "generated_at": _utc_now(),
        "provider": _provider_health(),
        "gateway": _gateway_health(),
        "approval": _approval_health(),
        "tool_risk_map": _tool_risk_map(),
        "pack_integrity": _pack_integrity(),
        "runtime": _runtime_health(),
    }


def run(input_data, context):
    del input_data, context
    return ok(build_dashboard_health())
