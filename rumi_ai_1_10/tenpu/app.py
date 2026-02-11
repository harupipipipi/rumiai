#!/usr/bin/env python3
"""
Rumi AI OS - エントリポイント

Kernelを起動し、Packが提供するサービス（HTTPサーバー等）を開始する。
Flask/dotenv等の特定フレームワークには依存しない。

HTTPサーバーが必要な場合:
  Packが io.http.server をInterfaceRegistryに登録する。
"""

import sys
import atexit
import argparse
import traceback

_kernel = None


def main():
    global _kernel
    
    parser = argparse.ArgumentParser(description="Rumi AI OS")
    parser.add_argument("--headless", action="store_true", help="Run without HTTP server")
    parser.add_argument("--permissive", action="store_true", help="Run in permissive security mode (development only)")
    args = parser.parse_args()
    
    # セキュリティモード設定
    if args.permissive:
        import os
        os.environ["RUMI_SECURITY_MODE"] = "permissive"
    
    try:
        from core_runtime import Kernel
        from core_runtime.lang import L, load_system_lang
        
        # Langシステム初期化
        load_system_lang()
        
        _kernel = Kernel()
        
        print(f"[Rumi] {L('startup.starting')}")
        _kernel.run_startup()
        
        atexit.register(lambda: _kernel.shutdown() if _kernel else None)
        
        try:
            from backend_core.ecosystem.compat import mark_ecosystem_initialized
            mark_ecosystem_initialized()
        except Exception:
            pass
        
        print(f"[Rumi] {L('startup.success')}")
        
        if args.headless:
            print(f"[Rumi] {L('startup.headless')}")
            return
        
        # HTTPサーバーがPackから提供されている場合は起動
        http_server = _kernel.interface_registry.get("io.http.server")
        if http_server and callable(http_server):
            print(f"[Rumi] {L('startup.http_starting')}")
            http_server(_kernel)
        else:
            print(f"[Rumi] {L('startup.no_http')}")
            print(f"[Rumi] {L('startup.install_http_pack')}")
            print(f"[Rumi] {L('startup.press_ctrl_c')}")
            _wait_for_signal()
        
    except KeyboardInterrupt:
        print(f"\n[Rumi] {L('shutdown.starting')}")
    except Exception as e:
        print(f"[Rumi] {L('startup.failed')}: {e}")
        traceback.print_exc()
        sys.exit(1)


def _wait_for_signal():
    """シグナル待機（プラットフォーム対応）"""
    try:
        import signal
        signal.pause()
    except AttributeError:
        # Windows
        import time
        while True:
            time.sleep(1)


if __name__ == '__main__':
    main()
