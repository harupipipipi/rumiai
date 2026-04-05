"""Tests for dependency_manager.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.dependency_manager import DependencyManager, ModuleDependency


class TestDependencyManager:
    def test_register_and_deps(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("a", required=[], provides=["cap_a"]))
        dm.register(ModuleDependency("b", required=["a"], provides=["cap_b"]))
        assert dm.get_required_deps("b") == ["a"]
        assert dm.get_dependents("a") == ["b"]

    def test_transitive_dependents(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("a", required=[]))
        dm.register(ModuleDependency("b", required=["a"]))
        dm.register(ModuleDependency("c", required=["b"]))
        affected = dm.get_transitive_dependents("a")
        assert "b" in affected
        assert "c" in affected

    def test_resolve_load_order(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("c", required=["b"]))
        dm.register(ModuleDependency("b", required=["a"]))
        dm.register(ModuleDependency("a", required=[]))
        order = dm.resolve_load_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_check_satisfied(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("a", required=[]))
        dm.register(ModuleDependency("b", required=["a"]))
        assert dm.check_satisfied("b", {"a"})["satisfied"]
        assert not dm.check_satisfied("b", set())["satisfied"]

    def test_impact_analysis(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("a"))
        dm.register(ModuleDependency("b", required=["a"]))
        dm.register(ModuleDependency("c", required=["a"]))
        impact = dm.get_impact_analysis("a")
        assert impact["total_affected"] == 2

    def test_catalog(self):
        dm = DependencyManager()
        dm.register(ModuleDependency("a", provides=["cap_a"]))
        cat = dm.get_catalog()
        assert "a" in cat
        assert "cap_a" in cat["a"]["provides"]
