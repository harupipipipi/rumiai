#!/usr/bin/env python3
"""check_deploy_final.py — 全項目の最終確認"""

from pathlib import Path

results = {"ok": 0, "fail": 0}

def check(filepath, markers, label):
    p = Path(filepath)
    if not p.exists():
        print(f"  [MISSING] {filepath}")
        results["fail"] += len(markers)
        return
    content = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker in content:
            print(f"  [OK]   {label}: '{marker[:60]}'")
            results["ok"] += 1
        else:
            print(f"  [FAIL] {label}: '{marker[:60]}'")
            results["fail"] += 1

print("=== Final verification ===\n")

check("app.py", [
    "def L(key, **kwargs):",
    "from core_runtime.lang import L as _L",
    "load_system_lang = lambda: None",
], "app.py")

check("core_runtime/python_file_executor.py", [
    "def _read_gid_env(",
    "def _get_egress_gid(",
    "def _get_capability_gid(",
    "egress_gid = _get_egress_gid()",
    "group_add_gids",
    '--group-add',
], "python_file_executor")

check("core_runtime/pack_applier.py", [
    '"pack_identity": data.get("pack_identity")',
    'new_pi = new_identity.get("pack_identity")',
    "pack_identity mismatch: existing pack_identity=",
], "pack_applier")

check("core_runtime/pip_installer.py", [
    "import ipaddress",
    "import re",
    "def validate_requirements_lock(",
    "def validate_index_url(",
    "_LOCK_LINE_PATTERN",
    "_LOCK_FORBIDDEN_PATTERNS",
    "def _check_pack_approval(",
    "RUMI_SECURITY_MODE",
    "pip_install_rejected_unapproved",
    "pip_requirements_lock_invalid",
    "pip_install_rejected_bad_index_url",
    "TOCTOU",
    "# C-4: idempotent",
], "pip_installer")

check("core_runtime/audit_logger.py", [
    "def _get_log_file_for_entry(",
    "def _extract_date_from_ts(",
    "by_file: Dict[Path, List[AuditEntry]]",
    "self._get_log_file_for_entry(entry.category, entry.ts)",
], "audit_logger")

check("core_runtime/kernel_handlers_runtime.py", [
    '"kernel:capability.grant": self._h_capability_grant',
    '"kernel:capability.revoke": self._h_capability_revoke',
    '"kernel:capability.list": self._h_capability_list',
    '"kernel:pending.export": self._h_pending_export',
    "def _h_capability_grant(",
    "def _h_capability_revoke(",
    "def _h_capability_list(",
    "def _h_pending_export(",
    "get_capability_grant_manager",
    "summary.json",
], "kernel_handlers_runtime")

check("core_runtime/pack_api_server.py", [
    '"/api/network/list"',
    '"/api/network/grant"',
    '"/api/network/revoke"',
    '"/api/network/check"',
    '"/api/capability/grants"',
    '"/api/capability/grants/grant"',
    '"/api/capability/grants/revoke"',
    "def _network_grant(",
    "def _network_revoke(",
    "def _network_check(",
    "def _network_list(",
    "def _capability_grants_grant(",
    "def _capability_grants_revoke(",
    "def _capability_grants_list(",
], "pack_api_server")

check("flows/00_startup.flow.yaml", [
    "pending_export",
    'handler: "kernel:pending.export"',
    "output_dir:",
], "startup_flow")

print(f"\n=== Result: {results['ok']} OK, {results['fail']} FAIL ===")
if results["fail"] == 0:
    print("ALL GREEN")
