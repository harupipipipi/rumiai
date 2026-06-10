"""Regression tests for flow function-step principal hardening."""
from __future__ import annotations

import time

from rumi_ai_1_10.core_runtime.capability_executor import CapabilityExecutor


class _KernelRecorder:
    def __init__(self):
        self.calls = []

    def execute_flow_sync(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def test_capability_flow_run_strips_spoofed_principal_and_sets_trusted_principal():
    executor = object.__new__(CapabilityExecutor)
    kernel = _KernelRecorder()
    executor._kernel = kernel

    response = executor._execute_flow_run(
        principal_id="actual_pack",
        permission_id="flow.run",
        grant_config={"allowed_flow_ids": ["demo.flow"]},
        args={
            "flow_id": "demo.flow",
            "inputs": {
                "_principal_id": "victim_pack",
                "_flow_run_principal_id": "victim_pack",
                "payload": "kept",
            },
        },
        timeout_seconds=30,
        request_id="req-1",
        start_time=time.time(),
    )

    assert response.success is True
    assert len(kernel.calls) == 1
    call = kernel.calls[0]
    assert call["context"] == {"payload": "kept"}
    assert call["trusted_context"]["_flow_run_principal_id"] == "actual_pack"
    assert call["trusted_context"]["_flow_run_request_id"] == "req-1"
