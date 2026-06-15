import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyAppearanceToRoot,
  normalizeColorMode,
  normalizeTheme,
  readStoredAppearance,
} from './appearance';

function fakeStorage(values: Record<string, string | null>): Pick<Storage, 'getItem'> {
  return {
    getItem: (key) => values[key] ?? null,
  };
}

function fakeRoot() {
  const classes = new Set<string>();
  const classList = {
    add: (...names: string[]) => {
      names.forEach((name) => classes.add(name));
    },
    remove: (...names: string[]) => {
      names.forEach((name) => classes.delete(name));
    },
    toggle: (name: string, force?: boolean) => {
      const shouldAdd = force ?? !classes.has(name);
      if (shouldAdd) {
        classes.add(name);
      } else {
        classes.delete(name);
      }
      return shouldAdd;
    },
  };

  return {
    classes,
    element: {
      classList,
      dataset: {},
      style: {},
    } as unknown as HTMLElement,
  };
}

test('appearance normalization falls back to the startup-safe defaults', () => {
  assert.equal(normalizeTheme('Rounded'), 'Rounded');
  assert.equal(normalizeTheme('Unknown'), 'Rumi');
  assert.equal(normalizeColorMode('light'), 'light');
  assert.equal(normalizeColorMode('sepia'), 'dark');
});

test('stored appearance reads the shared Viewer storage keys defensively', () => {
  assert.deepEqual(
    readStoredAppearance(fakeStorage({
      'rumi-theme': 'Minimal',
      'rumi-color-mode': 'light',
    })),
    { theme: 'Minimal', colorMode: 'light' },
  );
  assert.deepEqual(
    readStoredAppearance(fakeStorage({
      'rumi-theme': 'Bogus',
      'rumi-color-mode': 'Bogus',
    })),
    { theme: 'Rumi', colorMode: 'dark' },
  );
});

test('appearance application keeps one theme class and toggles dark before paint', () => {
  const root = fakeRoot();
  root.classes.add('theme-rumi');
  root.classes.add('dark');

  applyAppearanceToRoot(root.element, { theme: 'Rounded', colorMode: 'light' });

  assert.deepEqual([...root.classes].sort(), ['theme-rounded']);
  assert.equal(root.element.dataset.theme, 'Rounded');
  assert.equal(root.element.dataset.colorMode, 'light');
  assert.equal(root.element.style.colorScheme, 'light');
});
