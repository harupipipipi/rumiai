import { CheckCircle2 } from "lucide-react";
import { useRef, useState } from "react";

import type { AuthorityApproval } from "../lib/authorityApproval";
import { cn } from "../lib/cn";

type AuthorityApprovalScope = "once" | "conversation" | "profile" | "node";

type AuthorityApprovalCardProps = {
  approval: AuthorityApproval;
  title: string;
  onApprove: (scope: AuthorityApprovalScope) => Promise<void> | void;
  onDeny: () => void;
};

const AUTHORITY_SCOPE_OPTIONS: Array<[AuthorityApprovalScope, string]> = [
  ["once", "今回のみ"],
  ["conversation", "会話"],
  ["profile", "Profile"],
  ["node", "Node"],
];

export function AuthorityApprovalCard({ approval, title, onApprove, onDeny }: AuthorityApprovalCardProps) {
  const approvingRef = useRef(false);
  const [approvingScope, setApprovingScope] = useState<AuthorityApprovalScope | null>(null);
  const scopeOptions = AUTHORITY_SCOPE_OPTIONS.filter(([scope]) => {
    if (scope === "node") return approval.principalId.includes("__node:");
    if (scope === "profile") return approval.principalId.startsWith("profile:");
    return true;
  });
  const isApproving = approvingScope !== null;
  const approve = (scope: AuthorityApprovalScope) => {
    if (approvingRef.current) return;
    approvingRef.current = true;
    setApprovingScope(scope);
    void Promise.resolve().then(() => onApprove(scope)).finally(() => {
      approvingRef.current = false;
      setApprovingScope(null);
    });
  };

  return (
    <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-xl border border-sky-500/30 bg-zinc-950 p-3 shadow-2xl">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn(
              "shrink-0 rounded border px-1.5 py-0.5 text-[10px]",
              approval.riskLevel === "high"
                ? "border-red-500/30 bg-red-500/10 text-red-200"
                : "border-sky-500/30 bg-sky-500/10 text-sky-200",
            )}>
              {approval.riskLevel ?? "authority"}
            </span>
            <p className="truncate text-sm font-medium text-zinc-100">{title} の使用許可が必要です</p>
          </div>
          {approval.summary && (
            <p className="mt-1 truncate text-[11px] text-zinc-500">{approval.summary}</p>
          )}
          <details className="mt-1 text-[11px] text-zinc-500">
            <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">resource を表示</summary>
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
              {JSON.stringify(approval.resource, null, 2)}
            </pre>
          </details>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          <button
            type="button"
            onPointerDown={(event) => {
              event.preventDefault();
              if (!isApproving) onDeny();
            }}
            onClick={() => {
              if (!isApproving) onDeny();
            }}
            disabled={isApproving}
            className="h-8 rounded-lg border border-zinc-800 px-3 text-xs font-semibold text-zinc-400 transition hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            拒否
          </button>
          {scopeOptions.map(([scope, label]) => (
            <button
              key={scope}
              type="button"
              onPointerDown={(event) => {
                event.preventDefault();
                approve(scope);
              }}
              onClick={() => approve(scope)}
              disabled={isApproving}
              className={cn(
                "h-8 rounded-lg px-3 text-xs font-semibold transition disabled:cursor-not-allowed",
                approvingScope === scope
                  ? "bg-emerald-300 text-emerald-950 shadow-[0_0_0_3px_rgba(52,211,153,0.18)]"
                  : "bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-50",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {isApproving && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-emerald-500/10 backdrop-blur-[1px]" aria-live="polite">
          <span className="absolute h-14 w-14 rounded-full bg-emerald-300/20 animate-ping" />
          <span className="relative inline-flex items-center gap-2 rounded-full border border-emerald-300/40 bg-emerald-500/20 px-3 py-2 text-sm font-semibold text-emerald-100 shadow-2xl">
            <CheckCircle2 size={18} className="text-emerald-200" />
            許可しました
          </span>
        </div>
      )}
    </div>
  );
}
