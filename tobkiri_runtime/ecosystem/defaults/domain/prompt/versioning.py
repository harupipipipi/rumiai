"""Prompt Versioning — プロンプトの複数バージョン管理。

既存の domain/prompt モジュールを変更せず、バージョニング機能を追加する。

機能:
    - プロンプトのスナップショットをバージョンとして保存
    - バージョン一覧の取得
    - 特定バージョンの取得
    - アクティブバージョンの切り替え（PromptManager のプロンプトを上書き）

永続化先: user_data/shared/prompts/_versions/{name}/
    - manifest.json:  {"active_version": int, "versions": [...]}
    - v{N}.json:      各バージョンのプロンプトスナップショット

データ形式（manifest.json）:
    {
        "name":            str,
        "active_version":  int,
        "versions": [
            {
                "version":    int,
                "label":      str,
                "created_at": str,
                "summary":    str
            },
            ...
        ]
    }
"""

from __future__ import annotations

import copy
import json
import os
import time
from typing import Any


# ---------------------------------------------------------------------------
# バージョン保存ディレクトリ
# ---------------------------------------------------------------------------

def _get_versions_dir() -> str:
    """user_data/shared/prompts/_versions/ の絶対パスを返す。"""
    base = os.path.dirname(os.path.realpath(__file__))
    versions_dir = os.path.normpath(
        os.path.join(base, "..", "..", "user_data", "shared", "prompts", "_versions")
    )
    os.makedirs(versions_dir, exist_ok=True)
    return versions_dir


def _safe_filename(name: str) -> str:
    """name をファイルシステム安全な形式に変換する。"""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
    return safe or "unnamed"


def _get_prompt_version_dir(name: str) -> str:
    """特定プロンプトのバージョンディレクトリパスを返す。"""
    versions_dir = _get_versions_dir()
    prompt_dir = os.path.join(versions_dir, _safe_filename(name))
    os.makedirs(prompt_dir, exist_ok=True)
    return prompt_dir


# ---------------------------------------------------------------------------
# Manifest 操作
# ---------------------------------------------------------------------------

def _load_manifest(name: str) -> dict:
    """プロンプトの manifest.json をロードする。存在しなければ初期状態を返す。"""
    prompt_dir = _get_prompt_version_dir(name)
    manifest_path = os.path.join(prompt_dir, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "name": name,
        "active_version": 0,
        "versions": [],
    }


def _save_manifest(name: str, manifest: dict) -> None:
    """manifest.json を保存する。"""
    prompt_dir = _get_prompt_version_dir(name)
    manifest_path = os.path.join(prompt_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# バージョンスナップショット操作
# ---------------------------------------------------------------------------

def _save_version_snapshot(name: str, version: int, prompt_data: dict) -> None:
    """バージョンスナップショットを vN.json として保存する。"""
    prompt_dir = _get_prompt_version_dir(name)
    fpath = os.path.join(prompt_dir, f"v{version}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(prompt_data, f, ensure_ascii=False, indent=2)


def _load_version_snapshot(name: str, version: int) -> dict | None:
    """バージョンスナップショットをロードする。"""
    prompt_dir = _get_prompt_version_dir(name)
    fpath = os.path.join(prompt_dir, f"v{version}.json")
    if not os.path.isfile(fpath):
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# VersionManager
# ---------------------------------------------------------------------------

class VersionManager:
    """プロンプトのバージョン管理を行う。

    使用例:
        vm = VersionManager()
        vm.create_version("my_prompt", label="初版")
        versions = vm.list_versions("my_prompt")
        vm.switch_version("my_prompt", version=1)
    """

    def create_version(
        self,
        name: str,
        label: str = "",
        summary: str = "",
    ) -> dict:
        """現在のプロンプト状態をバージョンとしてスナップショット保存する。

        PromptManager から現在のプロンプトデータを読み取り、
        新しいバージョン番号で保存する。

        Args:
            name:    プロンプト名
            label:   バージョンラベル（例: "v1.0", "実験版"）
            summary: バージョンの説明

        Returns:
            作成されたバージョン情報 dict
            {"version": int, "label": str, "created_at": str, "summary": str, "prompt": dict}

        Raises:
            ValueError: プロンプトが存在しない場合
        """
        from domain.prompt.manager import get_manager
        manager = get_manager()
        prompt = manager.get_prompt_by_name(name)
        if prompt is None:
            raise ValueError(f"Prompt not found: {name}")

        manifest = _load_manifest(name)
        existing_versions = manifest.get("versions", [])
        next_version = (existing_versions[-1]["version"] + 1) if existing_versions else 1

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        version_info = {
            "version": next_version,
            "label": label or f"v{next_version}",
            "created_at": now,
            "summary": summary,
        }

        prompt_snapshot = copy.deepcopy(prompt)
        prompt_snapshot["_version"] = next_version
        prompt_snapshot["_version_created_at"] = now

        _save_version_snapshot(name, next_version, prompt_snapshot)

        manifest["versions"].append(version_info)
        if manifest["active_version"] == 0:
            manifest["active_version"] = next_version
        _save_manifest(name, manifest)

        result = dict(version_info)
        result["prompt"] = prompt_snapshot
        return result

    def list_versions(self, name: str) -> dict:
        """プロンプトの全バージョン情報を返す。

        Returns:
            {
                "name": str,
                "active_version": int,
                "versions": [{"version": int, "label": str, "created_at": str, "summary": str}, ...]
            }
        """
        manifest = _load_manifest(name)
        return {
            "name": manifest["name"],
            "active_version": manifest["active_version"],
            "versions": list(manifest.get("versions", [])),
        }

    def get_version(self, name: str, version: int) -> dict | None:
        """特定バージョンのプロンプトスナップショットを取得する。

        Args:
            name:    プロンプト名
            version: バージョン番号

        Returns:
            プロンプトスナップショット dict、存在しなければ None
        """
        manifest = _load_manifest(name)
        version_exists = any(
            v["version"] == version for v in manifest.get("versions", [])
        )
        if not version_exists:
            return None
        return _load_version_snapshot(name, version)

    def switch_version(self, name: str, version: int) -> dict:
        """アクティブバージョンを切り替え、PromptManager のプロンプトを上書きする。

        Args:
            name:    プロンプト名
            version: 切り替え先バージョン番号

        Returns:
            切り替え後のプロンプト dict

        Raises:
            ValueError: バージョンが存在しない場合
        """
        snapshot = self.get_version(name, version)
        if snapshot is None:
            raise ValueError(f"Version {version} not found for prompt: {name}")

        from domain.prompt.manager import get_manager
        manager = get_manager()

        existing = manager.get_prompt_by_name(name)
        if existing is None:
            # プロンプトが削除されていた場合、再作成する
            clean = copy.deepcopy(snapshot)
            clean.pop("_version", None)
            clean.pop("_version_created_at", None)
            clean.pop("id", None)
            manager.create_prompt(clean)
        else:
            update_fields = {}
            for key in ("body", "content", "description", "variables", "metadata"):
                if key in snapshot:
                    update_fields[key] = snapshot[key]
            if update_fields:
                manager.update_prompt(name, update_fields)

        manifest = _load_manifest(name)
        manifest["active_version"] = version
        _save_manifest(name, manifest)

        updated = manager.get_prompt_by_name(name)
        return updated if updated is not None else snapshot

    def delete_version(self, name: str, version: int) -> bool:
        """特定バージョンを削除する。アクティブバージョンは削除できない。

        Args:
            name:    プロンプト名
            version: 削除するバージョン番号

        Returns:
            削除成功時 True

        Raises:
            ValueError: アクティブバージョンを削除しようとした場合
        """
        manifest = _load_manifest(name)
        if manifest["active_version"] == version:
            raise ValueError("Cannot delete the active version")

        original_len = len(manifest["versions"])
        manifest["versions"] = [
            v for v in manifest["versions"] if v["version"] != version
        ]
        if len(manifest["versions"]) == original_len:
            return False

        _save_manifest(name, manifest)

        prompt_dir = _get_prompt_version_dir(name)
        fpath = os.path.join(prompt_dir, f"v{version}.json")
        if os.path.isfile(fpath):
            os.remove(fpath)

        return True


# ---------------------------------------------------------------------------
# モジュールレベル シングルトン
# ---------------------------------------------------------------------------
_version_manager = VersionManager()


def get_version_manager() -> VersionManager:
    """共有 VersionManager インスタンスを返す。"""
    return _version_manager
