from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class CapabilityCatalog:
    """Loads defaultspack's local-first service manifests."""

    def __init__(self, pack_root: Optional[Path] = None) -> None:
        self.pack_root = Path(pack_root) if pack_root is not None else Path(__file__).resolve().parents[2]

    def _load_yaml_dir(self, directory_name: str, suffix: str) -> List[Dict[str, Any]]:
        directory = self.pack_root / directory_name
        if not directory.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for path in sorted(directory.glob("*" + suffix)):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                data = {"id": path.stem, "error": str(exc)}
            if isinstance(data, dict):
                data.setdefault("id", path.name.replace(suffix, ""))
                data["_source_path"] = str(path.relative_to(self.pack_root))
                items.append(data)
        return items

    def capabilities(self, local_only: Any = None, risk_level: Optional[str] = None) -> List[Dict[str, Any]]:
        items = self._load_yaml_dir("capabilities", ".capability.yaml")
        if local_only is not None:
            expected = local_only
            if isinstance(expected, str):
                expected = expected.lower() in {"1", "true", "yes"}
            items = [item for item in items if item.get("local_only") == expected]
        if risk_level:
            items = [item for item in items if item.get("risk_level") == risk_level]
        return items

    def capability(self, capability_id: str) -> Optional[Dict[str, Any]]:
        for item in self.capabilities():
            if item.get("id") == capability_id or item.get("capability_id") == capability_id:
                return item
        return None

    def profiles(self) -> List[Dict[str, Any]]:
        return self._load_yaml_dir("profiles", ".profile.yaml")

    def presets(self) -> List[Dict[str, Any]]:
        return self._load_yaml_dir("presets", ".preset.yaml")

    def schemas(self) -> List[Dict[str, Any]]:
        return self._load_yaml_dir("schemas", ".schema.yaml")

    def examples(self) -> List[Dict[str, Any]]:
        return self._load_yaml_dir("examples", ".example.yaml")

    def prompts(self) -> List[Dict[str, Any]]:
        prompt_dir = self.pack_root / "prompts"
        if not prompt_dir.is_dir():
            return []
        prompts: List[Dict[str, Any]] = []
        for path in sorted(prompt_dir.glob("*.system.md")):
            text = path.read_text(encoding="utf-8")
            prompts.append(
                {
                    "id": path.name.replace(".system.md", ""),
                    "name": path.stem.replace(".system", ""),
                    "content_ref": str(path.relative_to(self.pack_root)),
                    "preview": text.strip().splitlines()[0] if text.strip() else "",
                }
            )
        return prompts

    def feature_catalog(self) -> Dict[str, Any]:
        path = self.pack_root / "docs" / "ai_agent_services_feature_catalog.md"
        return {
            "content_ref": str(path.relative_to(self.pack_root)),
            "exists": path.is_file(),
        }

    def profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        for profile in self.profiles():
            if profile.get("profile_id") == profile_id or profile.get("id") == profile_id:
                return profile
        return None

    def manifest(self) -> Dict[str, Any]:
        capabilities = self.capabilities()
        profiles = self.profiles()
        presets = self.presets()
        return {
            "service_id": "defaultspack.ai_agent_service",
            "version": "rumi.defaultspack.agent_service.v1",
            "local_first": True,
            "core_requires_api_key": False,
            "default_profile": "defaultspack.local_agent",
            "counts": {
                "capabilities": len(capabilities),
                "profiles": len(profiles),
                "presets": len(presets),
                "schemas": len(self.schemas()),
                "prompts": len(self.prompts()),
                "examples": len(self.examples()),
            },
            "capabilities": capabilities,
            "profiles": profiles,
            "presets": presets,
            "feature_catalog": self.feature_catalog(),
            "runtime": {
                "platforms": ["Darwin", "Windows"],
                "can_run_24_7": True,
                "scheduler": {
                    "mode": "in_process_threading_timer",
                    "armed_on_http_server_start": True,
                    "requires_process_alive": True,
                },
                "activation_modes": ["manual", "scheduled", "non_stop", "webhook"],
                "webhook": {
                    "local_route_template": "/api/agents/{agent_id}/webhook",
                    "cloudflare_pages_url": "https://rumi-agent-webhook.pages.dev/api/agent-webhook",
                    "custom_url_supported": True,
                },
            },
            "policy": {
                "network_default": "deny",
                "write_actions_require_approval": True,
                "delete_actions_require_approval": True,
                "terminal_actions_require_approval": True,
                "git_push_requires_approval": True,
                "secrets_redacted": True,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.manifest(), ensure_ascii=False, indent=2)
