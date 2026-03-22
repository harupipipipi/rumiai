import { useState, useCallback, useRef } from 'react';
import type { Node } from '@xyflow/react';
import { useMountedRef } from './useMountedRef';
import type { FlowExecutionResult, StepExecutionResult } from '@/src/lib/types';

function delay(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms));
}

export interface FlowExecutionState {
  isExecuting: boolean;
  executionResult: FlowExecutionResult | null;
  execute: () => Promise<FlowExecutionResult | null>;
  clearResult: () => void;
}

export function useFlowExecution(
  nodes: Node[],
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void,
): FlowExecutionState {
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<FlowExecutionResult | null>(null);
  const mountedRef = useMountedRef();
  const isExecutingRef = useRef(false);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  const execute = useCallback(async (): Promise<FlowExecutionResult | null> => {
    // Guard against double execution (C-2)
    if (isExecutingRef.current) return null;
    isExecutingRef.current = true;
    setIsExecuting(true);

    // Set all nodes to pending
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, executionStatus: 'pending' } })));

    const currentNodes = nodesRef.current;
    const steps = currentNodes.filter(n => n.type === 'step' && n.data.type !== 'reroute');
    const results: StepExecutionResult[] = [];

    // Run trigger
    if (mountedRef.current) {
      setNodes(nds => nds.map(n => n.type === 'trigger' ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));
    }
    await delay(500);
    if (!mountedRef.current) { isExecutingRef.current = false; return null; }
    setNodes(nds => nds.map(n => n.type === 'trigger' ? { ...n, data: { ...n.data, executionStatus: 'success' } } : n));

    // Run steps
    for (let i = 0; i < steps.length; i++) {
      if (!mountedRef.current) { isExecutingRef.current = false; return null; }

      const step = steps[i];
      setNodes(nds => nds.map(n => n.id === step.id ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));

      await delay(800);
      if (!mountedRef.current) { isExecutingRef.current = false; return null; }

      const isSuccess = Math.random() > 0.1;
      setNodes(nds => nds.map(n => n.id === step.id ? { ...n, data: { ...n.data, executionStatus: isSuccess ? 'success' : 'error' } } : n));

      results.push({
        name: (step.data.id as string) || `step_${i}`,
        status: isSuccess ? 'success' : 'error',
        duration: `${(Math.random() * 1 + 0.1).toFixed(1)}s`,
      });

      if (!isSuccess) break;
    }

    // Run end node
    if (mountedRef.current && results.every(r => r.status === 'success')) {
      setNodes(nds => nds.map(n => n.type === 'end' ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));
      await delay(300);
      if (mountedRef.current) {
        setNodes(nds => nds.map(n => n.type === 'end' ? { ...n, data: { ...n.data, executionStatus: 'success' } } : n));
      }
    }

    const result: FlowExecutionResult = {
      status: results.every(r => r.status === 'success') ? 'success' : 'error',
      duration: '1.2s',
      steps: results,
    };

    if (mountedRef.current) {
      setIsExecuting(false);
      setExecutionResult(result);
    }
    isExecutingRef.current = false;
    return result;
  }, [setNodes, mountedRef]);

  const clearResult = useCallback(() => {
    setExecutionResult(null);
  }, []);

  return {
    isExecuting,
    executionResult,
    execute,
    clearResult,
  };
}
