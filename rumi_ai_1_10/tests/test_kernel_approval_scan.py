from __future__ import annotations

from types import SimpleNamespace

from core_runtime.kernel_handlers_system import KernelSystemHandlersMixin


class _Diagnostics:
    def record_step(self, **kwargs):
        self.last = kwargs


class _Status:
    def __init__(self, value: str):
        self.value = value


class _ApprovalManager:
    def scan_packs(self):
        return ["defaultspack"]

    def get_status(self, pack_id):
        return _Status("modified")

    def auto_approve_if_dev(self, pack_id):
        return True

    def verify_hash(self, pack_id):
        raise AssertionError("verify_hash should not run after dev auto approval")

    def mark_modified(self, pack_id):
        raise AssertionError("mark_modified should not run after dev auto approval")


class _Kernel(KernelSystemHandlersMixin):
    def __init__(self):
        self.diagnostics = _Diagnostics()


def test_approval_scan_treats_dev_auto_approved_packs_as_approved(monkeypatch):
    import core_runtime.kernel_handlers_system as mod

    monkeypatch.setattr(mod, "get_approval_manager", lambda: _ApprovalManager())

    kernel = _Kernel()
    ctx = {}

    result = kernel._h_approval_scan({}, ctx)

    assert result["_kernel_step_status"] == "success"
    assert ctx["_packs_approved"] == ["defaultspack"]
    assert ctx["_packs_modified"] == []
    assert ctx["_packs_pending"] == []
