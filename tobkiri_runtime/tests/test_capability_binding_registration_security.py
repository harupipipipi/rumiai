from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import core_runtime.capability_binding_registration as registration
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.paths import PackLocation


def _artifact_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_v3_activation_failure_rolls_back_every_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    module_dir = pack_dir / "runtime"
    module_dir.mkdir(parents=True)
    ecosystem_path = pack_dir / "ecosystem.json"
    manifest_path = pack_dir / "rumi.pack.v3.json"
    ecosystem_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")
    modules = []
    for name in ("one", "two"):
        module_path = module_dir / f"{name}.py"
        module_path.write_text("", encoding="utf-8")
        modules.append(module_path)

    contract_ids = ("rumi.service.sample.one.v1", "rumi.service.sample.two.v1")
    manifest = {
        "pack": {"version": "1.0.0"},
        "contracts": {
            "requires": [],
            "provides": [
                {
                    "id": contract_id,
                    "version": "1.0.0",
                    "provider_instance_id": f"sample.{index}",
                    "isolation": "process",
                }
                for index, contract_id in enumerate(contract_ids)
            ],
        },
        "entrypoints": [
            {
                "contract_id": contract_id,
                "loader": "process",
                "module": f"ecosystem.sample_pack.runtime.{module_path.stem}",
                "artifact_hash": _artifact_hash(module_path),
            }
            for contract_id, module_path in zip(contract_ids, modules, strict=True)
        ],
        "provenance": {
            "content_hash": "sha256:" + ("0" * 64),
            "build_identity": "fixture",
            "trust_class": "system",
        },
    }
    monkeypatch.setattr(
        registration,
        "load_manifest",
        lambda _path: SimpleNamespace(ok=True, value=manifest),
    )
    monkeypatch.setattr(
        registration,
        "_read_manifest",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        registration,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (True, ()),
    )

    attempted_descriptors: list[dict[str, object]] = []
    observer_events: list[tuple[str, object, object]] = []

    class FailingRegistry(InterfaceRegistry):
        def _append_registration_locked(self, key, entry):
            attempted_descriptors.append(entry["value"])
            super()._append_registration_locked(key, entry)
            if key.endswith(".two.v1"):
                raise RuntimeError("injected registration failure")

    registry = FailingRegistry()
    preexisting = {"owner": "preexisting"}
    registry.register(
        f"global_contract.provider.{contract_ids[0]}",
        preexisting,
    )
    registry.observe(
        "global_contract.provider.*",
        lambda key, old, new: observer_events.append((key, old, new)),
    )
    result = registration.CapabilityBindingRegistrationResult()
    location = PackLocation(
        pack_dir=pack_dir,
        pack_id="sample_pack",
        ecosystem_json_path=ecosystem_path,
        pack_subdir=pack_dir,
    )

    handled, activated = registration._register_v3_contract_bindings(
        "sample_pack",
        location,
        registry,
        result,
    )

    assert handled is True
    assert activated is False
    assert result.ok is False
    remaining = registry.find(
        lambda key, _entry: key.startswith("global_contract.")
    )
    assert [entry["value"] for entry in remaining] == [preexisting]
    assert observer_events == []
    assert attempted_descriptors[0]["trust_class"] == "untrusted"
    assert (
        attempted_descriptors[0]["isolation"]
        == "host_measured_at_invocation"
    )
    assert attempted_descriptors[0]["declared_trust_class"] == "system"
    host_attestation = attempted_descriptors[0]["host_attestation"]
    assert callable(host_attestation)
    assert host_attestation() is None
    assert any(
        item["code"] == "v3_contract_activation_rolled_back"
        for item in result.diagnostics
    )


def test_atomic_batch_notifies_only_after_every_entry_is_visible() -> None:
    registry = InterfaceRegistry()
    snapshots: list[dict[str, int]] = []
    registry.observe(
        "global_contract.provider.*",
        lambda _key, _old, _new: snapshots.append(
            registry.list(prefix="global_contract.provider.")
        ),
    )

    registry.register_batch_atomic(
        [
            ("global_contract.provider.one", {"id": "one"}, {}),
            ("global_contract.provider.two", {"id": "two"}, {}),
        ]
    )

    assert snapshots == [
        {
            "global_contract.provider.one": 1,
            "global_contract.provider.two": 1,
        },
        {
            "global_contract.provider.one": 1,
            "global_contract.provider.two": 1,
        },
    ]


def test_failed_python_activation_runs_explicit_teardown_in_reverse_order() -> None:
    teardown_order: list[str] = []

    class ReversibleOperation:
        def __init__(self, name: str) -> None:
            self.name = name

        def __call__(self, _operation, _payload):
            return None

        def __rumi_deactivate__(self) -> None:
            teardown_order.append(self.name)

    pending: list[tuple[str, dict[str, object], dict[str, object]]] = [
        (
            f"global_contract.provider.{name}",
            {
                "contract_id": name,
                "isolation": "host_in_process",
                "operation": ReversibleOperation(name),
            },
            {},
        )
        for name in ("one", "two")
    ]
    result = registration.CapabilityBindingRegistrationResult()

    registration._deactivate_pending_python_operations(
        pending,
        result,
        "sample_pack",
    )

    assert result.ok is True
    assert teardown_order == ["two", "one"]


def test_context_manager_activation_cleans_failure_before_yield(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    pack_dir = runtime_root / "ecosystem" / "context_failure_pack"
    module_dir = pack_dir / "runtime"
    module_dir.mkdir(parents=True)
    marker = tmp_path / "activation.marker"
    module_path = module_dir / "activation.py"
    module_path.write_text(
        "\n".join(
            [
                "from contextlib import contextmanager",
                "from pathlib import Path",
                "",
                "@contextmanager",
                "def activate(_client):",
                f"    marker = Path({str(marker)!r})",
                "    try:",
                "        marker.write_text('acquired', encoding='utf-8')",
                "        raise RuntimeError('injected before yield')",
                "        yield lambda _name, _payload: None",
                "    finally:",
                "        marker.unlink(missing_ok=True)",
            ]
        ),
        encoding="utf-8",
    )
    location = PackLocation(
        pack_dir=pack_dir,
        pack_id="context_failure_pack",
        ecosystem_json_path=pack_dir / "ecosystem.json",
        pack_subdir=pack_dir,
    )

    with pytest.raises(RuntimeError, match="injected before yield"):
        registration._load_python_contract_operation(
            module="ecosystem.context_failure_pack.runtime.activation",
            symbol="activate",
            activation_mode="context_manager",
            pack_location=location,
            client=SimpleNamespace(),
        )

    assert marker.exists() is False
    assert str(runtime_root) not in registration.sys.path


def test_context_managed_python_activation_commit_failure_closes_in_reverse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    pack_dir = runtime_root / "ecosystem" / "context_pack"
    module_dir = pack_dir / "runtime"
    module_dir.mkdir(parents=True)
    ecosystem_path = pack_dir / "ecosystem.json"
    manifest_path = pack_dir / "rumi.pack.v3.json"
    ecosystem_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")
    module_path = module_dir / "activation.py"
    module_path.write_text(
        "\n".join(
            [
                "from contextlib import contextmanager",
                "EVENTS = []",
                "",
                "def _operation(_name, _payload):",
                "    return None",
                "",
                "@contextmanager",
                "def activate_one(_client):",
                "    EVENTS.append('enter-one')",
                "    try:",
                "        yield _operation",
                "    finally:",
                "        EVENTS.append('exit-one')",
                "",
                "@contextmanager",
                "def activate_two(_client):",
                "    EVENTS.append('enter-two')",
                "    try:",
                "        yield _operation",
                "    finally:",
                "        EVENTS.append('exit-two')",
            ]
        ),
        encoding="utf-8",
    )
    contract_ids = ("rumi.service.context.one.v1", "rumi.service.context.two.v1")
    manifest = {
        "pack": {"version": "1.0.0"},
        "contracts": {
            "requires": [],
            "provides": [
                {
                    "id": contract_id,
                    "version": "1.0.0",
                    "provider_instance_id": f"context.{index}",
                }
                for index, contract_id in enumerate(contract_ids)
            ],
        },
        "entrypoints": [
            {
                "contract_id": contract_id,
                "loader": "python",
                "module": "ecosystem.context_pack.runtime.activation",
                "symbol": f"activate_{name}",
                "activation_mode": "context_manager",
                "artifact_hash": _artifact_hash(module_path),
            }
            for name, contract_id in zip(
                ("one", "two"),
                contract_ids,
                strict=True,
            )
        ],
        "provenance": {
            "content_hash": "sha256:" + ("0" * 64),
            "build_identity": "fixture",
            "trust_class": "local",
        },
    }
    monkeypatch.setattr(
        registration,
        "load_manifest",
        lambda _path: SimpleNamespace(ok=True, value=manifest),
    )
    monkeypatch.setattr(
        registration,
        "_read_manifest",
        lambda *_args, **_kwargs: {"host_execution": True},
    )
    monkeypatch.setattr(
        registration,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (True, ()),
    )
    monkeypatch.setattr(
        registration,
        "_host_registration_allowed",
        lambda *_args, **_kwargs: (True, "test"),
    )

    class FailingRegistry(InterfaceRegistry):
        def _append_registration_locked(self, key, entry):
            super()._append_registration_locked(key, entry)
            if key.endswith(".two.v1"):
                raise RuntimeError("injected commit failure")

    registry = FailingRegistry()
    result = registration.CapabilityBindingRegistrationResult()
    location = PackLocation(
        pack_dir=pack_dir,
        pack_id="context_pack",
        ecosystem_json_path=ecosystem_path,
        pack_subdir=pack_dir,
    )

    handled, activated = registration._register_v3_contract_bindings(
        "context_pack",
        location,
        registry,
        result,
    )

    activated_module = importlib.import_module(
        "ecosystem.context_pack.runtime.activation"
    )
    assert handled is True
    assert activated is False
    assert result.ok is False
    assert activated_module.EVENTS == [
        "enter-one",
        "enter-two",
        "exit-two",
        "exit-one",
    ]
    assert registry.list(prefix="global_contract.provider.") == {}


def test_context_managed_operation_deactivates_once() -> None:
    events: list[str] = []

    class Activation:
        def __enter__(self):
            events.append("enter")
            return lambda name, _payload: name

        def __exit__(self, *_exc):
            events.append("exit")

    stack = registration.ExitStack()
    operation = registration._ManagedPythonOperation(
        stack.enter_context(Activation()),
        stack,
    )

    assert operation("ping", {}) == "ping"
    operation.__rumi_deactivate__()
    operation.__rumi_deactivate__()

    assert events == ["enter", "exit"]
    with pytest.raises(RuntimeError, match="deactivated"):
        operation("ping", {})
