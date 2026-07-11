import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"))

from blocks.ui.agent_notifications import _projection, run


class Registry:
    def __init__(self, running=False):
        self.running = running

    def has_active_callbacks(self, conversation_id):
        return self.running


def conversation(message):
    return {"id": "chat-1", "title": "Test", "updated_at": 20, "messages": [message]}


def test_projection_does_not_infer_waiting_from_latest_user():
    item = _projection(conversation({"role": "user", "created_at": 20, "content": "hello"}), Registry())
    assert item["status"] == "done"


def test_projection_uses_authoritative_running_and_pending_states_without_secrets():
    item = _projection(conversation({
        "role": "assistant", "created_at": 20, "content": "",
        "metadata": {"pendingAuthorityApproval": {"request_id": "secret-request", "approval_token": "secret-token"}},
    }), Registry())
    assert item["status"] == "waiting"
    assert "secret" not in repr(item)
    assert _projection(conversation({"role": "assistant", "content": ""}), Registry(True))["status"] == "running"


def test_projection_failure_only_uses_latest_message():
    item = _projection(conversation({"role": "assistant", "content": "failed", "finish_reason": "error"}), Registry())
    assert item["status"] == "failed"


def test_endpoint_returns_stable_scoped_namespace(monkeypatch, tmp_path):
    class Store:
        _storage_path = tmp_path / "chat.json"

        def list_conversations(self, **kwargs):
            return [], 0

    monkeypatch.setattr("blocks.ui.agent_notifications.ChatStore", Store)
    first = run({}, {})["data"]
    second = run({}, {})["data"]
    assert first == second
    assert len(first["storage_namespace"]) == 20
    assert str(tmp_path) not in first["storage_namespace"]
