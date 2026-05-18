from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .component_profiles import profile_specs_from_components
from .output_profile import OutputProfile


class OutputProfileRegistry:
    def __init__(self, pack_root: Path | None = None) -> None:
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]

    def list_profiles(self) -> list[OutputProfile]:
        profiles: list[OutputProfile] = []
        for directory in self._builtin_profile_dirs():
            for path in sorted(directory.glob("*.profile.yaml")):
                profile = self._load(path)
                if profile is not None:
                    profiles.append(profile)
        profiles.extend(
            OutputProfile.from_dict(spec)
            for spec in profile_specs_from_components(self.pack_root, "output_profiles")
        )
        for directory in self._custom_profile_dirs():
            for path in sorted(directory.glob("*.profile.yaml")):
                profile = self._load(path)
                if profile is not None:
                    profiles.append(profile)
        deduped: dict[str, OutputProfile] = {}
        for profile in profiles:
            deduped[profile.id] = profile
        return list(deduped.values())

    def get(self, profile_id: str) -> OutputProfile | None:
        for profile in self.list_profiles():
            if profile.id == profile_id:
                return profile
        return None

    def default_for_provider(self, provider: str) -> OutputProfile | None:
        preferred_ids = [f"{provider}.default", f"{provider}.bot_channel", f"{provider}.webhook", "generic.webhook"]
        for profile_id in preferred_ids:
            profile = self.get(profile_id)
            if profile is not None and (profile.provider == provider or profile_id == "generic.webhook"):
                return profile
        for profile in self.list_profiles():
            if profile.provider == provider:
                return profile
        return None

    def _builtin_profile_dirs(self) -> list[Path]:
        return [self.pack_root / "output_profiles"]

    def _custom_profile_dirs(self) -> list[Path]:
        return [self.pack_root / "user_data" / "shared" / "output_profiles"]

    @staticmethod
    def _load(path: Path) -> OutputProfile | None:
        try:
            data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        return OutputProfile.from_dict(data)
