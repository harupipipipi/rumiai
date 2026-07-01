import type {
  ApiStartupCatalog,
  ApiStartupGraphPort,
  ApiStartupNodeDefinition,
  ApiStartupNodePort,
  ApiStartupPack,
  ApiStartupProfile,
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

export interface StartupProfilePortSummary {
  healthy: boolean;
  label: string;
  portKey: string;
  resolvedNode: string;
  targetStandards: string[];
}

export interface StartupProfileView {
  badges: StartupProfileBadge[];
  basePack: ApiStartupPack | null;
  headline: string;
  issueCount: number;
  issues: StartupProfileIssue[];
  lastLaunched: boolean;
  packs: ApiStartupPack[];
  ports: StartupProfilePortSummary[];
  profile: ApiStartupProfile;
  runtimeReady: boolean;
  subtitle: string;
}

export type StartupPackRole = 'base' | 'frontend' | 'tool';

export interface StartupPackRoleOptions {
  basePacks: ApiStartupPack[];
  frontendPacks: ApiStartupPack[];
  toolPacks: ApiStartupPack[];
}

export type StartupProfilePatch = Partial<Pick<
  ApiStartupProfile,
  'base_pack' | 'graph_id' | 'packs' | 'node_overrides'
>>;

function sentenceCase(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function displayName(value?: Record<string, string>, fallback = ''): string {
  return value?.en || value?.ja || Object.values(value ?? {})[0] || fallback;
}

export function packLabel(pack: ApiStartupPack | null | undefined, fallback = ''): string {
  return pack?.name || fallback || 'Unavailable';
}

function portLabel(port: ApiStartupGraphPort): string {
  const target = port.target_port;
  return displayName(target?.display_name, port.port_key);
}

function portStandards(port: ApiStartupNodePort | undefined): string[] {
  return [...(port?.standards ?? port?.contracts ?? [])];
}

function nodeOutputPorts(node: ApiStartupNodeDefinition): ApiStartupNodePort[] {
  return (node.ports ?? []).filter((port) => port.direction === 'output');
}

function nodeMetadataString(node: ApiStartupNodeDefinition, key: string): string {
  const value = node.metadata?.[key];
  return typeof value === 'string' ? value : '';
}

function nodeComponentType(node: ApiStartupNodeDefinition): string {
  return (node.component_type || nodeMetadataString(node, 'component_type')).toLowerCase();
}

function nodeKind(node: ApiStartupNodeDefinition): string {
  return (node.kind || '').toLowerCase();
}

function nodeOutputStandards(node: ApiStartupNodeDefinition): string[] {
  return nodeOutputPorts(node).flatMap((port) => portStandards(port));
}

function hasOutputStandard(node: ApiStartupNodeDefinition, predicate: (standard: string) => boolean): boolean {
  return nodeOutputStandards(node).some((standard) => predicate(standard.toLowerCase()));
}

function isFrontendStandard(standard: string): boolean {
  return standard === 'rumi.surface' || standard.startsWith('rumi.surface.') || standard === 'rumi.frontend';
}

function isToolBundleStandard(standard: string): boolean {
  return standard === 'rumi.tool.bundle';
}

export function isStartupBasePack(pack: ApiStartupPack): boolean {
  return pack.graphs.length > 0;
}

export function isStartupFrontendNode(node: ApiStartupNodeDefinition): boolean {
  const componentType = nodeComponentType(node);
  const kind = nodeKind(node);
  return (
    componentType === 'frontend' ||
    componentType === 'surface' ||
    kind.includes('surface') ||
    hasOutputStandard(node, isFrontendStandard)
  );
}

export function isStartupFrontendPack(pack: ApiStartupPack): boolean {
  return pack.nodes.some(isStartupFrontendNode);
}

export function isStartupToolNode(node: ApiStartupNodeDefinition): boolean {
  const componentType = nodeComponentType(node);
  const kind = nodeKind(node);
  return componentType === 'tool' || kind.includes('tool') || hasOutputStandard(node, isToolBundleStandard);
}

export function isStartupToolPack(pack: ApiStartupPack): boolean {
  return pack.nodes.some(isStartupToolNode);
}

export function startupPacksByRole(catalog: ApiStartupCatalog | null): StartupPackRoleOptions {
  const packs = catalog?.packs.filter((pack) => pack.available) ?? [];
  return {
    basePacks: packs.filter(isStartupBasePack),
    frontendPacks: packs.filter(isStartupFrontendPack),
    toolPacks: packs.filter(isStartupToolPack),
  };
}

export function startupPacksForRole(catalog: ApiStartupCatalog | null, role: StartupPackRole): ApiStartupPack[] {
  const options = startupPacksByRole(catalog);
  if (role === 'base') return options.basePacks;
  if (role === 'frontend') return options.frontendPacks;
  return options.toolPacks;
}

export function isNodeCompatibleWithGraphPort(node: ApiStartupNodeDefinition, graphPort: ApiStartupGraphPort): boolean {
  const required = new Set(portStandards(graphPort.target_port));
  if (required.size === 0) return false;
  return nodeOutputPorts(node).some((port) =>
    portStandards(port).some((standard) => required.has(standard)),
  );
}

export function compatibleNodesForPort(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  graphPort: ApiStartupGraphPort,
): ApiStartupNodeDefinition[] {
  const compatibleById = new Map<string, ApiStartupNodeDefinition>();
  catalog.packs
    .filter((pack) => pack.available && profile.packs.includes(pack.pack_id))
    .flatMap((pack) => pack.nodes)
    .filter((node) => isNodeCompatibleWithGraphPort(node, graphPort))
    .forEach((node) => {
      if (!compatibleById.has(node.node_id)) {
        compatibleById.set(node.node_id, node);
      }
    });
  return [...compatibleById.values()].sort((left, right) => left.node_id.localeCompare(right.node_id));
}

function graphPortStandards(graphPort: ApiStartupGraphPort): string[] {
  return portStandards(graphPort.target_port).map((standard) => standard.toLowerCase());
}

export function isStartupFrontendGraphPort(graphPort: ApiStartupGraphPort): boolean {
  return (
    graphPortStandards(graphPort).some(isFrontendStandard) ||
    /(^|[._-])(frontend|surface)([._-]|$)/i.test(graphPort.port_key)
  );
}

function uniquePackIds(packIds: string[]): string[] {
  return [...new Set(packIds.filter(Boolean))];
}

function packContainsNode(pack: ApiStartupPack, nodeId: string): boolean {
  return pack.nodes.some((node) => node.node_id === nodeId);
}

function selectedPackContainsNode(catalog: ApiStartupCatalog, profile: ApiStartupProfile, nodeId: string): boolean {
  const selected = new Set(profile.packs);
  return catalog.packs.some((pack) => selected.has(pack.pack_id) && pack.available && packContainsNode(pack, nodeId));
}

function compatibleFrontendNodesForPort(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  graphPort: ApiStartupGraphPort,
): ApiStartupNodeDefinition[] {
  return compatibleNodesForPort(catalog, profile, graphPort).filter(isStartupFrontendNode);
}

function compatibleFrontendNodeFromPack(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  graphPort: ApiStartupGraphPort,
  packId: string,
): ApiStartupNodeDefinition | null {
  const pack = catalog.packs.find((item) => item.pack_id === packId && item.available);
  if (!pack || !profile.packs.includes(packId)) return null;
  return (
    pack.nodes
      .filter(isStartupFrontendNode)
      .find((node) => isNodeCompatibleWithGraphPort(node, graphPort)) ?? null
  );
}

function reconcileNodeOverridesForSelectedPacks(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  preferredFrontendPackId: string | null,
): Record<string, string> {
  const overrides = { ...profile.node_overrides };
  const preferredFrontendPack = preferredFrontendPackId
    ? catalog.packs.find((pack) => pack.pack_id === preferredFrontendPackId && isStartupFrontendPack(pack))
    : null;

  profile.graph_ports.forEach((graphPort) => {
    const portKey = graphPort.port_key;
    const currentOverride = overrides[portKey];
    const compatibleNodes = compatibleNodesForPort(catalog, profile, graphPort);
    const currentIsCompatible =
      Boolean(currentOverride) &&
      selectedPackContainsNode(catalog, profile, currentOverride) &&
      compatibleNodes.some((node) => node.node_id === currentOverride);

    if (!currentIsCompatible && currentOverride) {
      delete overrides[portKey];
    }

    if (!isStartupFrontendGraphPort(graphPort)) {
      return;
    }

    const preferredNode = preferredFrontendPack
      ? compatibleFrontendNodeFromPack(catalog, profile, graphPort, preferredFrontendPack.pack_id)
      : null;
    if (preferredNode) {
      overrides[portKey] = preferredNode.node_id;
      return;
    }

    if (currentOverride && !currentIsCompatible) {
      const fallbackNode = compatibleFrontendNodesForPort(catalog, profile, graphPort)[0];
      if (fallbackNode) {
        overrides[portKey] = fallbackNode.node_id;
      }
    }
  });

  return overrides;
}

export function buildStartupProfilePackSelectionPatch(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  selectedPackIds: string[],
  options: { preferredFrontendPackId?: string | null } = {},
): StartupProfilePatch {
  const packs = uniquePackIds([profile.base_pack, ...selectedPackIds]);
  const nextProfile = { ...profile, packs };
  return {
    packs,
    node_overrides: reconcileNodeOverridesForSelectedPacks(
      catalog,
      nextProfile,
      options.preferredFrontendPackId ?? null,
    ),
  };
}

export function buildAddStartupProfilePackPatch(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  packId: string,
): StartupProfilePatch {
  const pack = catalog.packs.find((item) => item.pack_id === packId);
  return buildStartupProfilePackSelectionPatch(catalog, profile, [...profile.packs, packId], {
    preferredFrontendPackId: pack && isStartupFrontendPack(pack) ? packId : null,
  });
}

export function buildRemoveStartupProfilePackPatch(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  packId: string,
): StartupProfilePatch {
  if (packId === profile.base_pack) {
    return buildStartupProfilePackSelectionPatch(catalog, profile, profile.packs);
  }
  return buildStartupProfilePackSelectionPatch(
    catalog,
    profile,
    profile.packs.filter((selectedPackId) => selectedPackId !== packId),
  );
}

export function buildSetStartupProfileBasePackPatch(
  catalog: ApiStartupCatalog,
  profile: ApiStartupProfile,
  basePackId: string,
): StartupProfilePatch {
  const basePack = catalog.packs.find((pack) => pack.pack_id === basePackId);
  const graphId = basePack?.graphs[0]?.graph_id ?? profile.graph_id;
  const packs = uniquePackIds([basePackId, ...profile.packs]);
  const nextProfile = { ...profile, base_pack: basePackId, graph_id: graphId, packs };
  return {
    base_pack: basePackId,
    graph_id: graphId,
    packs,
    node_overrides: reconcileNodeOverridesForSelectedPacks(catalog, nextProfile, null),
  };
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
  if (/Too many requests|429/i.test(error)) {
    return 'The local panel is receiving too many requests right now. Wait a moment and try again.';
  }
  if (/At least one startup profile must remain/i.test(error)) {
    return 'You need to keep at least one saved profile.';
  }
  if (/base_pack is required/i.test(error)) {
    return 'Choose a base pack before creating this profile.';
  }
  if (/Base pack .* not available|Unknown base pack/i.test(error)) {
    return 'The selected base pack is unavailable. Repair or switch the pack before saving.';
  }
  if (/does not satisfy port/i.test(error) || /Required standards/i.test(error)) {
    return 'That node does not provide the standard required by this graph port.';
  }
  if (/Component binding conflict/i.test(error)) {
    return 'This profile selects multiple components for the same runtime binding. Remove the conflicting override.';
  }
  if (/Runtime handoff is unavailable/i.test(error)) {
    return 'Launch could not hand off to the runtime. Restart the kernel and try again.';
  }
  return error || `We could not ${fallbackAction}.`;
}

function resolveProfileIssues(
  profile: ApiStartupProfile,
  catalog: ApiStartupCatalog,
): {
  basePack: ApiStartupPack | null;
  issues: StartupProfileIssue[];
  packs: ApiStartupPack[];
  ports: StartupProfilePortSummary[];
} {
  const byId = new Map(catalog.packs.map((pack) => [pack.pack_id, pack]));
  const basePack = byId.get(profile.base_pack) ?? null;
  const packs = profile.packs.map((packId) => byId.get(packId)).filter((pack): pack is ApiStartupPack => Boolean(pack));
  const issues: StartupProfileIssue[] = [];

  if (!basePack) {
    issues.push({
      title: 'Base pack unavailable',
      description: `${profile.base_pack || 'The selected base pack'} is not installed in this workspace.`,
      severity: 'danger',
    });
  } else if (!basePack.available) {
    (basePack.approval_issues.length ? basePack.approval_issues : ['Base pack is not available']).forEach((issue) => {
      issues.push(describeStartupIssue(issue, packLabel(basePack)));
    });
  }

  profile.packs.forEach((packId) => {
    const pack = byId.get(packId);
    if (!pack) {
      issues.push({
        title: 'Pack unavailable',
        description: `${packId} is not installed in this workspace.`,
        severity: 'danger',
      });
      return;
    }
    if (!pack.available) {
      (pack.approval_issues.length ? pack.approval_issues : [`Pack '${packId}' is disabled`]).forEach((issue) => {
        issues.push(describeStartupIssue(issue, packLabel(pack)));
      });
    }
  });

  const ports = profile.graph_ports.map((port) => {
    const resolvedNode = profile.node_overrides[port.port_key] || port.source_node_ref || port.source_ref;
    const compatible = compatibleNodesForPort(catalog, profile, port);
    const healthy = compatible.some((node) => node.node_id === resolvedNode);
    if (!healthy) {
      issues.push({
        title: `${portLabel(port)} needs a compatible node`,
        description: `Choose a node that provides ${portStandards(port.target_port).join(', ') || 'the required standard'}.`,
        severity: 'warning',
      });
    }
    return {
      portKey: port.port_key,
      label: portLabel(port),
      resolvedNode,
      targetStandards: portStandards(port.target_port),
      healthy,
    };
  });

  return { basePack, issues, packs, ports };
}

export function buildStartupProfileView(
  profile: ApiStartupProfile,
  catalog: ApiStartupCatalog,
  activeProfileId: string | null,
  lastLaunchedProfileId: string | null,
): StartupProfileView {
  const { basePack, issues, packs, ports } = resolveProfileIssues(profile, catalog);
  const active = activeProfileId === profile.profile_id;
  const lastLaunched = lastLaunchedProfileId === profile.profile_id;
  const runtimeReady = issues.length === 0;
  const badges: StartupProfileBadge[] = [];

  if (active) badges.push({ label: 'Active', tone: 'accent' });
  if (lastLaunched) badges.push({ label: 'Last Played', tone: 'neutral' });
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
    ? `${packLabel(basePack, profile.base_pack)} • ${packs.length} pack${packs.length === 1 ? '' : 's'} • ${ports.length} graph ports`
    : issues[0]?.description || `${packLabel(basePack, profile.base_pack)} needs attention.`;

  return {
    profile,
    basePack,
    packs,
    runtimeReady,
    issueCount: issues.length,
    issues,
    badges,
    headline,
    subtitle,
    ports,
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
          packLabel(profile.basePack, profile.profile.base_pack),
          ...profile.packs.map((pack) => `${pack.pack_id} ${packLabel(pack)}`),
          ...profile.ports.map((port) => `${port.label} ${port.resolvedNode} ${port.portKey}`),
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(normalizedQuery);
      })
    : profiles;

  return [...filtered].sort((left, right) => {
    if (sortMode === 'name') return left.profile.name.localeCompare(right.profile.name);
    if (sortMode === 'recent') return right.profile.updated_at - left.profile.updated_at;

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

    if (rightScore !== leftScore) return rightScore - leftScore;
    return right.profile.updated_at - left.profile.updated_at;
  });
}

export function defaultBasePack(catalog: ApiStartupCatalog | null): ApiStartupPack | null {
  return catalog?.packs.find((pack) => pack.available && pack.graphs.length > 0) ?? null;
}

export function titleCasePortKey(portKey: string): string {
  return sentenceCase(portKey.replace(/[._-]+/g, ' '));
}
