import type { AuthorityApproval } from "../lib/authorityApproval";
import { authorityApprovalViewModel } from "../lib/approvalPresentation";
import { ApprovalDecisionSurface } from "./ApprovalDecisionSurface";

type AuthorityApprovalNoticeProps = {
  approval: AuthorityApproval;
  title: string;
  onOpen: () => void;
};

export function AuthorityApprovalNotice({ approval, title, onOpen }: AuthorityApprovalNoticeProps) {
  return (
    <ApprovalDecisionSurface
      approval={authorityApprovalViewModel(approval, title)}
      onOpenTrustedWindow={onOpen}
      className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 max-h-[min(70vh,620px)] w-[min(620px,calc(100vw-24px))] -translate-x-1/2 overflow-y-auto"
    />
  );
}
