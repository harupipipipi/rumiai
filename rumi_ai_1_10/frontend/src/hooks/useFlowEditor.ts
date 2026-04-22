import type { MouseEvent, RefObject } from 'react';
import { useState, useCallback } from 'react';
import type { Node, Edge, Connection, ReactFlowInstance } from '@xyflow/react';
import { addEdge, reconnectEdge } from '@xyflow/react';
import type { FlowPort } from '@/src/lib/types';
import {
  createPort,
  createUniquePort,
  ensureUniquePortId,
  pickCompatibleHandles,
  replaceNodePorts,
  syncEdgesForUpdatedPort,
  validateConnection,
} from '@/src/lib/flowGraph';

interface UseFlowEditorParams {
  nodes: Node[];
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  edges: Edge[];
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void;
  saveHistory: () => void;
  reactFlowInstance: ReactFlowInstance | null;
  pressedKeys: RefObject<Set<string>>;
  onInvalidConnection?: (reason: string) => void;
}

function defaultStepPayload(kind: string): Record<string, unknown> {
  return { id: kind, type: 'action', title: kind, ports: [] as FlowPort[] };
}

export function useFlowEditor({
  nodes,
  setNodes,
  edges,
  setEdges,
  saveHistory,
  reactFlowInstance,
  pressedKeys,
  onInvalidConnection,
}: UseFlowEditorParams) {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const [menuFilter, setMenuFilter] = useState('');
  const [pendingConnection, setPendingConnection] = useState<any>(null);

  const isValidConnection = useCallback(
    (params: Connection | Edge) => validateConnection(params, nodes, edges).valid,
    [nodes, edges],
  );

  const onConnect = useCallback(
    (params: Connection | Edge) => {
      const validation = validateConnection(params, nodes, edges);
      if (!validation.valid) {
        onInvalidConnection?.(validation.reason || 'このポート同士は接続できません。');
        return;
      }
      saveHistory();
      setEdges((existing) => addEdge({ ...params, animated: true }, existing));
    },
    [edges, nodes, onInvalidConnection, saveHistory, setEdges],
  );

  const onNodeClick = useCallback((_: MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback((event: MouseEvent) => {
    setSelectedNode(null);
    setMenuPos(null);

    if (!reactFlowInstance) return;

    const position = reactFlowInstance.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    const keys = pressedKeys.current;
    let kind = '';

    if (keys.has('b')) {
      kind = 'branch';
    } else if (keys.has('s')) {
      kind = 'sequence';
    } else if (keys.has('d')) {
      kind = 'delay';
    } else if (keys.has('m')) {
      kind = 'multigate';
    } else if (keys.has('c')) {
      kind = 'comment';
    }

    if (kind) {
      saveHistory();
      const node: Node = {
        id: `step-${Date.now()}`,
        type: 'step',
        position,
        data: defaultStepPayload(kind),
      };
      setNodes((existing) => existing.concat(node));
    }
  }, [pressedKeys, reactFlowInstance, saveHistory, setNodes]);

  const onPaneContextMenu = useCallback((event: MouseEvent) => {
    event.preventDefault();
    setMenuPos({ x: event.clientX, y: event.clientY });
    setPendingConnection(null);
  }, []);

  const onConnectEnd = useCallback(
    (event: any, connectionState: any) => {
      if (!connectionState.isValid) {
        setMenuPos({ x: event.clientX, y: event.clientY });
        setPendingConnection(connectionState);
      }
    },
    [],
  );

  const onEdgeClick = useCallback((event: MouseEvent, edge: Edge) => {
    if (event.altKey) {
      saveHistory();
      setEdges((existing) => existing.filter((candidate) => candidate.id !== edge.id));
    }
  }, [saveHistory, setEdges]);

  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      const otherEdges = edges.filter((edge) => edge.id !== oldEdge.id);
      const validation = validateConnection(newConnection, nodes, otherEdges);
      if (!validation.valid) {
        onInvalidConnection?.(validation.reason || '接続を更新できません。');
        return;
      }
      saveHistory();
      setEdges((existing) => reconnectEdge(oldEdge, newConnection, existing));
    },
    [edges, nodes, onInvalidConnection, saveHistory, setEdges],
  );

  const onEdgeDoubleClick = useCallback((event: MouseEvent, edge: Edge) => {
    if (!reactFlowInstance) return;
    saveHistory();

    const position = reactFlowInstance.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    const rerouteNodeId = `reroute-${Date.now()}`;
    const rerouteNode: Node = {
      id: rerouteNodeId,
      type: 'step',
      position,
      data: {
        id: 'reroute',
        type: 'reroute',
        title: 'reroute',
        ports: [
          createPort('in', 'input', [], { id: 'reroute-in', allowMultiple: false }),
          createPort('out', 'output', [], { id: 'reroute-out', allowMultiple: false }),
        ],
      },
    };

    setNodes((existing) => existing.concat(rerouteNode));
    setEdges((existing) => {
      const filtered = existing.filter((candidate) => candidate.id !== edge.id);
      return [
        ...filtered,
        {
          id: `e-${edge.source}-${rerouteNodeId}`,
          source: edge.source,
          target: rerouteNodeId,
          sourceHandle: edge.sourceHandle,
          targetHandle: 'reroute-in',
          animated: true,
        },
        {
          id: `e-${rerouteNodeId}-${edge.target}`,
          source: rerouteNodeId,
          target: edge.target,
          sourceHandle: 'reroute-out',
          targetHandle: edge.targetHandle,
          animated: true,
        },
      ];
    });
  }, [reactFlowInstance, saveHistory, setEdges, setNodes]);

  const onNodesDelete = useCallback(() => {
    saveHistory();
  }, [saveHistory]);

  const onEdgesDelete = useCallback(() => {
    saveHistory();
  }, [saveHistory]);

  const handleAddNodeFromMenu = useCallback((step: { id: string; title?: string; type?: string; ports?: FlowPort[] }) => {
    if (!menuPos || !reactFlowInstance) return;

    saveHistory();
    const position = reactFlowInstance.screenToFlowPosition({ x: menuPos.x, y: menuPos.y });
    const newNode: Node = {
      id: `step-${Date.now()}`,
      type: 'step',
      position,
      data: {
        id: step.id,
        type: step.type ?? 'action',
        title: step.title ?? step.id,
        ports: step.ports ?? [
          createPort('input', 'input', [], { id: 'input-main' }),
          createPort('output', 'output', [], { id: 'output-main', allowMultiple: true }),
        ],
      },
    };

    setNodes((existing) => existing.concat(newNode));

    if (pendingConnection?.fromNode) {
      const sourceNode = pendingConnection.fromHandle?.type === 'target' ? newNode : pendingConnection.fromNode;
      const targetNode = pendingConnection.fromHandle?.type === 'target' ? pendingConnection.fromNode : newNode;
      const handles = pickCompatibleHandles(sourceNode, targetNode, edges);
      if (handles) {
        setEdges((existing) => existing.concat({
          id: `e-${Date.now()}`,
          source: sourceNode.id,
          target: targetNode.id,
          sourceHandle: handles.sourceHandle ?? undefined,
          targetHandle: handles.targetHandle ?? undefined,
          animated: true,
        }));
      }
    }

    setMenuPos(null);
    setMenuFilter('');
    setPendingConnection(null);
  }, [edges, menuPos, pendingConnection, reactFlowInstance, saveHistory, setEdges, setNodes]);

  const updateNodeData = useCallback((key: string, value: string) => {
    if (!selectedNode) return;
    setNodes((existing) =>
      existing.map((node) => (
        node.id === selectedNode.id
          ? { ...node, data: { ...node.data, [key]: value } }
          : node
      )),
    );
    setSelectedNode((previous) => previous ? { ...previous, data: { ...previous.data, [key]: value } } : null);
  }, [selectedNode, setNodes]);

  const updateNodePorts = useCallback((ports: FlowPort[]) => {
    if (!selectedNode) return;
    setNodes((existing) =>
      existing.map((node) => (
        node.id === selectedNode.id
          ? { ...node, data: { ...node.data, ports } }
          : node
      )),
    );
    setSelectedNode((previous) => previous ? { ...previous, data: { ...previous.data, ports } } : null);
  }, [selectedNode, setNodes]);

  const addPortToSelectedNode = useCallback((direction: 'input' | 'output') => {
    const ports = ((selectedNode?.data as { ports?: FlowPort[] } | undefined)?.ports ?? []);
    const nextPort = createUniquePort(direction === 'input' ? 'new-in' : 'new-out', direction, [], ports);
    updateNodePorts([...ports, nextPort]);
  }, [selectedNode, updateNodePorts]);

  const updateSelectedNodePort = useCallback((portId: string, patch: Partial<FlowPort>) => {
    if (!selectedNode) return;

    const ports = ((selectedNode.data as { ports?: FlowPort[] } | undefined)?.ports ?? []);
    const existingPort = ports.find((port) => port.id === portId);
    if (!existingPort) return;

    const siblingPorts = ports.filter((port) => port.id !== portId);
    const normalizedPort = createPort(
      patch.label ?? existingPort.label,
      patch.direction ?? existingPort.direction,
      patch.contracts ?? existingPort.contracts,
      {
        ...existingPort,
        ...patch,
        id: patch.id ?? existingPort.id,
      },
    );
    const nextPort = {
      ...normalizedPort,
      id: ensureUniquePortId(normalizedPort.id, siblingPorts),
    };
    const nextPorts = ports.map((port) => (port.id === portId ? nextPort : port));
    const nextNodes = replaceNodePorts(nodes, selectedNode.id, nextPorts);

    updateNodePorts(nextPorts);
    setEdges((existing) => syncEdgesForUpdatedPort(existing, nextNodes, selectedNode.id, portId, nextPort.id));
  }, [nodes, selectedNode, setEdges, updateNodePorts]);

  const removeSelectedNodePort = useCallback((portId: string) => {
    const ports = ((selectedNode?.data as { ports?: FlowPort[] } | undefined)?.ports ?? []).filter((port) => port.id !== portId);
    updateNodePorts(ports);
    setEdges((existing) => existing.filter((edge) => edge.sourceHandle !== portId && edge.targetHandle !== portId));
  }, [selectedNode, setEdges, updateNodePorts]);

  const deleteSelectedNode = useCallback(() => {
    if (!selectedNode) return;
    saveHistory();
    setNodes((existing) => existing.filter((node) => node.id !== selectedNode.id));
    setEdges((existing) => existing.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id));
    setSelectedNode(null);
  }, [saveHistory, selectedNode, setEdges, setNodes]);

  return {
    selectedNode,
    setSelectedNode,
    menuPos,
    setMenuPos,
    menuFilter,
    setMenuFilter,
    pendingConnection,
    setPendingConnection,
    onConnect,
    onNodeClick,
    onPaneClick,
    onPaneContextMenu,
    onConnectEnd,
    onEdgeClick,
    onReconnect,
    onEdgeDoubleClick,
    onNodesDelete,
    onEdgesDelete,
    handleAddNodeFromMenu,
    updateNodeData,
    updateNodePorts,
    addPortToSelectedNode,
    updateSelectedNodePort,
    removeSelectedNodePort,
    deleteSelectedNode,
    isValidConnection,
  };
}
