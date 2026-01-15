# chat_manager.py
import os
import json
import uuid
import shutil
import time
import stat
import time as time_module
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone


# ============================================
# 標準形式のヘルパー関数
# ============================================

def generate_message_id() -> str:
    """ユニークなメッセージIDを生成"""
    return f"msg-{uuid.uuid4().hex[:12]}"


def generate_tool_call_id() -> str:
    """ユニークなツールコールIDを生成"""
    return f"call-{uuid.uuid4().hex[:12]}"


def get_iso_timestamp() -> str:
    """ISO 8601形式のタイムスタンプを取得"""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def create_standard_history(conversation_id: str = None, title: str = "新しいチャット") -> Dict[str, Any]:
    """
    空の標準形式履歴を作成
    
    Args:
        conversation_id: 会話ID（省略時は自動生成）
        title: チャットタイトル
    
    Returns:
        標準形式の履歴辞書
    """
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())
    
    now = get_iso_timestamp()
    
    return {
        "conversation_id": conversation_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "platform": None,
        "model": None,
        "schema_version": "2.0",
        "current_node": None,
        "mapping": {},
        "messages": [],
        "is_pinned": False,
        "folder": None,
        "active_tools": None,
        "active_supporters": []
    }


def create_standard_message(
    role: str,
    content: Optional[str] = None,
    parent_id: Optional[str] = None,
    message_id: Optional[str] = None,
    attachments: Optional[List[Dict]] = None,
    tool_calls: Optional[List[Dict]] = None,
    tool_call_id: Optional[str] = None,
    status: str = "completed"
) -> Dict[str, Any]:
    """
    標準形式のメッセージを作成
    
    Args:
        role: "system", "user", "assistant", "tool"
        content: メッセージ内容
        parent_id: 親メッセージID
        message_id: メッセージID（省略時は自動生成）
        attachments: 添付ファイルリスト
        tool_calls: ツール呼び出しリスト（assistant用）
        tool_call_id: ツールコールID（tool用）
        status: メッセージステータス
    
    Returns:
        標準形式のメッセージ辞書
    """
    if message_id is None:
        message_id = generate_message_id()
    
    message = {
        "message_id": message_id,
        "role": role,
        "content": content,
        "timestamp": get_iso_timestamp(),
        "parent_id": parent_id,
        "children": [],
        "status": status
    }
    
    if attachments:
        message["attachments"] = attachments
    
    if tool_calls:
        message["tool_calls"] = tool_calls
    
    if tool_call_id:
        message["tool_call_id"] = tool_call_id
    
    return message


def add_message_to_history(history: Dict, message: Dict) -> Dict:
    """
    履歴にメッセージを追加し、mappingを自動更新
    
    Args:
        history: 標準形式の履歴
        message: 追加するメッセージ
    
    Returns:
        更新された履歴
    """
    message_id = message["message_id"]
    parent_id = message.get("parent_id")
    
    # メッセージを追加
    history["messages"].append(message)
    
    # mappingを更新
    history["mapping"][message_id] = {
        "id": message_id,
        "parent": parent_id,
        "children": []
    }
    
    # 親のchildrenを更新
    if parent_id and parent_id in history["mapping"]:
        if message_id not in history["mapping"][parent_id]["children"]:
            history["mapping"][parent_id]["children"].append(message_id)
        # メッセージオブジェクトのchildrenも更新
        for msg in history["messages"]:
            if msg["message_id"] == parent_id:
                if "children" not in msg:
                    msg["children"] = []
                if message_id not in msg["children"]:
                    msg["children"].append(message_id)
                break
    
    # current_nodeを更新
    history["current_node"] = message_id
    history["updated_at"] = get_iso_timestamp()
    
    return history


def get_conversation_thread(history: Dict, node_id: Optional[str] = None) -> List[Dict]:
    """
    mappingを辿って、ルートから指定ノードまでの線形スレッドを取得
    
    Args:
        history: 標準形式の履歴
        node_id: 終点ノードID（省略時はcurrent_node）
    
    Returns:
        メッセージのリスト（ルートから順番）
    """
    if node_id is None:
        node_id = history.get("current_node")
    
    if not node_id or not history.get("mapping"):
        return []
    
    # ノードIDからルートまで遡る
    path = []
    current = node_id
    
    while current:
        path.append(current)
        mapping_entry = history["mapping"].get(current)
        if not mapping_entry:
            break
        current = mapping_entry.get("parent")
    
    # 逆順にしてルートから順番にする
    path.reverse()
    
    # メッセージIDからメッセージを取得
    messages_by_id = {msg["message_id"]: msg for msg in history.get("messages", [])}
    
    return [messages_by_id[msg_id] for msg_id in path if msg_id in messages_by_id]


def convert_attachment_from_legacy(file_info: Dict) -> Dict:
    """
    旧形式のファイル情報を標準形式のattachmentに変換
    
    Args:
        file_info: 旧形式のファイル情報
    
    Returns:
        標準形式のattachment
    """
    file_type = file_info.get("type", "application/octet-stream")
    
    # タイプを判定
    if file_type.startswith("image/"):
        attachment_type = "image"
    elif file_type.startswith("video/"):
        attachment_type = "video"
    elif file_type.startswith("audio/"):
        attachment_type = "audio"
    else:
        attachment_type = "file"
    
    return {
        "type": attachment_type,
        "mime_type": file_type,
        "url": file_info.get("path", ""),
        "name": file_info.get("name", "unknown")
    }


def migrate_legacy_format(legacy_data: Dict) -> Dict:
    """
    旧形式の履歴を標準形式に変換
    
    Args:
        legacy_data: 旧形式の履歴データ
    
    Returns:
        標準形式の履歴データ
    """
    # 既に標準形式（schema_version 2.0）の場合はそのまま返す
    if legacy_data.get("schema_version") == "2.0":
        return legacy_data
    
    metadata = legacy_data.get("metadata", {})
    
    # 新しい標準形式の履歴を作成
    history = create_standard_history(
        conversation_id=metadata.get("id"),
        title=metadata.get("title", "新しいチャット")
    )
    
    # メタデータを引き継ぐ
    history["is_pinned"] = metadata.get("is_pinned", False)
    history["folder"] = metadata.get("folder")
    history["active_tools"] = metadata.get("active_tools", None)
    history["active_supporters"] = metadata.get("active_supporters", [])
    
    # 旧形式のメッセージを変換
    old_messages = legacy_data.get("messages", [])
    last_message_id = None
    
    for old_msg in old_messages:
        msg_type = old_msg.get("type")
        
        # システムメッセージはスキップ（イベントログとして別管理）
        if msg_type == "system":
            continue
        
        # ロールを変換
        if msg_type == "user":
            role = "user"
        elif msg_type == "ai":
            role = "assistant"
        else:
            continue
        
        # 添付ファイルを変換
        attachments = None
        if old_msg.get("files"):
            attachments = [convert_attachment_from_legacy(f) for f in old_msg["files"]]
        
        # ツール実行がある場合
        tool_executions = old_msg.get("tool_executions", [])
        
        if role == "assistant" and tool_executions:
            # ツール呼び出しを含むassistantメッセージ
            tool_calls = []
            for exec_info in tool_executions:
                tool_call_id = generate_tool_call_id()
                tool_calls.append({
                    "tool_call_id": tool_call_id,
                    "function_name": exec_info.get("function_name", ""),
                    "arguments": exec_info.get("args", {}),
                    "_exec_info": exec_info  # 後で参照するため一時保存
                })
            
            # 最初のツール実行のAI説明を取得
            first_explanation = None
            if tool_executions and tool_executions[0].get("ai_explanation"):
                first_explanation = tool_executions[0].get("ai_explanation")
            
            # tool_callsを持つassistantメッセージを作成
            assistant_msg = create_standard_message(
                role="assistant",
                content=first_explanation,
                parent_id=last_message_id,
                tool_calls=[{
                    "tool_call_id": tc["tool_call_id"],
                    "function_name": tc["function_name"],
                    "arguments": tc["arguments"]
                } for tc in tool_calls]
            )
            history = add_message_to_history(history, assistant_msg)
            last_message_id = assistant_msg["message_id"]
            
            # 各ツール実行結果をtoolメッセージとして追加
            for tc in tool_calls:
                exec_info = tc["_exec_info"]
                result = exec_info.get("result", {})
                
                tool_msg = create_standard_message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                    parent_id=last_message_id,
                    tool_call_id=tc["tool_call_id"]
                )
                history = add_message_to_history(history, tool_msg)
                last_message_id = tool_msg["message_id"]
            
            # 最終的なテキスト応答があれば追加
            if old_msg.get("text"):
                final_msg = create_standard_message(
                    role="assistant",
                    content=old_msg["text"],
                    parent_id=last_message_id
                )
                history = add_message_to_history(history, final_msg)
                last_message_id = final_msg["message_id"]
        else:
            # 通常のメッセージ
            message = create_standard_message(
                role=role,
                content=old_msg.get("text"),
                parent_id=last_message_id,
                attachments=attachments
            )
            history = add_message_to_history(history, message)
            last_message_id = message["message_id"]
    
    return history


class ChatManager:
    def __init__(self, chats_dir: str = None):
        if chats_dir is None:
            # エコシステム経由でパス解決を試みる
            try:
                from backend_core.ecosystem.compat import get_chats_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    chats_dir = get_chats_dir()
                else:
                    chats_dir = 'chats'
            except ImportError:
                chats_dir = 'chats'
        
        self.chats_dir = Path(chats_dir)
        if not self.chats_dir.exists():
            self.chats_dir.mkdir(parents=True)
        self.ui_history_lock = threading.Lock()  # UI履歴用のロック
    
    def create_chat(self, folder_name: Optional[str] = None) -> Dict[str, Any]:
        """新しいチャットを作成"""
        chat_id = str(uuid.uuid4())
        history = create_standard_history(conversation_id=chat_id)
        history["folder"] = folder_name
        
        return {
            'title': history['title'],
            'is_pinned': history['is_pinned'],
            'folder': folder_name,
            'id': chat_id,
            'created_at': history['created_at']
        }
    
    def find_chat_path(self, chat_id: str) -> Optional[Path]:
        """チャットIDからフルパスを検索"""
        # ルート直下を確認
        root_path = self.chats_dir / chat_id
        if root_path.exists() and root_path.is_dir():
            return root_path
        
        # サブフォルダ内を検索
        for item in self.chats_dir.iterdir():
            if item.is_dir() and not self._is_valid_uuid(str(item.name)):
                sub_path = item / chat_id
                if sub_path.exists() and sub_path.is_dir():
                    return sub_path
        return None
    
    def get_chat_metadata(self, chat_id: str) -> Tuple[Dict, bool]:
        """チャットのメタデータと空かどうかを取得"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            chat_path = self.chats_dir / chat_id
        
        history_file = chat_path / 'history.json'
        default_meta = {'title': '新しいチャット', 'is_pinned': False, 'folder': None}
        is_empty = True
        
        if not history_file.exists():
            return default_meta, is_empty
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 標準形式（2.0）の場合
            if data.get("schema_version") == "2.0":
                metadata = {
                    'title': data.get('title', '新しいチャット'),
                    'is_pinned': data.get('is_pinned', False),
                    'folder': data.get('folder')
                }
                # userまたはassistantメッセージがあれば空ではない
                for msg in data.get('messages', []):
                    if msg.get('role') in ('user', 'assistant'):
                        is_empty = False
                        break
            # 旧形式（1.0）の場合
            elif data.get("schema_version") == "1.0":
                metadata = data.get('metadata', default_meta)
                if len(data.get('messages', [])) > 0:
                    is_empty = False
            # さらに古い形式
            else:
                metadata = data.get('metadata', default_meta)
                if len(data.get('messages', [])) > 0:
                    is_empty = False
            
            if 'folder' not in metadata:
                metadata['folder'] = None
            return metadata, is_empty
        except (json.JSONDecodeError, IndexError):
            return default_meta, is_empty
    
    def get_all_chats(self) -> Dict[str, Any]:
        """すべてのチャットを取得"""
        pinned_list, folders, uncategorized_list = [], {}, []
        
        for item in self.chats_dir.iterdir():
            if item.is_dir():
                if self._is_valid_uuid(item.name):
                    # 通常のチャット
                    history_file = item / 'history.json'
                    if history_file.exists():
                        meta, is_empty = self.get_chat_metadata(item.name)
                        meta['id'] = item.name
                        meta['is_empty'] = is_empty
                        
                        try:
                            meta['mtime'] = item.stat().st_mtime
                            if meta.get('is_pinned'):
                                pinned_list.append(meta)
                            else:
                                uncategorized_list.append(meta)
                        except:
                            pass
                else:
                    # フォルダ
                    folder_name = item.name
                    if folder_name not in folders:
                        folders[folder_name] = []
                    
                    # フォルダ内のチャットを検索
                    for sub_item in item.iterdir():
                        if sub_item.is_dir() and self._is_valid_uuid(sub_item.name):
                            history_file = sub_item / 'history.json'
                            if history_file.exists():
                                meta, is_empty = self._get_chat_metadata_with_path(sub_item)
                                meta['id'] = sub_item.name
                                meta['is_empty'] = is_empty
                                meta['folder'] = folder_name
                                
                                try:
                                    meta['mtime'] = sub_item.stat().st_mtime
                                    folders[folder_name].append(meta)
                                except:
                                    pass
        
        # ソート
        pinned_list.sort(key=lambda x: x.get('mtime', 0), reverse=True)
        uncategorized_list.sort(key=lambda x: x.get('mtime', 0), reverse=True)
        for folder_name in folders:
            folders[folder_name].sort(key=lambda x: x.get('mtime', 0), reverse=True)
        
        return {'pinned': pinned_list, 'folders': folders, 'uncategorized': uncategorized_list}
    
    def load_chat_history(self, chat_id: str) -> Dict[str, Any]:
        """チャット履歴を読み込む（標準形式で返す）"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            raise FileNotFoundError(f"Chat {chat_id} not found")
        
        history_file = chat_path / 'history.json'
        if history_file.exists():
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 旧形式の場合はマイグレーション
            if data.get("schema_version") != "2.0":
                print(f"[Migration] Converting chat {chat_id} to standard format...")
                data = migrate_legacy_format(data)
                # マイグレーション後のデータを保存
                self.save_chat_history(chat_id, data)
            
            # active_tools フィールドがない場合はデフォルト値を補完
            if "active_tools" not in data:
                data["active_tools"] = None
            
            # active_supporters フィールドがない場合はデフォルト値を補完
            if "active_supporters" not in data:
                data["active_supporters"] = []
            
            return data
        else:
            # 新規作成
            return create_standard_history(conversation_id=chat_id)
    
    def save_chat_history(self, chat_id: str, data: Dict[str, Any], folder: Optional[str] = None):
        """チャット履歴を保存（標準形式）"""
        if folder:
            chat_path = self.chats_dir / folder / chat_id
        else:
            chat_path = self.find_chat_path(chat_id)
            if not chat_path:
                chat_path = self.chats_dir / chat_id
        
        chat_path.mkdir(parents=True, exist_ok=True)
        (chat_path / 'user_input').mkdir(exist_ok=True)
        
        # updated_atを更新
        data["updated_at"] = get_iso_timestamp()
        
        # schema_versionを確保
        if "schema_version" not in data:
            data["schema_version"] = "2.0"
        
        history_file = chat_path / 'history.json'
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def update_chat_metadata(self, chat_id: str, metadata: Dict[str, Any]):
        """チャットのメタデータを更新"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            raise FileNotFoundError(f"Chat {chat_id} not found")
        
        history_file = chat_path / 'history.json'
        
        # ファイルが存在しない場合は作成
        if not history_file.exists():
            chat_path.mkdir(parents=True, exist_ok=True)
            chat_data = create_standard_history(conversation_id=chat_id)
        else:
            with open(history_file, 'r', encoding='utf-8') as f:
                chat_data = json.load(f)
            
            # 旧形式の場合はマイグレーション
            if chat_data.get("schema_version") != "2.0":
                chat_data = migrate_legacy_format(chat_data)
        
        # フォルダ変更の処理
        if 'folder' in metadata:
            new_folder = metadata['folder']
            old_path = chat_path
            
            if new_folder:
                new_folder = self._sanitize_folder_name(new_folder)
                new_folder_path = self.chats_dir / new_folder
                new_folder_path.mkdir(exist_ok=True)
                new_path = new_folder_path / chat_id
            else:
                new_path = self.chats_dir / chat_id
            
            if old_path != new_path:
                if new_path.exists():
                    self._force_remove_tree(new_path)
                shutil.move(str(old_path), str(new_path))
                chat_path = new_path
                chat_data['folder'] = new_folder
        
        # その他のメタデータ更新
        if 'title' in metadata:
            chat_data['title'] = metadata['title']
        if 'is_pinned' in metadata:
            chat_data['is_pinned'] = metadata['is_pinned']
        
        # active_tools の更新
        if 'active_tools' in metadata:
            # None, [], または文字列リストを許可
            active_tools = metadata['active_tools']
            if active_tools is None or isinstance(active_tools, list):
                chat_data['active_tools'] = active_tools
        
        # active_supporters の更新
        if 'active_supporters' in metadata:
            active_supporters = metadata['active_supporters']
            if isinstance(active_supporters, list):
                # リスト内の要素が全て文字列かチェック
                if all(isinstance(s, str) for s in active_supporters):
                    chat_data['active_supporters'] = active_supporters
        
        chat_data['updated_at'] = get_iso_timestamp()
        
        # 保存
        with open(chat_path / 'history.json', 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
    
    def delete_chat(self, chat_id: str):
        """チャットを削除"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            raise FileNotFoundError(f"Chat {chat_id} not found")
        
        if chat_path.exists() and chat_path.is_dir():
            success = self._force_remove_tree(chat_path)
            if not success:
                raise Exception(f"Failed to delete chat directory: {chat_path}")
    
    def copy_chat(self, chat_id: str) -> str:
        """チャットを複製"""
        source_path = self.find_chat_path(chat_id)
        if not source_path:
            raise FileNotFoundError(f"Source chat {chat_id} not found")
        
        new_chat_id = str(uuid.uuid4())
        
        # コピー元と同じフォルダ構造を保持
        if source_path.parent != self.chats_dir:
            folder_name = source_path.parent.name
            dest_path = self.chats_dir / folder_name / new_chat_id
        else:
            dest_path = self.chats_dir / new_chat_id
        
        dest_path.mkdir(parents=True)
        (dest_path / 'user_input').mkdir()
        
        # 履歴をコピー
        source_history = source_path / 'history.json'
        dest_history = dest_path / 'history.json'
        
        with open(source_history, 'r', encoding='utf-8') as f:
            chat_data = json.load(f)
        
        # 標準形式（2.0）の場合
        if chat_data.get("schema_version") == "2.0":
            chat_data['title'] = chat_data.get('title', 'コピー') + ' (コピー)'
            chat_data['is_pinned'] = False
            chat_data['conversation_id'] = new_chat_id
            chat_data['created_at'] = get_iso_timestamp()
            chat_data['updated_at'] = get_iso_timestamp()
        # 旧形式の場合
        elif 'metadata' in chat_data:
            chat_data['metadata']['title'] = chat_data['metadata'].get('title', 'コピー') + ' (コピー)'
            chat_data['metadata']['is_pinned'] = False
        
        with open(dest_history, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
        
        return new_chat_id
    
    def create_folder(self, folder_name: str) -> str:
        """フォルダを作成"""
        if not folder_name or not folder_name.strip():
            raise ValueError("Folder name is required")
        
        folder_name = self._sanitize_folder_name(folder_name.strip())
        folder_path = self.chats_dir / folder_name
        folder_path.mkdir(exist_ok=True)
        return folder_name
    
    # UI履歴関連のメソッド
    def load_ui_history(self, chat_id: str) -> Dict[str, Any]:
        """UI履歴を読み込む（ロック不要、読み込みのみ）"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            return {
                'tool_logs': [],
                'ui_state': {}
            }
        
        ui_history_file = chat_path / 'ui_history.json'
        if ui_history_file.exists():
            try:
                with open(ui_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {
                    'tool_logs': [],
                    'ui_state': {}
                }
        else:
            return {
                'tool_logs': [],
                'ui_state': {}
            }
    
    def save_ui_history(self, chat_id: str, ui_data: Dict[str, Any]):
        """UI履歴を保存（この関数は直接呼ばない、append_tool_log経由で使用）"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            chat_path = self.chats_dir / chat_id
            chat_path.mkdir(parents=True, exist_ok=True)
        
        ui_history_file = chat_path / 'ui_history.json'
        with open(ui_history_file, 'w', encoding='utf-8') as f:
            json.dump(ui_data, f, ensure_ascii=False, indent=2)
    
    def append_tool_log(self, chat_id: str, log_entry: Dict[str, Any]) -> str:
        """ツールログを追加（スレッドセーフ）"""
        with self.ui_history_lock:
            # 既存のUI履歴を読み込み
            ui_data = self.load_ui_history(chat_id)
            
            # ログエントリにIDとタイムスタンプを追加
            if 'message_id' not in log_entry:
                log_entry['message_id'] = str(uuid.uuid4())
            if 'timestamp' not in log_entry:
                log_entry['timestamp'] = time.time()
            
            # ログを追加
            ui_data['tool_logs'].append(log_entry)
            
            # 保存（ロック内で直接保存）
            chat_path = self.find_chat_path(chat_id)
            if not chat_path:
                chat_path = self.chats_dir / chat_id
                chat_path.mkdir(parents=True, exist_ok=True)
            
            ui_history_file = chat_path / 'ui_history.json'
            with open(ui_history_file, 'w', encoding='utf-8') as f:
                json.dump(ui_data, f, ensure_ascii=False, indent=2)
            
            return log_entry['message_id']
    
    def get_tool_logs_for_execution(self, chat_id: str, execution_id: str) -> List[Dict[str, Any]]:
        """特定の実行IDに関連するツールログを取得"""
        ui_data = self.load_ui_history(chat_id)
        return [
            log for log in ui_data.get('tool_logs', [])
            if log.get('execution_id') == execution_id
        ]
    
    def clear_ui_history(self, chat_id: str):
        """UI履歴をクリア"""
        chat_path = self.find_chat_path(chat_id)
        if chat_path:
            ui_history_file = chat_path / 'ui_history.json'
            if ui_history_file.exists():
                ui_history_file.unlink()
    
    def update_ui_state(self, chat_id: str, state_key: str, state_value: Any):
        """UI状態を更新"""
        with self.ui_history_lock:
            ui_data = self.load_ui_history(chat_id)
            
            if 'ui_state' not in ui_data:
                ui_data['ui_state'] = {}
            
            ui_data['ui_state'][state_key] = state_value
            
            # 保存
            chat_path = self.find_chat_path(chat_id)
            if not chat_path:
                chat_path = self.chats_dir / chat_id
                chat_path.mkdir(parents=True, exist_ok=True)
            
            ui_history_file = chat_path / 'ui_history.json'
            with open(ui_history_file, 'w', encoding='utf-8') as f:
                json.dump(ui_data, f, ensure_ascii=False, indent=2)
    
    # ユーティリティメソッド
    def _is_valid_uuid(self, uuid_string: str) -> bool:
        """有効なUUIDかチェック"""
        try:
            uuid.UUID(str(uuid_string))
            return True
        except ValueError:
            return False
    
    def _sanitize_folder_name(self, name: str) -> str:
        """フォルダ名をサニタイズ"""
        invalid_chars = '<>:"|?*\\/\0'
        for char in invalid_chars:
            name = name.replace(char, '_')
        name = name.strip(' .')
        if not name:
            name = 'untitled'
        
        # 既存のフォルダと重複しない名前を生成
        existing_folders = set()
        for item in self.chats_dir.iterdir():
            if item.is_dir() and not self._is_valid_uuid(item.name):
                existing_folders.add(item.name)
        
        if name not in existing_folders:
            return name[:255]
        
        counter = 1
        while f"{name}_{counter}" in existing_folders:
            counter += 1
        return f"{name}_{counter}"[:255]
    
    def _get_chat_metadata_with_path(self, chat_path: Path) -> Tuple[Dict, bool]:
        """パスを指定してメタデータを取得"""
        history_file = chat_path / 'history.json'
        default_meta = {'title': '新しいチャット', 'is_pinned': False, 'folder': None}
        is_empty = True
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 標準形式（2.0）の場合
                if data.get("schema_version") == "2.0":
                    metadata = {
                        'title': data.get('title', '新しいチャット'),
                        'is_pinned': data.get('is_pinned', False),
                        'folder': data.get('folder')
                    }
                    # userまたはassistantメッセージがあれば空ではない
                    for msg in data.get('messages', []):
                        if msg.get('role') in ('user', 'assistant'):
                            is_empty = False
                            break
                # 旧形式（1.0）の場合
                elif data.get("schema_version") == "1.0":
                    metadata = data.get('metadata', default_meta)
                    if len(data.get('messages', [])) > 0:
                        is_empty = False
                # さらに古い形式
                else:
                    metadata = data.get('metadata', default_meta)
                    if len(data.get('messages', [])) > 0:
                        is_empty = False
                
                if 'folder' not in metadata:
                    metadata['folder'] = None
                
                return metadata, is_empty
            except (json.JSONDecodeError, IOError):
                pass
        
        return default_meta, is_empty
    
    def _force_remove_tree(self, path: Path) -> bool:
        """ディレクトリを強制削除"""
        def handle_remove_readonly(func, path, exc):
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)
                func(path)
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if path.exists():
                    if os.name == 'nt':
                        shutil.rmtree(path, onerror=handle_remove_readonly)
                    else:
                        shutil.rmtree(path)
                    return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    time_module.sleep(0.5)
                else:
                    raise e
        return False
    
    # ===========================
    # Chat Config (確定仕様)
    # ===========================
    
    def load_chat_config(self, chat_id: str) -> Dict[str, Any]:
        """
        チャット構成を読み込む（historyとは分離：確定仕様）。
        
        保存先:
          user_data/chats/<chat_id>/chat_config.json
        
        互換:
          chat_config.json が無い場合は、history.json から推定して初期化する（fail-soft）。
        """
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            # チャットディレクトリが無い場合でも、設定はデフォルトで返す
            return self._default_chat_config()
        
        cfg_file = chat_path / "chat_config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return self._normalize_chat_config(data)
            except Exception:
                pass
        
        # フォールバック：historyから推定して作成（fail-soft）
        inferred = self._default_chat_config()
        try:
            history = self.load_chat_history(chat_id)
            if isinstance(history, dict):
                # 旧互換：historyに残っている可能性があるフィールドを反映
                if history.get("model"):
                    inferred["model"] = history.get("model")
                if "active_tools" in history:
                    inferred["active_tools"] = history.get("active_tools")
                if "active_supporters" in history:
                    inferred["active_supporters"] = history.get("active_supporters") or []
        except Exception:
            pass
        
        # 初期化して保存（fail-soft：保存失敗でも返す）
        try:
            self.save_chat_config(chat_id, inferred)
        except Exception:
            pass
        
        return self._normalize_chat_config(inferred)
    
    def save_chat_config(self, chat_id: str, config: Dict[str, Any]) -> None:
        """chat_config.json を保存（確定仕様）"""
        chat_path = self.find_chat_path(chat_id)
        if not chat_path:
            # 新規チャットディレクトリ生成
            chat_path = self.chats_dir / chat_id
            chat_path.mkdir(parents=True, exist_ok=True)
            (chat_path / "user_input").mkdir(exist_ok=True)
        
        cfg_file = chat_path / "chat_config.json"
        normalized = self._normalize_chat_config(config or {})
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
    
    def update_chat_config(self, chat_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """chat_config.json を部分更新して保存し、更新後を返す"""
        current = self.load_chat_config(chat_id)
        if isinstance(updates, dict):
            current.update(updates)
        current = self._normalize_chat_config(current)
        self.save_chat_config(chat_id, current)
        return current
    
    def _default_chat_config(self) -> Dict[str, Any]:
        """chat_config のデフォルト（推奨キー。必須ではない）"""
        return {
            # チャット既定モデル（payloadが無い場合に参照）
            "model": None,
            # ツール構成：None=all, []=none, ["a","b"]=allowlist
            "active_tools": None,
            # サポーター構成
            "active_supporters": [],
            # チャット既定プロンプトID
            "prompt": "normal_prompt",
            # 既定thinking_budget（UIの既定として使える）
            "thinking_budget": 0,
        }
    
    def _normalize_chat_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """型崩れを吸収して正規化（fail-soft）"""
        base = self._default_chat_config()
        if not isinstance(data, dict):
            return base
        
        out = dict(base)
        out.update(data)
        
        # active_tools: None / list を許容
        at = out.get("active_tools", None)
        if at is not None and not isinstance(at, list):
            out["active_tools"] = None
        if isinstance(out.get("active_tools"), list):
            out["active_tools"] = [x for x in out["active_tools"] if isinstance(x, str)]
        
        # active_supporters: list[str]
        sup = out.get("active_supporters", [])
        if not isinstance(sup, list):
            sup = []
        out["active_supporters"] = [x for x in sup if isinstance(x, str)]
        
        # model/prompt: str or None
        if out.get("model") is not None and not isinstance(out.get("model"), str):
            out["model"] = None
        if out.get("prompt") is not None and not isinstance(out.get("prompt"), str):
            out["prompt"] = "normal_prompt"
        
        # thinking_budget: int
        tb = out.get("thinking_budget", 0)
        try:
            out["thinking_budget"] = int(tb)
        except Exception:
            out["thinking_budget"] = 0
        
        return out
