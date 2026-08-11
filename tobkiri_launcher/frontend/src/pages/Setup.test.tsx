import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import test from 'node:test';
import React from 'react';
import {renderToString} from 'react-dom/server';
import {MemoryRouter, Route, Routes} from 'react-router';
import {DefaultsReview} from './DefaultsReview';

const setupSource = readFileSync(resolve(import.meta.dirname, 'Setup.tsx'), 'utf8');
const appSource = readFileSync(resolve(import.meta.dirname, '..', 'App.tsx'), 'utf8');

test('the panel setup route renders the Defaults v4 review component', () => {
  const html = renderToString(
    <MemoryRouter initialEntries={['/setup']}>
      <Routes><Route path="/setup" element={<DefaultsReview
        setup={null}
        reviewed={false}
        activating={false}
        error={null}
        onReviewedChange={() => undefined}
        onActivate={() => undefined}
      />} /></Routes>
    </MemoryRouter>,
  );

  assert.match(html, /Defaults v4 bootstrap/);
  assert.match(html, /Activate Defaults Profile/);
  assert.match(html, /Loading verified catalog/);
});

test('the setup component exposes verification instead of replay after an ambiguous commit', () => {
  const html = renderToString(
    <DefaultsReview
      setup={null}
      reviewed={true}
      activating={false}
      activationCommitted={true}
      error="The activation response could not be confirmed."
      onRecover={() => undefined}
      onReviewedChange={() => undefined}
      onActivate={() => undefined}
    />,
  );

  assert.match(html, /Activation was submitted; verification is required/);
  assert.match(html, /previous confirmation will not be submitted again/);
  assert.match(html, /Verify activation/);
});

test('setup activation is explicit and followed by selected presentation materialization', () => {
  assert.match(setupSource, /activateDefaultsProfile/);
  const reviewSource = readFileSync(resolve(import.meta.dirname, 'DefaultsReview.tsx'), 'utf8');
  assert.match(reviewSource, /type="checkbox"/);
  assert.match(reviewSource, /disabled=\{!reviewed \|\| activating \|\| activationCommitted\}/);
  assert.match(reviewSource, /previous confirmation will not be submitted again/);
  assert.match(setupSource, /PresentationSelector/);
  assert.match(setupSource, /selectPresentation/);
  assert.match(setupSource, /navigate\(panelRoutes\.home\)/);
  assert.match(setupSource, /typeof error === 'string' && error\.trim\(\)/);
  assert.match(setupSource, /refreshRuntimeHealth/);
  assert.match(setupSource, /refreshMountedRuntimeSurfaces/);
  assert.match(setupSource, /refreshPackVMDoctor\(\{reconcile: false\}\)/);
  assert.match(setupSource, /formatPackVMRecoveryError/);
  assert.match(setupSource, /activationInFlightRef/);
  assert.match(setupSource, /runtimeStatus.*runtime_ready/);
  assert.match(setupSource, /activateDefaultsWithRecovery/);
  assert.match(setupSource, /recoverDefaultsActivation/);
  assert.match(setupSource, /fetchAuthoritativeSetup: fetchDefaultsSetupState/);
});

test('reconfirmation setup copy exposes only the Host-owned bootstrap ceremony', () => {
  const reviewSource = readFileSync(resolve(import.meta.dirname, 'DefaultsReview.tsx'), 'utf8');
  assert.match(reviewSource, /Profile reconfirmation required/);
  assert.match(reviewSource, /required_transaction/);
  assert.match(reviewSource, /Host-owned transaction/);
  assert.doesNotMatch(reviewSource, /profile\.change\.(resolve|review|approve|activate)/);
});

test('the current GUI has no dependency on retired setup-pack routing', () => {
  assert.doesNotMatch(setupSource, /setupPack|setup_pack|\/setup\?return_to/);
  assert.doesNotMatch(appSource, /hasSelectedSetupPack|setupPacks/);
  assert.match(appSource, /fetchDefaultsSetupState/);
  assert.match(appSource, /state\.state === 'active'/);
});
