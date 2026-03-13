"""
kernel.py - Kernel クラス組み立て (Mixin分割版)

KernelCore (エンジン本体) + KernelFlowExecutionMixin (Flow実行)
+ KernelSystemHandlersMixin (起動系ハンドラ)
+ KernelRuntimeHandlersMixin (運用系ハンドラ) を合成し、
既存の import 互換を維持する薄いモジュール。

使い方（既存互換）:
    from core_runtime.kernel import Kernel, KernelConfig
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from .kernel_core import KernelCore, KernelConfig
from .kernel_flow_execution import KernelFlowExecutionMixin
from .kernel_handlers_system import KernelSystemHandlersMixin
from .kernel_handlers_runtime import KernelRuntimeHandlersMixin

# re-export: 既存の import 互換のため
from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor

_logger = logging.getLogger("rumi.kernel")


# B4: 環境変数でverboseモード判定（後方互換: kernel.py から参照される可能性に備える）
def _is_diagnostics_verbose() -> bool:
    """RUMI_DIAGNOSTICS_VERBOSE=1 かどうか"""
    return os.environ.get("RUMI_DIAGNOSTICS_VERBOSE", "0") == "1"


# 既存のハンドラキー一覧（登録漏れ検知用）
_EXPECTED_HANDLER_KEYS = frozenset([
    "kernel:mounts.init", "kernel:registry.load", "kernel:active_ecosystem.load",
    "kernel:interfaces.publish", "kernel:ir.get", "kernel:ir.call", "kernel:ir.register",
    "kernel:exec_python", "kernel:ctx.set", "kernel:ctx.get", "kernel:ctx.copy",
    "kernel:execute_flow", "kernel:save_flow", "kernel:load_flows", "kernel:flow.compose",
    "kernel:security.init", "kernel:docker.check", "kernel:approval.init", "kernel:approval.scan",
    "kernel:container.init", "kernel:privilege.init", "kernel:api.init",
    "kernel:container.start_approved", "kernel:component.discover", "kernel:component.load",
    "kernel:emit", "kernel:startup.failed", "kernel:vocab.load", "kernel:noop",
    "kernel:flow.load_all", "kernel:flow.execute_by_id",
    "kernel:python_file_call",
    "kernel:modifier.load_all", "kernel:modifier.apply",
    "kernel:network.grant", "kernel:network.revoke", "kernel:network.check", "kernel:network.list",
    "kernel:egress_proxy.start", "kernel:egress_proxy.stop", "kernel:egress_proxy.status",
    "kernel:lib.process_all", "kernel:lib.check", "kernel:lib.execute",
    "kernel:lib.clear_record", "kernel:lib.list_records",
    "kernel:audit.query", "kernel:audit.summary", "kernel:audit.flush",
    "kernel:vocab.list_groups", "kernel:vocab.list_converters", "kernel:vocab.summary", "kernel:vocab.convert",
    "kernel:shared_dict.resolve", "kernel:shared_dict.propose", "kernel:shared_dict.explain",
    "kernel:shared_dict.list", "kernel:shared_dict.remove",
    "kernel:uds_proxy.init", "kernel:uds_proxy.ensure_socket", "kernel:uds_proxy.stop",
    "kernel:uds_proxy.stop_all", "kernel:uds_proxy.status",
    "kernel:capability_proxy.init", "kernel:capability_proxy.status", "kernel:capability_proxy.stop_all",
    "kernel:capability.grant", "kernel:capability.revoke", "kernel:capability.list",
    "kernel:pending.export",
])


# =====================================================================
# Phase B-2a/B-2b: Kernel Handler Manifests (設計決定 D-2)
# 全 kernel ハンドラの最小メタデータ。唯一の権威ソース。
# Phase B-2a: description + tags
# Phase B-2b: input_schema + output_schema (JSON Schema draft-07 互換)
# =====================================================================

# 共通出力スキーマ定義（多くのハンドラが共有する標準応答形式）
_STANDARD_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "_kernel_step_status": {
            "type": "string",
            "enum": ["success", "failed", "skipped"],
            "description": "Step execution result status",
        },
        "_kernel_step_meta": {
            "type": "object",
            "description": "Additional metadata about the step result",
        },
    },
    "required": ["_kernel_step_status"],
}

_KERNEL_HANDLER_MANIFESTS: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # System handlers (kernel_handlers_system.py) — 29 handlers
    # ------------------------------------------------------------------

    # --- mounts / registry / active_ecosystem / interfaces ---
    "kernel:mounts.init": {
        "description": "Initialize mount points from mounts.json configuration",
        "tags": ["kernel", "system", "init", "mounts"],
        "input_schema": {
            "type": "object",
            "properties": {
                "mounts_file": {
                    "type": "string",
                    "description": "Path to mounts.json configuration file",
                    "default": "user_data/mounts.json",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "description": "Returns mount_manager instance on success, or standard error object on failure",
        },
    },
    "kernel:registry.load": {
        "description": "Load the ecosystem pack registry from the ecosystem directory",
        "tags": ["kernel", "system", "init", "registry"],
        "input_schema": {
            "type": "object",
            "properties": {
                "ecosystem_dir": {
                    "type": "string",
                    "description": "Path to ecosystem directory containing packs",
                    "default": "ecosystem",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "description": "Returns Registry instance on success, or standard error object on failure",
        },
    },
    "kernel:active_ecosystem.load": {
        "description": "Load active ecosystem configuration from JSON file",
        "tags": ["kernel", "system", "init", "ecosystem"],
        "input_schema": {
            "type": "object",
            "properties": {
                "config_file": {
                    "type": "string",
                    "description": "Path to active_ecosystem.json configuration file",
                    "default": "user_data/active_ecosystem.json",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "description": "Returns ActiveEcosystemManager instance on success, or standard error object on failure",
        },
    },
    "kernel:interfaces.publish": {
        "description": "Publish kernel ready state to InterfaceRegistry",
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "services_ready": {
                    "type": "boolean",
                    "description": "Whether kernel services are ready",
                },
            },
            "required": ["services_ready"],
        },
    },

    # --- IR (InterfaceRegistry) handlers ---
    "kernel:ir.get": {
        "description": "Get a value from InterfaceRegistry by key",
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "InterfaceRegistry key to retrieve",
                },
                "strategy": {
                    "type": "string",
                    "description": "Retrieval strategy",
                    "default": "last",
                    "enum": ["last", "first", "all"],
                },
                "store_as": {
                    "type": "string",
                    "description": "If set, store the retrieved value in ctx under this key",
                },
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "strategy": {"type": "string"},
                        "found": {"type": "boolean"},
                    },
                },
                "value": {
                    "description": "The retrieved value (any type)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ir.call": {
        "description": "Call a callable registered in InterfaceRegistry by key",
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "InterfaceRegistry key of the callable to invoke",
                },
                "strategy": {
                    "type": "string",
                    "description": "Retrieval strategy for the callable",
                    "default": "last",
                },
                "call_args": {
                    "type": "object",
                    "description": "Keyword arguments to pass to the callable",
                    "default": {},
                },
                "pass_ctx": {
                    "type": "boolean",
                    "description": "If true, pass ctx as the sole argument instead of call_args",
                    "default": False,
                },
                "store_as": {
                    "type": "string",
                    "description": "If set, store the call result in ctx under this key",
                },
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed", "skipped"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "has_result": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                },
                "result": {
                    "description": "The return value of the called function (any type)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ir.register": {
        "description": "Register a value into InterfaceRegistry",
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "InterfaceRegistry key to register under",
                },
                "value": {
                    "description": "Value to register (any type, resolved via _resolve_value)",
                },
                "value_from_ctx": {
                    "type": "string",
                    "description": "If set, retrieve value from ctx[value_from_ctx] instead of 'value'",
                },
                "meta": {
                    "type": "object",
                    "description": "Optional metadata dict to attach to the registration",
                    "default": {},
                },
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "has_value": {"type": "boolean"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- exec_python ---
    "kernel:exec_python": {
        "description": "Execute a Python file with sandboxed context and inject support",
        "tags": ["kernel", "system", "exec"],
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Relative path to the Python file to execute",
                },
                "base_path": {
                    "type": "string",
                    "description": "Base directory for resolving file path",
                },
                "phase": {
                    "type": "string",
                    "description": "Execution phase name",
                    "default": "exec",
                },
                "inject": {
                    "type": "object",
                    "description": "Key-value pairs to inject into the execution context (blocked keys are filtered)",
                },
            },
            "required": ["file"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed", "skipped"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "phase": {"type": "string"},
                        "reason": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- ctx handlers ---
    "kernel:ctx.set": {
        "description": "Set a value in the flow execution context",
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Context key to set",
                },
                "value": {
                    "description": "Value to set (any type, resolved via _resolve_value)",
                },
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ctx.get": {
        "description": "Get a value from the flow execution context",
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Context key to retrieve",
                },
                "default": {
                    "description": "Default value if key is not found (any type)",
                },
                "store_as": {
                    "type": "string",
                    "description": "If set, store the retrieved value in ctx under this key",
                },
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "found": {"type": "boolean"},
                    },
                },
                "value": {
                    "description": "The retrieved value (any type)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ctx.copy": {
        "description": "Copy a value between keys in the flow execution context",
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {
            "type": "object",
            "properties": {
                "from_key": {
                    "type": "string",
                    "description": "Source context key to copy from",
                },
                "to_key": {
                    "type": "string",
                    "description": "Destination context key to copy to",
                },
            },
            "required": ["from_key", "to_key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "from_key": {"type": "string"},
                        "to_key": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- flow execution ---
    "kernel:execute_flow": {
        "description": "Execute a sub-flow by flow_id with optional context and timeout",
        "tags": ["kernel", "system", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_id": {
                    "type": "string",
                    "description": "ID of the flow to execute",
                },
                "context": {
                    "type": "object",
                    "description": "Context dict to pass to the sub-flow",
                    "default": {},
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the flow execution",
                },
            },
            "required": ["flow_id"],
        },
        "output_schema": {
            "type": "object",
            "description": "Flow execution result dict; contains _error key on failure",
        },
    },
    "kernel:save_flow": {
        "description": "Save a flow definition to a YAML file",
        "tags": ["kernel", "system", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_id": {
                    "type": "string",
                    "description": "ID for the flow to save",
                },
                "flow_def": {
                    "type": "object",
                    "description": "Flow definition dict to save",
                },
                "path": {
                    "type": "string",
                    "description": "Directory path to save the flow file",
                    "default": "user_data/flows",
                },
            },
            "required": ["flow_id", "flow_def"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path where the flow was saved",
                },
            },
        },
    },
    "kernel:load_flows": {
        "description": "Load user-defined flows from a directory",
        "tags": ["kernel", "system", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to load flows from",
                    "default": "user_data/flows",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "loaded": {
                    "type": "array",
                    "description": "List of loaded flow IDs",
                    "items": {"type": "string"},
                },
            },
        },
    },
    "kernel:flow.compose": {
        "description": "Collect and apply flow modifiers via FlowComposer",
        "tags": ["kernel", "system", "flow", "modifier"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed", "skipped"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "modifiers_collected": {"type": "integer"},
                        "modifiers_applied": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- security / docker / approval ---
    "kernel:security.init": {
        "description": "Initialize security subsystem with strict mode configuration",
        "tags": ["kernel", "system", "security", "init"],
        "input_schema": {
            "type": "object",
            "properties": {
                "strict_mode": {
                    "type": "boolean",
                    "description": "Whether to enable strict security mode",
                    "default": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:docker.check": {
        "description": "Check Docker daemon availability",
        "tags": ["kernel", "system", "security", "docker"],
        "input_schema": {
            "type": "object",
            "properties": {
                "required": {
                    "type": "boolean",
                    "description": "Whether Docker is required (fail if not available)",
                    "default": True,
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Timeout in seconds for docker info check",
                    "default": 10,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "docker_available": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:approval.init": {
        "description": "Initialize the approval manager for pack approval workflow",
        "tags": ["kernel", "system", "security", "approval"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:approval.scan": {
        "description": "Scan all packs and classify by approval status",
        "tags": ["kernel", "system", "security", "approval"],
        "input_schema": {
            "type": "object",
            "properties": {
                "check_hash": {
                    "type": "boolean",
                    "description": "Whether to verify pack hashes for approved packs",
                    "default": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "approved": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of approved pack IDs",
                        },
                        "pending": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of pending pack IDs",
                        },
                        "modified": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of modified pack IDs",
                        },
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- container / privilege / api ---
    "kernel:container.init": {
        "description": "Initialize the container orchestrator",
        "tags": ["kernel", "system", "component", "container"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:privilege.init": {
        "description": "Initialize the host privilege manager",
        "tags": ["kernel", "system", "security", "privilege"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:api.init": {
        "description": "Initialize the Pack API server on specified host and port",
        "tags": ["kernel", "system", "init", "api"],
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host address to bind the API server",
                    "default": "127.0.0.1",
                },
                "port": {
                    "type": "integer",
                    "description": "Port number for the API server",
                    "default": 8765,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:container.start_approved": {
        "description": "Start containers for all approved packs",
        "tags": ["kernel", "system", "component", "container"],
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout_per_pack": {
                    "type": "number",
                    "description": "Timeout in seconds for starting each pack container",
                    "default": 30,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "skipped"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "started": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Pack IDs whose containers were started",
                        },
                        "failed": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "pack_id": {"type": "string"},
                                    "error": {"type": "string"},
                                },
                            },
                            "description": "Packs that failed to start",
                        },
                        "reason": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- component discover / load ---
    "kernel:component.discover": {
        "description": "Discover components from approved packs with override and disable filtering",
        "tags": ["kernel", "system", "component"],
        "input_schema": {
            "type": "object",
            "properties": {
                "approved_only": {
                    "type": "boolean",
                    "description": "Whether to filter components to approved packs only",
                    "default": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of components discovered",
                        },
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:component.load": {
        "description": "Load discovered components and run setup phase",
        "tags": ["kernel", "system", "component"],
        "input_schema": {
            "type": "object",
            "properties": {
                "container_execution": {
                    "type": "boolean",
                    "description": "Whether to use container-based execution for components",
                    "default": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "loaded": {"type": "integer"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- emit / startup.failed / vocab.load / noop ---
    "kernel:emit": {
        "description": "Emit an event via EventBus",
        "tags": ["kernel", "system", "event"],
        "input_schema": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "string",
                    "description": "Event name to emit",
                    "default": "",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:startup.failed": {
        "description": "Record startup failure with pending approval and modified pack details",
        "tags": ["kernel", "system", "init", "error"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:vocab.load": {
        "description": "Load vocabulary definitions from a file into VocabRegistry",
        "tags": ["kernel", "system", "vocab"],
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to the vocabulary definition file",
                },
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID that owns this vocabulary file",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed", "skipped"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "groups_loaded": {
                            "type": "integer",
                            "description": "Number of vocabulary groups loaded",
                        },
                        "reason": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:noop": {
        "description": "No-operation placeholder handler",
        "tags": ["kernel", "system", "noop"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "handler": {
                            "type": "string",
                            "enum": ["noop"],
                        },
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # ------------------------------------------------------------------
    # Runtime handlers (kernel_handlers_runtime.py) — 41 handlers
    # ------------------------------------------------------------------

    # --- flow ---
    "kernel:flow.load_all": {
        "description": "Load all flow files, apply modifiers, and register to InterfaceRegistry",
        "tags": ["kernel", "runtime", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "flows_registered": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of registered flow IDs",
                        },
                        "flow_error_count": {"type": "integer"},
                        "modifiers_loaded": {"type": "integer"},
                        "modifiers_applied": {"type": "integer"},
                        "modifiers_skipped": {"type": "integer"},
                        "flows_skipped_count": {"type": "integer"},
                        "modifiers_skipped_by_approval": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:flow.execute_by_id": {
        "description": "Execute a flow by ID with optional shared dict resolution",
        "tags": ["kernel", "runtime", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_id": {
                    "type": "string",
                    "description": "ID of the flow to execute",
                },
                "inputs": {
                    "type": "object",
                    "description": "Input values to merge into the flow execution context",
                    "default": {},
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the flow execution",
                },
                "resolve": {
                    "type": "boolean",
                    "description": "Whether to resolve flow_id via shared dictionary",
                    "default": False,
                },
                "resolve_namespace": {
                    "type": "string",
                    "description": "Namespace to use for shared dict resolution",
                    "default": "flow_id",
                },
            },
            "required": ["flow_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "flow_id": {"type": "string"},
                        "original_flow_id": {"type": ["string", "null"]},
                        "resolved": {"type": "boolean"},
                    },
                },
                "result": {
                    "type": "object",
                    "description": "Flow execution result",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- python_file_call ---
    "kernel:python_file_call": {
        "description": "Execute a Python file via container with UDS egress proxy support",
        "tags": ["kernel", "runtime", "exec"],
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to the Python file to execute",
                },
                "owner_pack": {
                    "type": "string",
                    "description": "Pack ID that owns this file (for UDS proxy and security)",
                },
                "principal_id": {
                    "type": "string",
                    "description": "Principal ID for capability-based access control",
                },
                "input": {
                    "type": "object",
                    "description": "Input data to pass to the Python file",
                    "default": {},
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Execution timeout in seconds",
                    "default": 60.0,
                },
                "_step_id": {
                    "type": "string",
                    "description": "Internal step ID for diagnostics",
                    "default": "unknown",
                },
                "_phase": {
                    "type": "string",
                    "description": "Internal phase name for diagnostics",
                    "default": "flow",
                },
            },
            "required": ["file"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "execution_mode": {"type": "string"},
                        "execution_time_ms": {"type": "number"},
                        "error": {"type": "string"},
                        "error_type": {"type": "string"},
                    },
                },
                "output": {
                    "description": "Output data from the executed Python file (any type)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- modifier ---
    "kernel:modifier.load_all": {
        "description": "Load all modifier files for flow modification",
        "tags": ["kernel", "runtime", "modifier", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "loaded": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of loaded modifier IDs",
                        },
                        "error_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:modifier.apply": {
        "description": "Apply modifiers to a specific flow and update InterfaceRegistry",
        "tags": ["kernel", "runtime", "modifier", "flow"],
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_id": {
                    "type": "string",
                    "description": "Target flow ID to apply modifiers to (if omitted, applies to all flows)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "success_count": {"type": "integer"},
                        "skip_count": {"type": "integer"},
                        "fail_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- network ---
    "kernel:network.grant": {
        "description": "Grant network access to a pack with allowed domains and ports",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to grant network access to",
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of allowed domain names",
                    "default": [],
                },
                "allowed_ports": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of allowed port numbers",
                    "default": [],
                },
                "granted_by": {
                    "type": "string",
                    "description": "Identity of the granter",
                    "default": "kernel",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for the grant",
                    "default": "",
                },
            },
            "required": ["pack_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
                "grant": {
                    "type": "object",
                    "description": "Network grant details",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:network.revoke": {
        "description": "Revoke network access for a pack",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to revoke network access from",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for revoking network access",
                    "default": "",
                },
            },
            "required": ["pack_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "revoked": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:network.check": {
        "description": "Check if a pack has network access to a specific domain and port",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to check network access for",
                },
                "domain": {
                    "type": "string",
                    "description": "Domain name to check access to",
                },
                "port": {
                    "type": "integer",
                    "description": "Port number to check access to",
                },
            },
            "required": ["pack_id", "domain", "port"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "allowed": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
                "result": {
                    "type": "object",
                    "properties": {
                        "allowed": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "pack_id": {"type": "string"},
                        "domain": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:network.list": {
        "description": "List all network grants and disabled packs",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "grant_count": {"type": "integer"},
                        "disabled_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "grants": {
                    "type": "object",
                    "description": "Map of pack_id to grant details",
                },
                "disabled_packs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of disabled pack IDs",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- egress_proxy ---
    "kernel:egress_proxy.start": {
        "description": "Start the HTTP egress proxy server",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host address to bind the egress proxy",
                },
                "port": {
                    "type": "integer",
                    "description": "Port number for the egress proxy",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "endpoint": {"type": "string"},
                        "running": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:egress_proxy.stop": {
        "description": "Stop the HTTP egress proxy server",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:egress_proxy.status": {
        "description": "Get the HTTP egress proxy running status and endpoint",
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "running": {"type": "boolean"},
                        "endpoint": {"type": ["string", "null"]},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- lib ---
    "kernel:lib.process_all": {
        "description": "Process lib install/update scripts for all packs",
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {
            "type": "object",
            "properties": {
                "packs_dir": {
                    "type": "string",
                    "description": "Directory containing pack directories",
                    "default": "ecosystem",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "installed": {"type": "integer"},
                        "updated": {"type": "integer"},
                        "failed_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "results": {
                    "type": "object",
                    "description": "Detailed processing results per pack",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:lib.check": {
        "description": "Check if a pack needs lib install or update",
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to check",
                },
                "pack_dir": {
                    "type": "string",
                    "description": "Directory of the pack (defaults to ecosystem/<pack_id>)",
                },
            },
            "required": ["pack_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "needs_install": {"type": "boolean"},
                        "needs_update": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:lib.execute": {
        "description": "Manually execute a pack lib install or update script",
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to execute lib script for",
                },
                "lib_type": {
                    "type": "string",
                    "description": "Type of lib script to execute",
                    "enum": ["install", "update"],
                },
                "pack_dir": {
                    "type": "string",
                    "description": "Directory of the pack (defaults to ecosystem/<pack_id>)",
                },
            },
            "required": ["pack_id", "lib_type"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "lib_type": {"type": "string"},
                        "success": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
                "output": {
                    "description": "Output from the lib script execution",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:lib.clear_record": {
        "description": "Clear lib execution record for a pack or all packs",
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to clear record for (if omitted, clears all records)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "cleared": {"type": "boolean"},
                        "cleared_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:lib.list_records": {
        "description": "List all lib execution records",
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "records": {
                    "type": "object",
                    "description": "Map of pack_id to execution record",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- audit ---
    "kernel:audit.query": {
        "description": "Query audit logs with optional filters",
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by audit log category",
                },
                "start_date": {
                    "type": "string",
                    "description": "Filter by start date (ISO 8601)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Filter by end date (ISO 8601)",
                },
                "pack_id": {
                    "type": "string",
                    "description": "Filter by pack ID",
                },
                "flow_id": {
                    "type": "string",
                    "description": "Filter by flow ID",
                },
                "success_only": {
                    "type": "boolean",
                    "description": "If true, return only successful entries",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 100,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "results": {
                    "type": "array",
                    "description": "List of audit log entries",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:audit.summary": {
        "description": "Get audit log summary by category or date",
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter summary by category",
                },
                "date": {
                    "type": "string",
                    "description": "Filter summary by date (ISO 8601 date)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "description": "Summary statistics",
                },
                "summary": {
                    "type": "object",
                    "description": "Audit log summary data",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:audit.flush": {
        "description": "Flush pending audit log entries to storage",
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- vocab (runtime) ---
    "kernel:vocab.list_groups": {
        "description": "List all vocabulary groups in VocabRegistry",
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "groups": {
                    "type": "array",
                    "description": "List of vocabulary groups",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:vocab.list_converters": {
        "description": "List all vocabulary converters in VocabRegistry",
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "converters": {
                    "type": "array",
                    "description": "List of vocabulary converters",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:vocab.summary": {
        "description": "Get vocabulary registry summary statistics",
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "description": "Summary totals",
                },
                "summary": {
                    "type": "object",
                    "description": "Detailed vocabulary registry summary",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:vocab.convert": {
        "description": "Convert a term using VocabRegistry converters",
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {
            "type": "object",
            "properties": {
                "from_term": {
                    "type": "string",
                    "description": "Source term for conversion",
                },
                "to_term": {
                    "type": "string",
                    "description": "Target term for conversion",
                },
                "data": {
                    "description": "Data to convert (any type)",
                },
                "log_success": {
                    "type": "boolean",
                    "description": "Whether to log successful conversions",
                    "default": False,
                },
            },
            "required": ["from_term", "to_term"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "converted": {"type": "boolean"},
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
                "result": {
                    "description": "Conversion result (any type)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- shared_dict ---
    "kernel:shared_dict.resolve": {
        "description": "Resolve a key through the shared dictionary chain",
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Shared dictionary namespace",
                },
                "token": {
                    "type": "string",
                    "description": "Token to resolve",
                },
            },
            "required": ["namespace", "token"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "original": {"type": "string"},
                        "resolved": {"type": "string"},
                        "hop_count": {"type": "integer"},
                        "cycle_detected": {"type": "boolean"},
                        "max_hops_reached": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
                "resolved": {
                    "type": "string",
                    "description": "The resolved value",
                },
                "hops": {
                    "type": "array",
                    "description": "Resolution hop chain",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:shared_dict.propose": {
        "description": "Propose a new entry to the shared dictionary",
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Shared dictionary namespace",
                },
                "token": {
                    "type": "string",
                    "description": "Token to propose",
                },
                "value": {
                    "description": "Value to associate with the token (any type)",
                },
                "provenance": {
                    "type": "object",
                    "description": "Provenance metadata for the proposal",
                    "default": {},
                },
            },
            "required": ["namespace", "token", "value"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "accepted": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
                "result": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "namespace": {"type": "string"},
                        "token": {"type": "string"},
                        "value": {},
                        "reason": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:shared_dict.explain": {
        "description": "Explain resolution chain for a shared dictionary key",
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Shared dictionary namespace",
                },
                "token": {
                    "type": "string",
                    "description": "Token to explain resolution for",
                },
            },
            "required": ["namespace", "token"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "original": {"type": "string"},
                        "resolved": {"type": "string"},
                        "hop_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "explanation": {
                    "type": "object",
                    "properties": {
                        "original": {"type": "string"},
                        "resolved": {"type": "string"},
                        "hops": {"type": "array"},
                        "cycle_detected": {"type": "boolean"},
                        "max_hops_reached": {"type": "boolean"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:shared_dict.list": {
        "description": "List all entries in a shared dictionary namespace",
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list rules for (if omitted, lists all namespaces)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "rule_count": {"type": "integer"},
                        "namespace_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "rules": {
                    "type": "array",
                    "description": "List of rules in the namespace (when namespace specified)",
                },
                "namespaces": {
                    "type": "array",
                    "description": "List of all namespaces (when namespace not specified)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:shared_dict.remove": {
        "description": "Remove an entry from the shared dictionary",
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Shared dictionary namespace",
                },
                "token": {
                    "type": "string",
                    "description": "Token to remove",
                },
                "provenance": {
                    "type": "object",
                    "description": "Provenance metadata for the removal",
                    "default": {},
                },
            },
            "required": ["namespace", "token"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "removed": {"type": "boolean"},
                        "namespace": {"type": "string"},
                        "token": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- uds_proxy ---
    "kernel:uds_proxy.init": {
        "description": "Initialize the UDS egress proxy manager",
        "tags": ["kernel", "runtime", "network", "uds"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "base_dir": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:uds_proxy.ensure_socket": {
        "description": "Ensure a UDS socket exists for a pack",
        "tags": ["kernel", "runtime", "network", "uds"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to ensure socket for",
                },
            },
            "required": ["pack_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "socket_path": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:uds_proxy.stop": {
        "description": "Stop a UDS proxy for a specific pack",
        "tags": ["kernel", "runtime", "network", "uds"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID whose UDS proxy to stop",
                },
            },
            "required": ["pack_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string"},
                        "stopped": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:uds_proxy.stop_all": {
        "description": "Stop all UDS proxies",
        "tags": ["kernel", "runtime", "network", "uds"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "stopped": {"type": "integer"},
                        "packs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:uds_proxy.status": {
        "description": "Get UDS proxy status for a pack or all packs",
        "tags": ["kernel", "runtime", "network", "uds"],
        "input_schema": {
            "type": "object",
            "properties": {
                "pack_id": {
                    "type": "string",
                    "description": "Pack ID to check status for (if omitted, returns status for all)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "initialized": {"type": "boolean"},
                        "active_packs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "base_dir": {"type": "string"},
                        "pack_id": {"type": "string"},
                        "is_running": {"type": "boolean"},
                        "socket_path": {"type": ["string", "null"]},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- capability_proxy ---
    "kernel:capability_proxy.init": {
        "description": "Initialize the capability proxy for principal-based access control",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "base_dir": {"type": "string"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:capability_proxy.status": {
        "description": "Get capability proxy status",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "description": "Capability proxy status details (initialized, active principals, etc.)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:capability_proxy.stop_all": {
        "description": "Stop all capability proxy instances",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "stopped": {"type": "integer"},
                        "principals": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- capability grant ---
    "kernel:capability.grant": {
        "description": "Grant a capability to a principal",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {
                "principal_id": {
                    "type": "string",
                    "description": "Principal ID to grant capability to",
                },
                "permission_id": {
                    "type": "string",
                    "description": "Permission ID to grant",
                },
                "config": {
                    "type": "object",
                    "description": "Optional configuration for the granted capability",
                },
            },
            "required": ["principal_id", "permission_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "principal_id": {"type": "string"},
                        "permission_id": {"type": "string"},
                        "granted": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:capability.revoke": {
        "description": "Revoke a capability from a principal",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {
                "principal_id": {
                    "type": "string",
                    "description": "Principal ID to revoke capability from",
                },
                "permission_id": {
                    "type": "string",
                    "description": "Permission ID to revoke",
                },
            },
            "required": ["principal_id", "permission_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "principal_id": {"type": "string"},
                        "permission_id": {"type": "string"},
                        "revoked": {"type": "boolean"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:capability.list": {
        "description": "List capabilities for a principal",
        "tags": ["kernel", "runtime", "capability"],
        "input_schema": {
            "type": "object",
            "properties": {
                "principal_id": {
                    "type": "string",
                    "description": "Principal ID to list capabilities for (if omitted, lists all grants)",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "principal_id": {"type": "string"},
                        "found": {"type": "boolean"},
                        "grant_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
                "grant": {
                    "type": ["object", "null"],
                    "description": "Grant details for a specific principal",
                },
                "grants": {
                    "type": "object",
                    "description": "Map of principal_id to grant details (when listing all)",
                },
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- pending export ---
    "kernel:pending.export": {
        "description": "Export pending pack approval data to output directory",
        "tags": ["kernel", "runtime", "approval"],
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "Directory to write the pending summary file",
                    "default": "user_data/pending",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {
                    "type": "string",
                    "enum": ["success", "failed"],
                },
                "_kernel_step_meta": {
                    "type": "object",
                    "properties": {
                        "output_file": {"type": "string"},
                        "packs_pending": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
}


class Kernel(KernelSystemHandlersMixin, KernelRuntimeHandlersMixin, KernelFlowExecutionMixin, KernelCore):
    """
    Rumi AI OS カーネル

    Mixin方式で分割された4クラスを合成する:
    - KernelCore: エンジン本体（Flow読込、ctx構築、shutdown等）
    - KernelFlowExecutionMixin: Flow実行ロジック（run_startup, execute_flow等）
    - KernelSystemHandlersMixin: 起動/システム系 _h_* ハンドラ
    - KernelRuntimeHandlersMixin: 運用/実行系 _h_* ハンドラ
    """

    def __init__(self, config: Optional[KernelConfig] = None,
                 diagnostics: Optional[Diagnostics] = None,
                 install_journal: Optional[InstallJournal] = None,
                 interface_registry: Optional[InterfaceRegistry] = None,
                 event_bus: Optional[EventBus] = None,
                 lifecycle: Optional[ComponentLifecycleExecutor] = None) -> None:
        KernelCore.__init__(
            self,
            config=config,
            diagnostics=diagnostics,
            install_journal=install_journal,
            interface_registry=interface_registry,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )
        self._init_kernel_handlers()

    def _init_kernel_handlers(self) -> None:
        """
        全ハンドラを登録する。

        system/runtime の Mixin が提供する _register_*_handlers() を呼び、
        統合辞書を構築する。
        Phase B-2a: 登録後に FunctionRegistry へ最小メタデータを登録する。
        """
        self._kernel_handlers = {}
        self._kernel_handlers.update(self._register_system_handlers())
        self._kernel_handlers.update(self._register_runtime_handlers())

        # 登録漏れ検知（diagnostics warning のみ、起動は止めない）
        registered_keys = set(self._kernel_handlers.keys())
        missing = _EXPECTED_HANDLER_KEYS - registered_keys
        if missing:
            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.missing_check",
                handler="kernel:init",
                status="failed",
                error={"type": "MissingHandlers", "message": f"Missing handler keys: {sorted(missing)}"},
                meta={"missing_keys": sorted(missing), "registered_count": len(registered_keys)}
            )

        # Phase B-2a: Register kernel handlers to FunctionRegistry
        self._register_handlers_to_function_registry()

    def _register_handlers_to_function_registry(self) -> None:
        """
        Phase B-2a: _KERNEL_HANDLER_MANIFESTS の各エントリを
        FunctionRegistry に登録する。

        FunctionRegistry インスタンスを InterfaceRegistry から取得するか、
        なければ新規作成して "function_registry" キーで登録する。
        登録失敗時は警告ログのみ（起動を止めない）。
        """
        try:
            from .function_registry import FunctionRegistry, FunctionEntry

            # InterfaceRegistry から既存の FunctionRegistry を取得、なければ新規作成
            existing = self.interface_registry.get("function_registry", strategy="last")
            if existing is not None and isinstance(existing, FunctionRegistry):
                func_registry = existing
            else:
                func_registry = FunctionRegistry()
                self.interface_registry.register(
                    "function_registry",
                    func_registry,
                    meta={"source": "kernel", "phase": "b2a"},
                )

            registered_count = 0
            skipped_count = 0
            error_count = 0

            for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
                try:
                    # function_id: "kernel:" prefix を除去
                    function_id = handler_key
                    if function_id.startswith("kernel:"):
                        function_id = function_id[len("kernel:"):]

                    entry = FunctionEntry(
                        function_id=function_id,
                        pack_id="kernel",
                        description=manifest["description"],
                        tags=list(manifest["tags"]),
                        host_execution=True,
                        vocab_aliases=[handler_key],
                    )

                    if func_registry.register(entry):
                        registered_count += 1
                    else:
                        skipped_count += 1

                except Exception as exc:
                    error_count += 1
                    _logger.warning(
                        "Failed to register kernel handler to FunctionRegistry: %s (%s)",
                        handler_key, exc,
                    )

            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.function_registry",
                handler="kernel:init",
                status="success",
                meta={
                    "registered": registered_count,
                    "skipped": skipped_count,
                    "errors": error_count,
                    "total_manifests": len(_KERNEL_HANDLER_MANIFESTS),
                },
            )

            _logger.info(
                "Kernel handlers registered to FunctionRegistry: "
                "%d registered, %d skipped, %d errors",
                registered_count, skipped_count, error_count,
            )

        except Exception as exc:
            _logger.warning(
                "Failed to register kernel handlers to FunctionRegistry: %s", exc
            )
            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.function_registry",
                handler="kernel:init",
                status="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )


__all__ = ["Kernel", "KernelConfig"]
