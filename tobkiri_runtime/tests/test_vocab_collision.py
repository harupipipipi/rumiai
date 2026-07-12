"""
test_vocab_collision.py - CollisionStrategy のテスト

対象: core_runtime/vocab_registry.py (C-2-impl)
"""
from __future__ import annotations

import logging

import pytest

from core_runtime.vocab_registry import (
    CollisionStrategy,
    VocabKeyCollisionError,
    VocabRegistry,
)


def _make_colliding_registry() -> VocabRegistry:
    """tool と function_calling を同一グループに登録した VocabRegistry を返す"""
    vr = VocabRegistry()
    vr.register_group(["tool", "function_calling"])
    return vr


def _colliding_data():
    """tool と function_calling の両方をキーに持つ dict"""
    return {"tool": "v1", "function_calling": "v2"}


class TestCollisionKeepFirst:
    def test_collision_keep_first(self):
        vr = _make_colliding_registry()
        result, changes = vr.normalize_dict_keys(
            _colliding_data(),
            collision_strategy=CollisionStrategy.KEEP_FIRST,
        )
        assert result["tool"] == "v1"
        collision_entries = [c for c in changes if c[0].startswith("COLLISION:")]
        assert len(collision_entries) > 0


class TestCollisionKeepLast:
    def test_collision_keep_last(self):
        vr = _make_colliding_registry()
        result, changes = vr.normalize_dict_keys(
            _colliding_data(),
            collision_strategy=CollisionStrategy.KEEP_LAST,
        )
        assert result["tool"] == "v2"
        collision_entries = [c for c in changes if c[0].startswith("COLLISION:")]
        assert len(collision_entries) > 0


class TestCollisionRaise:
    def test_collision_raise(self):
        vr = _make_colliding_registry()
        with pytest.raises(VocabKeyCollisionError) as exc_info:
            vr.normalize_dict_keys(
                _colliding_data(),
                collision_strategy=CollisionStrategy.RAISE,
            )
        assert exc_info.value.key == "tool"


class TestCollisionMergeList:
    def test_collision_merge_list(self):
        vr = _make_colliding_registry()
        result, changes = vr.normalize_dict_keys(
            _colliding_data(),
            collision_strategy=CollisionStrategy.MERGE_LIST,
        )
        assert isinstance(result["tool"], list)
        assert "v1" in result["tool"]
        assert "v2" in result["tool"]


class TestCollisionWarn:
    def test_collision_warn(self, caplog):
        vr = _make_colliding_registry()
        with caplog.at_level(logging.WARNING, logger="core_runtime.vocab_registry"):
            result, changes = vr.normalize_dict_keys(
                _colliding_data(),
                collision_strategy=CollisionStrategy.WARN,
            )
        # WARN = 警告 + keep_first
        assert result["tool"] == "v1"
        assert any("collision" in r.message.lower() for r in caplog.records)


class TestCollisionCallback:
    def test_collision_callback(self):
        vr = _make_colliding_registry()

        def my_callback(key, existing, new):
            return f"{existing}+{new}"

        result, changes = vr.normalize_dict_keys(
            _colliding_data(),
            on_collision=my_callback,
        )
        assert result["tool"] == "v1+v2"


class TestCollisionBackwardCompat:
    def test_collision_backward_compat(self):
        """strategy=None でデフォルト動作 (WARN = keep_first)"""
        vr = _make_colliding_registry()
        result, changes = vr.normalize_dict_keys(_colliding_data())
        # デフォルトは WARN → keep_first
        assert result["tool"] == "v1"
        # COLLISION エントリが changes に含まれる（後方互換）
        collision_entries = [c for c in changes if c[0].startswith("COLLISION:")]
        assert len(collision_entries) > 0
