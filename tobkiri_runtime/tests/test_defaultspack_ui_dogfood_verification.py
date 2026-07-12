from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "quality" / "verify_recursive_ui_dogfood_build.py"
WEBAPP_NODE_MODULES = ROOT / "ecosystem" / "defaultspack" / "webapp" / "node_modules"


def test_recursive_ui_dogfood_verifier_rejects_missing_composition_source(tmp_path: Path) -> None:
    run_root = tmp_path / ".rumi" / "ui" / "runs" / "missing-app"
    run_root.mkdir(parents=True)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_root), "--json"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stderr)
    assert report["status"] == "failed"
    assert report["error"]["code"] == "COMPOSITION_APP_MISSING"


@pytest.mark.skipif(
    not WEBAPP_NODE_MODULES.is_dir(),
    reason="defaultspack webapp node_modules are required for the real Vite dogfood build",
)
def test_recursive_ui_dogfood_verifier_runs_real_vite_build(tmp_path: Path) -> None:
    run_root = _write_valid_run(tmp_path / ".rumi" / "ui" / "runs" / "dogfood-valid")
    keep_dir = tmp_path / "prepared"
    keep_dir.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(run_root),
            "--work-dir",
            str(keep_dir),
            "--keep-temp",
            "--json",
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(completed.stdout)
    project_dir = Path(report["projectDir"])
    assert report["status"] == "passed"
    assert report["command"]["command"] == "npm run build"
    assert report["copied"]["compositionFiles"] == ["App.tsx", "generated-index.ts"]
    assert report["copied"]["acceptedBundles"][0]["nodeId"] == "reply-composer"
    assert (project_dir / "dist" / "index.html").is_file()


def _write_valid_run(run_root: Path) -> Path:
    composition_source = run_root / "composition" / "source"
    accepted_source = run_root / "accepted" / "reply-composer" / "source"
    foundation = run_root / "foundation" / "accepted"
    composition_source.mkdir(parents=True)
    accepted_source.mkdir(parents=True)
    foundation.mkdir(parents=True)

    (composition_source / "generated-index.ts").write_text(
        "\n".join(
            [
                "import ReplyComposer from '../../accepted/reply-composer/source/Component';",
                "",
                "export const rumiComponents = {",
                "  'reply-composer': ReplyComposer,",
                "};",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (composition_source / "App.tsx").write_text(
        "\n".join(
            [
                "import { rumiComponents } from './generated-index';",
                "",
                "const ReplyComposer = rumiComponents['reply-composer'];",
                "",
                "export default function App() {",
                "  return (",
                "    <main data-rumi-composition=\"recursive-ui\">",
                "      <ReplyComposer title=\"Dogfood evidence\" />",
                "    </main>",
                "  );",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (accepted_source / "Component.tsx").write_text(
        "\n".join(
            [
                "import type { ReactNode } from 'react';",
                "import styles from './Component.module.css';",
                "",
                "type Props = {",
                "  title?: string;",
                "  children?: ReactNode;",
                "};",
                "",
                "export default function Component({ title = 'Ready', children }: Props) {",
                "  return (",
                "    <section className={styles.root}>",
                "      <h2>{title}</h2>",
                "      <button className={styles.button}>Action</button>",
                "      {children}",
                "    </section>",
                "  );",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (accepted_source / "Component.module.css").write_text(
        "\n".join(
            [
                ".root {",
                "  background: var(--rui-surface);",
                "  color: var(--rui-text-primary);",
                "  padding: var(--rui-space-4);",
                "}",
                "",
                ".button {",
                "  background: var(--rui-action-primary);",
                "  color: var(--rui-surface);",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (foundation / "tokens.css").write_text(
        "\n".join(
            [
                ":root {",
                "  --rui-surface: #ffffff;",
                "  --rui-text-primary: #111827;",
                "  --rui-space-4: 16px;",
                "  --rui-action-primary: #2563eb;",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (run_root / "accepted" / "reply-composer" / "runtime.accepted.json").write_text(
        json.dumps(
            {
                "nodeId": "reply-composer",
                "candidateId": "candidate-1",
                "sourceFiles": ["source/Component.tsx", "source/Component.module.css"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_root
