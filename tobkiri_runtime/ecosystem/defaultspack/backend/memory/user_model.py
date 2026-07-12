from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class UserModel:
    is_hypothesis: bool = True
    estimated_work_type: str = ""
    preferred_response_style: str = ""
    typo_patterns: List[str] = field(default_factory=list)


class UserModelClassifier:
    def __init__(self, model_dir: Path) -> None:
        self._dir = Path(model_dir)
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def update_from_input(self, user_id: str, text: str) -> UserModel:
        if not self._enabled:
            return UserModel(is_hypothesis=True, estimated_work_type="")
        lowered = (text or "").lower()
        work_type = "developer" if any(token in lowered for token in ("fix", "bug", "code", "main.py")) else ""
        typo_patterns = ["typo"] if "typo" in lowered else []
        return UserModel(is_hypothesis=True, estimated_work_type=work_type, typo_patterns=typo_patterns)
