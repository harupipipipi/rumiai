"""
Agent Runtime - ツールに提供するシステム操作APIセット
AIエージェントが他のエージェントと協調し、ファイルシステムを操作するためのインターフェース
"""

import os
import json
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

# chat_managerから標準形式ヘルパーをインポート
from chat_manager import (
    create_standard_history,
    create_standard_message,
    add_message_to_history,
    get_conversation_thread,
    generate_message_id,
    get_iso_timestamp
)


class FileSystemInterface:
    """
    安全なファイルシステム操作インターフェース
    パストラバーサル攻撃を防止し、指定されたベースディレクトリ内のみアクセス可能
    """
    
    def __init__(self, base_path: Path):
        """
        Args:
            base_path: 操作を許可するベースディレクトリ
        """
        self.base_path = Path(base_path).resolve()
        # ディレクトリが存在しなければ作成
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _validate_path(self, filename: str) -> Path:
        """
        パスを検証し、安全な絶対パスを返す
        
        Args:
            filename: ファイル名またはサブパス
        
        Returns:
            検証済みの絶対パス
        
        Raises:
            ValueError: パスがベースディレクトリ外を指す場合
        """
        # 絶対パスを拒否
        if os.path.isabs(filename):
            raise ValueError(f"絶対パスは許可されていません: {filename}")
        
        # パスを正規化
        requested_path = (self.base_path / filename).resolve()
        
        # ベースディレクトリ外へのアクセスを検出
        try:
            requested_path.relative_to(self.base_path)
        except ValueError:
            raise ValueError(f"ディレクトリ外へのアクセスは許可されていません: {filename}")
        
        return requested_path
    
    def read(self, filename: str, encoding: str = 'utf-8') -> str:
        """
        ファイルを読み込む
        
        Args:
            filename: ファイル名
            encoding: 文字エンコーディング
        
        Returns:
            ファイル内容
        """
        file_path = self._validate_path(filename)
        
        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {filename}")
        
        if not file_path.is_file():
            raise ValueError(f"ファイルではありません: {filename}")
        
        return file_path.read_text(encoding=encoding)
    
    def read_bytes(self, filename: str) -> bytes:
        """バイナリファイルを読み込む"""
        file_path = self._validate_path(filename)
        
        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {filename}")
        
        return file_path.read_bytes()
    
    def write(self, filename: str, content: str, encoding: str = 'utf-8') -> str:
        """
        ファイルに書き込む
        
        Args:
            filename: ファイル名
            content: 書き込む内容
            encoding: 文字エンコーディング
        
        Returns:
            書き込んだファイルのパス
        """
        file_path = self._validate_path(filename)
        
        # 親ディレクトリを作成
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_path.write_text(content, encoding=encoding)
        return str(file_path)
    
    def write_bytes(self, filename: str, content: bytes) -> str:
        """バイナリファイルに書き込む"""
        file_path = self._validate_path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return str(file_path)
    
    def append(self, filename: str, content: str, encoding: str = 'utf-8') -> str:
        """ファイルに追記する"""
        file_path = self._validate_path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'a', encoding=encoding) as f:
            f.write(content)
        
        return str(file_path)
    
    def exists(self, filename: str) -> bool:
        """ファイルまたはディレクトリが存在するか確認"""
        try:
            file_path = self._validate_path(filename)
            return file_path.exists()
        except ValueError:
            return False
    
    def is_file(self, filename: str) -> bool:
        """ファイルかどうか確認"""
        try:
            file_path = self._validate_path(filename)
            return file_path.is_file()
        except ValueError:
            return False
    
    def is_dir(self, filename: str) -> bool:
        """ディレクトリかどうか確認"""
        try:
            file_path = self._validate_path(filename)
            return file_path.is_dir()
        except ValueError:
            return False
    
    def list_files(self, subdir: str = "", recursive: bool = False) -> List[str]:
        """
        ファイル一覧を取得
        
        Args:
            subdir: サブディレクトリ（省略時はルート）
            recursive: 再帰的に検索するか
        
        Returns:
            ファイルパスのリスト（ベースパスからの相対パス）
        """
        if subdir:
            target_path = self._validate_path(subdir)
        else:
            target_path = self.base_path
        
        if not target_path.exists():
            return []
        
        if not target_path.is_dir():
            raise ValueError(f"ディレクトリではありません: {subdir}")
        
        files = []
        if recursive:
            for file_path in target_path.rglob("*"):
                if file_path.is_file():
                    files.append(str(file_path.relative_to(self.base_path)))
        else:
            for file_path in target_path.iterdir():
                if file_path.is_file():
                    files.append(str(file_path.relative_to(self.base_path)))
        
        return sorted(files)
    
    def list_dirs(self, subdir: str = "") -> List[str]:
        """ディレクトリ一覧を取得"""
        if subdir:
            target_path = self._validate_path(subdir)
        else:
            target_path = self.base_path
        
        if not target_path.exists():
            return []
        
        dirs = []
        for item in target_path.iterdir():
            if item.is_dir():
                dirs.append(str(item.relative_to(self.base_path)))
        
        return sorted(dirs)
    
    def delete(self, filename: str) -> bool:
        """
        ファイルを削除
        
        Args:
            filename: ファイル名
        
        Returns:
            削除成功の可否
        """
        file_path = self._validate_path(filename)
        
        if not file_path.exists():
            return False
        
        if file_path.is_file():
            file_path.unlink()
            return True
        
        return False
    
    def mkdir(self, dirname: str) -> str:
        """ディレクトリを作成"""
        dir_path = self._validate_path(dirname)
        dir_path.mkdir(parents=True, exist_ok=True)
        return str(dir_path)
    
    def get_path(self) -> str:
        """ベースパスを取得"""
        return str(self.base_path)
    
    def get_full_path(self, filename: str) -> str:
        """ファイルの完全パスを取得"""
        file_path = self._validate_path(filename)
        return str(file_path)


class AgentRuntime:
    """
    Agent Runtime - ツールに提供するシステム操作APIセット
    
    ツール開発者は context['runtime'] 経由でこのクラスのメソッドにアクセスできる。
    
    使用例:
        def execute(args, context):
            runtime = context['runtime']
            
            # 新しいエージェントを作成
            agent_id = runtime.create_agent("Research Agent", system_prompt="...")
            
            # エージェントにメッセージを送信
            response = runtime.send_message(agent_id, "調査してください")
            
            # ワークスペースにファイルを保存
            runtime.workspace(agent_id).write("result.md", response)
            
            # 共有ストレージからデータを読み込む
            data = runtime.shared_storage.read("knowledge.txt")
    """
    
    def __init__(
        self,
        chat_manager,
        relationship_manager,
        ai_invoke_callback: Callable[[str, str, str, str], str],
        current_chat_id: str,
        chats_dir: str = None,
        userdata_dir: str = None
    ):
        """
        Args:
            chat_manager: ChatManagerインスタンス
            relationship_manager: RelationshipManagerインスタンス
            ai_invoke_callback: AIを呼び出すコールバック関数
                                (chat_id, message, model_id, system_prompt) -> response_text
            current_chat_id: 現在のチャットID（親として使用）
            chats_dir: チャットディレクトリのパス
            userdata_dir: 共有ストレージディレクトリのパス
        """
        self.chat_manager = chat_manager
        self.relationship_manager = relationship_manager
        self._ai_invoke_callback = ai_invoke_callback
        self.current_chat_id = current_chat_id
        
        # エコシステム経由でパス解決
        if chats_dir is None:
            try:
                from backend_core.ecosystem.compat import get_chats_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    chats_dir = str(get_chats_dir())
                else:
                    chats_dir = 'chats'
            except ImportError:
                chats_dir = 'chats'
        
        if userdata_dir is None:
            try:
                from backend_core.ecosystem.compat import get_shared_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    userdata_dir = str(get_shared_dir())
                else:
                    userdata_dir = 'user_data/shared'
            except ImportError:
                userdata_dir = 'user_data/shared'
        
        self.chats_dir = Path(chats_dir)
        self.userdata_dir = Path(userdata_dir)
        
        # 共有ストレージインターフェース（遅延初期化）
        self._shared_storage: Optional[FileSystemInterface] = None
        
        # ワークスペースキャッシュ
        self._workspace_cache: Dict[str, FileSystemInterface] = {}
        
        # 現在のモデルID（send_message時に使用）
        self.default_model_id = "gemini-2.5-flash"
    
    @property
    def shared_storage(self) -> FileSystemInterface:
        """
        共有ストレージへのインターフェース
        
        userdata/ ディレクトリへの読み書きを提供する。
        すべてのチャット・エージェントで共有される永続的なストレージ。
        
        Returns:
            FileSystemInterface インスタンス
        """
        if self._shared_storage is None:
            self._shared_storage = FileSystemInterface(self.userdata_dir)
        return self._shared_storage
    
    def workspace(self, chat_id: str = None) -> FileSystemInterface:
        """
        チャットのワークスペースへのインターフェース
        
        chats/[chat_id]/workspace/ ディレクトリへの読み書きを提供する。
        各チャット固有の作業領域として使用。
        
        Args:
            chat_id: チャットID（省略時は現在のチャット）
        
        Returns:
            FileSystemInterface インスタンス
        """
        if chat_id is None:
            chat_id = self.current_chat_id
        
        if chat_id not in self._workspace_cache:
            workspace_path = self.chats_dir / chat_id / 'workspace'
            self._workspace_cache[chat_id] = FileSystemInterface(workspace_path)
        
        return self._workspace_cache[chat_id]
    
    def create_agent(
        self,
        name: str,
        system_prompt: str = None,
        model_id: str = None
    ) -> str:
        """
        新しいエージェント（チャット）を作成し、親子関係を設定
        
        Args:
            name: エージェント名（チャットのタイトルとして使用）
            system_prompt: システムプロンプト（省略時はデフォルト）
            model_id: 使用するモデルID（省略時はデフォルト）
        
        Returns:
            作成されたチャットのID
        """
        # 新しいチャットを作成
        chat_metadata = self.chat_manager.create_chat()
        new_chat_id = chat_metadata['id']
        
        # 履歴を作成してタイトルを設定
        history = create_standard_history(conversation_id=new_chat_id, title=name)
        
        # モデル情報を設定
        history['model'] = model_id or self.default_model_id
        
        # システムプロンプトがある場合は保存（メタデータとして）
        if system_prompt:
            # system_prompt はAI呼び出し時に使用するため、履歴にはメタデータとして保存
            history['agent_config'] = {
                'system_prompt': system_prompt,
                'created_by': self.current_chat_id,
                'created_at': get_iso_timestamp()
            }
        
        # 履歴を保存
        self.chat_manager.save_chat_history(new_chat_id, history)
        
        # 親子関係を作成
        if self.relationship_manager:
            self.relationship_manager.link(
                source=self.current_chat_id,
                target=new_chat_id,
                link_type="parent_child",
                metadata={
                    "agent_name": name,
                    "created_at": get_iso_timestamp()
                }
            )
        
        print(f"[AgentRuntime] 新しいエージェントを作成: {name} (ID: {new_chat_id})")
        
        return new_chat_id
    
    def get_history(self, chat_id: str = None) -> Dict[str, Any]:
        """
        チャットの履歴を取得
        
        Args:
            chat_id: チャットID（省略時は現在のチャット）
        
        Returns:
            標準形式の履歴データ
        """
        if chat_id is None:
            chat_id = self.current_chat_id
        
        try:
            return self.chat_manager.load_chat_history(chat_id)
        except FileNotFoundError:
            return create_standard_history(conversation_id=chat_id)
    
    def get_conversation_messages(self, chat_id: str = None) -> List[Dict[str, Any]]:
        """
        チャットの会話メッセージをリスト形式で取得
        
        Args:
            chat_id: チャットID（省略時は現在のチャット）
        
        Returns:
            メッセージのリスト（古い順）
        """
        history = self.get_history(chat_id)
        return get_conversation_thread(history)
    
    def send_message(
        self,
        chat_id: str,
        message: str,
        sender: str = "Tool",
        wait_for_response: bool = True
    ) -> str:
        """
        指定したチャットにメッセージを送信し、AIの応答を取得
        
        これにより、ツールが「部下のエージェントに指示を出して結果を受け取る」
        動きが可能になる。
        
        Args:
            chat_id: 送信先のチャットID
            message: 送信するメッセージ
            sender: 送信者名（メタデータとして記録）
            wait_for_response: AIの応答を待つかどうか
        
        Returns:
            AIの応答テキスト
        """
        # チャットの履歴を読み込む
        try:
            history = self.chat_manager.load_chat_history(chat_id)
        except FileNotFoundError:
            history = create_standard_history(conversation_id=chat_id)
        
        # システムプロンプトを取得（agent_configがあれば）
        system_prompt = None
        if 'agent_config' in history:
            system_prompt = history['agent_config'].get('system_prompt')
        
        # モデルIDを取得
        model_id = history.get('model', self.default_model_id)
        
        # ユーザーメッセージを履歴に追加
        user_msg = create_standard_message(
            role="user",
            content=message,
            parent_id=history.get('current_node')
        )
        # 送信者情報をメタデータとして追加
        user_msg['sender'] = sender
        user_msg['sent_via'] = 'agent_runtime'
        
        history = add_message_to_history(history, user_msg)
        
        # 履歴を保存（ユーザーメッセージ）
        self.chat_manager.save_chat_history(chat_id, history)
        
        if not wait_for_response:
            return ""
        
        # AIを呼び出す（コールバック経由）
        try:
            response_text = self._ai_invoke_callback(
                chat_id,
                message,
                model_id,
                system_prompt
            )
        except Exception as e:
            print(f"[AgentRuntime] AI呼び出しエラー: {e}")
            import traceback
            traceback.print_exc()
            response_text = f"エラーが発生しました: {str(e)}"
        
        # AIの応答を履歴に追加
        history = self.chat_manager.load_chat_history(chat_id)  # 最新を再読み込み
        
        ai_msg = create_standard_message(
            role="assistant",
            content=response_text,
            parent_id=history.get('current_node')
        )
        history = add_message_to_history(history, ai_msg)
        
        # 履歴を保存（AI応答）
        self.chat_manager.save_chat_history(chat_id, history)
        
        print(f"[AgentRuntime] エージェント {chat_id} からの応答を取得 ({len(response_text)}文字)")
        
        return response_text
    
    def get_child_agents(self) -> List[Dict[str, Any]]:
        """
        現在のチャットの子エージェント一覧を取得
        
        Returns:
            子エージェントの情報リスト
        """
        if not self.relationship_manager:
            return []
        
        links = self.relationship_manager.get_related(
            self.current_chat_id,
            link_type="parent_child",
            direction="outgoing"
        )
        
        agents = []
        for link in links:
            child_id = link['target']
            try:
                history = self.chat_manager.load_chat_history(child_id)
                agents.append({
                    'id': child_id,
                    'name': history.get('title', '無題'),
                    'model': history.get('model'),
                    'created_at': link.get('metadata', {}).get('created_at')
                })
            except FileNotFoundError:
                pass
        
        return agents
    
    def get_parent_agent(self) -> Optional[str]:
        """
        現在のチャットの親エージェントIDを取得
        
        Returns:
            親エージェントのID（存在しない場合はNone）
        """
        if not self.relationship_manager:
            return None
        
        links = self.relationship_manager.get_related(
            self.current_chat_id,
            link_type="parent_child",
            direction="incoming"
        )
        
        if links:
            return links[0]['source']
        return None
    
    def get_current_chat_id(self) -> str:
        """現在のチャットIDを取得"""
        return self.current_chat_id
    
    def set_default_model(self, model_id: str):
        """デフォルトモデルIDを設定"""
        self.default_model_id = model_id
    
    def log(self, message: str, level: str = "info"):
        """
        ログメッセージを出力
        
        Args:
            message: ログメッセージ
            level: ログレベル（info, warning, error）
        """
        prefix = {
            "info": "[AgentRuntime INFO]",
            "warning": "[AgentRuntime WARNING]",
            "error": "[AgentRuntime ERROR]"
        }.get(level, "[AgentRuntime]")
        
        print(f"{prefix} {message}")
