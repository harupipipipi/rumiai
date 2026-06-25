import type {
  AdaptiveActivityState,
  AdaptiveAutomationState,
  AdaptiveContextBudget,
  AdaptiveEvidenceBundle,
  AdaptiveOnboardingState,
  AdaptiveOperatingProfile,
  AdaptiveRepositoryMap,
} from "../lib/adaptiveApi";

export const demoOnboardingState: AdaptiveOnboardingState = {
  completedStepId: null,
  useCases: [
    {
      id: "uc_workspace_copilot",
      label: "Workspace copilot",
      description: "Plan, inspect, and summarize local project work with review gates.",
      enabled: true,
    },
    {
      id: "uc_routine_ops",
      label: "Routine operations",
      description: "Track recurring maintenance and surface evidence before any write action.",
      enabled: true,
    },
    {
      id: "uc_learning",
      label: "Skill learning",
      description: "Capture repeated corrections as draft skills that stay reviewable.",
      enabled: false,
    },
  ],
  role: {
    title: "Local runtime assistant",
    scope: "Help the operator prepare and supervise local-first workflows.",
    stakeholders: ["Primary operator", "Review owner", "Pack maintainer"],
  },
  autonomy: {
    level: "confirm",
    label: "Ask before acting",
    guardrails: [
      "Never trust client-supplied approval flags.",
      "Require explicit approval before write-like host actions.",
      "Keep cloud and network use opt-in.",
    ],
  },
  responsibilities: {
    owned: [
      "Collect task intent and operating constraints.",
      "Propose safe automation plans.",
      "Keep evidence attached to decisions.",
    ],
    excluded: [
      "Bypass local policy or approval paths.",
      "Run destructive terminal commands without approval.",
      "Expose hidden secrets or raw credentials.",
    ],
  },
  review: {
    cadence: "Review every automation change before enablement.",
    reviewers: ["Operator", "Pack owner"],
    gates: ["New permission", "Host write", "Network egress", "Memory retention change"],
  },
  permissions: [
    {
      id: "permission_workspace_read",
      label: "Read selected workspace",
      risk: "low",
      mode: "Allowed after workspace trust",
      description: "Index visible files and repository metadata.",
    },
    {
      id: "permission_host_write",
      label: "Write local files",
      risk: "high",
      mode: "Approval required",
      description: "Create or update local project files only after review.",
    },
    {
      id: "permission_network",
      label: "Network access",
      risk: "medium",
      mode: "Ask per destination",
      description: "Fetch external context only when the operator approves the destination.",
    },
  ],
  privacyMemory: {
    memoryMode: "Project-scoped summaries",
    retention: "Keep durable memory disabled until the operator enables it.",
    sensitiveBoundaries: ["Secrets", "Private keys", "Personal messages", "Unapproved screenshots"],
  },
  skillLearning: {
    enabled: true,
    sources: ["Operator corrections", "Approved playbooks", "Repeated review outcomes"],
    reviewRequired: true,
  },
  packRecommendations: [
    {
      id: "pack_coding",
      label: "Coding workspace guardrails",
      reason: "The selected use cases involve repository inspection and local file changes.",
      status: "enabled",
    },
    {
      id: "pack_evidence",
      label: "Evidence capture",
      reason: "Keeps approvals, diffs, and context snapshots together.",
      status: "recommended",
    },
    {
      id: "pack_automation",
      label: "Automation scheduler",
      reason: "Useful after scenario simulation passes.",
      status: "needs_review",
    },
  ],
  scenarioSimulation: [
    {
      id: "scenario_dependency_update",
      label: "Dependency update",
      prompt: "Summarize outdated packages and propose a safe update order.",
      expectedOutcome: "Draft plan only, with terminal execution held for approval.",
      requiredApprovals: ["Terminal command", "File write"],
    },
    {
      id: "scenario_release_notes",
      label: "Release notes",
      prompt: "Generate release notes from local git history and linked evidence.",
      expectedOutcome: "Editable draft with source citations.",
      requiredApprovals: ["Repository read"],
    },
  ],
  settingsDiff: [
    {
      id: "diff_autonomy",
      label: "Autonomy",
      before: "Manual only",
      after: "Ask before acting",
      tone: "info",
    },
    {
      id: "diff_memory",
      label: "Memory",
      before: "Off",
      after: "Project-scoped summaries, review required",
      tone: "warning",
    },
    {
      id: "diff_network",
      label: "Network",
      before: "Blocked",
      after: "Ask per destination",
      tone: "warning",
    },
  ],
};

export const demoOperatingProfile: AdaptiveOperatingProfile = {
  id: "demo_profile",
  name: "Default local operator profile",
  summary: "A conservative operating profile for adaptive runtime work in the defaultspack control panel.",
  role: demoOnboardingState.role,
  autonomy: demoOnboardingState.autonomy,
  focusAreas: ["Planning", "Repository evidence", "Approval-aware automation"],
  boundaries: demoOnboardingState.responsibilities.excluded,
  approvalPolicy: demoOnboardingState.permissions,
  privacyMemory: demoOnboardingState.privacyMemory,
  skillLearning: demoOnboardingState.skillLearning,
  packRecommendations: demoOnboardingState.packRecommendations,
  review: demoOnboardingState.review,
  updatedAt: null,
};

export const demoActivityState: AdaptiveActivityState = {
  counters: {
    running: 2,
    needsReview: 3,
    blocked: 1,
    completedToday: 8,
  },
  items: [
    {
      id: "activity_release_notes",
      title: "Release notes draft",
      kind: "task",
      status: "running",
      summary: "Collecting approved repository evidence and summarizing visible changes.",
      actor: "Adaptive runtime",
      startedAt: "Today 09:24",
      evidenceCount: 5,
      toolLabel: "Repository search",
      internalToolId: "coding_file_search",
    },
    {
      id: "activity_terminal_review",
      title: "Terminal action waiting",
      kind: "approval",
      status: "needs_review",
      summary: "A proposed command needs explicit operator approval before execution.",
      actor: "Automation studio",
      startedAt: "Today 09:18",
      evidenceCount: 2,
      requiresReview: true,
      internalToolId: "coding_terminal_exec",
    },
    {
      id: "activity_memory_boundary",
      title: "Memory retention boundary",
      kind: "memory",
      status: "blocked",
      summary: "Long-term memory write was blocked until a profile review completes.",
      actor: "Privacy guard",
      startedAt: "Yesterday 16:42",
      evidenceCount: 1,
      requiresReview: true,
      internalToolId: "memory_write",
    },
  ],
  reviewQueue: [
    {
      id: "review_host_write",
      title: "File write permission",
      reason: "Automation wants to update generated release notes.",
      risk: "high",
      requestedBy: "Release automation",
      ageLabel: "6 min",
    },
    {
      id: "review_network",
      title: "Network destination",
      reason: "Scenario simulation requests external documentation lookup.",
      risk: "medium",
      requestedBy: "Research step",
      ageLabel: "14 min",
    },
  ],
};

export const demoAutomationState: AdaptiveAutomationState = {
  automations: [
    {
      id: "automation_daily_context",
      name: "Daily context refresh",
      description: "Refresh repository map, stale tasks, and context budget before the workday starts.",
      trigger: "Weekday morning",
      schedule: "09:00 local time",
      enabled: true,
      risk: "low",
      lastRun: "Today 09:00",
      steps: [
        {
          id: "step_repository_map",
          label: "Refresh repository map",
          capabilityLabel: "Repository index",
          internalToolId: "coding_context",
        },
        {
          id: "step_budget",
          label: "Estimate context budget",
          capabilityLabel: "Context planner",
        },
      ],
    },
    {
      id: "automation_release_notes",
      name: "Release note assistant",
      description: "Draft release notes from approved git evidence and open review items.",
      trigger: "Manual",
      schedule: "On demand",
      enabled: false,
      risk: "medium",
      lastRun: null,
      steps: [
        {
          id: "step_git_summary",
          label: "Collect visible git changes",
          capabilityLabel: "Git summary",
          internalToolId: "coding_git_diff",
        },
        {
          id: "step_write_draft",
          label: "Prepare editable draft",
          capabilityLabel: "Draft writer",
          internalToolId: "artifact_create",
          requiresApproval: true,
        },
      ],
    },
  ],
  templates: [
    {
      id: "template_review_digest",
      name: "Review digest",
      description: "Collect pending approvals, blockers, and evidence into a short digest.",
    },
    {
      id: "template_pack_health",
      name: "Pack health check",
      description: "Summarize local pack status without enabling network access.",
    },
  ],
  simulation: {
    scenario: "Update a dependency and write the migration note.",
    result: "Plan is safe to draft; terminal and file write remain approval-gated.",
    approvals: ["Terminal command", "File write"],
  },
};

export const demoEvidenceBundle: AdaptiveEvidenceBundle = {
  selectedId: "evidence_diff",
  items: [
    {
      id: "evidence_diff",
      title: "Workspace diff summary",
      kind: "file",
      sourceLabel: "Local repository",
      capturedAt: "Today 09:21",
      summary: "Two adaptive UI files changed and no central integration files were touched.",
      confidence: 0.91,
      redactions: ["Secrets omitted", "Absolute user home hidden"],
      internalToolId: "coding_git_diff",
    },
    {
      id: "evidence_approval",
      title: "Approval policy snapshot",
      kind: "approval",
      sourceLabel: "Local policy",
      capturedAt: "Today 09:17",
      summary: "Write-like host actions require explicit local approval.",
      confidence: 0.96,
      redactions: ["Operator token redacted"],
    },
    {
      id: "evidence_test",
      title: "SSR component render",
      kind: "test",
      sourceLabel: "Webapp tests",
      capturedAt: "Pending",
      summary: "Adaptive surfaces are expected to render without a browser runtime.",
      confidence: 0.8,
      redactions: [],
    },
  ],
};

export const demoRepositoryMap: AdaptiveRepositoryMap = {
  rootLabel: "defaultspack webapp",
  branch: "adaptive-ui",
  sections: [
    {
      id: "section_owned",
      label: "Owned adaptive surface",
      description: "Files the adaptive frontend worker can safely create or edit.",
      paths: [
        {
          path: "src/adaptive/",
          role: "Reusable UI surfaces",
          status: "owned",
        },
        {
          path: "src/lib/adaptiveApi.ts",
          role: "Adaptive API wrapper",
          status: "owned",
        },
      ],
    },
    {
      id: "section_read_only",
      label: "Read-only integration context",
      description: "Central shell files that can inform design but are not edited by this worker.",
      paths: [
        {
          path: "src/App.tsx",
          role: "Application integration",
          status: "read_only",
        },
        {
          path: "src/components/WorkspaceTabs.tsx",
          role: "Workspace navigation",
          status: "read_only",
        },
      ],
    },
  ],
  risks: [
    "Do not edit central integration files from this surface task.",
    "Keep tool and permission display labels human-readable.",
  ],
};

export const demoContextBudget: AdaptiveContextBudget = {
  used: 6840,
  limit: 12000,
  reserved: 1800,
  riskLevel: "medium",
  lastTrim: "Today 09:05",
  segments: [
    {
      id: "segment_task",
      label: "Task brief",
      tokens: 1420,
      tone: "info",
    },
    {
      id: "segment_repo",
      label: "Repository map",
      tokens: 2180,
      tone: "good",
    },
    {
      id: "segment_evidence",
      label: "Evidence",
      tokens: 1960,
      tone: "warning",
    },
    {
      id: "segment_memory",
      label: "Memory guardrails",
      tokens: 1280,
      tone: "neutral",
    },
  ],
  compressionPlan: [
    "Keep file paths and approval facts verbatim.",
    "Summarize repeated activity rows after review.",
    "Drop stale simulation output before expanding repository context.",
  ],
};
