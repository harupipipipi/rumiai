import assert from 'node:assert/strict';
import test from 'node:test';

import { selectedSetupPackIds, setupPackSelectionUrl } from './setupPacks';

test('selectedSetupPackIds normalizes selected setup-pack ids', () => {
  assert.deepEqual(
    selectedSetupPackIds({ selected_setup_pack_ids: ['defaultspack', '', null, ' custom '] }),
    ['defaultspack', 'custom'],
  );
  assert.deepEqual(selectedSetupPackIds({ selected_setup_pack_ids: 'defaultspack' }), []);
  assert.deepEqual(selectedSetupPackIds(null), []);
});

test('setupPackSelectionUrl returns to panel setup for verification', () => {
  assert.equal(
    setupPackSelectionUrl(),
    '/setup?return_to=%2Fpanel%2Fsetup%3Fsetup_pack_done%3D1',
  );
});
