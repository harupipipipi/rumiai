import type { Node } from '@xyflow/react';

/** Execution status for flow nodes during simulation */
export type ExecutionStatus = 'pending' | 'running' | 'success' | 'error' | undefined;

export type PortDirection = 'input' | 'output';

export interface FlowPort {
  id: string;
  label: string;
  direction: PortDirection;
  contracts: string[];
  description?: string;
  allowMultiple?: boolean;
}

/** Data shape for Trigger nodes */
export interface TriggerNodeData {
  type: string;
  title?: string;
  ports?: FlowPort[];
  basePack?: string;
  executionStatus?: ExecutionStatus;
  [key: string]: unknown;
}

/** Data shape for Step nodes */
export interface StepNodeData {
  id: string;
  type: string;
  title?: string;
  phase?: string;
  ports?: FlowPort[];
  description?: string;
  inputs?: Record<string, unknown>;
  executionStatus?: ExecutionStatus;
  [key: string]: unknown;
}

/** Data shape for End nodes */
export interface EndNodeData {
  title?: string;
  ports?: FlowPort[];
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
  ports?: FlowPort[];
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

export interface FlowDocumentMeta {
  flowId: string;
  name?: string;
  description?: string;
  phases: string[];
  defaults: Record<string, unknown>;
  basePack: string;
}
