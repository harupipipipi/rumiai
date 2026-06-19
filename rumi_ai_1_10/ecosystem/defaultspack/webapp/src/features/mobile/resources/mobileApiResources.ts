import { api } from "../../../lib/api";
import type { MobilePairingStatus, MobileDevice, MobileDevicesResponse, CredentialTransferPayload, P2PPairing } from "../../../lib/api";

export const mobileApiResources = {
  startPairing(payload?: {
    peer_id?: string;
    peer_fingerprint?: string;
    peer_label?: string;
    ttl_seconds?: number;
    capabilities?: string[];
    allowed_company_ids?: string[];
  }) {
    return api.startP2PPairing(payload);
  },

  getPairingStatus(pairingId: string): Promise<MobilePairingStatus> {
    return api.getMobilePairingStatus(pairingId);
  },

  approvePairing(pairingId: string) {
    return api.approveMobilePairing(pairingId);
  },

  rejectPairing(pairingId: string, reason?: string) {
    return api.rejectMobilePairing(pairingId, reason);
  },

  listDevices(): Promise<MobileDevicesResponse> {
    return api.listMobileDevices();
  },

  revokeDevice(deviceId: string) {
    return api.revokeMobileDevice(deviceId);
  },

  createCredentialTransfer(payload: CredentialTransferPayload) {
    return api.createCredentialTransfer(payload);
  },
};

export type { MobilePairingStatus, MobileDevice, MobileDevicesResponse, CredentialTransferPayload, P2PPairing };
