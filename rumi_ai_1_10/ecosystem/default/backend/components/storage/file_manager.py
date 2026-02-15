# file_manager.py - 自己完結版
import os
import json
import base64
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


class MimeTypeUtils:
    """MIMEタイプ関連のユーティリティ（インライン）"""
    
    EXT_MAP = {
        'text/plain': '.txt',
        'text/html': '.html',
        'text/csv': '.csv',
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'image/svg+xml': '.svg',
        'application/pdf': '.pdf',
        'application/json': '.json',
        'application/xml': '.xml',
        'application/zip': '.zip',
        'application/x-tar': '.tar',
        'application/gzip': '.gz',
        'audio/mpeg': '.mp3',
        'audio/wav': '.wav',
        'audio/ogg': '.ogg',
        'video/mp4': '.mp4',
        'video/mpeg': '.mpeg',
        'video/webm': '.webm',
    }
    
    @staticmethod
    def get_extension_from_mime(mime_type: str, file_name: Optional[str] = None) -> str:
        """MIMEタイプから拡張子を取得"""
        if mime_type in MimeTypeUtils.EXT_MAP:
            return MimeTypeUtils.EXT_MAP[mime_type]
        for key, ext in MimeTypeUtils.EXT_MAP.items():
            if key in mime_type:
                return ext
        if file_name:
            parts = file_name.rsplit('.', 1)
            if len(parts) > 1:
                return '.' + parts[1]
        return '.bin'
    
    @staticmethod
    def extract_mime_from_data_url(data_url: str) -> str:
        """Data URLからMIMEタイプを抽出"""
        if not data_url.startswith('data:'):
            return 'application/octet-stream'
        try:
            header = data_url.split(',')[0]
            if ';' in header:
                mime_info = header.split(';')[0]
                if ':' in mime_info:
                    return mime_info.split(':')[1]
        except:
            pass
        return 'application/octet-stream'


class FileManager:
    """ファイル管理（自己完結・InterfaceRegistry経由でChatManager取得）"""
    
    def __init__(self, chats_dir: str = None, interface_registry=None):
        """
        Args:
            chats_dir: チャットディレクトリ（setup.pyから注入される）
            interface_registry: InterfaceRegistry（サービス取得用）
        """
        if chats_dir is None:
            chats_dir = 'user_data/chats'
        self.chats_dir = Path(chats_dir)
        self._ir = interface_registry
        self.temp_files = []
    
    def _get_chat_manager(self):
        """InterfaceRegistry経由でChatManagerを取得"""
        if self._ir:
            return self._ir.get("service.chats", strategy="last")
        return None
    
    def _find_chat_path(self, chat_id: str) -> Optional[Path]:
        """ChatManagerを使わずにチャットパスを検索"""
        import uuid as uuid_mod
        
        def is_valid_uuid(s):
            try:
                uuid_mod.UUID(str(s))
                return True
            except ValueError:
                return False
        
        # ルート直下を確認
        root_path = self.chats_dir / chat_id
        if root_path.exists() and root_path.is_dir():
            return root_path
        
        # サブフォルダ内を検索
        if self.chats_dir.exists():
            for item in self.chats_dir.iterdir():
                if item.is_dir() and not is_valid_uuid(item.name):
                    sub_path = item / chat_id
                    if sub_path.exists() and sub_path.is_dir():
                        return sub_path
        return None
    
    def process_uploaded_files(self, files_info: List[Dict]) -> Tuple[List[str], List[str]]:
        """
        アップロードされたファイルを処理して一時ファイルを作成
        
        Returns:
            Tuple[List[str], List[str]]: (ファイルパスのリスト, 一時ファイルパスのリスト)
        """
        current_file_paths = []
        temp_files_to_clean = []
        
        for file_info in files_info:
            try:
                if 'path' in file_info and file_info['path'].startswith('data:'):
                    # Data URLからファイルデータを抽出
                    file_path, temp_path = self._process_data_url_file(file_info)
                    if file_path:
                        current_file_paths.append(file_path)
                        temp_files_to_clean.append(temp_path)
                        print(f"一時ファイル作成: {temp_path}")
                elif 'path' in file_info:
                    # 既存のファイルパス
                    if os.path.exists(file_info['path']):
                        current_file_paths.append(file_info['path'])
                else:
                    print(f"警告: 無効なファイル形式: {file_info}")
            except Exception as e:
                print(f"Error processing file {file_info.get('name')}: {e}")
        
        print(f"処理されたファイル数: {len(current_file_paths)}")
        return current_file_paths, temp_files_to_clean
    
    def _process_data_url_file(self, file_info: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Data URLファイルを処理"""
        try:
            data_url = file_info['path']
            header, encoded_data = data_url.split(',', 1)
            file_data = base64.b64decode(encoded_data)
            
            # MIMEタイプを取得
            mime_type = MimeTypeUtils.extract_mime_from_data_url(data_url)
            
            # ファイル拡張子を決定
            ext = MimeTypeUtils.get_extension_from_mime(mime_type, file_info.get('name'))
            
            # 一時ファイルを作成
            suffix = f"_{file_info.get('name', 'tempfile')}" if file_info.get('name') else ext
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name
            
            print(f"一時ファイル作成: {temp_path} ({mime_type})")
            return temp_path, temp_path
            
        except Exception as e:
            print(f"Data URLファイル処理エラー: {e}")
            return None, None
    
    def save_tool_files(self, chat_id: str, tool_files: List[Dict]) -> List[Dict]:
        """
        ツールが返したファイルをチャットディレクトリに保存
        
        Args:
            chat_id: チャットID
            tool_files: ツールが返したファイル情報のリスト
            
        Returns:
            保存されたファイル情報のリスト
        """
        chat_path = self._find_chat_path(chat_id)
        if not chat_path:
            chat_path = self.chats_dir / chat_id
        
        # ツール用のファイルディレクトリを作成
        tool_files_dir = chat_path / "tool_files"
        tool_files_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        
        for file_info in tool_files:
            if "path" in file_info and os.path.exists(file_info["path"]):
                src_path = Path(file_info["path"])
                file_name = src_path.name
                
                # ファイル名が重複する場合は番号を付ける
                dest_path = tool_files_dir / file_name
                counter = 1
                while dest_path.exists():
                    name_parts = file_name.rsplit('.', 1)
                    if len(name_parts) > 1:
                        dest_path = tool_files_dir / f"{name_parts[0]}_{counter}.{name_parts[1]}"
                    else:
                        dest_path = tool_files_dir / f"{file_name}_{counter}"
                    counter += 1
                
                # ファイルをコピー
                shutil.copy2(src_path, dest_path)
                
                saved_files.append({
                    "original_path": str(src_path),
                    "saved_path": str(dest_path),
                    "file_name": dest_path.name,
                    "file_type": file_info.get("type", "application/octet-stream")
                })
                
                print(f"ツールファイル保存: {src_path} -> {dest_path}")
        
        # 履歴ファイルを更新
        self._update_history_with_tool_files(chat_path, saved_files)
        
        return saved_files
    
    def _update_history_with_tool_files(self, chat_path: Path, saved_files: List[Dict]):
        """履歴ファイルにツールファイル情報を追加"""
        history_file = chat_path / 'history.json'
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                # ツールファイル情報を記録
                if "tool_files" not in chat_data:
                    chat_data["tool_files"] = []
                chat_data["tool_files"].extend(saved_files)
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f, ensure_ascii=False, indent=2)
                    
                print(f"履歴ファイル更新: {len(saved_files)}個のツールファイルを記録")
            except Exception as e:
                print(f"Failed to update history with tool files: {e}")
    
    def cleanup_temp_files(self, temp_files: List[str]):
        """一時ファイルをクリーンアップ"""
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"一時ファイル削除: {temp_path}")
            except OSError as e:
                print(f"Temp file removal failed for {temp_path}: {e.strerror if hasattr(e, 'strerror') else e}")
    
    def save_user_file(self, chat_id: str, file_path: str, file_info: Dict) -> str:
        """
        ユーザーがアップロードしたファイルを保存
        
        Args:
            chat_id: チャットID
            file_path: ファイルのパス
            file_info: ファイル情報
            
        Returns:
            保存先のパス
        """
        chat_path = self._find_chat_path(chat_id)
        if not chat_path:
            chat_path = self.chats_dir / chat_id
            chat_path.mkdir(parents=True, exist_ok=True)
        
        # ユーザー入力ファイル用のディレクトリ
        user_input_dir = chat_path / "user_input"
        user_input_dir.mkdir(exist_ok=True)
        
        # ファイル名の決定
        file_name = file_info.get('name', 'uploaded_file')
        dest_path = user_input_dir / file_name
        
        # 重複チェック
        counter = 1
        while dest_path.exists():
            name_parts = file_name.rsplit('.', 1)
            if len(name_parts) > 1:
                dest_path = user_input_dir / f"{name_parts[0]}_{counter}.{name_parts[1]}"
            else:
                dest_path = user_input_dir / f"{file_name}_{counter}"
            counter += 1
        
        # ファイルをコピー
        shutil.copy2(file_path, dest_path)
        print(f"ユーザーファイル保存: {file_path} -> {dest_path}")
        
        return str(dest_path)
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """ファイル情報を取得"""
        path = Path(file_path)
        
        if not path.exists():
            return {
                'exists': False,
                'error': 'File not found'
            }
        
        stat_info = path.stat()
        
        return {
            'exists': True,
            'name': path.name,
            'size': stat_info.st_size,
            'modified': stat_info.st_mtime,
            'is_file': path.is_file(),
            'is_dir': path.is_dir(),
            'extension': path.suffix,
            'parent': str(path.parent)
        }
    
    def validate_file_upload(self, file_info: Dict) -> Tuple[bool, Optional[str]]:
        """
        ファイルアップロードの妥当性を検証
        
        Returns:
            Tuple[bool, Optional[str]]: (有効かどうか, エラーメッセージ)
        """
        # ファイルサイズチェック
        if 'size' in file_info:
            max_size_mb = 100  # 100MB制限
            max_size_bytes = max_size_mb * 1024 * 1024
            if file_info['size'] > max_size_bytes:
                return False, f"ファイルサイズが大きすぎます（最大{max_size_mb}MB）"
        
        # ファイルタイプチェック（必要に応じて）
        blocked_extensions = ['.exe', '.dll', '.bat', '.cmd', '.sh', '.app']
        if 'name' in file_info:
            file_ext = Path(file_info['name']).suffix.lower()
            if file_ext in blocked_extensions:
                return False, f"このファイルタイプはアップロードできません: {file_ext}"
        
        return True, None
    
    def create_file_preview(self, file_path: str, max_size: int = 1024) -> Optional[str]:
        """
        ファイルのプレビューを生成
        
        Args:
            file_path: ファイルパス
            max_size: プレビューの最大サイズ（バイト）
            
        Returns:
            プレビュー文字列またはNone
        """
        path = Path(file_path)
        
        if not path.exists() or not path.is_file():
            return None
        
        # テキストファイルの場合
        text_extensions = ['.txt', '.md', '.json', '.xml', '.csv', '.log', '.py', '.js', '.html', '.css']
        if path.suffix.lower() in text_extensions:
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(max_size)
                    if len(content) == max_size:
                        content += '\n... (truncated)'
                    return content
            except Exception as e:
                return f"Error reading file: {e}"
        
        return None
    
    def get_chat_files(self, chat_id: str) -> Dict[str, List[Dict]]:
        """
        チャットに関連するすべてのファイルを取得
        
        Returns:
            Dict with 'user_files' and 'tool_files' lists
        """
        chat_path = self._find_chat_path(chat_id)
        if not chat_path:
            return {'user_files': [], 'tool_files': []}
        
        result = {'user_files': [], 'tool_files': []}
        
        # ユーザーファイル
        user_input_dir = chat_path / "user_input"
        if user_input_dir.exists():
            for file_path in user_input_dir.iterdir():
                if file_path.is_file():
                    result['user_files'].append({
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })
        
        # ツールファイル
        tool_files_dir = chat_path / "tool_files"
        if tool_files_dir.exists():
            for file_path in tool_files_dir.iterdir():
                if file_path.is_file():
                    result['tool_files'].append({
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })
        
        return result
