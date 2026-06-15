import { useMemo, useState } from "react";

import type { CodingDiffResponse, CodingGitStatus } from "../../lib/api";
import type { ChangeRequestFile } from "../../lib/changeRequests";
import { DiffFileTree } from "./DiffFileTree";
import { DiffViewer, parseUnifiedDiff } from "./DiffViewer";

const GENERATED_RE = /(^|\/)(dist|build|coverage|node_modules|\.next|target|__generated__|generated)(\/|$)|(\.lock$|package-lock\.json$|pnpm-lock\.yaml$|yarn\.lock$)/i;
const TEST_RE = /(^|\/)(__tests__|tests?|specs?)(\/|$)|(\.|-)(test|spec)\.[cm]?[tj]sx?$/i;
const DOCS_RE = /(^|\/)(docs?|documentation)(\/|$)|\.(md|mdx|rst|txt)$/i;
const HIGH_RISK_RE = /(^|\/)(auth|security|approval|policy|secrets?|keys?|terminal|git|browser|computer|workspace|sandbox)(\/|$)|(\.env|secret|credential|token)/i;

function uniqueFiles(files: ChangeRequestFile[]): ChangeRequestFile[] {
  const byPath = new Map<string, ChangeRequestFile>();
  for (const file of files) {
    const previous = byPath.get(file.path);
    byPath.set(file.path, { ...(previous ?? {}), ...file });
  }
  return [...byPath.values()].sort((a, b) => a.path.localeCompare(b.path));
}

function decorateFile(file: ChangeRequestFile): ChangeRequestFile {
  const churn = (file.additions ?? 0) + (file.deletions ?? 0);
  return {
    ...file,
    generated: file.generated || GENERATED_RE.test(file.path),
    test: file.test || TEST_RE.test(file.path),
    docs: file.docs || DOCS_RE.test(file.path),
    highRisk: file.highRisk || HIGH_RISK_RE.test(file.path),
    large: file.large || churn >= 500,
  };
}

export function filesFromStatusAndDiff(status?: CodingGitStatus | null, diff?: CodingDiffResponse | null): ChangeRequestFile[] {
  const parsed = parseUnifiedDiff(diff?.diff ?? "");
  const fromDiff = parsed.map((file) => decorateFile({
    path: file.path,
    additions: file.additions,
    deletions: file.deletions,
    binary: file.binary,
  }));
  const fromStatus = [
    ...(status?.staged ?? []).map((path) => ({ path, status: "staged" })),
    ...(status?.modified ?? []).map((path) => ({ path, status: "modified" })),
    ...(status?.untracked ?? []).map((path) => ({ path, status: "untracked", untracked: true })),
  ].map(decorateFile);
  return uniqueFiles([...fromDiff, ...fromStatus]);
}

export function FilesChangedPane({
  files,
  diff,
}: {
  files: ChangeRequestFile[];
  diff?: string | null;
}) {
  const decoratedFiles = useMemo(() => uniqueFiles(files.map(decorateFile)), [files]);
  const [selectedPath, setSelectedPath] = useState<string | null>(decoratedFiles[0]?.path ?? null);
  const [viewedPaths, setViewedPaths] = useState<Set<string>>(() => new Set());
  const selected = selectedPath && decoratedFiles.some((file) => file.path === selectedPath) ? selectedPath : decoratedFiles[0]?.path ?? null;
  const highRiskCount = decoratedFiles.filter((file) => file.highRisk).length;
  const untrackedCount = decoratedFiles.filter((file) => file.untracked).length;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{decoratedFiles.length} files</span>
        <span className="rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-200">{untrackedCount} untracked</span>
        <span className="rounded border border-red-500/25 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-200">{highRiskCount} high risk</span>
        <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{viewedPaths.size} viewed</span>
      </div>
      <div className="grid gap-2 min-[1440px]:grid-cols-[minmax(170px,0.9fr)_minmax(0,1.3fr)]">
        <DiffFileTree
          files={decoratedFiles}
          selectedPath={selected}
          viewed={viewedPaths}
          onSelect={setSelectedPath}
          onViewedChange={(path, nextViewed) => {
            setViewedPaths((current) => {
              const next = new Set(current);
              if (nextViewed) next.add(path);
              else next.delete(path);
              return next;
            });
          }}
        />
        <DiffViewer diff={diff} selectedPath={selected} emptyText={selected ? "No patch for this file yet" : "No diff loaded"} />
      </div>
    </div>
  );
}
