import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  copyTextToClipboard,
  SupervisorSnapshot,
  summarizeSupervisorHealth,
} from './Dashboard';
import type { ApiSupervisorDashboard } from '@/src/lib/apiTypes';

function supervisorMetrics(
  overrides: Partial<ApiSupervisorDashboard['metrics']> = {},
): ApiSupervisorDashboard {
  return {
    capabilities: { snapshot: true, live_screen: true, takeover: false, replay: true },
    router: {
      policy: 'structured_first',
      structured_first: true,
      computer_use_role: 'fallback',
      preferred_order: [],
      fallback_order: [],
      operation_layers: [],
      fallback_layers: [],
      computer_driver_order: {},
    },
    sandbox_providers: [],
    runtime_templates: [],
    metrics: {
      available: true,
      active_runs: 1,
      waiting_approvals: 0,
      stale_runs: 0,
      failed_runs: 0,
      screen_sessions: 0,
      replay_ready: 0,
      artifact_streams: [],
      ...overrides,
    },
    sessions: [],
    selected_session: null,
    recent_events: [],
    event_schema: [],
    storage_targets: {},
    action_buttons: [],
    security_guardrails: [],
  };
}

test('copyTextToClipboard copies the complete runtime error message', async () => {
  let copied = '';
  const success = await copyTextToClipboard('Kernel failed to start', {
    writeText: async (text: string) => {
      copied = text;
    },
  });

  assert.equal(success, true);
  assert.equal(copied, 'Kernel failed to start');
});

test('copyTextToClipboard returns false when the clipboard is unavailable', async () => {
  const success = await copyTextToClipboard('message', undefined);
  assert.equal(success, false);
});

test('healthy supervisor data stays calm and contains no raw diagnostics', () => {
  assert.deepEqual(summarizeSupervisorHealth(supervisorMetrics(), false, null), {
    state: 'healthy',
    label: 'Healthy',
    summary: 'No failed, stale, or approval-blocked runs need attention.',
    issues: [],
  });
});

test('failed stale and approval-blocked work becomes a concise Home alert', () => {
  const summary = summarizeSupervisorHealth(supervisorMetrics({
    failed_runs: 2,
    stale_runs: 1,
    waiting_approvals: 3,
  }), false, null);

  assert.equal(summary.state, 'attention');
  assert.deepEqual(summary.issues, [
    '2 failed runs',
    '1 stale run',
    '3 approvals need review',
  ]);
});

test('loading missing and failed diagnostics never claim a healthy state', () => {
  assert.equal(summarizeSupervisorHealth(null, true, null).state, 'loading');
  assert.equal(summarizeSupervisorHealth(null, false, null).state, 'unavailable');
  assert.deepEqual(summarizeSupervisorHealth(null, false, 'offline'), {
    state: 'attention',
    label: 'Needs attention',
    summary: 'Tobkiri could not refresh runtime diagnostics.',
    issues: ['Runtime diagnostics could not be refreshed.'],
  });
});

test('healthy runtime details are collapsed behind a labeled disclosure', () => {
  const html = renderToStaticMarkup(createElement(SupervisorSnapshot, {
    data: supervisorMetrics(),
    loading: false,
    error: null,
  }));

  assert.match(html, /<details[^>]*>/);
  assert.doesNotMatch(html, /<details[^>]*\sopen(?:=|\s|>)/);
  assert.match(html, /Advanced runtime diagnostics/);
  assert.match(html, /Healthy/);
  assert.doesNotMatch(html, /Runtime needs attention/);
});

test('blocking runtime work stays visible without expanding raw details', () => {
  const html = renderToStaticMarkup(createElement(SupervisorSnapshot, {
    data: supervisorMetrics({ failed_runs: 1, waiting_approvals: 2 }),
    loading: false,
    error: null,
  }));

  assert.match(html, /role="alert"/);
  assert.match(html, /Runtime needs attention/);
  assert.match(html, /1 failed run · 2 approvals need review/);
  assert.match(html, /Review diagnostics/);
  assert.doesNotMatch(html, /<details[^>]*\sopen(?:=|\s|>)/);
});
