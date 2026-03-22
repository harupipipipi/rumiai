/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useCallback, useRef } from 'react';
import type { Node, Edge } from '@xyflow/react';

const MAX_HISTORY = 50;

export interface FlowHistoryActions {
  saveHistory: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function useFlowHistory(
  nodes: Node[],
  edges: Edge[],
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void,
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void,
): FlowHistoryActions {
  const [past, setPast] = useState<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const [future, setFuture] = useState<{ nodes: Node[]; edges: Edge[] }[]>([]);

  // Refs for stable closures (H-1)
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const pastRef = useRef(past);
  const futureRef = useRef(future);
  nodesRef.current = nodes;
  edgesRef.current = edges;
  pastRef.current = past;
  futureRef.current = future;

  const saveHistory = useCallback(() => {
    setPast(p => [...p, { nodes: nodesRef.current, edges: edgesRef.current }].slice(-MAX_HISTORY));
    setFuture([]);
  }, []);

  const undo = useCallback(() => {
    const p = pastRef.current;
    if (p.length === 0) return;
    const previous = p[p.length - 1];
    setFuture(f => [{ nodes: nodesRef.current, edges: edgesRef.current }, ...f]);
    setPast(p.slice(0, -1));
    setNodes(previous.nodes);
    setEdges(previous.edges);
  }, [setNodes, setEdges]);

  const redo = useCallback(() => {
    const f = futureRef.current;
    if (f.length === 0) return;
    const next = f[0];
    setPast(p => [...p, { nodes: nodesRef.current, edges: edgesRef.current }]);
    setFuture(f.slice(1));
    setNodes(next.nodes);
    setEdges(next.edges);
  }, [setNodes, setEdges]);

  return {
    saveHistory,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  };
}
