"""
デフォルトパックのテンプレート

ecosystem/default/ にコピーされる元ファイル
"""

from pathlib import Path

DEFAULTS_DIR = Path(__file__).parent


def get_default_pack_path() -> Path:
    """default pack のテンプレートパスを取得"""
    return DEFAULTS_DIR / "default"
