import { FolderPlus, RefreshCw, ShieldCheck } from "lucide-react";

import type { CodingWorkspaceRecord } from "../../lib/api";

export function CodingWorkspacePicker({
  workspaces,
  selectedWorkspaceId,
  disabled = false,
  busy = false,
  onSelect,
  onTrust,
  onCreate,
  onRefresh,
}: {
  workspaces: CodingWorkspaceRecord[];
  selectedWorkspaceId?: string | null;
  disabled?: boolean;
  busy?: boolean;
  onSelect?: (workspaceId: string) => void;
  onTrust?: (workspaceId: string) => void;
  onCreate?: () => void;
  onRefresh?: () => void;
}) {
  const selected = workspaces.find((workspace) => workspace.workspace_id === selectedWorkspaceId) ?? workspaces[0] ?? null;

  return (
    <div className="inline-flex min-w-0 items-center gap-1.5">
      <select
        value={selected?.workspace_id ?? ""}
        disabled={disabled || busy || workspaces.length === 0}
        onChange={(event) => event.target.value && onSelect?.(event.target.value)}
        className="h-6 max-w-[170px] rounded-md border border-zinc-800 bg-zinc-950/40 px-1.5 font-mono text-[11px] text-zinc-300 outline-none hover:border-zinc-700 disabled:opacity-50"
        title={selected?.root_path ?? "Coding workspace"}
      >
        {workspaces.map((workspace) => (
          <option key={workspace.workspace_id} value={workspace.workspace_id} className="bg-zinc-900 text-zinc-100">
            {workspace.label || workspace.workspace_id}
          </option>
        ))}
        {workspaces.length === 0 && <option value="">no workspace</option>}
      </select>
      {selected && !selected.trusted && onTrust && (
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => onTrust(selected.workspace_id)}
          className="flex h-6 w-6 items-center justify-center rounded-md text-amber-300 hover:bg-amber-500/10 disabled:opacity-40"
          title="Trust workspace"
        >
          <ShieldCheck size={12} />
        </button>
      )}
      {onRefresh && (
        <button
          type="button"
          disabled={disabled || busy}
          onClick={onRefresh}
          className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
          title="Refresh workspaces"
        >
          <RefreshCw size={12} />
        </button>
      )}
      {onCreate && (
        <button
          type="button"
          disabled={disabled || busy}
          onClick={onCreate}
          className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
          title="Add current workspace"
        >
          <FolderPlus size={12} />
        </button>
      )}
    </div>
  );
}
