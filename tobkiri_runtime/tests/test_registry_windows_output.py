from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from backend_core.ecosystem.registry import PackInfo, Registry


def test_registry_load_logs_are_cp932_safe(tmp_path, monkeypatch):
    pack_dir = tmp_path / "pack_a"
    pack_dir.mkdir()

    def fake_load_pack(self, candidate):
        return PackInfo(
            pack_id=candidate.name,
            pack_identity=f"test:{candidate.name}",
            version="1.0.0",
            uuid="00000000-0000-0000-0000-000000000001",
            ecosystem={"pack_id": candidate.name, "dependencies": {}},
            path=candidate,
            subdir=candidate,
        )

    monkeypatch.setattr(Registry, "_load_pack", fake_load_pack)

    registry = Registry(ecosystem_dir=str(tmp_path))
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp932", errors="strict")

    with contextlib.redirect_stdout(stream):
        registry.load_all_packs()

    stream.flush()
    assert "pack_a" in registry.packs
