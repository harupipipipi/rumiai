import type {
  ApiCapabilityNode,
  ApiCapabilityPort,
  ApiCapabilityProfile,
  CapabilityProfileNodesResponseData,
} from './apiTypes';

type LocalizedText = Record<string, string> | string | null | undefined;

export interface NormalizedCapabilityProfileNodes {
  profile: ApiCapabilityProfile | null;
  nodes: ApiCapabilityNode[];
  paletteNodes: ApiCapabilityNode[];
}

type CapabilityProfileNodesPayload = Partial<CapabilityProfileNodesResponseData> & {
  profile_id?: string;
  nodes?: ApiCapabilityNode[] | null;
  palette_nodes?: ApiCapabilityNode[] | null;
};

function localizedText(value: LocalizedText, fallback: string, locale = 'en'): string {
  if (typeof value === 'string' && value) {
    return value;
  }
  if (value && typeof value === 'object') {
    return value[locale] || value.en || value.ja || fallback;
  }
  return fallback;
}

export function capabilityNodeLabel(node: ApiCapabilityNode): string {
  return node.label || localizedText(node.display_name, node.node_id);
}

export function capabilityNodeDescription(node: ApiCapabilityNode): string {
  return node.description_label || localizedText(node.description, '');
}

export function capabilityNodePorts(node: ApiCapabilityNode): ApiCapabilityPort[] {
  return Array.isArray(node.ports) ? node.ports : [];
}

export function capabilityPortLabel(port: ApiCapabilityPort): string {
  return port.label || localizedText(port.display_name, port.id);
}

export function capabilityPortStandards(port: ApiCapabilityPort): string[] {
  return Array.isArray(port.standards) ? port.standards : [];
}

export function normalizeCapabilityProfileNodes(
  payload: CapabilityProfileNodesPayload,
  fallbackProfile: ApiCapabilityProfile | null = null,
): NormalizedCapabilityProfileNodes {
  const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
  const profile = payload.profile ?? fallbackProfile;

  if (Array.isArray(payload.palette_nodes)) {
    return {
      profile,
      nodes,
      paletteNodes: payload.palette_nodes,
    };
  }

  const hasNodeState = nodes.some(node => node.state !== undefined);
  const paletteNodes = hasNodeState
    ? nodes.filter(node => node.state?.enabled === true && node.state?.installed === true)
    : nodes;

  return {
    profile,
    nodes,
    paletteNodes,
  };
}
