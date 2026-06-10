from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import CapabilityExecutor, FLOW_RUN_PERMISSION_ID


def _make_executor():
    executor = CapabilityExecutor()
    executor._kernel = MagicMock()
    executor._kernel.execute_flow_sync.return_value = {"status": "done"}
    return executor


def _run_flow(executor, grant_config, inputs=None, flow_id="allowed.flow"):
    return executor._execute_flow_run(
        principal_id="caller_pack",
        permission_id=FLOW_RUN_PERMISSION_ID,
        grant_config=grant_config,
        args={"flow_id": flow_id, "inputs": inputs or {}},
        timeout_seconds=5,
        request_id="req-1",
        start_time=time.time(),
    )


def test_flow_run_requires_explicit_allowed_flow_ids():
    executor = _make_executor()

    response = _run_flow(executor, grant_config={})

    assert response.success is False
    assert response.error_type == "grant_denied"
    executor._kernel.execute_flow_sync.assert_not_called()


def test_flow_run_allows_explicit_whitelisted_flow():
    executor = _make_executor()

    response = _run_flow(executor, grant_config={"allowed_flow_ids": ["allowed.flow"]})

    assert response.success is True
    executor._kernel.execute_flow_sync.assert_called_once()


def test_flow_run_internal_context_cannot_be_overwritten_by_inputs():
    executor = _make_executor()

    response = _run_flow(
        executor,
        grant_config={"allowed_flow_ids": "allowed.flow"},
        inputs={
            "user_value": 42,
            "_flow_run_principal_id": "spoofed_pack",
            "_flow_run_request_id": "spoofed-request",
            "_flow_call_stack": [],
        },
    )

    assert response.success is True
    context = executor._kernel.execute_flow_sync.call_args.kwargs["context"]
    trusted_context = executor._kernel.execute_flow_sync.call_args.kwargs["trusted_context"]
    assert context["user_value"] == 42
    assert "_flow_run_principal_id" not in context
    assert "_flow_run_request_id" not in context
    assert "_flow_call_stack" not in context
    assert trusted_context["_flow_run_principal_id"] == "caller_pack"
    assert trusted_context["_flow_run_request_id"] == "req-1"
    assert trusted_context["_flow_call_stack"] == ["allowed.flow"]
