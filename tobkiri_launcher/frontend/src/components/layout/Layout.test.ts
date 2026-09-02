import assert from 'node:assert/strict';
import test from 'node:test';

import {shouldShowRuntimeErrorCopy} from './Layout';

test('runtime copy action is reserved for actionable danger diagnostics', () => {
  assert.equal(shouldShowRuntimeErrorCopy({tone: 'warning', detail: 'Preparing'}), false);
  assert.equal(shouldShowRuntimeErrorCopy({tone: 'warning', detail: 'Profile reconfirmation required'}), false);
  assert.equal(shouldShowRuntimeErrorCopy({tone: 'danger', detail: '   '}), false);
  assert.equal(shouldShowRuntimeErrorCopy({tone: 'danger', detail: 'Runtime connection failed'}), true);
});
