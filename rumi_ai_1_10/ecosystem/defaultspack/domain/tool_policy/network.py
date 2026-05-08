from __future__ import annotations


def network_allowed(policy: dict, target: str = "") -> bool:
    if policy.get("allow_network") is True:
        allowlist = policy.get("network_allowlist")
        if not allowlist:
            return True
        return any(str(item) in target for item in allowlist)
    return False
