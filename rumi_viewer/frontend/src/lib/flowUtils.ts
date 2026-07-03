import * as yaml from 'js-yaml';
import type { Edge, Node } from '@xyflow/react';
import type { AppNode, FlowDocumentMeta, FlowPort, StepNodeData, TriggerNodeData } from '@/src/lib/types';
import {
  buildExecutionPlan,
  clonePorts,
  createDefaultFlowGraph,
  createEndNode,
  createStartNode,
  defaultPortsForStep,
  DEFAULT_BASE_PACK,
  DEFAULT_GRAPH_PHASE,
  sanitizeNode,
} from '@/src/lib/flowGraph';

interface FlowStep {
  id: string;
  phase?: string;
  priority?: number;
  type: string;
  input?: Record<string, unknown>;
}

interface FlowDocument {
  flow_id?: string;
  name?: string;
  description?: string;
  trigger?: {
    type?: string;
    config?: Record<string, unknown>;
  };
  phases?: string[];
  defaults?: Record<string, unknown>;
  steps?: FlowStep[];
  rumi_graph?: {
    version?: number;
    base_pack?: string;
    entrypoint_node_id?: string;
    nodes?: Node[];
    edges?: Edge[];
  };
}

export interface ParsedFlowDocument {
  nodes: AppNode[];
  edges: Edge[];
  meta: FlowDocumentMeta;
}

function deriveFlowId(meta: Partial<FlowDocumentMeta>): string {
  if (meta.flowId?.trim()) {
    return meta.flowId.trim();
  }
  return 'untitled';
}

function inferMeta(doc: FlowDocument, fallback?: Partial<FlowDocumentMeta>): FlowDocumentMeta {
  const defaults = (doc.defaults && typeof doc.defaults === 'object' ? doc.defaults : fallback?.defaults) ?? {
    fail_soft: true,
    on_missing_step: 'skip',
  };
  const basePack = doc.rumi_graph?.base_pack || fallback?.basePack || DEFAULT_BASE_PACK;
  return {
    flowId: String(doc.flow_id || fallback?.flowId || 'untitled'),
    name: doc.name || fallback?.name,
    description: doc.description || fallback?.description,
    phases: Array.isArray(doc.phases) && doc.phases.length > 0 ? doc.phases.map(String) : [...(fallback?.phases ?? [DEFAULT_GRAPH_PHASE])],
    defaults,
    basePack,
  };
}

function createFallbackDocument(fallback?: Partial<FlowDocumentMeta>): ParsedFlowDocument {
  const graph = createDefaultFlowGraph(fallback?.basePack || DEFAULT_BASE_PACK);
  return {
    nodes: graph.nodes as AppNode[],
    edges: graph.edges,
    meta: {
      ...graph.meta,
      flowId: fallback?.flowId?.trim() || graph.meta.flowId,
      name: fallback?.name,
      description: fallback?.description,
      phases: fallback?.phases?.length ? [...fallback.phases] : graph.meta.phases,
      defaults: fallback?.defaults ?? graph.meta.defaults,
      basePack: fallback?.basePack || graph.meta.basePack,
    },
  };
}

function createNodesFromSimpleDocument(doc: FlowDocument, meta: FlowDocumentMeta): ParsedFlowDocument {
  const graph = createDefaultFlowGraph(meta.basePack);
  const nodes: AppNode[] = [
    createStartNode({ x: 120, y: 140 }, meta.basePack) as AppNode,
  ];
  const edges: Edge[] = [];

  if (doc.trigger?.type) {
    const startData = nodes[0].data as TriggerNodeData;
    startData.type = doc.trigger.type;
    startData.title = doc.trigger.type === 'rumi_start' ? 'rumi_start' : doc.trigger.type;
  }

  let previous = nodes[0];
  let currentY = 110;

  (doc.steps ?? []).forEach((step, index) => {
    const nodeId = `node-step-${index}`;
    const stepPorts = clonePorts(
      ((step.input as { ports?: FlowPort[] } | undefined)?.ports) ?? defaultPortsForStep(step.id),
    );
    const node: AppNode = {
      id: nodeId,
      type: 'step',
      position: { x: 580, y: currentY + index * 150 },
      data: {
        id: step.id || `step_${index}`,
        type: step.type || 'action',
        title: step.id || `step_${index}`,
        phase: step.phase || meta.phases[0] || DEFAULT_GRAPH_PHASE,
        description: (step.input as { description?: string } | undefined)?.description,
        inputs: (step.input as { payload?: Record<string, unknown> } | undefined)?.payload ?? {},
        ports: stepPorts,
      } satisfies StepNodeData,
    };
    nodes.push(node);

    const previousOutput = clonePorts((previous.data as { ports?: FlowPort[] }).ports).find((port) => port.direction === 'output');
    const nextInput = stepPorts.find((port) => port.direction === 'input');
    edges.push({
      id: `edge-${previous.id}-${nodeId}`,
      source: previous.id,
      target: nodeId,
      sourceHandle: previousOutput?.id,
      targetHandle: nextInput?.id,
      animated: true,
    });
    previous = node;
  });

  const endNode = createEndNode({ x: 1040, y: Math.max(180, currentY + (doc.steps?.length ?? 0) * 150) }) as AppNode;
  nodes.push(endNode);
  const endInput = clonePorts((endNode.data as { ports?: FlowPort[] }).ports).find((port) => port.direction === 'input');
  const previousOutput = clonePorts((previous.data as { ports?: FlowPort[] }).ports).find((port) => port.direction === 'output');
  edges.push({
    id: `edge-${previous.id}-${endNode.id}`,
    source: previous.id,
    target: endNode.id,
    sourceHandle: previousOutput?.id,
    targetHandle: endInput?.id,
    animated: true,
  });

  return {
    nodes,
    edges,
    meta,
  };
}

export function nodesToYaml(nodes: Node[], edges: Edge[], meta?: Partial<FlowDocumentMeta>): string {
  try {
    const flowId = deriveFlowId(meta);
    const startNode = nodes.find((node) => node.type === 'trigger');
    const executionPlan = buildExecutionPlan(nodes, edges);
    const phases = meta?.phases?.length ? meta.phases : [DEFAULT_GRAPH_PHASE];
    const compiledSteps = executionPlan.map((stepNode, index) => {
      const stepData = stepNode.data as StepNodeData;
      return {
        id: stepData.id || stepNode.id,
        phase: stepData.phase || phases[0] || DEFAULT_GRAPH_PHASE,
        priority: (index + 1) * 10,
        type: stepData.type || 'action',
        input: {
          description: stepData.description || '',
          payload: stepData.inputs || {},
          ports: clonePorts(stepData.ports),
        },
      };
    });

    const doc: FlowDocument = {
      flow_id: flowId,
      name: meta?.name || flowId,
      description: meta?.description || 'Graph editor flow',
      phases,
      defaults: (meta?.defaults as Record<string, unknown> | undefined) ?? {
        fail_soft: true,
        on_missing_step: 'skip',
      },
      steps: compiledSteps,
      rumi_graph: {
        version: 1,
        base_pack: (startNode?.data as TriggerNodeData | undefined)?.basePack || meta?.basePack || DEFAULT_BASE_PACK,
        entrypoint_node_id: startNode?.id,
        nodes: nodes.map(sanitizeNode),
        edges: edges.map((edge) => ({
          ...edge,
          data: edge.data ?? {},
        })),
      },
    };

    return yaml.dump(doc, { indent: 2, lineWidth: 120, noRefs: true });
  } catch (error) {
    console.error('YAML generation error', error);
    return '# Error generating YAML';
  }
}

export function yamlToNodes(yamlStr: string, fallbackMeta?: Partial<FlowDocumentMeta>): ParsedFlowDocument {
  if (!yamlStr.trim()) {
    return createFallbackDocument(fallbackMeta);
  }

  try {
    const parsed = yaml.load(yamlStr) as FlowDocument | null;
    if (!parsed || typeof parsed !== 'object') {
      return createFallbackDocument(fallbackMeta);
    }

    const meta = inferMeta(parsed, fallbackMeta);

    if (parsed.rumi_graph?.nodes?.length) {
      const nodes = parsed.rumi_graph.nodes.map((node) => sanitizeNode(node)) as AppNode[];
      const edges = (parsed.rumi_graph.edges ?? []).map((edge) => ({
        ...edge,
        animated: edge.animated ?? true,
      }));
      return {
        nodes,
        edges,
        meta,
      };
    }

    return createNodesFromSimpleDocument(parsed, meta);
  } catch (error) {
    console.error('YAML parsing error', error);
    return createFallbackDocument(fallbackMeta);
  }
}
