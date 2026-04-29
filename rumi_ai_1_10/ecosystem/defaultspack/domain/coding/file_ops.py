"""ファイル操作ドメインロジック

ワークスペースルート相対パスで動作し、パストラバーサルを防止する。
"""

import difflib
import glob
import os
import shutil
import time
import uuid


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

    def move_file(self, source, destination):
        """ファイルまたはディレクトリを移動する。"""
        resolved_source = self._resolve(source)
        resolved_destination = self._resolve(destination)
        if not os.path.exists(resolved_source):
            raise FileNotFoundError(f"Path not found: {source}")
        parent = os.path.dirname(resolved_destination)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        shutil.move(resolved_source, resolved_destination)
        return {
            "source": source,
            "destination": destination,
            "moved": True,
        }

    def diff_text(self, path, new_content):
        """既存ファイルと新しい内容の unified diff を返す。"""
        old_content = ""
        resolved = self._resolve(path)
        if os.path.exists(resolved):
            if not os.path.isfile(resolved):
                raise IsADirectoryError(f"Path is not a file: {path}")
            old_content = self.read_file(path)
        old_lines = old_content.splitlines(keepends=True)
        new_lines = str(new_content).splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=path + " (current)",
                tofile=path + " (proposed)",
            )
        )

    def apply_patch_text(self, path, old, new):
        """単純な old/new 置換パッチを適用する。"""
        content = self.read_file(path)
        if old not in content:
            raise ValueError("Patch old text was not found in file: " + path)
        updated = content.replace(old, new, 1)
        size = self.write_file(path, updated)
        return {
            "path": path,
            "patched": True,
            "size": size,
            "diff": "".join(
                difflib.unified_diff(
                    content.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=path + " (before)",
                    tofile=path + " (after)",
                )
            ),
        }

    def snapshot(self, paths=None):
        """対象ファイルを workspace 内の .rumi_snapshots にコピーする。"""
        snapshot_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + str(uuid.uuid4())[:8]
        snapshot_root = self._resolve(os.path.join(".rumi_snapshots", snapshot_id))
        os.makedirs(snapshot_root, exist_ok=True)
        selected = paths if paths else ["."]
        copied = []
        for item in selected:
            resolved = self._resolve(item)
            if not os.path.exists(resolved):
                continue
            rel = os.path.relpath(resolved, self._root)
            if rel == ".rumi_snapshots" or rel.startswith(".rumi_snapshots" + os.sep):
                continue
            destination = os.path.join(snapshot_root, rel)
            parent = os.path.dirname(destination)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            if os.path.isdir(resolved):
                shutil.copytree(resolved, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".rumi_snapshots", ".git"))
            else:
                shutil.copy2(resolved, destination)
            copied.append(rel)
        return {
            "snapshot_id": snapshot_id,
            "path": os.path.relpath(snapshot_root, self._root),
            "files": copied,
        }

    def restore_snapshot(self, snapshot_id, paths=None):
        """snapshot_id から workspace に復元する。"""
        snapshot_root = self._resolve(os.path.join(".rumi_snapshots", snapshot_id))
        if not os.path.isdir(snapshot_root):
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        selected = paths if paths else ["."]
        restored = []
        for item in selected:
            source = os.path.realpath(os.path.join(snapshot_root, item))
            if source != snapshot_root and not source.startswith(snapshot_root + os.sep):
                raise ValueError("Snapshot path traversal detected: " + str(item))
            if not os.path.exists(source):
                continue
            destination = self._resolve(item)
            parent = os.path.dirname(destination)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            if os.path.isdir(source):
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            restored.append(item)
        return {
            "snapshot_id": snapshot_id,
            "restored": restored,
        }

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
