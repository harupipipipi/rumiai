import { useState, useCallback, useRef } from 'react';
import type { Node, Edge, ReactFlowInstance } from '@xyflow/react';

interface UseFlowDragDropParams {
  nodes: Node[];
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void;
  saveHistory: () => void;
  reactFlowInstance: ReactFlowInstance | null;
  reactFlowWrapper: React.RefObject<HTMLDivElement | null>;
}

export function useFlowDragDrop({
  nodes,
  setNodes,
  setEdges,
  saveHistory,
  reactFlowInstance,
  reactFlowWrapper,
}: UseFlowDragDropParams) {
  const [isDraggingNode, setIsDraggingNode] = useState(false);
  const [isOverDeleteZone, setIsOverDeleteZone] = useState(false);
  const mousePosRef = useRef({ x: 0, y: 0 });

  const setupPointerTracking = useCallback(() => {
    const handler = (e: PointerEvent | MouseEvent) => {
      mousePosRef.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('pointermove', handler, true);
    window.addEventListener('mousemove', handler, true);
    return () => {
      window.removeEventListener('pointermove', handler, true);
      window.removeEventListener('mousemove', handler, true);
    };
  }, []);

  const onNodeDragStart = useCallback(() => {
    setIsDraggingNode(true);
    setIsOverDeleteZone(false);
  }, []);

  const onNodeDrag = useCallback(() => {
    const wrapper = reactFlowWrapper.current;
    if (!wrapper) return;
    const bounds = wrapper.getBoundingClientRect();
    setIsOverDeleteZone(mousePosRef.current.y > bounds.bottom - 80);
  }, [reactFlowWrapper]);

  const onNodeDragStop = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      setIsDraggingNode(false);
      setIsOverDeleteZone(false);

      const wrapper = reactFlowWrapper.current;
      if (!wrapper) return;
      const bounds = wrapper.getBoundingClientRect();

      if (mousePosRef.current.y > bounds.bottom - 80) {
        saveHistory();
        setNodes(nds => nds.filter(n => n.id !== node.id));
        setEdges(eds => eds.filter(e => e.source !== node.id && e.target !== node.id));
      }
    },
    [reactFlowWrapper, saveHistory, setNodes, setEdges]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      const stepId = event.dataTransfer.getData('stepId');

      if (!type || !reactFlowInstance) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode: Node = {
        id: `step-${Date.now()}`,
        type,
        position,
        data: { id: stepId, type: 'action' },
      };

      const threshold = 150;
      let closestNode: Node | null = null;
      let minDistance = Infinity;

      nodes.forEach(node => {
        const dx = node.position.x - position.x;
        const dy = node.position.y - position.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < minDistance && distance < threshold) {
          minDistance = distance;
          closestNode = node;
        }
      });

      setNodes(nds => nds.concat(newNode));

      if (closestNode) {
        const cn = closestNode as Node;
        const isTarget = cn.position.y > position.y;
        const newEdge: Edge = {
          id: `e-${isTarget ? newNode.id : cn.id}-${isTarget ? cn.id : newNode.id}`,
          source: isTarget ? newNode.id : cn.id,
          target: isTarget ? cn.id : newNode.id,
          animated: true,
        };
        setEdges(eds => eds.concat(newEdge));
      }
    },
    [reactFlowInstance, nodes, setNodes, setEdges],
  );

  return {
    isDraggingNode,
    isOverDeleteZone,
    mousePosRef,
    setupPointerTracking,
    onNodeDragStart,
    onNodeDrag,
    onNodeDragStop,
    onDragOver,
    onDrop,
  };
}
