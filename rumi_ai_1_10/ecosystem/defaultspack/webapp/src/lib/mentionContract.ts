export type MentionToken = {
  end: number;
  start: number;
  value: string;
};

export type ActiveMention = {
  query: string;
  startCodePoint: number;
  /** UTF-16 offset used by textarea selection APIs. */
  start: number;
};

const ASCII_MENTION_BOUNDARY_BLOCKERS = /[A-Za-z0-9_.%+\-/:@\\]/;
const MENTION_TOKEN_CHAR = /[\p{L}\p{M}\p{N}_./:-]/u;

/** Convert a textarea UTF-16 offset to the parser's Unicode code-point index. */
export function utf16OffsetToCodePointIndex(text: string, offset: number): number {
  const safeOffset = Math.min(Math.max(offset, 0), text.length);
  let codePointIndex = 0;
  let utf16Offset = 0;
  for (const character of text) {
    if (utf16Offset + character.length > safeOffset) break;
    utf16Offset += character.length;
    codePointIndex += 1;
  }
  return codePointIndex;
}

/** Convert a parser code-point index to a textarea UTF-16 offset. */
export function codePointIndexToUtf16Offset(text: string, index: number): number {
  const safeIndex = Math.max(index, 0);
  let codePointIndex = 0;
  let utf16Offset = 0;
  for (const character of text) {
    if (codePointIndex >= safeIndex) break;
    utf16Offset += character.length;
    codePointIndex += 1;
  }
  return utf16Offset;
}

/** Return whether an at sign begins a product mention rather than an email or URL. */
export function isMentionStart(text: string, atIndex: number): boolean {
  const characters = [...text];
  if (atIndex < 0 || atIndex >= characters.length || characters[atIndex] !== "@") return false;
  if (atIndex === 0) return true;
  return !ASCII_MENTION_BOUNDARY_BLOCKERS.test(characters[atIndex - 1]);
}

function isMentionTokenChar(value: string): boolean {
  return Boolean(value) && MENTION_TOKEN_CHAR.test(value);
}

/** Extract Unicode-safe product mention tokens and their source spans. */
export function extractMentionTokens(text: string): MentionToken[] {
  const characters = [...text];
  const result: MentionToken[] = [];
  for (let atIndex = characters.indexOf("@"); atIndex >= 0; atIndex = characters.indexOf("@", atIndex + 1)) {
    if (!isMentionStart(text, atIndex)) continue;
    let end = atIndex + 1;
    while (end < characters.length && isMentionTokenChar(characters[end])) end += 1;
    while (end > atIndex + 1 && characters[end - 1] === ".") end -= 1;
    if (end === atIndex + 1) continue;
    result.push({ start: atIndex, end, value: characters.slice(atIndex + 1, end).join("") });
  }
  return result;
}

/** Resolve the currently open mention at a textarea cursor, if one exists. */
export function activeMentionAtCursor(text: string, cursor: number): ActiveMention | null {
  const characters = [...text];
  const safeCursor = Math.min(Math.max(cursor, 0), text.length);
  const cursorCodePoint = utf16OffsetToCodePointIndex(text, safeCursor);
  const atIndex = characters.lastIndexOf("@", cursorCodePoint - 1);
  if (!isMentionStart(text, atIndex)) return null;
  const query = characters.slice(atIndex + 1, cursorCodePoint).join("");
  if (query.endsWith(".")) return null;
  if ([...query].some((character) => !isMentionTokenChar(character))) return null;
  return {
    start: codePointIndexToUtf16Offset(text, atIndex),
    startCodePoint: atIndex,
    query,
  };
}

/** Return whether exact human-facing mention syntax still occurs unescaped. */
export function hasUnescapedMentionSyntax(text: string, syntax: string): boolean {
  if (!syntax.startsWith("@") || syntax.length < 2) return false;
  for (let offset = text.indexOf(syntax); offset >= 0; offset = text.indexOf(syntax, offset + 1)) {
    const codePointIndex = utf16OffsetToCodePointIndex(text, offset);
    if (codePointIndexToUtf16Offset(text, codePointIndex) !== offset) continue;
    if (isMentionStart(text, codePointIndex)) return true;
  }
  return false;
}
