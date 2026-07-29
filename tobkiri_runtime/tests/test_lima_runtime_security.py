from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ecosystem.defaultspack.backend.sandbox.isolation.lima_runtime import (
    LIMA_GUEST_WORKSPACE_ROOT,
    LIMA_GUEST_PACK_DATA_ROOT,
    build_guest_bwrap_argv,
    lima_instance_payload,
    resolve_attested_lima_runtime,
    validate_lima_instance_config,
)
from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import (
    ManagedSandboxSupervisor,
)


def _hardened_payload() -> dict[str, object]:
    return {
        "name": "rumi-managed-runtime",
        "status": "Running",
        "vmType": "vz",
        "config": {
            "vmType": "vz",
            "mounts": [],
            "containerd": {"system": False, "user": False},
            "ssh": {
                "forwardAgent": False,
                "forwardX11": False,
                "forwardX11Trusted": False,
            },
            "propagateProxyEnv": False,
            "hostResolver": {"enabled": False},
            "portForwards": [
                {
                    "guestIP": "0.0.0.0",
                    "guestPortRange": [1, 65535],
                    "ignore": True,
                }
            ],
        },
    }


def test_lima_attestation_rejects_host_bridges() -> None:
    payload = _hardened_payload()
    assert validate_lima_instance_config(payload) is None

    config = payload["config"]
    assert isinstance(config, dict)
    config["mounts"] = [{"location": "/Users"}]
    assert "mounts" in str(validate_lima_instance_config(payload))
    config["mounts"] = []
    config["propagateProxyEnv"] = True
    assert "proxy" in str(validate_lima_instance_config(payload))
    config["propagateProxyEnv"] = False
    config["portForwards"] = [
        {"guestPortRange": [22, 22], "ignore": False},
        {"guestPortRange": [1, 65535], "ignore": True},
    ]
    assert "port forwarding" in str(validate_lima_instance_config(payload))


def test_lima_attestation_rejects_missing_mount_measurement() -> None:
    payload = _hardened_payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config.pop("mounts")

    assert "mounts" in str(validate_lima_instance_config(payload))


def test_lima_payload_resolves_omitted_mounts_from_owned_instance_yaml(
    tmp_path: Path,
) -> None:
    instance_dir = tmp_path / "rumi-managed-runtime"
    instance_dir.mkdir()
    (instance_dir / "lima.yaml").write_text("mounts: []\n", encoding="utf-8")
    payload = _hardened_payload()
    config = payload["config"]
    assert isinstance(config, dict)
    config.pop("mounts")
    payload["dir"] = str(instance_dir)

    resolved = lima_instance_payload(
        "limactl",
        "rumi-managed-runtime",
        runner=lambda *_args: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    assert resolved["config"]["mounts"] == []


def test_guest_bwrap_masks_backing_workspaces_and_network() -> None:
    source = f"{LIMA_GUEST_WORKSPACE_ROOT}/.rumi-sbx"
    argv = build_guest_bwrap_argv(
        workspace=source,
        cwd="/workspace",
        argv=("python3", "main.py"),
        env={"HOME": "/home"},
        network_enabled=False,
    )

    assert "--unshare-user" in argv
    assert "--unshare-pid" in argv
    assert "--unshare-net" in argv
    bind_index = argv.index(source)
    mask_index = argv.index(LIMA_GUEST_WORKSPACE_ROOT, bind_index + 1)
    assert bind_index < mask_index
    assert argv[argv.index("--bind") + 2] == "/workspace"
    assert LIMA_GUEST_PACK_DATA_ROOT in argv
    pack_mask = argv.index(LIMA_GUEST_PACK_DATA_ROOT)
    assert argv[pack_mask - 1] == "--tmpfs"


def test_guest_bwrap_rejects_pack_data_path_traversal() -> None:
    with pytest.raises(ValueError, match="Pack data"):
        build_guest_bwrap_argv(
            workspace=f"{LIMA_GUEST_WORKSPACE_ROOT}/.rumi-sbx",
            cwd="/workspace",
            argv=("true",),
            env={},
            network_enabled=False,
            data_dir=f"{LIMA_GUEST_PACK_DATA_ROOT}/pack/../../workspaces",
        )
    with pytest.raises(ValueError, match="sandbox paths"):
        build_guest_bwrap_argv(
            workspace=f"{LIMA_GUEST_WORKSPACE_ROOT}/.rumi-sbx",
            cwd="/workspace/../etc",
            argv=("true",),
            env={},
            network_enabled=False,
        )


@pytest.mark.skipif(
    os.environ.get("RUMI_RUN_LIMA_INTEGRATION") != "1",
    reason="real Lima sandbox integration is opt-in",
)
def test_real_macos_lima_boundary_blocks_host_siblings_and_network(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    limactl, instance = resolve_attested_lima_runtime()
    sibling_secret_dir = f"{LIMA_GUEST_PACK_DATA_ROOT}/other_pack"
    sibling_secret = f"{sibling_secret_dir}/secret.txt"
    subprocess.run(
        [
            limactl,
            "shell",
            instance,
            "--",
            "sh",
            "-c",
            f"mkdir -p {sibling_secret_dir} && printf cross-pack-secret > {sibling_secret}",
        ],
        check=True,
        timeout=10,
    )
    request.addfinalizer(
        lambda: subprocess.run(
            [limactl, "shell", instance, "--", "rm", "-rf", sibling_secret_dir],
            check=False,
            timeout=10,
        )
    )
    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text(
        "import os\n"
        "import socket\n"
        "\n"
        "def run(context, args):\n"
        "    try:\n"
        "        socket.create_connection(('1.1.1.1', 53), 0.25).close()\n"
        "        network = True\n"
        "    except OSError:\n"
        "        network = False\n"
        "    return {\n"
        "        'host_visible': os.path.exists('/Users'),\n"
        f"        'sibling_workspaces': os.listdir('{LIMA_GUEST_WORKSPACE_ROOT}'),\n"
        f"        'sibling_pack_secret': os.path.exists('{sibling_secret}'),\n"
        "        'network': network,\n"
        "    }\n",
        encoding="utf-8",
    )
    runner_path = Path(__file__).resolve().parents[1] / "core_runtime" / "function_runner.py"

    result = ManagedSandboxSupervisor().execute_capability(
        {
            "pack_id": "third_party_pack",
            "function_id": "boundary_probe",
            "function_dir": str(function_dir),
            "main_py_path": str(main_py),
            "entrypoint": "main.py:run",
            "runner_path": str(runner_path),
            "timeout_seconds": 10,
        }
    )

    assert result["success"] is True
    assert result["execution_boundary"] == "managed_sandbox"
    assert result["output"] == {
        "host_visible": False,
        "sibling_workspaces": [],
        "sibling_pack_secret": False,
        "network": False,
    }

    coding_workspace = tmp_path / "coding"
    coding_workspace.mkdir()
    coding = ManagedSandboxSupervisor().execute_coding_terminal(
        {
            "workspace_root": str(coding_workspace),
            "argv": [
                "python3",
                "-c",
                "import json,pathlib;"
                "pathlib.Path('proof.json').write_text("
                "json.dumps({"
                "'host':pathlib.Path('/Users').exists(),"
                f"'sibling_pack_secret':pathlib.Path('{sibling_secret}').exists()"
                "}))",
            ],
            "timeout_seconds": 10,
        }
    )
    assert coding["success"] is True
    assert json.loads((coding_workspace / "proof.json").read_text(encoding="utf-8")) == {
        "host": False,
        "sibling_pack_secret": False,
    }
