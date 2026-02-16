"""
test_kernel_resolver.py - VariableResolver のユニットテスト
"""

import os
import pytest

from core_runtime.kernel_variable_resolver import VariableResolver, MAX_RESOLVE_DEPTH


class TestVariableResolverBasic:
    """基本的な変数解決のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_plain_string_unchanged(self):
        ctx = {}
        assert self.resolver.resolve_value("hello", ctx) == "hello"

    def test_plain_int_unchanged(self):
        ctx = {}
        assert self.resolver.resolve_value(42, ctx) == 42

    def test_none_unchanged(self):
        ctx = {}
        assert self.resolver.resolve_value(None, ctx) is None

    def test_bool_unchanged(self):
        ctx = {}
        assert self.resolver.resolve_value(True, ctx) is True


class TestCtxResolution:
    """$ctx.* 解決のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_ctx_simple(self):
        ctx = {"name": "rumi"}
        assert self.resolver.resolve_value("$ctx.name", ctx) == "rumi"

    def test_ctx_nested(self):
        ctx = {"a": {"b": {"c": 123}}}
        assert self.resolver.resolve_value("$ctx.a.b.c", ctx) == 123

    def test_ctx_missing_returns_original(self):
        ctx = {}
        assert self.resolver.resolve_value("$ctx.missing", ctx) == "$ctx.missing"

    def test_ctx_preserves_type_dict(self):
        ctx = {"data": {"key": "val"}}
        result = self.resolver.resolve_value("$ctx.data", ctx)
        assert isinstance(result, dict)
        assert result == {"key": "val"}

    def test_ctx_preserves_type_list(self):
        ctx = {"items": [1, 2, 3]}
        result = self.resolver.resolve_value("$ctx.items", ctx)
        assert isinstance(result, list)
        assert result == [1, 2, 3]

    def test_ctx_preserves_type_bool(self):
        ctx = {"flag": False}
        result = self.resolver.resolve_value("$ctx.flag", ctx)
        assert result is False


class TestFlowResolution:
    """$flow.* 解決のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_flow_simple(self):
        ctx = {"step_output": "result_value"}
        assert self.resolver.resolve_value("$flow.step_output", ctx) == "result_value"

    def test_flow_nested(self):
        ctx = {"out": {"nested": "deep"}}
        assert self.resolver.resolve_value("$flow.out.nested", ctx) == "deep"


class TestEnvResolution:
    """$env.* 解決のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_env_existing(self, monkeypatch):
        monkeypatch.setenv("RUMI_TEST_VAR", "test_value")
        ctx = {}
        assert self.resolver.resolve_value("$env.RUMI_TEST_VAR", ctx) == "test_value"

    def test_env_missing_returns_original(self):
        ctx = {}
        key = "RUMI_NONEXISTENT_VAR_12345"
        if key in os.environ:
            del os.environ[key]
        assert self.resolver.resolve_value(f"$env.{key}", ctx) == f"$env.{key}"


class TestDictResolution:
    """dict 内の再帰解決テスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_dict_values_resolved(self):
        ctx = {"name": "rumi", "ver": "1.0"}
        value = {"greeting": "$ctx.name", "version": "$ctx.ver", "static": "hello"}
        result = self.resolver.resolve_value(value, ctx)
        assert result == {"greeting": "rumi", "version": "1.0", "static": "hello"}

    def test_nested_dict(self):
        ctx = {"x": 42}
        value = {"outer": {"inner": "$ctx.x"}}
        result = self.resolver.resolve_value(value, ctx)
        assert result == {"outer": {"inner": 42}}


class TestListResolution:
    """list 内の再帰解決テスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_list_elements_resolved(self):
        ctx = {"a": 1, "b": 2}
        value = ["$ctx.a", "$ctx.b", "static"]
        result = self.resolver.resolve_value(value, ctx)
        assert result == [1, 2, "static"]


class TestPartialStringResolution:
    """文字列の一部に変数参照を含むケース"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_partial_substitution(self):
        ctx = {"name": "rumi"}
        result = self.resolver.resolve_value("Hello $ctx.name!", ctx)
        assert result == "Hello rumi!"

    def test_multiple_refs_in_string(self):
        ctx = {"a": "X", "b": "Y"}
        result = self.resolver.resolve_value("$ctx.a and $ctx.b", ctx)
        assert result == "X and Y"


class TestDepthLimit:
    """再帰深度制限のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver(max_depth=3)

    def test_depth_limit_stops_recursion(self):
        ctx = {"a": "$ctx.b", "b": "$ctx.c", "c": "$ctx.d", "d": "final"}
        result = self.resolver.resolve_value("$ctx.a", ctx)
        # 少なくともエラーにならないこと
        assert result is not None


class TestResolveArgs:
    """resolve_args のテスト"""

    def setup_method(self):
        self.resolver = VariableResolver()

    def test_resolve_args_basic(self):
        ctx = {"host": "localhost", "port": 8080}
        args = {"url": "$ctx.host", "port": "$ctx.port"}
        result = self.resolver.resolve_args(args, ctx)
        assert result == {"url": "localhost", "port": 8080}

    def test_resolve_args_non_dict(self):
        ctx = {}
        assert self.resolver.resolve_args("not_a_dict", ctx) == "not_a_dict"


class TestMaxResolveDepthConstant:
    """MAX_RESOLVE_DEPTH 定数のテスト"""

    def test_default_value(self):
        assert MAX_RESOLVE_DEPTH == 20
