"""ファイル操作ドメインロジック

ワークスペースルート相対パスで動作し、パストラバーサルを防止する。
"""

import glob
import os


class FileOps:
    """ファイル操作を提供するクラス。

    全てのパスはワークスペースルートからの相対パスとして解釈され、
    ルート外へのアクセスは拒否される。
    """

    def __init__(self, workspace_root=None):
        if workspace_root is None:
            workspace_root = os.getcwd()
        self._root = os.path.realpath(workspace_root)

    @property
    def root(self):
        return self._root

    def _resolve(self, path):
        """パスをワークスペースルート配下に正規化する。

        ルート外を指す場合は ValueError を送出する。
        """
        if os.path.isabs(path):
            resolved = os.path.realpath(path)
        else:
            resolved = os.path.realpath(os.path.join(self._root, path))
        # ルート自体、またはルート配下であることを確認
        if resolved != self._root and not resolved.startswith(self._root + os.sep):
            raise ValueError(
                f"Path traversal detected: '{path}' resolves to '{resolved}' "
                f"which is outside workspace root '{self._root}'"
            )
        return resolved

    def read_file(self, path):
        """ファイルを読み取り、内容を文字列で返す。"""
        resolved = self._resolve(path)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"File not found: {path}")
        with open(resolved, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path, content):
        """ファイルに書き込み、書き込んだバイト数を返す。

        親ディレクトリが存在しない場合は自動作成する。
        """
        resolved = self._resolve(path)
        parent = os.path.dirname(resolved)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        encoded = content.encode("utf-8")
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return len(encoded)

    def create_file(self, path, content=""):
        """ファイルを新規作成する。既に存在する場合はエラー。

        親ディレクトリが存在しない場合は自動作成する。
        """
        resolved = self._resolve(path)
        if os.path.exists(resolved):
            raise FileExistsError(f"File already exists: {path}")
        parent = os.path.dirname(resolved)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

    def delete_file(self, path):
        """ファイルを削除する。"""
        resolved = self._resolve(path)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"File not found: {path}")
        os.remove(resolved)

    def search_files(self, pattern, directory="."):
        """globパターンでファイルを検索し、マッチしたパスのリストを返す。"""
        resolved_dir = self._resolve(directory)
        if not os.path.isdir(resolved_dir):
            raise NotADirectoryError(f"Directory not found: {directory}")
        full_pattern = os.path.join(resolved_dir, pattern)
        matches = glob.glob(full_pattern, recursive=True)
        result = []
        for m in sorted(matches):
            real_m = os.path.realpath(m)
            # ワークスペース外のシンボリックリンク先を除外
            if real_m == self._root or real_m.startswith(self._root + os.sep):
                result.append(os.path.relpath(real_m, self._root))
        return result

    def list_files(self, directory=".", recursive=False):
        """ディレクトリ内のファイル一覧を返す。

        各エントリは {"name", "path", "is_dir", "size"} の辞書。
        """
        resolved_dir = self._resolve(directory)
        if not os.path.isdir(resolved_dir):
            raise NotADirectoryError(f"Directory not found: {directory}")
        result = []
        if recursive:
            for dirpath, dirnames, filenames in os.walk(resolved_dir):
                dirnames.sort()
                for d in sorted(dirnames):
                    full = os.path.join(dirpath, d)
                    rel = os.path.relpath(full, self._root)
                    result.append({
                        "name": d,
                        "path": rel,
                        "is_dir": True,
                        "size": 0,
                    })
                for fname in sorted(filenames):
                    full = os.path.join(dirpath, fname)
                    rel = os.path.relpath(full, self._root)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    result.append({
                        "name": fname,
                        "path": rel,
                        "is_dir": False,
                        "size": size,
                    })
        else:
            entries = sorted(os.listdir(resolved_dir))
            for entry in entries:
                full = os.path.join(resolved_dir, entry)
                rel = os.path.relpath(full, self._root)
                is_dir = os.path.isdir(full)
                try:
                    size = 0 if is_dir else os.path.getsize(full)
                except OSError:
                    size = 0
                result.append({
                    "name": entry,
                    "path": rel,
                    "is_dir": is_dir,
                    "size": size,
                })
        return result
