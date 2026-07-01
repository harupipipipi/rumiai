import assert from 'node:assert/strict';
import test from 'node:test';
import {renderToStaticMarkup} from 'react-dom/server';

import {Settings} from './Settings';

test('Settings security tab exposes runtime guardrails without relying on desktop shell APIs', () => {
  const markup = renderToStaticMarkup(<Settings initialTab="security" />);

  assert.match(markup, /Runtime Security/);
  assert.match(markup, /Client approval flags/);
  assert.match(markup, /Never trusted directly/);
  assert.match(markup, /Write-like actions/);
  assert.match(markup, /Approval gated/);
  assert.match(markup, /Pack execution/);
  assert.match(markup, /Grant scoped/);
});
