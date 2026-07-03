import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

import { Header } from '@/src/components/layout/Header';
import { Sidebar } from '@/src/components/layout/Sidebar';
import { LAUNCHER_DISPLAY_NAME, LAUNCHER_VERSION_LABEL } from '@/src/lib/launcherBrand';
import { Setup } from './Setup';

function renderWithRoute(children: ReactNode, route = '/') {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[route]}>
      {children}
    </MemoryRouter>,
  );
}

test('launcher document and version labels use the Tobkiri Launcher spelling', () => {
  const indexHtml = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');

  assert.equal(LAUNCHER_DISPLAY_NAME, 'Tobkiri Launcher');
  assert.equal(LAUNCHER_VERSION_LABEL, 'Tobkiri Launcher Version');
  assert.match(indexHtml, /<title>Tobkiri Launcher<\/title>/);
});

test('sidebar renders launcher brand and primary navigation copy', () => {
  const html = renderWithRoute(<Sidebar />);

  assert.match(html, /Tobkiri Launcher/);
  assert.match(html, /Home/);
  assert.match(html, /Packs/);
  assert.match(html, /Flows/);
  assert.match(html, /Nodes/);
  assert.match(html, /Settings/);
});

test('header and setup screens render launcher-facing copy', () => {
  const headerHtml = renderWithRoute(<Header />, '/packs');
  const setupHtml = renderWithRoute(<Setup />);

  assert.match(headerHtml, /Packs/);
  assert.match(setupHtml, /Welcome to Tobkiri Launcher/);
});
