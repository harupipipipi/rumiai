from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.tool_policy.internal_context import (
    internal_tool_decision_allows,
    tool_server_approval_context_is_internal,
)
from domain.ui_compiler import (
    UIAgentTask,
    UICompilerArtifactStore,
    UICompilerConfig,
    UIPlan,
)
from domain.ui_compiler.models import DEFAULT_SCENARIOS, DEFAULT_TEXT_SCALES, DEFAULT_VIEWPORTS
from domain.ui_compiler.planner import RecursiveUIPlanner

from .agent_backend import UIAgentBackend
from .audit_orchestrator import UIQualityAuditOrchestrator
from .candidate_generator import CandidateGenerator
from .candidate_selector import CandidateSelector
from .composer import PageComposer
from .compression_inspector import CompressionInspector
from .fake_agent_backend import FakeUIAgentBackend
from .foundation_generator import FoundationGenerator
from .project_writer import write_json
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
            run_root = store.run_root(plan.run_id)
            existing_artifacts = _existing_idempotent_result(
                store=store,
                plan=plan,
                run_root=run_root,
                idempotency_key=_idempotency(data),
            )
            if existing_artifacts is not None:
                return existing_artifacts
            artifacts = store.save_plan(plan, idempotency_key=_idempotency(data))
            final_report = _read_final_report(run_root)
            if final_report and _idempotency(data):
                summary = final_report.get("summary") if isinstance(final_report.get("summary"), dict) else {}
                report_path = ".rumi/ui/runs/{}/reports/final.json".format(plan.run_id)
                if final_report.get("status") == "ok":
                    return {
                        "status": "ok",
                        "data": {
                            "runId": plan.run_id,
                            "artifacts": artifacts,
                            "summary": summary,
                            "report": report_path,
                            "idempotent": True,
                        },
                        "widget": {
                            "type": "ui_build_recursive",
                            "run_id": plan.run_id,
                            "report": report_path,
                            "summary": summary,
                        },
                    }
                return _error(
                    "recursive UI build verification failed",
                    "UI_RECURSIVE_BUILD_FAILED",
                    data={"runId": plan.run_id, "report": report_path, "idempotent": True},
                )
            store.ensure_run_dirs(plan.run_id)
            artifacts = {
                **artifacts,
                **_write_layer_artifacts(store=store, plan=plan, run_root=run_root, ui_tree=root_payload),
            }
            target_workspace = _target_workspace(workspace, data.get("target"))
            foundation_generator = FoundationGenerator(backend=self.agent_backend, store=store)
            foundations = foundation_generator.generate(
                run_id=plan.run_id,
                run_root=run_root,
                count=options["foundationCandidates"],
                context=context,
            )
            accepted_foundation = foundation_generator.select(run_id=plan.run_id, candidates=foundations)
            if options["stopAfter"] == "foundation":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="foundation",
                    summary=_summary(plan, foundations, {}, {}, compression_failures=0, build_status="stage-foundation"),
                    accepted_foundation=accepted_foundation.to_dict(),
                )
            candidate_generator = CandidateGenerator(backend=self.agent_backend, store=store)
            candidate_map = candidate_generator.generate_for_contracts(
                run_id=plan.run_id,
                run_root=run_root,
                contracts=plan.contracts(),
                foundation=accepted_foundation.spec.to_dict(),
                context=context,
                fake_failures=_fake_failures(data),
            )
            if options["stopAfter"] == "candidates":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="candidates",
                    summary=_summary(plan, foundations, candidate_map, {}, compression_failures=0, build_status="stage-candidates"),
                    accepted_foundation=accepted_foundation.to_dict(),
                )
            render_runner = RenderMatrixRunner(store=store)
            inspector = CompressionInspector()
            selector = CandidateSelector(store=store)
            accepted: dict[str, Any] = {}
            inspection_objects_by_node: dict[str, dict[str, Any]] = {}
            inspections_by_node: dict[str, dict[str, Any]] = {}
            render_matrices_by_node: dict[str, dict[str, Any]] = {}
            for contract in plan.contracts():
                render_matrices: dict[str, Any] = {}
                for bundle in candidate_map.get(contract.id, []):
                    matrix = render_runner.render_candidate(
                        run_id=plan.run_id,
                        bundle=bundle,
                        viewports=options["viewports"],
                        scenarios=options["scenarios"],
                        text_scales=options["textScales"],
                        browser_render=options["browserRender"],
                    )
                    render_matrices[bundle.candidate_id] = matrix
                render_matrices_by_node[contract.id] = render_matrices
            if options["stopAfter"] == "renderMatrix":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="renderMatrix",
                    summary=_summary(plan, foundations, candidate_map, {}, compression_failures=0, build_status="stage-render-matrix"),
                    accepted_foundation=accepted_foundation.to_dict(),
                    extra={
                        "renderMatrices": {
                            node_id: {
                                candidate_id: matrix.to_dict()
                                for candidate_id, matrix in matrices.items()
                            }
                            for node_id, matrices in render_matrices_by_node.items()
                        }
                    },
                )
            for contract in plan.contracts():
                inspections = {}
                for bundle in candidate_map.get(contract.id, []):
                    matrix = render_matrices_by_node[contract.id][bundle.candidate_id]
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
                inspection_objects_by_node[contract.id] = inspections
                inspections_by_node[contract.id] = {
                    candidate_id: report.to_dict()
                    for candidate_id, report in inspections.items()
                }
            if options["stopAfter"] == "inspectCompression":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="inspectCompression",
                    summary=_summary(
                        plan,
                        foundations,
                        candidate_map,
                        {},
                        compression_failures=_compression_failure_count(inspections_by_node),
                        build_status="stage-inspect-compression",
                    ),
                    accepted_foundation=accepted_foundation.to_dict(),
                    inspections=inspections_by_node,
                )
            for contract in plan.contracts():
                decision = selector.select(
                    run_id=plan.run_id,
                    node_id=contract.id,
                    candidates=candidate_map.get(contract.id, []),
                    inspections=inspection_objects_by_node.get(contract.id, {}),
                    run_root=run_root,
                )
                if not decision.passed:
                    retry_bundle = candidate_generator.generate_retry_for_contract(
                        run_id=plan.run_id,
                        run_root=run_root,
                        contract=contract,
                        foundation=accepted_foundation.spec.to_dict(),
                        attempt=1,
                        context=context,
                        fake_failures=_fake_failures(data),
                    )
                    candidate_map.setdefault(contract.id, []).append(retry_bundle)
                    retry_matrix = render_runner.render_candidate(
                        run_id=plan.run_id,
                        bundle=retry_bundle,
                        viewports=options["viewports"],
                        scenarios=options["scenarios"],
                        text_scales=options["textScales"],
                        browser_render=options["browserRender"],
                    )
                    retry_report = inspector.inspect_candidate(
                        bundle=retry_bundle,
                        contract=contract.to_dict(),
                        render_matrix=retry_matrix,
                    )
                    store.save_inspection_report(
                        run_id=plan.run_id,
                        node_id=contract.id,
                        candidate_id=retry_bundle.candidate_id,
                        report=retry_report.to_dict(),
                    )
                    inspection_objects_by_node.setdefault(contract.id, {})[retry_bundle.candidate_id] = retry_report
                    inspections_by_node.setdefault(contract.id, {})[retry_bundle.candidate_id] = retry_report.to_dict()
                    decision = selector.select(
                        run_id=plan.run_id,
                        node_id=contract.id,
                        candidates=candidate_map.get(contract.id, []),
                        inspections=inspection_objects_by_node.get(contract.id, {}),
                        run_root=run_root,
                    )
                if not decision.passed:
                    final = _final_report(
                        plan=plan,
                        artifacts=artifacts,
                        status="error",
                        summary=_summary(
                            plan,
                            foundations,
                            candidate_map,
                            accepted,
                            compression_failures=_compression_failure_count(inspections_by_node),
                            build_status="skipped",
                        ),
                        failure={
                            "code": "UI_RECURSIVE_BUILD_FAILED",
                            "failedNodeId": contract.id,
                            "attempts": [
                                "initial-candidates",
                                "regenerate-empty-directory-candidate",
                                "semantic-split-recommended",
                            ],
                        },
                        inspections=inspections_by_node,
                    )
                    report_path = store.save_final_report(run_id=plan.run_id, report=final)
                    return _error(
                        f"No acceptable candidate for {contract.id}",
                        "UI_RECURSIVE_BUILD_FAILED",
                        data={"runId": plan.run_id, "failedNodeId": contract.id, "report": report_path},
                    )
                accepted[contract.id] = decision
            if options["stopAfter"] == "selectCandidates":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="selectCandidates",
                    summary=_summary(
                        plan,
                        foundations,
                        candidate_map,
                        accepted,
                        compression_failures=_compression_failure_count(inspections_by_node),
                        build_status="stage-select-candidates",
                    ),
                    accepted_foundation=accepted_foundation.to_dict(),
                    accepted={node_id: decision.to_dict() for node_id, decision in accepted.items()},
                    inspections=inspections_by_node,
                )
            composition = PageComposer(store=store).compose(
                run_id=plan.run_id,
                run_root=run_root,
                plan=plan,
                accepted_decisions=accepted,
                target=data.get("target") if isinstance(data.get("target"), dict) else {},
            )
            if options["stopAfter"] == "composePage":
                return _stage_ok(
                    store=store,
                    plan=plan,
                    artifacts=artifacts,
                    stage="composePage",
                    summary=_summary(
                        plan,
                        foundations,
                        candidate_map,
                        accepted,
                        compression_failures=_compression_failure_count(inspections_by_node),
                        build_status="stage-compose-page",
                    ),
                    accepted_foundation=accepted_foundation.to_dict(),
                    accepted={node_id: decision.to_dict() for node_id, decision in accepted.items()},
                    composition=composition.to_dict(),
                    inspections=inspections_by_node,
                )
            page_manifest = composition.to_dict()
            page_matrix = render_runner.render_page(
                run_id=plan.run_id,
                run_root=run_root,
                manifest={
                    **page_manifest,
                    "visibleActionBudget": max(3, len(accepted) * 2),
                    "visibleActionCount": 2,
                },
                viewports=options["viewports"],
                scenarios=options["scenarios"],
                text_scales=options["textScales"],
                browser_render=options["browserRender"],
            )
            page_compression = inspector.inspect_page(render_matrix=page_matrix, accepted_count=len(accepted))
            quality_audit = UIQualityAuditOrchestrator().audit(
                plan=plan,
                foundation=accepted_foundation.spec.to_dict(),
                page_matrix=page_matrix,
                page_compression=page_compression,
                accepted_count=len(accepted),
            )
            verification_compression = dict(page_compression)
            if quality_audit.get("status") != "pass":
                verification_compression["status"] = "fail"
                verification_compression["qualityAuditStatus"] = quality_audit.get("status")
                verification_compression["failedAudits"] = quality_audit.get("failedAudits", [])
            verification = self.verifier.verify(
                workspace=target_workspace,
                render_matrix=page_matrix,
                compression_report=verification_compression,
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
                quality_audit=quality_audit,
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
        workspace_root=_context_workspace_root(context),
        authorized=_authorized(context),
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


def _context_workspace_root(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    raw = context.get("workspace_root") or context.get("workspaceRoot") or context.get("conversation_workspace_dir") or context.get("workspace_dir")
    return str(raw) if raw else None


def _authorized(context: dict[str, Any] | None) -> bool:
    return tool_server_approval_context_is_internal(context) or internal_tool_decision_allows(context)


def _options(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "foundationCandidates": _positive_int(data.get("foundationCandidates"), 3, 1, 6),
        "viewports": _int_list(data.get("viewports"), DEFAULT_VIEWPORTS, 8),
        "scenarios": _str_list(data.get("scenarios"), DEFAULT_SCENARIOS, 8),
        "textScales": _float_list(data.get("textScales"), DEFAULT_TEXT_SCALES, 6),
        "runBuild": bool(data.get("runBuild", True)),
        "stopAfter": _stage_name(data.get("stopAfter") or data.get("stop_after")),
        "browserRender": bool(data.get("browserRender") or data.get("browser_render")),
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
    quality_audit: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    inspections: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audits = quality_audit if isinstance(quality_audit, dict) else {}
    accepted_payload = accepted or {}
    verification_payload = verification or {}
    return {
        "status": status,
        "runId": plan.run_id,
        "artifacts": artifacts,
        "summary": summary,
        "planSummary": plan.to_dict()["summary"],
        "intent": audits.get("intent", {}),
        "acceptedFoundation": accepted_foundation or {},
        "foundation": audits.get("foundation", accepted_foundation or {}),
        "topology": audits.get("topology", {}),
        "split": audits.get("split", {}),
        "candidateGeneration": {
            "contracts": len(plan.contracts()),
            "candidateBundles": summary.get("candidateBundles"),
            "compressionFailures": summary.get("compressionFailures"),
        },
        "accepted": accepted or {},
        "acceptedSelection": accepted_payload,
        "composition": composition or {},
        "pageCompression": page_compression or {},
        "compression": audits.get("compression", page_compression or {}),
        "textPressure": audits.get("textPressure", {}),
        "typography": audits.get("typography", {}),
        "colorRoles": audits.get("colorRoles", {}),
        "surfaceAudit": audits.get("surfaceAudit", {}),
        "interactionBudget": audits.get("interactionBudget", {}),
        "responsive": audits.get("responsive", {}),
        "accessibility": audits.get("accessibility", {}),
        "qualityAudit": audits,
        "generatedFilesSummary": _generated_files_summary(
            plan=plan,
            artifacts=artifacts,
            composition=composition or {},
            verification=verification_payload,
        ),
        "recursiveSplitSummary": _recursive_split_summary(plan),
        "acceptedFoundationSummary": _accepted_foundation_summary(accepted_foundation or {}),
        "acceptedLeafBundlesSummary": _accepted_leaf_bundles_summary(accepted_payload),
        "auditSummary": _audit_summary(audits),
        "failedRetriedCandidateSummary": _failed_retried_candidate_summary(accepted_payload),
        "verification": verification_payload,
        "buildTestLint": {
            "lint": verification_payload.get("lint"),
            "test": verification_payload.get("test"),
            "build": verification_payload.get("build"),
            "commands": verification_payload.get("commands", []),
        },
        "inspections": inspections or {},
        "failure": failure or {},
    }


def _write_layer_artifacts(
    *,
    store: UICompilerArtifactStore,
    plan: UIPlan,
    run_root: Path,
    ui_tree: dict[str, Any],
) -> dict[str, Any]:
    run_prefix = f".rumi/ui/runs/{plan.run_id}"
    intent = _intent_artifact(plan)
    topology = _topology_artifact(plan)
    split = _split_manifest_artifact(plan, ui_tree)
    write_json(run_root / "intent.json", intent)
    write_json(run_root / "topology.json", topology)
    write_json(run_root / "split-manifest.json", split)
    pipeline_tasks = _save_pipeline_specialist_tasks(store=store, plan=plan, run_root=run_root)
    return {
        "intent": f"{run_prefix}/intent.json",
        "topology": f"{run_prefix}/topology.json",
        "splitManifest": f"{run_prefix}/split-manifest.json",
        "pipelineTasks": pipeline_tasks,
    }


PIPELINE_SPECIALIST_TASKS = [
    ("intent-agent", "intent", "Resolve product intent, audience, constraints, and trust/speed/readability/safety order."),
    ("page-topology-agent", "topology", "Design desktop, tablet, and mobile topology without desktop-shrink mobile."),
    ("semantic-region-planner", "semantic-region", "Split the page by responsibility, density, and visible action budget."),
    ("state-completeness-auditor", "state-audit", "Audit default, long, empty, loading, error, selected, disabled, success, warn, and error states."),
    ("responsive-auditor", "responsive", "Audit 390/768/1440 topology, overflow, disclosure, drawer, sheet, and step-down behavior."),
    ("accessibility-interaction-auditor", "accessibility", "Audit keyboard navigation, aria roles, contrast, focus visibility, and touch targets."),
    ("text-pressure-auditor", "text-pressure-audit", "Audit visible text blocks, visible characters, line length, clipping, ellipses, and Japanese wrapping."),
    ("compression-auditor", "compression-audit", "Audit gap, boundary, text, action, surface, hierarchy, and responsive pressure."),
    ("candidate-selector", "candidate-selector", "Select only artifact-backed candidates that passed render and audit evidence."),
    ("composition-agent", "composition", "Compose accepted bundles by slot mapping without editing leaf sources."),
    ("refinement-selector", "refinement-selector", "Choose accepted artifacts or trigger regenerate/refine based on audit evidence."),
]


def _save_pipeline_specialist_tasks(
    *,
    store: UICompilerArtifactStore,
    plan: UIPlan,
    run_root: Path,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for role_id, kind, prompt in PIPELINE_SPECIALIST_TASKS:
        task_id = f"{plan.run_id}-{role_id}"
        output_dir = run_root / "pipeline-tasks" / role_id
        task = UIAgentTask(
            task_id=task_id,
            run_id=plan.run_id,
            node_id="page",
            candidate_id=role_id,
            kind=kind,
            prompt=prompt,
            output_dir=str(output_dir),
            allowed_paths=[str(output_dir)],
            metadata={"role": role_id, "stage": kind, "subagentSplit": True},
        )
        payload = task.to_dict()
        store.save_agent_task(run_id=plan.run_id, task_id=task_id, task=payload)
        write_json(output_dir / "task.json", payload)
        tasks.append(
            {
                "role": role_id,
                "kind": kind,
                "taskId": task_id,
                "outputDir": f".rumi/ui/runs/{plan.run_id}/pipeline-tasks/{role_id}",
            }
        )
    return tasks


def _intent_artifact(plan: UIPlan) -> dict[str, Any]:
    root = plan.root.node
    metadata = dict(root.metadata or {})
    responsibilities = root.responsibilities.to_dict()
    return {
        "status": "planned",
        "runId": plan.run_id,
        "productMode": metadata.get("productMode") or root.density,
        "audience": metadata.get("audience") or "coding-tool-user",
        "primaryIntent": root.purpose,
        "secondaryIntent": [
            child.node.purpose
            for child in plan.root.children
            if child.node.importance != "primaryRegion"
        ],
        "tertiaryIntent": [],
        "priorityOrder": metadata.get("priorityOrder") or ["trust", "readability", "speed", "safety"],
        "density": root.density,
        "importance": root.importance,
        "desktopTabletMobilePriority": ["desktop", "mobile", "tablet"],
        "constraints": {
            "implementationMode": root.implementation_mode,
            "responsibilities": responsibilities,
            "mobilePolicy": metadata.get("mobilePolicy"),
        },
    }


def _topology_artifact(plan: UIPlan) -> dict[str, Any]:
    nodes = []
    for planned in plan.root.planned_nodes():
        envelope = planned.node.layout_envelope
        nodes.append(
            {
                "nodeId": planned.node.id,
                "importance": planned.node.importance,
                "density": planned.node.density,
                "desktop": {
                    "preferredWidth": envelope.preferred_width,
                    "maxWidth": envelope.max_width,
                },
                "tablet": {
                    "minWidth": envelope.min_width,
                    "preferredWidth": envelope.preferred_width,
                },
                "mobile": {
                    "behavior": envelope.mobile_behavior or "stack",
                    "policy": "route/drawer/sheet/disclosure/step-down instead of desktop shrink",
                },
                "visibleActionBudget": planned.node.visible_action_budget,
            }
        )
    return {
        "status": "planned",
        "runId": plan.run_id,
        "viewports": [390, 768, 1440],
        "nodes": nodes,
    }


def _split_manifest_artifact(plan: UIPlan, ui_tree: dict[str, Any]) -> dict[str, Any]:
    root_children = [
        {
            "nodeId": child.node.id,
            "purpose": child.node.purpose,
            "importance": child.node.importance,
            "density": child.node.density,
            "visibleActionBudget": child.node.visible_action_budget,
            "responsibilities": child.node.responsibilities.to_dict(),
            "slotId": _slot_for_child(plan.root, child.node.id),
        }
        for child in plan.root.children
    ]
    contracts = [
        {
            "contractId": contract.id,
            "nodeId": contract.source_node_id or contract.id,
            "candidateCount": contract.candidate_count,
            "visibleActionBudget": contract.visible_action_budget,
            "requiredStates": list(contract.required_states),
        }
        for contract in plan.contracts()
    ]
    return {
        "status": "planned",
        "runId": plan.run_id,
        "splitBasis": "semantic responsibility boundaries",
        "uiTree": ui_tree,
        "regions": root_children,
        "contracts": contracts,
    }


def _slot_for_child(parent: Any, child_id: str) -> str | None:
    for slot in parent.node.slots:
        if slot.accepts_node_id == child_id:
            return slot.id
    return None


def _generated_files_summary(
    *,
    plan: UIPlan,
    artifacts: dict[str, Any],
    composition: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    return {
        "plan": {
            "manifest": artifacts.get("manifest"),
            "blueprint": artifacts.get("blueprint"),
            "report": artifacts.get("report"),
            "intent": artifacts.get("intent"),
            "topology": artifacts.get("topology"),
            "splitManifest": artifacts.get("splitManifest"),
            "pipelineTasks": list(artifacts.get("pipelineTasks") if isinstance(artifacts.get("pipelineTasks"), list) else []),
            "contracts": list(artifacts.get("contracts") or []),
        },
        "composition": {
            "sourceRoot": composition.get("sourceRoot"),
            "entry": composition.get("entry"),
            "imports": len(composition.get("imports") if isinstance(composition.get("imports"), list) else []),
            "slotMappings": len(composition.get("slotMappings") if isinstance(composition.get("slotMappings"), list) else []),
        },
        "finalReport": f".rumi/ui/runs/{plan.run_id}/reports/final.json",
        "npm": {
            "lint": verification.get("lint"),
            "test": verification.get("test"),
            "build": verification.get("build"),
        },
    }


def _recursive_split_summary(plan: UIPlan) -> dict[str, Any]:
    plan_dict = plan.to_dict()
    return {
        "summary": plan_dict.get("summary") or {},
        "semanticRegions": [
            {
                "nodeId": child.node.id,
                "purpose": child.node.purpose,
                "density": child.node.density,
                "visibleActionBudget": child.node.visible_action_budget,
            }
            for child in plan.root.children
        ],
        "contracts": [
            {
                "contractId": contract.id,
                "candidateCount": contract.candidate_count,
                "visibleActionBudget": contract.visible_action_budget,
            }
            for contract in plan.contracts()
        ],
    }


def _accepted_foundation_summary(foundation: dict[str, Any]) -> dict[str, Any]:
    spec = foundation.get("spec") if isinstance(foundation.get("spec"), dict) else {}
    if not spec:
        spec = foundation
    direction = spec.get("direction") if isinstance(spec.get("direction"), dict) else {}
    typography = spec.get("typography") if isinstance(spec.get("typography"), dict) else {}
    color = spec.get("color") if isinstance(spec.get("color"), dict) else {}
    surface = spec.get("surface") if isinstance(spec.get("surface"), dict) else {}
    return {
        "candidateId": foundation.get("candidateId") or spec.get("candidateId"),
        "productMode": direction.get("productMode"),
        "typographyRoles": sorted((typography.get("roles") or {}).keys()) if isinstance(typography.get("roles"), dict) else [],
        "colorRoles": list(color.get("roles") if isinstance(color.get("roles"), list) else []),
        "surfacePolicy": surface,
        "primitiveCount": len(spec.get("primitives") if isinstance(spec.get("primitives"), list) else []),
    }


def _accepted_leaf_bundles_summary(accepted: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for node_id, decision in sorted(accepted.items()):
        data = decision if isinstance(decision, dict) else {}
        chosen = data.get("acceptedCandidateId")
        decision_payload = data.get("decision") if isinstance(data.get("decision"), dict) else {}
        rows.append(
            {
                "nodeId": node_id,
                "acceptedCandidateId": chosen,
                "compressionScore": decision_payload.get("compressionScore"),
                "rejectedCount": len(data.get("rejected") if isinstance(data.get("rejected"), list) else []),
                "stateCoverage": decision_payload.get("stateCoverage"),
                "renderMatrix": decision_payload.get("renderMatrix"),
            }
        )
    return rows


def _audit_summary(audits: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "compression",
        "textPressure",
        "typography",
        "colorRoles",
        "surfaceAudit",
        "interactionBudget",
        "responsive",
        "accessibility",
    ]
    return {
        "status": audits.get("status"),
        "failedAudits": list(audits.get("failedAudits") if isinstance(audits.get("failedAudits"), list) else []),
        "sections": {
            key: audits.get(key, {}).get("status")
            for key in keys
            if isinstance(audits.get(key), dict)
        },
    }


def _failed_retried_candidate_summary(accepted: dict[str, Any]) -> dict[str, Any]:
    rejected: list[dict[str, Any]] = []
    retried: list[dict[str, Any]] = []
    for node_id, decision in sorted(accepted.items()):
        data = decision if isinstance(decision, dict) else {}
        for item in data.get("rejected") if isinstance(data.get("rejected"), list) else []:
            if isinstance(item, dict):
                rejected.append({"nodeId": node_id, **item})
        accepted_candidate = str(data.get("acceptedCandidateId") or "")
        if "retry" in accepted_candidate:
            retried.append({"nodeId": node_id, "acceptedCandidateId": accepted_candidate})
    return {
        "rejectedCount": len(rejected),
        "retriedAcceptedCount": len(retried),
        "rejected": rejected,
        "retriedAccepted": retried,
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


def _stage_name(value: Any) -> str:
    stage = str(value or "").strip()
    return stage if stage in _STOP_AFTER_STAGES else ""


_STOP_AFTER_STAGES = {
    "foundation",
    "candidates",
    "renderMatrix",
    "inspectCompression",
    "selectCandidates",
    "composePage",
}


def _compression_failure_count(inspections_by_node: dict[str, dict[str, Any]]) -> int:
    return sum(
        1
        for reports in inspections_by_node.values()
        for report in reports.values()
        if isinstance(report, dict) and report.get("status") != "pass"
    )


def _stage_ok(
    *,
    store: UICompilerArtifactStore,
    plan: UIPlan,
    artifacts: dict[str, Any],
    stage: str,
    summary: dict[str, Any],
    accepted_foundation: dict[str, Any] | None = None,
    accepted: dict[str, Any] | None = None,
    composition: dict[str, Any] | None = None,
    inspections: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final = _final_report(
        plan=plan,
        artifacts=artifacts,
        status="ok",
        summary=summary,
        accepted_foundation=accepted_foundation,
        accepted=accepted,
        composition=composition,
        inspections=inspections,
    )
    final["stage"] = stage
    if extra:
        final.update(extra)
    report_path = store.save_final_report(run_id=plan.run_id, report=final)
    data: dict[str, Any] = {
        "runId": plan.run_id,
        "artifacts": artifacts,
        "summary": summary,
        "report": report_path,
        "stage": stage,
    }
    if accepted_foundation:
        data["acceptedFoundation"] = accepted_foundation
    if accepted:
        data["accepted"] = accepted
    if composition:
        data["composition"] = composition
    return {
        "status": "ok",
        "data": data,
        "widget": {
            "type": "ui_build_recursive_stage",
            "stage": stage,
            "run_id": plan.run_id,
            "report": report_path,
            "summary": summary,
        },
    }


def _error(message: str, code: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["data"] = data
    return payload


def _read_final_report(run_root: Path) -> dict[str, Any]:
    import json

    try:
        payload = json.loads((run_root / "reports" / "final.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _existing_idempotent_result(
    *,
    store: UICompilerArtifactStore,
    plan: UIPlan,
    run_root: Path,
    idempotency_key: str | None,
) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    manifest = _read_json(run_root / "manifest.json")
    if manifest.get("idempotencyKey") != idempotency_key:
        return None
    final_report = _read_final_report(run_root)
    if not final_report:
        return None
    summary = final_report.get("summary") if isinstance(final_report.get("summary"), dict) else {}
    report_path = ".rumi/ui/runs/{}/reports/final.json".format(plan.run_id)
    artifacts = store._artifact_response(  # type: ignore[attr-defined]
        run_id=plan.run_id,
        constitution_hash=str(manifest.get("constitutionHash") or ""),
        plan_hash=str(manifest.get("planHash") or ""),
        contract_paths=list((manifest.get("files") or {}).get("contracts") or []),
    )
    if final_report.get("status") == "ok":
        return {
            "status": "ok",
            "data": {
                "runId": plan.run_id,
                "artifacts": artifacts,
                "summary": summary,
                "report": report_path,
                "idempotent": True,
            },
            "widget": {
                "type": "ui_build_recursive",
                "run_id": plan.run_id,
                "report": report_path,
                "summary": summary,
            },
        }
    return _error(
        "recursive UI build verification failed",
        "UI_RECURSIVE_BUILD_FAILED",
        data={"runId": plan.run_id, "report": report_path, "idempotent": True},
    )


def _read_json(path: Path) -> dict[str, Any]:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
