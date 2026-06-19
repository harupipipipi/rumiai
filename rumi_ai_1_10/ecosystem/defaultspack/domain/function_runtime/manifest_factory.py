from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import ENVELOPE_SCHEMA, OBJECT_SCHEMA
from .security import HIGH_RISK_CALLER_REQUIREMENT


@dataclass(frozen=True)
class FunctionSpec:
    function_id: str
    description: str
    tags: tuple[str, ...]
    risk: str = "low"
    block_module: str | None = None
    handler_ref: str | None = None
    default_args: dict[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    caller_requires: tuple[str, ...] = ()
    input_schema: dict[str, Any] | None = None
    permission_id: str | None = None


def _alias_pair(namespace: str, operation: str) -> tuple[str, str]:
    return (f"defaults.{namespace}.{operation}", f"defaultspack.{namespace}.{operation}")


def _default_aliases(function_id: str) -> tuple[str, ...]:
    parts = function_id.split("_", 1)
    if len(parts) == 1:
        return (f"defaultspack.{function_id}",)
    namespace, operation = parts
    aliases = list(_alias_pair(namespace, operation))
    op_parts = operation.split("_")
    if len(op_parts) > 1:
        dotted = ".".join(op_parts)
        aliases.extend(_alias_pair(namespace, dotted))
    return tuple(dict.fromkeys(aliases))


def _requires(function_id: str, risk: str) -> tuple[str, ...]:
    if risk == "low":
        return ()
    namespace, _, operation = function_id.partition("_")
    permission = f"{namespace}.{operation.replace('_', '.')}" if operation else namespace
    return (permission,)


def _caller_requires(risk: str) -> tuple[str, ...]:
    return (HIGH_RISK_CALLER_REQUIREMENT,) if risk == "high" else ()


def _spec(
    function_id: str,
    description: str,
    tags: tuple[str, ...],
    *,
    risk: str = "low",
    block: str | None = None,
    default_args: dict[str, Any] | None = None,
    aliases: tuple[str, ...] = (),
    requires: tuple[str, ...] | None = None,
    caller_requires: tuple[str, ...] | None = None,
    input_schema: dict[str, Any] | None = None,
) -> FunctionSpec:
    all_aliases = tuple(dict.fromkeys([*_default_aliases(function_id), *aliases]))
    return FunctionSpec(
        function_id=function_id,
        description=description,
        tags=tags,
        risk=risk,
        block_module=block,
        default_args=dict(default_args or {}),
        aliases=all_aliases,
        requires=_requires(function_id, risk) if requires is None else requires,
        caller_requires=_caller_requires(risk) if caller_requires is None else caller_requires,
        input_schema=input_schema,
    )


def manifest_for(spec: FunctionSpec) -> dict[str, Any]:
    defaultspack_extension = {
        "block_module": spec.block_module,
        "default_args": spec.default_args,
    }
    if spec.handler_ref:
        defaultspack_extension["handler_ref"] = spec.handler_ref
    manifest = {
        "function_id": spec.function_id,
        "description": spec.description,
        "tags": list(spec.tags),
        "risk": spec.risk,
        "requires": list(spec.requires),
        "caller_requires": list(spec.caller_requires),
        "host_execution": False,
        "calling_convention": "subprocess",
        "entrypoint": "main.py:run",
        "vocab_aliases": list(spec.aliases),
        "input_schema": dict(spec.input_schema or OBJECT_SCHEMA),
        "output_schema": dict(ENVELOPE_SCHEMA),
        "extensions": {
            "defaultspack": defaultspack_extension
        },
    }
    if spec.permission_id:
        manifest["permission_id"] = spec.permission_id
    return manifest


AI_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec("ai_catalog", "List AI catalog entries.", ("ai", "catalog"), block="blocks.ai.catalog"),
    _spec("ai_complete", "Complete a chat request using the configured AI provider.", ("ai", "model", "completion"), risk="medium", block="blocks.ai.complete"),
    _spec("ai_stream", "Start an AI streaming completion.", ("ai", "model", "stream"), risk="medium", block="blocks.ai.stream"),
    _spec("ai_models", "List available AI models.", ("ai", "model", "catalog"), block="blocks.ai.models"),
    _spec("ai_search_models", "Search available AI models by capabilities.", ("ai", "model", "catalog"), block="blocks.ai.search_models", aliases=("defaults.ai.search_models", "defaultspack.ai.search_models")),
    _spec("ai_get_model_capabilities", "Get AI model capability metadata.", ("ai", "model", "catalog"), block="blocks.ai.get_model_capabilities", aliases=("defaults.ai.get_model_capabilities", "defaultspack.ai.get_model_capabilities")),
    _spec("ai_recommend_model", "Recommend an AI model for a request.", ("ai", "model", "routing"), block="blocks.ai.recommend_model", aliases=("defaults.ai.recommend_model", "defaultspack.ai.recommend_model")),
    _spec("ai_route_model", "Route a request to a compatible model.", ("ai", "model", "routing"), risk="medium", block="blocks.ai.route_model", aliases=("defaults.ai.route_model", "defaultspack.ai.route_model")),
    _spec("ai_explain_model_choice", "Explain a model routing decision.", ("ai", "model", "routing"), block="blocks.ai.explain_model_choice", aliases=("defaults.ai.explain_model_choice", "defaultspack.ai.explain_model_choice")),
    _spec("ai_model_call", "Ask another model a bounded question without tool access by default.", ("ai", "model", "delegation"), risk="medium", aliases=("defaults.ai.model_call", "defaultspack.ai.model_call")),
    _spec("ai_providers", "List available AI providers.", ("ai", "provider", "catalog"), block="blocks.ai.providers"),
    _spec("ai_profiles", "List available AI model profiles.", ("ai", "profile", "catalog"), block="blocks.ai.profiles"),
    _spec("ai_embed", "Create embeddings with the configured AI provider.", ("ai", "embedding"), risk="medium", block="blocks.ai.embed"),
    _spec("ai_image_gen", "Generate an image with the configured AI provider.", ("ai", "image"), risk="medium", block="blocks.ai.image_gen"),
    _spec("ai_image_analyze", "Analyze an image with the configured AI provider.", ("ai", "image"), risk="medium", block="blocks.ai.image_analyze"),
    _spec("ai_transcribe", "Transcribe audio with the configured AI provider.", ("ai", "audio"), risk="medium", block="blocks.ai.transcribe"),
    _spec("ai_tts", "Generate speech with the configured AI provider.", ("ai", "audio"), risk="medium", block="blocks.ai.tts"),
    _spec("ai_get_preferred_model", "Get the preferred model profile.", ("ai", "model_runtime")),
    _spec("ai_set_preferred_model", "Set the preferred model profile.", ("ai", "model_runtime"), risk="medium"),
    _spec("ai_get_thinking_level", "Get the configured model thinking level.", ("ai", "model_runtime"), aliases=("defaults.model_runtime.get_thinking_level", "defaultspack.model_runtime.get_thinking_level")),
    _spec("ai_set_thinking_level", "Set the configured model thinking level.", ("ai", "model_runtime"), risk="medium", aliases=("defaults.model_runtime.set_thinking_level", "defaultspack.model_runtime.set_thinking_level")),
    _spec("ai_get_effective_thinking_level", "Resolve the effective thinking level.", ("ai", "model_runtime"), aliases=("defaults.model_runtime.get_effective_thinking_level", "defaultspack.model_runtime.get_effective_thinking_level")),
    _spec("ai_normalize_thinking_level", "Normalize a thinking level for a provider.", ("ai", "model_runtime"), aliases=("defaults.model_runtime.normalize_thinking_level", "defaultspack.model_runtime.normalize_thinking_level")),
    _spec("ai_validate_model_params", "Validate model runtime parameters.", ("ai", "model_runtime")),
    _spec("ai_get_provider_key_status", "Get provider API key status.", ("ai", "provider_key")),
    _spec("ai_set_provider_key", "Set a provider API key.", ("ai", "provider_key"), risk="high"),
    _spec("ai_delete_provider_key", "Delete a provider API key.", ("ai", "provider_key"), risk="high"),
    _spec("ai_routing_analyze", "Analyze a request for model routing.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.analyze"),
    _spec("ai_routing_route", "Route a request to an AI model profile.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.route"),
    _spec("ai_routing_profiles_list", "List AI routing profiles.", ("ai", "routing"), block="blocks.ai.routing.profiles", default_args={"_method": "GET"}),
    _spec("ai_routing_profiles_create", "Create an AI routing profile.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.profiles", default_args={"_method": "POST"}),
    _spec("ai_routing_profiles_update", "Update an AI routing profile.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.profiles", default_args={"_method": "PUT"}),
    _spec("ai_routing_profiles_delete", "Delete an AI routing profile.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.profiles", default_args={"_method": "DELETE"}),
    _spec("ai_routing_rules_list", "List AI routing rules.", ("ai", "routing"), block="blocks.ai.routing.rules", default_args={"_method": "GET"}),
    _spec("ai_routing_rules_create", "Create an AI routing rule.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.rules", default_args={"_method": "POST"}),
    _spec("ai_routing_rules_delete", "Delete an AI routing rule.", ("ai", "routing"), risk="medium", block="blocks.ai.routing.rules", default_args={"_method": "DELETE"}),
    _spec("ai_routing_log", "Get AI routing logs.", ("ai", "routing"), block="blocks.ai.routing.log"),
)


CHAT_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, ("chat",), risk=risk, block=block)
    for function_id, description, risk, block in (
        ("chat_create_conversation", "Create a chat conversation.", "medium", "blocks.chat.create_conversation"),
        ("chat_get_conversation", "Get a chat conversation.", "low", "blocks.chat.get_conversation"),
        ("chat_list_conversations", "List chat conversations.", "low", "blocks.chat.list_conversations"),
        ("chat_update_conversation", "Update a chat conversation.", "medium", "blocks.chat.update_conversation"),
        ("chat_delete_conversation", "Delete a chat conversation.", "high", "blocks.chat.delete_conversation"),
        ("chat_export_conversation", "Export a chat conversation.", "low", "blocks.chat.export_conversation"),
        ("chat_send", "Send a chat message.", "medium", "blocks.chat.send"),
        ("chat_stream", "Start a chat stream.", "medium", "blocks.chat.stream"),
        ("chat_add_message", "Add a chat message.", "medium", "blocks.chat.add_message"),
        ("chat_get_message", "Get a chat message.", "low", "blocks.chat.get_message"),
        ("chat_update_message", "Update a chat message.", "medium", "blocks.chat.update_message"),
        ("chat_delete_message", "Delete a chat message.", "high", "blocks.chat.delete_message"),
        ("chat_branch", "Branch a chat conversation.", "medium", "blocks.chat.branch"),
        ("chat_search", "Search chat conversations.", "low", "blocks.chat.search"),
        ("chat_stop", "Stop a chat response.", "medium", "blocks.chat.stop"),
        ("chat_regenerate", "Regenerate a chat response.", "medium", "blocks.chat.regenerate"),
        ("chat_summarize_and_trim", "Summarize and trim a chat.", "medium", "blocks.chat.summarize_and_trim"),
        ("chat_auto_trim", "Auto trim a chat.", "medium", "blocks.chat.auto_trim"),
        ("chat_browser_screenshots", "List browser screenshots for a chat run.", "low", "blocks.chat.browser_screenshots"),
    )
) + tuple(
    _spec(f"chat_channel_{name}", f"{label} a chat channel.", ("chat", "channel"), risk=risk, block=f"blocks.chat.channel.{module}")
    for name, label, risk, module in (
        ("create", "Create", "medium", "create"),
        ("list", "List", "low", "list"),
        ("get", "Get", "low", "get"),
        ("update", "Update", "medium", "update"),
        ("delete", "Delete", "high", "delete"),
        ("join", "Join", "medium", "join"),
        ("leave", "Leave", "medium", "leave"),
        ("send_message", "Send a message to", "medium", "send_message"),
        ("get_messages", "Get messages from", "low", "get_messages"),
        ("reply", "Reply in", "medium", "reply"),
    )
)


TOOL_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, ("tool",), risk=risk, block=block)
    for function_id, description, risk, block in (
        ("tool_invoke", "Invoke a registered tool.", "medium", "blocks.tool.invoke"),
        ("tool_list", "List registered tools.", "low", "blocks.tool.list"),
        ("tool_names", "List registered tool names only.", "low", "blocks.tool.names"),
        ("tool_schema", "Get a registered tool schema.", "low", "blocks.tool.schema"),
        ("tool_mcp_connect", "Connect an MCP server.", "high", "blocks.tool.mcp_connect"),
        ("tool_mcp_list", "List MCP servers.", "low", "blocks.tool.mcp_list"),
        ("tool_mcp_registry", "Manage registered MCP servers.", "medium", "blocks.tool.mcp_registry"),
        ("tool_create", "Create a dynamic tool.", "high", "blocks.tool.create"),
        ("tool_update", "Update a dynamic tool.", "high", "blocks.tool.update"),
        ("tool_delete", "Delete a dynamic tool.", "high", "blocks.tool.delete"),
        ("tool_export", "Export a dynamic tool.", "low", "blocks.tool.export"),
        ("tool_consent_check", "Check tool consent.", "low", "blocks.tool.consent_check"),
        ("tool_consent_confirm", "Confirm tool consent.", "medium", "blocks.tool.consent_confirm"),
    )
) + tuple(
    _spec(function_id, description, tags, risk=risk)
    for function_id, description, tags, risk in (
        ("tool_web_search", "Run the default web search tool.", ("tool", "research"), "medium"),
        ("tool_reddit_search", "Run the default reddit search tool.", ("tool", "research"), "medium"),
        ("tool_calculator", "Run the default calculator tool.", ("tool", "math"), "low"),
        ("tool_file_reader", "Run the default file reader tool.", ("tool", "file"), "low"),
        ("tool_todo", "Run the default todo tool.", ("tool", "planning"), "medium"),
        ("tool_task_board", "Run the default task board tool.", ("tool", "planning", "task_board"), "medium"),
        ("tool_task_board_agent_session", "Link task board cards to defaultspack coding agent sessions.", ("tool", "planning", "task_board", "agent"), "medium"),
        ("tool_subagent", "Run the default subagent tool.", ("tool", "agent"), "medium"),
        ("browser_session", "Open or inspect a browser session.", ("tool", "browser"), "high"),
        ("browser_open_url", "Open a URL in a browser session.", ("tool", "browser"), "high"),
        ("browser_screenshot", "Capture a browser screenshot.", ("tool", "browser"), "high"),
        ("computer_screenshot", "Capture a computer screenshot.", ("tool", "computer"), "high"),
        ("computer_move", "Move the computer cursor.", ("tool", "computer"), "high"),
        ("computer_click", "Click with the computer controller.", ("tool", "computer"), "high"),
        ("computer_drag", "Drag with the computer controller.", ("tool", "computer"), "high"),
        ("computer_type", "Type with the computer controller.", ("tool", "computer"), "high"),
        ("computer_key", "Send a key with the computer controller.", ("tool", "computer"), "high"),
        ("computer_scroll", "Scroll with the computer controller.", ("tool", "computer"), "high"),
    )
)
SKILL_CREATE_FROM_FEEDBACK_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "anyOf": [{"required": ["feedback"]}, {"required": ["correction"]}],
    "properties": {
        "feedback": {"type": "string", "minLength": 1},
        "correction": {"type": "string", "minLength": 1},
        "applies_to_tools": {"oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
        "tool_ids": {"oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
        "triggers": {"oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
        "keywords": {"oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
        "skill_id": {"type": "string"},
        "name": {"type": "string"},
        "display_name": {"type": "string"},
        "description": {"type": "string"},
        "conversation_id": {"type": "string"},
        "message_id": {"type": "string"},
    },
}


SKILL_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec(
        "skill_create_from_feedback",
        "Create a Rumi extension skill from corrective feedback.",
        ("skill", "feedback", "dream"),
        risk="high",
        block="blocks.skill.create_from_feedback",
        aliases=("defaults.skill.create_from_feedback", "defaultspack.skill.create_from_feedback"),
        input_schema=SKILL_CREATE_FROM_FEEDBACK_INPUT_SCHEMA,
    ),
)


CONVERSATION_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec(
        "conversation_guidance",
        "Inject high-priority guidance into a running conversation or agent task.",
        ("conversation", "guidance", "interrupt"),
        risk="medium",
        block="blocks.conversation.guidance",
        aliases=("defaults.conversation.guidance", "defaultspack.conversation.guidance"),
    ),
    _spec(
        "conversation_steer",
        "Queue, list, cancel, or process a follow-up steer after a conversation task completes.",
        ("conversation", "steer"),
        risk="medium",
        block="blocks.conversation.steer",
        aliases=("defaults.conversation.steer", "defaultspack.conversation.steer"),
    ),
    _spec(
        "conversation_handoff",
        "Create a new conversation, optionally seed it with a prompt, and return a move card.",
        ("conversation", "handoff"),
        risk="medium",
        block="blocks.conversation.handoff",
        aliases=("defaults.conversation.handoff", "defaultspack.conversation.handoff"),
    ),
)


CODING_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, ("coding",), risk=risk, block=block)
    for function_id, description, risk, block in (
        ("coding_context", "Get coding context.", "low", "blocks.coding.context"),
        ("coding_file_read", "Read a workspace file.", "low", "blocks.coding.file_read"),
        ("coding_file_write", "Write a workspace file.", "high", "blocks.coding.file_write"),
        ("coding_file_create", "Create a workspace file.", "high", "blocks.coding.file_create"),
        ("coding_file_delete", "Delete a workspace file.", "high", "blocks.coding.file_delete"),
        ("coding_file_diff", "Preview a workspace file diff.", "low", "blocks.coding.file_diff"),
        ("coding_file_patch", "Patch a workspace file with old/new text.", "high", "blocks.coding.file_patch"),
        ("coding_file_snapshot", "Create a workspace file snapshot.", "medium", "blocks.coding.file_snapshot"),
        ("coding_file_restore", "Restore a workspace checkpoint.", "high", "blocks.coding.file_restore"),
        ("coding_checkpoint_create", "Create a reversible workspace checkpoint.", "medium", "blocks.coding.file_checkpoint"),
        ("coding_checkpoint_list", "List workspace checkpoints.", "low", "blocks.coding.file_checkpoint"),
        ("coding_checkpoint_restore", "Restore a reversible workspace checkpoint.", "high", "blocks.coding.file_restore"),
        ("coding_file_search", "Search workspace files.", "low", "blocks.coding.file_search"),
        ("coding_file_list", "List workspace files.", "low", "blocks.coding.file_list"),
        ("coding_terminal_exec", "Execute a terminal command.", "high", "blocks.coding.terminal_exec"),
        ("coding_terminal_stream", "Stream a terminal command.", "high", "blocks.coding.terminal_stream"),
        ("coding_git_status", "Get git status.", "low", "blocks.coding.git_status"),
        ("coding_git_diff", "Get git diff.", "low", "blocks.coding.git_diff"),
        ("coding_git_branch_get", "Get the current git branch.", "low", "blocks.coding.git_branch",),
        ("coding_git_branch_create", "Create a git branch.", "high", "blocks.coding.git_branch"),
        ("coding_git_commit", "Create a git commit.", "high", "blocks.coding.git_commit"),
        ("coding_git_push", "Push git changes.", "high", "blocks.coding.git_push"),
        ("coding_rumi_log", "List or append local .rumi coding history.", "medium", "blocks.coding.rumi_log"),
        ("coding_approval_list", "List pending coding approvals.", "low", "blocks.coding.approval_list"),
        ("coding_approval_approve", "Approve a pending coding operation.", "medium", "blocks.coding.approval_approve"),
        ("coding_approval_deny", "Deny a pending coding operation.", "medium", "blocks.coding.approval_deny"),
        ("coding_github_pr_read", "Read GitHub pull request metadata.", "medium", "blocks.coding.github_pr_read"),
        ("coding_github_issue_read", "Read GitHub issue metadata.", "medium", "blocks.coding.github_issue_read"),
        ("coding_github_ci_status", "Read GitHub pull request CI status.", "medium", "blocks.coding.github_ci_status"),
        ("coding_agent_session_create", "Create a multi-agent coding workspace session.", "medium", "blocks.agent.coding_session_create"),
        ("coding_agent_session_status", "Get a multi-agent coding workspace session.", "low", "blocks.agent.coding_session_status"),
        ("coding_agent_session_merge_report", "Get a multi-agent coding workspace merge report.", "low", "blocks.agent.coding_session_merge_report"),
    )
)


BROWSER_ARTIFACT_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec("browser_artifacts", "List persistent browser coding artifacts.", ("tool", "browser"), block="blocks.browser.artifacts"),
)


RECORDING_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec(
        "recording_capture",
        "List devices and capture screen, microphone, or system audio recordings.",
        ("recording", "media"),
        risk="high",
        block="blocks.recording.capture",
        aliases=("defaults.recording.capture", "defaultspack.recording.capture"),
    ),
)


AGENT_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, ("agent",), risk=risk, block=block)
    for function_id, description, risk, block in (
        ("agent_execute", "Start an agent execution.", "medium", "blocks.agent.execute"),
        ("agent_plan", "Create an agent plan.", "medium", "blocks.agent.plan"),
        ("agent_approve", "Approve an agent action.", "medium", "blocks.agent.approve"),
        ("agent_reject", "Reject an agent action.", "medium", "blocks.agent.reject"),
        ("agent_cancel", "Cancel an agent execution.", "medium", "blocks.agent.cancel"),
        ("agent_status", "Get agent execution status.", "low", "blocks.agent.status"),
        ("agent_add_instruction", "Add an instruction to an agent.", "medium", "blocks.agent.add_instruction"),
        ("agent_multi_execute", "Compatibility wrapper that routes to CompanySlackRuntime.", "medium", "blocks.agent.multi_execute"),
        ("agent_multi_status", "Get compatibility CompanySlackRuntime thread status.", "low", "blocks.agent.multi_status"),
        ("agent_multi_message", "Post compatibility message to CompanySlackRuntime.", "medium", "blocks.agent.multi_message"),
        ("agent_interrupt_add", "Add an agent interrupt.", "medium", "blocks.agent.interrupt.add"),
        ("agent_interrupt_cancel", "Cancel an agent interrupt.", "medium", "blocks.agent.interrupt.cancel"),
        ("agent_pause", "Pause an agent.", "medium", "blocks.agent.interrupt.pause"),
        ("agent_resume", "Resume an agent.", "medium", "blocks.agent.interrupt.resume"),
        ("agent_redirect", "Redirect an agent.", "medium", "blocks.agent.interrupt.redirect"),
        ("agent_stepback", "Step an agent back.", "medium", "blocks.agent.interrupt.stepback"),
        ("agent_queue_get", "Get the agent queue.", "low", "blocks.agent.interrupt.queue"),
        ("agent_queue_update", "Update the agent queue.", "medium", "blocks.agent.interrupt.queue"),
        ("agent_progress", "Get agent progress.", "low", "blocks.agent.interrupt.progress"),
        ("agent_run_subagent", "Compatibility alias for utility model routing or delegated runs.", "medium", "blocks.agent.run_subagent"),
    )
) + tuple(
    _spec(f"agent_schedule_{name}", f"{label} an agent schedule.", ("agent", "scheduler"), risk=risk, block=f"blocks.agent.scheduler.{module}")
    for name, label, risk, module in (
        ("create", "Create", "medium", "create"),
        ("list", "List", "low", "list"),
        ("get", "Get", "low", "get"),
        ("update", "Update", "medium", "update"),
        ("delete", "Delete", "high", "delete"),
        ("trigger", "Trigger", "medium", "trigger"),
        ("pause", "Pause", "medium", "pause"),
        ("resume", "Resume", "medium", "resume"),
        ("history", "Get history for", "low", "history"),
    )
) + tuple(
    _spec(function_id, description, ("agent", "org"), risk=risk, block=block)
    for function_id, description, risk, block in (
        ("agent_org_list", "List agent organizations.", "low", "blocks.agent.org.list"),
        ("agent_org_create", "Create an agent organization.", "medium", "blocks.agent.org.create"),
        ("agent_org_get", "Get an agent organization.", "low", "blocks.agent.org.get"),
        ("agent_org_delete", "Delete an agent organization.", "high", "blocks.agent.org.delete"),
        ("agent_org_roles_list", "List agent organization roles.", "low", "blocks.agent.org.list_roles"),
        ("agent_org_role_define", "Define an agent organization role.", "medium", "blocks.agent.org.define_role"),
        ("agent_org_member_add", "Add an agent organization member.", "medium", "blocks.agent.org.add_member"),
        ("agent_org_member_remove", "Remove an agent organization member.", "medium", "blocks.agent.org.remove_member"),
        ("agent_org_ask", "Ask an agent organization.", "medium", "blocks.agent.org.ask"),
        ("agent_org_instruct", "Instruct an agent organization.", "medium", "blocks.agent.org.instruct"),
        ("agent_org_report", "Request an agent organization report.", "medium", "blocks.agent.org.report"),
        ("agent_org_transfer_context", "Transfer context to an agent organization.", "medium", "blocks.agent.org.transfer_context"),
    )
)


REMOTE_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec(
        "remote_task_create",
        "Create and optionally dispatch a remote task.",
        ("remote", "task"),
        risk="medium",
        block="blocks.remote.task_create",
    ),
    _spec(
        "remote_task_get",
        "Get a remote task snapshot.",
        ("remote", "task"),
        risk="low",
        block="blocks.remote.task_get",
    ),
    _spec(
        "remote_task_events",
        "List remote task timeline events.",
        ("remote", "task"),
        risk="low",
        block="blocks.remote.task_events",
    ),
    _spec(
        "remote_task_cancel",
        "Cancel a remote task and linked agent runs.",
        ("remote", "task"),
        risk="medium",
        block="blocks.remote.task_cancel",
    ),
    _spec(
        "remote_host_status",
        "Get remote host readiness and runtime status.",
        ("remote", "host"),
        risk="low",
        block="blocks.remote.host_status",
    ),
)


DATA_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, tags, risk=risk, block=block)
    for function_id, description, tags, risk, block in (
        ("prompt_render", "Render a prompt.", ("prompt",), "low", "blocks.prompt.render"),
        ("prompt_list", "List prompts.", ("prompt",), "low", "blocks.prompt.list"),
        ("prompt_create", "Create a prompt.", ("prompt",), "medium", "blocks.prompt.create"),
        ("prompt_system_get", "Get the system prompt.", ("prompt",), "low", "blocks.prompt.system"),
        ("prompt_system_set", "Set the system prompt.", ("prompt",), "medium", "blocks.prompt.system"),
        ("prompt_update", "Update a prompt.", ("prompt",), "medium", "blocks.prompt.update"),
        ("prompt_delete", "Delete a prompt.", ("prompt",), "high", "blocks.prompt.delete"),
        ("prompt_convert", "Convert a prompt.", ("prompt",), "low", "blocks.prompt.convert"),
        ("prompt_validate_template", "Validate a prompt template.", ("prompt",), "low", None),
        ("prompt_resolve_for_conversation", "Resolve prompt context for a conversation.", ("prompt",), "low", None),
        ("memory_store", "Store memory.", ("memory",), "medium", "blocks.memory.store"),
        ("memory_recall", "Recall memory.", ("memory",), "low", "blocks.memory.recall"),
        ("memory_project_context", "Get project memory context.", ("memory",), "low", "blocks.memory.project_context"),
        ("memory_vector_store", "Store memory vector data.", ("memory",), "medium", "blocks.memory.vector_store"),
        ("memory_vector_query", "Query memory vectors.", ("memory",), "low", "blocks.memory.vector_query"),
        ("memory_memo", "Dispatch memo folder or note operations.", ("memory", "memo"), "medium", "blocks.memory.memo"),
        ("memory_memo_folders", "Manage memo folders.", ("memory", "memo"), "medium", "blocks.memory.memo_folders"),
        ("memory_memo_notes", "Manage memo notes.", ("memory", "memo"), "medium", "blocks.memory.memo_notes"),
        ("memory_list", "List memories.", ("memory",), "low", None),
        ("memory_update", "Update memory.", ("memory",), "medium", None),
        ("memory_delete", "Delete memory.", ("memory",), "high", None),
        ("memory_compact", "Compact memory.", ("memory",), "medium", None),
        ("memory_attach_to_profile", "Attach memory to a profile.", ("memory",), "medium", None),
        ("memory_resolve_for_agent", "Resolve memory for an agent.", ("memory",), "low", None),
        ("knowledge_create", "Create knowledge.", ("knowledge",), "medium", "blocks.knowledge.create"),
        ("knowledge_get", "Get knowledge.", ("knowledge",), "low", "blocks.knowledge.get"),
        ("knowledge_list", "List knowledge.", ("knowledge",), "low", "blocks.knowledge.list"),
        ("knowledge_search", "Search knowledge.", ("knowledge",), "low", "blocks.knowledge.search"),
        ("knowledge_update", "Update knowledge.", ("knowledge",), "medium", "blocks.knowledge.update"),
        ("knowledge_delete", "Delete knowledge.", ("knowledge",), "high", "blocks.knowledge.delete"),
        ("knowledge_import_file", "Import knowledge from a file.", ("knowledge",), "medium", None),
        ("knowledge_import_url", "Import knowledge from a URL.", ("knowledge",), "medium", None),
        ("knowledge_index", "Index knowledge.", ("knowledge",), "medium", None),
        ("knowledge_reindex", "Reindex knowledge.", ("knowledge",), "medium", None),
        ("knowledge_attach_to_project", "Attach knowledge to a project.", ("knowledge",), "medium", None),
        ("artifact_list", "List artifacts.", ("artifact",), "low", "blocks.artifact.list"),
        ("artifact_create", "Create an artifact.", ("artifact",), "medium", "blocks.artifact.create"),
        ("artifact_get", "Get an artifact.", ("artifact",), "low", "blocks.artifact.get"),
        ("artifact_update", "Update an artifact.", ("artifact",), "medium", None),
        ("artifact_delete", "Delete an artifact.", ("artifact",), "high", None),
        ("artifact_read_file", "Read an artifact file.", ("artifact",), "low", None),
        ("artifact_write_file", "Write an artifact file.", ("artifact",), "high", None),
        ("artifact_attach_to_conversation", "Attach an artifact to a conversation.", ("artifact",), "medium", None),
        ("share_list", "List shares.", ("share",), "low", "blocks.share.list"),
        ("share_create", "Create a share.", ("share",), "medium", "blocks.share.create"),
        ("share_get", "Get a share.", ("share",), "low", "blocks.share.get"),
        ("share_revoke", "Revoke a share.", ("share",), "medium", "blocks.share.revoke"),
    )
)


PROFILE_WORKSPACE_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, tags, risk=risk, block=block)
    for function_id, description, tags, risk, block in (
        ("profile_load_active", "Load the active startup profile.", ("profile",), "low", "blocks.profile.load_active"),
        ("profile_workspace", "Resolve and initialize a profile workspace.", ("profile",), "low", "blocks.profile.workspace"),
        ("chat_detect_modalities", "Detect message input modalities.", ("chat",), "low", "blocks.chat.detect_modalities"),
        ("prompt_load_effective", "Load the effective profile-scoped system prompt.", ("prompt",), "low", "blocks.prompt.load_effective"),
        ("tools_select_relevant", "Select relevant tools for a profile-scoped chat turn.", ("tools",), "low", "blocks.tool.select_relevant"),
        ("permissions_filter_tools", "Filter selected tools through profile permission defaults.", ("permissions",), "low", "blocks.permissions.filter_tools"),
        ("ai_build_request", "Build a routed AI completion request.", ("ai",), "medium", "blocks.ai.build_request"),
        ("chat_persist_turn", "Persist a profile-scoped chat turn.", ("chat",), "medium", "blocks.chat.persist_turn"),
        ("audit_record_event", "Record a profile-scoped audit event.", ("audit",), "medium", "blocks.audit.record_event"),
    )
)


RESEARCH_MEDIA_UI_DEV_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, tags, risk=risk, block=block)
    for function_id, description, tags, risk, block in (
        ("research_local_search", "Run local research search.", ("research",), "low", "blocks.research.local_search"),
        ("research_web_search", "Run web research search.", ("research",), "medium", "blocks.research.web_search"),
        ("research_reddit_search", "Run reddit research search.", ("research",), "medium", "blocks.research.reddit_search"),
        ("research_report", "Create a research report.", ("research",), "medium", "blocks.research.report"),
        ("research_summary_site", "Create a browsable local research summary site.", ("research", "artifact"), "medium", "blocks.research.summary_site"),
        ("research_search_sources", "Search research sources.", ("research",), "low", None),
        ("research_summarize_sources", "Summarize research sources.", ("research",), "medium", None),
        ("research_build_report", "Build a research report.", ("research",), "medium", None),
        ("research_cache_result", "Cache a research result.", ("research",), "medium", None),
        ("media_image_read", "Read image metadata.", ("media",), "low", "blocks.media.image_read"),
        ("media_image_transform", "Transform an image.", ("media",), "medium", "blocks.media.image_transform"),
        ("media_doc_parse", "Parse a document.", ("media",), "low", "blocks.media.doc_parse"),
        ("media_pdf_parse", "Parse a PDF.", ("media",), "low", None),
        ("media_ocr", "Run OCR.", ("media",), "medium", None),
        ("media_clipboard_read", "Read clipboard content.", ("media",), "high", "blocks.media.clipboard_read"),
        ("media_clipboard_write", "Write clipboard content.", ("media",), "high", "blocks.media.clipboard_write"),
        ("media_screenshot", "Capture a screenshot.", ("media",), "high", "blocks.media.screenshot"),
        ("media_audio_transcribe", "Transcribe audio media.", ("media",), "medium", None),
        ("media_tts", "Generate media speech.", ("media",), "medium", None),
        ("media_image_analyze", "Analyze an image.", ("media",), "medium", None),
        ("media_image_generate", "Generate an image.", ("media",), "medium", None),
        ("vision_describe_images", "Describe attached images for non-vision models.", ("vision", "ai"), "medium", "blocks.vision.describe_images"),
        ("prompt_lint_prompt", "Lint prompt redundancy and budget risk.", ("prompt",), "low", "blocks.prompt.lint_prompt"),
        ("prompt_compact_prompt", "Suggest a safe compacted prompt.", ("prompt",), "medium", "blocks.prompt.compact_prompt"),
        ("ui_catalog", "Build the UI catalog.", ("ui",), "low", "blocks.ui.catalog"),
        ("ui_settings_get", "Get UI settings.", ("ui",), "low", "blocks.ui.settings",),
        ("ui_settings_update", "Update UI settings.", ("ui",), "medium", "blocks.ui.settings",),
        ("ui_conversation_preview", "Build a conversation UI preview.", ("ui",), "low", "blocks.ui.conversation_preview"),
        ("ui_shell_get", "Get UI shell configuration.", ("ui",), "low", None),
        ("ui_shell_update", "Update UI shell configuration.", ("ui",), "medium", None),
        ("ui_extensions_list", "List UI extensions.", ("ui",), "low", None),
        ("ui_extension_enable", "Enable a UI extension.", ("ui",), "medium", None),
        ("ui_extension_disable", "Disable a UI extension.", ("ui",), "medium", None),
        ("ui_composer_config_get", "Get composer UI config.", ("ui",), "low", None),
        ("ui_composer_config_set", "Set composer UI config.", ("ui",), "medium", None),
        ("ui_model_selector_config_get", "Get model selector config.", ("ui",), "low", None),
        ("ui_model_selector_config_set", "Set model selector config.", ("ui",), "medium", None),
        ("frontend_start", "Start the frontend.", ("frontend",), "medium", "blocks.frontend.start"),
        ("frontend_stop", "Stop the frontend.", ("frontend",), "medium", "blocks.frontend.stop"),
        ("frontend_emit", "Emit a frontend event.", ("frontend",), "medium", "blocks.frontend.emit"),
        ("dev_inspect", "Inspect defaultspack runtime state.", ("dev",), "low", "blocks.dev.inspect"),
        ("dev_prompt_history", "List prompt history.", ("dev",), "low", "blocks.dev.prompt_history"),
        ("dev_edit_prompt_live", "Edit prompt live.", ("dev",), "high", "blocks.dev.edit_prompt_live"),
        ("dev_replay", "Replay a request.", ("dev",), "medium", "blocks.dev.replay"),
        ("dev_list_logs", "List developer logs.", ("dev",), "low", None),
        ("dev_get_request_log", "Get a developer request log.", ("dev",), "low", None),
        ("dev_replay_request", "Replay a developer request.", ("dev",), "medium", None),
        ("dev_diff_prompt", "Diff prompt history.", ("dev",), "low", None),
        ("dev_export_trace", "Export a developer trace.", ("dev",), "low", None),
    )
)


MANAGEMENT_FUNCTIONS: tuple[FunctionSpec, ...] = tuple(
    _spec(function_id, description, tags, risk=risk, block=None)
    for function_id, description, tags, risk in (
        ("management_list_modules", "List defaultspack modules.", ("management",), "low"),
        ("management_get_module", "Get a defaultspack module.", ("management",), "low"),
        ("management_set_module_state", "Set defaultspack module state.", ("management",), "high"),
        ("management_get_migration_status", "Get defaultspack migration status.", ("management",), "low"),
        ("pack_request_list", "List pack requests.", ("pack_request",), "low"),
        ("pack_request_get", "Get a pack request.", ("pack_request",), "low"),
        ("pack_request_request_extension", "Request a pack extension.", ("pack_request",), "medium"),
        ("pack_request_forced_patch", "Request a forced patch.", ("pack_request",), "high"),
        ("pack_request_review", "Review a pack request.", ("pack_request",), "medium"),
        ("pack_request_rollback", "Rollback a pack request.", ("pack_request",), "high"),
    )
)


EXTERNAL_INPUT_FUNCTIONS: tuple[FunctionSpec, ...] = (
    _spec("input_endpoint_create", "Create a localhost-only inbound webhook endpoint.", ("external", "input", "webhook"), risk="medium", aliases=("defaults.input.endpoint.create", "defaultspack.input.endpoint.create")),
    _spec("input_endpoint_delete", "Delete a localhost-only inbound webhook endpoint.", ("external", "input", "webhook"), risk="medium", aliases=("defaults.input.endpoint.delete", "defaultspack.input.endpoint.delete")),
    _spec("input_endpoint_list", "List inbound webhook endpoints.", ("external", "input", "webhook"), aliases=("defaults.input.endpoint.list", "defaultspack.input.endpoint.list")),
)


FUNCTION_SPECS: tuple[FunctionSpec, ...] = (
    AI_FUNCTIONS
    + CHAT_FUNCTIONS
    + TOOL_FUNCTIONS
    + SKILL_FUNCTIONS
    + CONVERSATION_FUNCTIONS
    + CODING_FUNCTIONS
    + AGENT_FUNCTIONS
    + REMOTE_FUNCTIONS
    + BROWSER_ARTIFACT_FUNCTIONS
    + RECORDING_FUNCTIONS
    + DATA_FUNCTIONS
    + PROFILE_WORKSPACE_FUNCTIONS
    + RESEARCH_MEDIA_UI_DEV_FUNCTIONS
    + MANAGEMENT_FUNCTIONS
    + EXTERNAL_INPUT_FUNCTIONS
)


FUNCTION_SPECS_BY_ID: dict[str, FunctionSpec] = {
    spec.function_id: spec for spec in FUNCTION_SPECS
}
