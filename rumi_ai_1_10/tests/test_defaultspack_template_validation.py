from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import TemplatePieceKind, has_errors, parse_template  # noqa: E402


def test_parse_template_accepts_allowed_piece_kinds():
    raw = {
        "id": "sample.template",
        "kind": "pack",
        "version": "1.0.0",
        "status": "active",
        "pieces": [{"id": "fn", "kind": "function", "entrypoint": "handlers.fn"}],
    }

    result = parse_template(raw)

    assert result.ok
    assert result.template is not None
    assert result.template.pieces[0].kind == TemplatePieceKind.FUNCTION


def test_parse_template_accepts_composer_shell_and_context_piece_kinds():
    raw = {
        "id": "composer.template",
        "kind": "frontend",
        "version": "1.0.0",
        "status": "active",
        "pieces": [
            {
                "id": "context_txt_command",
                "kind": "composer_command",
                "command": {
                    "id": "context_txt",
                    "name": "context_txt",
                    "execution": {
                        "type": "pack_block",
                        "qualified_name": "defaultspack:chat.materialize_context",
                    },
                },
            },
            {
                "id": "composer_input",
                "kind": "composer_input",
                "region_id": "composer",
                "renderer": "composer",
            },
            {
                "id": "composer_region",
                "kind": "shell_region",
                "region": {"id": "composer", "renderer": "composer"},
            },
            {
                "id": "composer_renderer",
                "kind": "shell_renderer",
                "renderer": {"id": "composer", "component": "Composer", "regions": ["composer"]},
            },
            {
                "id": "materialize_txt_policy",
                "kind": "context_policy",
                "mode": "materialize_txt",
            },
        ],
    }

    result = parse_template(raw)

    assert result.ok
    assert result.template is not None
    assert {piece.kind for piece in result.template.pieces} >= {
        TemplatePieceKind.COMPOSER_COMMAND,
        TemplatePieceKind.COMPOSER_INPUT,
        TemplatePieceKind.SHELL_REGION,
        TemplatePieceKind.SHELL_RENDERER,
        TemplatePieceKind.CONTEXT_POLICY,
    }


def test_parse_template_accepts_ai_input_and_tool_policy_piece_kinds():
    raw = {
        "id": "ai.input.template",
        "kind": "frontend",
        "version": "1.0.0",
        "status": "active",
        "pieces": [
            {
                "id": "composer_input",
                "kind": "composer_input",
                "input": {
                    "id": "default_composer",
                    "region_id": "composer",
                    "renderer": "composer",
                },
            },
            {
                "id": "context_policy",
                "kind": "context_policy",
                "policy": {"id": "materialize_txt", "mode": "materialize_txt"},
            },
            {
                "id": "tool_policy",
                "kind": "tool_policy",
                "policy": {
                    "id": "chat_tools",
                    "toggleable": True,
                    "default_enabled_tools": ["web_search"],
                    "default_disabled_tools": ["terminal_exec"],
                    "tool_choice": {"type": "function", "function": {"name": "write_file"}},
                    "parallel_tool_calls": False,
                    "params": {"max_tool_count": 1},
                },
            },
            {
                "id": "ai_input",
                "kind": "ai_input",
                "input": {
                    "id": "default_ai_input",
                    "composer_input": "default_composer",
                    "context_policy": "materialize_txt",
                    "tool_policy": "chat_tools",
                    "params": {"thinking_level": "low"},
                },
            },
        ],
    }

    result = parse_template(raw)

    assert result.ok
    assert result.template is not None
    assert {piece.kind for piece in result.template.pieces} >= {
        TemplatePieceKind.AI_INPUT,
        TemplatePieceKind.TOOL_POLICY,
    }


def test_parse_template_reports_required_and_enum_errors():
    result = parse_template(
        {
            "id": "bad.template",
            "kind": "unknown_kind",
            "version": "",
            "status": "active",
            "pieces": [{"id": "piece", "kind": "not_allowed"}],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert has_errors(result.diagnostics)
    assert "template.missing_required" in codes
    assert "template.invalid_kind" in codes
    assert "template.piece.invalid_kind" in codes


def test_parse_template_rejects_noncanonical_template_id():
    result = parse_template(
        {
            "id": " bad.template ",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [{"id": "piece", "kind": "function"}],
        }
    )

    assert result.template is not None
    assert result.template.id == "bad.template"
    assert any(diagnostic.code == "template.invalid_id" for diagnostic in result.diagnostics)
    assert not result.ok


def test_duplicate_piece_ids_are_diagnostic_warnings():
    result = parse_template(
        {
            "id": "dup.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {"id": "same", "kind": "function"},
                {"id": "same", "kind": "api_route"},
            ],
        }
    )

    duplicate = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code == "template.piece.duplicate_id"
    ]
    assert duplicate
    assert duplicate[0].severity == "warning"
    assert result.ok


def test_reference_validation_reports_missing_renderers_permissions_and_route_metadata():
    result = parse_template(
        {
            "id": "bad.refs",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "capabilities": {"permissions": ["missing.permission"]},
            "pieces": [
                {"id": "field", "kind": "settings_field", "type": "unknown_field_type"},
                {"id": "renderer", "kind": "field_renderer", "field_types": []},
                {
                    "id": "route_contract",
                    "kind": "test_contract",
                    "route_metadata": {"method": "GET"},
                },
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.settings_field_renderer_missing" in codes
    assert "template.reference.field_renderer_missing_field_types" in codes
    assert "template.reference.permission_missing_piece" in codes
    assert "template.reference.route_metadata_missing_method_path" in codes
    assert not result.ok


def test_reference_validation_reports_external_io_template_shape_errors():
    result = parse_template(
        {
            "id": "bad.external.io",
            "kind": "integration",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "bad_external",
                    "kind": "external_io_template",
                    "template": {
                        "id": "",
                        "direction": "sideways",
                        "provider": "",
                    },
                }
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.external_io_template_missing_id" in codes
    assert "template.reference.external_io_template_invalid_direction" in codes
    assert "template.reference.external_io_template_missing_provider" in codes
    assert not result.ok


def test_reference_validation_reports_composer_shell_and_context_errors():
    result = parse_template(
        {
            "id": "bad.surface.refs",
            "kind": "frontend",
            "version": "1.0.0",
            "status": "active",
            "trust_level": "user",
            "pieces": [
                {"id": "bad_command", "kind": "composer_command"},
                {
                    "id": "bad_pack_block",
                    "kind": "composer_command",
                    "execution": {"type": "pack_block"},
                },
                {"id": "bad_input", "kind": "composer_input"},
                {
                    "id": "bad_renderer",
                    "kind": "shell_renderer",
                    "renderer": {
                        "id": "remote_renderer",
                        "component": "Remote",
                        "regions": ["composer"],
                        "module": "https://example.com/remote.js",
                    },
                },
                {
                    "id": "bad_region",
                    "kind": "shell_region",
                    "region": {"id": "bad_region", "renderer": "missing_renderer"},
                },
                {"id": "bad_policy", "kind": "context_policy"},
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.command_missing_execution" in codes
    assert "template.reference.command_execution_missing_qualified_name" in codes
    assert "template.reference.composer_input_missing_reference" in codes
    assert "template.reference.shell_renderer_module_requires_builtin" in codes
    assert "template.reference.shell_renderer_untrusted_module" in codes
    assert "template.reference.shell_renderer_missing_local_trust" in codes
    assert "template.reference.shell_region_unknown_renderer" in codes
    assert "template.reference.context_policy_missing_mode" in codes
    assert not result.ok


def test_reference_validation_reports_ai_input_and_tool_policy_errors():
    result = parse_template(
        {
            "id": "bad.ai.input.refs",
            "kind": "frontend",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "bad_tool_policy",
                    "kind": "tool_policy",
                    "policy": {
                        "id": "bad_tools",
                        "toggleable": "yes",
                        "default_enabled_tools": ["web_search", 3],
                        "default_disabled_tools": "terminal_exec",
                        "tool_choice": "manual",
                        "parallel_tool_calls": "true",
                        "params": [],
                        "handler_ref": "domain.bad:run",
                    },
                },
                {
                    "id": "empty_tool_policy",
                    "kind": "tool_policy",
                    "policy": {"id": "empty_tools"},
                },
                {
                    "id": "bad_ai_input",
                    "kind": "ai_input",
                    "input": {
                        "id": "bad_ai_input",
                        "composer_input": "missing_composer",
                        "context_policy": "missing_context",
                        "tool_policy": "missing_tools",
                        "params": [],
                        "entrypoint": "domain.bad:start",
                    },
                },
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.tool_policy_invalid_boolean" in codes
    assert "template.reference.tool_policy_invalid_string_list" in codes
    assert "template.reference.tool_policy_invalid_tool_choice" in codes
    assert "template.reference.tool_policy_invalid_params" in codes
    assert "template.reference.tool_policy_executable_ref" in codes
    assert "template.reference.tool_policy_empty" in codes
    assert "template.reference.ai_input_invalid_params" in codes
    assert "template.reference.ai_input_unknown_composer_input" in codes
    assert "template.reference.ai_input_unknown_context_policy" in codes
    assert "template.reference.ai_input_unknown_tool_policy" in codes
    assert "template.reference.ai_input_executable_ref" in codes
    assert not result.ok


def test_reference_validation_reports_duplicate_action_and_data_source_ids():
    result = parse_template(
        {
            "id": "dup.refs",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "first_action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
                {
                    "id": "second_action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
                {
                    "id": "first_source",
                    "kind": "function",
                    "role": "data_source",
                    "data_source": "same_source",
                },
                {
                    "id": "second_source",
                    "kind": "function",
                    "role": "data_source",
                    "data_source": "same_source",
                },
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.duplicate_action_id" in codes
    assert "template.reference.duplicate_data_source_id" in codes
    assert not result.ok


def test_non_builtin_handler_refs_are_metadata_only_by_default():
    result = parse_template(
        {
            "id": "user.handler",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "trust_level": "user",
            "pieces": [
                {
                    "id": "action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "user_action",
                    "handler_ref": "domain.somewhere:run",
                }
            ],
        }
    )

    diagnostic = next(
        item
        for item in result.diagnostics
        if item.code == "template.reference.non_builtin_handler_not_executable"
    )
    assert diagnostic.severity == "warning"
    assert result.ok
