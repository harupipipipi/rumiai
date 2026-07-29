from __future__ import annotations

import hashlib
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
