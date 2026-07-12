import { useMemo } from "react";

export type DiffLine = {
  kind: "add" | "delete" | "context" | "meta";
  text: string;
};

export type ParsedDiffFile = {
  path: string;
  oldPath?: string;
  lines: DiffLine[];
  binary?: boolean;
  additions: number;
  deletions: number;
};

function cleanDiffPath(value: string): string {
  return value.replace(/^[ab]\//, "").trim();
}

function filePathFromHeader(line: string): string {
  const match = /^diff --git a\/(.+?) b\/(.+)$/.exec(line);
  return match?.[2] ?? line.replace(/^diff --git\s+/, "").trim();
}

export function parseUnifiedDiff(diff: string): ParsedDiffFile[] {
  const files: ParsedDiffFile[] = [];
  let current: ParsedDiffFile | null = null;
  for (const line of diff.split(/\r?\n/)) {
    if (line.startsWith("diff --git ")) {
      current = { path: filePathFromHeader(line), lines: [{ kind: "meta", text: line }], additions: 0, deletions: 0 };
      files.push(current);
      continue;
    }
    if (!current) {
      if (!line.trim()) continue;
      current = { path: "working tree", lines: [], additions: 0, deletions: 0 };
      files.push(current);
    }
    if (line.startsWith("+++ ")) {
      const nextPath = cleanDiffPath(line.slice(4));
      if (nextPath && nextPath !== "/dev/null") current.path = nextPath;
      current.lines.push({ kind: "meta", text: line });
    } else if (line.startsWith("--- ")) {
      const oldPath = cleanDiffPath(line.slice(4));
      if (oldPath && oldPath !== "/dev/null") current.oldPath = oldPath;
      current.lines.push({ kind: "meta", text: line });
    } else if (line.startsWith("+")) {
      current.additions += 1;
      current.lines.push({ kind: "add", text: line });
    } else if (line.startsWith("-")) {
      current.deletions += 1;
      current.lines.push({ kind: "delete", text: line });
    } else if (line.startsWith("@@") || line.startsWith("index ") || line.startsWith("new file ") || line.startsWith("deleted file ")) {
      current.lines.push({ kind: "meta", text: line });
    } else {
      if (line.startsWith("Binary files ")) current.binary = true;
      current.lines.push({ kind: "context", text: line });
    }
  }
  return files;
}

function lineClass(kind: DiffLine["kind"]): string {
  if (kind === "add") return "bg-emerald-500/10 text-emerald-100";
  if (kind === "delete") return "bg-red-500/10 text-red-100";
  if (kind === "meta") return "bg-sky-500/10 text-sky-200";
  return "text-zinc-400";
}

export function DiffViewer({
  diff,
  selectedPath,
  emptyText = "No diff for this file",
}: {
  diff?: string | null;
  selectedPath?: string | null;
  emptyText?: string;
}) {
  const files = useMemo(() => parseUnifiedDiff(diff ?? ""), [diff]);
  const selectedFile = useMemo(() => {
    if (!selectedPath) return files[0] ?? null;
    return files.find((file) => file.path === selectedPath || file.oldPath === selectedPath) ?? files[0] ?? null;
  }, [files, selectedPath]);

  if (!diff?.trim()) {
    return (
      <div className="flex min-h-40 items-center justify-center rounded-md border border-zinc-800 bg-black/25 px-3 py-8 text-center text-[11px] text-zinc-600">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-zinc-800 bg-black/30">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-2 py-1.5">
        <span className="min-w-0 truncate font-mono text-[11px] text-zinc-300">{selectedFile?.path ?? "Diff"}</span>
        {selectedFile && (
          <span className="flex-shrink-0 font-mono text-[10px] text-zinc-600">
            +{selectedFile.additions} -{selectedFile.deletions}
          </span>
        )}
      </div>
      <pre className="max-h-[420px] overflow-auto p-0 font-mono text-[10px] leading-relaxed">
        {(selectedFile?.lines ?? []).map((line, index) => (
          <div key={`${index}:${line.text}`} className={`min-w-max px-2 ${lineClass(line.kind)}`}>
            {line.text || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}
