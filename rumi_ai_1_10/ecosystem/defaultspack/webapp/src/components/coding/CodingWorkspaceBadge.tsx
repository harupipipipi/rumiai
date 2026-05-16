import { FolderCheck, ShieldCheck, ShieldQuestion } from "lucide-react";

import type { CodingWorkspaceRecord } from "../../lib/api";

export function CodingWorkspaceBadge({
  workspace,
  compact = false,
}: {
  workspace?: CodingWorkspaceRecord | null;
  compact?: boolean;
}) {
  if (!workspace) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/50 px-2 py-0.5 text-[11px] text-zinc-500">
        <FolderCheck size={11} />
        no workspace
      </span>
    );
  }

  return (
    <span
      className="inline-flex min-w-0 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/50 px-2 py-0.5 text-[11px] text-zinc-300"
      title={workspace.root_path}
    >
      {workspace.trusted ? <ShieldCheck size={11} className="text-emerald-300" /> : <ShieldQuestion size={11} className="text-amber-300" />}
      <span className={compact ? "max-w-[110px] truncate" : "max-w-[180px] truncate"}>{workspace.label || workspace.workspace_id}</span>
    </span>
  );
}
