from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates.services import TemplateBackendServiceRegistry  # noqa: E402


def _write_service_module(tmp_path: Path, package: str, module: str, body: str) -> str:
    package_dir = tmp_path / package
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / f"{module}.py").write_text(body, encoding="utf-8")
    importlib.invalidate_caches()
    return f"{package}.{module}.Service"


def _catalog(entrypoint: str, **overrides: object) -> dict:
    item = {
        "id": "service_piece",
        "service_id": "alpha",
        "entrypoint": entrypoint,
        "lifecycle": "singleton",
        "dependencies": [],
        "template_id": "template.services",
        "piece_id": "service_piece",
        "trust_level": "builtin",
        "_source": "templates/service/template.json",
    }
    item.update(overrides)
    return {"backend_services": [item]}


def test_builtin_service_loads_starts_stops_and_reports_health(tmp_path, monkeypatch):
    package = "template_services_alpha"
    entrypoint = _write_service_module(
        tmp_path,
        package,
        "alpha",
        """
events = []
class Service:
    def start(self):
        events.append("start")
    def stop(self):
        events.append("stop")
    def health(self):
        return {"ready": True}
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )

    assert registry.load_from_catalog(_catalog(entrypoint)) == []
    first = registry.get("alpha")
    second = registry.get("alpha")
    assert first is second
    assert registry.start_all() == []
    assert registry.health()["services"]["alpha"]["health"] == {"ready": True}
    assert registry.stop_all() == []

    module = importlib.import_module(f"{package}.alpha")
    assert module.events == ["start", "stop"]


def test_request_lifecycle_returns_fresh_instance(tmp_path, monkeypatch):
    package = "template_services_request"
    entrypoint = _write_service_module(
        tmp_path,
        package,
        "request_service",
        "class Service:\n    pass\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )
    registry.load_from_catalog(_catalog(entrypoint, lifecycle="request"))

    assert registry.get("alpha") is not registry.get("alpha")


def test_user_template_service_is_rejected(tmp_path, monkeypatch):
    package = "template_services_user"
    entrypoint = _write_service_module(tmp_path, package, "alpha", "class Service:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )

    diagnostics = registry.load_from_catalog(_catalog(entrypoint, trust_level="user"))

    assert diagnostics[0]["code"] == "template.service.non_builtin_rejected"
    assert registry.get("alpha") is None


def test_service_module_escape_is_rejected(tmp_path):
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=("json",),
    )

    diagnostics = registry.load_from_catalog(_catalog("json", service_id="stdlib_json"))

    assert diagnostics[0]["code"] == "template.service.module_escape_rejected"


def test_service_dependency_order_and_reverse_stop(tmp_path, monkeypatch):
    package = "template_services_order"
    _write_service_module(
        tmp_path,
        package,
        "events",
        """
events = []
class Alpha:
    def start(self):
        events.append("alpha:start")
    def stop(self):
        events.append("alpha:stop")
class Beta:
    def start(self):
        events.append("beta:start")
    def stop(self):
        events.append("beta:stop")
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )
    catalog = {
        "backend_services": [
            _catalog(f"{package}.events.Beta", service_id="beta", dependencies=["alpha"])[
                "backend_services"
            ][0],
            _catalog(f"{package}.events.Alpha", service_id="alpha")["backend_services"][0],
        ]
    }

    assert registry.load_from_catalog(catalog) == []
    assert registry.start_all() == []
    assert registry.stop_all() == []

    module = importlib.import_module(f"{package}.events")
    assert module.events == [
        "alpha:start",
        "beta:start",
        "beta:stop",
        "alpha:stop",
    ]


def test_service_dependency_cycle_blocks_all_cycle_members(tmp_path, monkeypatch):
    package = "template_services_cycle"
    entrypoint = _write_service_module(tmp_path, package, "alpha", "class Service:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )
    catalog = {
        "backend_services": [
            _catalog(entrypoint, service_id="alpha", dependencies=["beta"])["backend_services"][0],
            _catalog(entrypoint, service_id="beta", dependencies=["alpha"])["backend_services"][0],
        ]
    }
    registry.load_from_catalog(catalog)

    diagnostics = registry.start_all()

    assert {item["service_id"] for item in diagnostics} >= {"alpha", "beta"}
    assert any(item["code"] == "template.service.dependency_cycle" for item in diagnostics)


def test_service_start_failure_isolates_dependents(tmp_path, monkeypatch):
    package = "template_services_failure"
    _write_service_module(
        tmp_path,
        package,
        "services",
        """
events = []
class Bad:
    def start(self):
        events.append("bad:start")
        raise RuntimeError("boom")
class Dependent:
    def start(self):
        events.append("dependent:start")
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateBackendServiceRegistry(
        defaultspack_root=tmp_path,
        allowed_module_prefixes=(f"{package}.",),
    )
    catalog = {
        "backend_services": [
            _catalog(f"{package}.services.Bad", service_id="bad")["backend_services"][0],
            _catalog(
                f"{package}.services.Dependent",
                service_id="dependent",
                dependencies=["bad"],
            )["backend_services"][0],
        ]
    }
    registry.load_from_catalog(catalog)

    diagnostics = registry.start_all()

    assert any(item["code"] == "template.service.start_failed" for item in diagnostics)
    assert any(item["code"] == "template.service.dependency_failed" for item in diagnostics)
    module = importlib.import_module(f"{package}.services")
    assert module.events == ["bad:start"]


def test_shipped_template_services_load_as_specs_without_user_execution():
    from domain.templates.projectors import build_template_catalog

    catalog = build_template_catalog(defaultspack_root=DEFAULTSPACK_ROOT)
    registry = TemplateBackendServiceRegistry(defaultspack_root=DEFAULTSPACK_ROOT)
    diagnostics = registry.load_from_catalog(catalog)

    assert "model_router" in registry.specs
    assert all(item["code"] != "template.service.non_builtin_rejected" for item in diagnostics)
