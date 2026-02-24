"""
pack_scaffold.py - Pack 雛形生成ユーティリティ (Wave 14 T-055)

Pack 開発者が新しい Pack を作る際に、テンプレートに基づいた
ディレクトリ構造とファイルを自動生成する。

テンプレート:
  minimal    : ecosystem.json + __init__.py
  capability : minimal + capability_handler.py
  flow       : minimal + flows/ + sample_flow.yaml
  full       : 上記全部 + tests/ + README.md

依存: stdlib + core_runtime.validation のみ

CLI:
  python -m core_runtime.pack_scaffold <pack_id> [--template TYPE] [--output DIR] [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .validation import validate_pack_id

# ======================================================================
# 定数
# ======================================================================

VALID_TEMPLATES = ("minimal", "capability", "flow", "full")


# ======================================================================
# テンプレート内容生成
# ======================================================================

def _ecosystem_json_content(pack_id: str) -> str:
    """ecosystem.json のテンプレート内容を生成する。"""
    data = {
        "pack_id": pack_id,
        "version": "0.1.0",
        "description": f"{pack_id} - A Rumi AI OS Pack",
        "capabilities": [],
        "flows": [],
        "connectivity": [],
        "trust": {
            "level": "sandboxed",
            "permissions": [],
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _init_py_content(pack_id: str) -> str:
    """__init__.py のテンプレート内容を生成する。"""
    return f'"""\n{pack_id} - Pack entry point\n"""\n'


def _capability_handler_content(pack_id: str) -> str:
    """capability_handler.py のテンプレート内容を生成する。"""
    return (
        f'"""\n'
        f'{pack_id} - Capability handler\n'
        f'"""\n'
        f'\n'
        f'from __future__ import annotations\n'
        f'\n'
        f'\n'
        f'def handle(request: dict) -> dict:\n'
        f'    """Handle a capability request.\n'
        f'\n'
        f'    Args:\n'
        f'        request: The incoming capability request.\n'
        f'\n'
        f'    Returns:\n'
        f'        Response dictionary.\n'
        f'    """\n'
        f'    return {{"status": "ok", "pack_id": "{pack_id}"}}\n'
    )


def _sample_flow_yaml_content(pack_id: str) -> str:
    """sample_flow.yaml のテンプレート内容を生成する。"""
    return (
        f"# {pack_id} - Sample flow\n"
        f"name: sample_flow\n"
        f"description: A sample flow for {pack_id}\n"
        f"steps:\n"
        f"  - id: step_1\n"
        f"    action: noop\n"
        f"    description: Replace with your flow logic\n"
    )


def _readme_content(pack_id: str) -> str:
    """README.md のテンプレート内容を生成する。"""
    return (
        f"# {pack_id}\n"
        f"\n"
        f"A Rumi AI OS Pack.\n"
        f"\n"
        f"## Overview\n"
        f"\n"
        f"Describe what this Pack does.\n"
        f"\n"
        f"## Usage\n"
        f"\n"
        f"Describe how to use this Pack.\n"
    )


def _test_init_content(pack_id: str) -> str:
    """tests/__init__.py のテンプレート内容を生成する。"""
    return (
        f'"""\n'
        f'Tests for {pack_id}\n'
        f'"""\n'
    )


# ======================================================================
# PackScaffold クラス
# ======================================================================

class PackScaffold:
    """Pack のディレクトリ構造を生成するユーティリティ。

    Usage::

        scaffold = PackScaffold()
        pack_dir = scaffold.generate("my_pack", Path("./output"), template="full")
    """

    def generate(
        self,
        pack_id: str,
        target_dir: Path,
        template: str = "minimal",
        force: bool = False,
    ) -> Path:
        """指定ディレクトリに Pack 雛形を生成する。

        Args:
            pack_id:    Pack の識別子（validate_pack_id で検証）。
            target_dir: Pack ディレクトリを作成する親ディレクトリ。
            template:   テンプレート名 (minimal / capability / flow / full)。
            force:      True の場合、既存ディレクトリの上書きを許可する。

        Returns:
            生成された Pack ディレクトリの Path。

        Raises:
            ValueError:      pack_id が不正、または template が未知の場合。
            FileExistsError: target_dir/pack_id が既に存在し中身がある場合（force=False）。
        """
        # --- バリデーション ---
        if not validate_pack_id(pack_id):
            raise ValueError(
                f"Invalid pack_id: {pack_id!r}. "
                f"Must match [a-zA-Z0-9_-]{{1,64}}."
            )

        if template not in VALID_TEMPLATES:
            raise ValueError(
                f"Unknown template: {template!r}. "
                f"Valid templates: {', '.join(VALID_TEMPLATES)}"
            )

        target_dir = Path(target_dir)
        pack_dir = target_dir / pack_id

        # --- 上書き防止 ---
        if pack_dir.exists() and any(pack_dir.iterdir()) and not force:
            raise FileExistsError(
                f"Directory already exists and is not empty: {pack_dir}. "
                f"Use force=True to overwrite."
            )

        # --- ファイル生成計画 ---
        files = self._plan_files(pack_id, template)

        # --- ディレクトリ作成 & ファイル書き込み ---
        pack_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in files.items():
            file_path = pack_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        return pack_dir

    def _plan_files(self, pack_id: str, template: str) -> Dict[str, str]:
        """テンプレートに応じた生成ファイル一覧を返す。

        Returns:
            {相対パス: ファイル内容} の辞書。
        """
        files: Dict[str, str] = {}

        # --- minimal (全テンプレート共通) ---
        files["ecosystem.json"] = _ecosystem_json_content(pack_id)
        files["__init__.py"] = _init_py_content(pack_id)

        # --- capability ---
        if template in ("capability", "full"):
            files["capability_handler.py"] = _capability_handler_content(pack_id)

        # --- flow ---
        if template in ("flow", "full"):
            files["flows/sample_flow.yaml"] = _sample_flow_yaml_content(pack_id)

        # --- full ---
        if template == "full":
            files["tests/__init__.py"] = _test_init_content(pack_id)
            files["README.md"] = _readme_content(pack_id)

        return files


# ======================================================================
# CLI エントリポイント
# ======================================================================

def _build_parser() -> argparse.ArgumentParser:
    """CLI 引数パーサーを構築する。"""
    parser = argparse.ArgumentParser(
        prog="python -m core_runtime.pack_scaffold",
        description="Generate a new Pack scaffold for Rumi AI OS.",
    )
    parser.add_argument(
        "pack_id",
        help="Pack identifier (must match [a-zA-Z0-9_-]{1,64})",
    )
    parser.add_argument(
        "--template", "-t",
        choices=VALID_TEMPLATES,
        default="minimal",
        help="Scaffold template (default: minimal)",
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Parent directory for the generated Pack (default: current directory)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        default=False,
        help="Overwrite existing Pack directory",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI メインエントリポイント。

    Args:
        argv: コマンドライン引数（None の場合は sys.argv を使用）。

    Returns:
        終了コード（0: 成功、1: エラー）。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    scaffold = PackScaffold()

    try:
        pack_dir = scaffold.generate(
            pack_id=args.pack_id,
            target_dir=Path(args.output),
            template=args.template,
            force=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Pack scaffold created: {pack_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
