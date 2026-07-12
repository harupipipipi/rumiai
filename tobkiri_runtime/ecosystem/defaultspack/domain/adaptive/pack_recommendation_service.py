from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import coerce_int


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
        try:
            from core_runtime.setup_pack import get_setup_pack_manager

            listed = get_setup_pack_manager().list_packs()
        except Exception:
            return []
        packs = listed.get("packs") if isinstance(listed, dict) else []
        if not isinstance(packs, list):
            return []
        signals = self._recommendation_signals(args)
        limit = coerce_int(args.get("limit"), 12, minimum=1, maximum=50)
        recommendations: list[dict[str, Any]] = []

        for raw_pack in packs:
            if not isinstance(raw_pack, dict):
                continue
            score, reasons = self._score_setup_pack(raw_pack, signals)
            if score <= 0:
                continue
            pack_id = str(raw_pack.get("pack_id") or "").strip()
            if not pack_id:
                continue
            target_pack_id = str(raw_pack.get("target_pack_id") or pack_id).strip() or pack_id
            recommendations.append(
                {
                    "pack_id": pack_id,
                    "setup_pack_id": pack_id,
                    "target_pack_id": target_pack_id,
                    "id": pack_id,
                    "label": str(raw_pack.get("display_name") or pack_id),
                    "description": str(raw_pack.get("description") or ""),
                    "reason": "; ".join(reasons[:3]),
                    "reasons": reasons[:5],
                    "status": "recommended",
                    "confidence": min(0.99, 0.55 + (score / 200)),
                    "score": score,
                    "risk_level": str(raw_pack.get("risk_level") or "medium"),
                    "supports_all_ok": bool(raw_pack.get("supports_all_ok")),
                    "required_permissions": raw_pack.get("required_permissions") if isinstance(raw_pack.get("required_permissions"), list) else [],
                    "install_surfaces": raw_pack.get("install_surfaces") if isinstance(raw_pack.get("install_surfaces"), list) else [],
                    "selected": bool(raw_pack.get("selected")),
                    "source": "setup_pack",
                    "local_only": True,
                }
            )
        recommendations.sort(
            key=lambda item: (
                item["selected"],
                item["score"],
                item["confidence"],
                item["risk_level"] == "low",
                item["pack_id"] == "defaultspack",
            ),
            reverse=True,
        )
        return recommendations[:limit]

    def _recommendation_signals(self, args: dict[str, Any]) -> set[str]:
        answers = self._answers_from(args)
        use_cases = answers.get("use_cases") if isinstance(answers.get("use_cases"), dict) else {}
        actions = answers.get("actions") if isinstance(answers.get("actions"), dict) else {}
        selected = {str(key) for key, enabled in use_cases.items() if enabled is not False}
        signals = {"baseline"}
        if not selected or {"coding", "uc_coding", "repository", "backend", "code"} & selected:
            signals.update({"coding", "workspace"})
        if {"frontend", "ui", "design", "app"} & selected:
            signals.update({"frontend", "browser", "qa"})
        if {"research", "uc_research", "evidence", "knowledge"} & selected:
            signals.update({"research", "knowledge", "evidence"})
        if {"automation", "uc_automation", "workflow", "scheduler"} & selected:
            signals.update({"automation", "workflow", "agent"})
        if str(actions.get("terminal") or "") in {"ask", "allow"}:
            signals.update({"coding", "tool"})
        if str(actions.get("browser_control") or "") in {"ask", "allow"}:
            signals.update({"browser", "qa"})
        if str(actions.get("external_send") or "") in {"ask", "allow"}:
            signals.update({"connector", "gateway"})
        if str(actions.get("computer_control") or "") in {"ask", "allow"}:
            signals.update({"computer", "tool"})
        if answers.get("skill_learning_enabled"):
            signals.update({"prompt", "skill", "knowledge"})
        if str(answers.get("memory_mode") or "") not in {"", "off"}:
            signals.update({"memory", "knowledge", "continuity"})
        return signals

    def _score_setup_pack(self, pack: dict[str, Any], signals: set[str]) -> tuple[int, list[str]]:
        pack_id = str(pack.get("pack_id") or "")
        display_name = str(pack.get("display_name") or "")
        description = str(pack.get("description") or "")
        marketplace = pack.get("marketplace") if isinstance(pack.get("marketplace"), dict) else {}
        haystack = " ".join(
            [
                pack_id,
                display_name,
                description,
                str(marketplace.get("category") or ""),
                str(marketplace.get("id") or ""),
            ]
        ).lower()
        keyword_map: dict[str, tuple[str, ...]] = {
            "baseline": ("defaultspack", "default tools", "local agent"),
            "coding": ("code", "ide", "devops", "migration", "security review"),
            "workspace": ("workspace", "sandbox"),
            "frontend": ("frontend", "ui", "design", "artifact app"),
            "browser": ("browser", "form", "session replay", "element"),
            "qa": ("qa", "evidence", "eval", "benchmark"),
            "research": ("research", "dossier", "experiment", "customer"),
            "knowledge": ("knowledge", "memory", "document", "meeting"),
            "evidence": ("evidence", "observability", "review"),
            "automation": ("automation", "ambient", "workflow", "scheduler"),
            "workflow": ("workflow", "scheduler", "operations", "sop"),
            "agent": ("agent", "workroom", "services", "continuity"),
            "tool": ("tool", "host capabilities", "api toolsmith"),
            "connector": ("connector", "mcp", "omnichannel", "telephony"),
            "gateway": ("gateway", "connector", "mcp"),
            "computer": ("computer", "control"),
            "prompt": ("prompt", "studio"),
            "skill": ("prompt", "studio", "marketplace"),
            "memory": ("memory", "continuity"),
            "continuity": ("continuity", "memory"),
        }
        representative_pack_map: dict[str, tuple[str, ...]] = {
            "baseline": ("defaultspack", "rumi_default_tools_pack", "rumi_local_agent_pack"),
            "coding": ("rumi_code_ide_pack", "rumi_default_tools_pack"),
            "workspace": ("rumi_workspace_pack", "rumi_sandbox_runtime_pack"),
            "frontend": ("rumi_frontend_design_pack", "rumi_artifact_app_runtime_pack"),
            "browser": ("rumi_browser_automation_pack", "rumi_browser_element_pack"),
            "qa": ("rumi_agentic_qa_pack", "rumi_evidence_dossier_pack"),
            "research": ("rumi_research_pack", "rumi_customer_research_pack"),
            "knowledge": ("rumi_memory_knowledge_pack", "rumi_knowledge_marketplace_pack"),
            "evidence": ("rumi_evidence_dossier_pack", "rumi_observability_pack"),
            "automation": ("rumi_workflow_scheduler_pack", "rumi_ambient_trigger_pack"),
            "workflow": ("rumi_workflow_scheduler_pack", "rumi_business_ops_pack"),
            "agent": ("rumi_local_agent_pack", "rumi_agent_services_pack"),
            "tool": ("rumi_default_tools_pack", "rumi_host_capabilities_pack"),
            "connector": ("rumi_connector_gateway_pack", "rumi_mcp_gateway_pack"),
            "gateway": ("rumi_connector_gateway_pack", "rumi_mcp_gateway_pack"),
            "computer": ("rumi_computer_control_pack",),
            "prompt": ("rumi_prompt_studio_pack",),
            "skill": ("rumi_prompt_studio_pack", "rumi_knowledge_marketplace_pack"),
            "memory": ("rumi_memory_knowledge_pack", "rumi_agent_continuity_pack"),
            "continuity": ("rumi_agent_continuity_pack", "rumi_memory_knowledge_pack"),
        }
        score = 0
        reasons: list[str] = []
        if bool(pack.get("recommended")):
            score += 18
            reasons.append("bundled setup pack is marked recommended")
        if bool(pack.get("selected")):
            score += 10
            reasons.append("already selected in setup-pack configuration")
        for signal in sorted(signals):
            if pack_id in representative_pack_map.get(signal, ()):
                score += 24
                reasons.append(f"representative setup pack for {signal}")
            keywords = keyword_map.get(signal, ())
            if keywords and any(keyword in haystack for keyword in keywords):
                score += 14
                reasons.append(f"matches {signal} onboarding signal")
        if str(pack.get("risk_level") or "") == "low":
            score += 4
        if pack_id == "defaultspack":
            score += 8
        if not reasons and score > 0:
            reasons.append("compatible local setup-pack candidate")
        return score, reasons

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
        manifest_path = Path(__file__).resolve().parents[2] / "ecosystem.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        components = manifest.get("components")
        return components if isinstance(components, dict) else {}
