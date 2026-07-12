from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core_runtime.kernel_flow_execution import KernelFlowExecutionMixin


class _FakeDiagnostics:
    def __init__(self) -> None:
        self.records = []

    def record_step(self, **kwargs) -> None:
        self.records.append(kwargs)

    def as_dict(self):
        return {"records": list(self.records)}


class _FakeKernel(KernelFlowExecutionMixin):
    def __init__(self) -> None:
        self._flow = {
            "defaults": {"fail_soft": True, "on_missing_handler": "skip"},
            "pipelines": {
                "startup": [
                    {"id": "setup_check", "run": {"handler": "kernel:noop", "args": {}}},
                    {"id": "api_init", "run": {"handler": "kernel:noop", "args": {}}},
                    {"id": "flow_load_all", "run": {"handler": "kernel:noop", "args": {}}},
                    {"id": "emit_ready", "run": {"handler": "kernel:noop", "args": {}}},
                ]
            },
        }
        self.diagnostics = _FakeDiagnostics()
        self.executed = []
        self._startup_ctx = None
        self._startup_steps = None
        self._startup_next_index = 0
        self._startup_executed_ids = set()
        self._startup_fail_soft_default = True

    def load_user_flows(self, path=None):
        return []

    def load_flow(self, path=None):
        return self._flow

    def _build_kernel_context(self):
        return {"shared": []}

    def _execute_flow_step(self, step, phase="startup", ctx=None):
        ctx["shared"].append(step["id"])
        self.executed.append(step["id"])
        return False


def test_run_startup_until_keeps_remaining_steps_for_background_finish():
    kernel = _FakeKernel()

    kernel.run_startup_until("api_init")

    assert kernel.executed == ["setup_check", "api_init"]
    assert kernel._startup_ctx is not None
    assert kernel._startup_next_index == 2

    kernel.run_startup_remaining()

    assert kernel.executed == ["setup_check", "api_init", "flow_load_all", "emit_ready"]
    assert kernel._startup_ctx is None
    assert kernel._startup_next_index == 0


def test_run_startup_executes_everything_when_not_split():
    kernel = _FakeKernel()

    kernel.run_startup()

    assert kernel.executed == ["setup_check", "api_init", "flow_load_all", "emit_ready"]
    assert kernel._startup_ctx is None
