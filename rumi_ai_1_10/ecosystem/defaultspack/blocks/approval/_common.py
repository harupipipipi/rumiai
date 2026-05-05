from __future__ import annotations

from blocks._common import error, ok
from domain.approval.store import ApprovalStore


def approval_error(exc: Exception):
    return error(str(exc), code="APPROVAL_FAILED")


__all__ = ["ApprovalStore", "approval_error", "ok"]
