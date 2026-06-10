import type { AuthorityApproval } from "../lib/authorityApproval";
import { cn } from "../lib/cn";

type AuthorityApprovalScope = "once" | "conversation" | "profile" | "node";

type AuthorityApprovalCardProps = {
  approval: AuthorityApproval;
  title: string;
  onApprove: (scope: AuthorityApprovalScope) => void;
  onDeny: () => void;
};

const AUTHORITY_SCOPE_OPTIONS: Array<[AuthorityApprovalScope, string]> = [
  ["once", "今回のみ"],
  ["conversation", "会話"],
  ["profile", "Profile"],
  ["node", "Node"],
];

export function AuthorityApprovalCard({ approval, title, onApprove, onDeny }: AuthorityApprovalCardProps) {
  const scopeOptions = AUTHORITY_SCOPE_OPTIONS.filter(([scope]) => {
    if (scope === "node") return approval.principalId.includes("__node:");
    if (scope === "profile") return approval.principalId.startsWith("profile:");
    return true;
  });

  return (
    <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-sky-500/30 bg-zinc-950 p-3 shadow-2xl">
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
              onDeny();
            }}
            onClick={onDeny}
            className="h-8 rounded-lg border border-zinc-800 px-3 text-xs font-semibold text-zinc-400 hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-200"
          >
            拒否
          </button>
          {scopeOptions.map(([scope, label]) => (
            <button
              key={scope}
              type="button"
              onPointerDown={(event) => {
                event.preventDefault();
                onApprove(scope);
              }}
              onClick={() => onApprove(scope)}
              className="h-8 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
