import assert from 'node:assert/strict';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import test from 'node:test';

import {OperationInputForm} from './OperationInputForm';
import type {RuntimeOperationDescriptor} from '@/src/lib/runtimeSurface';

const digest = (character: string): string => `sha256:${character.repeat(64)}`;

function operation(invokable = true): RuntimeOperationDescriptor {
  return {
    operation_id: 'conversation.turn',
    contract_id: 'conversation.v1',
    owner_pack_id: 'conversation-pack',
    contribution_id: 'conversation-contribution',
    target_provider_id: 'tobkiri.provider',
    artifact_digest: digest('a'),
    invocation_contribution_id: invokable ? 'conversation-invocation' : null,
    invocation_owner_pack_id: invokable ? 'conversation-pack' : null,
    invocation_catalog_hash: invokable ? digest('c') : null,
    invocation_reason: invokable ? null : 'Host readiness attestation is stale.',
    invokable,
    catalog_digest: digest('c'),
    function_id: 'conversation.turn',
    function_principal_id: 'principal.conversation.turn',
    caller_function_id: 'caller.conversation.turn',
    authority_reference: 'authority://conversation/turn',
    route: {
      contract_id: 'conversation.v1',
      operation_id: 'conversation.turn',
      function_id: 'conversation.turn',
      provider_pack_id: 'conversation-pack',
    },
    schema: {
      input_schema: {
        type: 'object',
        required: ['prompt'],
        properties: {
          prompt: {type: 'string', title: 'Prompt', default: 'hello'},
          temperature: {type: 'number', default: 0.2, title: 'Temperature'},
        },
      },
    },
    input_schema: {
      type: 'object',
      required: ['prompt'],
      properties: {
        prompt: {type: 'string', title: 'Prompt', default: 'hello'},
        temperature: {type: 'number', default: 0.2, title: 'Temperature'},
      },
    },
  };
}

function createDom(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  return {dom, container, root: createRoot(container)};
}

test('OperationInputForm renders the declared schema and invokes the exact payload', async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const {dom, container, root} = createDom();
  let received: Record<string, unknown> | null = null;
  try {
    await act(async () => {
      root.render(
        <OperationInputForm
          operation={operation()}
          busy={false}
          onInvoke={async (payload) => { received = payload; }}
        />,
      );
    });
    assert.match(container.textContent ?? '', /Schema-driven input/);
    const submit = [...container.querySelectorAll('button')].find((button) => button.type === 'submit');
    assert.ok(submit);
    const form = container.querySelector<HTMLFormElement>('form');
    assert.ok(form);

    await act(async () => {
      form.dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true}));
    });
    assert.deepEqual(received, {prompt: 'hello', temperature: 0.2});
  } finally {
    act(() => root.unmount());
    dom.window.close();
    Object.defineProperty(globalThis, 'window', {value: previousWindow, configurable: true});
    Object.defineProperty(globalThis, 'document', {value: previousDocument, configurable: true});
  }
});

test('OperationInputForm disables invocation when Host readiness is not authoritative', async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const {dom, container, root} = createDom();
  try {
    await act(async () => {
      root.render(
        <OperationInputForm operation={operation(false)} busy={false} onInvoke={async () => {}} />,
      );
    });
    const submit = [...container.querySelectorAll('button')].find((button) => button.type === 'submit');
    assert.ok(submit);
    assert.equal(submit.disabled, true);
    assert.match(container.textContent ?? '', /Invoke declared operation/);
  } finally {
    act(() => root.unmount());
    dom.window.close();
    Object.defineProperty(globalThis, 'window', {value: previousWindow, configurable: true});
    Object.defineProperty(globalThis, 'document', {value: previousDocument, configurable: true});
  }
});
