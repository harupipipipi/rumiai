#!/usr/bin/env python3
"""
Rumi AI OS - エントリポイント

Kernelを起動し、Packが提供するサービス（HTTPサーバー等）を開始する。
Flask/dotenv等の特定フレームワークには依存しない。

HTTPサーバーが必要な場合:
  Packが io.http.server をInterfaceRegistryに登録する。

Wave 19-A 変更:
  VULN-C01: production 環境での --permissive 起動を拒否
  host_execution ガード: 未承認 Pack の起動時拒否
"""

import sys
import atexit
import argparse
import traceback

_kernel = None


# Fallback L() — overwritten if core_runtime.lang loads successfully
def L(key, **kwargs):
    return key


def _check_permissive_production_guard():
    """
    VULN-C01: production 環境で --permissive フラグが使用された場合に起動を拒否する。
    自動化を妨げないため確認プロンプトは入れない。
    """
    import os
    if os.environ.get("RUMI_ENVIRONMENT") == "production":
        print(
            "FATAL: --permissive flag is not allowed when "
            "RUMI_ENVIRONMENT=production.",
            file=sys.stderr,
        )
        print(
            "Remove --permissive or set RUMI_ENVIRONMENT to a "
            "non-production value.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    global _kernel

    parser = argparse.ArgumentParser(description="Rumi AI OS")
    parser.add_argument("--headless", action="store_true", help="Run without HTTP server")
    parser.add_argument("--permissive", action="store_true", help="Run in permissive security mode (development only)")
    parser.add_argument("--validate", action="store_true", help="Validate all Pack ecosystem.json files and exit")
    parser.add_argument("--health", action="store_true", help="Run health check and exit with status")
    args = parser.parse_args()

    # --- ログ設定 ---
    import os
    from core_runtime.logging_utils import configure_logging
    _log_level = os.environ.get("RUMI_LOG_LEVEL", "INFO")
    _log_format = os.environ.get("RUMI_LOG_FORMAT", "json")
    configure_logging(level=_log_level, fmt=_log_format)

    # --- Health check mode (early exit) ---
    if args.health:
        from core_runtime.health import (
            get_health_checker, probe_disk_space, probe_file_writable,
        )
        import json
        checker = get_health_checker()
        checker.register_probe("disk", lambda: probe_disk_space("/"))
        checker.register_probe("writable_tmp", lambda: probe_file_writable("/tmp"))
        result = checker.aggregate_health()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "UP" else 1)

    # --- Pack validation mode (early exit) ---
    if args.validate:
        _run_validation()
        return

    # セキュリティモード設定 — デフォルトは strict（secure）
    if args.permissive:
        # VULN-C01: production 環境では --permissive を拒否
        _check_permissive_production_guard()

        # W19-B: production 環境では --permissive を拒否
        if os.environ.get("RUMI_ENVIRONMENT", "").lower() == "production":
            print("FATAL: --permissive cannot be used in production environment.", file=sys.stderr)
            sys.exit(1)
        os.environ["RUMI_SECURITY_MODE"] = "permissive"
        print("=" * 60)
        print("WARNING: Running in permissive mode. Sandbox is disabled.")
        print("Pack code may execute on host without Docker isolation.")
        print("Do NOT use --permissive in production.")
        print("=" * 60)
    else:
        # 明示的に strict を設定（外部環境変数による意図しない permissive 化を防止）
        os.environ.setdefault("RUMI_SECURITY_MODE", "strict")

    # --- host_execution ガード (W19-A) ---
    try:
        from core_runtime.pack_validator import validate_host_execution
        validate_host_execution()
    except SystemExit:
        raise
    except Exception:
        # Pack 探索に失敗してもメイン起動は妨げない（ecosystem 未構築時など）
        pass

    try:
        from core_runtime import Kernel
        try:
            from core_runtime.lang import L as _L, load_system_lang
            global L
            L = _L
        except ImportError:
            load_system_lang = lambda: None

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
        http_server = None

        # interface_overrides で優先 Pack が指定されていればそれを使う
        try:
            from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager
            aem = get_active_ecosystem_manager()
            override_pack = aem.get_interface_override("io.http.server")
            if override_pack:
                http_server = _kernel.interface_registry.get_by_owner(
                    "io.http.server", override_pack
                )
        except Exception:
            pass

        # override が見つからなければ通常の last を使う
        if http_server is None:
            http_server = _kernel.interface_registry.get("io.http.server")
        if http_server and callable(http_server):
            print(f"[Rumi] {L('startup.http_starting')}")
            # Wave 17-A: KernelFacade でラップし、Pack コードへの Kernel 直接参照を遮断
            from core_runtime.kernel_facade import KernelFacade
            http_server(KernelFacade(_kernel))
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


def _run_validation():
    """Pack ecosystem.json を検証し結果を出力する。"""
    from core_runtime.pack_validator import validate_packs

    report = validate_packs()

    for err in report.errors:
        print(f"ERROR: {err}")
    for warn in report.warnings:
        print(f"WARNING: {warn}")

    summary = (
        f"{report.pack_count} packs scanned, {report.valid_count} valid, "
        f"{len(report.warnings)} warnings, {len(report.errors)} errors"
    )
    print(summary)


if __name__ == '__main__':
    main()
