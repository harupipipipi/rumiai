export type MentionToken = {
  end: number;
  start: number;
  value: string;
};

export type ActiveMention = {
  query: string;
  start: number;
};

const ASCII_MENTION_BOUNDARY_BLOCKERS = /[A-Za-z0-9_.%+\-/:@\\]/;
const MENTION_TOKEN_CHAR = /[\p{L}\p{M}\p{N}_./:-]/u;

/** Return whether an at sign begins a product mention rather than an email or URL. */
export function isMentionStart(text: string, atIndex: number): boolean {
  if (atIndex < 0 || atIndex >= text.length || text[atIndex] !== "@") return false;
  if (atIndex === 0) return true;
  return !ASCII_MENTION_BOUNDARY_BLOCKERS.test(text[atIndex - 1]);
}

function isMentionTokenChar(value: string): boolean {
  return Boolean(value) && MENTION_TOKEN_CHAR.test(value);
}

/** Extract Unicode-safe product mention tokens and their source spans. */
export function extractMentionTokens(text: string): MentionToken[] {
  const result: MentionToken[] = [];
  for (let atIndex = text.indexOf("@"); atIndex >= 0; atIndex = text.indexOf("@", atIndex + 1)) {
    if (!isMentionStart(text, atIndex)) continue;
    let end = atIndex + 1;
    while (end < text.length && isMentionTokenChar(text[end])) end += 1;
    while (end > atIndex + 1 && text[end - 1] === ".") end -= 1;
    if (end === atIndex + 1) continue;
    result.push({ start: atIndex, end, value: text.slice(atIndex + 1, end) });
  }
  return result;
}

/** Resolve the currently open mention at a textarea cursor, if one exists. */
export function activeMentionAtCursor(text: string, cursor: number): ActiveMention | null {
  const safeCursor = Math.min(Math.max(cursor, 0), text.length);
  const atIndex = text.lastIndexOf("@", safeCursor - 1);
  if (!isMentionStart(text, atIndex)) return null;
  const query = text.slice(atIndex + 1, safeCursor);
  if (query.endsWith(".")) return null;
  if ([...query].some((character) => !isMentionTokenChar(character))) return null;
  return { start: atIndex, query };
}
