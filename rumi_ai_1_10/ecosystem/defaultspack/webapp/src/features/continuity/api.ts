import { api } from "../../lib/api";
import type {
  ContinuityHandoffOperation,
  ContinuityHandoffPlan,
  ContinuityHandoffRequest,
  ContinuityNode,
  ContinuityPairingStartResponse,
  ContinuityPreflightResult,
  ContinuityProviderRoute,
} from "../../lib/api";

export type {
  ContinuityHandoffOperation,
  ContinuityHandoffPlan,
  ContinuityHandoffRequest,
  ContinuityNode,
  ContinuityPairingStartResponse,
  ContinuityPreflightResult,
  ContinuityProviderRoute,
};

export const continuityApi = {
  listNodes() {
    return api.listContinuityNodes();
  },

  startPairing(displayName?: string) {
    return api.startContinuityPairing({ display_name: displayName });
  },

  acceptPairing(payload: Parameters<typeof api.acceptContinuityPairing>[0]) {
    return api.acceptContinuityPairing(payload);
  },

  probeNode(nodeId: string) {
    return api.probeContinuityNode(nodeId);
  },

  listProviderRoutes() {
    return api.listContinuityProviderRoutes();
  },

  probeProviderRoute(routeId: string, destinationNodeId?: string) {
    return api.probeContinuityProviderRoute(routeId, { destination_node_id: destinationNodeId });
  },

  planHandoff(payload: ContinuityHandoffRequest) {
    return api.planContinuityHandoff(payload);
  },

  listHandoffs() {
    return api.listContinuityHandoffs();
  },

  cancelHandoff(operationId: string) {
    return api.cancelContinuityHandoff(operationId);
  },
};
