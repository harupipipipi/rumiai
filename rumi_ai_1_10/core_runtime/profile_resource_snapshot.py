from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from .paths import discover_pack_locations
from .profile_workspace import ProfileWorkspaceManager


class ProfileResourceSnapshotManager:
    def __init__(
        self,
        user_data_root: Path | None = None,
        *,
        ecosystem_dir: str | None = None,
    ) -> None:
        self.workspace_manager = ProfileWorkspaceManager(user_data_root)
        self.ecosystem_dir = ecosystem_dir

    def snapshot_default_resources(
        self,
        profile_id: str,
        *,
        base_pack: str,
        graph_id: str | None = None,
        flow_ids: list[str] | None = None,
        prompt_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        paths = self.workspace_manager.paths_for_profile(profile_id)
        pack_path = self._pack_path(base_pack)
        snapshot_root = paths.snapshots_dir / base_pack
        flows_root = snapshot_root / "flows"
        prompts_root = snapshot_root / "prompts"
        flows_root.mkdir(parents=True, exist_ok=True)
        prompts_root.mkdir(parents=True, exist_ok=True)

        items: list[dict[str, Any]] = []
        for flow_id in flow_ids or ["chat_turn"]:
            source = self._resolve_flow_path(pack_path, flow_id)
            if source is None:
                continue
            dest = flows_root / source.name
            self._copy_with_record(pack_path, source, snapshot_root, dest, "flow", items)

        for prompt_id in prompt_ids or []:
            source = self._resolve_prompt_path(pack_path, prompt_id)
            if source is None:
                continue
            dest = prompts_root / source.name
            self._copy_with_record(pack_path, source, snapshot_root, dest, "prompt", items)

        graph_refs = self._graph_refs(pack_path, graph_id)
        nodes_payload = {"version": 1, "graph_id": graph_id, "nodes": graph_refs["nodes"]}
        blocks_payload = {"version": 1, "graph_id": graph_id, "blocks": graph_refs["blocks"]}
        (snapshot_root / "nodes.json").write_text(
            json.dumps(nodes_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (snapshot_root / "blocks.json").write_text(
            json.dumps(blocks_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        manifest = {
            "version": 1,
            "profile_id": paths.profile_id,
            "source_pack": base_pack,
            "source_pack_path": str(pack_path),
            "source_graph_id": graph_id,
            "snapshot_at": int(time.time()),
            "items": items,
        }
        (snapshot_root / "manifest.lock.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def _pack_path(self, base_pack: str) -> Path:
        for location in discover_pack_locations(self.ecosystem_dir):
            if location.pack_id == base_pack:
                return location.pack_subdir
        root = Path(self.ecosystem_dir) if self.ecosystem_dir else Path(__file__).resolve().parent.parent / "ecosystem"
        candidate = root / base_pack
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"Pack '{base_pack}' was not found")

    def _resolve_flow_path(self, pack_path: Path, flow_id: str) -> Path | None:
        candidates = []
        raw = Path(flow_id)
        if raw.suffix in {".yaml", ".yml"}:
            candidates.append(pack_path / raw)
            candidates.append(pack_path / "flows" / raw.name)
        else:
            candidates.extend(
                [
                    pack_path / "flows" / f"{flow_id}.flow.yaml",
                    pack_path / "flows" / f"{flow_id}.yaml",
                    pack_path / "flows" / flow_id / "flow.yaml",
                ]
            )
        return next((path for path in candidates if path.is_file()), None)

    def _resolve_prompt_path(self, pack_path: Path, prompt_id: str) -> Path | None:
        raw = Path(prompt_id)
        candidates = []
        if raw.suffix:
            candidates.append(pack_path / raw)
            candidates.append(pack_path / "prompts" / raw.name)
        else:
            candidates.extend(
                [
                    pack_path / "prompts" / f"{prompt_id}.md",
                    pack_path / "prompts" / f"{prompt_id}.prompt.md",
                    pack_path / "extensions" / "prompts" / prompt_id / "manifest.json",
                ]
            )
        return next((path for path in candidates if path.is_file()), None)

    def _copy_with_record(
        self,
        pack_path: Path,
        source: Path,
        snapshot_root: Path,
        dest: Path,
        item_type: str,
        items: list[dict[str, Any]],
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        items.append(
            {
                "type": item_type,
                "source": source.relative_to(pack_path).as_posix(),
                "dest": dest.relative_to(snapshot_root).as_posix(),
                "sha256": self._sha256(source),
            }
        )

    def _graph_refs(self, pack_path: Path, graph_id: str | None) -> dict[str, Any]:
        if not graph_id:
            return {"nodes": [], "blocks": []}
        graph_name = graph_id.rsplit(".", 1)[-1]
        candidates = [
            pack_path / "graphs" / f"{graph_name}.graph.yaml",
            pack_path / "graphs" / f"{graph_name}.yaml",
            pack_path / "graphs" / f"{graph_id}.graph.yaml",
        ]
        graph_path = next((path for path in candidates if path.is_file()), None)
        if graph_path is None:
            return {"nodes": [], "blocks": []}
        data = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}
        nodes = data.get("nodes") if isinstance(data, dict) else []
        node_refs = []
        block_refs = []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                ref = str(node.get("ref") or node.get("node_id") or node.get("id") or "")
                if ref:
                    node_refs.append(ref)
                block = node.get("block") or node.get("handler") or node.get("function")
                if block:
                    block_refs.append(str(block))
        return {"nodes": sorted(set(node_refs)), "blocks": sorted(set(block_refs))}

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
