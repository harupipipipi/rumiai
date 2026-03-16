"""
save_profile.py - セットアップデータを profile.json に保存する

Kernel の _h_exec_python または直接 import から呼ばれる。

バリデーション:
- username: 必須、空文字不可、100文字以内
- language: 許可リスト (ja, en, zh, ko, es, fr, de, pt, ru, ar)

保存先: user_data/settings/profile.json
スキーマ: schema_version=1, setup_completed=true
"""

import json
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_LANGUAGES = frozenset({
    "ja", "en", "zh", "ko", "es", "fr", "de", "pt", "ru", "ar",
})

PROFILE_SCHEMA_VERSION = 1


def validate_profile_data(data):
    """
    プロフィールデータをバリデーションする。

    Args:
        data: {"username": str, "language": str, "icon": optional, "occupation": optional}

    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors = []

    # username
    username = data.get("username")
    if username is None or not isinstance(username, str) or username.strip() == "":
        errors.append("username is required and must be a non-empty string")
    elif len(username) > 100:
        errors.append("username must be 100 characters or less")

    # language
    language = data.get("language")
    if language is None or not isinstance(language, str):
        errors.append("language is required and must be a string")
    elif language not in ALLOWED_LANGUAGES:
        errors.append(
            "language '{}' is not allowed. Allowed: {}".format(
                language, ", ".join(sorted(ALLOWED_LANGUAGES))
            )
        )

    return (len(errors) == 0, errors)


def save_profile(data, base_dir=None):
    """
    プロフィールデータを profile.json に保存する。

    バリデーション -> ディレクトリ作成 -> JSON 書き込み の順で実行。
    冪等: 既存ファイルがあれば上書き。

    Args:
        data: 保存するプロフィールデータ
        base_dir: ソースコードルート（rumi_ai_1_10/）

    Returns:
        {"success": bool, "errors": list, "path": str or None}
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    # バリデーション
    is_valid, errors = validate_profile_data(data)
    if not is_valid:
        return {"success": False, "errors": errors, "path": None}

    # プロフィール構築
    profile = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "initialized_at": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "username": data["username"].strip(),
        "language": data["language"],
        "icon": data.get("icon"),
        "occupation": data.get("occupation"),
        "setup_completed": True,
    }

    # ディレクトリ作成 + 書き込み
    profile_path = base_dir / "user_data" / "settings" / "profile.json"
    try:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return {
            "success": False,
            "errors": ["Failed to write profile: {}".format(e)],
            "path": None,
        }

    return {"success": True, "errors": [], "path": str(profile_path)}


# --- Kernel exec_python entry point ---
if __name__ != "__main__":
    _ctx = locals()
    _input_data = {}
    for _key in ("username", "language", "icon", "occupation"):
        if _key in _ctx:
            _input_data[_key] = _ctx[_key]
    if _input_data:
        _result = save_profile(_input_data)
        if "interface_registry" in _ctx:
            _ctx["interface_registry"].register(
                "setup.save_result",
                _result,
                meta={"source": "core_setup.save_profile"},
            )
