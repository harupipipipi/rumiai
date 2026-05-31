from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_eval_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "eval_rumi_human_tasks.py"
    spec = importlib.util.spec_from_file_location("eval_rumi_human_tasks", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


eval_rumi = _load_eval_module()


def test_extract_response_text_handles_nested_success_envelope() -> None:
    envelope = {
        "success": True,
        "data": {
            "status": "ok",
            "data": {
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            },
        },
    }

    assert eval_rumi._extract_response_text(envelope) == "first second"
    assert eval_rumi._is_ok_chat_response(envelope) is True


def test_extract_response_text_handles_conversation_messages() -> None:
    envelope = {
        "status": "ok",
        "data": {
            "messages": [
                {"role": "user", "raw_text": "question"},
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "answer"}],
                },
            ],
        },
    }

    assert eval_rumi._extract_response_text(envelope) == "answer"
    assert eval_rumi._is_ok_chat_response(envelope) is True


def test_validate_response_text_checks_length_required_and_forbidden_text() -> None:
    ok, error = eval_rumi._validate_response_text(
        {
            "min_chars": 10,
            "must_include": ["決定事項"],
            "must_not_include": ["http://", "https://"],
        },
        "決定事項: 今日は社内メモだけで整理します。",
    )
    assert ok is True
    assert error == ""

    ok, error = eval_rumi._validate_response_text(
        {"min_chars": 10},
        "短い",
    )
    assert ok is False
    assert "min_chars" in error

    ok, error = eval_rumi._validate_response_text(
        {"min_chars": 1, "must_include": ["TODO"]},
        "決定事項だけです",
    )
    assert ok is False
    assert "missing required text" in error

    ok, error = eval_rumi._validate_response_text(
        {"min_chars": 1, "must_not_include": ["https://"]},
        "参考: https://example.com",
    )
    assert ok is False
    assert "forbidden text" in error


def test_run_task_fetches_conversation_when_post_response_has_no_text(monkeypatch) -> None:
    def fake_send_task_once(*args):
        return "conversation-1", 200, {"status": "ok", "data": {"id": "conversation-1"}}

    def fake_get_conversation(*args):
        return (
            200,
            {
                "status": "ok",
                "data": {
                    "messages": [
                        {"role": "user", "raw_text": "question"},
                        {"role": "assistant", "raw_text": "決定事項 TODO 確認待ち"},
                    ],
                },
            },
        )

    monkeypatch.setattr(eval_rumi, "_send_task_once", fake_send_task_once)
    monkeypatch.setattr(eval_rumi, "_get_conversation", fake_get_conversation)

    result = eval_rumi.run_task(
        "http://127.0.0.1:8765",
        "token",
        "google/gemma-4-31b-it",
        1,
        {
            "id": "task_a",
            "prompt": "prompt",
            "min_chars": 5,
            "must_include": ["TODO"],
        },
        0,
    )

    assert result.ok is True
    assert result.response_chars == len("決定事項 TODO 確認待ち")


def test_run_task_keeps_preview_for_quality_error(monkeypatch) -> None:
    def fake_send_task_once(*args):
        return "conversation-1", 200, {"status": "ok", "data": {"id": "conversation-1"}}

    def fake_get_conversation(*args):
        return (
            200,
            {
                "status": "ok",
                "data": {
                    "messages": [
                        {"role": "assistant", "raw_text": "短い回答"},
                    ],
                },
            },
        )

    monkeypatch.setattr(eval_rumi, "_send_task_once", fake_send_task_once)
    monkeypatch.setattr(eval_rumi, "_get_conversation", fake_get_conversation)

    result = eval_rumi.run_task(
        "http://127.0.0.1:8765",
        "token",
        "google/gemma-4-31b-it",
        1,
        {"id": "task_a", "prompt": "prompt", "min_chars": 20},
        0,
    )

    assert result.ok is False
    assert result.classification == "quality_error"
    assert result.response_preview == "短い回答"
    assert result.response_chars == len("短い回答")


def test_load_tasks_preserves_content_expectations(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "task_a",
                    "prompt": "整理して",
                    "min_chars": 42,
                    "must_include": "TODO",
                    "must_not_include": ["https://"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = eval_rumi._load_tasks(path, default_min_chars=20)

    assert tasks == [
        {
            "id": "task_a",
            "prompt": "整理して",
            "min_chars": 42,
            "must_include": ["TODO"],
            "must_not_include": ["https://"],
        }
    ]
