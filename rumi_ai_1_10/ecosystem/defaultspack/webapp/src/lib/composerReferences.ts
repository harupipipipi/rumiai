import type { ComposerExtensionItem, ComposerSkillItem } from "../renderers/types";

export const COMPOSER_REFERENCE_MIME = "application/x-rumi-composer-references+json";

export type ComposerEntityReference = {
  kind: "tool" | "skill" | "file";
  id: string;
  syntax: string;
};

type SerializedComposerReference = {
  kind: ComposerEntityReference["kind"];
  id: string;
  start: number;
  end: number;
};

type ComposerReferenceClipboardPayload = {
  version: 1;
  text: string;
  references: SerializedComposerReference[];
};

function referenceKey(reference: Pick<ComposerEntityReference, "kind" | "id">): string {
  return `${reference.kind}:${reference.id}`;
}

function isReferenceKind(value: unknown): value is ComposerEntityReference["kind"] {
  return value === "tool" || value === "skill" || value === "file";
}

function parsePayload(raw: string): ComposerReferenceClipboardPayload | null {
  if (!raw || raw.length > 1_000_000) return null;
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (value.version !== 1 || typeof value.text !== "string" || !Array.isArray(value.references)) return null;
    const references: SerializedComposerReference[] = [];
    for (const candidate of value.references.slice(0, 100)) {
      if (!candidate || typeof candidate !== "object") return null;
      const item = candidate as Record<string, unknown>;
      if (!isReferenceKind(item.kind) || typeof item.id !== "string" || !item.id.trim()) return null;
      if (!Number.isInteger(item.start) || !Number.isInteger(item.end)) return null;
      const start = Number(item.start);
      const end = Number(item.end);
      if (start < 0 || end <= start || end > value.text.length) return null;
      references.push({ kind: item.kind, id: item.id.trim(), start, end });
    }
    return { version: 1, text: value.text, references };
  } catch {
    return null;
  }
}

function findReferenceRanges(text: string, references: ComposerEntityReference[]): SerializedComposerReference[] {
  const ranges: SerializedComposerReference[] = [];
  const occupied = new Set<number>();
  for (const reference of references) {
    const syntax = reference.syntax || `@${reference.id}`;
    let start = text.indexOf(syntax);
    while (start >= 0) {
      const end = start + syntax.length;
      let overlaps = false;
      for (let index = start; index < end; index += 1) overlaps ||= occupied.has(index);
      if (!overlaps) {
        ranges.push({ kind: reference.kind, id: reference.id, start, end });
        for (let index = start; index < end; index += 1) occupied.add(index);
        break;
      }
      start = text.indexOf(syntax, start + 1);
    }
  }
  return ranges.sort((left, right) => left.start - right.start);
}

export function serializeComposerReferences(text: string, references: ComposerEntityReference[]): string | null {
  const ranges = findReferenceRanges(text, references);
  if (!text || ranges.length === 0) return null;
  return JSON.stringify({ version: 1, text, references: ranges } satisfies ComposerReferenceClipboardPayload);
}

export function restoreComposerReferences(
  raw: string,
  catalog: { tools: ComposerExtensionItem[]; skills: ComposerSkillItem[]; files?: string[] },
): { text: string; references: ComposerEntityReference[] } | null {
  const payload = parsePayload(raw);
  if (!payload) return null;
  const toolIds = new Set(catalog.tools.filter((item) => !item.disabled).map((item) => item.id));
  const skillIds = new Set(catalog.skills.map((item) => item.id));
  const fileIds = new Set(catalog.files ?? []);
  const seen = new Set<string>();
  const references: ComposerEntityReference[] = [];

  for (const item of payload.references) {
    const known = item.kind === "tool" ? toolIds.has(item.id) : item.kind === "skill" ? skillIds.has(item.id) : fileIds.has(item.id);
    if (!known) continue;
    const syntax = payload.text.slice(item.start, item.end);
    if (syntax !== `@${item.id}`) continue;
    const reference = { kind: item.kind, id: item.id, syntax } satisfies ComposerEntityReference;
    const key = referenceKey(reference);
    if (seen.has(key)) continue;
    seen.add(key);
    references.push(reference);
  }
  return { text: payload.text, references };
}

export function insertComposerReferencePaste(
  input: string,
  selectionStart: number,
  selectionEnd: number,
  restored: { text: string; references: ComposerEntityReference[] },
): { value: string; cursor: number; references: ComposerEntityReference[] } {
  const start = Math.max(0, Math.min(selectionStart, input.length));
  const end = Math.max(start, Math.min(selectionEnd, input.length));
  return {
    value: `${input.slice(0, start)}${restored.text}${input.slice(end)}`,
    cursor: start + restored.text.length,
    references: restored.references,
  };
}

export function mergeComposerReferences(
  current: ComposerEntityReference[],
  additions: ComposerEntityReference[],
  input: string,
): ComposerEntityReference[] {
  const byKey = new Map<string, ComposerEntityReference>();
  for (const reference of [...current, ...additions]) {
    if (!input.includes(reference.syntax)) continue;
    byKey.set(referenceKey(reference), reference);
  }
  return [...byKey.values()];
}
