"""Network Grant ハンドラ Mixin"""
from __future__ import annotations

from .._helpers import _log_internal_error, _SAFE_ERROR_MSG


class NetworkHandlersMixin:
    """ネットワークアクセス許可 (B-2) のハンドラ"""

    def _network_grant(self, pack_id: str, allowed_domains: list, allowed_ports: list,
                       granted_by: str = "api_user", notes: str = "") -> dict:
        try:
            from ...network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            grant = ngm.grant_network_access(
                pack_id=pack_id,
                allowed_domains=allowed_domains,
                allowed_ports=allowed_ports,
                granted_by=granted_by,
                notes=notes,
            )
            return {"success": True, "pack_id": pack_id, "grant": grant.to_dict()}
        except Exception as e:
            _log_internal_error("network_grant", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _network_revoke(self, pack_id: str, reason: str = "") -> dict:
        try:
            from ...network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            success = ngm.revoke_network_access(pack_id=pack_id, reason=reason)
            return {"success": success, "pack_id": pack_id, "revoked": success}
        except Exception as e:
            _log_internal_error("network_revoke", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _network_check(self, pack_id: str, domain: str, port: int) -> dict:
        try:
            from ...network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            result = ngm.check_access(pack_id, domain, port)
            return {
                "allowed": result.allowed,
                "reason": result.reason,
                "pack_id": result.pack_id,
                "domain": result.domain,
                "port": result.port,
            }
        except Exception as e:
            _log_internal_error("network_check", e)
            return {"allowed": False, "error": _SAFE_ERROR_MSG}

    def _network_list(self) -> dict:
        try:
            from ...network_grant_manager import get_network_grant_manager
            ngm = get_network_grant_manager()
            grants = ngm.get_all_grants()
            disabled = ngm.get_disabled_packs()
            return {
                "grants": {k: v.to_dict() for k, v in grants.items()},
                "grant_count": len(grants),
                "disabled_packs": list(disabled),
                "disabled_count": len(disabled),
            }
        except Exception as e:
            _log_internal_error("network_list", e)
            return {"grants": {}, "error": _SAFE_ERROR_MSG}
