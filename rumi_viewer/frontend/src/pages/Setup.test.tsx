import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import test from 'node:test';

const source = readFileSync(resolve(import.meta.dirname, 'Setup.tsx'), 'utf8');
const appSource = readFileSync(resolve(import.meta.dirname, '..', 'App.tsx'), 'utf8');

test('panel setup does not bypass setup-pack installation', () => {
  assert.match(source, /hasSelectedSetupPack\(\)/);
  assert.match(source, /window\.location\.assign\(setupPackSelectionUrl\(\)\)/);
  assert.doesNotMatch(
    source,
    /const handleSkip = \(\) => \{\s*setSetupDone\(true\);\s*navigate\(panelRoutes\.home\);/,
  );
});

test('panel entry verifies backend setup-pack selection before showing the app', () => {
  assert.match(appSource, /import \{ hasSelectedSetupPack \} from '@\/src\/lib\/setupPacks'/);
  assert.match(appSource, /function SetupVerificationGate\(\)/);
  assert.match(appSource, /void hasSelectedSetupPack\(\)[\s\S]*setSetupDone\(false\)/);
  assert.match(appSource, /setupPackVerified \? <Layout \/> : <SetupVerificationGate \/>/);
  assert.doesNotMatch(
    appSource,
    /element=\{isSetupDone \? <Layout \/> : <Navigate to=\{panelRoutes\.setup\} replace \/>\}/,
  );
});
