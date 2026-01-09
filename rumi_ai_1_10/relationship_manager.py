# relationship_manager.py
"""
チャット間のリレーションシップ（関係性）を管理するモジュール
エッジリスト形式でグラフ構造を表現し、チャット間の親子関係やツール割り当てなどを管理する
"""

import os
import json
import tempfile
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal


class RelationshipManager:
    """
    チャット間のリンク情報を一元管理するクラス
    
    データは chats/relationships.json に保存され、以下の構造を持つ:
    {
        "version": "1.0",
        "links": [
            {"source": "chat_uuid_A", "target": "chat_uuid_B", "type": "parent_child", "metadata": {}},
            {"source": "chat_uuid_A", "target": "tool_name_X", "type": "assigned_agent", "metadata": {}}
        ]
    }
    """
    
    VERSION = "1.0"
    
    def __init__(self, chats_dir: str = None):
        """
        RelationshipManagerを初期化
        
        Args:
            chats_dir: チャットディレクトリのパス
        """
        if chats_dir is None:
            # エコシステム経由でパス解決を試みる
            resolved = False
            try:
                from backend_core.ecosystem.compat import get_chats_dir, is_ecosystem_initialized
                if is_ecosystem_initialized():
                    chats_dir = str(get_chats_dir())
                    resolved = True
            except ImportError:
                pass
            
            if not resolved:
                chats_dir = 'chats'
        
        self.chats_dir = Path(chats_dir)
        self.relationships_file = self.chats_dir / 'relationships.json'
        self._lock = threading.Lock()
        
        # ディレクトリが存在しない場合は作成
        if not self.chats_dir.exists():
            self.chats_dir.mkdir(parents=True)
        
        # ファイルが存在しない場合は初期化
        if not self.relationships_file.exists():
            self._save_data(self._create_empty_data())
    
    def _create_empty_data(self) -> Dict[str, Any]:
        """空のリレーションシップデータを作成"""
        return {
            "version": self.VERSION,
            "links": []
        }
    
    def _load_data(self) -> Dict[str, Any]:
        """リレーションシップデータを読み込む"""
        try:
            with open(self.relationships_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # バージョンチェックと互換性処理
            if data.get("version") != self.VERSION:
                data = self._migrate_data(data)
            
            return data
        except (json.JSONDecodeError, FileNotFoundError):
            return self._create_empty_data()
    
    def _save_data(self, data: Dict[str, Any]):
        """
        リレーションシップデータをアトミックに保存
        一時ファイルに書き込んでからリネームすることで、書き込み中の破損を防ぐ
        """
        # ディレクトリが存在することを確認
        if not self.chats_dir.exists():
            self.chats_dir.mkdir(parents=True)
        
        # 一時ファイルを同じディレクトリに作成（os.replaceのため）
        fd, temp_path = tempfile.mkstemp(
            dir=str(self.chats_dir),
            prefix='.relationships_',
            suffix='.tmp'
        )
        
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # アトミックにリネーム
            os.replace(temp_path, self.relationships_file)
        except Exception:
            # エラー時は一時ファイルを削除
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def _migrate_data(self, old_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        古いバージョンのデータを最新バージョンに移行
        現在はv1.0のみなので、そのまま返す
        """
        # 将来のバージョン移行ロジックをここに追加
        new_data = self._create_empty_data()
        new_data["links"] = old_data.get("links", [])
        return new_data
    
    def link(
        self,
        source: str,
        target: str,
        link_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        リンクを作成または更新
        
        Args:
            source: ソースID（チャットIDまたはその他のエンティティID）
            target: ターゲットID
            link_type: リンクタイプ（例: "parent_child", "assigned_agent", "reference"）
            metadata: 追加のメタデータ
        
        Returns:
            作成/更新されたリンク情報
        """
        if metadata is None:
            metadata = {}
        
        with self._lock:
            data = self._load_data()
            
            # 既存のリンクを検索
            existing_link = None
            for link in data["links"]:
                if (link["source"] == source and 
                    link["target"] == target and 
                    link["type"] == link_type):
                    existing_link = link
                    break
            
            if existing_link:
                # 既存リンクを更新
                existing_link["metadata"] = {**existing_link.get("metadata", {}), **metadata}
                result = existing_link
            else:
                # 新規リンクを作成
                new_link = {
                    "source": source,
                    "target": target,
                    "type": link_type,
                    "metadata": metadata
                }
                data["links"].append(new_link)
                result = new_link
            
            self._save_data(data)
            return result
    
    def unlink(
        self,
        source: str,
        target: str,
        link_type: str
    ) -> bool:
        """
        リンクを削除
        
        Args:
            source: ソースID
            target: ターゲットID
            link_type: リンクタイプ
        
        Returns:
            削除が成功したかどうか
        """
        with self._lock:
            data = self._load_data()
            
            original_count = len(data["links"])
            data["links"] = [
                link for link in data["links"]
                if not (link["source"] == source and 
                       link["target"] == target and 
                       link["type"] == link_type)
            ]
            
            if len(data["links"]) < original_count:
                self._save_data(data)
                return True
            
            return False
    
    def get_related(
        self,
        entity_id: str,
        link_type: Optional[str] = None,
        direction: Literal["outgoing", "incoming", "both"] = "both"
    ) -> List[Dict[str, Any]]:
        """
        指定されたエンティティに関連するリンクを取得
        
        Args:
            entity_id: エンティティID（チャットIDなど）
            link_type: フィルタするリンクタイプ（Noneの場合は全タイプ）
            direction: 検索方向
                - "outgoing": entity_idがsourceのリンク
                - "incoming": entity_idがtargetのリンク
                - "both": 両方
        
        Returns:
            関連するリンクのリスト
        """
        with self._lock:
            data = self._load_data()
        
        results = []
        
        for link in data["links"]:
            # タイプフィルタ
            if link_type is not None and link["type"] != link_type:
                continue
            
            # 方向フィルタ
            is_outgoing = link["source"] == entity_id
            is_incoming = link["target"] == entity_id
            
            if direction == "outgoing" and is_outgoing:
                results.append(link)
            elif direction == "incoming" and is_incoming:
                results.append(link)
            elif direction == "both" and (is_outgoing or is_incoming):
                results.append(link)
        
        return results
    
    def get_related_ids(
        self,
        entity_id: str,
        link_type: Optional[str] = None,
        direction: Literal["outgoing", "incoming", "both"] = "both"
    ) -> List[str]:
        """
        関連するエンティティのIDリストを取得
        
        Args:
            entity_id: エンティティID
            link_type: フィルタするリンクタイプ
            direction: 検索方向
        
        Returns:
            関連するエンティティIDのリスト
        """
        links = self.get_related(entity_id, link_type, direction)
        
        ids = set()
        for link in links:
            if link["source"] == entity_id:
                ids.add(link["target"])
            if link["target"] == entity_id:
                ids.add(link["source"])
        
        return list(ids)
    
    def delete_all_links_for(self, entity_id: str) -> int:
        """
        指定されたエンティティに関連する全リンクを削除
        
        Args:
            entity_id: エンティティID
        
        Returns:
            削除されたリンクの数
        """
        with self._lock:
            data = self._load_data()
            
            original_count = len(data["links"])
            data["links"] = [
                link for link in data["links"]
                if link["source"] != entity_id and link["target"] != entity_id
            ]
            
            deleted_count = original_count - len(data["links"])
            
            if deleted_count > 0:
                self._save_data(data)
            
            return deleted_count
    
    def get_all_links(self) -> List[Dict[str, Any]]:
        """全リンクを取得"""
        with self._lock:
            data = self._load_data()
        return data["links"]
    
    def get_links_by_type(self, link_type: str) -> List[Dict[str, Any]]:
        """指定タイプのリンクを全て取得"""
        with self._lock:
            data = self._load_data()
        
        return [link for link in data["links"] if link["type"] == link_type]
    
    def clear_all(self) -> int:
        """全リンクを削除（主にテスト用）"""
        with self._lock:
            data = self._load_data()
            count = len(data["links"])
            self._save_data(self._create_empty_data())
            return count
