import type {
  ApiCapabilityNode,
  ApiCapabilityProfile,
  ApiStartupProfile,
} from './apiTypes';
import {capabilityNodeLabel} from './nodeCatalog';

export type CapabilityPackGroup = {
  packId: string;
  nodes: ApiCapabilityNode[];
  enabledCount: number;
  readyCount: number;
};

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
}

export function capabilityPackId(node: ApiCapabilityNode): string {
  const fromMetadata = node.metadata?.pack_id;
  if (typeof fromMetadata === 'string' && fromMetadata.trim()) return fromMetadata;
  return node.node_id.split('.')[0] ?? 'unknown';
}

export function capabilityDomains(node: ApiCapabilityNode): string[] {
  const metadata = recordValue(node.metadata);
  const requirements = recordValue(node.requirements);
  const permissions = recordValue(node.permissions);
  const requirementNetwork = recordValue(requirements.network);
  const permissionNetwork = recordValue(permissions.network);
  return [...new Set([
    ...stringList(metadata.allowed_domains),
    ...stringList(metadata.network_domains),
    ...stringList(requirementNetwork.domains),
    ...stringList(requirementNetwork.allowed_domains),
    ...stringList(permissionNetwork.domains),
    ...stringList(permissionNetwork.allowed_domains),
  ])].sort();
}

export function capabilityProfileForStartup(
  startupProfile: ApiStartupProfile | null,
  capabilityProfiles: ApiCapabilityProfile[],
): string {
  const candidates = [
    startupProfile?.capability_profile_id,
    startupProfile?.default_graph,
    startupProfile?.graph_id,
  ].filter((value): value is string => Boolean(value));
  return candidates.find((candidate) => (
    capabilityProfiles.some((profile) => profile.profile_id === candidate)
  )) ?? capabilityProfiles[0]?.profile_id ?? '';
}

/** Groups one catalog pass at a time, avoiding repeated array copies for large Packs. */
export function buildCapabilityPackGroups(nodes: ApiCapabilityNode[]): CapabilityPackGroup[] {
  const groups = new Map<string, ApiCapabilityNode[]>();
  for (const node of nodes) {
    const packId = capabilityPackId(node);
    const packNodes = groups.get(packId);
    if (packNodes) {
      packNodes.push(node);
    } else {
      groups.set(packId, [node]);
    }
  }

  return [...groups.entries()]
    .map(([packId, packNodes]) => ({
      packId,
      nodes: packNodes.sort((left, right) => capabilityNodeLabel(left).localeCompare(capabilityNodeLabel(right))),
      enabledCount: packNodes.filter((node) => node.state?.enabled).length,
      readyCount: packNodes.filter((node) => node.state?.status === 'ready').length,
    }))
    .sort((left, right) => left.packId.localeCompare(right.packId));
}

/** A request token makes it safe to ignore an older profile response after a profile switch. */
export class LatestRequestToken {
  private current = 0;

  begin(): number {
    this.current += 1;
    return this.current;
  }

  isCurrent(token: number): boolean {
    return token === this.current;
  }

  invalidate(): void {
    this.current += 1;
  }
}
