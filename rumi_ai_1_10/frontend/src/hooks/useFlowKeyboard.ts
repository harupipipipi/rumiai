/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef } from 'react';
import type { Node, ReactFlowInstance } from '@xyflow/react';

interface UseFlowKeyboardParams {
  nodes: Node[];
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  saveHistory: () => void;
  undo: () => void;
  redo: () => void;
  execute: () => void;
  reactFlowInstance: ReactFlowInstance | null;
  setMenuPos: (pos: { x: number; y: number } | null) => void;
}

export function useFlowKeyboard({
  nodes,
  setNodes,
  saveHistory,
  undo,
  redo,
  execute,
  reactFlowInstance,
  setMenuPos,
}: UseFlowKeyboardParams) {
  const pressedKeys = useRef<Set<string>>(new Set());
  const copiedNodesRef = useRef<Node[]>([]);

  // Refs for stable closures (H-1)
  const nodesRef = useRef(nodes);
  const saveHistoryRef = useRef(saveHistory);
  const undoRef = useRef(undo);
  const redoRef = useRef(redo);
  const executeRef = useRef(execute);
  const reactFlowInstanceRef = useRef(reactFlowInstance);
  const setNodesRef = useRef(setNodes);
  const setMenuPosRef = useRef(setMenuPos);

  nodesRef.current = nodes;
  saveHistoryRef.current = saveHistory;
  undoRef.current = undo;
  redoRef.current = redo;
  executeRef.current = execute;
  reactFlowInstanceRef.current = reactFlowInstance;
  setNodesRef.current = setNodes;
  setMenuPosRef.current = setMenuPos;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      pressedKeys.current.add(e.key.toLowerCase());

      if (e.key === 'F7') {
        e.preventDefault();
        executeRef.current();
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        saveHistoryRef.current();
        setNodesRef.current(nds => {
          const selected = nds.filter(n => n.selected);
          const newNodes = selected.map(n => ({
            ...n,
            id: `${n.type}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
            position: { x: n.position.x + 50, y: n.position.y + 50 },
            selected: true,
          }));
          return nds.map(n => ({ ...n, selected: false })).concat(newNodes);
        });
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'c') {
        copiedNodesRef.current = nodesRef.current.filter(n => n.selected);
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'v') {
        if (copiedNodesRef.current.length > 0) {
          saveHistoryRef.current();
          setNodesRef.current(nds => {
            const newNodes = copiedNodesRef.current.map(n => ({
              ...n,
              id: `${n.type}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
              position: { x: n.position.x + 50, y: n.position.y + 50 },
              selected: true,
            }));
            return nds.map(n => ({ ...n, selected: false })).concat(newNodes);
          });
        }
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        setMenuPosRef.current({ x: window.innerWidth / 2 - 128, y: window.innerHeight / 2 - 150 });
      }
      if (e.key.toLowerCase() === 'q') {
        saveHistoryRef.current();
        setNodesRef.current(nds => {
          const selected = nds.filter(n => n.selected);
          if (selected.length < 2) return nds;
          const refX = selected[0].position.x;
          return nds.map(n => n.selected ? { ...n, position: { ...n.position, x: refX } } : n);
        });
      }
      if (e.key === 'Home') {
        reactFlowInstanceRef.current?.fitView({ duration: 800 });
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        undoRef.current();
      }
      if (e.ctrlKey && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redoRef.current();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      pressedKeys.current.delete(e.key.toLowerCase());
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []); // Empty deps — all values accessed via refs (H-1)

  return { pressedKeys };
}
