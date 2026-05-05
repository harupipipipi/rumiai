from __future__ import annotations

from blocks._common import ok


DEFAULT_POLICY = {
    "server_side_only": True,
    "deny_client_approved": True,
    "high_risk_requires_approval": True,
    "approve_once": True,
    "approve_for_session": True,
}


def run(input_data, context=None):
    return ok({**DEFAULT_POLICY, **dict((input_data or {}).get("policy") or {})})
