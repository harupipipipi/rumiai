"""
Chats コンポーネント セットアップ

起動時に実行され、マウントとサービスを登録する。
"""

def run(context: dict):
    """
    セットアップエントリーポイント
    
    Args:
        context: Kernelから渡されるコンテキスト
            - interface_registry: サービス登録用
            - install_journal: 生成物記録用
            - paths.mounts: 現在のマウント
    """
    from pathlib import Path
    
    interface_registry = context.get("interface_registry")
    install_journal = context.get("install_journal")
    mounts = context.get("paths", {}).get("mounts", {})
    
    # 1. マウントを登録
    try:
        from backend_core.ecosystem.compat import register_mount_from_component
        
        # chats用マウントを登録（既存があればスキップ）
        if "data.chats" not in mounts:
            register_mount_from_component("data.chats", "./user_data/chats")
        
        # chatsディレクトリを作成
        chats_dir = Path("./user_data/chats")
        chats_dir.mkdir(parents=True, exist_ok=True)
        
        if install_journal:
            install_journal.append({
                "event": "mount_register",
                "scope": "component",
                "ref": "chats:chats_v1",
                "result": "success",
                "paths": {"created": [str(chats_dir)]},
                "meta": {"mount_key": "data.chats"}
            })
    except Exception as e:
        print(f"[chats/setup] マウント登録エラー: {e}")
    
    # 2. ChatManagerをサービスとして登録
    try:
        from .chat_manager import ChatManager
        
        # chatsディレクトリを解決
        chats_path = mounts.get("data.chats", "./user_data/chats")
        manager = ChatManager(chats_dir=chats_path)
        
        if interface_registry:
            interface_registry.register(
                "service.chats",
                manager,
                meta={"component": "chats:chats_v1", "version": "1.0.0"}
            )
        
        print("[chats/setup] ChatManager registered as service.chats")
    except Exception as e:
        print(f"[chats/setup] ChatManager登録エラー: {e}")
    
    # 3. RelationshipManagerをサービスとして登録
    try:
        from .relationship_manager import RelationshipManager
        
        chats_path = mounts.get("data.chats", "./user_data/chats")
        rel_manager = RelationshipManager(chats_dir=chats_path)
        
        if interface_registry:
            interface_registry.register(
                "service.relationships",
                rel_manager,
                meta={"component": "chats:chats_v1", "version": "1.0.0"}
            )
        
        print("[chats/setup] RelationshipManager registered as service.relationships")
    except Exception as e:
        print(f"[chats/setup] RelationshipManager登録エラー: {e}")
    
    # 4. 旧chatsディレクトリからの移行（存在する場合）
    _migrate_legacy_chats(install_journal)


def _migrate_legacy_chats(install_journal):
    """旧 ./chats から user_data/chats への移行"""
    from pathlib import Path
    import shutil
    
    legacy_chats = Path("./chats")
    new_chats = Path("./user_data/chats")
    
    if not legacy_chats.exists():
        return
    
    if not new_chats.exists():
        new_chats.mkdir(parents=True, exist_ok=True)
    
    # 既にデータがあればスキップ
    existing_items = list(new_chats.iterdir()) if new_chats.exists() else []
    if len(existing_items) > 0:
        return
    
    migrated = []
    try:
        for item in legacy_chats.iterdir():
            dest = new_chats / item.name
            if not dest.exists():
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
                migrated.append(str(dest))
        
        if migrated and install_journal:
            install_journal.append({
                "event": "migrate",
                "scope": "component",
                "ref": "chats:chats_v1",
                "result": "success",
                "paths": {"created": migrated},
                "meta": {"from": str(legacy_chats), "to": str(new_chats)}
            })
        
        if migrated:
            print(f"[chats/setup] Migrated {len(migrated)} items from ./chats")
    except Exception as e:
        print(f"[chats/setup] 移行エラー: {e}")
