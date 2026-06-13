"""Unified defaultspack tool policy and execution orchestration."""

__all__ = ["PolicyDecision", "ToolOrchestrator", "ToolRisk"]


def __getattr__(name: str):
    if name in {"PolicyDecision", "ToolRisk"}:
        from .models import PolicyDecision, ToolRisk

        return {
            "PolicyDecision": PolicyDecision,
            "ToolRisk": ToolRisk,
        }[name]
    if name == "ToolOrchestrator":
        from .orchestrator import ToolOrchestrator

        return ToolOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
