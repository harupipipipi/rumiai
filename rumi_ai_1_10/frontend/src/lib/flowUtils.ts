/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import yaml from 'js-yaml';
import type { Node, Edge } from '@xyflow/react';
import type { AppNode, TriggerNodeData, StepNodeData } from '@/src/lib/types';

interface FlowTrigger {
  type: string;
}

interface FlowStep {
  id: string;
  type: string;
  inputs?: Record<string, unknown>;
}

interface FlowDocument {
  trigger?: FlowTrigger;
  steps?: FlowStep[];
}

export function nodesToYaml(nodes: Node[], edges: Edge[]): string {
  try {
    const triggerNode = nodes.find(n => n.type === 'trigger');
    const stepNodes = nodes.filter(n => n.type === 'step' && n.data.type !== 'reroute');

    const sortedSteps = [...stepNodes].sort((a, b) => a.position.y - b.position.y);

    const flowObj: FlowDocument = {};

    if (triggerNode) {
      const triggerData = triggerNode.data as TriggerNodeData;
      flowObj.trigger = {
        type: triggerData.type || 'on_setup',
      };
    }

    if (sortedSteps.length > 0) {
      flowObj.steps = sortedSteps.map(step => {
        const stepData = step.data as StepNodeData;
        const result: FlowStep = {
          id: stepData.id || 'step',
          type: stepData.type || 'action',
        };
        if (stepData.inputs && Object.keys(stepData.inputs).length > 0) {
          result.inputs = stepData.inputs;
        }
        return result;
      });
    }

    return yaml.dump(flowObj, { indent: 2 });
  } catch (e) {
    console.error('YAML generation error', e);
    return '# Error generating YAML';
  }
}

export function yamlToNodes(yamlStr: string): { nodes: AppNode[], edges: Edge[] } {
  const nodes: AppNode[] = [];
  const edges: Edge[] = [];

  try {
    const parsed = yaml.load(yamlStr) as FlowDocument | null;
    if (!parsed) return { nodes, edges };

    let currentY = 50;
    let lastNodeId = '';

    if (parsed.trigger) {
      const triggerId = 'node-trigger';
      nodes.push({
        id: triggerId,
        type: 'trigger',
        position: { x: 250, y: currentY },
        data: { type: parsed.trigger.type || 'on_setup' },
      });
      lastNodeId = triggerId;
      currentY += 100;
    }

    if (parsed.steps && Array.isArray(parsed.steps)) {
      parsed.steps.forEach((step, index) => {
        const stepId = `node-step-${index}`;
        nodes.push({
          id: stepId,
          type: 'step',
          position: { x: 250, y: currentY },
          data: {
            id: step.id || `step_${index}`,
            type: step.type || 'action',
            inputs: step.inputs || {},
          },
        });

        if (lastNodeId) {
          edges.push({
            id: `edge-${lastNodeId}-${stepId}`,
            source: lastNodeId,
            target: stepId,
            animated: true,
          });
        }

        lastNodeId = stepId;
        currentY += 100;
      });
    }

    const endId = 'node-end';
    nodes.push({
      id: endId,
      type: 'end',
      position: { x: 250, y: currentY },
      data: {},
    });

    if (lastNodeId) {
      edges.push({
        id: `edge-${lastNodeId}-${endId}`,
        source: lastNodeId,
        target: endId,
        animated: true,
      });
    }

    return { nodes, edges };
  } catch (e) {
    console.error('YAML parsing error', e);
    return { nodes, edges };
  }
}
