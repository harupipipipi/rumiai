import assert from 'node:assert/strict';
import {beforeEach, test} from 'node:test';

import type {Pack, Profile, Toast} from '@/src/store';
import {useAppStore} from '@/src/store';
import {runConfirmedMutation} from './mutations';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

const originalProfile: Profile = {
  avatar: '/avatar.png',
  username: 'Rumi user',
  language: 'en',
  job: 'Engineer',
  connected: true,
};

const originalPack: Pack = {
  id: 'defaultspack',
  name: 'Defaults Pack',
  version: '1.0.0',
  type: 'core',
  enabled: true,
  description: 'Built-in capabilities',
  approvalStatus: 'approved',
  approvalReason: null,
  approved: true,
  hashValid: true,
  criticalChanged: false,
  approvalIssues: [],
  capabilities: [],
  flows: [],
  dependencies: [],
};

let toastEvents: Array<Pick<Toast, 'message' | 'type'>> = [];

beforeEach(() => {
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: storage,
    writable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      history: {replaceState: () => {}},
      location: {href: 'http://127.0.0.1:8765/panel/'},
    },
    writable: true,
  });
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async () => {
      throw new Error('request rejected');
    },
    writable: true,
  });

  toastEvents = [];
  useAppStore.setState({
    flows: [{id: 'draft-flow', name: 'draft.flow.yaml', content: 'draft yaml'}],
    packs: [originalPack],
    profile: originalProfile,
    toasts: [],
    addToast: (message, type) => {
      toastEvents.push({message, type});
    },
  });
});

function assertOnlyFailureFeedback(): void {
  assert.deepEqual(toastEvents, [{message: 'request rejected', type: 'error'}]);
}

test('rejected flow create keeps the draft in creation mode without success feedback', async () => {
  const editor = {
    isCreating: true,
    selectedFlowId: null as string | null,
    nodes: ['draft-node'],
    edges: ['draft-edge'],
  };

  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().addFlow({
      id: 'new-flow',
      name: 'new-flow.flow.yaml',
      content: 'draft yaml',
    }),
    () => {
      editor.isCreating = false;
      editor.selectedFlowId = 'new-flow';
      toastEvents.push({message: 'Flow created', type: 'success'});
    },
  );

  assert.equal(confirmed, false);
  assert.deepEqual(editor, {
    isCreating: true,
    selectedFlowId: null,
    nodes: ['draft-node'],
    edges: ['draft-edge'],
  });
  assert.deepEqual(useAppStore.getState().flows, [
    {id: 'draft-flow', name: 'draft.flow.yaml', content: 'draft yaml'},
  ]);
  assertOnlyFailureFeedback();
});

test('successful flow write is not confirmed when the required refresh fails', async () => {
  let fetchCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async () => {
      fetchCalls += 1;
      if (fetchCalls === 1) {
        return new Response(JSON.stringify({success: true, data: {}}), {
          headers: {'Content-Type': 'application/json'},
          status: 200,
        });
      }
      throw new Error('refresh rejected');
    },
    writable: true,
  });

  let successFeedback = false;
  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().addFlow({
      id: 'new-flow',
      name: 'new-flow.flow.yaml',
      content: 'draft yaml',
    }),
    () => {
      successFeedback = true;
    },
  );

  assert.equal(fetchCalls, 2);
  assert.equal(confirmed, false);
  assert.equal(successFeedback, false);
  assert.deepEqual(toastEvents, [{message: 'refresh rejected', type: 'error'}]);
});

test('rejected flow update keeps the selected edited graph without success feedback', async () => {
  const editor = {
    selectedFlowId: 'draft-flow',
    nodes: ['edited-node'],
    edges: ['edited-edge'],
  };

  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().updateFlow('draft-flow', 'edited yaml'),
    () => {
      toastEvents.push({message: 'Flow saved', type: 'success'});
    },
  );

  assert.equal(confirmed, false);
  assert.deepEqual(editor, {
    selectedFlowId: 'draft-flow',
    nodes: ['edited-node'],
    edges: ['edited-edge'],
  });
  assertOnlyFailureFeedback();
});

test('rejected flow delete keeps the selection and graph without success feedback', async () => {
  const editor = {
    selectedFlowId: 'draft-flow' as string | null,
    nodes: ['draft-node'],
    edges: ['draft-edge'],
  };

  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().deleteFlow('draft-flow'),
    () => {
      editor.selectedFlowId = null;
      editor.nodes = [];
      editor.edges = [];
      toastEvents.push({message: 'Flow deleted', type: 'success'});
    },
  );

  assert.equal(confirmed, false);
  assert.deepEqual(editor, {
    selectedFlowId: 'draft-flow',
    nodes: ['draft-node'],
    edges: ['draft-edge'],
  });
  assert.deepEqual(useAppStore.getState().flows, [
    {id: 'draft-flow', name: 'draft.flow.yaml', content: 'draft yaml'},
  ]);
  assertOnlyFailureFeedback();
});

test('rejected profile update keeps the edited form without success feedback', async () => {
  const editedForm: Profile = {
    ...originalProfile,
    username: 'Edited user',
    job: 'Edited role',
  };

  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().updateProfile(editedForm),
    () => {
      toastEvents.push({message: 'Settings saved', type: 'success'});
    },
  );

  assert.equal(confirmed, false);
  assert.equal(editedForm.username, 'Edited user');
  assert.equal(editedForm.job, 'Edited role');
  assert.deepEqual(useAppStore.getState().profile, originalProfile);
  assertOnlyFailureFeedback();
});

test('rejected pack toggle keeps its confirmed state without success feedback', async () => {
  const confirmed = await runConfirmedMutation(
    () => useAppStore.getState().togglePack('defaultspack'),
    () => {
      toastEvents.push({message: 'Defaults Pack disabled', type: 'success'});
    },
  );

  assert.equal(confirmed, false);
  assert.equal(useAppStore.getState().packs[0]?.enabled, true);
  assertOnlyFailureFeedback();
});
