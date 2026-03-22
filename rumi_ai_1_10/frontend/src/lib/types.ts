/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import type { Node } from '@xyflow/react';

/** Execution status for flow nodes during simulation */
export type ExecutionStatus = 'pending' | 'running' | 'success' | 'error' | undefined;

/** Data shape for Trigger nodes */
export interface TriggerNodeData {
  type: string;
  executionStatus?: ExecutionStatus;
  [key: string]: unknown;
}

/** Data shape for Step nodes */
export interface StepNodeData {
  id: string;
  type: string;
  description?: string;
  inputs?: Record<string, unknown>;
  executionStatus?: ExecutionStatus;
  [key: string]: unknown;
}

/** Data shape for End nodes */
export interface EndNodeData {
  executionStatus?: ExecutionStatus;
  [key: string]: unknown;
}

/** Union of all node data types */
export type FlowNodeData = TriggerNodeData | StepNodeData | EndNodeData;

/** Typed node variants */
export type TriggerNode = Node<TriggerNodeData, 'trigger'>;
export type StepNode = Node<StepNodeData, 'step'>;
export type EndNode = Node<EndNodeData, 'end'>;

/** Union of all app node types */
export type AppNode = TriggerNode | StepNode | EndNode;

/** Available step definition for the block bar */
export interface AvailableStep {
  id: string;
  name: string;
  pack: string;
  description: string;
}

/** Execution result for a single step */
export interface StepExecutionResult {
  name: string;
  status: 'success' | 'error';
  duration: string;
}

/** Overall execution result */
export interface FlowExecutionResult {
  status: 'success' | 'error';
  duration: string;
  steps: StepExecutionResult[];
}
