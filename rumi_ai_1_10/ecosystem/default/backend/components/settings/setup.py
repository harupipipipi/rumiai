"""
Settings コンポーネント セットアップ
"""

def run(context: dict):
    from pathlib import Path
    
    interface_registry = context.get("interface_registry")
    install_journal = context.get("install_journal")
    mounts = context.get("paths", {}).get("mounts", {})
    
    # 1. マウントを登録
    try:
        from backend_core.ecosystem.compat import register_mount_from_component
        
        if "data.settings" not in mounts:
            register_mount_from_component("data.settings", "./user_data/settings")
        
        settings_dir = Path("./user_data/settings")
        settings_dir.mkdir(parents=True, exist_ok=True)
        
        # user_data直下も確保
        user_data_dir = Path("./user_data")
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        if install_journal:
            install_journal.append({
                "event": "mount_register",
                "scope": "component",
                "ref": "settings:settings_v1",
                "result": "success",
                "paths": {"created": [str(settings_dir)]},
                "meta": {"mount_key": "data.settings"}
            })
    except Exception as e:
        print(f"[settings/setup] マウント登録エラー: {e}")
    
    # 2. SettingsManagerをサービスとして登録
    try:
        from .settings_manager import SettingsManager
        
        user_data_path = "./user_data"
        manager = SettingsManager(user_data_dir=user_data_path)
        
        if interface_registry:
            interface_registry.register(
                "service.settings_manager",
                manager,
                meta={"component": "settings:settings_v1", "version": "1.0.0"}
            )
        
        print("[settings/setup] SettingsManager registered")
    except Exception as e:
        print(f"[settings/setup] SettingsManager登録エラー: {e}")
