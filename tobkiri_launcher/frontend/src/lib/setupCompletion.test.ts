import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveSetupCompletion } from './setupCompletion';

test('connect-first completion reports both verified outcomes', () => {
  const result = resolveSetupCompletion({
    source: 'oauth',
    accountConnected: true,
    packSelected: true,
  });

  assert.equal(result.kind, 'account-and-pack');
  assert.equal(result.canRedirect, true);
  assert.match(result.description, /Account is connected/);
});

test('pack-only completion never claims that an account was linked', () => {
  const result = resolveSetupCompletion({
    source: 'setup-pack',
    accountConnected: false,
    packSelected: true,
  });

  assert.equal(result.kind, 'pack-only');
  assert.equal(result.canRedirect, true);
  assert.equal(result.title, 'Setup pack ready');
  assert.doesNotMatch(`${result.title} ${result.description} ${result.toast}`, /account linked/i);
});

test('already-connected completion reports account and pack readiness', () => {
  const result = resolveSetupCompletion({
    source: 'existing-account',
    accountConnected: true,
    packSelected: true,
  });

  assert.equal(result.kind, 'account-and-pack');
  assert.equal(result.canRedirect, true);
});

test('OAuth return cannot redirect before the account is verified', () => {
  const result = resolveSetupCompletion({
    source: 'oauth',
    accountConnected: false,
    packSelected: true,
  });

  assert.equal(result.kind, 'account-verification-error');
  assert.equal(result.canRedirect, false);
});

test('OAuth and pack-selection errors remain distinct non-success outcomes', () => {
  const oauth = resolveSetupCompletion({
    source: 'oauth',
    accountConnected: false,
    packSelected: false,
    oauthError: 'access_denied',
  });
  const pack = resolveSetupCompletion({
    source: 'setup-pack',
    accountConnected: false,
    packSelected: false,
  });

  assert.equal(oauth.kind, 'oauth-error');
  assert.equal(pack.kind, 'pack-selection-error');
  assert.equal(oauth.canRedirect, false);
  assert.equal(pack.canRedirect, false);
});
