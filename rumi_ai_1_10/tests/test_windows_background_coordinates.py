"""Windows background-coordinate helpers with mocked user32."""

from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_postmessage import (
    WindowsPostMessageDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.windows import messages
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.windows.coords import unpack_lparam


def _value(value) -> int:
    return int(getattr(value, "value", value))


class _FakeUser32:
    def __init__(self, *, offset_x: int = 100, offset_y: int = 50) -> None:
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.screen_to_client_hwnds: list[int] = []
        self.posts: list[tuple[int, int, int, int]] = []

    def ScreenToClient(self, hwnd, point_ref) -> int:
        self.screen_to_client_hwnds.append(_value(hwnd))
        point = point_ref._obj
        point.x = int(point.x) - self.offset_x
        point.y = int(point.y) - self.offset_y
        return 1

    def PostMessageW(self, hwnd, message, wparam, lparam) -> int:
        self.posts.append((_value(hwnd), _value(message), _value(wparam), _value(lparam)))
        return 1


def test_screen_to_client_uses_mocked_user32(monkeypatch):
    fake_user32 = _FakeUser32(offset_x=12, offset_y=7)
    monkeypatch.setattr(messages, "_user32", fake_user32)

    assert messages.screen_to_client(9001, 112, 57) == (100, 50)
    assert fake_user32.screen_to_client_hwnds == [9001]


def test_screen_to_client_noops_without_user32(monkeypatch):
    monkeypatch.setattr(messages, "_user32", None)

    assert messages.screen_to_client(9001, 112, 57) == (112, 57)
    client_x, client_y, metadata = messages.resolve_client_point(
        9001,
        112,
        57,
        coordinate_space="screen",
    )
    assert (client_x, client_y) == (112, 57)
    assert metadata == {
        "input_space": "screen",
        "screen": {"x": 112, "y": 57},
        "client": {"x": 112, "y": 57},
    }


def test_post_click_converts_screen_coordinates_before_postmessage(monkeypatch):
    fake_user32 = _FakeUser32(offset_x=100, offset_y=50)
    monkeypatch.setattr(messages, "_user32", fake_user32)
    monkeypatch.setattr(messages, "can_post_to_hwnd", lambda hwnd: True)

    ok = messages.post_click(9001, 150, 90, coordinate_space="screen")

    assert ok is True
    assert [post[1] for post in fake_user32.posts] == [
        messages.WM_LBUTTONDOWN,
        messages.WM_LBUTTONUP,
    ]
    assert [unpack_lparam(post[3]) for post in fake_user32.posts] == [(50, 40), (50, 40)]


def test_post_click_converts_explicit_screen_coordinates(monkeypatch):
    fake_user32 = _FakeUser32(offset_x=100, offset_y=50)
    monkeypatch.setattr(messages, "_user32", fake_user32)
    monkeypatch.setattr(messages, "can_post_to_hwnd", lambda hwnd: True)

    ok = messages.post_click(9001, 0, 0, screen_x=150, screen_y=90)

    assert ok is True
    assert [unpack_lparam(post[3]) for post in fake_user32.posts] == [(50, 40), (50, 40)]


def test_windows_postmessage_driver_reports_screen_and_client_coordinates(monkeypatch):
    fake_user32 = _FakeUser32(offset_x=100, offset_y=50)
    monkeypatch.setattr(messages, "_user32", fake_user32)
    monkeypatch.setattr(messages, "can_post_to_hwnd", lambda hwnd: True)
    monkeypatch.setattr(
        WindowsPostMessageDriver,
        "_resolve",
        staticmethod(lambda target: 9001),
    )

    target = ComputerTarget(hwnd=9001, coordinate_space="screen")
    result = WindowsPostMessageDriver().click(target, x=150, y=90)

    assert result.executed is True
    assert result.data["hwnd"] == 9001
    assert result.data["input_space"] == "screen"
    assert result.data["screen"] == {"x": 150, "y": 90}
    assert result.data["client"] == {"x": 50, "y": 40}
    assert [unpack_lparam(post[3]) for post in fake_user32.posts] == [(50, 40), (50, 40)]
