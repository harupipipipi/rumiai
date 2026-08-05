from __future__ import annotations

from typing import Any

class PackRecommendationServiceMixin:
    def pack_recommendations_preview(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        recommendations = self._pack_recommendations(args)
        return {
            "profile_id": self.profile_id,
            "recommendations": recommendations,
            "pack_recommendations": recommendations,
            "count": len(recommendations),
            "local_only": True,
        }

    def _pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        setup_pack_recommendations = self._setup_pack_recommendations(args)
        if setup_pack_recommendations:
            return setup_pack_recommendations
        return self._component_pack_recommendations(args)

    def _setup_pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        del args
        # Setup Pack selection is retired. The Launcher reads the finite v4
        # Host Pack Control catalog instead of importing a mutable manager.
        return []

    def _component_pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        answers = self._answers_from(args)
        use_cases = answers.get("use_cases") if isinstance(answers.get("use_cases"), dict) else {}
        actions = answers.get("actions") if isinstance(answers.get("actions"), dict) else {}
        selected = {str(key) for key, enabled in use_cases.items() if enabled is not False}
        desired: list[str] = []

        def add(component_id: str) -> None:
            if component_id not in desired:
                desired.append(component_id)

        if not selected or {"coding", "uc_coding", "repository", "frontend", "backend"} & selected:
            add("coding")
            add("context")
            add("agent")
        if {"research", "uc_research", "evidence"} & selected:
            add("research")
            add("knowledge")
            add("context")
        if {"automation", "uc_automation", "workflow"} & selected:
            add("scheduler")
            add("agent")
            add("tool")
        if answers.get("skill_learning_enabled"):
            add("prompt")
            add("memory")
        if str(answers.get("memory_mode") or "") not in {"", "off"}:
            add("memory")
        if str(actions.get("browser_control") or "") in {"ask", "allow"}:
            add("tool")
        if str(actions.get("external_send") or "") in {"ask", "allow"}:
            add("gateway")
        if not desired:
            desired.extend(["context", "memory", "tool"])

        components = self._component_manifest()
        recommendations: list[dict[str, Any]] = []
        for component_id in desired:
            component = components.get(component_id)
            if not isinstance(component, dict):
                continue
            recommendations.append(
                {
                    "pack_id": component_id,
                    "id": component_id,
                    "label": str(component.get("id") or component_id).replace("_", " ").title(),
                    "component_type": str(component.get("type") or component_id),
                    "reason": f"Local defaultspack component supports {component_id.replace('_', ' ')} work under this operating profile.",
                    "status": "recommended",
                    "confidence": 0.82,
                    "local_only": True,
                }
            )
        return recommendations

    def _component_manifest(self) -> dict[str, Any]:
        # Legacy ecosystem components are not Pack v4 recommendation authority.
        return {}
