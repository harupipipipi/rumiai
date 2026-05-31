from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _server():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    return object.__new__(DefaultsHttpServer)


def test_desktop_system_info_fallback_is_unreliable_without_missing_permission(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import viewer_broker_client
    from ecosystem.defaultspack.transport import http

    class FakeClient:
        def available(self):
            return False

    monkeypatch.setattr(http.sys, "platform", "darwin")
    monkeypatch.setattr(
        viewer_broker_client.ViewerBrokerClient,
        "from_environment",
        classmethod(lambda cls: FakeClient()),
    )

    response = _server()._handle_desktop_system_info({}, {})
    data = response["data"]

    assert data["source"] == "fallback"
    assert data["reliable"] is False
    assert data["permissions"] == []


def test_desktop_system_info_viewer_broker_is_authoritative_when_available(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import viewer_broker_client
    from ecosystem.defaultspack.transport import http

    class FakeClient:
        def available(self):
            return True

        def permissions(self):
            return {
                "permission_subject": "Rumi Viewer",
                "host_broker": {
                    "enabled": True,
                    "available": True,
                    "status": "running",
                },
                "permissions": [
                    {
                        "id": "screen_recording",
                        "label": "Screen Recording",
                        "status": "missing",
                        "granted": False,
                        "detail": "Allows screen capture.",
                        "settings_hint": "System Settings > Privacy & Security > Screen Recording",
                    }
                ],
            }

    monkeypatch.setattr(http.sys, "platform", "darwin")
    monkeypatch.setattr(
        viewer_broker_client.ViewerBrokerClient,
        "from_environment",
        classmethod(lambda cls: FakeClient()),
    )

    response = _server()._handle_desktop_system_info({}, {})
    data = response["data"]

    assert data["source"] == "viewer_broker"
    assert data["reliable"] is True
    assert data["permissions"][0]["status"] == "missing"


def test_desktop_system_info_viewer_broker_payload_can_be_unreliable(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import viewer_broker_client
    from ecosystem.defaultspack.transport import http

    class FakeClient:
        def available(self):
            return True

        def permissions(self):
            return {
                "host_broker": {
                    "enabled": True,
                    "available": False,
                    "status": "starting",
                },
                "permissions": [],
            }

    monkeypatch.setattr(http.sys, "platform", "darwin")
    monkeypatch.setattr(
        viewer_broker_client.ViewerBrokerClient,
        "from_environment",
        classmethod(lambda cls: FakeClient()),
    )

    response = _server()._handle_desktop_system_info({}, {})
    data = response["data"]

    assert data["source"] == "viewer_broker"
    assert data["reliable"] is False
