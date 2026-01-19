"""
Storage コンポーネント セットアップ

ファイル管理サービスを提供する。
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
    interface_registry = context.get("interface_registry")
    install_journal = context.get("install_journal")
    mounts = context.get("paths", {}).get("mounts", {})
    
    # FileManagerをサービスとして登録
    try:
        from .file_manager import FileManager
        
        # chatsのマウントを参照（依存関係）
        chats_path = mounts.get("data.chats", "./user_data/chats")
        
        # FileManagerにinterface_registryを渡す（ChatManager取得用）
        manager = FileManager(chats_dir=chats_path, interface_registry=interface_registry)
        
        if interface_registry:
            interface_registry.register(
                "service.file_manager",
                manager,
                meta={"component": "storage:storage_v1", "version": "1.0.0"}
            )
        
        if install_journal:
            install_journal.append({
                "event": "service_register",
                "scope": "component",
                "ref": "storage:storage_v1",
                "result": "success",
                "paths": {"created": [], "modified": []},
                "meta": {"service_key": "service.file_manager"}
            })
        
        print("[storage/setup] FileManager registered")
    except Exception as e:
        print(f"[storage/setup] FileManager登録エラー: {e}")
        
        if install_journal:
            install_journal.append({
                "event": "service_register",
                "scope": "component",
                "ref": "storage:storage_v1",
                "result": "failed",
                "paths": {"created": [], "modified": []},
                "meta": {"error": str(e)}
            })
