import assert from 'node:assert/strict';
import test from 'node:test';

import { isDefaultspackLaunchPack } from './defaultspackLaunch';

test('defaultspack launch detection covers v1 id, v2 id, and v2 display name', () => {
  assert.equal(isDefaultspackLaunchPack({id: 'defaultspack', name: 'Rumi Defaultspack', version: '1.0.0'}), true);
  assert.equal(isDefaultspackLaunchPack({id: 'defaultspackv2', name: 'defaultspackv2', version: '2.0.0'}), true);
  assert.equal(isDefaultspackLaunchPack({id: 'defaultspack', name: 'Rumi Defaultspack v2', version: '2.0.0'}), true);
  assert.equal(isDefaultspackLaunchPack({id: 'otherpack', name: 'Other Pack', version: '2.0.0'}), false);
});
