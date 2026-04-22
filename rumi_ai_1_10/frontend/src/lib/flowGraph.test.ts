import test from 'node:test';
import assert from 'node:assert/strict';
import type { Edge, Node } from '@xyflow/react';
import { createPort, createStartNode, createStepNode, validateConnection } from './flowGraph';
import { nodesToYaml, yamlToNodes } from './flowUtils';

test('validateConnection accepts matching contracts', () => {
  const source = createStartNode();
  const target = createStepNode(
    {
      id: 'http.get',
      ports: [
        createPort('boot', 'input', ['flow.start'], { id: 'boot-in' }),
        createPort('response', 'output', ['http.response'], { id: 'http-out' }),
      ],
    },
    { x: 100, y: 100 },
  );

  const result = validateConnection(
    {
      source: source.id,
      target: target.id,
      sourceHandle: 'start-out',
      targetHandle: 'boot-in',
    },
    [source as Node, target as Node],
    [],
  );

  assert.equal(result.valid, true);
});

test('validateConnection rejects mismatched contracts', () => {
  const source = createStepNode(
    {
      id: 'http.get',
      ports: [createPort('response', 'output', ['http.response'], { id: 'out' })],
    },
    { x: 100, y: 100 },
  );
  const target = createStepNode(
    {
      id: 'log.info',
      ports: [createPort('request', 'input', ['command.python'], { id: 'in' })],
    },
    { x: 260, y: 100 },
  );

  const result = validateConnection(
    {
      source: source.id,
      target: target.id,
      sourceHandle: 'out',
      targetHandle: 'in',
    },
    [source as Node, target as Node],
    [],
  );

  assert.equal(result.valid, false);
  assert.match(result.reason ?? '', /規格/);
});

test('nodesToYaml and yamlToNodes preserve rumi_graph metadata', () => {
  const start = createStartNode();
  const step = createStepNode(
    {
      id: 'registry.load',
      title: 'registry.load',
      ports: [
        createPort('boot', 'input', ['flow.start'], { id: 'boot-in' }),
        createPort('registry', 'output', ['registry.ready'], { id: 'registry-out' }),
      ],
    },
    { x: 320, y: 140 },
  );
  const edges: Edge[] = [
    {
      id: 'e-1',
      source: start.id,
      target: step.id,
      sourceHandle: 'start-out',
      targetHandle: 'boot-in',
    },
  ];

  const yaml = nodesToYaml([start as Node, step as Node], edges, {
    flowId: 'rumi_start_demo',
    name: 'rumi_start_demo.flow.yaml',
    phases: ['graph'],
    defaults: { fail_soft: true, on_missing_step: 'skip' },
    basePack: 'basepack',
  });

  const parsed = yamlToNodes(yaml);

  assert.equal(parsed.meta.flowId, 'rumi_start_demo');
  assert.equal(parsed.meta.basePack, 'basepack');
  assert.equal(parsed.nodes.length, 2);
  assert.equal(parsed.edges.length, 1);
  assert.equal((parsed.nodes[0].data as { title?: string }).title, 'rumi_start');
});
