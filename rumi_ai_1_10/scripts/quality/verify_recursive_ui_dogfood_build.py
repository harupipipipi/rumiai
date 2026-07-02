#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


RUMI_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEBAPP_ROOT = RUMI_ROOT / "ecosystem" / "defaultspack" / "webapp"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy a .rumi/ui recursive dogfood run into a minimal Vite/TS project "
            "and verify it with npm run build."
        )
    )
    parser.add_argument("run_root", help="Path to .rumi/ui/runs/{runId}")
    parser.add_argument(
        "--webapp-root",
        default=str(DEFAULT_WEBAPP_ROOT),
        help="defaultspack webapp root whose existing node_modules should be reused",
    )
    parser.add_argument("--work-dir", help="Directory to create the temporary Vite project under")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the generated Vite project")
    parser.add_argument("--timeout", type=int, default=120, help="npm run build timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    args = parser.parse_args(argv)

    run_root = Path(args.run_root).expanduser().resolve()
    webapp_root = Path(args.webapp_root).expanduser().resolve()
    temp_parent = Path(args.work_dir).expanduser().resolve() if args.work_dir else None
    project_root: Path | None = None

    try:
        project_root = Path(
            tempfile.mkdtemp(prefix="rumi-ui-dogfood-build-", dir=str(temp_parent) if temp_parent else None)
        ).resolve()
        copied = prepare_project(run_root=run_root, project_root=project_root, webapp_root=webapp_root)
        command = run_build(project_root, timeout=args.timeout)
        passed = command["status"] == "passed"
        report = {
            "status": "passed" if passed else "failed",
            "runRoot": str(run_root),
            "projectDir": str(project_root),
            "copied": copied,
            "command": command,
        }
        _emit_report(report, as_json=args.json)
        return 0 if passed else 1
    except VerificationError as exc:
        report = {
            "status": "failed",
            "runRoot": str(run_root),
            "projectDir": str(project_root) if project_root else None,
            "error": {"message": str(exc), "code": exc.code},
        }
        _emit_report(report, as_json=args.json, stderr=True)
        return exc.exit_code
    finally:
        if project_root and project_root.exists() and not args.keep_temp:
            shutil.rmtree(project_root, ignore_errors=True)


def prepare_project(*, run_root: Path, project_root: Path, webapp_root: Path) -> dict[str, Any]:
    if not run_root.is_dir():
        raise VerificationError(f"run root does not exist: {run_root}", code="RUN_ROOT_MISSING")

    composition_source = run_root / "composition" / "source"
    app_source = composition_source / "App.tsx"
    if not app_source.is_file():
        raise VerificationError(
            f"composition/source/App.tsx is missing under {run_root}",
            code="COMPOSITION_APP_MISSING",
        )

    accepted_root = run_root / "accepted"
    accepted_sources = _accepted_source_dirs(accepted_root)
    if not accepted_sources:
        raise VerificationError(
            f"no accepted bundle source directories found under {accepted_root}",
            code="ACCEPTED_SOURCE_MISSING",
        )

    src_root = project_root / "src"
    _copy_tree(composition_source, src_root / "composition" / "source")
    copied_accepted: list[dict[str, str]] = []
    for node_id, source_dir in accepted_sources:
        destination = src_root / "accepted" / node_id / "source"
        _copy_tree(source_dir, destination)
        copied_accepted.append(
            {
                "nodeId": node_id,
                "source": str(source_dir),
                "destination": str(destination.relative_to(project_root)),
            }
        )

    tokens_css = run_root / "foundation" / "accepted" / "tokens.css"
    if tokens_css.is_file():
        shutil.copy2(tokens_css, src_root / "tokens.css")
        token_source: str | None = str(tokens_css)
    else:
        (src_root / "tokens.css").write_text(":root {}\n", encoding="utf-8")
        token_source = None

    _write_minimal_project_files(project_root)
    node_modules = _require_node_modules(webapp_root)
    _link_node_modules(project_root, node_modules)
    return {
        "compositionSource": str(composition_source),
        "compositionFiles": _relative_files(src_root / "composition" / "source"),
        "acceptedBundles": copied_accepted,
        "tokensCss": token_source,
    }


def run_build(project_root: Path, *, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(project_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": "npm run build",
            "status": "failed",
            "exitCode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": "npm run build",
        "status": "passed" if completed.returncode == 0 else "failed",
        "exitCode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


def _accepted_source_dirs(accepted_root: Path) -> list[tuple[str, Path]]:
    if not accepted_root.is_dir():
        return []
    source_dirs: list[tuple[str, Path]] = []
    for child in sorted(accepted_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        source_dir = child / "source"
        if source_dir.is_dir() and any(source_dir.rglob("*")):
            source_dirs.append((child.name, source_dir))
    return source_dirs


def _write_minimal_project_files(project_root: Path) -> None:
    (project_root / "package.json").write_text(
        json.dumps(
            {
                "name": "rumi-ui-dogfood-build",
                "private": True,
                "type": "module",
                "scripts": {"build": "tsc --noEmit && vite build"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "index.html").write_text(
        "\n".join(
            [
                '<!doctype html>',
                '<html lang="en">',
                "  <head>",
                '    <meta charset="UTF-8" />',
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
                "    <title>Rumi UI dogfood build</title>",
                "  </head>",
                "  <body>",
                '    <div id="root"></div>',
                '    <script type="module" src="/src/main.tsx"></script>',
                "  </body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2020",
                    "useDefineForClassFields": True,
                    "lib": ["ES2020", "DOM", "DOM.Iterable"],
                    "allowJs": False,
                    "skipLibCheck": True,
                    "esModuleInterop": True,
                    "allowSyntheticDefaultImports": True,
                    "strict": True,
                    "forceConsistentCasingInFileNames": True,
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "noEmit": True,
                    "jsx": "react-jsx",
                },
                "include": ["src"],
                "references": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "vite.config.ts").write_text(
        "\n".join(
            [
                'import { defineConfig } from "vite";',
                "",
                "export default defineConfig({",
                "  build: {",
                '    outDir: "dist",',
                "    emptyOutDir: true,",
                "  },",
                "});",
                "",
            ]
        ),
        encoding="utf-8",
    )
    src_root = project_root / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    (src_root / "main.tsx").write_text(
        "\n".join(
            [
                'import { StrictMode } from "react";',
                'import { createRoot } from "react-dom/client";',
                'import "./tokens.css";',
                'import App from "./composition/source/App";',
                "",
                'const root = document.getElementById("root");',
                "if (!root) {",
                '  throw new Error("root element missing");',
                "}",
                "",
                "createRoot(root).render(",
                "  <StrictMode>",
                "    <App />",
                "  </StrictMode>",
                ");",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (src_root / "vite-env.d.ts").write_text('/// <reference types="vite/client" />\n', encoding="utf-8")


def _require_node_modules(webapp_root: Path) -> Path:
    node_modules = webapp_root / "node_modules"
    if not node_modules.is_dir():
        raise VerificationError(
            f"defaultspack webapp node_modules missing: {node_modules}. Run npm install in {webapp_root}.",
            code="NODE_MODULES_MISSING",
            exit_code=2,
        )
    return node_modules


def _link_node_modules(project_root: Path, node_modules: Path) -> None:
    target = project_root / "node_modules"
    try:
        target.symlink_to(node_modules, target_is_directory=True)
    except OSError:
        shutil.copytree(node_modules, target, symlinks=True)


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _relative_files(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def _emit_report(report: dict[str, Any], *, as_json: bool, stderr: bool = False) -> None:
    stream = sys.stderr if stderr else sys.stdout
    if as_json:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return
    if report["status"] == "passed":
        stream.write(f"PASS recursive UI dogfood build: {report['projectDir']}\n")
    else:
        error = report.get("error") or {}
        stream.write(f"FAIL recursive UI dogfood build: {error.get('message') or report.get('projectDir')}\n")
    command = report.get("command")
    if isinstance(command, dict):
        stream.write(f"{command['command']}: {command['status']} (exit {command['exitCode']})\n")
        if command.get("stdout"):
            stream.write(command["stdout"])
            if not command["stdout"].endswith("\n"):
                stream.write("\n")
        if command.get("stderr"):
            stream.write(command["stderr"])
            if not command["stderr"].endswith("\n"):
                stream.write("\n")


class VerificationError(Exception):
    def __init__(self, message: str, *, code: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


if __name__ == "__main__":
    raise SystemExit(main())
