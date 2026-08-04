import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import test from 'node:test';

const source = readFileSync(resolve(import.meta.dirname, 'Setup.tsx'), 'utf8');
const appSource = readFileSync(resolve(import.meta.dirname, '..', 'App.tsx'), 'utf8');

test('panel setup does not bypass setup-pack installation', () => {
  assert.match(source, /hasSelectedSetupPack\(\)/);
  assert.match(source, /window\.location\.assign\(setupPackSelectionUrl\(undefined, colorMode\)\)/);
  assert.match(source, /tobkiri-launcher-icon\.png/);
  assert.doesNotMatch(
    source,
    /const handleSkip = \(\) => \{\s*setSetupDone\(true\);\s*navigate\(panelRoutes\.home\);/,
  );
});

test('panel setup requires an exact Base Pack then app.shell.v1 presentation selection', () => {
  assert.match(source, /PresentationSelector/);
  assert.match(source, /fetchPresentationState/);
  assert.match(source, /selectPresentation/);
  assert.match(source, /launchSelectedPresentation/);
  assert.match(source, /preparePresentationSetup/);
});

test('panel setup preserves actionable Tauri string errors', () => {
  assert.match(source, /function presentationErrorMessage\(error: unknown, fallback: string\)/);
  assert.match(source, /typeof error === 'string' && error\.trim\(\)/);
  assert.match(source, /presentationErrorMessage\(error, 'Presentation catalog could not be loaded\.'/);
});

test('panel setup reports async failures and only renders a trusted bundled icon', () => {
  assert.match(source, /setPresentationError\(\s*presentationErrorMessage\(/);
  assert.match(source, /setSetupPackError\(\s*presentationErrorMessage\(/);
  assert.match(source, /data-asset-trust.*bundled/);
  assert.doesNotMatch(source, /<img[\s\S]{0,160}\bsrc\s*=\s*\{/);
});

test('panel entry shows Home first and verifies the setup pack in the background', () => {
  assert.match(appSource, /import \{ hasSelectedSetupPack \} from '@\/src\/lib\/setupPacks'/);
  assert.match(appSource, /requestIdleCallback/);
  assert.match(appSource, /void hasSelectedSetupPack\(\)[\s\S]*setSetupDone\(false\)/);
  assert.match(appSource, /element=\{isSetupDone \? <Layout \/> : <Navigate to=\{panelRoutes\.setup\} replace \/>\}/);
  assert.doesNotMatch(appSource, /function SetupVerificationGate\(\)/);
});
