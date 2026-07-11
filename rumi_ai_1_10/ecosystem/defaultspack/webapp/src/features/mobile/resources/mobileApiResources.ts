import { api } from "../../../lib/api";
import type {
  MobilePairingApprovePayload,
  MobilePairingReview,
  MobilePairingStatus,
  MobileDevice,
  MobileDevicesResponse,
  P2PPairing,
} from "../../../lib/api";

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

  getPairingReview(pairingId: string): Promise<MobilePairingReview> {
    return api.getMobilePairingReview(pairingId);
  },

  approvePairing(pairingId: string, payload: MobilePairingApprovePayload) {
    return api.approveMobilePairing(pairingId, payload);
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

  createCredentialTransfer(payload: { device_id: string; provider_id: string; api_id: string; provider_label?: string }) {
    return api.createCredentialTransfer(payload);
  },

  confirmCredentialTransfer(transferId: string, payload: { device_id: string; provider_id: string; api_id: string; user_confirmed: true }) {
    return api.confirmCredentialTransfer(transferId, payload);
  },

  getCredentialTransferStatus(transferId: string) {
    return api.getCredentialTransferStatus(transferId);
  },

  cancelCredentialTransfer(transferId: string) {
    return api.cancelCredentialTransfer(transferId);
  },

  revokeCredentialTransfer(transferId: string) {
    return api.revokeCredentialTransfer(transferId);
  },

};

export type {
  MobilePairingApprovePayload,
  MobilePairingReview,
  MobilePairingStatus,
  MobileDevice,
  MobileDevicesResponse,
  P2PPairing,
};
