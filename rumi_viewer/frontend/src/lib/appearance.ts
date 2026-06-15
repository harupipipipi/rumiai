export const VALID_THEMES = ['Rumi', 'Minimal', 'Standard', 'Rounded'] as const;
export type Theme = (typeof VALID_THEMES)[number];

export const VALID_COLOR_MODES = ['light', 'dark'] as const;
export type ColorMode = (typeof VALID_COLOR_MODES)[number];

export const THEME_STORAGE_KEY = 'rumi-theme';
export const COLOR_MODE_STORAGE_KEY = 'rumi-color-mode';

export interface Appearance {
  theme: Theme;
  colorMode: ColorMode;
}

export const THEME_CLASS_NAMES = VALID_THEMES.map(themeClassName);

export function themeClassName(theme: Theme): string {
  return `theme-${theme.toLowerCase()}`;
}

export function normalizeTheme(value: unknown): Theme {
  return typeof value === 'string' && (VALID_THEMES as readonly string[]).includes(value)
    ? (value as Theme)
    : 'Rumi';
}

export function normalizeColorMode(value: unknown): ColorMode {
  return value === 'light' || value === 'dark' ? value : 'dark';
}

function readStorageValue(storage: Pick<Storage, 'getItem'> | null | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function getBrowserStorage(): Pick<Storage, 'getItem'> | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function readStoredAppearance(storage?: Pick<Storage, 'getItem'> | null): Appearance {
  const effectiveStorage = storage === undefined ? getBrowserStorage() : storage;
  return {
    theme: normalizeTheme(readStorageValue(effectiveStorage, THEME_STORAGE_KEY)),
    colorMode: normalizeColorMode(readStorageValue(effectiveStorage, COLOR_MODE_STORAGE_KEY)),
  };
}

export function applyAppearanceToRoot(root: Pick<HTMLElement, 'classList' | 'dataset' | 'style'>, appearance: Appearance): void {
  root.classList.remove(...THEME_CLASS_NAMES);
  root.classList.add(themeClassName(appearance.theme));
  root.classList.toggle('dark', appearance.colorMode === 'dark');
  root.dataset.theme = appearance.theme;
  root.dataset.colorMode = appearance.colorMode;
  root.style.colorScheme = appearance.colorMode;
}

export function bootstrapDocumentAppearance(
  documentRef?: Pick<Document, 'documentElement'>,
  storage?: Pick<Storage, 'getItem'> | null,
): Appearance {
  const appearance = readStoredAppearance(storage);
  const currentDocument = documentRef ?? (typeof document === 'undefined' ? null : document);
  if (currentDocument) {
    applyAppearanceToRoot(currentDocument.documentElement, appearance);
  }
  return appearance;
}
