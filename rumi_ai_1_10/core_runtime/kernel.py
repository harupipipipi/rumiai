"""
kernel.py - Kernel クラス組み立て (Mixin分割版)

KernelCore (エンジン本体) + KernelFlowExecutionMixin (Flow実行)
+ KernelSystemHandlersMixin (起動系ハンドラ)
+ KernelRuntimeHandlersMixin (運用系ハンドラ) を合成し、
既存の import 互換を維持する薄いモジュール。

使い方（既存互換）:
    from core_runtime.kernel import Kernel, KernelConfig

Phase B-1: _KERNEL_HANDLER_MANIFESTS が唯一の権威ソース。
           _EXPECTED_HANDLER_KEYS は _KERNEL_HANDLER_MANIFESTS.keys() から導出。
Phase B-2a: description + tags
Phase B-2b: input_schema + output_schema (JSON Schema draft-07 互換)
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


# =====================================================================
# Phase B-1 / B-2a / B-2b: Kernel Handler Manifests (設計決定 D-2)
# 全 kernel ハンドラの最小メタデータ。唯一の権威ソース。
# Phase B-1: permission_id + risk + requires (Function Unification)
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
        "permission_id": "kernel:mounts.init",
        "risk": "medium",
        "requires": [],
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
        "permission_id": "kernel:registry.load",
        "risk": "low",
        "requires": [],
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
        "permission_id": "kernel:active_ecosystem.load",
        "risk": "low",
        "requires": [],
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
        "permission_id": "kernel:interfaces.publish",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "ir"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {
            "type": "object",
            "properties": {
                "services_ready": {"type": "boolean", "description": "Whether kernel services are ready"},
            },
            "required": ["services_ready"],
        },
    },

    # --- IR (InterfaceRegistry) handlers ---
    "kernel:ir.get": {
        "description": "Get a value from InterfaceRegistry by key",
        "permission_id": "kernel:ir.get",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "InterfaceRegistry key to retrieve"},
                "strategy": {"type": "string", "description": "Retrieval strategy", "default": "last", "enum": ["last", "first", "all"]},
                "store_as": {"type": "string", "description": "If set, store the retrieved value in ctx under this key"},
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {"type": "string", "enum": ["success", "failed"]},
                "_kernel_step_meta": {"type": "object"},
                "value": {"description": "The retrieved value (any type)"},
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ir.call": {
        "description": "Call a callable registered in InterfaceRegistry by key",
        "permission_id": "kernel:ir.call",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "InterfaceRegistry key of the callable to invoke"},
                "strategy": {"type": "string", "description": "Retrieval strategy for the callable", "default": "last"},
                "call_args": {"type": "object", "description": "Keyword arguments to pass to the callable", "default": {}},
                "pass_ctx": {"type": "boolean", "description": "If true, pass ctx as the sole argument", "default": False},
                "store_as": {"type": "string", "description": "If set, store the call result in ctx under this key"},
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {"type": "string", "enum": ["success", "failed", "skipped"]},
                "_kernel_step_meta": {"type": "object"},
                "result": {"description": "The return value of the called function (any type)"},
            },
            "required": ["_kernel_step_status"],
        },
    },
    "kernel:ir.register": {
        "description": "Register a value into InterfaceRegistry",
        "permission_id": "kernel:ir.register",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "ir"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "InterfaceRegistry key to register under"},
                "value": {"description": "Value to register (any type, resolved via _resolve_value)"},
                "value_from_ctx": {"type": "string", "description": "If set, retrieve value from ctx[value_from_ctx]"},
                "meta": {"type": "object", "description": "Optional metadata dict", "default": {}},
            },
            "required": ["key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {"type": "string", "enum": ["success", "failed"]},
                "_kernel_step_meta": {"type": "object"},
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- exec_python ---
    "kernel:exec_python": {
        "description": "Execute a Python file with sandboxed context and inject support",
        "permission_id": "kernel:exec_python",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "exec"],
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Relative path to the Python file to execute"},
                "base_path": {"type": "string", "description": "Base directory for resolving file path"},
                "phase": {"type": "string", "description": "Execution phase name", "default": "exec"},
                "inject": {"type": "object", "description": "Key-value pairs to inject (blocked keys are filtered)"},
            },
            "required": ["file"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {"type": "string", "enum": ["success", "failed", "skipped"]},
                "_kernel_step_meta": {"type": "object"},
            },
            "required": ["_kernel_step_status"],
        },
    },

    # --- ctx handlers ---
    "kernel:ctx.set": {
        "description": "Set a value in the flow execution context",
        "permission_id": "kernel:ctx.set",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Context key to set"},
                "value": {"description": "Value to set (any type)"},
            },
            "required": ["key"],
        },
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:ctx.get": {
        "description": "Get a value from the flow execution context",
        "permission_id": "kernel:ctx.get",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Context key to retrieve"},
                "default": {"description": "Default value if key is not found"},
                "store_as": {"type": "string", "description": "If set, store value in ctx under this key"},
            },
            "required": ["key"],
        },
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "value": {"description": "Retrieved value"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:ctx.copy": {
        "description": "Copy a value between keys in the flow execution context",
        "permission_id": "kernel:ctx.copy",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "ctx"],
        "input_schema": {"type": "object", "properties": {"from_key": {"type": "string"}, "to_key": {"type": "string"}}, "required": ["from_key", "to_key"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- flow execution ---
    "kernel:execute_flow": {
        "description": "Execute a sub-flow by flow_id with optional context and timeout",
        "permission_id": "kernel:execute_flow",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "flow"],
        "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}, "context": {"type": "object", "default": {}}, "timeout": {"type": "number"}}, "required": ["flow_id"]},
        "output_schema": {"type": "object", "description": "Flow execution result dict; contains _error key on failure"},
    },
    "kernel:save_flow": {
        "description": "Save a flow definition to a YAML file",
        "permission_id": "kernel:save_flow",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "flow"],
        "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}, "flow_def": {"type": "object"}, "path": {"type": "string", "default": "user_data/flows"}}, "required": ["flow_id", "flow_def"]},
        "output_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    "kernel:load_flows": {
        "description": "Load user-defined flows from a directory",
        "permission_id": "kernel:load_flows",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "flow"],
        "input_schema": {"type": "object", "properties": {"path": {"type": "string", "default": "user_data/flows"}}},
        "output_schema": {"type": "object", "properties": {"loaded": {"type": "array", "items": {"type": "string"}}}},
    },
    "kernel:flow.compose": {
        "description": "Collect and apply flow modifiers via FlowComposer",
        "permission_id": "kernel:flow.compose",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "flow", "modifier"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed", "skipped"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- security / docker / approval ---
    "kernel:security.init": {
        "description": "Initialize security subsystem with strict mode configuration",
        "permission_id": "kernel:security.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "security", "init"],
        "input_schema": {"type": "object", "properties": {"strict_mode": {"type": "boolean", "default": True}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:docker.check": {
        "description": "Check Docker daemon availability",
        "permission_id": "kernel:docker.check",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "security", "docker"],
        "input_schema": {"type": "object", "properties": {"required": {"type": "boolean", "default": True}, "timeout_seconds": {"type": "number", "default": 10}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:approval.init": {
        "description": "Initialize the approval manager for pack approval workflow",
        "permission_id": "kernel:approval.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "security", "approval"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:approval.scan": {
        "description": "Scan all packs and classify by approval status",
        "permission_id": "kernel:approval.scan",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "security", "approval"],
        "input_schema": {"type": "object", "properties": {"check_hash": {"type": "boolean", "default": True}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- container / privilege / api ---
    "kernel:container.init": {
        "description": "Initialize the container orchestrator",
        "permission_id": "kernel:container.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "component", "container"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:privilege.init": {
        "description": "Initialize the host privilege manager",
        "permission_id": "kernel:privilege.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "security", "privilege"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:api.init": {
        "description": "Initialize the Pack API server on specified host and port",
        "permission_id": "kernel:api.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "init", "api"],
        "input_schema": {"type": "object", "properties": {"host": {"type": "string", "default": "127.0.0.1"}, "port": {"type": "integer", "default": 8765}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:container.start_approved": {
        "description": "Start containers for all approved packs",
        "permission_id": "kernel:container.start_approved",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "component", "container"],
        "input_schema": {"type": "object", "properties": {"timeout_per_pack": {"type": "number", "default": 30}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "skipped"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- component discover / load ---
    "kernel:component.discover": {
        "description": "Discover components from approved packs with override and disable filtering",
        "permission_id": "kernel:component.discover",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "component"],
        "input_schema": {"type": "object", "properties": {"approved_only": {"type": "boolean", "default": True}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:component.load": {
        "description": "Load discovered components and run setup phase",
        "permission_id": "kernel:component.load",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "system", "component"],
        "input_schema": {"type": "object", "properties": {"container_execution": {"type": "boolean", "default": True}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- emit / startup.failed / vocab.load / noop ---
    "kernel:emit": {
        "description": "Emit an event via EventBus",
        "permission_id": "kernel:emit",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "event"],
        "input_schema": {"type": "object", "properties": {"event": {"type": "string", "default": ""}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success"]}}, "required": ["_kernel_step_status"]},
    },
    "kernel:startup.failed": {
        "description": "Record startup failure with pending approval and modified pack details",
        "permission_id": "kernel:startup.failed",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "init", "error"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success"]}}, "required": ["_kernel_step_status"]},
    },
    "kernel:vocab.load": {
        "description": "Load vocabulary definitions from a file into VocabRegistry",
        "permission_id": "kernel:vocab.load",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "vocab"],
        "input_schema": {"type": "object", "properties": {"file": {"type": "string"}, "pack_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed", "skipped"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:noop": {
        "description": "No-operation placeholder handler",
        "permission_id": "kernel:noop",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "system", "noop"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # ------------------------------------------------------------------
    # Runtime handlers (kernel_handlers_runtime.py) — 41 handlers
    # ------------------------------------------------------------------

    # --- flow ---
    "kernel:flow.load_all": {
        "description": "Load all flow files, apply modifiers, and register to InterfaceRegistry",
        "permission_id": "kernel:flow.load_all",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "flow"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:flow.execute_by_id": {
        "description": "Execute a flow by ID with optional shared dict resolution",
        "permission_id": "kernel:flow.execute_by_id",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "flow"],
        "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}, "inputs": {"type": "object", "default": {}}, "timeout": {"type": "number"}, "resolve": {"type": "boolean", "default": False}, "resolve_namespace": {"type": "string", "default": "flow_id"}}, "required": ["flow_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "result": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- python_file_call ---
    "kernel:python_file_call": {
        "description": "Execute a Python file via container with UDS egress proxy support",
        "permission_id": "kernel:python_file_call",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "exec"],
        "input_schema": {"type": "object", "properties": {"file": {"type": "string"}, "owner_pack": {"type": "string"}, "principal_id": {"type": "string"}, "input": {"type": "object", "default": {}}, "timeout_seconds": {"type": "number", "default": 60.0}, "_step_id": {"type": "string", "default": "unknown"}, "_phase": {"type": "string", "default": "flow"}}, "required": ["file"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "output": {}}, "required": ["_kernel_step_status"]},
    },

    # --- universal_call ---
    "kernel:universal_call": {
        "description": "Execute a file from a pack with configurable runtime "
                       "(python/binary/command). Supports stdio_json protocol. "
                       "Optional Docker isolation.",
        "permission_id": "kernel:universal_call",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "exec", "universal"],
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_pack": {"type": "string", "description": "Pack ID that owns the target file"},
                "file": {"type": "string", "description": "Relative path within the pack"},
                "runtime": {"type": "string", "default": "python", "enum": ["python", "binary", "command"]},
                "protocol": {"type": "string", "default": "stdio_json"},
                "input": {"type": "object", "default": {}},
                "timeout_seconds": {"type": "number", "default": 30, "maximum": 120},
                "docker_image": {"type": "string", "description": "Optional Docker image override"}
            },
            "required": ["owner_pack", "file"]
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "_kernel_step_status": {"type": "string", "enum": ["success", "failed"]},
                "_kernel_step_meta": {"type": "object"},
                "result": {}
            },
            "required": ["_kernel_step_status"]
        },
    },

    # --- modifier ---
    "kernel:modifier.load_all": {
        "description": "Load all modifier files for flow modification",
        "permission_id": "kernel:modifier.load_all",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "modifier", "flow"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:modifier.apply": {
        "description": "Apply modifiers to a specific flow and update InterfaceRegistry",
        "permission_id": "kernel:modifier.apply",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "modifier", "flow"],
        "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- network ---
    "kernel:network.grant": {
        "description": "Grant network access to a pack with allowed domains and ports",
        "permission_id": "kernel:network.grant",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}, "allowed_domains": {"type": "array", "items": {"type": "string"}, "default": []}, "allowed_ports": {"type": "array", "items": {"type": "integer"}, "default": []}, "granted_by": {"type": "string", "default": "kernel"}, "notes": {"type": "string", "default": ""}}, "required": ["pack_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "grant": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:network.revoke": {
        "description": "Revoke network access for a pack",
        "permission_id": "kernel:network.revoke",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}, "reason": {"type": "string", "default": ""}}, "required": ["pack_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:network.check": {
        "description": "Check if a pack has network access to a specific domain and port",
        "permission_id": "kernel:network.check",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}, "domain": {"type": "string"}, "port": {"type": "integer"}}, "required": ["pack_id", "domain", "port"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "result": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:network.list": {
        "description": "List all network grants and disabled packs",
        "permission_id": "kernel:network.list",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "grants": {"type": "object"}, "disabled_packs": {"type": "array"}}, "required": ["_kernel_step_status"]},
    },

    # --- egress_proxy ---
    "kernel:egress_proxy.start": {
        "description": "Start the HTTP egress proxy server",
        "permission_id": "kernel:egress_proxy.start",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress", "proxy"],
        "input_schema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:egress_proxy.stop": {
        "description": "Stop the HTTP egress proxy server",
        "permission_id": "kernel:egress_proxy.stop",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:egress_proxy.status": {
        "description": "Get the HTTP egress proxy server status",
        "permission_id": "kernel:egress_proxy.status",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "egress", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- lib ---
    "kernel:lib.process_all": {
        "description": "Process all pack lib scripts (install/update)",
        "permission_id": "kernel:lib.process_all",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {"type": "object", "properties": {"packs_dir": {"type": "string", "default": "ecosystem"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "results": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:lib.check": {
        "description": "Check if a pack needs lib install or update",
        "permission_id": "kernel:lib.check",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}, "pack_dir": {"type": "string"}}, "required": ["pack_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:lib.execute": {
        "description": "Manually execute a pack lib script (install or update)",
        "permission_id": "kernel:lib.execute",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}, "lib_type": {"type": "string", "enum": ["install", "update"]}, "pack_dir": {"type": "string"}}, "required": ["pack_id", "lib_type"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "output": {}}, "required": ["_kernel_step_status"]},
    },
    "kernel:lib.clear_record": {
        "description": "Clear lib execution record for a pack or all packs",
        "permission_id": "kernel:lib.clear_record",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:lib.list_records": {
        "description": "List lib execution records for all packs",
        "permission_id": "kernel:lib.list_records",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "lib"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "records": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- audit ---
    "kernel:audit.query": {
        "description": "Query audit logs with filters",
        "permission_id": "kernel:audit.query",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {"type": "object", "properties": {"category": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "pack_id": {"type": "string"}, "flow_id": {"type": "string"}, "success_only": {"type": "boolean"}, "limit": {"type": "integer", "default": 100}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "results": {"type": "array"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:audit.summary": {
        "description": "Get audit log summary",
        "permission_id": "kernel:audit.summary",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {"type": "object", "properties": {"category": {"type": "string"}, "date": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "summary": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:audit.flush": {
        "description": "Flush audit log buffers to persistent storage",
        "permission_id": "kernel:audit.flush",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "audit"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- vocab ---
    "kernel:vocab.list_groups": {
        "description": "List all vocabulary groups",
        "permission_id": "kernel:vocab.list_groups",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "groups": {"type": "array"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:vocab.list_converters": {
        "description": "List all vocabulary converters",
        "permission_id": "kernel:vocab.list_converters",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "converters": {"type": "array"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:vocab.summary": {
        "description": "Get vocabulary registry summary",
        "permission_id": "kernel:vocab.summary",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "summary": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:vocab.convert": {
        "description": "Convert a value using vocabulary converter",
        "permission_id": "kernel:vocab.convert",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "vocab"],
        "input_schema": {"type": "object", "properties": {"term": {"type": "string"}, "from_format": {"type": "string"}, "to_format": {"type": "string"}}, "required": ["term"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "result": {}}, "required": ["_kernel_step_status"]},
    },

    # --- shared_dict ---
    "kernel:shared_dict.resolve": {
        "description": "Resolve a key via shared dictionary chain",
        "permission_id": "kernel:shared_dict.resolve",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}, "key": {"type": "string"}}, "required": ["namespace", "key"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "result": {}}, "required": ["_kernel_step_status"]},
    },
    "kernel:shared_dict.propose": {
        "description": "Propose a new shared dictionary entry",
        "permission_id": "kernel:shared_dict.propose",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}, "key": {"type": "string"}, "value": {"type": "string"}, "pack_id": {"type": "string"}}, "required": ["namespace", "key", "value"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:shared_dict.explain": {
        "description": "Explain the resolution chain for a shared dictionary key",
        "permission_id": "kernel:shared_dict.explain",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}, "key": {"type": "string"}}, "required": ["namespace", "key"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "explanation": {}}, "required": ["_kernel_step_status"]},
    },
    "kernel:shared_dict.list": {
        "description": "List all shared dictionary entries",
        "permission_id": "kernel:shared_dict.list",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "entries": {"type": "array"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:shared_dict.remove": {
        "description": "Remove a shared dictionary entry",
        "permission_id": "kernel:shared_dict.remove",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "shared_dict"],
        "input_schema": {"type": "object", "properties": {"namespace": {"type": "string"}, "key": {"type": "string"}}, "required": ["namespace", "key"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- uds_proxy ---
    "kernel:uds_proxy.init": {
        "description": "Initialize the UDS egress proxy manager",
        "permission_id": "kernel:uds_proxy.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "uds", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:uds_proxy.ensure_socket": {
        "description": "Ensure a UDS socket exists for a pack",
        "permission_id": "kernel:uds_proxy.ensure_socket",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "uds", "proxy"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}}, "required": ["pack_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:uds_proxy.stop": {
        "description": "Stop a specific UDS proxy for a pack",
        "permission_id": "kernel:uds_proxy.stop",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "uds", "proxy"],
        "input_schema": {"type": "object", "properties": {"pack_id": {"type": "string"}}, "required": ["pack_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:uds_proxy.stop_all": {
        "description": "Stop all UDS proxies",
        "permission_id": "kernel:uds_proxy.stop_all",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "uds", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:uds_proxy.status": {
        "description": "Get UDS proxy status for all packs",
        "permission_id": "kernel:uds_proxy.status",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "network", "uds", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- capability_proxy ---
    "kernel:capability_proxy.init": {
        "description": "Initialize the capability proxy server",
        "permission_id": "kernel:capability_proxy.init",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:capability_proxy.status": {
        "description": "Get capability proxy server status",
        "permission_id": "kernel:capability_proxy.status",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:capability_proxy.stop_all": {
        "description": "Stop all capability proxy servers",
        "permission_id": "kernel:capability_proxy.stop_all",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "proxy"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- capability grant (G-1) ---
    "kernel:capability.grant": {
        "description": "Grant a capability permission to a principal",
        "permission_id": "kernel:capability.grant",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "security"],
        "input_schema": {"type": "object", "properties": {"principal_id": {"type": "string"}, "permission_id": {"type": "string"}, "config": {"type": "object", "default": {}}}, "required": ["principal_id", "permission_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:capability.revoke": {
        "description": "Revoke a capability permission from a principal",
        "permission_id": "kernel:capability.revoke",
        "risk": "high",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "security"],
        "input_schema": {"type": "object", "properties": {"principal_id": {"type": "string"}, "permission_id": {"type": "string"}}, "required": ["principal_id", "permission_id"]},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },
    "kernel:capability.list": {
        "description": "List capability grants for a principal or all principals",
        "permission_id": "kernel:capability.list",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "capability", "security"],
        "input_schema": {"type": "object", "properties": {"principal_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}, "grants": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- pending export (G-2) ---
    "kernel:pending.export": {
        "description": "Export pending approval information to output directory",
        "permission_id": "kernel:pending.export",
        "risk": "low",
        "requires": [],
        "tags": ["kernel", "runtime", "approval", "export"],
        "input_schema": {"type": "object", "properties": {"output_dir": {"type": "string", "default": "user_data/pending"}}},
        "output_schema": {"type": "object", "properties": {"_kernel_step_status": {"type": "string", "enum": ["success", "failed"]}, "_kernel_step_meta": {"type": "object"}}, "required": ["_kernel_step_status"]},
    },

    # --- Phase B-1: kernel function registration ---
    "kernel:register_kernel_functions": {
        "description": "Register all kernel handler manifests into FunctionRegistry",
        "permission_id": "kernel:register_kernel_functions",
        "risk": "medium",
        "requires": [],
        "tags": ["kernel", "system", "init", "function_registry"],
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
                        "registered_count": {"type": "integer"},
                        "error": {"type": "string"},
                    },
                },
            },
            "required": ["_kernel_step_status"],
        },
    },
}

# Phase B-1: _EXPECTED_HANDLER_KEYS derived from _KERNEL_HANDLER_MANIFESTS (原則 D)
_EXPECTED_HANDLER_KEYS = frozenset(_KERNEL_HANDLER_MANIFESTS.keys())

# =====================================================================
# Phase B-1: _EXPECTED_HANDLER_KEYS — 後方互換（_KERNEL_HANDLER_MANIFESTS から導出）
# =====================================================================
_EXPECTED_HANDLER_KEYS: frozenset = frozenset(_KERNEL_HANDLER_MANIFESTS.keys())


# =====================================================================
# Phase B-1: _register_kernel_functions
# FunctionRegistry にカーネルハンドラを一括登録する。
# =====================================================================

def _register_kernel_functions(function_registry) -> int:
    """
    _KERNEL_HANDLER_MANIFESTS の全エントリを FunctionRegistry に登録する。

    Phase A で追加される register_kernel_function() を使用する。
    pack_id="kernel", calling_convention="kernel", is_builtin=True が固定設定される。

    Args:
        function_registry: FunctionRegistry インスタンス

    Returns:
        登録された function の数
    """
    if function_registry is None:
        _logger.warning("_register_kernel_functions: function_registry is None, skipping")
        return 0

    # Phase A の register_kernel_function() が存在するか確認
    register_fn = getattr(function_registry, "register_kernel_function", None)

    registered = 0
    for key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
        try:
            if register_fn is not None:
                # Phase A パス: register_kernel_function() を使用
                register_fn(key, manifest)
            else:
                # フォールバック: 汎用 register() を直接使用
                # handler_key "kernel:xxx.yyy" → function_id = "xxx.yyy"
                parts = key.split(":", 1)
                function_id = parts[1] if len(parts) == 2 else key

                from .function_registry import FunctionEntry
                entry = FunctionEntry(
                    function_id=function_id,
                    pack_id="kernel",
                    description=manifest.get("description", ""),
                    requires=manifest.get("requires", []),
                    tags=manifest.get("tags", []),
                    input_schema=manifest.get("input_schema", {}),
                    output_schema=manifest.get("output_schema", {}),
                    risk=manifest.get("risk"),
                    entrypoint=None,
                    vocab_aliases=[manifest["permission_id"]] if manifest.get("permission_id") else None,
                )
                entry.host_execution = False
                function_registry.register(entry)

            registered += 1
        except Exception as exc:
            _logger.warning(
                "_register_kernel_functions: failed to register '%s': %s",
                key, exc,
            )

    _logger.info(
        "Kernel functions registered: %d / %d",
        registered, len(_KERNEL_HANDLER_MANIFESTS),
    )
    return registered


# =====================================================================
# Kernel クラス（Mixin 合成）
# =====================================================================

class Kernel(
    KernelRuntimeHandlersMixin,
    KernelSystemHandlersMixin,
    KernelFlowExecutionMixin,
    KernelCore,
):
    """
    合成 Kernel クラス

    MRO: Kernel → RuntimeHandlers → SystemHandlers → FlowExecution → KernelCore
    """

    def _init_kernel_handlers(self) -> None:
        """
        カーネルハンドラを初期化し、_kernel_handlers に登録する。

        _KERNEL_HANDLER_MANIFESTS を権威ソースとし、
        実際のハンドラ関数は Mixin の _register_*_handlers() から取得する。
        """
        system = self._register_system_handlers()
        runtime = self._register_runtime_handlers()

        self._kernel_handlers.update(system)
        self._kernel_handlers.update(runtime)

        # 登録漏れ検知
        registered_keys = frozenset(self._kernel_handlers.keys())
        expected_keys = frozenset(_KERNEL_HANDLER_MANIFESTS.keys())

        missing = expected_keys - registered_keys
        if missing:
            _logger.error(
                "Kernel handler registration incomplete! Missing handlers: %s",
                sorted(missing),
            )

        extra = registered_keys - expected_keys
        if extra:
            _logger.warning(
                "Kernel handlers registered but not in manifests: %s",
                sorted(extra),
            )


    def _vocab_normalize_output(self, output: dict, step: dict, ctx: dict) -> dict:
        """vocab_normalize の実装。VocabRegistry 経由でキー正規化。"""
        try:
            from .vocab_registry import get_vocab_registry
            vr = get_vocab_registry()
            if vr is None:
                return output
            normalized = {}
            for k, v in output.items():
                try:
                    new_key = vr.resolve(k, to_preferred=True)
                    normalized[new_key] = v
                except Exception:
                    normalized[k] = v
            return normalized
        except Exception:
            return output
