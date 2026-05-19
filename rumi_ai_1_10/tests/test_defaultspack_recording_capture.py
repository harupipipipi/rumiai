from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


AVFOUNDATION_DEVICES = """
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x1] [1] BlackHole 2ch
"""


class _RunResult:
    stdout = ""

    def __init__(self, stderr: str):
        self.stderr = stderr


class _PopenResult:
    pid = 4321


def test_recording_list_devices_detects_system_audio(monkeypatch, tmp_path):
    from domain.recording.capture import RecordingCaptureService
    import domain.recording.capture as capture_module

    monkeypatch.setattr(capture_module.subprocess, "run", lambda *args, **kwargs: _RunResult(AVFOUNDATION_DEVICES))
    service = RecordingCaptureService(
        artifact_dir=tmp_path / "recordings",
        sessions_path=tmp_path / "sessions.json",
        ffmpeg_path="/usr/bin/ffmpeg",
    )

    result = service.list_devices()

    assert result["system_audio_available"] is True
    assert result["system_audio_devices"][0]["name"] == "BlackHole 2ch"


def test_recording_start_builds_avfoundation_command(monkeypatch, tmp_path):
    from domain.recording.capture import RecordingCaptureService
    import domain.recording.capture as capture_module

    calls: list[list[str]] = []
    monkeypatch.setattr(capture_module.subprocess, "run", lambda *args, **kwargs: _RunResult(AVFOUNDATION_DEVICES))

    def fake_popen(command, **kwargs):
        calls.append(command)
        return _PopenResult()

    monkeypatch.setattr(capture_module.subprocess, "Popen", fake_popen)
    service = RecordingCaptureService(
        artifact_dir=tmp_path / "recordings",
        sessions_path=tmp_path / "sessions.json",
        ffmpeg_path="/usr/bin/ffmpeg",
    )

    result = service.start({"action": "start", "screen": True, "system_audio": True, "filename": "demo"})

    assert result["status"] == "recording"
    assert calls[0][:5] == ["/usr/bin/ffmpeg", "-y", "-f", "avfoundation", "-framerate"]
    assert calls[0][calls[0].index("-i") + 1] == "0:1"
    assert result["path"].endswith("demo.mov")


def test_recording_system_audio_missing_is_not_tool_error(monkeypatch, tmp_path):
    from domain.recording.capture import RecordingCaptureService
    import domain.recording.capture as capture_module

    output = """
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
"""
    monkeypatch.setattr(capture_module.subprocess, "run", lambda *args, **kwargs: _RunResult(output))
    service = RecordingCaptureService(
        artifact_dir=tmp_path / "recordings",
        sessions_path=tmp_path / "sessions.json",
        ffmpeg_path="/usr/bin/ffmpeg",
    )

    result = service.start({"action": "start", "screen": True, "system_audio": True})

    assert result["status"] == "missing_system_audio_device"
    assert result["is_error"] is False
    assert "loopback" in result["message"].lower()
