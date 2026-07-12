import { api } from "../../../lib/api";
import type { MobileDevice, MobileDevicesResponse } from "../../../lib/api";

export const mobileApiResources = {
  listDevices(): Promise<MobileDevicesResponse> {
    return api.listMobileDevices();
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
  MobileDevice,
  MobileDevicesResponse,
};
