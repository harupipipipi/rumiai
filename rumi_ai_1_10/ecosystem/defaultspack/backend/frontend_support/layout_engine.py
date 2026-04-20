from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid


@dataclass
class PaneConfig:
    component: str
    props: Dict[str, Any] = field(default_factory=dict)
    size: Optional[float] = None


@dataclass
class LayoutConfig:
    name: str
    mode: str
    panes: List[PaneConfig] = field(default_factory=list)
    layout_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.layout_id:
            self.layout_id = uuid.uuid4().hex


class LayoutEngine:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, layout_id: str) -> Path:
        return self.root / f"{layout_id}.json"

    def save(self, layout: LayoutConfig) -> LayoutConfig:
        payload = {
            "layout_id": layout.layout_id,
            "name": layout.name,
            "mode": layout.mode,
            "panes": [
                {"component": pane.component, "props": pane.props, "size": pane.size}
                for pane in layout.panes
            ],
            "metadata": layout.metadata,
        }
        self._path(layout.layout_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return layout

    def load(self, layout_id: str) -> Optional[LayoutConfig]:
        path = self._path(layout_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return LayoutConfig(
            layout_id=str(data.get("layout_id", layout_id)),
            name=str(data.get("name", layout_id)),
            mode=str(data.get("mode", "")),
            panes=[
                PaneConfig(
                    component=str(pane.get("component", "")),
                    props=dict(pane.get("props", {})),
                    size=pane.get("size"),
                )
                for pane in data.get("panes", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )
