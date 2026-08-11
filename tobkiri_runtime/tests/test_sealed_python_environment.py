"""Synthetic contract tests for the fixed sealed Python packaging boundary."""

from __future__ import annotations

import importlib.util
import io
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / ".github" / "scripts" / "build_sealed_python_environment.py"
BOOTSTRAP_PATH = (
    ROOT
    / ".github"
    / "scripts"
    / "sealed_python_sources"
    / "tobkiri_sealed"
    / "bootstrap.py"
)


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "tobkiri_sealed_python_builder_tests",
        BUILDER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()

_SEALED_TEST_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "SystemRoot",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
)


def _clean_sealed_test_environment() -> dict[str, str]:
    """Keep subprocess fixtures free of host loader and Python injection state."""
    return {
        key: value
        for key, value in os.environ.items()
        if key in _SEALED_TEST_ENV_ALLOWLIST
    }


def _make_test_mutable(path: Path) -> None:
    """Temporarily grant a fixture path write access for tamper tests."""
    path.chmod(path.stat().st_mode | 0o200)


def _fixture_sources(base: Path, target: str) -> tuple[Path, Path, Path]:
    """Create a tiny runtime and venv with the same target layout as release."""
    spec = BUILDER.target_spec(target)
    runtime = base / "runtime-source"
    venv = base / "venv-source"
    if spec.windows:
        runtime_python = runtime / "python.exe"
        stdlib = runtime / "Lib"
        venv_python = venv / "Scripts" / "python.exe"
        site_packages = venv / "Lib" / "site-packages"
        runtime_native = runtime / "DLLs" / "_ssl.pyd"
    else:
        runtime_python = runtime / "bin" / "python3"
        stdlib = runtime / "lib" / "python3.13"
        venv_python = venv / "bin" / "python3"
        site_packages = venv / "lib" / "python3.13" / "site-packages"
        runtime_native = stdlib / "lib-dynload" / "_ssl.so"

    runtime_python.parent.mkdir(parents=True, exist_ok=True)
    runtime_python.write_bytes(b"synthetic native CPython executable\n")
    runtime_python.chmod(0o755)
    (stdlib / "encodings").mkdir(parents=True)
    (stdlib / "os.py").write_text("synthetic stdlib\n", encoding="utf-8")
    (stdlib / "encodings" / "__init__.py").write_text(
        "synthetic encoding\n",
        encoding="utf-8",
    )
    (stdlib / "locale.py").write_text(
        "def normalize(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    (stdlib / "shutil.py").write_text(
        "class _TerminalSize:\n"
        "    columns = 80\n"
        "def get_terminal_size(fallback=(80, 24)):\n"
        "    return _TerminalSize()\n",
        encoding="utf-8",
    )
    runtime_native.parent.mkdir(parents=True, exist_ok=True)
    runtime_native.write_bytes(b"synthetic native extension\n")
    if not spec.windows:
        (stdlib / "native_alias.so").symlink_to(runtime_native)

    venv_python.parent.mkdir(parents=True, exist_ok=True)
    if spec.windows:
        venv_python.write_bytes(runtime_python.read_bytes())
        venv_python.chmod(0o755)
    else:
        venv_python.symlink_to(runtime_python)
    site_packages.mkdir(parents=True)
    (site_packages / "fixture_dependency.py").write_text(
        "VALUE = 'sealed'\n",
        encoding="utf-8",
    )
    (venv / "pyvenv.cfg").write_text(
        "home = /build-machine/python\ninclude-system-site-packages = false\n",
        encoding="utf-8",
    )
    if not spec.windows:
        (site_packages / "native_alias.so").symlink_to(runtime_native)

    application = base / "application-source"
    (application / "ecosystem/defaultspack/defaultspack").mkdir(parents=True)
    (application / "core_runtime/host_broker").mkdir(parents=True)
    (application / "app.py").write_text(
        "import json, os\n"
        "def main(argv=None):\n"
        "    with open(os.environ['ROLE_MARKER'], 'a') as handle:\n"
        "        handle.write(json.dumps(['typed', list(argv or [])]) + '\\n')\n"
        "    return 7\n",
        encoding="utf-8",
    )
    (application / "ecosystem/defaultspack/defaultspack/desktop_app.py").write_text(
        "import json, os\n"
        "def prepare_for_sealed_dispatch(scope):\n"
        "    scope.app_root_for(__file__)\n"
        "def main(argv=None):\n"
        "    with open(os.environ['ROLE_MARKER'], 'a') as handle:\n"
        "        handle.write(json.dumps(['defaultspack', list(argv or [])]) + '\\n')\n"
        "    return 8\n",
        encoding="utf-8",
    )
    (application / "core_runtime/host_broker/computer_host_helper.py").write_text(
        "import json, os, sys\n"
        "def main():\n"
        "    request = json.loads(sys.stdin.read())\n"
        "    with open(os.environ['ROLE_MARKER'], 'a') as handle:\n"
        "        handle.write(json.dumps(['host_helper', request]) + '\\n')\n"
        "    print(json.dumps({'ok': True}))\n"
        "    return 9\n",
        encoding="utf-8",
    )

    output = base / "snapshot-not-python-runtime"
    BUILDER.assemble_environment(
        output,
        runtime,
        venv,
        target,
        release_digest="a" * 64,
        application_source=application,
    )
    return runtime, venv, output


@pytest.mark.parametrize(
    "target",
    ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc"),
)
def test_manifest_is_strict_complete_and_reproducible(tmp_path: Path, target: str) -> None:
    """Both fixed platform layouts produce byte-identical sealed manifests."""
    first = _fixture_sources(tmp_path / "first", target)[2]
    second = _fixture_sources(tmp_path / "second", target)[2]
    first_manifest = first / BUILDER.MANIFEST_FILENAME
    second_manifest = second / BUILDER.MANIFEST_FILENAME

    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    first_document = json.loads(first_manifest.read_text(encoding="utf-8"))
    assert tuple(first_document) == BUILDER.MANIFEST_KEYS
    assert tuple(first_document["package_provenance"]) == (
        "kind",
        "package_id",
        "release_digest",
    )
    assert first_document["package_provenance"]["package_id"] == "dev.tobkiri.launcher"
    assert tuple(first_document["sentinels"]) == BUILDER.SENTINEL_KEYS
    records = first_document["files"]
    assert records == sorted(records, key=lambda entry: entry["path"])
    assert all(entry.keys() == set(BUILDER.FILE_KEYS) for entry in records)
    assert BUILDER.MANIFEST_FILENAME not in {entry["path"] for entry in records}
    assert "lease.v1" in {entry["path"] for entry in records}
    assert first_document["environment_digest"] == BUILDER._files_digest(records)
    assert BUILDER.validate_environment(first, target, run_native_smoke=False)


def test_manifest_contains_fixed_entrypoints_and_bootstrap_paths(tmp_path: Path) -> None:
    """The Unix layout inventories every fixed role and installed bootstrap."""
    output = _fixture_sources(tmp_path, "x86_64-unknown-linux-gnu")[2]
    paths = {
        entry["path"]
        for entry in json.loads(
            (output / BUILDER.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )["files"]
    }
    assert {
        "lease.v1",
        "venv/bin/python3",
        "venv/lib/python3.13/site-packages/tobkiri_sealed/bootstrap.py",
        "app/kernel_entry.py",
        "app/defaultspack_entry.py",
        "app/host_helper_entry.py",
        "sentinels/stdlib.sha256",
        "sentinels/site-packages.sha256",
        "sentinels/native.sha256",
    } <= paths
    assert {
        "app/app.py",
        "app/ecosystem/defaultspack/defaultspack/desktop_app.py",
        "app/core_runtime/host_broker/computer_host_helper.py",
    } <= paths


def test_assembly_materializes_links_and_freezes_the_complete_snapshot(
    tmp_path: Path,
) -> None:
    """The final resource has no links, bytecode, or write bits."""
    output = _fixture_sources(tmp_path, "x86_64-unknown-linux-gnu")[2]
    alias = output / "venv/lib/python3.13/site-packages/native_alias.so"
    assert alias.is_file()
    assert not alias.is_symlink()
    assert alias.read_bytes() == b"synthetic native extension\n"
    runtime_alias = output / "runtime/lib/python3.13/native_alias.so"
    assert runtime_alias.is_file()
    assert not runtime_alias.is_symlink()

    for path in (output, *output.rglob("*")):
        assert not path.is_symlink(), path
        assert not path.stat().st_mode & 0o222, path
    assert all(
        not any(part == "__pycache__" for part in path.relative_to(output).parts)
        and path.suffix not in {".pyc", ".pyo"}
        for path in output.rglob("*")
    )


@pytest.mark.parametrize("case", ("outside", "cycle"))
def test_venv_link_materializer_rejects_escape_and_cycle(
    tmp_path: Path,
    case: str,
) -> None:
    """Only links inside the assembly root may be materialized."""
    root = tmp_path / "assembly" / "venv"
    python_dir = root / "bin"
    python_dir.mkdir(parents=True)
    if case == "outside":
        target = tmp_path / "outside-python"
        target.write_bytes(b"outside\n")
        (python_dir / "python3").symlink_to(target)
    else:
        (python_dir / "python3").symlink_to(python_dir / "loop")
        (python_dir / "loop").symlink_to(python_dir / "python3")

    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER._materialize_venv_links(
            root,
            BUILDER.target_spec("x86_64-unknown-linux-gnu"),
        )


def test_runtime_link_materializer_rejects_outside_target(tmp_path: Path) -> None:
    """CPython runtime aliases cannot resolve outside their runtime root."""
    root = tmp_path / "runtime"
    (root / "lib").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside\n")
    (root / "lib" / "alias.so").symlink_to(outside)

    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER._materialize_runtime_links(
            root,
            BUILDER.target_spec("x86_64-unknown-linux-gnu"),
        )


def test_bootstrap_wire_dispatches_all_roles_and_publishes_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent wire reaches each canonical role with exact argv/stdin."""
    output = _fixture_sources(tmp_path / "sealed", "x86_64-unknown-linux-gnu")[2]
    assert output.name != "python-runtime"
    marker = tmp_path / "roles.jsonl"

    source_root = ROOT / ".github" / "scripts" / "sealed_python_sources"
    old_prefix = sys.prefix
    old_base_prefix = sys.base_prefix
    old_executable = sys.executable
    old_path = sys.path[:]
    old_argv = sys.argv[:]
    old_dont_write_bytecode = sys.dont_write_bytecode
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    old_env = os.environ.copy()
    clean_env = _clean_sealed_test_environment()
    os.environ.clear()
    os.environ.update(clean_env)
    sys.path = [
        str(output / "venv/lib/python3.13/site-packages"),
        str(output / "runtime/lib/python3.13"),
    ]
    sys.prefix = str(output / "venv")
    sys.base_prefix = str(output / "runtime")
    sys.executable = str(output / "venv/bin/python3")
    sys.dont_write_bytecode = True
    sys.modules.pop("tobkiri_sealed.bootstrap", None)
    sys.modules.pop("tobkiri_sealed", None)
    monkeypatch.setenv("ROLE_MARKER", str(marker))
    monkeypatch.setenv(
        "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256",
        BUILDER._sha256_file(output / BUILDER.MANIFEST_FILENAME),
    )
    try:
        sys.path.insert(0, str(source_root))
        import tobkiri_sealed.bootstrap as bootstrap
        sys.path = [
            str(output / "venv/lib/python3.13/site-packages"),
            str(output / "runtime/lib/python3.13"),
        ]

        for role, role_args, expected_return in (
            ("typed", ("--health",), 7),
            ("defaultspack", ("--port", "8766"), 8),
            ("host_helper", (), 9),
        ):
            attestation_dir = tmp_path / f"attestation-{role}"
            attestation_dir.mkdir()
            nonce = "a" * 64
            attestation = attestation_dir / f"startup-{nonce}.json"
            if role == "host_helper":
                sys.stdin = io.StringIO('{"function_id":"computer.observe"}')
                sys.stdout = io.StringIO()
            result = bootstrap.main(
                [
                    "--role",
                    role,
                    "--nonce",
                    nonce,
                    "--attestation",
                    str(attestation),
                    "--manifest",
                    str(output / BUILDER.MANIFEST_FILENAME),
                    "--environment-root",
                    str(output),
                    "--",
                    *role_args,
                ]
            )
            assert result == expected_return
            evidence = json.loads(attestation.read_text(encoding="utf-8"))
            assert list(evidence) == [
                "schema",
                "nonce",
                "role",
                "environment_digest",
                "executable",
                "prefix",
                "base_prefix",
                "sys_path",
                "stdlib_sha256",
                "site_packages_sha256",
                "native_sha256",
                "lifetime_lease",
            ]
            assert evidence["role"] == role
            assert evidence["nonce"] == nonce
            assert evidence["lifetime_lease"] is True
            assert attestation.stat().st_mode & 0o777 == 0o600
            assert all(
                Path(item).resolve().is_relative_to(output)
                for item in evidence["sys_path"]
            )
            assert all(
                Path(item).resolve().is_relative_to(output) for item in sys.path
            )
            assert list(sys.path) == evidence["sys_path"]
            if role == "typed":
                with pytest.raises(bootstrap.SealedBootstrapError, match="already exists"):
                    bootstrap.main(
                        [
                            "--role",
                            role,
                            "--nonce",
                            nonce,
                            "--attestation",
                            str(attestation),
                            "--manifest",
                            str(output / BUILDER.MANIFEST_FILENAME),
                            "--environment-root",
                            str(output),
                            "--",
                            *role_args,
                        ]
                    )
            sys.path = [
                str(output / "venv/lib/python3.13/site-packages"),
                str(output / "runtime/lib/python3.13"),
            ]
            sys.stdin = old_stdin
            sys.stdout = old_stdout
        records = [json.loads(line) for line in marker.read_text().splitlines()]
        assert records == [
            ["typed", ["--health"]],
            ["defaultspack", ["--port", "8766"]],
            ["host_helper", {"function_id": "computer.observe"}],
        ]
    finally:
        sys.prefix = old_prefix
        sys.base_prefix = old_base_prefix
        sys.executable = old_executable
        sys.path = old_path
        sys.argv = old_argv
        sys.dont_write_bytecode = old_dont_write_bytecode
        sys.stdin = old_stdin
        sys.stdout = old_stdout
        os.environ.clear()
        os.environ.update(old_env)
        sys.modules.pop("tobkiri_sealed.bootstrap", None)
        sys.modules.pop("tobkiri_sealed", None)


def test_bootstrap_rejects_path_environment_and_external_import_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject inherited path variables, cwd, user-site, and shadow roots."""
    output = _fixture_sources(tmp_path / "sealed", "x86_64-unknown-linux-gnu")[2]
    source_root = ROOT / ".github" / "scripts" / "sealed_python_sources"
    external = tmp_path / "external-shadow"
    external.mkdir()
    for filename in ("sitecustomize.py", "usercustomize.py", "shadow.pth"):
        (external / filename).write_text(
            "raise RuntimeError('external metadata executed')\n",
            encoding="utf-8",
        )
    (external / "app.py").write_text(
        "raise RuntimeError('external shadow imported')\n",
        encoding="utf-8",
    )
    attestation_dir = tmp_path / "attestation"
    attestation_dir.mkdir()
    nonce = "c" * 64

    old_path = sys.path[:]
    old_prefix = sys.prefix
    old_base_prefix = sys.base_prefix
    old_executable = sys.executable
    sys.modules.pop("tobkiri_sealed.bootstrap", None)
    sys.modules.pop("tobkiri_sealed", None)
    forbidden = (
        "REPO",
        "RUMI_CORE_DIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "DYLD_LIBRARY_PATH",
        "LD_LIBRARY_PATH",
    )
    try:
        sys.path = [
            str(output / "venv/lib/python3.13/site-packages"),
            str(output / "runtime/lib/python3.13"),
        ]
        sys.prefix = str(output / "venv")
        sys.base_prefix = str(output / "runtime")
        sys.executable = str(output / "venv/bin/python3")
        for key in forbidden:
            monkeypatch.delenv(key, raising=False)
        sys.path.insert(0, str(source_root))
        import tobkiri_sealed.bootstrap as bootstrap

        for key in forbidden:
            monkeypatch.setenv(key, str(external))
            attestation = attestation_dir / f"startup-{nonce}.json"
            with pytest.raises(bootstrap.SealedBootstrapError, match="forbidden"):
                bootstrap.main(
                    [
                        "--role",
                        "defaultspack",
                        "--nonce",
                        nonce,
                        "--attestation",
                        str(attestation),
                        "--manifest",
                        str(output / BUILDER.MANIFEST_FILENAME),
                        "--environment-root",
                        str(output),
                        "--",
                    ]
                )
            assert not attestation.exists()
            monkeypatch.delenv(key, raising=False)

        sys.path = [
            str(output / "venv/lib/python3.13/site-packages"),
            str(output / "runtime/lib/python3.13"),
            str(external),
        ]
        monkeypatch.chdir(external)
        attestation = attestation_dir / f"startup-{nonce}.json"
        with pytest.raises(bootstrap.SealedBootstrapError, match="escaped"):
            bootstrap.main(
                [
                    "--role",
                    "defaultspack",
                    "--nonce",
                    nonce,
                    "--attestation",
                    str(attestation),
                    "--manifest",
                    str(output / BUILDER.MANIFEST_FILENAME),
                    "--environment-root",
                    str(output),
                    "--",
                ]
            )
        assert not attestation.exists()
    finally:
        sys.path = old_path
        sys.prefix = old_prefix
        sys.base_prefix = old_base_prefix
        sys.executable = old_executable
        sys.modules.pop("tobkiri_sealed.bootstrap", None)
        sys.modules.pop("tobkiri_sealed", None)


def test_fresh_isolated_subprocess_rejects_external_launch_metadata(
    tmp_path: Path,
) -> None:
    """A real isolated interpreter starts only from the sealed snapshot."""
    target = (
        "x86_64-pc-windows-msvc"
        if os.name == "nt"
        else "x86_64-unknown-linux-gnu"
    )
    output = _fixture_sources(tmp_path / "sealed", target)[2]
    source_root = ROOT / ".github" / "scripts" / "sealed_python_sources"
    external = tmp_path / "external-shadow"
    external.mkdir()
    metadata_code = (
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['METADATA_MARKER']).write_text('executed')\n"
    )
    for filename in ("sitecustomize.py", "usercustomize.py", "shadow.pth"):
        (external / filename).write_text(metadata_code, encoding="utf-8")
    (external / "app.py").write_text(metadata_code, encoding="utf-8")
    user_site = external / "user-site/lib/python3.13/site-packages"
    user_site.mkdir(parents=True)
    for filename in ("sitecustomize.py", "usercustomize.py", "user-shadow.pth"):
        (user_site / filename).write_text(metadata_code, encoding="utf-8")

    child_code = """
import json
import os
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
output = Path(sys.argv[2])
attestation = Path(sys.argv[3])
if os.name == "nt":
    site_packages = output / "venv/Lib/site-packages"
    stdlib = output / "runtime/Lib"
    executable = output / "venv/Scripts/python.exe"
else:
    import fcntl
    site_packages = output / "venv/lib/python3.13/site-packages"
    stdlib = output / "runtime/lib/python3.13"
    executable = output / "venv/bin/python3"
sys.path.insert(0, str(source_root))
import tobkiri_sealed.bootstrap as bootstrap

sealed_path = [
    str(site_packages),
    str(stdlib),
]
if os.environ.get("INJECT_EXTERNAL_PATH"):
    sys.path = [os.environ["INJECT_EXTERNAL_PATH"], *sealed_path]
else:
    sys.path = sealed_path
sys.prefix = str(output / "venv")
sys.base_prefix = str(output / "runtime")
sys.executable = str(executable)
sys.dont_write_bytecode = True
result = bootstrap.main(
    [
        "--role",
        "defaultspack",
        "--nonce",
        "d" * 64,
        "--attestation",
        str(attestation),
        "--manifest",
        str(output / "sealed-environment.v1.json"),
        "--environment-root",
        str(output),
        "--",
        "--subprocess",
    ]
)
print(json.dumps({"result": result, "sys_path": list(sys.path)}))
"""
    base_env = _clean_sealed_test_environment()
    base_env["ROLE_MARKER"] = str(tmp_path / "roles.jsonl")
    base_env["TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256"] = BUILDER._sha256_file(
        output / BUILDER.MANIFEST_FILENAME
    )
    base_env["METADATA_MARKER"] = str(tmp_path / "metadata-success")
    attestation_name = "startup-" + "d" * 64 + ".json"
    success_attestation = tmp_path / "attestation-success" / attestation_name
    success_attestation.parent.mkdir()
    success = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            child_code,
            str(source_root),
            str(output),
            str(success_attestation),
        ],
        cwd=external,
        env=base_env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert success.returncode == 0, success.stderr
    child_evidence = json.loads(success.stdout)
    attestation_evidence = json.loads(
        success_attestation.read_text(encoding="utf-8")
    )
    assert child_evidence["result"] == 8
    assert child_evidence["sys_path"] == attestation_evidence["sys_path"]
    assert not Path(base_env["METADATA_MARKER"]).exists()
    assert success_attestation.is_file()

    for index, key in enumerate(
        (
            "REPO",
            "RUMI_CORE_DIR",
            "PYTHONPATH",
            "PYTHONHOME",
            "DYLD_LIBRARY_PATH",
            "LD_LIBRARY_PATH",
        ),
        start=1,
    ):
        environment = base_env.copy()
        environment[key] = str(external)
        environment["METADATA_MARKER"] = str(tmp_path / f"metadata-{index}")
        attestation = tmp_path / f"attestation-{index}" / attestation_name
        attestation.parent.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                child_code,
                str(source_root),
                str(output),
                str(attestation),
            ],
            cwd=external,
            env=environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert result.returncode != 0
        assert "forbidden injection keys" in result.stderr
        assert not attestation.exists()
        assert not Path(environment["METADATA_MARKER"]).exists()

    environment = base_env.copy()
    environment["INJECT_EXTERNAL_PATH"] = str(external)
    environment["METADATA_MARKER"] = str(tmp_path / "metadata-path")
    attestation = tmp_path / "attestation-path" / attestation_name
    attestation.parent.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            child_code,
            str(source_root),
            str(output),
            str(attestation),
        ],
        cwd=external,
        env=environment,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert not attestation.exists()
    assert not Path(environment["METADATA_MARKER"]).exists()


@pytest.mark.parametrize(
    ("target", "output"),
    (
        (
            "aarch64-apple-darwin",
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin)\n",
        ),
        (
            "x86_64-apple-darwin",
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-apple-darwin)\n",
        ),
        (
            "x86_64-unknown-linux-gnu",
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)\n",
        ),
        (
            "x86_64-pc-windows-msvc",
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-pc-windows-msvc)\n",
        ),
    ),
)
def test_uv_parser_accepts_official_structured_output(
    target: str,
    output: str,
) -> None:
    """Official uv 0.11.14 output binds version and executable identity."""
    identity = BUILDER.parse_uv_version(output, expected_target=target)
    assert identity.version == BUILDER.UV_VERSION
    assert identity.revision == "3fdfdc7d4"
    assert identity.release_date == "2026-05-12"
    assert identity.target == target


@pytest.mark.parametrize(
    ("output", "expected_target"),
    (
        (
            "uv 0.11.13 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
        (
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
        (
            "warning: uv 0.11.14 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
        ("uv 0.11.14\n", "aarch64-apple-darwin"),
        (
            "uv 0.11.14 (3FDFDC7D4 2026-05-12 aarch64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
        (
            "uv 0.11.14 (3fdfdc7d4 2026-5-12 aarch64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
        (
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin extra)\n",
            "aarch64-apple-darwin",
        ),
        (
            "uv 0.11.14 (3fdfdc7d4 2026-05-12 arm64-apple-darwin)\n",
            "aarch64-apple-darwin",
        ),
    ),
)
def test_uv_parser_rejects_version_prefix_tamper_and_wrong_binary(
    output: str,
    expected_target: str,
) -> None:
    """Unexpected display text, version, metadata, or target fails closed."""
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER.parse_uv_version(output, expected_target=expected_target)


def test_uv_version_runner_uses_structured_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generator checks the executable-reported target, not just text."""
    output = "uv 0.11.14 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin)\n"
    monkeypatch.setattr(
        BUILDER.subprocess,
        "run",
        lambda *_args, **_kwargs: types.SimpleNamespace(stdout=output),
    )
    identity = BUILDER._uv_version(Path("uv"), "aarch64-apple-darwin")
    assert identity.target == "aarch64-apple-darwin"
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER._uv_version(Path("wrong-architecture-uv"), "x86_64-apple-darwin")


def _write_fake_uv(path: Path, output: str, *, mode: int = 0o555) -> None:
    """Write a tiny executable that can exercise the uv identity gate."""
    path.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{output.rstrip()}'\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def test_builder_never_uses_fake_path_uv_when_bundled_binary_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PATH executable cannot satisfy the production pinned-uv contract."""
    repo_root = tmp_path / "repo"
    bundled = repo_root / "tobkiri_runtime" / "bundled"
    bundled.mkdir(parents=True)
    requirements = repo_root / "tobkiri_runtime" / "requirements.txt"
    requirements.write_text("", encoding="utf-8")
    fake_dir = tmp_path / "fake-bin"
    fake_dir.mkdir()
    marker = tmp_path / "executed"
    fake_uv = fake_dir / "uv"
    _write_fake_uv(
        fake_uv,
        "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)",
    )
    fake_uv.chmod(0o755)
    fake_uv.write_text(
        fake_uv.read_text(encoding="utf-8")
        + f"touch '{marker}'\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o555)
    monkeypatch.setenv("PATH", str(fake_dir))

    with pytest.raises(BUILDER.SealedEnvironmentError, match="disappeared"):
        BUILDER.build_environment(
            repo_root,
            "x86_64-unknown-linux-gnu",
            requirements_path=requirements,
        )
    assert not marker.exists()


def test_builder_rejects_correct_version_stdout_spoof(
    tmp_path: Path,
) -> None:
    """A fake executable cannot pass by printing the pinned version."""
    expected_target = "x86_64-unknown-linux-gnu"
    repo_root = tmp_path / "repo"
    bundled = repo_root / "tobkiri_runtime" / "bundled"
    bundled.mkdir(parents=True)
    uv = bundled / "uv"
    _write_fake_uv(
        uv,
        "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)",
    )
    with pytest.raises(BUILDER.SealedEnvironmentError, match="SHA256 mismatch"):
        BUILDER._validate_pinned_uv_executable(
            repo_root,
            uv,
            BUILDER.target_spec(expected_target),
        )


@pytest.mark.parametrize(
    "output",
    (
        "uv 0.11.13 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)",
        "uv 0.11.14 (3fdfdc7d4 2026-05-12 aarch64-apple-darwin)",
    ),
)
def test_builder_rejects_wrong_version_or_target_after_byte_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    """Even a byte-bound fixture must report the requested official identity."""
    expected_target = "x86_64-unknown-linux-gnu"
    repo_root = tmp_path / "repo"
    bundled = repo_root / "tobkiri_runtime" / "bundled"
    bundled.mkdir(parents=True)
    uv = bundled / "uv"
    _write_fake_uv(uv, output)
    monkeypatch.setitem(
        BUILDER.UV_BINARY_SHA256_BY_TARGET,
        expected_target,
        BUILDER._sha256_file(uv),
    )
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER._validate_pinned_uv_executable(
            repo_root,
            uv,
            BUILDER.target_spec(expected_target),
        )


def test_builder_rejects_owner_writable_staged_uv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extracted executable is immutable before uv is ever invoked."""
    expected_target = "x86_64-unknown-linux-gnu"
    repo_root = tmp_path / "repo"
    bundled = repo_root / "tobkiri_runtime" / "bundled"
    bundled.mkdir(parents=True)
    uv = bundled / "uv"
    _write_fake_uv(
        uv,
        "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)",
        mode=0o755,
    )
    monkeypatch.setitem(
        BUILDER.UV_BINARY_SHA256_BY_TARGET,
        expected_target,
        BUILDER._sha256_file(uv),
    )
    with pytest.raises(BUILDER.SealedEnvironmentError, match="owner-writable"):
        BUILDER._validate_pinned_uv_executable(
            repo_root,
            uv,
            BUILDER.target_spec(expected_target),
        )


def test_pinned_uv_archive_and_binary_maps_cover_every_supported_target() -> None:
    """Every release target has both immutable archive and member identities."""
    targets = set(BUILDER.TARGETS)
    assert set(BUILDER.UV_ARCHIVE_SHA256_BY_TARGET) == targets
    assert set(BUILDER.UV_BINARY_SHA256_BY_TARGET) == targets
    assert all(
        len(digest) == 64 and digest == digest.lower()
        for digest in (
            *BUILDER.UV_ARCHIVE_SHA256_BY_TARGET.values(),
            *BUILDER.UV_BINARY_SHA256_BY_TARGET.values(),
        )
    )


def test_pinned_uv_maps_match_the_resource_preparer() -> None:
    """The generator and resource stage cannot silently drift in their pins."""
    preparer_path = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
    spec = importlib.util.spec_from_file_location("sealed_uv_preparer_tests", preparer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {preparer_path}")
    preparer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = preparer
    spec.loader.exec_module(preparer)
    assert preparer.UV_PINNED_VERSION == BUILDER.UV_VERSION
    assert preparer.UV_SHA256_BY_TARGET == BUILDER.UV_ARCHIVE_SHA256_BY_TARGET
    assert preparer.UV_BINARY_SHA256_BY_TARGET == BUILDER.UV_BINARY_SHA256_BY_TARGET
    assert preparer.expected_uv_member("x86_64-unknown-linux-gnu") == (
        "uv-x86_64-unknown-linux-gnu/uv"
    )
    assert preparer.expected_uv_member("x86_64-pc-windows-msvc") == "uv.exe"


def test_sealed_basename_alone_does_not_select_packaged_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A familiar snapshot basename cannot forge the bootstrap-issued scope."""
    sealed_root = tmp_path / "python-runtime"
    app_root = sealed_root / "app"
    desktop_path = app_root / "ecosystem/defaultspack/defaultspack/desktop_app.py"
    desktop_path.parent.mkdir(parents=True)
    desktop_path.write_text(
        (
            ROOT
            / "tobkiri_runtime/ecosystem/defaultspack/defaultspack/desktop_app.py"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (sealed_root / "sealed-environment.v1.json").write_text("{}", encoding="utf-8")
    (sealed_root / "lease.v1").write_text("lease\n", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    old_path = sys.path[:]
    old_ecosystem = sys.modules.get("ecosystem")
    old_defaultspack = sys.modules.get("ecosystem.defaultspack")
    module = types.ModuleType("sealed_desktop_test")
    module.__file__ = str(desktop_path)
    module.__package__ = ""
    source = desktop_path.read_text(encoding="utf-8")
    try:
        exec(compile(source, str(desktop_path), "exec"), module.__dict__)
        sys.path = []
        for key in ("REPO", "RUMI_CORE_DIR", "RUMI_APP_DIR"):
            monkeypatch.setenv(key, str(external))
        assert module._sealed_app_root() is None
        module._ensure_import_path()
        assert module._sealed_app_root() is None
        assert str(external) in sys.path
    finally:
        sys.path = old_path
        if old_ecosystem is None:
            sys.modules.pop("ecosystem", None)
        else:
            sys.modules["ecosystem"] = old_ecosystem
        if old_defaultspack is None:
            sys.modules.pop("ecosystem.defaultspack", None)
        else:
            sys.modules["ecosystem.defaultspack"] = old_defaultspack


def test_explicit_scope_selects_custom_named_snapshot_for_defaultspack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The actual Defaultspack module accepts only the bootstrap scope."""
    sealed_root = tmp_path / "snapshot-7f3c"
    app_root = sealed_root / "app"
    desktop_path = app_root / "ecosystem/defaultspack/defaultspack/desktop_app.py"
    desktop_path.parent.mkdir(parents=True)
    desktop_path.write_text(
        (
            ROOT
            / "tobkiri_runtime/ecosystem/defaultspack/defaultspack/desktop_app.py"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest_path = sealed_root / "sealed-environment.v1.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    (sealed_root / "lease.v1").write_text("lease\n", encoding="utf-8")
    app_root.chmod(0o555)
    desktop_path.chmod(0o444)
    external = tmp_path / "external"
    external.mkdir()
    old_path = sys.path[:]
    old_ecosystem = sys.modules.get("ecosystem")
    old_defaultspack = sys.modules.get("ecosystem.defaultspack")
    old_bootstrap = sys.modules.get("tobkiri_sealed.bootstrap")
    old_package = sys.modules.get("tobkiri_sealed")
    module = types.ModuleType("custom_snapshot_desktop_test")
    module.__file__ = str(desktop_path)
    module.__package__ = ""
    try:
        sys.path = old_path[:]
        sys.modules.pop("tobkiri_sealed.bootstrap", None)
        sys.modules.pop("tobkiri_sealed", None)
        sys.path.insert(0, str(ROOT / ".github/scripts/sealed_python_sources"))
        import tobkiri_sealed.bootstrap as bootstrap

        source = desktop_path.read_text(encoding="utf-8")
        exec(compile(source, str(desktop_path), "exec"), module.__dict__)
        sys.path = []
        for key in ("REPO", "RUMI_CORE_DIR", "RUMI_APP_DIR"):
            monkeypatch.setenv(key, str(external))
        scope = bootstrap._SealedDispatchScope(
            bootstrap._SCOPE_CONSTRUCTOR_TOKEN,
            sealed_root,
            manifest_path,
            BUILDER._sha256_file(manifest_path),
            "a" * 64,
            bootstrap.ROLE_TARGETS["defaultspack"],
        )
        module.prepare_for_sealed_dispatch(scope)
        assert module._sealed_app_root() == app_root
        assert sys.path == [str(app_root)]
        assert str(external) not in sys.path
    finally:
        sys.path = old_path
        if old_ecosystem is None:
            sys.modules.pop("ecosystem", None)
        else:
            sys.modules["ecosystem"] = old_ecosystem
        if old_defaultspack is None:
            sys.modules.pop("ecosystem.defaultspack", None)
        else:
            sys.modules["ecosystem.defaultspack"] = old_defaultspack
        if old_bootstrap is None:
            sys.modules.pop("tobkiri_sealed.bootstrap", None)
        else:
            sys.modules["tobkiri_sealed.bootstrap"] = old_bootstrap
        if old_package is None:
            sys.modules.pop("tobkiri_sealed", None)
        else:
            sys.modules["tobkiri_sealed"] = old_package


def test_bootstrap_rejects_unknown_parent_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap-only options cannot be smuggled through the role boundary."""
    output = _fixture_sources(tmp_path, "x86_64-unknown-linux-gnu")[2]
    source_root = ROOT / ".github" / "scripts" / "sealed_python_sources"
    attestation_dir = tmp_path / "attestation"
    attestation_dir.mkdir()
    nonce = "b" * 64
    attestation = attestation_dir / f"startup-{nonce}.json"
    old_path = sys.path[:]
    old_prefix = sys.prefix
    old_base_prefix = sys.base_prefix
    old_executable = sys.executable
    sys.path = [str(output / "venv/lib/python3.13/site-packages")]
    sys.prefix = str(output / "venv")
    sys.base_prefix = str(output / "runtime")
    sys.executable = str(output / "venv/bin/python3")
    sys.modules.pop("tobkiri_sealed.bootstrap", None)
    sys.modules.pop("tobkiri_sealed", None)
    monkeypatch.setenv(
        "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256",
        BUILDER._sha256_file(output / BUILDER.MANIFEST_FILENAME),
    )
    try:
        sys.path.insert(0, str(source_root))
        import tobkiri_sealed.bootstrap as bootstrap

        with pytest.raises(SystemExit):
            bootstrap.main(
                [
                    "--role",
                    "typed",
                    "--nonce",
                    nonce,
                    "--attestation",
                    str(attestation),
                    "--manifest",
                    str(output / BUILDER.MANIFEST_FILENAME),
                    "--environment-root",
                    str(output),
                    "--unknown-parent-option",
                    "--",
                ]
            )
    finally:
        sys.path = old_path
        sys.prefix = old_prefix
        sys.base_prefix = old_base_prefix
        sys.executable = old_executable
        sys.modules.pop("tobkiri_sealed.bootstrap", None)
        sys.modules.pop("tobkiri_sealed", None)


@pytest.mark.parametrize("case", ("tampered", "missing", "wrong-target", "extra"))
def test_validator_rejects_tamper_missing_wrong_target_and_extra(
    tmp_path: Path,
    case: str,
) -> None:
    """The validator fails closed for the core integrity failure classes."""
    output = _fixture_sources(tmp_path, "x86_64-unknown-linux-gnu")[2]
    if case == "tampered":
        _make_test_mutable(output / "app/kernel_entry.py")
        (output / "app/kernel_entry.py").write_bytes(b"tampered\n")
        target = "x86_64-unknown-linux-gnu"
    elif case == "missing":
        _make_test_mutable(output / "app")
        (output / "app/defaultspack_entry.py").unlink()
        target = "x86_64-unknown-linux-gnu"
    elif case == "wrong-target":
        target = "x86_64-pc-windows-msvc"
    else:
        _make_test_mutable(output)
        (output / "unlisted.bin").write_bytes(b"extra\n")
        target = "x86_64-unknown-linux-gnu"

    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER.validate_environment(output, target, run_native_smoke=False)


def test_validator_rejects_links_hardlinks_and_manifest_path_escape(tmp_path: Path) -> None:
    """A sealed tree cannot smuggle links or traversal through the inventory."""
    linked = _fixture_sources(tmp_path / "linked", "x86_64-unknown-linux-gnu")[2]
    _make_test_mutable(linked)
    (linked / "extra-link").symlink_to(linked / "lease.v1")
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER.validate_environment(linked, "x86_64-unknown-linux-gnu", run_native_smoke=False)

    hardlinked = _fixture_sources(tmp_path / "hardlinked", "x86_64-unknown-linux-gnu")[2]
    _make_test_mutable(hardlinked)
    os.link(hardlinked / "lease.v1", hardlinked / "hardlink")
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER.validate_environment(
            hardlinked,
            "x86_64-unknown-linux-gnu",
            run_native_smoke=False,
        )

    escaped = _fixture_sources(tmp_path / "escaped", "x86_64-unknown-linux-gnu")[2]
    manifest_path = escaped / BUILDER.MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["files"][0]["path"] = "../outside"
    _make_test_mutable(manifest_path)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BUILDER.SealedEnvironmentError):
        BUILDER.validate_environment(
            escaped,
            "x86_64-unknown-linux-gnu",
            run_native_smoke=False,
        )


def test_bootstrap_and_resource_wiring_match_the_fixed_contract() -> None:
    """Static checks cover the wire, raw digest, and resource boundary."""
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    builder = BUILDER_PATH.read_text(encoding="utf-8")
    preparer = (
        ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
    ).read_text(encoding="utf-8")
    build_rs = (ROOT / "tobkiri_launcher" / "src-tauri" / "build.rs").read_text(
        encoding="utf-8"
    )
    rust_protocol = (
        ROOT / "tobkiri_launcher" / "src-tauri" / "src" / "sealed_python.rs"
    ).read_text(encoding="utf-8")
    protocol_path = (
        ROOT
        / "tobkiri_launcher"
        / "src-tauri"
        / "src"
        / "sealed_python_protocol.rs"
    )
    protocol_source = protocol_path.read_text(encoding="utf-8") if protocol_path.exists() else ""
    rust_contract = rust_protocol + protocol_source
    environment_schema = json.loads(
        (
            ROOT
            / ".github"
            / "schemas"
            / "sealed-python-environment.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    attestation_schema = json.loads(
        (
            ROOT
            / ".github"
            / "schemas"
            / "sealed-python-attestation.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    tauri = json.loads(
        (ROOT / "tobkiri_launcher" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )

    assert "lease.v1" in bootstrap
    assert "LOCK_SH" in bootstrap and "LK_RLCK" in bootstrap
    assert 'values.index("--")' in bootstrap
    assert "io.tobkiri.sealed-python-launch.v1" in bootstrap
    assert "os.replace" in bootstrap
    assert "fsync" in bootstrap and "chmod" in bootstrap
    assert all(
        f'"{role}"' in bootstrap
        for role in ("typed", "defaultspack", "host_helper")
    )
    assert "sha256:" not in bootstrap
    assert "sha256:" not in builder
    assert "sha256:" not in json.dumps(environment_schema)
    for field in (
        "schema",
        "nonce",
        "role",
        "environment_digest",
        "executable",
        "prefix",
        "base_prefix",
        "sys_path",
        "stdlib_sha256",
        "site_packages_sha256",
        "native_sha256",
        "lifetime_lease",
    ):
        assert f'"{field}"' in bootstrap
    for marker in (
        '"-I"',
        '"-B"',
        '"tobkiri_sealed.bootstrap"',
        "_hashlib",
        "_ssl",
        "cryptography",
        '"typed"',
        '"defaultspack"',
        '"host_helper"',
    ):
        assert marker in builder
    assert "--health" not in (
        ROOT
        / ".github"
        / "scripts"
        / "sealed_python_sources"
        / "app"
        / "defaultspack_entry.py"
    ).read_text(encoding="utf-8")
    assert "--headless" not in (
        ROOT
        / ".github"
        / "scripts"
        / "sealed_python_sources"
        / "app"
        / "host_helper_entry.py"
    ).read_text(encoding="utf-8")
    assert "python-runtime" in preparer
    assert "sealed-environment.v1.json" in preparer
    assert "python-runtime" in build_rs
    assert "bind_sealed_python_environment" in build_rs
    assert "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256" in build_rs
    assert environment_schema["$id"] == BUILDER.MANIFEST_SCHEMA
    assert environment_schema["$defs"]["sha256"]["pattern"] == "^[0-9a-f]{64}$"
    assert attestation_schema["properties"]["nonce"]["pattern"] == "^[0-9a-f]{64}$"
    assert attestation_schema["properties"]["role"]["enum"] == [
        "typed",
        "defaultspack",
        "host_helper",
    ]
    for marker in (
        '"--nonce"',
        '"--attestation"',
        '"--manifest"',
        '"--environment-root"',
        '"--"',
        '"venv/bin/python3"',
        '"app/kernel_entry.py"',
        '"app/defaultspack_entry.py"',
        '"app/host_helper_entry.py"',
    ):
        assert marker in rust_contract
    if protocol_source:
        for marker in ('"typed"', '"defaultspack"', '"host_helper"'):
            assert marker in protocol_source
    assert tauri["bundle"]["resources"] == {"./gen/app": "app"}


def test_raw_manifest_digest_matches_compact_cross_language_contract() -> None:
    """The Python digest is raw SHA-256 over compact manifest JSON bytes."""
    records = [
        {
            "path": "a.txt",
            "size": 1,
            "sha256": "a" * 64,
            "executable": False,
        }
    ]
    compact = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()
    digest = BUILDER._files_digest(records)
    assert digest == hashlib.sha256(compact).hexdigest()
    assert not digest.startswith("sha256:")


def test_all_tauri_build_callsites_are_mac_release_gated() -> None:
    """No workflow or local production caller can publish Windows/Linux builds."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    ).decode("utf-8").split("\0")
    needle = "cargo tauri " + "build"
    all_hits = []
    callsites = []
    for relative in tracked:
        if not relative:
            continue
        try:
            text = (ROOT / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if needle in text:
            all_hits.append(relative)
        if Path(relative).suffix not in {".sh", ".yml", ".yaml"}:
            continue
        if needle in text:
            callsites.append(relative)
    assert set(all_hits) == {
        ".github/workflows/desktop-installers.yml",
        ".github/workflows/release.yml",
        "scripts/build-and-sign.sh",
        "tobkiri_runtime/docs/ci_build_guide.md",
        "tobkiri_runtime/docs/quality_pack/claude_desktop_quality_pack.md",
        "tobkiri_runtime/tests/test_claude_quality_pack_contract.py",
        "tobkiri_runtime/tests/test_viewer_build_contract.py",
    }
    assert set(callsites) == {
        ".github/workflows/desktop-installers.yml",
        ".github/workflows/release.yml",
        "scripts/build-and-sign.sh",
    }

    desktop = (ROOT / ".github/workflows/desktop-installers.yml").read_text(
        encoding="utf-8"
    )
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    release_build = release.split("\n  gather:", 1)[0]
    assert "release workflow is currently macOS-only" in release
    for workflow in (desktop, release_build):
        assert "windows-latest" not in workflow
        assert "x86_64-pc-windows-msvc" not in workflow
        assert "x86_64-unknown-linux-gnu" not in workflow
        assert "if: runner.os != 'macOS'" not in workflow
        assert "--features" not in workflow
        for line in workflow.splitlines():
            if needle in line:
                assert "${{ matrix.target }}" in line

    helper = (ROOT / "scripts/build-and-sign.sh").read_text(encoding="utf-8")
    guard = 'if [[ "$mode" == "production" && "$presentation_platform" != "macos" ]]'
    assert guard in helper
    assert helper.index(guard) < helper.index(needle)
