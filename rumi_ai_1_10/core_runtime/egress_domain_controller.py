"""
egress_domain_controller.py - Pack別ドメイン制御

ecosystem.json ベースのドメインホワイトリスト/ブラックリスト。
egress_proxy.py から分離 (W13-T047)。
W12-T046 で追加。
"""
from __future__ import annotations

import fnmatch
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Tuple


# ============================================================
# ドメイン制御定数
# ============================================================

_ECOSYSTEM_DIR = os.environ.get("RUMI_ECOSYSTEM_DIR", "packs")


# ============================================================
# DomainController
# ============================================================

class DomainController:
    """
    Pack別のドメインホワイトリスト/ブラックリスト制御。

    ecosystem.json の egress_allow_domains / egress_deny_domains を参照。
    deny が優先（deny にマッチ → allow に関係なくブロック）。
    ワイルドカードパターン対応（*.example.com）。
    初回アクセス時にキャッシュ。
    """

    def __init__(self, ecosystem_dir: str = None):
        self._ecosystem_dir = ecosystem_dir or _ECOSYSTEM_DIR
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _load_pack_config(self, pack_id: str) -> Dict[str, Any]:
        """Pack の ecosystem.json からドメイン制御設定を読み込む"""
        try:
            eco_path = Path(self._ecosystem_dir) / pack_id / "ecosystem.json"
            if not eco_path.exists():
                return {"allow": [], "deny": []}

            with open(eco_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return {
                "allow": data.get("egress_allow_domains", []),
                "deny": data.get("egress_deny_domains", []),
            }
        except Exception:
            return {"allow": [], "deny": []}

    def _get_pack_config(self, pack_id: str) -> Dict[str, Any]:
        """キャッシュ付きで設定を取得"""
        with self._lock:
            if pack_id not in self._cache:
                self._cache[pack_id] = self._load_pack_config(pack_id)
            return self._cache[pack_id]

    def _match_domain(self, domain: str, patterns: list) -> bool:
        """ドメインがパターンリストにマッチするか判定"""
        domain_lower = domain.lower()
        for pattern in patterns:
            pattern_lower = pattern.lower()
            if domain_lower == pattern_lower:
                return True
            if pattern_lower == "*":
                return True
            if pattern_lower.startswith("*."):
                base = pattern_lower[2:]
                if domain_lower == base:
                    return True
                if domain_lower.endswith("." + base):
                    return True
            if fnmatch.fnmatch(domain_lower, pattern_lower):
                return True
        return False

    def check_domain(self, pack_id: str, domain: str) -> Tuple[bool, str]:
        """
        ドメイン制御チェック。

        Returns:
            (allowed, reason)

        ルール:
        - deny リストにマッチ → ブロック（allow に関係なく）
        - allow リストが空 → 制限なし（ドメイン制御未設定扱い）
        - allow リストが非空 → allow にマッチしなければブロック
        """
        config = self._get_pack_config(pack_id)
        deny_list = config.get("deny", [])
        allow_list = config.get("allow", [])

        if deny_list and self._match_domain(domain, deny_list):
            return False, f"Domain '{domain}' is in egress deny list for pack '{pack_id}'"

        if not allow_list:
            return True, ""

        if self._match_domain(domain, allow_list):
            return True, ""

        return False, f"Domain '{domain}' is not in egress allow list for pack '{pack_id}'"

    def invalidate_cache(self, pack_id: str = None) -> None:
        """キャッシュを無効化（設定変更時に呼び出し）"""
        with self._lock:
            if pack_id:
                self._cache.pop(pack_id, None)
            else:
                self._cache.clear()
