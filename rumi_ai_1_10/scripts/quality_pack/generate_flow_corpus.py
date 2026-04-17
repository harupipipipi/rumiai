#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml


PHASE_PATTERNS = [
    ["init", "prepare", "execute", "finalize"],
    ["init", "main", "cleanup"],
    ["bootstrap", "load", "run", "finish"],
    ["start", "middle", "end"],
]

STEP_TYPES = [
    "action",
    "action",
    "action",
    "python_file_call",
    "action",
]


def _phase_for_step(phases: list[str], step_index: int, step_count: int) -> str:
    chunk = max(1, step_count // len(phases))
    phase_idx = min(len(phases) - 1, step_index // chunk)
    return phases[phase_idx]


def _build_valid_steps(case_id: int, phases: list[str], step_count: int) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for step_index in range(step_count):
        step_id = f"step_{case_id:05d}_{step_index:02d}"
        phase = _phase_for_step(phases, step_index, step_count)
        step_type = STEP_TYPES[(case_id + step_index) % len(STEP_TYPES)]

        step: dict[str, Any] = {
            "id": step_id,
            "phase": phase,
            "type": step_type,
            "priority": 50 + ((step_index * 7 + case_id) % 80),
            "input": {
                "case": case_id,
                "step": step_index,
                "phase": phase,
                "payload": {
                    "feature_flag": f"flag_{(case_id + step_index) % 17}",
                    "retry": (step_index % 3) + 1,
                    "timeout_ms": 1000 + ((case_id + step_index) % 20) * 100,
                },
            },
            "output": f"out_{step_id}",
            "when": "true" if (step_index + case_id) % 5 else "context.user.enabled",
        }

        if step_index > 0:
            depends_on = [steps[step_index - 1]["id"]]
            if step_index > 3 and step_index % 4 == 0:
                depends_on.append(steps[step_index - 3]["id"])
            step["depends_on"] = depends_on

        if step_type == "python_file_call":
            step["owner_pack"] = "defaults"
            step["file"] = "workers/default_worker.py"
            step["timeout_seconds"] = 30.0 + (step_index % 5) * 5.0
            step["principal_id"] = f"principal_{case_id:05d}"

        steps.append(step)
    return steps


def _build_valid_flow(case_id: int) -> dict[str, Any]:
    phases = PHASE_PATTERNS[case_id % len(PHASE_PATTERNS)]
    step_count = 18 + (case_id % 8)
    flow = {
        "flow_id": f"corpus.valid.{case_id:05d}",
        "inputs": {
            "user_id": "string",
            "request_id": "string",
            "session_id": "string",
        },
        "outputs": {
            "status": "string",
            "result": "object",
            "metrics": "object",
        },
        "phases": phases,
        "defaults": {
            "fail_soft": True,
            "on_missing_step": "skip",
            "max_retries": 3,
            "batch_window_ms": 250,
        },
        "schedule": {
            "enabled": case_id % 2 == 0,
            "interval_seconds": 300 + (case_id % 60),
        },
        "steps": _build_valid_steps(case_id, phases, step_count),
    }
    return flow


def _build_invalid_flow(case_id: int, category: int) -> dict[str, Any]:
    base = _build_valid_flow(case_id)
    base["flow_id"] = f"corpus.invalid.{case_id:05d}"
    if category == 0:
        base.pop("flow_id", None)
    elif category == 1:
        base["phases"] = []
    elif category == 2:
        phases = list(base["phases"])
        phases[0] = 100
        base["phases"] = phases
    elif category == 3:
        base["steps"] = {"not": "an-array"}
    elif category == 4:
        base["steps"][0].pop("id", None)
    elif category == 5:
        base["steps"][1]["id"] = base["steps"][0]["id"]
    elif category == 6:
        base["steps"][0]["phase"] = "nonexistent_phase"
    elif category == 7:
        base["steps"][0]["type"] = "python_file_call"
        base["steps"][0].pop("file", None)
    elif category == 8:
        base["inputs"] = ["wrong", "type"]
    else:
        base["outputs"] = ["wrong", "type"]
    return base


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        ),
        encoding="utf-8",
    )


def generate_corpus(root_dir: Path, valid_count: int, invalid_count: int) -> None:
    corpus_dir = root_dir / "tests" / "flow_corpus"
    valid_dir = corpus_dir / "valid"
    invalid_dir = corpus_dir / "invalid"
    manifest_path = corpus_dir / "manifest.json"

    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    records: dict[str, list[dict[str, Any]]] = {"valid": [], "invalid": []}

    for index in range(valid_count):
        flow = _build_valid_flow(index)
        flow_path = valid_dir / f"valid_{index:05d}.flow.yaml"
        _write_yaml(flow_path, flow)
        records["valid"].append({"file": str(flow_path.relative_to(root_dir))})

    for index in range(invalid_count):
        category = index % 10
        flow = _build_invalid_flow(index + valid_count, category)
        flow_path = invalid_dir / f"invalid_{index:05d}.flow.yaml"
        _write_yaml(flow_path, flow)
        records["invalid"].append(
            {
                "file": str(flow_path.relative_to(root_dir)),
                "category": category,
            }
        )

    manifest_path.write_text(
        json.dumps(
            {
                "valid_count": valid_count,
                "invalid_count": invalid_count,
                "valid": records["valid"],
                "invalid": records["invalid"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate flow corpus for loader regression testing."
    )
    parser.add_argument("--valid-count", type=int, default=1300)
    parser.add_argument("--invalid-count", type=int, default=1000)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    generate_corpus(repo_root, args.valid_count, args.invalid_count)


if __name__ == "__main__":
    main()
