import { useState, useCallback } from 'react';
import type { Node, Edge, Connection, ReactFlowInstance } from '@xyflow/react';
import { addEdge, reconnectEdge } from '@xyflow/react';

interface UseFlowEditorParams {
  nodes: Node[];
  setNodes: (updater: Node[] | ((nodes: Node[]) => Node[])) => void;
  edges: Edge[];
  setEdges: (updater: Edge[] | ((edges: Edge[]) => Edge[])) => void;
  saveHistory: () => void;
  reactFlowInstance: ReactFlowInstance | null;
  pressedKeys: React.RefObject<Set<string>>;
}

export function useFlowEditor({
  nodes,
  setNodes,
  edges,
  setEdges,
  saveHistory,
  reactFlowInstance,
  pressedKeys,
}: UseFlowEditorParams) {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const [menuFilter, setMenuFilter] = useState('');
  const [pendingConnection, setPendingConnection] = useState<any>(null);

  const onConnect = useCallback(
    (params: Connection | Edge) => {
      saveHistory();
      setEdges(eds => addEdge({ ...params, animated: true }, eds));
    },
    [setEdges, saveHistory],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback((event: React.MouseEvent) => {
    setSelectedNode(null);
    setMenuPos(null);

    if (!reactFlowInstance) return;

    const position = reactFlowInstance.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    const keys = pressedKeys.current;
    let newNodeType = '';
    let newNodeData: Record<string, unknown> = {};

    if (keys.has('b')) {
      newNodeType = 'step';
      newNodeData = { id: 'branch', type: 'action', description: 'Branch' };
    } else if (keys.has('s')) {
      newNodeType = 'step';
      newNodeData = { id: 'sequence', type: 'action', description: 'Sequence' };
    } else if (keys.has('d')) {
      newNodeType = 'step';
      newNodeData = { id: 'delay', type: 'action', description: 'Delay' };
    } else if (keys.has('p')) {
      newNodeType = 'trigger';
      newNodeData = { type: 'event_begin_play' };
    } else if (keys.has('m')) {
      newNodeType = 'step';
      newNodeData = { id: 'multigate', type: 'action', description: 'Multigate' };
    } else if (keys.has('c')) {
      newNodeType = 'step';
      newNodeData = { id: 'comment', type: 'comment', description: 'Comment' };
    }

    if (newNodeType) {
      saveHistory();
      const newNode: Node = {
        id: `${newNodeType}-${Date.now()}`,
        type: newNodeType,
        position,
        data: newNodeData,
      };
      setNodes(nds => nds.concat(newNode));
    }
  }, [reactFlowInstance, setNodes, saveHistory, pressedKeys]);

  const onPaneContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    setMenuPos({ x: event.clientX, y: event.clientY });
    setPendingConnection(null);
  }, []);

  const onConnectEnd = useCallback(
    (event: any, connectionState: any) => {
      if (!connectionState.isValid) {
        const { clientX, clientY } = event;
        setMenuPos({ x: clientX, y: clientY });
        setPendingConnection(connectionState);
      }
    },
    []
  );

  const onEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
    if (event.altKey) {
      saveHistory();
      setEdges(eds => eds.filter(e => e.id !== edge.id));
    }
  }, [setEdges, saveHistory]);

  // H-5: renamed from onEdgeUpdate to onReconnect
  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      saveHistory();
      setEdges(els => reconnectEdge(oldEdge, newConnection, els));
    },
    [setEdges, saveHistory]
  );

  const onEdgeDoubleClick = useCallback((event: React.MouseEvent, edge: Edge) => {
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
      data: { id: 'reroute', type: 'reroute' },
    };

    setNodes(nds => nds.concat(rerouteNode));

    setEdges(eds => {
      const filtered = eds.filter(e => e.id !== edge.id);
      return [
        ...filtered,
        { id: `e-${edge.source}-${rerouteNodeId}`, source: edge.source, target: rerouteNodeId, sourceHandle: edge.sourceHandle, animated: true },
        { id: `e-${rerouteNodeId}-${edge.target}`, source: rerouteNodeId, target: edge.target, targetHandle: edge.targetHandle, animated: true },
      ];
    });
  }, [reactFlowInstance, saveHistory, setNodes, setEdges]);

  const onNodesDelete = useCallback(() => {
    saveHistory();
  }, [saveHistory]);

  const onEdgesDelete = useCallback(() => {
    saveHistory();
  }, [saveHistory]);

  const handleAddNodeFromMenu = useCallback((step: { id: string }) => {
    if (!menuPos || !reactFlowInstance) return;

    saveHistory();
    const position = reactFlowInstance.screenToFlowPosition({ x: menuPos.x, y: menuPos.y });
    const newNode: Node = {
      id: `step-${Date.now()}`,
      type: 'step',
      position,
      data: { id: step.id, type: 'action' },
    };

    setNodes(nds => nds.concat(newNode));

    if (pendingConnection && pendingConnection.fromNode) {
      const isTarget = pendingConnection.fromHandle?.type === 'target';
      const newEdge: Edge = {
        id: `e-${Date.now()}`,
        source: isTarget ? newNode.id : pendingConnection.fromNode.id,
        target: isTarget ? pendingConnection.fromNode.id : newNode.id,
        sourceHandle: isTarget ? null : pendingConnection.fromHandle?.id,
        targetHandle: isTarget ? pendingConnection.fromHandle?.id : null,
        animated: true,
      };
      setEdges(eds => eds.concat(newEdge));
    }

    setMenuPos(null);
    setMenuFilter('');
    setPendingConnection(null);
  }, [menuPos, reactFlowInstance, saveHistory, setNodes, setEdges, pendingConnection]);

  const updateNodeData = useCallback((key: string, value: string) => {
    if (!selectedNode) return;
    setNodes(nds =>
      nds.map(node => {
        if (node.id === selectedNode.id) {
          return { ...node, data: { ...node.data, [key]: value } };
        }
        return node;
      })
    );
    setSelectedNode(prev => prev ? { ...prev, data: { ...prev.data, [key]: value } } : null);
  }, [selectedNode, setNodes]);

  const deleteSelectedNode = useCallback(() => {
    if (!selectedNode) return;
    saveHistory();
    setNodes(nds => nds.filter(node => node.id !== selectedNode.id));
    setEdges(eds => eds.filter(edge => edge.source !== selectedNode.id && edge.target !== selectedNode.id));
    setSelectedNode(null);
  }, [selectedNode, saveHistory, setNodes, setEdges]);

  return {
    selectedNode,
    setSelectedNode,
    menuPos,
    setMenuPos,
    menuFilter,
    setMenuFilter,
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
    deleteSelectedNode,
  };
}
