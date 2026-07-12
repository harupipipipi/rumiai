export const VALID_THEMES = ['Rumi', 'Minimal', 'Standard', 'Rounded'] as const;
export type Theme = (typeof VALID_THEMES)[number];

export const VALID_COLOR_MODES = ['light', 'dark'] as const;
export type ColorMode = (typeof VALID_COLOR_MODES)[number];

export const THEME_STORAGE_KEY = 'tobkiri-theme';
export const COLOR_MODE_STORAGE_KEY = 'tobkiri-color-mode';
export const LEGACY_THEME_STORAGE_KEY = 'rumi-theme';
export const LEGACY_COLOR_MODE_STORAGE_KEY = 'rumi-color-mode';

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

type AppearanceStorage = Pick<Storage, 'getItem'> & Partial<Pick<Storage, 'setItem'>>;

function readStorageValue(storage: AppearanceStorage | null | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function getBrowserStorage(): AppearanceStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

function readMigratedValue(storage: AppearanceStorage | null | undefined, canonicalKey: string, legacyKey: string): string | null {
  const canonical = readStorageValue(storage, canonicalKey);
  if (canonical !== null) return canonical;
  const legacy = readStorageValue(storage, legacyKey);
  if (legacy === null) return null;
  try { storage?.setItem?.(canonicalKey, legacy); } catch { /* storage is optional */ }
  return legacy;
}

export function readStoredAppearance(storage?: AppearanceStorage | null): Appearance {
  const effectiveStorage = storage === undefined ? getBrowserStorage() : storage;
  return {
    theme: normalizeTheme(readMigratedValue(effectiveStorage, THEME_STORAGE_KEY, LEGACY_THEME_STORAGE_KEY)),
    colorMode: normalizeColorMode(readMigratedValue(effectiveStorage, COLOR_MODE_STORAGE_KEY, LEGACY_COLOR_MODE_STORAGE_KEY)),
  };
}

export function applyAppearanceToRoot(root: Pick<HTMLElement, 'classList' | 'dataset' | 'style'>, appearance: Appearance): void {
  root.classList.remove(...THEME_CLASS_NAMES);
  root.classList.add(themeClassName(appearance.theme));
  root.classList.toggle('dark', appearance.colorMode === 'dark');
  root.dataset.theme = appearance.theme;
  root.dataset.colorMode = appearance.colorMode;
  root.style.colorScheme = appearance.colorMode;
  root.style.backgroundColor = '';
  root.style.color = '';
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
