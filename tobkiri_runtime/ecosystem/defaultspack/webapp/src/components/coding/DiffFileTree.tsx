import { ChevronRight, FileText, Folder } from "lucide-react";

import type { ChangeRequestFile } from "../../lib/changeRequests";

type FileTreeNode = {
  name: string;
  path: string;
  children: Map<string, FileTreeNode>;
  file?: ChangeRequestFile;
};

function makeRoot(): FileTreeNode {
  return { name: "", path: "", children: new Map() };
}

function addFile(root: FileTreeNode, file: ChangeRequestFile): void {
  const parts = file.path.split("/").filter(Boolean);
  let node = root;
  parts.forEach((part, index) => {
    const path = parts.slice(0, index + 1).join("/");
    let child = node.children.get(part);
    if (!child) {
      child = { name: part, path, children: new Map() };
      node.children.set(part, child);
    }
    node = child;
  });
  node.file = file;
}

function sortedNodes(node: FileTreeNode): FileTreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    if (a.file && !b.file) return 1;
    if (!a.file && b.file) return -1;
    return a.name.localeCompare(b.name);
  });
}

function badgeClass(file: ChangeRequestFile): string {
  if (file.highRisk) return "border-red-500/30 bg-red-500/10 text-red-200";
  if (file.untracked) return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-zinc-800 text-zinc-500";
}

function FileBadge({ label, className = "border-zinc-800 text-zinc-500" }: { label: string; className?: string }) {
  return <span className={`rounded border px-1 py-0.5 text-[9px] uppercase leading-none ${className}`}>{label}</span>;
}

function NodeRow({
  node,
  depth,
  selectedPath,
  viewed,
  onSelect,
  onViewedChange,
}: {
  node: FileTreeNode;
  depth: number;
  selectedPath?: string | null;
  viewed: Set<string>;
  onSelect: (path: string) => void;
  onViewedChange?: (path: string, nextViewed: boolean) => void;
}) {
  const isFile = Boolean(node.file);
  const selected = selectedPath === node.path;
  return (
    <div>
      <button
        type="button"
        onClick={() => isFile && onSelect(node.path)}
        className={`flex min-h-7 w-full items-center gap-1.5 rounded px-1.5 text-left ${
          selected ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-200"
        }`}
        style={{ paddingLeft: `${6 + depth * 12}px` }}
      >
        {isFile ? <FileText size={12} className="flex-shrink-0 text-zinc-500" /> : <Folder size={12} className="flex-shrink-0 text-zinc-500" />}
        <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{node.name}</span>
        {isFile && node.file && (
          <>
            {(node.file.additions || node.file.deletions) && (
              <span className="flex-shrink-0 font-mono text-[9px] text-zinc-600">
                +{node.file.additions ?? 0}/-{node.file.deletions ?? 0}
              </span>
            )}
            <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${viewed.has(node.path) ? "bg-emerald-400" : "bg-zinc-700"}`} title={viewed.has(node.path) ? "Viewed" : "Not viewed"} />
          </>
        )}
        {!isFile && <ChevronRight size={11} className="flex-shrink-0 rotate-90 text-zinc-600" />}
      </button>
      {isFile && node.file && (
        <div className="mb-1 flex flex-wrap gap-1 pl-7 pr-1" style={{ marginLeft: `${depth * 12}px` }}>
          {node.file.generated && <FileBadge label="Gen" />}
          {node.file.test && <FileBadge label="Test" />}
          {node.file.docs && <FileBadge label="Docs" />}
          {node.file.highRisk && <FileBadge label="Risk" className={badgeClass(node.file)} />}
          {node.file.untracked && <FileBadge label="New" className={badgeClass(node.file)} />}
          {node.file.binary && <FileBadge label="Bin" />}
          {node.file.large && <FileBadge label="Large" />}
          {onViewedChange && (
            <label className="ml-auto flex items-center gap-1 text-[10px] text-zinc-600">
              <input
                type="checkbox"
                checked={viewed.has(node.path)}
                onChange={(event) => onViewedChange(node.path, event.target.checked)}
                className="h-3 w-3 accent-zinc-200"
              />
              viewed
            </label>
          )}
        </div>
      )}
      {sortedNodes(node).map((child) => (
        <NodeRow
          key={child.path}
          node={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          viewed={viewed}
          onSelect={onSelect}
          onViewedChange={onViewedChange}
        />
      ))}
    </div>
  );
}

export function DiffFileTree({
  files,
  selectedPath,
  viewed,
  onSelect,
  onViewedChange,
}: {
  files: ChangeRequestFile[];
  selectedPath?: string | null;
  viewed: Set<string>;
  onSelect: (path: string) => void;
  onViewedChange?: (path: string, nextViewed: boolean) => void;
}) {
  const root = makeRoot();
  files.forEach((file) => addFile(root, file));
  const nodes = sortedNodes(root);
  if (nodes.length === 0) {
    return <p className="rounded-md border border-zinc-800 bg-black/20 px-2 py-4 text-center text-[11px] text-zinc-600">No files changed</p>;
  }
  return (
    <div className="max-h-[420px] overflow-auto rounded-md border border-zinc-800 bg-black/20 p-1">
      {nodes.map((node) => (
        <NodeRow
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          viewed={viewed}
          onSelect={onSelect}
          onViewedChange={onViewedChange}
        />
      ))}
    </div>
  );
}
