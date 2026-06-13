import assert from 'node:assert/strict';
import test from 'node:test';

import {shouldShowDashboardSkeleton} from './Dashboard';

test('Dashboard keeps loaded content visible while the runtime reconnects', () => {
  assert.equal(
    shouldShowDashboardSkeleton({
      runtimeReconnecting: true,
      profilesLoading: false,
      hasPayload: true,
    }),
    false,
  );
});

test('Dashboard shows the skeleton before the first profile payload is loaded', () => {
  assert.equal(
    shouldShowDashboardSkeleton({
      runtimeReconnecting: true,
      profilesLoading: false,
      hasPayload: false,
    }),
    true,
  );
  assert.equal(
    shouldShowDashboardSkeleton({
      runtimeReconnecting: false,
      profilesLoading: true,
      hasPayload: false,
    }),
    true,
  );
});
