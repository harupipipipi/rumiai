"""
Storage コンポーネント セットアップ
"""

def run(context: dict):
    interface_registry = context.get("interface_registry")
    mounts = context.get("paths", {}).get("mounts", {})
    
    # FileManagerをサービスとして登録
    try:
        from .file_manager import FileManager
        
        # chatsのマウントを参照（依存関係）
        chats_path = mounts.get("data.chats", "./user_data/chats")
        manager = FileManager(chats_dir=chats_path)
        
        if interface_registry:
            interface_registry.register(
                "service.file_manager",
                manager,
                meta={"component": "storage:storage_v1", "version": "1.0.0"}
            )
        
        print("[storage/setup] FileManager registered")
    except Exception as e:
        print(f"[storage/setup] FileManager登録エラー: {e}")
