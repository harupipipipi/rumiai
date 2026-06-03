#!/usr/bin/env python3
"""Verify local OSS release-readiness materials.

This script intentionally avoids network calls. It checks whether the repository
has the public-facing docs, packaging checks, and release safeguards needed
before maintainers publish release artifacts or invite setup feedback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check(condition: bool, name: str, details: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if condition else "fail",
        "details": details,
    }


def main() -> int:
    required_files = [
        "pyproject.toml",
        "README.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        ".github/SUPPORT.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/setup_feedback.yml",
        "docs/first-run-check.md",
        "docs/release-checklist.md",
        "docs/user-feedback-evidence.md",
        "docs/demo-script.md",
        "docs/release-readiness.md",
        "docs/releases/v0.2.0.md",
        "scripts/check_package_install.py",
    ]

    results: list[dict[str, Any]] = []
    for rel_path in required_files:
        path = ROOT / rel_path
        results.append(
            check(path.is_file() and bool(path.read_text(encoding="utf-8").strip()), rel_path)
        )

    root_pyproject = read("pyproject.toml")
    readme = read("README.md")
    contributing = read("CONTRIBUTING.md")
    release_workflow = read(".github/workflows/release.yml")
    test_workflow = read(".github/workflows/test.yml")
    first_run = read("docs/first-run-check.md")
    justfile = read("justfile")
    release_checklist = read("docs/release-checklist.md")
    evidence = read("docs/user-feedback-evidence.md")
    demo = read("docs/demo-script.md")
    readiness = read("docs/release-readiness.md")
    package_smoke = read("scripts/check_package_install.py")
    setup_template = read(".github/ISSUE_TEMPLATE/setup_feedback.yml")

    results.extend(
        [
            check("docs/first-run-check.md" in readme, "README links first-run guide"),
            check(
                "docs/user-feedback-evidence.md" in readme,
                "README links feedback evidence",
            ),
            check(
                "docs/release-checklist.md" in readme,
                "README links release checklist",
            ),
            check('name = "rumi-ai"' in root_pyproject, "root pyproject names package"),
            check(
                '"rumi_ai*"' in root_pyproject and '"rumi_ai_1_10*"' in root_pyproject,
                "root pyproject includes stable and runtime packages",
            ),
            check(
                'rumi-ai = "rumi_ai.cli:main"' in root_pyproject,
                "root pyproject exposes rumi-ai console script",
            ),
            check(
                'pip install -e "."' not in readme and 'pip install -e ".[dev]"' in readme,
                "README documents root editable install",
            ),
            check(
                'pip install -e ".[dev]"' in contributing,
                "CONTRIBUTING documents root editable install",
            ),
            check(
                "cd \"$RUNNER_TEMP\"" in test_workflow
                and "python -m rumi_ai --health" in test_workflow,
                "CI checks installed entrypoint outside repository",
            ),
            check(
                "rumi-ai --health" in test_workflow,
                "CI checks console script outside repository",
            ),
            check(
                "python scripts/check_package_install.py" in first_run
                and "just package-smoke" in first_run,
                "first-run guide documents package smoke check",
            ),
            check(
                "package-smoke:" in justfile
                and "python scripts/check_package_install.py" in justfile,
                "justfile exposes package smoke check",
            ),
            check(
                "\"pip\", \"wheel\"" in package_smoke
                and "rumi-ai" in package_smoke
                and "outside-checkout" in package_smoke,
                "package smoke builds wheel and checks public entrypoints outside checkout",
            ),
            check("draft: true" in release_workflow, "release workflow creates draft releases"),
            check(
                "python -m rumi_ai --health" in first_run
                and "rumi-ai --health" in first_run
                and "just health" in first_run
                and "pip install -e ." in first_run,
                "first-run guide documents health check",
            ),
            check(
                "user-feedback-evidence.md" in release_checklist,
                "release checklist links evidence tracker",
            ),
            check(
                "releases/v0.2.0.md" in release_checklist,
                "release checklist links release notes",
            ),
            check(
                "setup_feedback.yml" in release_checklist and "setup_feedback.yml" in evidence,
                "release and evidence docs link setup feedback template",
            ),
            check("Release Readiness" in readiness, "release readiness note is present"),
            check(
                "qualify" not in readiness.lower()
                and "credit use" not in readiness.lower()
                and "draft under" not in readiness.lower(),
                "release readiness note avoids request-specific framing",
            ),
            check("Do not count:" in evidence, "evidence tracker has anti-inflation rules"),
            check("python -m rumi_ai --health" in demo, "demo script uses health check"),
            check(
                "python scripts/verify_oss_readiness.py" in demo,
                "demo script uses readiness verifier",
            ),
            check(
                "python scripts/check_package_install.py" in demo,
                "demo script uses package smoke verifier",
            ),
            check(
                "python -m rumi_ai --health" in setup_template,
                "setup feedback template asks for health check",
            ),
            check(
                "remove secrets" in setup_template.lower(),
                "setup feedback template asks users to remove secrets",
            ),
            check("Bought stars" in evidence, "evidence tracker names invalid metrics"),
        ]
    )

    failed = [item for item in results if item["status"] != "pass"]
    payload = {
        "status": "pass" if not failed else "fail",
        "checks": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
