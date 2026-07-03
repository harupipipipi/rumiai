import assert from 'node:assert/strict';
import test from 'node:test';
import {ReactFlowProvider, type NodeProps} from '@xyflow/react';
import {renderToStaticMarkup} from 'react-dom/server';

import {StepNode} from '@/src/components/flow/CustomNodes';
import type {FlowPort, StepNode as StepNodeType} from '@/src/lib/types';

const densePorts = [
  {
    id: 'input-super-long-localized-port-name-for-user-profile-handoff',
    label: '超長い入力ポート名_ユーザープロファイル引き継ぎと権限検査',
    direction: 'input',
    contracts: [
      'application/vnd.rumi.profile-context+json',
      'application/vnd.rumi.permissions.audit.v2+json',
    ],
    description: 'Full disclosure should keep this localized label readable to assistive tech.',
  },
  {
    id: 'output-contract-with-very-long-provider-payload-name',
    label: 'provider.result.with.really.long.contract.name.and.localized.summary',
    direction: 'output',
    contracts: [
      'application/vnd.rumi.tool-result.long-provider-payload+json',
      'application/vnd.rumi.trace.span-with-extra-debug-context+json',
      'text/markdown; charset=utf-8',
    ],
    description: 'A dense output port with multiple contracts.',
  },
] satisfies FlowPort[];

test('flow nodes expose full dense labels while rendering compact port text', () => {
  const markup = renderToStaticMarkup(
    <ReactFlowProvider>
      <StepNode
        {...({
          data: {
            id: 'defaultspack.research.deeply_nested_provider_chain_with_extremely_long_identifier',
            type: 'action',
            title: 'Localized Research Step / 多言語ラベル検証ノード',
            phase: 'graph.integration.validation.phase.with.long.name',
            description: 'Runs the dense React Flow label fixture with long pack ids, port names, and contracts.',
            ports: densePorts,
          },
          selected: false,
        } as NodeProps<StepNodeType>)}
      />
    </ReactFlowProvider>,
  );

  assert.match(markup, /role="group"/);
  assert.match(markup, /data-flow-node-label="Localized Research Step \/ 多言語ラベル検証ノード"/);
  assert.match(markup, /data-flow-port-label="超長い入力ポート名_ユーザープロファイル引き継ぎと権限検査"/);
  assert.match(markup, /application\/vnd\.rumi\.profile-context\+json/);
  assert.match(markup, /application\/vnd\.rumi\.tool-result\.long-provider-payload\+json \+2/);
  assert.match(markup, /Full disclosure should keep this localized label readable to assistive tech\./);
  assert.doesNotMatch(markup, /\btruncate\b/);
});
