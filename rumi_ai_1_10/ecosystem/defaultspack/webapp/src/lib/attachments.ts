import type { AttachedFile } from "../renderers/types";

const TEXT_TRUNCATE_LIMIT = 120_000;

const TEXT_MIME_PREFIXES = ["text/"];
const TEXT_MIME_TYPES = new Set([
  "application/csv",
  "application/graphql",
  "application/javascript",
  "application/json",
  "application/ld+json",
  "application/rtf",
  "application/toml",
  "application/typescript",
  "application/x-httpd-php",
  "application/x-javascript",
  "application/x-sh",
  "application/xhtml+xml",
  "application/xml",
  "image/svg+xml",
]);

const TEXT_EXTENSIONS = new Set([
  "bash",
  "bat",
  "c",
  "cfg",
  "conf",
  "cpp",
  "cs",
  "css",
  "csv",
  "env",
  "go",
  "graphql",
  "h",
  "hpp",
  "html",
  "ini",
  "java",
  "js",
  "json",
  "jsx",
  "kt",
  "log",
  "lua",
  "md",
  "mdx",
  "mjs",
  "php",
  "properties",
  "py",
  "rb",
  "rs",
  "sh",
  "sql",
  "svg",
  "toml",
  "ts",
  "tsx",
  "txt",
  "xml",
  "yaml",
  "yml",
  "zsh",
]);

function fileExtension(name: string): string {
  const basename = name.split(/[\\/]/).pop() ?? name;
  const dotIndex = basename.lastIndexOf(".");
  return dotIndex >= 0 ? basename.slice(dotIndex + 1).toLowerCase() : "";
}

export function isTextLikeFile(file: Pick<File, "name" | "type">): boolean {
  const mime = (file.type || "").toLowerCase();
  if (mime && TEXT_MIME_PREFIXES.some((prefix) => mime.startsWith(prefix))) return true;
  if (mime && TEXT_MIME_TYPES.has(mime)) return true;
  return TEXT_EXTENSIONS.has(fileExtension(file.name));
}

export async function fileToAttachment(file: File): Promise<AttachedFile> {
  const base = {
    id: `file-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    size: file.size,
    type: file.type || undefined,
    truncated: false,
  };

  if (!isTextLikeFile(file)) {
    return base;
  }

  const text = await file.text();
  const truncated = text.length > TEXT_TRUNCATE_LIMIT;
  return {
    ...base,
    type: file.type || "text/plain",
    content: truncated ? text.slice(0, TEXT_TRUNCATE_LIMIT) : text,
    truncated,
  };
}

export function buildAttachmentSnippet(file: AttachedFile): string {
  if (file.content === undefined) return "";
  return `\n\n添付ファイル: ${file.name}\n\`\`\`\n${file.content}${file.truncated ? "\n..." : ""}\n\`\`\``;
}
