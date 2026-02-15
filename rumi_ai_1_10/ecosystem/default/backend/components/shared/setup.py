"""
Shared コンポーネント セットアップ

共有ユーティリティをsys.pathに追加し、他コンポーネントから利用可能にする。
"""

def run(context: dict):
    from pathlib import Path
    
    # このコンポーネントのパスをsys.pathに追加
    try:
        from backend_core.ecosystem.compat import add_to_sys_path
        
        component_path = str(Path(__file__).parent)
        add_to_sys_path(component_path)
        
        print("[shared/setup] Utils path added to sys.path")
    except Exception as e:
        print(f"[shared/setup] エラー: {e}")
