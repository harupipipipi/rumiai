"""
test_core_setup.py - core_setup Pack のユニットテスト

pytest + tmp_path を使用して check_profile.py と save_profile.py をテスト。
実際の user_data/ を汚さない。
"""

import json
import sys
from pathlib import Path

import pytest

# テスト対象モジュールのパスを sys.path に追加
_CORE_SETUP_DIR = (
    Path(__file__).resolve().parent.parent
    / "core_runtime"
    / "core_pack"
    / "core_setup"
)
if str(_CORE_SETUP_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_SETUP_DIR))

from check_profile import check_profile
from save_profile import save_profile, validate_profile_data, ALLOWED_LANGUAGES


# ======================================================================
# check_profile テスト
# ======================================================================


class TestCheckProfile:
    """check_profile.py のテスト"""

    def test_profile_not_found(self, tmp_path):
        """profile.json が存在しない場合 -> needs_setup: True"""
        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "profile_not_found"

    def test_profile_valid(self, tmp_path):
        """profile.json が存在し有効な場合 -> needs_setup: False"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        profile = {
            "schema_version": 1,
            "initialized_at": "2026-03-16T12:00:00Z",
            "username": "testuser",
            "language": "ja",
            "icon": None,
            "occupation": None,
            "setup_completed": True,
        }
        (settings_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is False
        assert result["reason"] == "profile_valid"

    def test_profile_setup_not_completed(self, tmp_path):
        """setup_completed: false -> needs_setup: True"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        profile = {
            "schema_version": 1,
            "initialized_at": "2026-03-16T12:00:00Z",
            "username": "testuser",
            "language": "ja",
            "setup_completed": False,
        }
        (settings_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "setup_not_completed"

    def test_profile_invalid_json(self, tmp_path):
        """壊れた JSON -> needs_setup: True"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        (settings_dir / "profile.json").write_text(
            "{invalid json!!!", encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "profile_invalid_json"

    def test_profile_not_dict(self, tmp_path):
        """JSON がオブジェクトではない -> needs_setup: True"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        (settings_dir / "profile.json").write_text(
            json.dumps([1, 2, 3]), encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "profile_not_dict"

    def test_profile_missing_schema_version(self, tmp_path):
        """schema_version が無い -> needs_setup: True"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        profile = {
            "username": "testuser",
            "language": "ja",
            "setup_completed": True,
        }
        (settings_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "missing_schema_version"

    def test_profile_setup_completed_missing(self, tmp_path):
        """setup_completed フィールドが無い -> needs_setup: True"""
        settings_dir = tmp_path / "user_data" / "settings"
        settings_dir.mkdir(parents=True)
        profile = {
            "schema_version": 1,
            "username": "testuser",
            "language": "ja",
        }
        (settings_dir / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )

        result = check_profile(base_dir=tmp_path)
        assert result["needs_setup"] is True
        assert result["reason"] == "setup_not_completed"


# ======================================================================
# validate_profile_data テスト
# ======================================================================


class TestValidateProfileData:
    """validate_profile_data() のテスト"""

    def test_valid_data(self):
        """正常なデータ"""
        is_valid, errors = validate_profile_data(
            {"username": "testuser", "language": "ja"}
        )
        assert is_valid is True
        assert errors == []

    def test_username_empty(self):
        """username が空"""
        is_valid, errors = validate_profile_data(
            {"username": "", "language": "ja"}
        )
        assert is_valid is False
        assert any("username" in e for e in errors)

    def test_username_none(self):
        """username が None"""
        is_valid, errors = validate_profile_data(
            {"username": None, "language": "ja"}
        )
        assert is_valid is False
        assert any("username" in e for e in errors)

    def test_username_missing(self):
        """username が存在しない"""
        is_valid, errors = validate_profile_data({"language": "ja"})
        assert is_valid is False
        assert any("username" in e for e in errors)

    def test_username_too_long(self):
        """username が100文字超"""
        is_valid, errors = validate_profile_data(
            {"username": "a" * 101, "language": "ja"}
        )
        assert is_valid is False
        assert any("100" in e for e in errors)

    def test_username_exactly_100(self):
        """username がちょうど100文字 -> OK"""
        is_valid, errors = validate_profile_data(
            {"username": "a" * 100, "language": "ja"}
        )
        assert is_valid is True
        assert errors == []

    def test_username_whitespace_only(self):
        """username がスペースのみ -> エラー"""
        is_valid, errors = validate_profile_data(
            {"username": "   ", "language": "ja"}
        )
        assert is_valid is False
        assert any("username" in e for e in errors)

    def test_language_invalid(self):
        """language が許可リスト外"""
        is_valid, errors = validate_profile_data(
            {"username": "testuser", "language": "xx"}
        )
        assert is_valid is False
        assert any("language" in e for e in errors)

    def test_language_none(self):
        """language が None"""
        is_valid, errors = validate_profile_data(
            {"username": "testuser", "language": None}
        )
        assert is_valid is False
        assert any("language" in e for e in errors)

    def test_language_missing(self):
        """language が存在しない"""
        is_valid, errors = validate_profile_data({"username": "testuser"})
        assert is_valid is False
        assert any("language" in e for e in errors)

    def test_all_allowed_languages(self):
        """全ての許可言語が通る"""
        for lang in ALLOWED_LANGUAGES:
            is_valid, errors = validate_profile_data(
                {"username": "testuser", "language": lang}
            )
            assert is_valid is True, "Language '{}' should be valid".format(lang)

    def test_multiple_errors(self):
        """複数のエラーが同時に返る"""
        is_valid, errors = validate_profile_data({})
        assert is_valid is False
        assert len(errors) >= 2


# ======================================================================
# save_profile テスト
# ======================================================================


class TestSaveProfile:
    """save_profile() のテスト"""

    def test_save_success(self, tmp_path):
        """正常なデータでの保存成功"""
        result = save_profile(
            {"username": "testuser", "language": "ja"},
            base_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["errors"] == []
        assert result["path"] is not None

        # ファイルが実際に存在するか
        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        assert profile_path.exists()

        # 内容を検証
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert data["username"] == "testuser"
        assert data["language"] == "ja"
        assert data["setup_completed"] is True
        assert data["initialized_at"] is not None
        assert data["icon"] is None
        assert data["occupation"] is None

    def test_save_with_optional_fields(self, tmp_path):
        """オプションフィールド付きの保存"""
        result = save_profile(
            {
                "username": "testuser",
                "language": "en",
                "icon": "/path/to/icon.png",
                "occupation": "Developer",
            },
            base_dir=tmp_path,
        )
        assert result["success"] is True

        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["icon"] == "/path/to/icon.png"
        assert data["occupation"] == "Developer"

    def test_save_validation_error_username_empty(self, tmp_path):
        """username が空 -> バリデーションエラー"""
        result = save_profile(
            {"username": "", "language": "ja"},
            base_dir=tmp_path,
        )
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert result["path"] is None

        # ファイルが作られていないこと
        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        assert not profile_path.exists()

    def test_save_validation_error_username_too_long(self, tmp_path):
        """username が100文字超 -> バリデーションエラー"""
        result = save_profile(
            {"username": "a" * 101, "language": "ja"},
            base_dir=tmp_path,
        )
        assert result["success"] is False
        assert any("100" in e for e in result["errors"])

    def test_save_validation_error_invalid_language(self, tmp_path):
        """language が無効 -> バリデーションエラー"""
        result = save_profile(
            {"username": "testuser", "language": "invalid"},
            base_dir=tmp_path,
        )
        assert result["success"] is False
        assert any("language" in e for e in result["errors"])

    def test_save_creates_directory(self, tmp_path):
        """ディレクトリが存在しない場合の自動作成"""
        result = save_profile(
            {"username": "testuser", "language": "ja"},
            base_dir=tmp_path,
        )
        assert result["success"] is True

        settings_dir = tmp_path / "user_data" / "settings"
        assert settings_dir.is_dir()

    def test_save_overwrites_existing(self, tmp_path):
        """既存 profile.json の上書き（冪等性）"""
        # 1回目の保存
        save_profile(
            {"username": "user1", "language": "ja"},
            base_dir=tmp_path,
        )

        # 2回目の保存（上書き）
        result = save_profile(
            {"username": "user2", "language": "en"},
            base_dir=tmp_path,
        )
        assert result["success"] is True

        # 2回目の内容で上書きされている
        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["username"] == "user2"
        assert data["language"] == "en"

    def test_save_strips_username(self, tmp_path):
        """username の前後空白が除去される"""
        result = save_profile(
            {"username": "  testuser  ", "language": "ja"},
            base_dir=tmp_path,
        )
        assert result["success"] is True

        profile_path = tmp_path / "user_data" / "settings" / "profile.json"
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert data["username"] == "testuser"


# ======================================================================
# check_profile + save_profile 統合テスト
# ======================================================================


class TestCheckAndSaveIntegration:
    """check_profile と save_profile の統合テスト"""

    def test_full_flow(self, tmp_path):
        """保存前: needs_setup=True -> 保存後: needs_setup=False"""
        # 保存前
        result_before = check_profile(base_dir=tmp_path)
        assert result_before["needs_setup"] is True

        # 保存
        save_result = save_profile(
            {"username": "testuser", "language": "ja"},
            base_dir=tmp_path,
        )
        assert save_result["success"] is True

        # 保存後
        result_after = check_profile(base_dir=tmp_path)
        assert result_after["needs_setup"] is False
        assert result_after["reason"] == "profile_valid"
