import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ecosystem", "defaultspack"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_compact_tool_filter_entries_keeps_ui_fields_without_actual_snapshot():
    from domain.chat.public_metadata import compact_tool_filter_entries

    compact = compact_tool_filter_entries(
        [
            {
                "tool_name": "vision_tool",
                "status": "blocked",
                "reason_code": "model_unsupported",
                "reason": "selected model does not support this tool",
                "required": {
                    "model_capabilities": ["model.image_input"],
                    "runtime_capabilities": [],
                },
                "actual": {
                    "model_capabilities": ["model.text"],
                    "tags": ["model.text", "runtime.workspace"],
                },
                "repair_suggestions": ["Switch models.", "Disable this tool.", "Extra verbose item."],
            }
        ]
    )

    assert compact == [
        {
            "tool_name": "vision_tool",
            "status": "blocked",
            "reason_code": "model_unsupported",
            "reason": "selected model does not support this tool",
            "required": {"model_capabilities": ["model.image_input"]},
            "repair_suggestions": ["Switch models.", "Disable this tool."],
        }
    ]


def test_compact_provider_planning_removes_full_tool_schemas_and_context_duplicates():
    from domain.chat.public_metadata import compact_provider_planning

    compact = compact_provider_planning(
        {
            "model": "google/gemma-4-31b-it",
            "provider_tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "artifact_export",
                        "description": "Export artifacts.",
                        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                    },
                }
            ],
            "metadata": {
                "provider_tool_definitions": [{"id": "artifact_export", "schema": {"large": True}}],
                "tool_name_mapping": {"to_provider": {"artifact_export": "artifact_export"}},
                "context": {
                    "conversation_id": "c1",
                    "request_id": "r1",
                    "tool_filter_result": [{"tool_name": "artifact_export", "actual": {"tags": ["x"]}}],
                },
            },
        }
    )

    assert compact["provider_tool_count"] == 1
    assert compact["provider_tools"] == [
        {"name": "artifact_export", "type": "function", "description": "Export artifacts."}
    ]
    assert "parameters" not in str(compact)
    assert compact["metadata"]["provider_tool_definition_count"] == 1
    assert compact["metadata"]["tool_name_mapping_count"] == 1
    assert compact["metadata"]["context"]["tool_filter_count"] == 1
    assert "tool_filter_result" not in str(compact["metadata"]["context"])


def test_compact_conversation_for_response_does_not_mutate_original():
    from domain.chat.public_metadata import compact_conversation_for_response

    conversation = {
        "id": "c1",
        "messages": [
            {
                "id": "m1",
                "metadata": {
                    "tool_filter_result": [
                        {
                            "tool_name": "tool",
                            "status": "allowed",
                            "actual": {"tags": ["many"]},
                        }
                    ]
                },
            }
        ],
    }

    compact = compact_conversation_for_response(conversation)

    assert "actual" in conversation["messages"][0]["metadata"]["tool_filter_result"][0]
    assert "actual" not in compact["messages"][0]["metadata"]["tool_filter_result"][0]
