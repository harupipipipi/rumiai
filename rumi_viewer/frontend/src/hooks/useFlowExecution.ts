import { useState, useCallback, useEffect, useRef } from 'react';
import type { Edge, Node } from '@xyflow/react';
import { useMountedRef } from './useMountedRef';
import type { FlowExecutionResult, StepExecutionResult } from '@/src/lib/types';
import { buildExecutionPlan } from '@/src/lib/flowGraph';

function delay(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms));
}

export interface FlowExecutionState {
  isExecuting: boolean;
  executionResult: FlowExecutionResult | null;
  execute: () => Promise<FlowExecutionResult | null>;
  isExecutingNow: () => boolean;
  cancel: () => void;
  clearResult: () => void;
}

export function useFlowExecution(
  nodes: Node[],
  edges: Edge[],
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void,
): FlowExecutionState {
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<FlowExecutionResult | null>(null);
  const mountedRef = useMountedRef();
  const isExecutingRef = useRef(false);
  const executionGenerationRef = useRef(0);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;

  const cancel = useCallback((): void => {
    executionGenerationRef.current += 1;
    isExecutingRef.current = false;
    if (mountedRef.current) {
      setIsExecuting(false);
    }
  }, [mountedRef]);

  useEffect(() => () => {
    executionGenerationRef.current += 1;
    isExecutingRef.current = false;
  }, []);

  const execute = useCallback(async (): Promise<FlowExecutionResult | null> => {
    // Guard against double execution (C-2)
    if (isExecutingRef.current) return null;
    isExecutingRef.current = true;
    const executionGeneration = executionGenerationRef.current + 1;
    executionGenerationRef.current = executionGeneration;
    setIsExecuting(true);

    const isCurrentExecution = (): boolean => (
      mountedRef.current
      && executionGenerationRef.current === executionGeneration
    );

    try {
      // Set all nodes to pending
      setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, executionStatus: 'pending' } })));

      const currentNodes = nodesRef.current;
      const steps = buildExecutionPlan(currentNodes, edgesRef.current)
        .filter((node) => node.data.type !== 'reroute');
      const results: StepExecutionResult[] = [];

      // Run trigger
      if (isCurrentExecution()) {
        setNodes(nds => nds.map(n => n.type === 'trigger' ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));
      }
      await delay(500);
      if (!isCurrentExecution()) return null;
      setNodes(nds => nds.map(n => n.type === 'trigger' ? { ...n, data: { ...n.data, executionStatus: 'success' } } : n));

      // Run steps
      for (let i = 0; i < steps.length; i++) {
        if (!isCurrentExecution()) return null;

        const step = steps[i];
        setNodes(nds => nds.map(n => n.id === step.id ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));

        await delay(800);
        if (!isCurrentExecution()) return null;

        const isSuccess = Math.random() > 0.1;
        setNodes(nds => nds.map(n => n.id === step.id ? { ...n, data: { ...n.data, executionStatus: isSuccess ? 'success' : 'error' } } : n));

        results.push({
          name: (step.data.title as string) || (step.data.id as string) || `step_${i}`,
          status: isSuccess ? 'success' : 'error',
          duration: `${(Math.random() * 1 + 0.1).toFixed(1)}s`,
        });

        if (!isSuccess) break;
      }

      // Run end node
      if (isCurrentExecution() && results.every(r => r.status === 'success')) {
        setNodes(nds => nds.map(n => n.type === 'end' ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));
        await delay(300);
        if (isCurrentExecution()) {
          setNodes(nds => nds.map(n => n.type === 'end' ? { ...n, data: { ...n.data, executionStatus: 'success' } } : n));
        }
      }

      if (!isCurrentExecution()) return null;
      const result: FlowExecutionResult = {
        status: results.every(r => r.status === 'success') ? 'success' : 'error',
        duration: '1.2s',
        steps: results,
      };

      setExecutionResult(result);
      return result;
    } finally {
      if (executionGenerationRef.current === executionGeneration) {
        isExecutingRef.current = false;
        if (mountedRef.current) {
          setIsExecuting(false);
        }
      }
    }
  }, [mountedRef, setNodes]);

  const isExecutingNow = useCallback((): boolean => isExecutingRef.current, []);

  const clearResult = useCallback(() => {
    setExecutionResult(null);
  }, []);

  return {
    isExecuting,
    executionResult,
    execute,
    isExecutingNow,
    cancel,
    clearResult,
  };
}
