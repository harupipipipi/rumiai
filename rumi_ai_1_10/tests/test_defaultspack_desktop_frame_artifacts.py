from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeManager:
    def validate_desktop_access(self, seat_id, access_key, owner_id=None):
        return {"ok": True, "seat_id": seat_id, "owner_id": owner_id}

    def screenshot(self, seat_id):
        assert seat_id == "seat-1"
        return {
            "ok": True,
            "data": b"\x89PNG\r\n\x1a\nframe",
            "content_type": "image/png",
            "width": 640,
            "height": 480,
            "source": "test",
        }


def test_desktop_frame_persists_artifact_for_visual_qa(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.frame_cache import FrameCache
    from ecosystem.defaultspack.blocks.sandbox import api

    class Service:
        manager = _FakeManager()
        frame_cache = FrameCache(min_capture_interval_seconds=0, time_fn=lambda: 1_750_000_000)

    monkeypatch.setattr(api, "_defaultspack_root", lambda: tmp_path)

    result = api._desktop_frame(
        Service(),
        {"seat_id": "seat-1"},
        {"owner_pack": "defaultspack"},
    )

    assert result["_binary"] is True
    assert result["artifact_paths"]
    artifact = result["artifacts"][0]
    artifact_path = tmp_path / "user_data" / "artifacts" / artifact["path"]
    assert artifact["mime_type"] == "image/png"
    assert artifact["path"].startswith("desktop_frames/seat-1/")
    assert artifact_path.read_bytes() == b"\x89PNG\r\n\x1a\nframe"
    assert result["headers"]["X-Rumi-Artifact-Path"] == artifact["path"]


def test_desktop_frame_tool_preserves_artifact_paths(monkeypatch):
    from domain.tool import desktop_tools

    class FakeApi:
        @staticmethod
        def run(payload, context):
            assert payload["_handler"] == "desktop_frame"
            assert context["principal_id"] == "local-user"
            return {
                "_binary": True,
                "content_type": "image/png",
                "body": b"frame",
                "headers": {
                    "X-Rumi-Frame-Seq": "7",
                    "X-Rumi-Frame-Width": "320",
                    "X-Rumi-Frame-Height": "200",
                    "X-Rumi-Captured-At": "1750000000.0",
                },
                "artifacts": [
                    {
                        "path": "desktop_frames/seat-1/frame.png",
                        "mime_type": "image/png",
                        "size": 5,
                    }
                ],
            }

    monkeypatch.setattr(desktop_tools, "_sandbox_api", lambda: FakeApi)

    result = desktop_tools.desktop_frame(
        {"seat_id": "seat-1"},
        {"owner_pack": "defaultspack"},
    )

    assert result["status"] == "ok"
    assert result["artifact_paths"] == ["desktop_frames/seat-1/frame.png"]
    assert result["data"]["artifact_paths"] == ["desktop_frames/seat-1/frame.png"]
    assert result["artifacts"][0]["mime_type"] == "image/png"
