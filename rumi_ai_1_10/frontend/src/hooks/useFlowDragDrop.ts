import type { DragEvent, MouseEvent as ReactMouseEvent, RefObject } from 'react';
import { useState, useCallback, useRef } from 'react';
import type { Node, Edge, ReactFlowInstance } from '@xyflow/react';
import type { FlowPort } from '@/src/lib/types';
import { createPort, pickCompatibleHandles } from '@/src/lib/flowGraph';

interface UseFlowDragDropParams {
  nodes: Node[];
  edges: Edge[];
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void;
  saveHistory: () => void;
  reactFlowInstance: ReactFlowInstance | null;
  reactFlowWrapper: RefObject<HTMLDivElement | null>;
}

export function useFlowDragDrop({
  nodes,
  edges,
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
    const handler = (e: globalThis.PointerEvent | globalThis.MouseEvent) => {
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
    (_event: ReactMouseEvent, node: Node) => {
      setIsDraggingNode(false);
      setIsOverDeleteZone(false);

      const wrapper = reactFlowWrapper.current;
      if (!wrapper) return;
      const bounds = wrapper.getBoundingClientRect();

      if (mousePosRef.current.y > bounds.bottom - 80) {
        saveHistory();
        setNodes((existing) => existing.filter((candidate) => candidate.id !== node.id));
        setEdges((existing) => existing.filter((edge) => edge.source !== node.id && edge.target !== node.id));
      }
    },
    [reactFlowWrapper, saveHistory, setEdges, setNodes],
  );

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((event: DragEvent) => {
    event.preventDefault();

    const type = event.dataTransfer.getData('application/reactflow');
    const stepId = event.dataTransfer.getData('stepId');
    const title = event.dataTransfer.getData('stepTitle');
    const serializedPorts = event.dataTransfer.getData('stepPorts');

    if (!type || !reactFlowInstance) return;

    const position = reactFlowInstance.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    let ports: FlowPort[];
    try {
      ports = serializedPorts ? JSON.parse(serializedPorts) as FlowPort[] : [];
    } catch {
      ports = [];
    }
    if (ports.length === 0) {
      ports = [
        createPort('input', 'input', [], { id: 'input-main' }),
        createPort('output', 'output', [], { id: 'output-main', allowMultiple: true }),
      ];
    }

    const newNode: Node = {
      id: `step-${Date.now()}`,
      type,
      position,
      data: {
        id: stepId,
        type: 'action',
        title: title || stepId,
        ports,
      },
    };

    const threshold = 180;
    let closestNode: Node | null = null;
    let minDistance = Infinity;

    nodes.forEach((node) => {
      const dx = node.position.x - position.x;
      const dy = node.position.y - position.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (distance < minDistance && distance < threshold) {
        minDistance = distance;
        closestNode = node;
      }
    });

    saveHistory();
    setNodes((existing) => existing.concat(newNode));

    if (closestNode) {
      const candidate = closestNode as Node;
      const isIncoming = candidate.position.x > position.x;
      const sourceNode = isIncoming ? newNode : candidate;
      const targetNode = isIncoming ? candidate : newNode;
      const handles = pickCompatibleHandles(sourceNode, targetNode, edges);
      if (handles) {
        setEdges((existing) => existing.concat({
          id: `e-${sourceNode.id}-${targetNode.id}-${Date.now()}`,
          source: sourceNode.id,
          target: targetNode.id,
          sourceHandle: handles.sourceHandle ?? undefined,
          targetHandle: handles.targetHandle ?? undefined,
          animated: true,
        }));
      }
    }
  }, [edges, nodes, reactFlowInstance, saveHistory, setEdges, setNodes]);

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
