import { ExternalLink, ShieldAlert } from "lucide-react";

import { authorityApprovalRiskTone, type AuthorityApproval } from "../lib/authorityApproval";
import { cn } from "../lib/cn";

type AuthorityApprovalNoticeProps = {
  approval: AuthorityApproval;
  title: string;
  onOpen: () => void;
};

export function AuthorityApprovalNotice({ approval, title, onOpen }: AuthorityApprovalNoticeProps) {
  return (
    <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-sky-500/30 bg-zinc-950 p-3 shadow-2xl">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded border",
              authorityApprovalRiskTone(approval.riskLevel),
            )}>
              <ShieldAlert size={14} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-100">{title} の承認待ち</p>
              <p className="truncate text-[11px] text-zinc-500">
                {approval.summary || approval.reason || "専用の承認ウィンドウで確認してください。"}
              </p>
            </div>
          </div>
          <details className="mt-2 text-[11px] text-zinc-500">
            <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">request details</summary>
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
              {JSON.stringify({
                request_id: approval.requestId,
                principal_id: approval.principalId,
                permission_id: approval.permissionId,
                risk_level: approval.riskLevel,
                resource: approval.resource,
              }, null, 2)}
            </pre>
          </details>
        </div>
        <button
          type="button"
          onPointerDown={(event) => {
            event.preventDefault();
          }}
          onClick={onOpen}
          className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
          title="承認ウィンドウを開く"
        >
          <ExternalLink size={13} />
          開く
        </button>
      </div>
    </div>
  );
}
