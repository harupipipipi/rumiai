"""
binary_call.py - バイナリ実行エンジン

Pack のバイナリファイルを stdin/stdout JSON プロトコルで実行する。
capability_executor.py の _execute_binary_function() を参考にした独立実装。

セキュリティ:
- パストラバーサル防止（resolve() が基準ディレクトリ内に収まることを確認）
- バイナリの存在と実行権限を確認
- 出力サイズ制限（1MB）
- タイムアウト制御
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 出力サイズ上限（1MB）
MAX_OUTPUT_SIZE: int = 1 * 1024 * 1024

# デフォルトタイムアウト（秒）
DEFAULT_TIMEOUT: float = 30.0

# 最大タイムアウト（秒）
MAX_TIMEOUT: float = 120.0


@dataclass
class BinaryCallResult:
    """バイナリ実行結果を表すデータクラス。"""

    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """結果を辞書形式で返す。"""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
        }


def _resolve_base_dir(pack_id: str) -> Path:
    """Pack のバイナリ基準ディレクトリを解決する。

    ecosystem/<pack_id>/backend/ を基準ディレクトリとする。

    Args:
        pack_id: 対象 Pack の ID。

    Returns:
        基準ディレクトリの Path。
    """
    return Path("ecosystem") / pack_id / "backend"


def _validate_pack_id(pack_id: str) -> bool:
    """pack_id がパストラバーサルを含まないことを検証する。

    Args:
        pack_id: 検証対象の pack_id。

    Returns:
        安全であれば True。
    """
    if not pack_id or not isinstance(pack_id, str):
        return False
    if ".." in pack_id or "/" in pack_id or "\\" in pack_id:
        return False
    if pack_id.startswith("."):
        return False
    return True


def run(input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """バイナリファイルを実行し結果を返す。

    stdin に args の JSON を渡し、stdout から JSON を読み取る。
    パストラバーサル防止、タイムアウト制御、出力サイズ制限を備える。

    Args:
        input_data: 実行パラメータ。
            - pack_id (str): 対象 Pack の ID。
            - binary (str): バイナリファイルの相対パス。
            - args (dict): バイナリに渡す引数（JSON オブジェクト）。
            - timeout (float): タイムアウト秒数（デフォルト 30）。
        context: 実行コンテキスト（principal_id 等）。

    Returns:
        実行結果の辞書。success, output, error, error_type を含む。
    """
    pack_id = input_data.get("pack_id", "")
    binary = input_data.get("binary", "")
    args = input_data.get("args", {})
    timeout = input_data.get("timeout", DEFAULT_TIMEOUT)

    # --- pack_id 検証 ---
    if not _validate_pack_id(pack_id):
        return BinaryCallResult(
            success=False,
            error=f"Invalid pack_id: {pack_id}",
            error_type="security_violation",
        ).to_dict()

    # --- binary パス検証 ---
    if not binary or not isinstance(binary, str):
        return BinaryCallResult(
            success=False,
            error="Missing or invalid binary path",
            error_type="binary_not_found",
        ).to_dict()

    # --- タイムアウト正規化 ---
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(1.0, min(timeout, MAX_TIMEOUT))

    # --- パストラバーサル防止 ---
    base_dir = _resolve_base_dir(pack_id)
    binary_path = (base_dir / binary).resolve()
    base_dir_resolved = base_dir.resolve()

    try:
        if not binary_path.is_relative_to(base_dir_resolved):
            return BinaryCallResult(
                success=False,
                error="Binary path escapes allowed directory",
                error_type="security_violation",
            ).to_dict()
    except (TypeError, ValueError):
        return BinaryCallResult(
            success=False,
            error="Binary path validation failed",
            error_type="security_violation",
        ).to_dict()

    # --- バイナリ存在確認 ---
    if not binary_path.is_file():
        return BinaryCallResult(
            success=False,
            error=f"Binary not found: {binary}",
            error_type="binary_not_found",
        ).to_dict()

    # --- 実行権限確認 ---
    if not os.access(str(binary_path), os.X_OK):
        return BinaryCallResult(
            success=False,
            error=f"Binary is not executable: {binary}",
            error_type="binary_not_found",
        ).to_dict()

    # --- 入力 JSON 構築 ---
    input_json = json.dumps(
        {"context": context, "args": args},
        ensure_ascii=False,
        default=str,
    )

    # --- サブプロセス実行 ---
    try:
        proc = subprocess.run(
            [str(binary_path)],
            input=input_json,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(base_dir_resolved),
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Binary call timed out: pack_id=%s, binary=%s, timeout=%s",
            pack_id, binary, timeout,
        )
        return BinaryCallResult(
            success=False,
            error=f"Binary execution timed out after {timeout}s",
            error_type="timeout",
        ).to_dict()
    except FileNotFoundError:
        return BinaryCallResult(
            success=False,
            error=f"Binary not found at execution time: {binary}",
            error_type="binary_not_found",
        ).to_dict()
    except OSError as exc:
        logger.error(
            "Binary call OS error: pack_id=%s, binary=%s, error=%s",
            pack_id, binary, exc,
        )
        return BinaryCallResult(
            success=False,
            error=f"Execution error: {exc}",
            error_type="execution_error",
        ).to_dict()

    # --- 終了コード確認 ---
    if proc.returncode != 0:
        stderr_snippet = (proc.stderr or "").strip()[:500]
        return BinaryCallResult(
            success=False,
            error=f"Binary exited with code {proc.returncode}: {stderr_snippet}",
            error_type="execution_error",
        ).to_dict()

    # --- 出力サイズ確認 ---
    stdout = proc.stdout or ""
    if len(stdout.encode("utf-8")) > MAX_OUTPUT_SIZE:
        return BinaryCallResult(
            success=False,
            error="Output exceeds size limit (1MB)",
            error_type="execution_error",
        ).to_dict()

    # --- 出力 JSON パース ---
    stdout_stripped = stdout.strip()
    if not stdout_stripped:
        return BinaryCallResult(success=True, output=None).to_dict()

    try:
        parsed = json.loads(stdout_stripped)
    except json.JSONDecodeError as exc:
        return BinaryCallResult(
            success=False,
            error=f"Binary output is not valid JSON: {exc}",
            error_type="invalid_json_output",
        ).to_dict()

    return BinaryCallResult(success=True, output=parsed).to_dict()
