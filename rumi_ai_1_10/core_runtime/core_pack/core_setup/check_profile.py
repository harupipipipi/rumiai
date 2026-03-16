"""
check_profile.py - profile.json の存在と有効性をチェックする

Kernel の _h_exec_python から呼ばれる。
結果は InterfaceRegistry の "setup.check_result" に格納される。

チェック項目:
- user_data/settings/profile.json の存在
- JSON として有効か
- schema_version が存在するか
- setup_completed フラグが true か
"""

import json
from pathlib import Path


def check_profile(base_dir=None):
    """
    profile.json の存在と有効性をチェックする。

    Args:
        base_dir: ソースコードルート（rumi_ai_1_10/）。
                  None の場合はこのファイルから相対パスで解決。

    Returns:
        {"needs_setup": bool, "reason": str}
    """
    if base_dir is None:
        # core_runtime/core_pack/core_setup/check_profile.py
        # -> parent x4 = rumi_ai_1_10/
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    profile_path = base_dir / "user_data" / "settings" / "profile.json"

    if not profile_path.exists():
        return {"needs_setup": True, "reason": "profile_not_found"}

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"needs_setup": True, "reason": "profile_invalid_json"}

    if not isinstance(data, dict):
        return {"needs_setup": True, "reason": "profile_not_dict"}

    if "schema_version" not in data:
        return {"needs_setup": True, "reason": "missing_schema_version"}

    if not data.get("setup_completed", False):
        return {"needs_setup": True, "reason": "setup_not_completed"}

    return {"needs_setup": False, "reason": "profile_valid"}


# --- Kernel exec_python entry point ---
# _h_exec_python runs exec() on this file.
# The exec_ctx dict is available via locals().
if __name__ != "__main__":
    _ctx = locals()
    _result = check_profile()
    if "interface_registry" in _ctx:
        _ctx["interface_registry"].register(
            "setup.check_result",
            _result,
            meta={"source": "core_setup.check_profile"},
        )
