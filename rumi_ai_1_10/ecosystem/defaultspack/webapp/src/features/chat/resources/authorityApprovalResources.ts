import { api, type AuthorityApprovalDecision, type AuthorityRequest, type AuthorityRequestsResponse, type AuthorityUiOperator } from "../../../lib/api";
import type { AuthorityApprovalScope } from "../../../lib/authorityApproval";

export const authorityApprovalResources = {
  listAuthorityRequests(options?: { status?: string }) {
    return api.listAuthorityRequests(options) as Promise<AuthorityRequestsResponse>;
  },

  getAuthorityRequest(requestId: string) {
    return api.getAuthorityRequest(requestId) as Promise<AuthorityRequest>;
  },

  approveAuthorityApproval(
    requestId: string,
    options: {
      scope: AuthorityApprovalScope;
      config: Record<string, unknown>;
      related_permissions?: string[];
      ui_operator: AuthorityUiOperator;
    },
  ) {
    return api.approveAuthorityApproval(requestId, options) as Promise<AuthorityApprovalDecision>;
  },

  denyAuthorityApproval(
    requestId: string,
    options: {
      reason: string;
      persist: boolean;
      ui_operator: AuthorityUiOperator;
    },
  ) {
    return api.denyAuthorityApproval(requestId, options);
  },

  sendAuthorityResume(
    conversationId: string,
    text: string,
    metadata: Record<string, unknown>,
  ) {
    return api.sendMessage(conversationId, text, { metadata });
  },
};

export type { AuthorityApprovalDecision, AuthorityRequest, AuthorityRequestsResponse, AuthorityUiOperator };
