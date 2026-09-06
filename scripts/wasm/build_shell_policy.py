"""Build an import-free Shell Policy component from its canonical Python source.

This produces a migration artifact, not an enabled production backend. No Pack
manifest or active Profile is changed by this command.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


TOOLS = {"componentize-py": "0.25.0", "wasmtime": "48.0.0"}
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tobkiri_runtime/ecosystem/rumi_shell_policy_pack/runtime/policy.py"


def build(output: Path) -> dict[str, object]:
    """Build and verify component bytes with pinned, preinstalled tools."""
    from wasmtime import Config, Engine
    from wasmtime.component import Component

    for tool, expected in TOOLS.items():
        if version(tool) != expected:
            raise ValueError(f"{tool} must be version {expected}")
    if output.suffix != ".wasm" or output.is_symlink():
        raise ValueError("output must be a regular .wasm artifact")
    compiler = Path(sys.executable).parent / "componentize-py"
    if not compiler.is_file():
        raise ValueError("componentize-py must be installed beside this Python")
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    directory = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="tobkiri-wasm-build-") as temporary:
        stage = Path(temporary)
        shutil.copyfile(SOURCE, stage / "policy.py")
        shutil.copyfile(directory / "pack.wit", stage / "pack.wit")
        shutil.copyfile(directory / "shell_policy_component.py", stage / "app.py")
        # No user credentials, HOME, or environment variables enter preinit.
        environment = {
            "PATH": os.pathsep.join((str(compiler.parent), os.defpath)),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
        command = [str(compiler), "-d", "pack.wit", "-w", "pack"]
        for arguments in (
            ["bindings", "."],
            ["componentize", "--stub-wasi", "app", "-o", "policy.wasm"],
        ):
            subprocess.run(
                [*command, *arguments],
                cwd=stage,
                env=environment,
                check=True,
                timeout=180,
            )
        config = Config()
        config.parallel_compilation = False
        engine = Engine(config)
        component = Component.from_file(engine, str(stage / "policy.wasm"))
        if component.type.imports(engine):
            raise ValueError("Shell Policy component must not import Host capabilities")
        binary = (stage / "policy.wasm").read_bytes()
        provenance: dict[str, object] = {
            "schema": "io.tobkiri.wasm-build-evidence.v1",
            "source_sha256": hashlib.sha256(
                (stage / "policy.py").read_bytes()
            ).hexdigest(),
            "wit_sha256": hashlib.sha256((stage / "pack.wit").read_bytes()).hexdigest(),
            "adapter_sha256": hashlib.sha256(
                (stage / "app.py").read_bytes()
            ).hexdigest(),
            "artifact_sha256": hashlib.sha256(binary).hexdigest(),
            "artifact_bytes": len(binary),
            "tools": TOOLS,
            "imports": [],
            "production_enabled": False,
        }
        output.write_bytes(binary)
        output.with_suffix(".build.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return provenance


def main() -> None:
    """Build one explicit output without modifying runtime selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), sort_keys=True))


if __name__ == "__main__":
    main()
