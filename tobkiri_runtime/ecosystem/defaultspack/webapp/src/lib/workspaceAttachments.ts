import type { AttachedFile } from "../renderers/types";

export const WORKSPACE_ATTACHMENT_TEXT_LIMIT = 120_000;

export function workspaceFileToAttachment(path: string, content: string, size?: number): AttachedFile {
  const truncated = content.length > WORKSPACE_ATTACHMENT_TEXT_LIMIT;
  return {
    id: `workspace-${path}-${Date.now()}`,
    name: path,
    size: size ?? content.length,
    type: "text/plain",
    content: truncated ? content.slice(0, WORKSPACE_ATTACHMENT_TEXT_LIMIT) : content,
    truncated,
    source: "workspace",
    sourcePath: path,
  };
}

export function hasWorkspaceAttachment(files: AttachedFile[], path: string): boolean {
  return files.some((file) => file.sourcePath === path || (file.source === "workspace" && file.name === path));
}
