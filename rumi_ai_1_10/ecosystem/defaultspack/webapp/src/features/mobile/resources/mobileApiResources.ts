import { api } from "../../../lib/api";
import type { MobilePairingApprovePayload, MobilePairingReview, MobilePairingStatus } from "../../../lib/api";

export const mobileApiResources = {
  getPairingStatus: (pairingId: string): Promise<MobilePairingStatus> => api.getMobilePairingStatus(pairingId),
  getPairingReview: (pairingId: string): Promise<MobilePairingReview> => api.getMobilePairingReview(pairingId),
  approvePairing: (pairingId: string, payload: MobilePairingApprovePayload) => api.approveMobilePairing(pairingId, payload),
  rejectPairing: (pairingId: string, reason?: string) => api.rejectMobilePairing(pairingId, reason),
};

export type MobilePairingApi = typeof mobileApiResources;
export type { MobilePairingApprovePayload, MobilePairingReview, MobilePairingStatus };
