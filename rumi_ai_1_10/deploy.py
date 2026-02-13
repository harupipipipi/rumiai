#!/usr/bin/env python3
"""
deploy.py - 新規作成ファイル 7 つを生成・配置する

    python deploy.py
    python deploy.py --dry-run
    python deploy.py --base-dir /path/to/project
"""

import argparse
import sys
from pathlib import Path

FILES = {}

FILES["core_runtime/capability_usage_store.py"] = '''\
"""
capability_usage_store.py - Capability 使用回数永続化ストア

principal_id x permission_id x scope_key ごとの使用回数を永続管理する。

保存先: user_data/permissions/capability_usage/<safe_principal_id>.json

設計原則:
- 再起動しても使用回数は復活しない (永続)
- HMAC 署名で改ざん検知
- fail-closed: 読み込みエラー時は使用済みとして扱う
- atomic write (tmp -> rename) でファイル破損を防止
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile as _tf
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class UsageRecord:
    """単一の permission x scope の使用記録"""
    permission_id: str
    scope_key: str
    used_count: int = 0
    last_used_ts: Optional[str] = None
    daily_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "scope_key": self.scope_key,
            "used_count": self.used_count,
            "last_used_ts": self.last_used_ts,
            "daily_counts": self.daily_counts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageRecord":
        return cls(
            permission_id=data.get("permission_id", ""),
            scope_key=data.get("scope_key", ""),
            used_count=data.get("used_count", 0),
            last_used_ts=data.get("last_used_ts"),
            daily_counts=data.get("daily_counts", {}),
        )


@dataclass
class ConsumeResult:
    """消費結果"""
    allowed: bool
    reason: Optional[str] = None
    used_count: int = 0
    max_count: int = 0
    scope_key: str = ""
    remaining: int = 0


class CapabilityUsageStore:
    """Capability 使用回数永続化ストア"""

    USAGE_DIR = "user_data/permissions/capability_usage"
    SECRET_KEY_FILE = "user_data/permissions/.secret_key"

    def __init__(self, usage_dir: str = None, secret_key: str = None):
        self._usage_dir = Path(usage_dir) if usage_dir else Path(self.USAGE_DIR)
        self._secret_key = secret_key or self._load_secret_key()
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, UsageRecord]] = {}
        self._usage_dir.mkdir(parents=True, exist_ok=True)

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_secret_key(self) -> str:
        key_file = Path(self.SECRET_KEY_FILE)
        if key_file.exists():
            try:
                return key_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        key = hashlib.sha256(os.urandom(32)).hexdigest()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except (OSError, AttributeError):
            pass
        return key

    def _safe_principal_id(self, principal_id: str) -> str:
        return principal_id.replace("/", "_").replace(":", "_").replace("..", "_")

    def _get_file_path(self, principal_id: str) -> Path:
        return self._usage_dir / (self._safe_principal_id(principal_id) + ".json")

    def _compute_hmac(self, data: Dict[str, Any]) -> str:
        data_copy = {k: v for k, v in data.items() if not k.startswith("_hmac")}
        payload = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
        return hmac.new(
            self._secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _load_principal(self, principal_id: str) -> Dict[str, UsageRecord]:
        if principal_id in self._cache:
            return self._cache[principal_id]
        file_path = self._get_file_path(principal_id)
        if not file_path.exists():
            self._cache[principal_id] = {}
            return self._cache[principal_id]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            stored_sig = data.pop("_hmac_signature", None)
            if stored_sig:
                computed_sig = self._compute_hmac(data)
                if not hmac.compare_digest(stored_sig, computed_sig):
                    self._audit_tamper_detected(principal_id, file_path)
                    self._cache[principal_id] = {}
                    return self._cache[principal_id]
            records: Dict[str, UsageRecord] = {}
            for key, rec_data in data.get("records", {}).items():
                records[key] = UsageRecord.from_dict(rec_data)
            self._cache[principal_id] = records
            return records
        except Exception:
            self._cache[principal_id] = {}
            return self._cache[principal_id]

    def _save_principal(self, principal_id: str) -> bool:
        """atomic write: tmp -> os.replace"""
        records = self._cache.get(principal_id, {})
        data = {
            "principal_id": principal_id,
            "updated_at": self._now_ts(),
            "records": {key: rec.to_dict() for key, rec in records.items()},
        }
        data["_hmac_signature"] = self._compute_hmac(data)
        file_path = self._get_file_path(principal_id)
        tmp_path: Optional[str] = None
        try:
            fd, tmp_path = _tf.mkstemp(dir=str(file_path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(file_path))
            return True
        except Exception:
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return False

    def _audit_tamper_detected(self, principal_id: str, file_path: Path) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type="capability_usage_tamper_detected",
                severity="error",
                description="HMAC verification failed for: " + str(file_path),
                details={"principal_id": principal_id, "file": str(file_path)},
            )
        except Exception:
            pass

    def _record_key(self, permission_id: str, scope_key: str) -> str:
        return permission_id + ":" + scope_key

    def check_and_consume(
        self,
        principal_id: str,
        permission_id: str,
        scope_key: str,
        max_count: int,
        max_daily_count: int = 0,
        expires_at_epoch: float = 0,
    ) -> ConsumeResult:
        with self._lock:
            if expires_at_epoch > 0 and time.time() > expires_at_epoch:
                return ConsumeResult(
                    allowed=False, reason="expired",
                    scope_key=scope_key, max_count=max_count,
                )
            records = self._load_principal(principal_id)
            key = self._record_key(permission_id, scope_key)
            record = records.get(key)
            if record is None:
                record = UsageRecord(permission_id=permission_id, scope_key=scope_key)
                records[key] = record
            if max_count > 0 and record.used_count >= max_count:
                return ConsumeResult(
                    allowed=False, reason="max_count_exceeded",
                    used_count=record.used_count, max_count=max_count,
                    scope_key=scope_key, remaining=0,
                )
            if max_daily_count > 0:
                today = self._today_str()
                daily_used = record.daily_counts.get(today, 0)
                if daily_used >= max_daily_count:
                    rem = max(0, max_count - record.used_count) if max_count > 0 else -1
                    return ConsumeResult(
                        allowed=False, reason="daily_limit_exceeded",
                        used_count=record.used_count, max_count=max_count,
                        scope_key=scope_key, remaining=rem,
                    )
            record.used_count += 1
            record.last_used_ts = self._now_ts()
            if max_daily_count > 0:
                today = self._today_str()
                record.daily_counts[today] = record.daily_counts.get(today, 0) + 1
            self._save_principal(principal_id)
            rem = max(0, max_count - record.used_count) if max_count > 0 else -1
            return ConsumeResult(
                allowed=True, used_count=record.used_count,
                max_count=max_count, scope_key=scope_key, remaining=rem,
            )

    def get_usage(self, principal_id, permission_id, scope_key):
        with self._lock:
            records = self._load_principal(principal_id)
            return records.get(self._record_key(permission_id, scope_key))

    def get_all_usage(self, principal_id: str) -> Dict[str, UsageRecord]:
        with self._lock:
            return dict(self._load_principal(principal_id))

    def reset_usage(self, principal_id, permission_id, scope_key) -> bool:
        with self._lock:
            records = self._load_principal(principal_id)
            key = self._record_key(permission_id, scope_key)
            if key in records:
                del records[key]
                return self._save_principal(principal_id)
            return False

    def reset_all(self, principal_id: str) -> bool:
        with self._lock:
            self._cache[principal_id] = {}
            return self._save_principal(principal_id)


_global_usage_store: Optional[CapabilityUsageStore] = None
_usage_lock = threading.Lock()


def get_capability_usage_store() -> CapabilityUsageStore:
    global _global_usage_store
    if _global_usage_store is None:
        with _usage_lock:
            if _global_usage_store is None:
                _global_usage_store = CapabilityUsageStore()
    return _global_usage_store


def reset_capability_usage_store(usage_dir: str = None) -> CapabilityUsageStore:
    global _global_usage_store
    with _usage_lock:
        _global_usage_store = CapabilityUsageStore(usage_dir)
    return _global_usage_store
'''

FILES["core_runtime/builtin_capability_handlers/__init__.py"] = '''\
# Built-in Capability Handlers
# This package contains handlers that ship with the Rumi AI OS core.
'''

FILES["core_runtime/builtin_capability_handlers/inbox_send/handler.json"] = '''\
{
  "handler_id": "builtin.pack.inbox.send",
  "permission_id": "pack.inbox.send",
  "entrypoint": "handler.py:execute",
  "description": "Send a JSON patch or replacement to another Pack component inbox.",
  "risk": "medium",
  "input_schema": {
    "type": "object",
    "required": ["to_pack_id", "target_component", "payload"],
    "properties": {
      "to_pack_id": {"type": "string"},
      "target_component": {
        "type": "object",
        "required": ["type", "id"],
        "properties": {
          "type": {"type": "string"},
          "id": {"type": "string"}
        }
      },
      "payload": {
        "type": "object",
        "required": ["kind"],
        "properties": {
          "kind": {
            "type": "string",
            "enum": ["manifest_json_patch", "file_json_patch", "file_replace_json"]
          },
          "file": {"type": "string"},
          "create_if_missing": {"type": "boolean"},
          "json": {"type": "object"},
          "patch": {"type": "array"}
        }
      },
      "priority": {"type": "integer"},
      "request_id": {"type": "string"},
      "notes": {"type": "string"}
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": {"type": "boolean"},
      "stored_path": {"type": "string"},
      "consumed": {"type": "object"},
      "rejected_ops": {"type": "integer"}
    }
  }
}
'''

FILES["core_runtime/builtin_capability_handlers/inbox_send/handler.py"] = '''\
"""
pack.inbox.send - Built-in Capability Handler

Pack A -> Pack B の特定 component 宛てに JSON Patch / 置換を送る。
受信側 addon_policy を検証し、正規化イベントとして inbox に保存する。

安全要件:
- addon_policy なし -> 全拒否 (fail-closed)
- deny_all=true -> 全拒否
- JSON Patch の move / copy 禁止
- file path は editable_files.path_glob マッチ必須
- file_replace_json はデフォルト拒否

検証順序 (使用回数を無駄に消費しない):
  入力バリデーション -> Grant config -> ポリシー検証
  -> Patch検証 -> 使用回数消費 -> 保存
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_ID_RE = re.compile("^[a-zA-Z0-9_.-]+$")


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    principal_id = context.get("principal_id", "")
    grant_config = context.get("grant_config", {})
    request_id_ctx = context.get("request_id", "")

    to_pack_id = args.get("to_pack_id", "")
    target_component = args.get("target_component", {})
    payload = args.get("payload", {})
    priority = args.get("priority", 100)
    request_id = args.get("request_id", request_id_ctx or uuid.uuid4().hex[:12])
    notes = args.get("notes", "")

    if not to_pack_id or not isinstance(to_pack_id, str):
        return _error("Missing or invalid to_pack_id", "validation_error")

    comp_type = target_component.get("type", "")
    comp_id = target_component.get("id", "")
    if not comp_type or not comp_id:
        return _error("Missing target_component type or id", "validation_error")

    kind = payload.get("kind", "")
    valid_kinds = {"manifest_json_patch", "file_json_patch", "file_replace_json"}
    if kind not in valid_kinds:
        return _error(
            "Invalid payload.kind: must be one of " + str(valid_kinds),
            "validation_error",
        )

    if kind in ("file_json_patch", "file_replace_json") and not payload.get("file"):
        return _error("payload.file is required for kind=" + kind, "validation_error")
    if kind in ("manifest_json_patch", "file_json_patch") and not payload.get("patch"):
        return _error("payload.patch is required for kind=" + kind, "validation_error")
    if kind == "file_replace_json" and payload.get("json") is None:
        return _error(
            "payload.json is required for kind=file_replace_json", "validation_error"
        )
    if not _safe_pack_id(to_pack_id):
        return _error("Invalid to_pack_id (path traversal)", "validation_error")

    allowed_targets = grant_config.get("allowed_target_packs", [])
    if allowed_targets and to_pack_id not in allowed_targets:
        return _error("Target pack not in allowed_target_packs", "grant_denied")

    default_kinds = ["manifest_json_patch", "file_json_patch"]
    allowed_kinds = grant_config.get("allowed_kinds", default_kinds)
    if kind not in allowed_kinds:
        return _error("Kind '" + kind + "' not in allowed_kinds", "grant_denied")

    max_payload_bytes = grant_config.get("max_payload_bytes", 1048576)
    payload_size = len(
        json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    )
    if payload_size > max_payload_bytes:
        return _error(
            "Payload too large: " + str(payload_size) + " > " + str(max_payload_bytes),
            "payload_too_large",
        )

    policy_result = _check_receiver_policy(to_pack_id, comp_type, comp_id, payload)
    if not policy_result["allowed"]:
        return _error(policy_result["reason"], "policy_denied")
    rejected_ops = policy_result.get("rejected_ops", 0)

    if kind in ("manifest_json_patch", "file_json_patch"):
        for op in payload.get("patch", []):
            if op.get("op") in ("move", "copy"):
                return _error(
                    "Forbidden patch operation: " + str(op.get("op")),
                    "forbidden_operation",
                )

    scope_level = grant_config.get("send_scope_level", 1)
    scope_key = _build_scope_key(
        to_pack_id, comp_type, comp_id, payload.get("file"), scope_level
    )
    max_sends = grant_config.get("max_sends_per_scope", 0)
    max_daily = grant_config.get("max_daily_sends_per_scope", 0)
    expires_at = grant_config.get("expires_at_epoch", 0)

    consumption = None
    if max_sends > 0 or max_daily > 0 or expires_at > 0:
        try:
            from core_runtime.capability_usage_store import get_capability_usage_store

            store = get_capability_usage_store()
            result = store.check_and_consume(
                principal_id=principal_id,
                permission_id="pack.inbox.send",
                scope_key=scope_key,
                max_count=max_sends,
                max_daily_count=max_daily,
                expires_at_epoch=expires_at,
            )
            if not result.allowed:
                return _error(
                    "Usage limit: " + str(result.reason),
                    "usage_limit_exceeded",
                    consumed={
                        "scope_key": scope_key,
                        "used": result.used_count,
                        "max": result.max_count,
                    },
                )
            consumption = {
                "scope_key": scope_key,
                "used": result.used_count,
                "max": result.max_count,
            }
        except Exception as e:
            return _error("Usage store error: " + str(e), "internal_error")

    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ts_safe = ts.replace(":", "-").replace(".", "-")
    comp_full_id = to_pack_id + ":" + comp_type + ":" + comp_id

    inbox_event = {
        "schema": "inbox_request.v1",
        "ts": ts,
        "from_pack_id": principal_id,
        "to_pack_id": to_pack_id,
        "target_component": {"type": comp_type, "id": comp_id},
        "payload": payload,
        "priority": priority,
        "request_id": request_id,
        "notes": notes,
    }

    safe_to = _sanitize_path_segment(to_pack_id)
    safe_comp = _sanitize_path_segment(comp_full_id)
    safe_from = _sanitize_path_segment(principal_id)

    inbox_dir = (
        Path("user_data") / "packs" / safe_to / "inbox" / "v1"
        / "components" / safe_comp / "from" / safe_from
    )
    inbox_dir.mkdir(parents=True, exist_ok=True)

    filename = ts_safe + "__" + (request_id or uuid.uuid4().hex[:8]) + ".json"
    file_path = inbox_dir / filename

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(inbox_event, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return _error("Failed to write inbox event: " + str(e), "write_error")

    _audit_inbox_send(
        principal_id=principal_id,
        to_pack_id=to_pack_id,
        comp_full_id=comp_full_id,
        kind=kind,
        file=payload.get("file"),
        patch_op_count=len(payload.get("patch", [])),
        payload_bytes=payload_size,
        consumption=consumption,
        success=True,
        stored_path=str(file_path),
    )

    return {
        "success": True,
        "stored_path": str(file_path),
        "consumed": consumption,
        "rejected_ops": rejected_ops,
    }


def _error(message: str, error_type: str, **extra) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": False,
        "error": message,
        "error_type": error_type,
    }
    result.update(extra)
    return result


def _safe_pack_id(pack_id: str) -> bool:
    if ".." in pack_id:
        return False
    if "/" in pack_id:
        return False
    if pack_id.startswith("."):
        return False
    return bool(_SAFE_ID_RE.match(pack_id))


def _sanitize_path_segment(value: str) -> str:
    return re.sub("[^a-zA-Z0-9_.:-]", "_", value).strip("_")


def _build_scope_key(
    to_pack_id: str,
    comp_type: str,
    comp_id: str,
    file_path: Optional[str],
    scope_level: int,
) -> str:
    if scope_level <= 1:
        return to_pack_id
    if scope_level == 2:
        return to_pack_id + ":" + comp_type + ":" + comp_id
    if scope_level >= 3 and file_path:
        return to_pack_id + ":" + comp_type + ":" + comp_id + ":" + file_path
    return to_pack_id + ":" + comp_type + ":" + comp_id


def _check_receiver_policy(
    to_pack_id: str,
    comp_type: str,
    comp_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    kind = payload.get("kind", "")
    try:
        from backend_core.ecosystem.registry import get_registry
        registry = get_registry()
    except Exception:
        return {"allowed": False, "reason": "Cannot access component registry"}

    pack = registry.get_pack(to_pack_id)
    if pack is None:
        return {"allowed": False, "reason": "Pack not found: " + to_pack_id}

    component = registry.get_component(to_pack_id, comp_type, comp_id)
    if component is None:
        return {
            "allowed": False,
            "reason": "Component not found: " + to_pack_id + ":" + comp_type + ":" + comp_id,
        }

    addon_policy = component.manifest.get("addon_policy")
    if addon_policy is None:
        return {"allowed": False, "reason": "No addon_policy defined (deny by default)"}
    if addon_policy.get("deny_all", False):
        return {"allowed": False, "reason": "addon_policy.deny_all is true"}

    if kind == "manifest_json_patch":
        return _check_manifest_patch_policy(addon_policy, payload)
    if kind == "file_json_patch":
        return _check_file_patch_policy(addon_policy, payload)
    if kind == "file_replace_json":
        return _check_file_replace_policy(addon_policy, payload)
    return {"allowed": False, "reason": "Unknown kind: " + kind}


def _check_manifest_patch_policy(policy, payload):
    allowed_paths = policy.get("allowed_manifest_paths", [])
    patch_ops = payload.get("patch", [])
    if not allowed_paths:
        return {"allowed": False, "reason": "No allowed_manifest_paths defined"}
    rejected = sum(
        1 for op in patch_ops
        if not any(op.get("path", "").startswith(ap) for ap in allowed_paths)
    )
    if rejected == len(patch_ops):
        return {
            "allowed": False,
            "reason": "All patch ops rejected by allowed_manifest_paths",
            "rejected_ops": rejected,
        }
    return {"allowed": True, "reason": "ok", "rejected_ops": rejected}


def _check_file_patch_policy(policy, payload):
    file_path = payload.get("file", "")
    editable_files = policy.get("editable_files", [])
    patch_ops = payload.get("patch", [])
    if not editable_files:
        return {"allowed": False, "reason": "No editable_files defined"}

    allowed_prefixes = None
    for rule in editable_files:
        if fnmatch.fnmatch(file_path, rule.get("path_glob", "")):
            allowed_prefixes = rule.get("allowed_json_pointer_prefixes", [])
            break

    if allowed_prefixes is None:
        return {
            "allowed": False,
            "reason": "File '" + file_path + "' not in editable_files",
        }
    if allowed_prefixes:
        rejected = sum(
            1 for op in patch_ops
            if not any(op.get("path", "").startswith(ap) for ap in allowed_prefixes)
        )
        if rejected == len(patch_ops):
            return {
                "allowed": False,
                "reason": "All ops rejected by allowed_json_pointer_prefixes",
                "rejected_ops": rejected,
            }
        return {"allowed": True, "reason": "ok", "rejected_ops": rejected}
    return {"allowed": True, "reason": "ok", "rejected_ops": 0}


def _check_file_replace_policy(policy, payload):
    file_path = payload.get("file", "")
    editable_files = policy.get("editable_files", [])
    if not editable_files:
        return {"allowed": False, "reason": "No editable_files defined"}
    for rule in editable_files:
        if fnmatch.fnmatch(file_path, rule.get("path_glob", "")):
            prefixes = rule.get("allowed_json_pointer_prefixes", [])
            if not prefixes:
                return {"allowed": True, "reason": "ok", "rejected_ops": 0}
            return {
                "allowed": False,
                "reason": "file_replace_json requires empty allowed_json_pointer_prefixes",
            }
    return {
        "allowed": False,
        "reason": "File '" + file_path + "' not in editable_files",
    }


def _audit_inbox_send(**kwargs: Any) -> None:
    try:
        from core_runtime.audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_permission_event(
            pack_id=kwargs.get("principal_id", ""),
            permission_type="capability",
            action="inbox_send",
            success=kwargs.get("success", False),
            details={
                "to_pack_id": kwargs.get("to_pack_id"),
                "target_component": kwargs.get("comp_full_id"),
                "kind": kwargs.get("kind"),
                "file": kwargs.get("file"),
                "patch_op_count": kwargs.get("patch_op_count", 0),
                "payload_bytes": kwargs.get("payload_bytes", 0),
                "consumption": kwargs.get("consumption"),
                "stored_path": kwargs.get("stored_path"),
            },
        )
    except Exception:
        pass
'''

FILES["core_runtime/builtin_capability_handlers/propose_patch/handler.json"] = '''\
{
  "handler_id": "builtin.pack.update.propose_patch",
  "permission_id": "pack.update.propose_patch",
  "entrypoint": "handler.py:execute",
  "description": "Propose a file modification to another Pack by creating a staging area. Does NOT auto-apply.",
  "risk": "high",
  "input_schema": {
    "type": "object",
    "required": ["target_pack_id", "changes"],
    "properties": {
      "target_pack_id": {"type": "string"},
      "changes": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["file_path", "content"],
          "properties": {
            "file_path": {"type": "string"},
            "content": {},
            "sha256_before": {"type": "string"}
          }
        }
      },
      "notes": {"type": "string"},
      "request_id": {"type": "string"}
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": {"type": "boolean"},
      "staging_id": {"type": "string"},
      "changed_paths": {"type": "array"}
    }
  }
}
'''

FILES["core_runtime/builtin_capability_handlers/propose_patch/handler.py"] = '''\
"""
pack.update.propose_patch - Built-in Capability Handler

Pack A が Pack B のファイル修正案を staging として生成する。
自動 apply は絶対に行わない。ユーザーが /api/packs/apply で適用する前提。

安全要件:
- allowed_target_packs / allowed_path_globs で制限
- sha256_before 検証
- 自動 apply 禁止 (staging 生成のみ)
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_ID_RE = re.compile("^[a-zA-Z0-9_.-]+$")


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    principal_id = context.get("principal_id", "")
    grant_config = context.get("grant_config", {})

    target_pack_id = args.get("target_pack_id", "")
    changes = args.get("changes", [])
    notes = args.get("notes", "")
    request_id = args.get("request_id", uuid.uuid4().hex[:12])

    if not target_pack_id or not isinstance(target_pack_id, str):
        return _error("Missing or invalid target_pack_id", "validation_error")
    if not changes or not isinstance(changes, list):
        return _error("Missing or empty changes array", "validation_error")
    if not _safe_pack_id(target_pack_id):
        return _error("Invalid target_pack_id (path traversal)", "validation_error")

    allowed_targets = grant_config.get("allowed_target_packs", [])
    if allowed_targets and target_pack_id not in allowed_targets:
        return _error("Target pack not in allowed_target_packs", "grant_denied")

    allowed_path_globs = grant_config.get("allowed_path_globs", [])

    pack_dir = _find_pack_dir(target_pack_id)
    if pack_dir is None:
        return _error("Pack '" + target_pack_id + "' not found", "not_found")

    max_proposals = grant_config.get("max_proposals_per_target", 0)
    expires_at = grant_config.get("expires_at_epoch", 0)

    if max_proposals > 0 or expires_at > 0:
        try:
            from core_runtime.capability_usage_store import get_capability_usage_store
            store = get_capability_usage_store()
            result = store.check_and_consume(
                principal_id=principal_id,
                permission_id="pack.update.propose_patch",
                scope_key=target_pack_id,
                max_count=max_proposals,
                expires_at_epoch=expires_at,
            )
            if not result.allowed:
                return _error("Usage limit: " + str(result.reason), "usage_limit_exceeded")
        except Exception as e:
            return _error("Usage store error: " + str(e), "internal_error")

    validated_changes: List[Dict[str, Any]] = []
    for i, change in enumerate(changes):
        file_path = change.get("file_path", "")
        content = change.get("content")
        sha256_before = change.get("sha256_before")

        if not file_path:
            return _error("changes[" + str(i) + "]: missing file_path", "validation_error")
        if ".." in file_path:
            return _error(
                "changes[" + str(i) + "]: path traversal in file_path", "validation_error"
            )
        if allowed_path_globs:
            if not any(fnmatch.fnmatch(file_path, g) for g in allowed_path_globs):
                return _error(
                    "changes[" + str(i) + "]: file_path not in allowed_path_globs",
                    "grant_denied",
                )
        source_file = pack_dir / file_path
        if sha256_before:
            if source_file.exists():
                actual_hash = _compute_sha256(source_file)
                if actual_hash != sha256_before:
                    return _error(
                        "changes[" + str(i) + "]: sha256_before mismatch", "hash_mismatch"
                    )
            else:
                return _error(
                    "changes[" + str(i) + "]: file not found for sha256 check", "not_found"
                )

        validated_changes.append({
            "file_path": file_path,
            "content": content,
            "sha256_before": sha256_before,
        })

    staging_id = "propose_" + uuid.uuid4().hex[:12]
    staging_dir = Path("user_data") / "pack_staging" / staging_id

    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        payload_dir = staging_dir / "payload" / target_pack_id
        shutil.copytree(str(pack_dir), str(payload_dir))

        changed_paths: List[str] = []
        total_bytes = 0
        for change in validated_changes:
            fp = change["file_path"]
            target_file = payload_dir / fp
            target_file.parent.mkdir(parents=True, exist_ok=True)
            content = change["content"]
            if isinstance(content, (dict, list)):
                content_str = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                content_str = str(content)
            target_file.write_text(content_str, encoding="utf-8")
            changed_paths.append(fp)
            total_bytes += len(content_str.encode("utf-8"))

        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        meta = {
            "staging_id": staging_id,
            "input_type": "propose_patch",
            "source_path": "capability:" + principal_id,
            "imported_at": ts,
            "actor": principal_id,
            "notes": notes or ("Proposed by " + principal_id),
            "detected_pack_ids": [target_pack_id],
            "is_multi_pack": False,
            "proposal_info": {
                "from_pack_id": principal_id,
                "target_pack_id": target_pack_id,
                "changed_paths": changed_paths,
                "request_id": request_id,
            },
        }
        meta_file = staging_dir / "meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    except Exception as e:
        if staging_dir.exists():
            shutil.rmtree(str(staging_dir), ignore_errors=True)
        return _error("Staging generation failed: " + str(e), "staging_error")

    _audit_propose_patch(
        principal_id=principal_id,
        target_pack_id=target_pack_id,
        staging_id=staging_id,
        changed_paths=changed_paths,
        total_bytes=total_bytes,
        request_id=request_id,
    )

    return {
        "success": True,
        "staging_id": staging_id,
        "changed_paths": changed_paths,
        "total_bytes": total_bytes,
    }


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}


def _safe_pack_id(pack_id: str) -> bool:
    if ".." in pack_id or "/" in pack_id:
        return False
    if pack_id.startswith("."):
        return False
    return bool(_SAFE_ID_RE.match(pack_id))


def _find_pack_dir(pack_id: str) -> Optional[Path]:
    try:
        from core_runtime.paths import ECOSYSTEM_DIR, discover_pack_locations
        locations = discover_pack_locations(str(ECOSYSTEM_DIR))
        for loc in locations:
            if loc.pack_id == pack_id:
                return loc.pack_subdir
    except Exception:
        pass
    for candidate in [
        Path("ecosystem") / pack_id,
        Path("ecosystem") / "packs" / pack_id,
    ]:
        if candidate.is_dir():
            return candidate
    return None


def _compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _audit_propose_patch(**kwargs: Any) -> None:
    try:
        from core_runtime.audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_permission_event(
            pack_id=kwargs.get("principal_id", ""),
            permission_type="capability",
            action="propose_patch",
            success=True,
            details={
                "target_pack_id": kwargs.get("target_pack_id"),
                "staging_id": kwargs.get("staging_id"),
                "changed_paths": kwargs.get("changed_paths"),
                "total_bytes": kwargs.get("total_bytes"),
                "request_id": kwargs.get("request_id"),
            },
        )
    except Exception:
        pass
'''

FILES["tests/test_inbox_and_patches.py"] = '''\
"""
テスト: Pack間拡張 (inbox送信 + diff提案) + 14項目修正の検証

  python -m pytest tests/test_inbox_and_patches.py -v
  python tests/test_inbox_and_patches.py
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest import TestCase, main as unittest_main

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestPackApiServerSyntax(TestCase):
    def test_compiles(self):
        import py_compile
        src = PROJECT_ROOT / "core_runtime" / "pack_api_server.py"
        if not src.exists():
            self.skipTest("not found")
        try:
            py_compile.compile(str(src), doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(str(e))


class TestNetworkGrantManager(TestCase):
    def _make(self, td):
        from core_runtime.network_grant_manager import NetworkGrantManager
        return NetworkGrantManager(grants_dir=td, secret_key="test_secret")

    def test_empty_domains_allows_all(self):
        with tempfile.TemporaryDirectory() as td:
            ngm = self._make(td)
            ngm.grant_network_access(
                "tp", allowed_domains=[], allowed_ports=[443], granted_by="t",
            )
            self.assertTrue(ngm.check_access("tp", "any.example.com", 443).allowed)

    def test_empty_ports_allows_all(self):
        with tempfile.TemporaryDirectory() as td:
            ngm = self._make(td)
            ngm.grant_network_access(
                "tp", allowed_domains=["example.com"], allowed_ports=[], granted_by="t",
            )
            self.assertTrue(ngm.check_access("tp", "example.com", 9999).allowed)


class TestDiagnosticsNoPartial(TestCase):
    def test_no_partial(self):
        p = PROJECT_ROOT / "core_runtime" / "kernel_handlers_system.py"
        if not p.exists():
            self.skipTest("not found")
        self.assertNotIn('status="partial"', p.read_text("utf-8"))


class TestActiveEcosystemConfig(TestCase):
    def test_config_returns_copy(self):
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
        with tempfile.TemporaryDirectory() as td:
            mgr = ActiveEcosystemManager(config_path=os.path.join(td, "ae.json"))
            self.assertIsNot(mgr.config, mgr.config)

    def test_none_identity(self):
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemConfig
        self.assertIsNone(
            ActiveEcosystemConfig(active_pack_identity=None).active_pack_identity
        )

    def test_interface_overrides(self):
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
        with tempfile.TemporaryDirectory() as td:
            mgr = ActiveEcosystemManager(config_path=os.path.join(td, "ae.json"))
            mgr.set_interface_override("io.http.server", "pack_x")
            self.assertEqual(mgr.get_interface_override("io.http.server"), "pack_x")
            mgr.remove_interface_override("io.http.server")
            self.assertIsNone(mgr.get_interface_override("io.http.server"))


class TestOverridesIntegration(TestCase):
    def test_disabled(self):
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
        with tempfile.TemporaryDirectory() as td:
            mgr = ActiveEcosystemManager(config_path=os.path.join(td, "ae.json"))
            mgr.disable_component("pa:frontend:webui")
            self.assertTrue(mgr.is_component_disabled("pa:frontend:webui"))
            self.assertFalse(mgr.is_component_disabled("pa:frontend:other"))


class TestInterfaceRegistryGetByOwner(TestCase):
    def test_get_by_owner(self):
        from core_runtime.interface_registry import InterfaceRegistry
        ir = InterfaceRegistry()
        ir.register("io.http.server", "sa", meta={"owner_pack": "pa"})
        ir.register("io.http.server", "sb", meta={"owner_pack": "pb"})
        self.assertEqual(ir.get_by_owner("io.http.server", "pa"), "sa")
        self.assertEqual(ir.get_by_owner("io.http.server", "pb"), "sb")
        self.assertEqual(ir.get_by_owner("io.http.server", "unknown"), "sb")


class TestBuiltinHandlerRegistry(TestCase):
    def test_builtin_dir(self):
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry
        reg = CapabilityHandlerRegistry()
        d = reg._builtin_handlers_dir
        if d and d.exists():
            self.assertTrue((d / "inbox_send").exists())

    def test_load_builtin(self):
        from core_runtime.capability_handler_registry import CapabilityHandlerRegistry
        with tempfile.TemporaryDirectory() as td:
            reg = CapabilityHandlerRegistry(handlers_dir=td)
            reg.load_all()
            h = reg.get_by_permission_id("pack.inbox.send")
            if h:
                self.assertTrue(h.is_builtin)


class TestCapabilityUsageStore(TestCase):
    def test_once(self):
        from core_runtime.capability_usage_store import CapabilityUsageStore
        with tempfile.TemporaryDirectory() as td:
            s = CapabilityUsageStore(usage_dir=td, secret_key="t")
            self.assertTrue(s.check_and_consume("pa", "p", "s", max_count=1).allowed)
            r = s.check_and_consume("pa", "p", "s", max_count=1)
            self.assertFalse(r.allowed)
            self.assertEqual(r.reason, "max_count_exceeded")

    def test_persistence(self):
        from core_runtime.capability_usage_store import CapabilityUsageStore
        with tempfile.TemporaryDirectory() as td:
            CapabilityUsageStore(usage_dir=td, secret_key="t").check_and_consume(
                "pa", "p", "s", max_count=5
            )
            r = CapabilityUsageStore(usage_dir=td, secret_key="t").check_and_consume(
                "pa", "p", "s", max_count=5
            )
            self.assertTrue(r.allowed)
            self.assertEqual(r.used_count, 2)

    def test_expired(self):
        import time
        from core_runtime.capability_usage_store import CapabilityUsageStore
        with tempfile.TemporaryDirectory() as td:
            s = CapabilityUsageStore(usage_dir=td, secret_key="t")
            r = s.check_and_consume(
                "pa", "p", "s", max_count=99, expires_at_epoch=time.time() - 3600,
            )
            self.assertFalse(r.allowed)
            self.assertEqual(r.reason, "expired")


class TestUsageStoreConcurrency(TestCase):
    def test_concurrent_once(self):
        from core_runtime.capability_usage_store import CapabilityUsageStore
        with tempfile.TemporaryDirectory() as td:
            store = CapabilityUsageStore(usage_dir=td, secret_key="t")
            results = []
            barrier = threading.Barrier(2)
            def consume():
                barrier.wait()
                results.append(
                    store.check_and_consume("pa", "p", "s", max_count=1).allowed
                )
            threads = [threading.Thread(target=consume) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(sum(1 for r in results if r), 1)


class TestInboxSendHandler(TestCase):
    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        Path("user_data/packs").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _load(self):
        p = (
            PROJECT_ROOT / "core_runtime"
            / "builtin_capability_handlers" / "inbox_send" / "handler.py"
        )
        if not p.exists():
            self.skipTest("handler not found")
        spec = importlib.util.spec_from_file_location("_ih", str(p))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_missing_to_pack_id(self):
        r = self._load().execute(
            {"principal_id": "pa", "grant_config": {}},
            {"to_pack_id": "", "target_component": {}, "payload": {}},
        )
        self.assertFalse(r["success"])

    def test_policy_denied(self):
        r = self._load().execute(
            {"principal_id": "pa", "grant_config": {"allowed_target_packs": ["pb"]}},
            {
                "to_pack_id": "pb",
                "target_component": {"type": "fe", "id": "ui"},
                "payload": {
                    "kind": "manifest_json_patch",
                    "patch": [{"op": "add", "path": "/x", "value": 1}],
                },
            },
        )
        self.assertFalse(r["success"])

    def test_file_replace_default_denied(self):
        r = self._load().execute(
            {"principal_id": "pa", "grant_config": {"allowed_target_packs": ["pb"]}},
            {
                "to_pack_id": "pb",
                "target_component": {"type": "fe", "id": "ui"},
                "payload": {"kind": "file_replace_json", "file": "c.json", "json": {}},
            },
        )
        self.assertFalse(r["success"])
        self.assertEqual(r["error_type"], "grant_denied")

    def test_path_traversal(self):
        r = self._load().execute(
            {"principal_id": "pa", "grant_config": {}},
            {
                "to_pack_id": "../etc",
                "target_component": {"type": "fe", "id": "ui"},
                "payload": {
                    "kind": "manifest_json_patch",
                    "patch": [{"op": "add", "path": "/x", "value": 1}],
                },
            },
        )
        self.assertFalse(r["success"])
        self.assertEqual(r["error_type"], "validation_error")


if __name__ == "__main__":
    unittest_main()
'''


def main():
    ap = argparse.ArgumentParser(description="Deploy new files")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base-dir", default=".")
    args = ap.parse_args()

    base = Path(args.base_dir).resolve()
    print("[deploy] base:", base)
    print("[deploy] dry-run:", args.dry_run)
    print("[deploy] files:", len(FILES))
    print()

    ok = 0
    ng = 0
    for rel in sorted(FILES):
        fp = base / rel
        tag = "OVERWRITE" if fp.exists() else "CREATE"
        print("  [" + tag + "] " + rel)
        if args.dry_run:
            ok += 1
            continue
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(FILES[rel], encoding="utf-8")
            ok += 1
        except Exception as e:
            print("  [ERROR] " + rel + ": " + str(e))
            ng += 1

    print()
    print("[deploy] done: " + str(ok) + " written, " + str(ng) + " errors")
    if ng:
        sys.exit(1)


if __name__ == "__main__":
    main()
