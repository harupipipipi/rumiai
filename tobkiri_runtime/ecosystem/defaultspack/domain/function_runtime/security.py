from __future__ import annotations

HIGH_RISK_CALLER_REQUIREMENT = "user.approved.high_risk"
GLOBAL_MODEL_RUNTIME_CALLER_REQUIREMENT = "user.approved.model_runtime_global"


def caller_requires_for_risk(risk: str) -> list[str]:
    return [HIGH_RISK_CALLER_REQUIREMENT] if risk == "high" else []


def is_high_risk(function_id: str) -> bool:
    tokens = function_id.split("_")
    return any(
        marker in function_id
        for marker in (
            "file_write",
            "file_create",
            "file_delete",
            "terminal_exec",
            "terminal_stream",
            "git_commit",
            "git_push",
            "clipboard_write",
            "provider_key",
            "forced_patch",
            "set_module_state",
            "browser_",
            "computer_",
        )
    ) or tokens[-1:] in (["delete"], ["push"])
