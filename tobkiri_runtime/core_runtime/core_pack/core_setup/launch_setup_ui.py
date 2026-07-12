"""
launch_setup_ui.py - セットアップ UI をブラウザで開く

pack_api_server のポート（デフォルト 8765）を使用して
セットアップ UI の URL をブラウザで開く。

InterfaceRegistry から setup.check_result を取得し、
needs_setup == True の場合のみブラウザを開く。

注意: React UI の静的ファイル配信は別途実装が必要（このスクリプトのスコープ外）。
ここでは URL を開くだけ。
"""

import os
import webbrowser


def launch_setup_ui(port=None):
    """
    セットアップ UI をデフォルトブラウザで開く。

    Args:
        port: pack_api_server のポート番号。
              None の場合は環境変数 RUMI_API_PORT またはデフォルト 8765。

    Returns:
        {"launched": bool, "url": str, "error": str or None}
    """
    if port is None:
        port = int(os.environ.get("RUMI_API_PORT", "8765"))

    url = "http://localhost:{}/setup".format(port)

    try:
        webbrowser.open(url)
        return {"launched": True, "url": url, "error": None}
    except Exception as e:
        return {"launched": False, "url": url, "error": str(e)}


# --- Kernel exec_python entry point ---
# Only launches if setup.check_result indicates needs_setup == True.
if __name__ != "__main__":
    _ctx = locals()
    _ir = _ctx.get("interface_registry")
    _should_launch = False
    if _ir is not None:
        _check_result = _ir.get("setup.check_result", strategy="last")
        if isinstance(_check_result, dict) and _check_result.get("needs_setup"):
            _should_launch = True
    if _should_launch:
        _result = launch_setup_ui()
        if _ir is not None:
            _ir.register(
                "setup.launch_result",
                _result,
                meta={"source": "core_setup.launch_setup_ui"},
            )
