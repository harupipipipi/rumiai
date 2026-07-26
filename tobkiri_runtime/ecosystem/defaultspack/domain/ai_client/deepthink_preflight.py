"""Provider-neutral, fail-closed readiness checks for DeepThink."""

from __future__ import annotations

from typing import Any


def deepthink_preflight(
    *,
    pack_root: Any = None,
    model: str | None = None,
    model_source: str = "conversation",
    tools: list[dict[str, Any]] | None = None,
    tool_policy: dict[str, Any] | None = None,
    budgets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the local DeepThink selection without coupling it to a provider."""

    del pack_root
    normalized_source = str(model_source or "conversation").strip().lower()
    selected_model = str(model or "").strip()
    checks = {
        "provider_neutral": True,
        "model_source": normalized_source,
        "selected_model": selected_model,
        "readiness_scope": "local_configuration",
        "remote_availability_checked": False,
        "tool_policy": "runtime_approval_enforced",
        "tool_budget": max(1, int((budgets or {}).get("max_tool_calls") or 16)),
    }
    failures: list[str] = []
    if normalized_source not in {"conversation", "selected"}:
        failures.append("model_source")
    if normalized_source == "selected" and not selected_model:
        failures.append("selected_model")
    if tools and not isinstance(tool_policy, dict):
        failures.append("tool_approval_policy")
    fixes = {
        "model_source": "Choose the conversation model or a Settings-selected model.",
        "selected_model": "Select a DeepThink model in Settings.",
        "tool_approval_policy": "Provide an explicit tool approval policy.",
    }
    return {
        "ready": not failures,
        "checks": checks,
        "failures": failures,
        "message": (
            "DeepThink is locally configured and provider-neutral; model availability "
            "is checked when the conversation runs."
            if not failures
            else "DeepThink preflight failed: {}".format(
                "; ".join(fixes.get(item, item) for item in failures)
            )
        ),
    }


def require_deepthink_ready(**kwargs: Any) -> dict[str, Any]:
    result = deepthink_preflight(**kwargs)
    if not result["ready"]:
        raise RuntimeError(result["message"])
    return result
