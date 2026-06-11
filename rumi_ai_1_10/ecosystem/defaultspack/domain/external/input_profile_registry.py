from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .component_profiles import profile_specs_from_components
from .input_profile import InputProfile


class InputProfileRegistry:
    def __init__(self, pack_root: Path | None = None) -> None:
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]

    def list_profiles(self) -> list[InputProfile]:
        profiles: list[InputProfile] = []
        for directory in self._builtin_profile_dirs():
            for path in sorted(directory.glob("*.profile.yaml")):
                profile = self._load(path)
                if profile is not None:
                    profiles.append(profile)
        builtin_ids = {profile.id for profile in profiles}
        for spec in profile_specs_from_components(self.pack_root, "input_profiles"):
            profile = InputProfile.from_dict(spec)
            if profile.id not in builtin_ids:
                profiles.append(profile)
        for directory in self._custom_profile_dirs():
            for path in sorted(directory.glob("*.profile.yaml")):
                profile = self._load(path)
                if profile is not None:
                    profiles.append(profile)
        deduped: dict[str, InputProfile] = {}
        for profile in profiles:
            deduped[profile.id] = profile
        return list(deduped.values())

    def get(self, profile_id: str) -> InputProfile | None:
        for profile in self.list_profiles():
            if profile.id == profile_id:
                return profile
        return None

    def default_for_provider(self, provider: str) -> InputProfile | None:
        preferred_ids = [f"{provider}.default", f"{provider}.webhook.default", "generic.webhook.default"]
        for profile_id in preferred_ids:
            profile = self.get(profile_id)
            if profile is not None and (profile.provider == provider or profile_id == "generic.webhook.default"):
                return profile
        for profile in self.list_profiles():
            if profile.provider == provider:
                return profile
        return None

    def _builtin_profile_dirs(self) -> list[Path]:
        return [self.pack_root / "input_profiles"]

    def _custom_profile_dirs(self) -> list[Path]:
        return [self.pack_root / "user_data" / "shared" / "input_profiles"]

    @staticmethod
    def _load(path: Path) -> InputProfile | None:
        try:
            data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        return InputProfile.from_dict(data)
