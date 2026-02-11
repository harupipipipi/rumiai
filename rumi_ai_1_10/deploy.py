"""
deploy.py - 既存ファイル修正適用スクリプト

7つの既存ファイルにパッチを適用する。
実行前にバックアップを作成し、失敗時はロールバックする。

Usage:
    python deploy.py
    python deploy.py --dry-run
    python deploy.py --rollback
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple


BACKUP_DIR = ".deploy_backup"


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log(msg: str) -> None:
    print(f"[deploy] {msg}")


def log_ok(msg: str) -> None:
    print(f"[deploy]  OK  {msg}")


def log_err(msg: str) -> None:
    print(f"[deploy]  ERR {msg}", file=sys.stderr)


# ======================================================================
# バックアップ / ロールバック
# ======================================================================

def backup_file(filepath: Path, backup_dir: Path) -> Path:
    rel = filepath.resolve().relative_to(Path.cwd().resolve())
    dest = backup_dir / str(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(filepath, dest)
    return dest


def rollback(backup_dir: Path) -> None:
    if not backup_dir.exists():
        log_err(f"Backup directory not found: {backup_dir}")
        sys.exit(1)
    cwd = Path.cwd().resolve()
    count = 0
    for bf in backup_dir.rglob("*"):
        if bf.is_file():
            rel = bf.relative_to(backup_dir)
            target = cwd / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bf, target)
            log_ok(f"Restored: {rel}")
            count += 1
    log(f"Rollback complete: {count} files restored from {backup_dir}")


# ======================================================================
# 汎用ヘルパー
# ======================================================================

def find_line_index(lines: List[str], needle: str, start: int = 0) -> int:
    """needle を含む行のインデックスを返す。見つからなければ -1。"""
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return -1


def find_line_index_stripped(lines: List[str], needle: str, start: int = 0) -> int:
    """strip() 後に needle と一致する行のインデックスを返す。"""
    for i in range(start, len(lines)):
        if lines[i].strip() == needle:
            return i
    return -1


def get_indent(line: str) -> str:
    """行の先頭インデントを返す。"""
    return line[: len(line) - len(line.lstrip())]


# ======================================================================
# 1. python_file_executor.py
# ======================================================================

def patch_python_file_executor(content: str) -> str:
    """
    principal 強制: effective_principal = resolved_pack 固定。
    '# 2. 承認チェック' の直前にブロックを挿入する。
    """
    if "# principal 強制（v1）" in content:
        return content  # 既に適用済み

    lines = content.split("\n")

    # '# 2. 承認チェック' を探す
    idx = find_line_index(lines, "# 2. 承認チェック")
    if idx == -1:
        # フォールバック: 'approved, reason = self._approval_checker.is_approved' を探す
        idx = find_line_index(lines, "self._approval_checker.is_approved")
        if idx == -1:
            raise ValueError("python_file_executor.py: cannot find insertion point for principal enforcement")
        # その前の 'if resolved_pack:' を探す
        for j in range(idx, max(idx - 10, 0), -1):
            if "if resolved_pack:" in lines[j]:
                idx = j
                break

    indent = get_indent(lines[idx])

    block = [
        f"{indent}# principal 強制（v1）: principal は必ず owner_pack に固定",
        f"{indent}# FlowStep から principal_id が来ても無視（乱用事故防止）",
        f"{indent}effective_principal = resolved_pack",
        f"{indent}if principal_id is not None and principal_id != resolved_pack:",
        f"{indent}    try:",
        f"{indent}        from .audit_logger import get_audit_logger",
        f"{indent}        _audit = get_audit_logger()",
        f"{indent}        _audit.log_security_event(",
        f'{indent}            event_type="principal_id_overridden",',
        f'{indent}            severity="warning",',
        f"{indent}            description=(",
        f"""{indent}                f"principal_id '{{principal_id}}' overridden to \"""",
        f"""{indent}                f"owner_pack '{{resolved_pack}}' (v1 principal enforcement)\"""",
        f"{indent}            ),",
        f"{indent}            details={{",
        f'{indent}                "requested_principal": principal_id,',
        f'{indent}                "effective_principal": resolved_pack,',
        f"{indent}            }},",
        f"{indent}        )",
        f"{indent}    except Exception:",
        f"{indent}        pass",
        f"",
    ]

    lines = lines[:idx] + block + lines[idx:]
    return "\n".join(lines)


# ======================================================================
# 2. kernel_handlers_runtime.py
# ======================================================================

def patch_kernel_handlers_runtime(content: str) -> str:
    """
    effective_principal = principal_id or owner_pack
    → effective_principal = owner_pack
    """
    old = "effective_principal = principal_id or owner_pack"
    new = "effective_principal = owner_pack  # v1 principal enforcement: always owner_pack"

    if old not in content:
        if "# v1 principal enforcement" in content:
            return content  # 既に適用済み
        raise ValueError("kernel_handlers_runtime.py: cannot find 'effective_principal = principal_id or owner_pack'")

    return content.replace(old, new, 1)


# ======================================================================
# 3. kernel_core.py
# ======================================================================

def patch_kernel_core(content: str) -> str:
    """
    _execute_handler_step_async 内の handler 解決を統一。
    IR のみ → _resolve_handler 優先 + IR フォールバック。
    """
    if "# handler 解決統一" in content:
        return content  # 既に適用済み

    lines = content.split("\n")

    # _execute_handler_step_async メソッド内を探す
    method_idx = find_line_index(lines, "async def _execute_handler_step_async")
    if method_idx == -1:
        raise ValueError("kernel_core.py: cannot find _execute_handler_step_async")

    # メソッド内で 'self.interface_registry.get(handler_key' を探す
    ir_get_idx = find_line_index(lines, 'self.interface_registry.get(handler_key', method_idx)
    if ir_get_idx == -1:
        raise ValueError("kernel_core.py: cannot find interface_registry.get(handler_key) in _execute_handler_step_async")

    indent = get_indent(lines[ir_get_idx])

    # 旧コードの範囲を特定:
    # Line A: handler = self.interface_registry.get(handler_key, strategy="last")
    # Line B: if not handler or not callable(handler):
    # Line C:     return ctx, None
    # Line D: resolved_args = self._resolve_value(step.get("args", {}), ctx)
    old_start = ir_get_idx
    old_end = ir_get_idx

    # B行を探す
    for j in range(ir_get_idx + 1, min(ir_get_idx + 5, len(lines))):
        s = lines[j].strip()
        if s.startswith("if not handler") or s.startswith("if handler is None"):
            old_end = j
            break

    # C行 (return ctx, None)
    for j in range(old_end + 1, min(old_end + 3, len(lines))):
        if "return ctx, None" in lines[j]:
            old_end = j
            break

    # D行 (resolved_args)
    for j in range(old_end + 1, min(old_end + 3, len(lines))):
        if "resolved_args" in lines[j] and "_resolve_value" in lines[j]:
            old_end = j
            break

    new_block = [
        f'{indent}resolved_args = self._resolve_value(step.get("args", {{}}), ctx)',
        f"",
        f"{indent}# handler 解決統一: kernel:* は _resolve_handler を優先し、",
        f"{indent}# pipeline 実行と同じ経路で解決する（async/pipeline 非対称の解消）",
        f"{indent}handler = self._resolve_handler(handler_key, resolved_args)",
        f"",
        f"{indent}# kernel:* で見つからなかった場合は IR にフォールバック",
        f"{indent}if handler is None:",
        f'{indent}    handler = self.interface_registry.get(handler_key, strategy="last")',
        f"",
        f"{indent}if handler is None or not callable(handler):",
        f"{indent}    return ctx, None",
    ]

    lines = lines[:old_start] + new_block + lines[old_end + 1:]
    return "\n".join(lines)


# ======================================================================
# 4. capability_grant_manager.py
# ======================================================================

def patch_capability_grant_manager(content: str) -> str:
    """
    - import hierarchical_grant を追加
    - check() の本体を階層 grant 評価に書き換え
    """
    if "parse_principal_chain" in content:
        return content  # 既に適用済み

    # --- 1. import 追加 ---
    import_line = "from .hierarchical_grant import parse_principal_chain, intersect_config"

    lines = content.split("\n")

    # 'from typing import' の行を探す
    typing_idx = find_line_index(lines, "from typing import")
    if typing_idx == -1:
        raise ValueError("capability_grant_manager.py: cannot find 'from typing import'")

    lines.insert(typing_idx + 1, "")
    lines.insert(typing_idx + 2, import_line)

    # --- 2. check() 本体の置換 ---
    # check() メソッド内の 'with self._lock:' ブロック内、
    # 改ざんチェックの後の '# Grant が存在するか' または
    # 'grant = self._grants.get(principal_id)' から
    # メソッド末尾の 'config=dict(perm.config)' を含む return まで。

    content_rejoined = "\n".join(lines)
    lines = content_rejoined.split("\n")

    # check() メソッドを探す
    check_idx = find_line_index(lines, "def check(self, principal_id")
    if check_idx == -1:
        raise ValueError("capability_grant_manager.py: cannot find 'def check('")

    # check() メソッドの次のメソッド定義を探す（check の終わりを決定）
    next_def_idx = -1
    for j in range(check_idx + 1, len(lines)):
        stripped = lines[j].strip()
        # 同レベルの def（インデント4スペース）
        if lines[j].startswith("    def ") and not lines[j].startswith("        "):
            next_def_idx = j
            break

    if next_def_idx == -1:
        # クラスの終わりまで
        next_def_idx = len(lines)

    # check() 内で旧コードの開始を探す
    # 'grant = self._grants.get(principal_id)' を探す（改ざんチェック後）
    old_body_start = -1
    for j in range(check_idx, next_def_idx):
        s = lines[j].strip()
        if s == "grant = self._grants.get(principal_id)":
            old_body_start = j
            break
        # コメント行も候補
        if "Grant" in s and "存在" in s:
            old_body_start = j
            break

    if old_body_start == -1:
        # もうひとつのパターン: 直接 grant = を探す
        for j in range(check_idx, next_def_idx):
            if "self._grants.get(principal_id)" in lines[j] and "grant" in lines[j]:
                old_body_start = j
                break

    if old_body_start == -1:
        raise ValueError(
            "capability_grant_manager.py: cannot find old check() body. "
            "Searched for 'grant = self._grants.get(principal_id)' between lines "
            f"{check_idx} and {next_def_idx}"
        )

    # old_body_start の前に日本語コメント行がある場合はそれも含める
    if old_body_start > 0 and ("Grant" in lines[old_body_start - 1] or "存在" in lines[old_body_start - 1]):
        old_body_start -= 1
    # 空行も含める
    if old_body_start > 0 and lines[old_body_start - 1].strip() == "":
        old_body_start -= 1

    old_body_end = next_def_idx

    # 旧コードの最後の行を探す（return GrantCheckResult の閉じ括弧 ')'）
    # next_def の直前の空行やコメントをスキップ
    actual_end = old_body_end
    for j in range(old_body_end - 1, old_body_start, -1):
        s = lines[j].strip()
        if s == "" or s.startswith("#"):
            actual_end = j
        else:
            actual_end = j + 1
            break

    indent = "            "  # 12 spaces (inside with self._lock:)

    new_body = [
        f"",
        f"{indent}# 階層 principal チェーン（parent__child 形式に対応）",
        f"{indent}chain = parse_principal_chain(principal_id)",
        f"{indent}configs = []",
        f"",
        f"{indent}for ancestor_id in chain:",
        f"{indent}    # 改ざんチェック（各階層）",
        f"{indent}    if (ancestor_id in self._tampered_principals",
        f"{indent}            or sanitize_principal_id(ancestor_id) in self._tampered_principals):",
        f"{indent}        label = 'ancestor' if ancestor_id != principal_id else 'principal'",
        f"{indent}        return GrantCheckResult(",
        f"{indent}            allowed=False,",
        f'{indent}            reason=f"Grant file for {{label}} \'{{ancestor_id}}\' has been tampered with",',
        f"{indent}            principal_id=principal_id,",
        f"{indent}            permission_id=permission_id,",
        f"{indent}        )",
        f"",
        f"{indent}    grant = self._grants.get(ancestor_id)",
        f"{indent}    label = 'ancestor' if ancestor_id != principal_id else 'principal'",
        f"",
        f"{indent}    if grant is None:",
        f"{indent}        return GrantCheckResult(",
        f"{indent}            allowed=False,",
        f'{indent}            reason=f"No capability grant for {{label}} \'{{ancestor_id}}\'",',
        f"{indent}            principal_id=principal_id,",
        f"{indent}            permission_id=permission_id,",
        f"{indent}        )",
        f"",
        f"{indent}    if not grant.enabled:",
        f"{indent}        return GrantCheckResult(",
        f"{indent}            allowed=False,",
        f'{indent}            reason=f"Capability grant for {{label}} \'{{ancestor_id}}\' is disabled",',
        f"{indent}            principal_id=principal_id,",
        f"{indent}            permission_id=permission_id,",
        f"{indent}        )",
        f"",
        f"{indent}    perm = grant.permissions.get(permission_id)",
        f"{indent}    if perm is None:",
        f"{indent}        return GrantCheckResult(",
        f"{indent}            allowed=False,",
        f'{indent}            reason=f"Permission \'{{permission_id}}\' not granted to {{label}} \'{{ancestor_id}}\'",',
        f"{indent}            principal_id=principal_id,",
        f"{indent}            permission_id=permission_id,",
        f"{indent}        )",
        f"",
        f"{indent}    if not perm.enabled:",
        f"{indent}        return GrantCheckResult(",
        f"{indent}            allowed=False,",
        f'{indent}            reason=f"Permission \'{{permission_id}}\' is disabled for {{label}} \'{{ancestor_id}}\'",',
        f"{indent}            principal_id=principal_id,",
        f"{indent}            permission_id=permission_id,",
        f"{indent}        )",
        f"",
        f"{indent}    configs.append(dict(perm.config))",
        f"",
        f"{indent}# 全階層 OK → config は intersection",
        f"{indent}final_config = intersect_config(configs) if len(configs) > 1 else (configs[0] if configs else {{}})",
        f"",
        f"{indent}return GrantCheckResult(",
        f"{indent}    allowed=True,",
        f'{indent}    reason="Granted",',
        f"{indent}    principal_id=principal_id,",
        f"{indent}    permission_id=permission_id,",
        f"{indent}    config=final_config,",
        f"{indent})",
        f"",
    ]

    lines = lines[:old_body_start] + new_body + lines[actual_end:]
    return "\n".join(lines)


# ======================================================================
# 5. capability_executor.py
# ======================================================================

def patch_capability_executor(content: str) -> str:
    """
    - import collections 追加
    - rate limit 定数追加
    - __init__ に rate limit 状態追加
    - execute() に secret.get rate limit 挿入
    - _check_rate_limit メソッド追加
    """
    lines = content.split("\n")

    # --- 1. import collections ---
    if "import collections" not in content:
        idx = find_line_index(lines, "import json")
        if idx == -1:
            raise ValueError("capability_executor.py: cannot find 'import json'")
        lines.insert(idx, "import collections")

    # --- 2. rate limit 定数 ---
    if "SECRET_GET_PERMISSION_ID" not in content:
        content_tmp = "\n".join(lines)
        lines = content_tmp.split("\n")
        idx = find_line_index(lines, "MAX_TIMEOUT")
        if idx == -1:
            raise ValueError("capability_executor.py: cannot find 'MAX_TIMEOUT'")
        insert_lines = [
            "",
            "# rate limit: secret.get のみ（無限ループ事故防止）",
            'SECRET_GET_PERMISSION_ID = "secret.get"',
            "DEFAULT_SECRET_GET_RATE_LIMIT = 60  # 回/分/principal",
        ]
        lines = lines[:idx + 1] + insert_lines + lines[idx + 1:]

    # --- 3. __init__ に rate limit 状態追加 ---
    if "_rate_limit_state" not in "\n".join(lines):
        content_tmp = "\n".join(lines)
        lines = content_tmp.split("\n")
        idx = find_line_index(lines, "self._grant_manager = None")
        if idx == -1:
            raise ValueError("capability_executor.py: cannot find 'self._grant_manager = None'")
        indent = get_indent(lines[idx])
        insert_lines = [
            f"{indent}# rate limit 状態: principal_id -> deque of timestamps",
            f"{indent}self._rate_limit_state = {{}}",
            f"{indent}self._rate_limit_lock = threading.Lock()",
            f"{indent}self._secret_get_rate_limit = int(",
            f'{indent}    os.environ.get("RUMI_SECRET_GET_RATE_LIMIT",',
            f"{indent}                   str(DEFAULT_SECRET_GET_RATE_LIMIT)))",
        ]
        lines = lines[:idx + 1] + insert_lines + lines[idx + 1:]

    # --- 4. execute() に rate limit チェック挿入 ---
    content_tmp = "\n".join(lines)
    if "SECRET_GET_PERMISSION_ID" not in content_tmp.split("def execute(")[1].split("\n    def ")[0] if "def execute(" in content_tmp else "x":
        lines = content_tmp.split("\n")
        # '# 初期化チェック' を execute() 内で探す
        exec_idx = find_line_index(lines, "def execute(")
        if exec_idx == -1:
            raise ValueError("capability_executor.py: cannot find 'def execute('")
        init_check_idx = find_line_index(lines, "# 初期化チェック", exec_idx)
        if init_check_idx == -1:
            # フォールバック: 'if not self._initialized:' を探す
            init_check_idx = find_line_index(lines, "if not self._initialized:", exec_idx)
            if init_check_idx == -1:
                raise ValueError("capability_executor.py: cannot find initialization check in execute()")

        indent = get_indent(lines[init_check_idx])
        insert_lines = [
            f"{indent}# rate limit: secret.get のみ（無限ループ事故防止）",
            f"{indent}if permission_id == SECRET_GET_PERMISSION_ID:",
            f"{indent}    if not self._check_rate_limit(principal_id):",
            f"{indent}        resp = CapabilityResponse(",
            f"{indent}            success=False,",
            f'{indent}            error="Rate limited",',
            f'{indent}            error_type="rate_limited",',
            f"{indent}            latency_ms=(time.time() - start_time) * 1000,",
            f"{indent}        )",
            f"{indent}        self._audit(",
            f"{indent}            principal_id, permission_id, None, resp, args, request_id,",
            f'{indent}            detail_reason=f"Rate limit exceeded ({{self._secret_get_rate_limit}}/min)",',
            f"{indent}        )",
            f"{indent}        return resp",
            f"",
        ]
        lines = lines[:init_check_idx] + insert_lines + lines[init_check_idx:]

    # --- 5. _check_rate_limit メソッド追加 ---
    content_tmp = "\n".join(lines)
    if "def _check_rate_limit" not in content_tmp:
        lines = content_tmp.split("\n")
        # _audit メソッドの直前に挿入
        audit_idx = find_line_index(lines, "def _audit(")
        if audit_idx == -1:
            raise ValueError("capability_executor.py: cannot find 'def _audit('")

        method_lines = [
            "    def _check_rate_limit(self, principal_id: str) -> bool:",
            '        """',
            "        secret.get の rate limit チェック（sliding window 60秒）。",
            "",
            "        Returns:",
            "            True = 許可, False = 超過",
            '        """',
            "        now = time.time()",
            "        window = 60.0",
            "",
            "        with self._rate_limit_lock:",
            "            if principal_id not in self._rate_limit_state:",
            "                self._rate_limit_state[principal_id] = collections.deque()",
            "",
            "            dq = self._rate_limit_state[principal_id]",
            "",
            "            # ウィンドウ外のエントリを削除",
            "            while dq and dq[0] < now - window:",
            "                dq.popleft()",
            "",
            "            if len(dq) >= self._secret_get_rate_limit:",
            "                return False",
            "",
            "            dq.append(now)",
            "            return True",
            "",
        ]
        lines = lines[:audit_idx] + method_lines + lines[audit_idx:]

    return "\n".join(lines)


# ======================================================================
# 6. pack_api_server.py
# ======================================================================

def patch_pack_api_server(content: str) -> str:
    """
    - from pathlib import Path 追加
    - GET endpoints 追加
    - POST endpoints 追加
    - handler methods 追加
    """
    lines = content.split("\n")

    # --- 1. import Path ---
    if "from pathlib import Path" not in content:
        idx = find_line_index(lines, "from dataclasses import")
        if idx == -1:
            raise ValueError("pack_api_server.py: cannot find 'from dataclasses import'")
        lines.insert(idx, "from pathlib import Path")

    # --- 2. GET endpoints ---
    content_tmp = "\n".join(lines)
    if '"/api/secrets"' not in content_tmp:
        lines = content_tmp.split("\n")

        # "/api/docker/status" のレスポンス送信行の後に追加
        docker_resp_idx = -1
        docker_handler_idx = find_line_index(lines, '"/api/docker/status"')
        if docker_handler_idx != -1:
            # その後の _send_response 行を探す
            for j in range(docker_handler_idx, min(docker_handler_idx + 5, len(lines))):
                if "_send_response" in lines[j] and "docker" in "\n".join(lines[docker_handler_idx:j + 1]).lower():
                    docker_resp_idx = j
                    break

        if docker_resp_idx == -1:
            # フォールバック: capability/blocked の前に挿入
            docker_resp_idx = find_line_index(lines, '"/api/capability/blocked"')
            if docker_resp_idx == -1:
                raise ValueError("pack_api_server.py: cannot find insertion point for GET endpoints")
            docker_resp_idx -= 1  # その前の行

        indent = "            "
        new_get = [
            f"",
            f'{indent}elif path == "/api/secrets":',
            f"{indent}    result = self._secrets_list()",
            f"{indent}    self._send_response(APIResponse(True, result))",
            f"",
            f'{indent}elif path == "/api/stores":',
            f"{indent}    result = self._stores_list()",
            f"{indent}    self._send_response(APIResponse(True, result))",
            f"",
            f'{indent}elif path == "/api/units":',
            f"{indent}    query = parse_qs(urlparse(self.path).query)",
            f'{indent}    store_id = query.get("store_id", [None])[0]',
            f"{indent}    result = self._units_list(store_id)",
            f"{indent}    self._send_response(APIResponse(True, result))",
        ]
        lines = lines[:docker_resp_idx + 1] + new_get + lines[docker_resp_idx + 1:]

    # --- 3. POST endpoints ---
    content_tmp = "\n".join(lines)
    if '"/api/packs/import"' not in content_tmp:
        lines = content_tmp.split("\n")

        # "/api/packs/scan" の _send_response 行の後に追加
        scan_idx = find_line_index(lines, '"/api/packs/scan"')
        if scan_idx == -1:
            raise ValueError("pack_api_server.py: cannot find '/api/packs/scan'")
        # scan の _send_response を探す
        scan_resp_idx = scan_idx
        for j in range(scan_idx, min(scan_idx + 5, len(lines))):
            if "_send_response" in lines[j]:
                scan_resp_idx = j
                break

        indent = "            "
        new_post = [
            f"",
            f'{indent}elif path == "/api/packs/import":',
            f'{indent}    source_path = body.get("path", "")',
            f'{indent}    notes = body.get("notes", "")',
            f"{indent}    if not source_path:",
            f"""{indent}        self._send_response(APIResponse(False, error="Missing 'path'"), 400)""",
            f"{indent}    else:",
            f"{indent}        result = self._pack_import(source_path, notes)",
            f'{indent}        if result.get("success"):',
            f"{indent}            self._send_response(APIResponse(True, result))",
            f"{indent}        else:",
            f"""{indent}            self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/packs/apply":',
            f'{indent}    staging_id = body.get("staging_id", "")',
            f'{indent}    mode = body.get("mode", "replace")',
            f"{indent}    if not staging_id:",
            f"""{indent}        self._send_response(APIResponse(False, error="Missing 'staging_id'"), 400)""",
            f"{indent}    else:",
            f"{indent}        result = self._pack_apply(staging_id, mode)",
            f'{indent}        if result.get("success"):',
            f"{indent}            self._send_response(APIResponse(True, result))",
            f"{indent}        else:",
            f"""{indent}            self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/secrets/set":',
            f"{indent}    result = self._secrets_set(body)",
            f'{indent}    if result.get("success"):',
            f"{indent}        self._send_response(APIResponse(True, result))",
            f"{indent}    else:",
            f"""{indent}        self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/secrets/delete":',
            f"{indent}    result = self._secrets_delete(body)",
            f'{indent}    if result.get("success"):',
            f"{indent}        self._send_response(APIResponse(True, result))",
            f"{indent}    else:",
            f"""{indent}        self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/stores/create":',
            f"{indent}    result = self._stores_create(body)",
            f'{indent}    if result.get("success"):',
            f"{indent}        self._send_response(APIResponse(True, result))",
            f"{indent}    else:",
            f"""{indent}        self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/units/publish":',
            f"{indent}    result = self._units_publish(body)",
            f'{indent}    if result.get("success"):',
            f"{indent}        self._send_response(APIResponse(True, result))",
            f"{indent}    else:",
            f"""{indent}        self._send_response(APIResponse(False, error=result.get("error")), 400)""",
            f"",
            f'{indent}elif path == "/api/units/execute":',
            f"{indent}    result = self._units_execute(body)",
            f'{indent}    if result.get("success"):',
            f"{indent}        self._send_response(APIResponse(True, result))",
            f"{indent}    else:",
            f'{indent}        status_code = 403 if result.get("error_type") in (',
            f'{indent}            "approval_denied", "grant_denied", "trust_denied"',
            f"{indent}        ) else 400",
            f"""{indent}        self._send_response(APIResponse(False, error=result.get("error")), status_code)""",
        ]
        lines = lines[:scan_resp_idx + 1] + new_post + lines[scan_resp_idx + 1:]

    # --- 4. handler methods ---
    content_tmp = "\n".join(lines)
    if "def _pack_import" not in content_tmp:
        lines = content_tmp.split("\n")

        # 'class PackAPIServer:' の直前に挿入
        class_idx = find_line_index(lines, "class PackAPIServer:")
        if class_idx == -1:
            raise ValueError("pack_api_server.py: cannot find 'class PackAPIServer:'")

        handler_code = [
            "",
            "    # ------------------------------------------------------------------",
            "    # Pack import/apply",
            "    # ------------------------------------------------------------------",
            "",
            '    def _pack_import(self, source_path: str, notes: str = "") -> dict:',
            "        try:",
            "            from .pack_importer import get_pack_importer",
            "            importer = get_pack_importer()",
            "            result = importer.import_pack(source_path, notes=notes)",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
            '    def _pack_apply(self, staging_id: str, mode: str = "replace") -> dict:',
            "        try:",
            "            from .pack_applier import get_pack_applier",
            "            applier = get_pack_applier()",
            "            result = applier.apply(staging_id, mode=mode)",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
            "    # ------------------------------------------------------------------",
            "    # Secrets",
            "    # ------------------------------------------------------------------",
            "",
            "    def _secrets_list(self) -> dict:",
            "        try:",
            "            from .secrets_store import get_secrets_store",
            "            store = get_secrets_store()",
            "            keys = store.list_keys()",
            '            return {"secrets": [k.to_dict() for k in keys], "count": len(keys)}',
            "        except Exception as e:",
            '            return {"secrets": [], "error": str(e)}',
            "",
            "    def _secrets_set(self, body: dict) -> dict:",
            '        key = body.get("key", "")',
            '        value = body.get("value", "")',
            "        if not key:",
            """            return {"success": False, "error": "Missing 'key'"}""",
            "        if not isinstance(value, str):",
            """            return {"success": False, "error": "'value' must be a string"}""",
            "        try:",
            "            from .secrets_store import get_secrets_store",
            "            store = get_secrets_store()",
            "            result = store.set_secret(key, value)",
            "            return result.to_dict()",
            "        except Exception:",
            '            return {"success": False, "error": "Failed to set secret"}',
            "",
            "    def _secrets_delete(self, body: dict) -> dict:",
            '        key = body.get("key", "")',
            "        if not key:",
            """            return {"success": False, "error": "Missing 'key'"}""",
            "        try:",
            "            from .secrets_store import get_secrets_store",
            "            store = get_secrets_store()",
            "            result = store.delete_secret(key)",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
            "    # ------------------------------------------------------------------",
            "    # Store",
            "    # ------------------------------------------------------------------",
            "",
            "    def _stores_list(self) -> dict:",
            "        try:",
            "            from .store_registry import get_store_registry",
            "            reg = get_store_registry()",
            "            stores = reg.list_stores()",
            '            return {"stores": stores, "count": len(stores)}',
            "        except Exception as e:",
            '            return {"stores": [], "error": str(e)}',
            "",
            "    def _stores_create(self, body: dict) -> dict:",
            '        store_id = body.get("store_id", "")',
            '        root_path = body.get("root_path", "")',
            "        if not store_id or not root_path:",
            """            return {"success": False, "error": "Missing 'store_id' or 'root_path'"}""",
            "        try:",
            "            from .store_registry import get_store_registry",
            "            reg = get_store_registry()",
            "            result = reg.create_store(store_id, root_path)",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
            "    # ------------------------------------------------------------------",
            "    # Unit",
            "    # ------------------------------------------------------------------",
            "",
            "    def _units_list(self, store_id=None) -> dict:",
            "        try:",
            "            from .store_registry import get_store_registry",
            "            from .unit_registry import get_unit_registry",
            "            store_reg = get_store_registry()",
            "            unit_reg = get_unit_registry()",
            "            if store_id:",
            "                store_def = store_reg.get_store(store_id)",
            "                if store_def is None:",
            '                    return {"units": [], "error": f"Store not found: {store_id}"}',
            "                units = unit_reg.list_units(Path(store_def.root_path))",
            '                return {"units": [u.to_dict() for u in units], "count": len(units), "store_id": store_id}',
            "            else:",
            "                all_units = []",
            "                for sd in store_reg.list_stores():",
            '                    sid = sd.get("store_id", "")',
            '                    rp = sd.get("root_path", "")',
            "                    if rp:",
            "                        units = unit_reg.list_units(Path(rp))",
            "                        for u in units:",
            "                            u.store_id = sid",
            "                        all_units.extend(units)",
            '                return {"units": [u.to_dict() for u in all_units], "count": len(all_units)}',
            "        except Exception as e:",
            '            return {"units": [], "error": str(e)}',
            "",
            "    def _units_publish(self, body: dict) -> dict:",
            '        store_id = body.get("store_id", "")',
            '        source_dir = body.get("source_dir", "")',
            '        namespace = body.get("namespace", "")',
            '        name = body.get("name", "")',
            '        version = body.get("version", "")',
            "        if not all([store_id, source_dir, namespace, name, version]):",
            '            return {"success": False, "error": "Missing required fields"}',
            "        try:",
            "            from .store_registry import get_store_registry",
            "            from .unit_registry import get_unit_registry",
            "            store_reg = get_store_registry()",
            "            store_def = store_reg.get_store(store_id)",
            "            if store_def is None:",
            '                return {"success": False, "error": f"Store not found: {store_id}"}',
            "            unit_reg = get_unit_registry()",
            "            result = unit_reg.publish_unit(",
            "                Path(store_def.root_path), Path(source_dir),",
            "                namespace, name, version, store_id=store_id,",
            "            )",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
            "    def _units_execute(self, body: dict) -> dict:",
            '        principal_id = body.get("principal_id", "")',
            '        unit_ref = body.get("unit_ref", {})',
            '        mode = body.get("mode", "")',
            '        args = body.get("args", {})',
            '        timeout = body.get("timeout_seconds", 60.0)',
            "        if not principal_id or not unit_ref or not mode:",
            '            return {"success": False, "error": "Missing principal_id, unit_ref, or mode"}',
            "        try:",
            "            from .unit_executor import get_unit_executor",
            "            executor = get_unit_executor()",
            "            result = executor.execute(principal_id, unit_ref, mode, args, timeout)",
            "            return result.to_dict()",
            "        except Exception as e:",
            '            return {"success": False, "error": str(e)}',
            "",
        ]
        lines = lines[:class_idx] + handler_code + lines[class_idx:]

    return "\n".join(lines)


# ======================================================================
# 7. flows/00_startup.flow.yaml
# ======================================================================

def patch_startup_flow(content: str) -> str:
    """packs_dir: ecosystem/packs → ecosystem"""
    replacements = [
        ('packs_dir: "ecosystem/packs"', 'packs_dir: "ecosystem"'),
        ("packs_dir: ecosystem/packs", "packs_dir: ecosystem"),
        ("packs_dir: 'ecosystem/packs'", "packs_dir: 'ecosystem'"),
    ]
    for old, new in replacements:
        if old in content:
            return content.replace(old, new, 1)

    if 'packs_dir: "ecosystem"' in content or "packs_dir: ecosystem" in content:
        return content  # 既に修正済み

    raise ValueError("00_startup.flow.yaml: cannot find packs_dir")


# ======================================================================
# パッチテーブル
# ======================================================================

PATCHES: List[Tuple[str, callable]] = [
    ("core_runtime/python_file_executor.py", patch_python_file_executor),
    ("core_runtime/kernel_handlers_runtime.py", patch_kernel_handlers_runtime),
    ("core_runtime/kernel_core.py", patch_kernel_core),
    ("core_runtime/capability_grant_manager.py", patch_capability_grant_manager),
    ("core_runtime/capability_executor.py", patch_capability_executor),
    ("core_runtime/pack_api_server.py", patch_pack_api_server),
    ("flows/00_startup.flow.yaml", patch_startup_flow),
]


# ======================================================================
# メイン
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Apply patches to existing files")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--rollback", action="store_true", help="Rollback from last backup")
    parser.add_argument("--backup-dir", default=None, help="Custom backup directory")
    args = parser.parse_args()

    ts = now_ts()
    backup_dir = Path(args.backup_dir) if args.backup_dir else Path(BACKUP_DIR) / ts

    if args.rollback:
        base = Path(BACKUP_DIR)
        if args.backup_dir:
            rollback(Path(args.backup_dir))
        elif base.exists():
            backups = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
            if backups:
                rollback(backups[0])
            else:
                log_err("No backups found")
                sys.exit(1)
        else:
            log_err("No backup directory found")
            sys.exit(1)
        return

    log(f"Starting patch deployment (dry_run={args.dry_run})")
    log(f"Backup directory: {backup_dir}")

    # 存在確認
    missing = [fp for fp, _ in PATCHES if not Path(fp).exists()]
    if missing:
        log_err(f"Missing files: {missing}")
        sys.exit(1)

    # バックアップ
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filepath, _ in PATCHES:
            bp = backup_file(Path(filepath), backup_dir)
            log_ok(f"Backed up: {filepath}")

    # パッチ適用
    success = 0
    failed = 0

    for filepath, patch_fn in PATCHES:
        p = Path(filepath)
        log(f"Patching: {filepath}")
        try:
            original = p.read_text(encoding="utf-8")
            patched = patch_fn(original)

            if patched == original:
                log_ok(f"Already patched: {filepath}")
                success += 1
                continue

            if args.dry_run:
                added = len(patched.splitlines()) - len(original.splitlines())
                log_ok(f"Would modify: {filepath} ({added:+d} lines)")
            else:
                p.write_text(patched, encoding="utf-8")
                log_ok(f"Patched: {filepath}")

            success += 1
        except Exception as e:
            log_err(f"FAILED: {filepath}: {e}")
            failed += 1
            if not args.dry_run:
                log_err("Rolling back all changes...")
                rollback(backup_dir)
                log_err("Rollback complete. No files were modified.")
                sys.exit(1)

    log("")
    log(f"{'DRY RUN ' if args.dry_run else ''}Complete: {success} succeeded, {failed} failed")
    if not args.dry_run and failed == 0:
        log(f"Backup saved to: {backup_dir}")
        log(f"To rollback: python deploy.py --rollback")


if __name__ == "__main__":
    main()
