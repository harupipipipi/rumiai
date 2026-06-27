from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.ui_compiler import (
    UICompilerArtifactStore,
    UICompilerConfig,
    UIPlan,
)
from domain.ui_compiler.models import DEFAULT_SCENARIOS, DEFAULT_TEXT_SCALES, DEFAULT_VIEWPORTS
from domain.ui_compiler.planner import RecursiveUIPlanner

from .agent_backend import UIAgentBackend
from .candidate_generator import CandidateGenerator
from .candidate_selector import CandidateSelector
from .composer import PageComposer
from .compression_inspector import CompressionInspector
from .fake_agent_backend import FakeUIAgentBackend
from .foundation_generator import FoundationGenerator
from .render_matrix import RenderMatrixRunner
from .subagent_backend import SubagentToolBackend
from .verifier import ProjectVerifier


class RecursiveUIBuildOrchestrator:
    def __init__(
        self,
        *,
        agent_backend: UIAgentBackend | None = None,
        verifier: ProjectVerifier | None = None,
    ) -> None:
        self.agent_backend = agent_backend or SubagentToolBackend()
        self.verifier = verifier or ProjectVerifier()

    def run(
        self,
        arguments: dict[str, Any] | None,
        *,
        workspace_root: str | Path | None,
        authorized: bool,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not authorized:
            return _error(
                "recursive UI build requires a verified internal tool approval context",
                "APPROVAL_REQUIRED",
                data={"approval_required": True},
            )
        if workspace_root is None:
            return _error("trusted workspace is required", "WORKSPACE_REQUIRED")
        data = arguments if isinstance(arguments, dict) else {}
        unsupported = sorted(str(key) for key in data if str(key) not in _ALLOWED_KEYS)
        if unsupported:
            return _error(f"unsupported request keys: {', '.join(unsupported)}", "INVALID_REQUEST")
        root_payload = data.get("ui_tree") or data.get("uiTree") or data.get("root") or data.get("page")
        if not isinstance(root_payload, dict):
            return _error("ui_tree object is required", "INVALID_UI_TREE")

        try:
            workspace = Path(workspace_root).expanduser().resolve()
            config = UICompilerConfig.from_dict(data.get("config") or {})
            options = _options(data.get("options"))
            run_id = _run_id(data)
            plan = RecursiveUIPlanner(config).plan(root_payload, run_id=run_id)
            if not plan.is_executable():
                return _error(
                    "UI plan is not executable",
                    "PLAN_NOT_EXECUTABLE",
                    data={"diagnostics": [item.to_dict() for item in plan.diagnostics], "partialPlan": plan.to_dict()},
                )
            store = UICompilerArtifactStore(workspace / ".rumi" / "ui")
            artifacts = store.save_plan(plan, idempotency_key=_idempotency(data))
            store.ensure_run_dirs(plan.run_id)
            run_root = store.run_root(plan.run_id)
            target_workspace = _target_workspace(workspace, data.get("target"))
            foundation_generator = FoundationGenerator(backend=self.agent_backend, store=store)
            foundations = foundation_generator.generate(
                run_id=plan.run_id,
                run_root=run_root,
                count=options["foundationCandidates"],
                context=context,
            )
            accepted_foundation = foundation_generator.select(run_id=plan.run_id, candidates=foundations)
            candidate_generator = CandidateGenerator(backend=self.agent_backend, store=store)
            candidate_map = candidate_generator.generate_for_contracts(
                run_id=plan.run_id,
                run_root=run_root,
                contracts=plan.contracts(),
                foundation=accepted_foundation.spec.to_dict(),
                context=context,
                fake_failures=_fake_failures(data),
            )
            render_runner = RenderMatrixRunner(store=store)
            inspector = CompressionInspector()
            selector = CandidateSelector(store=store)
            accepted: dict[str, Any] = {}
            inspections_by_node: dict[str, dict[str, Any]] = {}
            for contract in plan.contracts():
                inspections = {}
                for bundle in candidate_map.get(contract.id, []):
                    matrix = render_runner.render_candidate(
                        run_id=plan.run_id,
                        bundle=bundle,
                        viewports=options["viewports"],
                        scenarios=options["scenarios"],
                        text_scales=options["textScales"],
                    )
                    report = inspector.inspect_candidate(
                        bundle=bundle,
                        contract=contract.to_dict(),
                        render_matrix=matrix,
                    )
                    store.save_inspection_report(
                        run_id=plan.run_id,
                        node_id=contract.id,
                        candidate_id=bundle.candidate_id,
                        report=report.to_dict(),
                    )
                    inspections[bundle.candidate_id] = report
                decision = selector.select(
                    run_id=plan.run_id,
                    node_id=contract.id,
                    candidates=candidate_map.get(contract.id, []),
                    inspections=inspections,
                    run_root=run_root,
                )
                inspections_by_node[contract.id] = {
                    candidate_id: report.to_dict()
                    for candidate_id, report in inspections.items()
                }
                if not decision.passed:
                    final = _final_report(
                        plan=plan,
                        artifacts=artifacts,
                        status="error",
                        summary=_summary(plan, foundations, candidate_map, accepted, compression_failures=1, build_status="skipped"),
                        failure={"code": "UI_RECURSIVE_BUILD_FAILED", "failedNodeId": contract.id},
                        inspections=inspections_by_node,
                    )
                    report_path = store.save_final_report(run_id=plan.run_id, report=final)
                    return _error(
                        f"No acceptable candidate for {contract.id}",
                        "UI_RECURSIVE_BUILD_FAILED",
                        data={"runId": plan.run_id, "failedNodeId": contract.id, "report": report_path},
                    )
                accepted[contract.id] = decision
            composition = PageComposer(store=store).compose(
                run_id=plan.run_id,
                run_root=run_root,
                plan=plan,
                accepted_decisions=accepted,
                target=data.get("target") if isinstance(data.get("target"), dict) else {},
            )
            page_manifest = composition.to_dict()
            page_matrix = render_runner.render_page(
                run_id=plan.run_id,
                run_root=run_root,
                manifest={
                    **page_manifest,
                    "visibleActionBudget": max(3, len(accepted) * 2),
                    "visibleActionCount": min(max(1, len(accepted)), max(3, len(accepted) * 2)),
                },
                viewports=options["viewports"],
                scenarios=options["scenarios"],
                text_scales=options["textScales"],
            )
            page_compression = inspector.inspect_page(render_matrix=page_matrix, accepted_count=len(accepted))
            verification = self.verifier.verify(
                workspace=target_workspace,
                render_matrix=page_matrix,
                compression_report=page_compression,
                run_build=options["runBuild"],
            )
            status = "ok" if verification.passed else "error"
            final = _final_report(
                plan=plan,
                artifacts=artifacts,
                status=status,
                summary=_summary(
                    plan,
                    foundations,
                    candidate_map,
                    accepted,
                    compression_failures=sum(
                        1
                        for reports in inspections_by_node.values()
                        for report in reports.values()
                        if report.get("status") != "pass"
                    ),
                    build_status="passed" if verification.passed else "failed",
                ),
                accepted_foundation=accepted_foundation.to_dict(),
                accepted={node_id: decision.to_dict() for node_id, decision in accepted.items()},
                composition=composition.to_dict(),
                page_compression=page_compression,
                verification=verification.to_dict(),
                inspections=inspections_by_node,
            )
            report_path = store.save_final_report(run_id=plan.run_id, report=final)
            if status != "ok":
                return _error(
                    "recursive UI build verification failed",
                    "UI_RECURSIVE_BUILD_FAILED",
                    data={"runId": plan.run_id, "report": report_path, "verification": verification.to_dict()},
                )
            return {
                "status": "ok",
                "data": {
                    "runId": plan.run_id,
                    "artifacts": artifacts,
                    "summary": final["summary"],
                    "report": report_path,
                },
                "widget": {
                    "type": "ui_build_recursive",
                    "run_id": plan.run_id,
                    "report": report_path,
                    "summary": final["summary"],
                },
            }
        except Exception as exc:
            return _error(str(exc), "UI_RECURSIVE_BUILD_FAILED")


def run_recursive_build(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return RecursiveUIBuildOrchestrator(agent_backend=SubagentToolBackend()).run(
        arguments,
        workspace_root=(context or {}).get("conversation_workspace_dir") if isinstance(context, dict) else None,
        authorized=True,
        context=context,
    )


_ALLOWED_KEYS = {
    "ui_tree",
    "uiTree",
    "root",
    "page",
    "config",
    "target",
    "run_id",
    "runId",
    "idempotency_key",
    "idempotencyKey",
    "options",
}


def backend_from_context(context: dict[str, Any] | None) -> UIAgentBackend:
    if isinstance(context, dict) and context.get("_ui_compiler_backend") == "fake":
        return FakeUIAgentBackend()
    return SubagentToolBackend()


def _options(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "foundationCandidates": _positive_int(data.get("foundationCandidates"), 3, 1, 6),
        "viewports": _int_list(data.get("viewports"), DEFAULT_VIEWPORTS, 8),
        "scenarios": _str_list(data.get("scenarios"), DEFAULT_SCENARIOS, 8),
        "textScales": _float_list(data.get("textScales"), DEFAULT_TEXT_SCALES, 6),
        "runBuild": bool(data.get("runBuild", True)),
    }


def _run_id(data: dict[str, Any]) -> str | None:
    raw = str(data.get("run_id") or data.get("runId") or "").strip()
    return raw or None


def _idempotency(data: dict[str, Any]) -> str | None:
    raw = str(data.get("idempotency_key") or data.get("idempotencyKey") or "").strip()
    return raw or None


def _fake_failures(data: dict[str, Any]) -> dict[str, str]:
    options = data.get("options") if isinstance(data.get("options"), dict) else {}
    failures = options.get("fakeFailures") if isinstance(options.get("fakeFailures"), dict) else {}
    return {str(key): str(value) for key, value in failures.items()}


def _target_workspace(workspace: Path, target: Any) -> Path:
    data = target if isinstance(target, dict) else {}
    raw = data.get("projectPath") or data.get("project_path") or data.get("packagePath") or data.get("package_path")
    if not raw:
        return workspace
    path = (workspace / str(raw)).resolve() if not Path(str(raw)).is_absolute() else Path(str(raw)).resolve()
    path.relative_to(workspace)
    return path


def _summary(
    plan: UIPlan,
    foundations: list[Any],
    candidate_map: dict[str, list[Any]],
    accepted: dict[str, Any],
    *,
    compression_failures: int,
    build_status: str,
) -> dict[str, Any]:
    return {
        "foundationCandidates": len(foundations),
        "contracts": len(plan.contracts()),
        "candidateBundles": sum(len(items) for items in candidate_map.values()),
        "acceptedBundles": len(accepted),
        "compressionFailures": compression_failures,
        "buildStatus": build_status,
    }


def _final_report(
    *,
    plan: UIPlan,
    artifacts: dict[str, Any],
    status: str,
    summary: dict[str, Any],
    accepted_foundation: dict[str, Any] | None = None,
    accepted: dict[str, Any] | None = None,
    composition: dict[str, Any] | None = None,
    page_compression: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    inspections: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "runId": plan.run_id,
        "artifacts": artifacts,
        "summary": summary,
        "planSummary": plan.to_dict()["summary"],
        "acceptedFoundation": accepted_foundation or {},
        "accepted": accepted or {},
        "composition": composition or {},
        "pageCompression": page_compression or {},
        "verification": verification or {},
        "inspections": inspections or {},
        "failure": failure or {},
    }


def _positive_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _int_list(value: Any, default: list[int], max_items: int) -> list[int]:
    if not isinstance(value, list):
        return list(default)
    result = []
    for item in value[:max_items]:
        try:
            result.append(max(1, min(4096, int(item))))
        except (TypeError, ValueError):
            continue
    return result or list(default)


def _float_list(value: Any, default: list[float], max_items: int) -> list[float]:
    if not isinstance(value, list):
        return list(default)
    result = []
    for item in value[:max_items]:
        try:
            parsed = float(item)
        except (TypeError, ValueError):
            continue
        if 0.5 <= parsed <= 2:
            result.append(parsed)
    return result or list(default)


def _str_list(value: Any, default: list[str], max_items: int) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    result = [str(item).strip() for item in value[:max_items] if str(item).strip()]
    return result or list(default)


def _error(message: str, code: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["data"] = data
    return payload
