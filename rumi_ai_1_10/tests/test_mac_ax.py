"""Tests for macOS AX helper serialization, scoring, and actions."""

from __future__ import annotations

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import ax


class FakeAXElement:
    def __init__(self, attrs=None, actions=None):
        self.attrs = dict(attrs or {})
        self.actions = list(actions or [])
        self.performed: list[str] = []
        self.set_values: list[tuple[str, object]] = []

    def copyAttributeValue_(self, attr):
        return 0, self.attrs.get(attr)

    def actionNames(self):
        return list(self.actions)

    def performAction_(self, action):
        self.performed.append(action)
        return 0

    def setAttributeValue_value_(self, attr, value):
        self.set_values.append((attr, value))
        self.attrs[attr] = value
        return 0


def _enable_fake_ax(monkeypatch, app_element):
    ax._ELEMENT_STORE.clear()
    monkeypatch.setattr(ax.sys, "platform", "darwin")
    monkeypatch.setattr(ax, "_AX_AVAILABLE", True)
    monkeypatch.setattr(ax, "AXUIElementCreateApplication", lambda pid: app_element, raising=False)


def _fake_app_tree():
    button = FakeAXElement(
        {
            "AXRole": "AXButton",
            "AXTitle": "Save",
            "AXDescription": "Save document",
            "AXValue": None,
            "AXEnabled": True,
            "AXPosition": (20, 20),
            "AXSize": (80, 30),
        },
        actions=["AXPress"],
    )
    field = FakeAXElement(
        {
            "AXRole": "AXTextField",
            "AXTitle": "Name",
            "AXValue": "",
            "AXEnabled": True,
            "AXPosition": (20, 70),
            "AXSize": (180, 28),
        },
    )
    window = FakeAXElement(
        {
            "AXRole": "AXWindow",
            "AXTitle": "Untitled",
            "AXDescription": "Document window",
            "AXEnabled": True,
            "AXPosition": (0, 0),
            "AXSize": (400, 300),
            "AXWindowNumber": 42,
            "AXChildren": [button, field],
        },
        actions=["AXRaise"],
    )
    app = FakeAXElement(
        {
            "AXRole": "AXApplication",
            "AXTitle": "FakeApp",
            "AXWindows": [window],
            "AXFocusedUIElement": field,
        },
    )
    return app, window, button, field


def test_safe_empty_when_ax_unavailable(monkeypatch):
    monkeypatch.setattr(ax.sys, "platform", "win32")
    monkeypatch.setattr(ax, "_AX_AVAILABLE", False)

    assert ax.ax_get_tree(pid=123) == {}
    assert ax.ax_find_candidates(pid=123, intent="press Save") == []
    assert ax.ax_press("ax:123:missing") is False
    assert ax.ax_set_value(123, None, "hello") is False
    assert ax.ax_raise(42) is False


def test_tree_uses_stable_ax_ids_and_exposes_attributes(monkeypatch):
    app, _window, _button, _field = _fake_app_tree()
    _enable_fake_ax(monkeypatch, app)

    first = ax.ax_get_tree(pid=123)
    second = ax.ax_get_tree(pid=123)
    window = first["children"][0]
    button = window["children"][0]

    assert first["id"].startswith("ax:123:")
    assert button["id"] == second["children"][0]["children"][0]["id"]
    assert button["frame"] == {"x": 20.0, "y": 20.0, "width": 80.0, "height": 30.0}
    assert button["actions"] == ["AXPress"]
    assert button["value"] is None
    assert button["enabled"] is True
    assert window["window_id"] == 42


def test_find_candidates_scores_point_and_intent(monkeypatch):
    app, _window, _button, _field = _fake_app_tree()
    _enable_fake_ax(monkeypatch, app)

    candidates = ax.ax_find_candidates(pid=123, point=(25, 25), intent="press Save")

    assert candidates
    assert candidates[0]["title"] == "Save"
    assert candidates[0]["score"] > candidates[-1]["score"]


def test_press_set_value_and_raise_call_real_ax_actions(monkeypatch):
    app, window, button, field = _fake_app_tree()
    _enable_fake_ax(monkeypatch, app)
    candidates = ax.ax_find_candidates(pid=123, intent="press Save")

    assert ax.ax_press(candidates[0]["id"]) is True
    assert button.performed == ["AXPress"]

    assert ax.ax_set_value(123, None, "Ada") is True
    assert field.set_values == [("AXValue", "Ada")]

    ax.ax_get_tree(pid=123)
    assert ax.ax_raise(42) is True
    assert window.performed == ["AXRaise"]


def test_element_store_expires_cached_refs(monkeypatch):
    app, _window, button, _field = _fake_app_tree()
    _enable_fake_ax(monkeypatch, app)
    candidates = ax.ax_find_candidates(pid=123, intent="press Save")
    element_id = candidates[0]["id"]

    monkeypatch.setattr(ax.time, "monotonic", lambda: 10**12)

    assert ax.ax_press(element_id) is False
    assert button.performed == []
