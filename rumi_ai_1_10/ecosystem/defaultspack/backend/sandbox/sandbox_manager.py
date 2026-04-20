from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SandboxInstance:
    sandbox_id: str = ""
    image: str = "ubuntu:22.04"
    display: bool = True
    status: str = "ready"
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.sandbox_id:
            self.sandbox_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "image": self.image,
            "display": self.display,
            "status": self.status,
            "created_at": self.created_at,
        }


class SandboxManager:
    def __init__(self) -> None:
        self._instances: Dict[str, SandboxInstance] = {}
        self._model_mode: str = "fast"

    def create(self, image: str = "ubuntu:22.04", display: bool = True) -> Dict[str, Any]:
        inst = SandboxInstance(image=image, display=display)
        self._instances[inst.sandbox_id] = inst
        return {"created": True, "sandbox_id": inst.sandbox_id}

    def destroy(self, sandbox_id: str) -> Dict[str, Any]:
        inst = self._instances.pop(sandbox_id, None)
        if inst is None:
            return {"error": f"Sandbox not found: {sandbox_id}", "status_code": 404}
        inst.status = "destroyed"
        return {"destroyed": True, "sandbox_id": sandbox_id}

    def screenshot(self, sandbox_id: str) -> Dict[str, Any]:
        if sandbox_id not in self._instances:
            return {"error": f"Sandbox not found: {sandbox_id}", "status_code": 404}
        return {"sandbox_id": sandbox_id, "screenshot": "base64_placeholder", "format": "png"}

    def click(self, sandbox_id: str, x: int, y: int) -> Dict[str, Any]:
        if sandbox_id not in self._instances:
            return {"error": f"Sandbox not found: {sandbox_id}", "status_code": 404}
        return {"clicked": True, "x": x, "y": y}

    def type_text(self, sandbox_id: str, text: str) -> Dict[str, Any]:
        if sandbox_id not in self._instances:
            return {"error": f"Sandbox not found: {sandbox_id}", "status_code": 404}
        return {"typed": True, "text": text}

    def scroll(self, sandbox_id: str, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        if sandbox_id not in self._instances:
            return {"error": f"Sandbox not found: {sandbox_id}", "status_code": 404}
        return {"scrolled": True, "direction": direction, "amount": amount}

    def set_model_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in {"fast", "heavy"}:
            return {"error": f"Invalid mode: {mode}", "status_code": 400}
        self._model_mode = mode
        return {"mode": mode}

    def list_instances(self) -> List[Dict[str, Any]]:
        return [instance.to_dict() for instance in self._instances.values()]
