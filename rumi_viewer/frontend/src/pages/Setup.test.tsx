import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import test from 'node:test';

import {selectedSetupPackIds, setupPackSelectionUrl} from './Setup';

const source = readFileSync(resolve(import.meta.dirname, 'Setup.tsx'), 'utf8');

test('selectedSetupPackIds normalizes selected setup-pack ids', () => {
  assert.deepEqual(
    selectedSetupPackIds({selected_setup_pack_ids: ['defaultspack', '', null, ' custom ']}),
    ['defaultspack', 'custom'],
  );
  assert.deepEqual(selectedSetupPackIds({selected_setup_pack_ids: 'defaultspack'}), []);
  assert.deepEqual(selectedSetupPackIds(null), []);
});

test('setupPackSelectionUrl returns to panel setup for verification', () => {
  assert.equal(
    setupPackSelectionUrl(),
    '/setup?return_to=%2Fpanel%2Fsetup%3Fsetup_pack_done%3D1',
  );
});

test('panel setup does not bypass setup-pack installation', () => {
  assert.match(source, /apiFetch<SetupPacksPayload>\('\/api\/setup\/packs'\)/);
  assert.match(source, /selectedSetupPackIds\(packs\)\.length > 0/);
  assert.match(source, /window\.location\.assign\(setupPackSelectionUrl\(\)\)/);
  assert.doesNotMatch(
    source,
    /const handleSkip = \(\) => \{\s*setSetupDone\(true\);\s*navigate\(panelRoutes\.home\);/,
  );
});
