from __future__ import annotations

from .artifact_store import UICompilerArtifactStore
from .compression_models import CompressionIssue, CompressionReport
from .composition_models import BuildVerificationReport, CompositionManifest, SelectionDecision
from .complexity import budget_violations, calculate_complexity, is_within_leaf_budget
from .foundation_models import FoundationCandidate, FoundationSpec
from .generation_models import (
    AcceptedBundle,
    CandidateBundle,
    ComponentBundleManifest,
    UIAgentResult,
    UIAgentTask,
    UIBuildRun,
)
from .models import (
    CandidateBudget,
    ComponentContract,
    ComplexitySignals,
    LayoutEnvelope,
    LeafBudget,
    OwnershipGroup,
    PlannedNode,
    PlanningDiagnostic,
    ResponsibilitySet,
    SlotDefinition,
    UICompilerConfig,
    UINode,
    UIPlan,
)
from .planner import RecursiveUIPlanner
from .render_models import RenderMatrix, RenderSnapshot
from .service import commit_ui_plan, compile_ui_plan

__all__ = [
    "AcceptedBundle",
    "BuildVerificationReport",
    "CandidateBudget",
    "CandidateBundle",
    "ComponentBundleManifest",
    "ComponentContract",
    "CompressionIssue",
    "CompressionReport",
    "CompositionManifest",
    "ComplexitySignals",
    "FoundationCandidate",
    "FoundationSpec",
    "LayoutEnvelope",
    "LeafBudget",
    "OwnershipGroup",
    "PlannedNode",
    "PlanningDiagnostic",
    "RecursiveUIPlanner",
    "RenderMatrix",
    "RenderSnapshot",
    "ResponsibilitySet",
    "SelectionDecision",
    "SlotDefinition",
    "UIAgentResult",
    "UIAgentTask",
    "UIBuildRun",
    "UICompilerArtifactStore",
    "UICompilerConfig",
    "UINode",
    "UIPlan",
    "budget_violations",
    "calculate_complexity",
    "commit_ui_plan",
    "compile_ui_plan",
    "is_within_leaf_budget",
]
