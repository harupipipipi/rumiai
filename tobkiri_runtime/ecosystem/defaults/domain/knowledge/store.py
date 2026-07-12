"""KnowledgeStore — シングルトンのナレッジストア.

永続化: user_data/shared/knowledge/ に {id}.json として保存。
起動時に全 JSON ファイルを読み込んでメモリに復元する。
ベクトル検索: cosine similarity で上位 k 件を返す。
フォールバック: embedding が取得できない場合は文字列マッチで代用。
"""

import json
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.knowledge.embedder import (
    cosine_similarity,
    get_embedding,
    text_similarity,
)


def _timestamp():
    """ISO 8601 タイムスタンプを返す."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class KnowledgeStore:
    """スレッドセーフなシングルトン Knowledge Store."""

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._entries = {}
            self._data_dir = self._resolve_data_dir()
            self._load_all()
            self._initialized = True

    # -- ディレクトリ解決 -----------------------------------------------------

    def _resolve_data_dir(self):
        """user_data/shared/knowledge/ のパスを解決し、なければ作成する.

        realpath でシンボリックリンクを解決し、Pack ルートを正確に特定する。
        カーネルの ecosystem/defaults/ 配下に配置された場合でも
        リンク先の実パスを基準にするため、Pack ルート内に user_data/ が作られる。
        """
        base = os.path.dirname(os.path.realpath(__file__))
        pack_root = os.path.normpath(os.path.join(base, "..", ".."))
        data_dir = os.path.join(pack_root, "user_data", "shared", "knowledge")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    # -- 永続化 ---------------------------------------------------------------

    def _load_all(self):
        """起動時にディレクトリ内の全 JSON ファイルを読み込む."""
        if not os.path.isdir(self._data_dir):
            return
        for fname in os.listdir(self._data_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._data_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                entry_id = entry.get("id")
                if entry_id:
                    self._entries[entry_id] = entry
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                print(
                    "knowledge.store: failed to load " + fpath + ": " + str(exc),
                    file=sys.stderr,
                )

    def _persist(self, entry):
        """エントリを JSON ファイルに書き出す."""
        fpath = os.path.join(self._data_dir, entry["id"] + ".json")
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(
                "knowledge.store: failed to write " + fpath + ": " + str(exc),
                file=sys.stderr,
            )

    def _delete_file(self, entry_id):
        """JSON ファイルを削除する."""
        fpath = os.path.join(self._data_dir, entry_id + ".json")
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
        except OSError as exc:
            print(
                "knowledge.store: failed to delete " + fpath + ": " + str(exc),
                file=sys.stderr,
            )

    # -- CRUD ----------------------------------------------------------------

    def create(self, content, metadata=None):
        """ナレッジエントリを作成する.

        content を embedding 化して保存する。embedding 取得に失敗しても
        エントリ自体は作成される (embedding=None)。
        """
        entry_id = str(uuid.uuid4())
        now = _timestamp()
        embedding = get_embedding(content)
        entry = {
            "id": entry_id,
            "content": content,
            "embedding": embedding,
            "metadata": metadata if metadata is not None else {},
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._entries[entry_id] = entry
        self._persist(entry)
        return entry

    def get(self, entry_id):
        """ID でエントリを取得する. 見つからなければ None."""
        with self._lock:
            return self._entries.get(entry_id)

    def list_entries(self, limit=50, offset=0):
        """エントリ一覧を返す. created_at 降順."""
        with self._lock:
            all_entries = list(self._entries.values())
        all_entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        total = len(all_entries)
        sliced = all_entries[offset: offset + limit]
        safe_items = []
        for e in sliced:
            safe_items.append({
                "id": e["id"],
                "content": e["content"],
                "metadata": e["metadata"],
                "created_at": e["created_at"],
                "updated_at": e["updated_at"],
            })
        return {"items": safe_items, "total": total}

    def update(self, entry_id, content=None, metadata=None):
        """エントリを更新する. content が変わった場合は embedding を再取得する.

        見つからなければ None を返す。
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            entry = dict(entry)

        changed = False
        if content is not None and content != entry["content"]:
            entry["content"] = content
            entry["embedding"] = get_embedding(content)
            changed = True
        if metadata is not None:
            entry["metadata"] = metadata
            changed = True

        if changed:
            entry["updated_at"] = _timestamp()
            with self._lock:
                self._entries[entry_id] = entry
            self._persist(entry)

        return entry

    def delete(self, entry_id):
        """エントリを削除する. 見つからなければ False."""
        with self._lock:
            if entry_id not in self._entries:
                return False
            del self._entries[entry_id]
        self._delete_file(entry_id)
        return True

    # -- 検索 -----------------------------------------------------------------

    def search(self, query, limit=5, threshold=0.0):
        """クエリテキストで関連ナレッジをベクトル検索する.

        1. クエリを embedding 化
        2. 各エントリとの cosine similarity を計算
        3. embedding が無いエントリは文字列マッチでフォールバック
        4. threshold 以上のスコアを持つ上位 limit 件を返す
        """
        query_embedding = get_embedding(query)
        use_vector = query_embedding is not None

        with self._lock:
            all_entries = list(self._entries.values())

        results = []
        for entry in all_entries:
            score = 0.0
            if use_vector and entry.get("embedding") is not None:
                score = cosine_similarity(query_embedding, entry["embedding"])
            else:
                score = text_similarity(query, entry["content"])

            if score > threshold:
                results.append({
                    "id": entry["id"],
                    "content": entry["content"],
                    "metadata": entry["metadata"],
                    "score": round(score, 6),
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]
