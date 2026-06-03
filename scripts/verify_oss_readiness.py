#!/usr/bin/env python3
"""Verify local OSS program readiness materials.

This script intentionally avoids network calls. It checks whether the repository
has the public-facing docs and release safeguards needed before maintainers ask
real users for feedback or submit OSS support-program applications.
"""

from __future__ import annotations

import json
import re
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


def paragraph_after(text: str, label: str) -> str:
    start = text.index(label) + len(label)
    return text[start:].strip().split("\n\n", 1)[0].strip()


def main() -> int:
    required_files = [
        "README.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        ".github/SUPPORT.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        "docs/first-run-check.md",
        "docs/community-launch-plan.md",
        "docs/adoption-evidence.md",
        "docs/demo-script.md",
        "docs/oss-program-readiness.md",
        "docs/releases/v0.2.0.md",
    ]

    results: list[dict[str, Any]] = []
    for rel_path in required_files:
        path = ROOT / rel_path
        results.append(
            check(path.is_file() and bool(path.read_text(encoding="utf-8").strip()), rel_path)
        )

    readme = read("README.md")
    release_workflow = read(".github/workflows/release.yml")
    first_run = read("docs/first-run-check.md")
    launch = read("docs/community-launch-plan.md")
    evidence = read("docs/adoption-evidence.md")
    demo = read("docs/demo-script.md")
    readiness = read("docs/oss-program-readiness.md")

    results.extend(
        [
            check("docs/first-run-check.md" in readme, "README links first-run guide"),
            check("docs/adoption-evidence.md" in readme, "README links adoption evidence"),
            check("draft: true" in release_workflow, "release workflow creates draft releases"),
            check(
                "python -m rumi_ai --health" in first_run and "just health" in first_run,
                "first-run guide documents health check",
            ),
            check("adoption-evidence.md" in launch, "launch plan links evidence tracker"),
            check("demo-script.md" in launch, "launch plan links demo script"),
            check("Do not count:" in evidence, "evidence tracker has anti-inflation rules"),
            check("python -m rumi_ai --health" in demo, "demo script uses health check"),
            check(
                "python scripts/verify_oss_readiness.py" in demo,
                "demo script uses readiness verifier",
            ),
            check(
                re.search(r"buy|bought|star-for-star|fake", evidence, re.IGNORECASE)
                is not None,
                "evidence tracker names invalid metrics",
            ),
        ]
    )

    for label in [
        "Why this repository should qualify (500 chars max):",
        "API credit use (500 chars max):",
        "Additional note (500 chars max):",
    ]:
        value = paragraph_after(readiness, label)
        results.append(
            check(
                len(value) <= 500,
                f"OpenAI draft under 500 chars: {label}",
                f"{len(value)} chars",
            )
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
