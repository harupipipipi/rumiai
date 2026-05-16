"""ファイル操作ドメインロジック

ワークスペースルート相対パスで動作し、パストラバーサルを防止する。
"""

import difflib
import glob
import json
import os
import re
import shutil
import tempfile
import time
import uuid

MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
SNAPSHOT_DIR = ".rumi_snapshots"
SNAPSHOT_MANIFEST = "snapshot.json"
SNAPSHOT_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-fA-F]{8}$")
PROTECTED_PATHS = {".git", SNAPSHOT_DIR}


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

    def _relative(self, resolved):
        return os.path.relpath(resolved, self._root).replace(os.sep, "/")

    def _ensure_unprotected_mutation(self, resolved):
        rel = self._relative(resolved)
        parts = set(rel.replace("\\", "/").split("/"))
        if rel in PROTECTED_PATHS or parts & PROTECTED_PATHS:
            raise PermissionError("Protected workspace path cannot be modified: " + rel)

    def _ensure_text_size(self, resolved):
        if os.path.exists(resolved) and os.path.isfile(resolved):
            size = os.path.getsize(resolved)
            if size > MAX_TEXT_FILE_BYTES:
                raise ValueError(f"File is too large for text operation: {size} bytes")

    def _looks_binary(self, resolved):
        if not os.path.isfile(resolved):
            return False
        with open(resolved, "rb") as handle:
            sample = handle.read(4096)
        return b"\0" in sample

    def read_file(self, path):
        """ファイルを読み取り、内容を文字列で返す。"""
        resolved = self._resolve(path)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"File not found: {path}")
        self._ensure_text_size(resolved)
        if self._looks_binary(resolved):
            raise ValueError("Binary file cannot be read as text: " + str(path))
        with open(resolved, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path, content):
        """ファイルに書き込み、書き込んだバイト数を返す。

        親ディレクトリが存在しない場合は自動作成する。
        """
        resolved = self._resolve(path)
        self._ensure_unprotected_mutation(resolved)
        parent = os.path.dirname(resolved)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        encoded = content.encode("utf-8")
        fd, tmp_path = tempfile.mkstemp(prefix=".rumi-write-", dir=parent or self._root, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, resolved)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return len(encoded)

    def write_file_atomic(self, path, content):
        """Write a text file using the same atomic path as write_file."""
        return self.write_file(path, content)

    def checkpoint_before_mutation(self, operation, paths, metadata=None):
        """Create a reversible checkpoint before a workspace mutation."""
        clean_paths = []
        for path in paths if isinstance(paths, list) else [paths]:
            if path is not None:
                clean_paths.append(str(path))
        checkpoint_metadata = {
            "operation": str(operation or "mutation"),
            "kind": "pre_mutation",
        }
        if isinstance(metadata, dict):
            checkpoint_metadata.update(metadata)
        return self.snapshot(
            clean_paths or ["."],
            metadata=checkpoint_metadata,
            include_missing=True,
        )

    def preview_write(self, path, content):
        return {
            "path": path,
            "diff": self.diff_text(path, content),
        }

    def create_file(self, path, content=""):
        """ファイルを新規作成する。既に存在する場合はエラー。

        親ディレクトリが存在しない場合は自動作成する。
        """
        resolved = self._resolve(path)
        self._ensure_unprotected_mutation(resolved)
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
        self._ensure_unprotected_mutation(resolved)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"File not found: {path}")
        os.remove(resolved)

    def safe_delete(self, path):
        snapshot = self.snapshot([path])
        self.delete_file(path)
        return {"path": path, "deleted": True, "snapshot": snapshot}

    def move_file(self, source, destination):
        """ファイルまたはディレクトリを移動する。"""
        resolved_source = self._resolve(source)
        resolved_destination = self._resolve(destination)
        self._ensure_unprotected_mutation(resolved_source)
        self._ensure_unprotected_mutation(resolved_destination)
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

    def _snapshot_manifest_path(self, snapshot_root):
        return os.path.join(snapshot_root, SNAPSHOT_MANIFEST)

    def _validate_snapshot_id(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
            raise ValueError("Invalid snapshot id")

    def _load_snapshot_manifest(self, snapshot_id):
        self._validate_snapshot_id(snapshot_id)
        snapshot_root = self._resolve(os.path.join(SNAPSHOT_DIR, snapshot_id))
        manifest_path = self._snapshot_manifest_path(snapshot_root)
        if not os.path.isfile(manifest_path):
            return {}
        with open(manifest_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else {}

    def snapshot(self, paths=None, metadata=None, include_missing=False):
        """対象ファイルを workspace 内の .rumi_snapshots にコピーする。"""
        snapshot_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + str(uuid.uuid4())[:8]
        snapshot_root = self._resolve(os.path.join(SNAPSHOT_DIR, snapshot_id))
        os.makedirs(snapshot_root, exist_ok=True)
        selected = paths if paths else ["."]
        copied = []
        entries = []
        for item in selected:
            resolved = self._resolve(item)
            rel = self._relative(resolved)
            entry = {
                "path": rel,
                "requested_path": str(item),
                "existed": os.path.exists(resolved),
                "is_dir": os.path.isdir(resolved),
                "is_file": os.path.isfile(resolved),
            }
            if os.path.isfile(resolved):
                entry["size"] = os.path.getsize(resolved)
            entries.append(entry)
            if not os.path.exists(resolved):
                if include_missing:
                    copied.append(rel)
                continue
            if rel == SNAPSHOT_DIR or rel.startswith(SNAPSHOT_DIR + "/"):
                continue
            destination = os.path.join(snapshot_root, rel)
            parent = os.path.dirname(destination)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            if os.path.isdir(resolved):
                shutil.copytree(
                    resolved,
                    destination,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(SNAPSHOT_DIR, ".git"),
                )
            else:
                shutil.copy2(resolved, destination)
            copied.append(rel)
        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace_root": self._root,
            "paths": entries,
            "metadata": dict(metadata or {}) if isinstance(metadata, dict) else {},
        }
        with open(self._snapshot_manifest_path(snapshot_root), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        return {
            "snapshot_id": snapshot_id,
            "path": self._relative(snapshot_root),
            "files": copied,
            "metadata": manifest["metadata"],
        }

    def restore_snapshot(self, snapshot_id, paths=None):
        """snapshot_id から workspace に復元する。"""
        self._validate_snapshot_id(snapshot_id)
        snapshot_root = self._resolve(os.path.join(SNAPSHOT_DIR, snapshot_id))
        if not os.path.isdir(snapshot_root):
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        manifest = self._load_snapshot_manifest(snapshot_id)
        path_entries = {}
        for entry in manifest.get("paths", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("requested_path"):
                path_entries[str(entry["requested_path"])] = entry
            if entry.get("path"):
                path_entries[str(entry["path"])] = entry
        selected = paths if paths else ["."]
        restored = []
        removed = []
        for item in selected:
            source = os.path.realpath(os.path.join(snapshot_root, item))
            if source != snapshot_root and not source.startswith(snapshot_root + os.sep):
                raise ValueError("Snapshot path traversal detected: " + str(item))
            entry = path_entries.get(str(item))
            if entry is None:
                try:
                    entry = path_entries.get(self._relative(self._resolve(item)))
                except Exception:
                    entry = None
            if entry and entry.get("existed") is False:
                destination = self._resolve(item)
                self._ensure_unprotected_mutation(destination)
                if os.path.isdir(destination):
                    shutil.rmtree(destination)
                    removed.append(str(item))
                elif os.path.exists(destination):
                    os.remove(destination)
                    removed.append(str(item))
                continue
            if not os.path.exists(source):
                continue
            destination = self._resolve(item)
            self._ensure_unprotected_mutation(destination)
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
            "removed": removed,
        }

    def list_snapshots(self, limit=50):
        """List workspace snapshots newest-first."""
        root = self._resolve(SNAPSHOT_DIR)
        if not os.path.isdir(root):
            return []
        entries = []
        for name in sorted(os.listdir(root), reverse=True):
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            manifest = {}
            manifest_path = self._snapshot_manifest_path(path)
            if os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as handle:
                        loaded = json.load(handle)
                    manifest = loaded if isinstance(loaded, dict) else {}
                except (OSError, ValueError):
                    manifest = {}
            entries.append({
                "snapshot_id": name,
                "path": self._relative(path),
                "created_at": manifest.get("created_at"),
                "metadata": manifest.get("metadata", {}),
                "paths": manifest.get("paths", []),
            })
            if len(entries) >= int(limit):
                break
        return entries

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
                result.append(self._relative(real_m))
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
                    rel = self._relative(full)
                    result.append({
                        "name": d,
                        "path": rel,
                        "is_dir": True,
                        "size": 0,
                    })
                for fname in sorted(filenames):
                    full = os.path.join(dirpath, fname)
                    rel = self._relative(full)
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
                rel = self._relative(full)
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
