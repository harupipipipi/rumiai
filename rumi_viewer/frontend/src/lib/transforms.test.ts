import test from 'node:test';
import assert from 'node:assert/strict';

import { transformPack } from './transforms';

test('transformPack preserves approval state from panel packs API', () => {
  const pack = transformPack({
    pack_id: 'pack_a',
    name: 'Pack A',
    version: '1.0.0',
    description: 'Demo pack',
    is_core: false,
    enabled: true,
    approval_status: 'modified',
    approval_reason: 'hash_mismatch',
    approved: false,
    hash_valid: false,
    critical_changed: true,
    approval_issues: ['hash_mismatch', 'critical_changed'],
  });

  assert.equal(pack.id, 'pack_a');
  assert.equal(pack.approvalStatus, 'modified');
  assert.equal(pack.approvalReason, 'hash_mismatch');
  assert.equal(pack.approved, false);
  assert.equal(pack.hashValid, false);
  assert.equal(pack.criticalChanged, true);
  assert.deepEqual(pack.approvalIssues, ['hash_mismatch', 'critical_changed']);
});
