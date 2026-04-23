import type {
  ApiStartupCatalog,
  ApiStartupProfile,
  ApiStartupSlotCandidate,
  ApiStartupStandardPack,
} from './apiTypes';

export type StartupSortMode = 'recommended' | 'recent' | 'name';

export interface StartupProfileIssue {
  description: string;
  severity: 'warning' | 'danger';
  title: string;
}

export interface StartupProfileBadge {
  label: string;
  tone: 'accent' | 'neutral' | 'success' | 'warning' | 'danger';
}

export interface StartupProfileSlotSummary {
  healthy: boolean;
  label: string;
  packId: string;
  packName: string;
  slotId: string;
}

export interface StartupProfileView {
  badges: StartupProfileBadge[];
  headline: string;
  issueCount: number;
  issues: StartupProfileIssue[];
  lastLaunched: boolean;
  profile: ApiStartupProfile;
  runtimeReady: boolean;
  slots: StartupProfileSlotSummary[];
  standardPack: ApiStartupStandardPack | null;
  subtitle: string;
}

function sentenceCase(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function packDisplayName(packId: string, candidate: ApiStartupSlotCandidate | null): string {
  return candidate?.display_name || packId || 'Unavailable';
}

function describeApprovalIssue(issue: string): string | null {
  if (/needs approval/i.test(issue) || /must be approved/i.test(issue)) {
    return 'Approve this pack before using it in a launch profile.';
  }
  if (/changed since it was last approved/i.test(issue) || /modified since approval/i.test(issue)) {
    return 'This pack changed after approval. Re-approve it before launch.';
  }
  if (/is blocked/i.test(issue)) {
    return 'This pack is blocked in the current workspace.';
  }
  return null;
}

export function describeStartupIssue(issue: string, contextLabel?: string): StartupProfileIssue {
  const approvalIssue = describeApprovalIssue(issue);
  if (approvalIssue) {
    return {
      title: `${contextLabel || 'Pack'} needs attention`,
      description: approvalIssue,
      severity: /blocked/i.test(issue) ? 'danger' : 'warning',
    };
  }

  const missingPath = issue.match(/path '([^']+)' is missing/i);
  if (missingPath) {
    return {
      title: `${contextLabel || 'Pack'} is incomplete`,
      description: `Required files are missing at ${missingPath[1]}. Reinstall or repair the pack.`,
      severity: 'danger',
    };
  }

  const loadOrder = issue.match(/load_order is missing '([^']+)'/i);
  if (loadOrder) {
    return {
      title: `${contextLabel || 'Pack'} is misconfigured`,
      description: `The runtime is missing ${loadOrder[1]} in its load order.`,
      severity: 'danger',
    };
  }

  const missingTypes = issue.match(/missing required component types: (.+)/i);
  if (missingTypes) {
    return {
      title: `${contextLabel || 'Pack'} is missing required parts`,
      description: `The pack still needs: ${missingTypes[1]}.`,
      severity: 'danger',
    };
  }

  const standardPackMissing = issue.match(/Standard pack '([^']+)' is not installed/i);
  if (standardPackMissing) {
    return {
      title: 'Standard pack unavailable',
      description: `${standardPackMissing[1]} is not installed in this workspace.`,
      severity: 'danger',
    };
  }

  const standardPackSlot = issue.match(/Standard pack '([^']+)' has no runtime-ready '([^']+)' slot implementation/i);
  if (standardPackSlot) {
    return {
      title: `${sentenceCase(standardPackSlot[2])} slot is unavailable`,
      description: `${standardPackSlot[1]} cannot provide a working ${standardPackSlot[2]} slot right now.`,
      severity: 'warning',
    };
  }

  const packDisabled = issue.match(/Pack '([^']+)' is disabled/i);
  if (packDisabled) {
    return {
      title: `${contextLabel || packDisabled[1]} is turned off`,
      description: 'Enable the pack before trying to play or make it active.',
      severity: 'warning',
    };
  }

  return {
    title: `${contextLabel || 'Runtime issue'}`,
    description: issue,
    severity: 'warning',
  };
}

export function describeStartupActionError(error: string, fallbackAction: string): string {
  if (/Unauthorized|Invalid or expired code/i.test(error)) {
    return 'Your launcher session expired. Reload the panel and try again.';
  }
  if (/At least one startup profile must remain/i.test(error)) {
    return 'You need to keep at least one saved profile.';
  }
  const slotRuntime = error.match(/not runtime-ready for slot '([^']+)'(?:: (.+))?/i);
  if (slotRuntime) {
    const issue = slotRuntime[2] ? describeStartupIssue(slotRuntime[2], sentenceCase(slotRuntime[1])) : null;
    return issue?.description || `${sentenceCase(slotRuntime[1])} is not ready for launch yet.`;
  }
  const slotMismatch = error.match(/does not satisfy slot '([^']+)'/i);
  if (slotMismatch) {
    return `${sentenceCase(slotMismatch[1])} only accepts compatible packs. Pick another pack for that slot.`;
  }
  if (/Contract mismatch/i.test(error)) {
    return 'That pack does not match the selected slot contract.';
  }
  if (/Runtime handoff is unavailable/i.test(error)) {
    return 'Launch could not hand off to the runtime. Restart the kernel and try again.';
  }
  if (/Unknown standard pack/i.test(error)) {
    return 'The selected standard pack is no longer available in this workspace.';
  }
  if (/not available/i.test(error) && /Standard pack/i.test(error)) {
    return 'The selected standard pack is unavailable. Repair or switch the pack before saving.';
  }
  return error || `We could not ${fallbackAction}.`;
}

function resolveProfileIssues(
  profile: ApiStartupProfile,
  catalog: ApiStartupCatalog,
): {
  issues: StartupProfileIssue[];
  selectedCandidates: Record<string, ApiStartupSlotCandidate | null>;
  standardPack: ApiStartupStandardPack | null;
  slots: StartupProfileSlotSummary[];
} {
  const standardPack = catalog.standard_packs.find((pack) => pack.pack_id === profile.standard_pack_id) ?? null;
  const issues: StartupProfileIssue[] = [];
  const selectedCandidates: Record<string, ApiStartupSlotCandidate | null> = {};
  const slots: StartupProfileSlotSummary[] = [];

  if (standardPack && !standardPack.runtime_ready) {
    standardPack.runtime_issues.forEach((issue) => {
      issues.push(describeStartupIssue(issue, standardPack.display_name));
    });
  }

  catalog.slot_specs.forEach((slot) => {
    const packId = profile.slots[slot.slot_id] ?? '';
    const candidate = (catalog.slot_candidates[slot.slot_id] ?? []).find(
      (item) => item.pack_id === packId,
    ) ?? null;

    selectedCandidates[slot.slot_id] = candidate;
    slots.push({
      slotId: slot.slot_id,
      label: slot.label,
      packId,
      packName: packDisplayName(packId, candidate),
      healthy: Boolean(candidate?.runtime_ready),
    });

    if (!candidate) {
      issues.push({
        title: `${slot.label} slot needs a pack`,
        description: `Choose a compatible pack for ${slot.label.toLowerCase()}.`,
        severity: 'warning',
      });
      return;
    }

    if (!candidate.runtime_ready) {
      const candidateIssues = candidate.runtime_issues.length
        ? candidate.runtime_issues
        : ['No runtime-ready component matched this slot.'];
      candidateIssues.forEach((issue) => {
        issues.push(describeStartupIssue(issue, slot.label));
      });
    }
  });

  return { standardPack, selectedCandidates, issues, slots };
}

export function buildStartupProfileView(
  profile: ApiStartupProfile,
  catalog: ApiStartupCatalog,
  activeProfileId: string | null,
  lastLaunchedProfileId: string | null,
): StartupProfileView {
  const { issues, slots, standardPack } = resolveProfileIssues(profile, catalog);
  const active = activeProfileId === profile.profile_id;
  const lastLaunched = lastLaunchedProfileId === profile.profile_id;
  const runtimeReady = issues.length === 0;
  const badges: StartupProfileBadge[] = [];

  if (active) {
    badges.push({ label: 'Active', tone: 'accent' });
  }
  if (lastLaunched) {
    badges.push({ label: 'Last Played', tone: 'neutral' });
  }
  badges.push({
    label: runtimeReady ? 'Ready to Play' : `${issues.length} issue${issues.length === 1 ? '' : 's'}`,
    tone: runtimeReady ? 'success' : issues.some((issue) => issue.severity === 'danger') ? 'danger' : 'warning',
  });

  const headline = runtimeReady
    ? active
      ? 'Ready to play from your active setup.'
      : 'Ready for launch.'
    : issues[0]?.title || 'Needs attention before launch.';

  const subtitle = runtimeReady
    ? `${standardPack?.display_name || profile.standard_pack_id} • ${slots.length} connected slots`
    : issues[0]?.description || `${standardPack?.display_name || profile.standard_pack_id} needs attention.`;

  return {
    profile,
    standardPack,
    runtimeReady,
    issueCount: issues.length,
    issues,
    badges,
    headline,
    subtitle,
    slots,
    lastLaunched,
  };
}

export function filterAndSortStartupProfiles(
  profiles: StartupProfileView[],
  query: string,
  sortMode: StartupSortMode,
): StartupProfileView[] {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = normalizedQuery
    ? profiles.filter((profile) => {
        const haystack = [
          profile.profile.name,
          profile.profile.profile_id,
          profile.standardPack?.display_name || profile.profile.standard_pack_id,
          ...profile.slots.map((slot) => `${slot.label} ${slot.packName} ${slot.packId}`),
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(normalizedQuery);
      })
    : profiles;

  return [...filtered].sort((left, right) => {
    if (sortMode === 'name') {
      return left.profile.name.localeCompare(right.profile.name);
    }
    if (sortMode === 'recent') {
      return right.profile.updated_at - left.profile.updated_at;
    }

    const leftScore =
      (left.badges.some((badge) => badge.label === 'Active') ? 100 : 0) +
      (left.lastLaunched ? 40 : 0) +
      (left.runtimeReady ? 20 : 0) -
      left.issueCount * 10;
    const rightScore =
      (right.badges.some((badge) => badge.label === 'Active') ? 100 : 0) +
      (right.lastLaunched ? 40 : 0) +
      (right.runtimeReady ? 20 : 0) -
      right.issueCount * 10;

    if (rightScore !== leftScore) {
      return rightScore - leftScore;
    }
    return right.profile.updated_at - left.profile.updated_at;
  });
}
