# utils.py
import os
import uuid
import stat
import time
import shutil
from pathlib import Path
from typing import Optional, Set

class PathUtils:
    """パス関連のユーティリティ"""
    
    @staticmethod
    def is_valid_uuid(uuid_string: str) -> bool:
        """文字列が有効なUUIDかどうかを判定"""
        try:
            uuid.UUID(str(uuid_string))
            return True
        except ValueError:
            return False
    
    @staticmethod
    def sanitize_folder_name(name: str) -> str:
        """フォルダ名として使用できない文字を除去"""
        # Windowsで使えない文字を置換
        invalid_chars = '<>:"|?*\\/\0'
        for char in invalid_chars:
            name = name.replace(char, '_')
        # 先頭・末尾の空白とピリオドを削除
        name = name.strip(' .')
        # 空の場合はデフォルト名
        if not name:
            name = 'untitled'
        return name[:255]  # 最大長を制限
    
    @staticmethod
    def get_unique_folder_name(base_name: str, existing_folders: Set[str]) -> str:
        """既存のフォルダと重複しない名前を生成"""
        sanitized_name = PathUtils.sanitize_folder_name(base_name)
        if sanitized_name not in existing_folders:
            return sanitized_name
        
        counter = 1
        while f"{sanitized_name}_{counter}" in existing_folders:
            counter += 1
        return f"{sanitized_name}_{counter}"
    
    @staticmethod
    def force_remove_tree(path: Path) -> bool:
        """Windowsでも確実にディレクトリを削除する"""
        def handle_remove_readonly(func, path, exc):
            """読み取り専用ファイルも削除できるようにする"""
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)
                func(path)
        
        # 複数回試行
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if path.exists():
                    # Windowsの場合、onexcパラメータを使用
                    if os.name == 'nt':  # Windows
                        shutil.rmtree(path, onerror=handle_remove_readonly)
                    else:
                        shutil.rmtree(path)
                    return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"削除試行 {attempt + 1} 失敗: {e}")
                    time.sleep(0.5)  # 少し待機
                else:
                    raise e
        return False


class MimeTypeUtils:
    """MIMEタイプ関連のユーティリティ"""
    
    @staticmethod
    def get_extension_from_mime(mime_type: str, file_name: Optional[str] = None) -> str:
        """MIMEタイプから拡張子を取得"""
        ext_map = {
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
        
        # 完全一致を試す
        if mime_type in ext_map:
            return ext_map[mime_type]
        
        # 部分一致を試す
        for key, ext in ext_map.items():
            if key in mime_type:
                return ext
        
        # ファイル名から拡張子を取得
        if file_name:
            name_parts = file_name.rsplit('.', 1)
            if len(name_parts) > 1:
                return '.' + name_parts[1]
        
        # デフォルト
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


class ValidationUtils:
    """バリデーション関連のユーティリティ"""
    
    @staticmethod
    def validate_chat_id(chat_id: str) -> bool:
        """チャットIDの妥当性を検証"""
        if not chat_id:
            return False
        return PathUtils.is_valid_uuid(chat_id)
    
    @staticmethod
    def validate_file_size(file_size: int, max_size_mb: int = 100) -> bool:
        """ファイルサイズの妥当性を検証"""
        max_size_bytes = max_size_mb * 1024 * 1024
        return 0 < file_size <= max_size_bytes
    
    @staticmethod
    def validate_folder_name(folder_name: str) -> bool:
        """フォルダ名の妥当性を検証"""
        if not folder_name or not folder_name.strip():
            return False
        
        # 予約語チェック
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                         'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                         'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
        
        if folder_name.upper() in reserved_names:
            return False
        
        # 無効な文字チェック
        invalid_chars = '<>:"|?*\\/\0'
        for char in invalid_chars:
            if char in folder_name:
                return False
        
        return True


class ErrorHandler:
    """エラーハンドリング関連のユーティリティ"""
    
    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """リトライ可能なエラーかどうかを判定"""
        error_str = str(error)
        retryable_patterns = [
            '500 INTERNAL',
            '502 BAD GATEWAY',
            '503 SERVICE UNAVAILABLE',
            '504 GATEWAY TIMEOUT',
            'INTERNAL',
            'ConnectionError',
            'TimeoutError'
        ]
        
        for pattern in retryable_patterns:
            if pattern in error_str.upper():
                return True
        return False
    
    @staticmethod
    def get_error_message(error: Exception) -> str:
        """エラーメッセージを取得"""
        error_str = str(error)
        
        # 特定のエラーに対するカスタムメッセージ
        if '500 INTERNAL' in error_str:
            return 'サーバー内部エラーが発生しました。しばらく待ってから再度お試しください。'
        elif '503' in error_str:
            return 'サービスが一時的に利用できません。しばらく待ってから再度お試しください。'
        elif 'Duplicate function declaration' in error_str:
            return 'ツールの定義が重複しています。ツールを再読み込みしてください。'
        elif 'API key' in error_str.lower():
            return 'APIキーが無効です。設定を確認してください。'
        elif 'rate limit' in error_str.lower():
            return 'APIのレート制限に達しました。しばらく待ってから再度お試しください。'
        
        return error_str


class ResponseFormatter:
    """レスポンスフォーマット関連のユーティリティ"""
    
    @staticmethod
    def success_response(data: dict = None, message: str = None) -> tuple:
        """成功レスポンスを生成"""
        response = {'success': True}
        if data:
            response.update(data)
        if message:
            response['message'] = message
        return response, 200
    
    @staticmethod
    def error_response(error: str, status_code: int = 400) -> tuple:
        """エラーレスポンスを生成"""
        return {'success': False, 'error': error}, status_code
    
    @staticmethod
    def not_found_response(resource: str = 'Resource') -> tuple:
        """404レスポンスを生成"""
        return {'success': False, 'error': f'{resource} not found'}, 404
    
    @staticmethod
    def validation_error_response(field: str, message: str) -> tuple:
        """バリデーションエラーレスポンスを生成"""
        return {
            'success': False,
            'error': 'Validation error',
            'details': {
                'field': field,
                'message': message
            }
        }, 400
