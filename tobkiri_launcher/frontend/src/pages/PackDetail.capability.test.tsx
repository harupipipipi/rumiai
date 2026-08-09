import assert from 'node:assert/strict';
import test from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {MemoryRouter, Route, Routes} from 'react-router';

import {type Pack, useAppStore} from '@/src/store';
import type {ApiDynamicFrontendCatalog} from '@/src/lib/apiTypes';
import {PackDetail} from './PackDetail';

const operation = {
  operationId: 'rumi_file_inspect_pack.file-inspect',
  contractId: 'tobkiri.service.file.inspect.v1',
  providerId: 'rumi_file_inspect_pack.file-inspect.service',
  capabilities: ['file.inspect'],
  inputSchema: {},
  invokable: true,
};

const pack: Pack = {
  id: 'rumi_file_inspect_pack',
  name: 'Tobkiri File Inspect',
  version: '1.0.0',
  type: 'community',
  installed: true,
  enabled: true,
  description: 'Inspect workspace files.',
  artifactDigest: 'sha256:artifact',
  profileId: 'profile-a',
  workspaceId: 'workspace-a',
  profileRevision: 'sha256:profile',
  planDigest: 'sha256:plan',
  catalogRevision: 'catalog-a',
  approvalStatus: 'approved',
  approvalReason: null,
  approved: true,
  hashValid: true,
  criticalChanged: false,
  approvalIssues: [],
  capabilities: [{name: 'file.inspect', description: 'Inspect files.'}],
  operations: [operation],
  flows: [operation.operationId],
  dependencies: [],
};

const catalog: ApiDynamicFrontendCatalog = {
  version: 'rumi.ui.contribution.v1',
  profile_id: 'profile-a',
  profile_revision: 'sha256:profile',
  plan_hash: 'sha256:plan',
  contributions: [{
    contribution_id: 'file-inspect',
    owner_pack_id: pack.id,
    label: operation.operationId,
    operation_id: operation.operationId,
    action_contract: operation.contractId,
  }],
  diagnostics: [],
  quarantined_pack_ids: [],
  catalog_hash: 'sha256:catalog',
};

function createSurface(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: `http://localhost/packs/${pack.id}`,
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  return {dom, container, root: createRoot(container)};
}

async function renderDetail(root: Root): Promise<void> {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[`/packs/${pack.id}`]}>
        <Routes>
          <Route path="/packs/:id" element={<PackDetail />} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

function configureStore(currentPack: Pack): void {
  useAppStore.setState({
    packs: [currentPack],
    packsLoading: false,
    packsError: null,
    frontendCatalog: catalog,
    frontendCatalogLoading: false,
    frontendCatalogError: null,
    packOperationPending: {},
    loadPacks: async () => {},
    loadFrontendCatalog: async () => {},
    invokePackOperation: async () => ({ok: true}),
    installPack: async () => {},
    approvePack: async () => {},
    revokePackApproval: async () => {},
    togglePack: async () => false,
  });
}

test('PackDetail displays declared capabilities and the verified file operation surface', async () => {
  const previousState = useAppStore.getState();
  const {dom, container, root} = createSurface();
  configureStore(pack);

  try {
    await renderDetail(root);
    assert.match(container.textContent ?? '', /file\.inspect/);
    assert.match(container.textContent ?? '', /rumi_file_inspect_pack\.file-inspect/);
    assert.match(container.textContent ?? '', /tobkiri\.service\.file\.inspect\.v1/);
    assert.ok(container.querySelector('#file-inspect-path'));
    assert.equal(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled, true);
  } finally {
    act(() => root.unmount());
    useAppStore.setState(previousState, true);
    dom.window.close();
  }
});

test('PackDetail keeps the file operation unavailable after approval revocation', async () => {
  const previousState = useAppStore.getState();
  const {dom, container, root} = createSurface();
  configureStore({
    ...pack,
    enabled: false,
    approved: false,
    approvalStatus: 'revoked',
    approvalReason: 'approval_revoked',
    approvalIssues: ['approval_revoked'],
  });

  try {
    await renderDetail(root);
    assert.match(container.textContent ?? '', /Approval revoked/);
    assert.match(container.textContent ?? '', /approval is revoked/i);
    assert.equal(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled, true);
  } finally {
    act(() => root.unmount());
    useAppStore.setState(previousState, true);
    dom.window.close();
  }
});
