import { useState, useCallback, useEffect, useRef } from 'react';
import { useAppStore } from '@/src/store';
import { useT } from '@/src/lib/i18n';
import { cn } from '@/src/lib/utils';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { Plus, Play, Save, Trash2, FileText, CheckCircle2, Clock, Workflow, X, Box, Loader2 } from 'lucide-react';
import CodeMirror from '@uiw/react-codemirror';
import { yaml } from '@codemirror/lang-yaml';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  SelectionMode,
} from '@xyflow/react';
import type { Node, Edge, ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { nodeTypes } from '@/src/components/flow/CustomNodes';
import { nodesToYaml, yamlToNodes } from '@/src/lib/flowUtils';
import { useFlowHistory } from '@/src/hooks/useFlowHistory';
import { useFlowExecution } from '@/src/hooks/useFlowExecution';
import { useFlowKeyboard } from '@/src/hooks/useFlowKeyboard';
import { useFlowDragDrop } from '@/src/hooks/useFlowDragDrop';
import { useFlowEditor } from '@/src/hooks/useFlowEditor';
import type { AvailableStep } from '@/src/lib/types';
import { fetchFlowDetail } from '@/src/lib/api';
import { transformFlowDetail } from '@/src/lib/transforms';

const AVAILABLE_STEPS: AvailableStep[] = [
  { id: 'mounts.init', name: 'mounts.init', pack: 'core', description: 'Initialize mounts' },
  { id: 'registry.load', name: 'registry.load', pack: 'core', description: 'Load registry' },
  { id: 'check_profile', name: 'check_profile', pack: 'utils', description: 'Check user profile' },
  { id: 'emit', name: 'emit', pack: 'core', description: 'Emit an event' },
  { id: 'exec_py', name: 'exec_py', pack: 'python', description: 'Execute Python script' },
  { id: 'http.get', name: 'http.get', pack: 'network', description: 'Make an HTTP GET request' },
  { id: 'http.post', name: 'http.post', pack: 'network', description: 'Make an HTTP POST request' },
  { id: 'log.info', name: 'log.info', pack: 'utils', description: 'Log info message' },
];

/** Inner component that has access to ReactFlow hooks via provider */
function FlowEditorInner() {
  const t = useT();
  const flows = useAppStore(state => state.flows);
  const isLoading = useAppStore(state => state.isLoading);
  const loadFlows = useAppStore(state => state.loadFlows);
  const addFlow = useAppStore(state => state.addFlow);
  const updateFlow = useAppStore(state => state.updateFlow);
  const deleteFlow = useAppStore(state => state.deleteFlow);
  const showDialog = useAppStore(state => state.showDialog);
  const addToast = useAppStore(state => state.addToast);
  const colorMode = useAppStore(state => state.colorMode);

  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newFlowName, setNewFlowName] = useState('');
  const [activeTab, setActiveTab] = useState<'yaml' | 'result'>('yaml');
  const [selectedPack, setSelectedPack] = useState<string>('all');
  const [flowLoading, setFlowLoading] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  const selectedFlow = flows.find(f => f.id === selectedFlowId);
  const packs = ['all', ...Array.from(new Set(AVAILABLE_STEPS.map(s => s.pack)))];
  const filteredSteps = selectedPack === 'all' ? AVAILABLE_STEPS : AVAILABLE_STEPS.filter(s => s.pack === selectedPack);

  // Custom hooks
  const history = useFlowHistory(nodes, edges, setNodes, setEdges);
  const execution = useFlowExecution(nodes, setNodes);

  // Break circular dep: keyboard needs setMenuPos, editor needs pressedKeys
  const menuPosRef = useRef<((pos: { x: number; y: number } | null) => void) | null>(null);

  const keyboard = useFlowKeyboard({
    nodes,
    setNodes,
    saveHistory: history.saveHistory,
    undo: history.undo,
    redo: history.redo,
    execute: execution.execute,
    reactFlowInstance,
    setMenuPos: (pos) => { menuPosRef.current?.(pos); },
  });

  const editorHook = useFlowEditor({
    nodes,
    setNodes,
    edges,
    setEdges,
    saveHistory: history.saveHistory,
    reactFlowInstance,
    pressedKeys: keyboard.pressedKeys,
  });

  // Wire up the ref after editorHook is created
  menuPosRef.current = editorHook.setMenuPos;

  const dragDrop = useFlowDragDrop({
    nodes,
    setNodes,
    setEdges,
    saveHistory: history.saveHistory,
    reactFlowInstance,
    reactFlowWrapper,
  });

  // Pointer tracking
  useEffect(() => {
    return dragDrop.setupPointerTracking();
  }, [dragDrop.setupPointerTracking]);

  // Load flows from API
  useEffect(() => {
    loadFlows();
  }, [loadFlows]);

  // Select first flow when flows load
  useEffect(() => {
    if (flows.length > 0 && !selectedFlowId && !isCreating) {
      setSelectedFlowId(flows[0].id);
    }
  }, [flows, selectedFlowId, isCreating]);

  // Load flow detail when selected flow changes
  useEffect(() => {
    if (selectedFlowId && !isCreating) {
      setFlowLoading(true);
      fetchFlowDetail(selectedFlowId)
        .then((detail) => {
          const flow = transformFlowDetail(detail);
          const { nodes: newNodes, edges: newEdges } = yamlToNodes(flow.content);
          setNodes(newNodes);
          setEdges(newEdges);
          editorHook.setSelectedNode(null);
          execution.clearResult();
        })
        .catch((err) => {
          // Fallback: use flow content from list (empty string)
          if (selectedFlow) {
            const { nodes: newNodes, edges: newEdges } = yamlToNodes(selectedFlow.content);
            setNodes(newNodes);
            setEdges(newEdges);
          }
          addToast(err instanceof Error ? err.message : 'Failed to load flow detail', 'error');
        })
        .finally(() => setFlowLoading(false));
    }
  }, [selectedFlowId]);

  const handleSelectFlow = (id: string) => {
    setSelectedFlowId(id);
    setIsCreating(false);
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setSelectedFlowId(null);
    setNewFlowName('');
    execution.clearResult();

    setNodes([
      { id: 'end-1', type: 'end', position: { x: 250, y: 150 }, data: {} }
    ]);
    setEdges([]);
  };

  const handleSave = async () => {
    const generatedYaml = nodesToYaml(nodes, edges);

    if (isCreating) {
      if (!newFlowName.trim()) {
        addToast(t('flows.name_required'), 'error');
        return;
      }
      const newId = Math.random().toString(36).substring(2, 9);
      const fileName = newFlowName.endsWith('.yaml') ? newFlowName : `${newFlowName}.yaml`;
      await addFlow({ id: newId, name: fileName, content: generatedYaml });
      // After API create + reload, select the new flow
      const updatedFlows = useAppStore.getState().flows;
      const created = updatedFlows.find(f => f.name === fileName);
      if (created) {
        setSelectedFlowId(created.id);
      }
      setIsCreating(false);
      addToast(t('flows.created'), 'success');
    } else if (selectedFlowId) {
      await updateFlow(selectedFlowId, generatedYaml);
      addToast(t('flows.saved'), 'success');
    }
  };

  const handleDelete = () => {
    if (!selectedFlowId) return;
    showDialog({
      title: t('flows.delete_title'),
      message: t('flows.delete_message'),
      confirmText: t('flows.delete_confirm'),
      onConfirm: async () => {
        await deleteFlow(selectedFlowId);
        setSelectedFlowId(null);
        setNodes([]);
        setEdges([]);
        addToast(t('flows.deleted'), 'success');
      },
    });
  };

  const handleExecute = async () => {
    if (!selectedFlowId) return;
    setActiveTab('result');
    const result = await execution.execute();
    if (result) {
      addToast(t('flows.executed'), result.status === 'success' ? 'success' : 'error');
    }
  };

  const onDragStart = (event: React.DragEvent, nodeType: string, stepId: string) => {
    const ghost = new Image();
    ghost.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
    event.dataTransfer.setDragImage(ghost, 0, 0);
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('stepId', stepId);
    event.dataTransfer.effectAllowed = 'move';
  };

  const handleStepMiddleClick = useCallback(
    (event: React.MouseEvent, step: AvailableStep) => {
      if (event.button !== 1) return;
      event.preventDefault();
      if (!reactFlowInstance) return;

      const wrapper = reactFlowWrapper.current;
      if (!wrapper) return;
      const bounds = wrapper.getBoundingClientRect();

      const position = reactFlowInstance.screenToFlowPosition({
        x: bounds.left + bounds.width / 2,
        y: bounds.top + bounds.height / 2,
      });

      history.saveHistory();
      setNodes(nds =>
        nds.concat({
          id: `step-${Date.now()}`,
          type: 'step',
          position,
          data: { id: step.id, type: 'action' },
        })
      );
    },
    [reactFlowInstance, history.saveHistory, setNodes]
  );

  const generatedYaml = nodesToYaml(nodes, edges);

  if (isLoading && flows.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">{t('flows.loading')}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full p-8 flex gap-6 animate-in fade-in slide-in-from-bottom-4">
      {/* Left Pane: Flow List */}
      <div className="flex w-64 flex-col gap-4 rounded-xl border border-border bg-bg-card p-4 shadow-sm shrink-0">
        <Button size="sm" onClick={handleCreateNew} variant={isCreating ? 'default' : 'outline'} className="w-full">
          <Plus className="mr-2 h-4 w-4" />
          {t('flows.new')}
        </Button>
        <div className="flex flex-col gap-2 overflow-y-auto mt-2">
          {flows.map(flow => (
            <div
              key={flow.id}
              onClick={() => handleSelectFlow(flow.id)}
              className={`flex cursor-pointer items-center gap-3 rounded-lg p-3 transition-colors ${selectedFlowId === flow.id && !isCreating ? 'bg-accent text-accent-fg' : 'hover:bg-bg-hover text-text-main'}`}
            >
              <FileText className="h-4 w-4 shrink-0" />
              <span className="truncate text-sm font-medium">{flow.name}</span>
            </div>
          ))}
          {flows.length === 0 && !isCreating && (
            <div className="p-4 text-center text-sm text-text-muted">{t('flows.no_flows')}</div>
          )}
        </div>
      </div>

      {/* Right Pane: Editor */}
      <div className="flex flex-1 flex-col gap-4 rounded-xl border border-border bg-bg-card p-4 shadow-sm overflow-hidden relative">
        {isCreating || selectedFlowId ? (
          <>
            {/* Header */}
            <div className="flex items-center justify-between shrink-0">
              {isCreating ? (
                <Input
                  placeholder={t('flows.name_placeholder')}
                  value={newFlowName}
                  onChange={(e) => setNewFlowName(e.target.value)}
                  className="max-w-xs"
                />
              ) : (
                <h2 className="text-xl font-bold text-text-main">{selectedFlow?.name}</h2>
              )}
              <div className="flex items-center gap-2">
                {!isCreating && (
                  <Button variant="outline" onClick={handleExecute} disabled={true} className="gap-2" title="Flow execution is not yet available">
                    <Play className="h-4 w-4" />
                    {t('flows.execute')}
                  </Button>
                )}
                <Button variant="outline" onClick={handleSave} className="gap-2">
                  <Save className="h-4 w-4" />
                  {t('flows.save')}
                </Button>
                {!isCreating && (
                  <Button variant="destructive" onClick={handleDelete} className="gap-2">
                    <Trash2 className="h-4 w-4" />
                    {t('flows.delete')}
                  </Button>
                )}
              </div>
            </div>

            {/* Block Bar */}
            <div className="flex items-center gap-4 p-2 border border-border rounded-md bg-bg-main shrink-0">
              <select
                value={selectedPack}
                onChange={(e) => setSelectedPack(e.target.value)}
                className="h-8 rounded-md border border-border bg-bg-card px-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {packs.map(p => <option key={p} value={p}>{p === 'all' ? 'All Packs' : p}</option>)}
              </select>
              <div className="flex-1 overflow-x-auto flex gap-2 pb-1 items-center scrollbar-thin">
                {filteredSteps.map(step => (
                  <div
                    key={step.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-card border border-border rounded-full text-xs font-medium cursor-grab hover:border-accent hover:text-accent transition-colors shrink-0 shadow-sm"
                    draggable
                    onDragStart={(e) => onDragStart(e, 'step', step.id)}
                    onMouseDown={(e) => handleStepMiddleClick(e, step)}
                    onAuxClick={(e) => e.preventDefault()}
                    title={`${step.description} (Pack: ${step.pack})`}
                  >
                    <Box className="w-3.5 h-3.5" />
                    {step.name}
                  </div>
                ))}
              </div>
            </div>

            {/* Main Area: Node Editor */}
            <div ref={reactFlowWrapper} className={`flex-1 relative border border-border rounded-md overflow-hidden ${colorMode === 'dark' ? 'bg-[#1a1a1a]' : 'bg-gray-50'}`}>
              {flowLoading ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-accent" />
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={editorHook.onConnect}
                  onNodeClick={editorHook.onNodeClick}
                  onNodeDragStart={dragDrop.onNodeDragStart}
                  onNodeDrag={dragDrop.onNodeDrag}
                  onNodeDragStop={dragDrop.onNodeDragStop}
                  onPaneClick={editorHook.onPaneClick}
                  onPaneContextMenu={editorHook.onPaneContextMenu}
                  onConnectEnd={editorHook.onConnectEnd}
                  onEdgeClick={editorHook.onEdgeClick}
                  onReconnect={editorHook.onReconnect}
                  onEdgeDoubleClick={editorHook.onEdgeDoubleClick}
                  onNodesDelete={editorHook.onNodesDelete}
                  onEdgesDelete={editorHook.onEdgesDelete}
                  onInit={setReactFlowInstance}
                  onDrop={dragDrop.onDrop}
                  onDragOver={dragDrop.onDragOver}
                  nodeTypes={nodeTypes}
                  panOnDrag={[1, 2]}
                  selectionOnDrag={true}
                  selectionMode={SelectionMode.Partial}
                  fitView
                  className={colorMode === 'dark' ? 'bg-[#1a1a1a]' : 'bg-gray-50'}
                >
                  <Background color={colorMode === 'dark' ? '#333' : '#ccc'} gap={16} />
                  <Controls className="bg-bg-card border-border fill-text-main" />
                </ReactFlow>
              )}

              {/* Delete Drop Zone */}
              <div
                className={cn(
                  "absolute bottom-0 left-0 right-0 flex items-center justify-center z-50 pointer-events-none border-t-2 border-dashed transition-all duration-200",
                  dragDrop.isDraggingNode ? "h-20 opacity-100" : "h-0 opacity-0",
                  dragDrop.isOverDeleteZone
                    ? "bg-red-500/30 border-red-500 backdrop-blur-sm"
                    : "bg-red-500/10 border-red-400/50"
                )}
              >
                <div
                  className={cn(
                    "flex items-center gap-2 font-medium text-sm transition-transform duration-150",
                    dragDrop.isOverDeleteZone ? "text-red-300 scale-110" : "text-red-400"
                  )}
                >
                  <Trash2 className="w-5 h-5" />
                  {dragDrop.isOverDeleteZone ? t('flows.release_to_delete') : t('flows.drop_to_delete')}
                </div>
              </div>

              {/* Context Menu */}
              {editorHook.menuPos && (
                <div
                  className="absolute z-50 bg-bg-card border border-border shadow-xl rounded-lg w-64 p-2 flex flex-col"
                  style={{ top: editorHook.menuPos.y, left: editorHook.menuPos.x }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-text-muted px-1">Add Node</span>
                    <button onClick={() => editorHook.setMenuPos(null)} className="text-text-muted hover:text-text-main"><X className="w-3 h-3" /></button>
                  </div>
                  <Input
                    autoFocus
                    placeholder="Search nodes..."
                    value={editorHook.menuFilter}
                    onChange={(e) => editorHook.setMenuFilter(e.target.value)}
                    className="mb-2 h-8 text-sm"
                  />
                  <div className="max-h-64 overflow-y-auto flex flex-col gap-1 scrollbar-thin">
                    {AVAILABLE_STEPS.filter(s => s.name.toLowerCase().includes(editorHook.menuFilter.toLowerCase()) || s.description.toLowerCase().includes(editorHook.menuFilter.toLowerCase())).map(step => (
                      <div
                        key={step.id}
                        className="px-2 py-1.5 hover:bg-bg-hover cursor-pointer text-sm rounded flex flex-col"
                        onClick={() => editorHook.handleAddNodeFromMenu(step)}
                      >
                        <span className="font-medium">{step.name}</span>
                        <span className="text-[10px] text-text-muted">{step.description}</span>
                      </div>
                    ))}
                    {['Branch', 'Sequence', 'Delay', 'Multigate', 'Comment'].filter(n => n.toLowerCase().includes(editorHook.menuFilter.toLowerCase())).map(name => (
                      <div
                        key={name}
                        className="px-2 py-1.5 hover:bg-bg-hover cursor-pointer text-sm rounded flex flex-col border-t border-border mt-1"
                        onClick={() => editorHook.handleAddNodeFromMenu({ id: name.toLowerCase(), name, description: `Basic ${name} node` })}
                      >
                        <span className="font-medium text-accent">{name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Property Panel */}
              {editorHook.selectedNode && (
                <div className="absolute top-4 right-4 w-64 bg-bg-card border border-border rounded-lg shadow-lg z-10 flex flex-col">
                  <div className="flex items-center justify-between p-3 border-b border-border">
                    <h3 className="font-semibold text-sm">{t('flows.properties')}</h3>
                    <button onClick={() => editorHook.setSelectedNode(null)} className="text-text-muted hover:text-text-main">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="p-4 flex flex-col gap-4">
                    {editorHook.selectedNode.type === 'trigger' && (
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-text-muted">Trigger Type</label>
                        <Input
                          value={(editorHook.selectedNode.data.type as string) || ''}
                          onChange={(e) => editorHook.updateNodeData('type', e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                    )}
                    {editorHook.selectedNode.type === 'step' && (
                      <>
                        <div className="space-y-2">
                          <label className="text-xs font-medium text-text-muted">Step ID</label>
                          <Input
                            value={(editorHook.selectedNode.data.id as string) || ''}
                            onChange={(e) => editorHook.updateNodeData('id', e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="text-xs font-medium text-text-muted">Step Type</label>
                          <Input
                            value={(editorHook.selectedNode.data.type as string) || ''}
                            onChange={(e) => editorHook.updateNodeData('type', e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                      </>
                    )}
                    {editorHook.selectedNode.type === 'end' && (
                      <div className="text-sm text-text-muted">End Node</div>
                    )}

                    <Button variant="destructive" size="sm" onClick={editorHook.deleteSelectedNode} className="mt-2">
                      <Trash2 className="w-4 h-4 mr-2" /> {t('flows.delete_node')}
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Area: Tabs */}
            <div className="h-48 shrink-0 flex flex-col border border-border rounded-md overflow-hidden bg-bg-main">
              <div className="flex border-b border-border bg-bg-card">
                <button
                  className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'yaml' ? 'border-b-2 border-accent text-text-main' : 'text-text-muted hover:text-text-main'}`}
                  onClick={() => setActiveTab('yaml')}
                >
                  {t('flows.yaml')}
                </button>
                <button
                  className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'result' ? 'border-b-2 border-accent text-text-main' : 'text-text-muted hover:text-text-main'}`}
                  onClick={() => setActiveTab('result')}
                >
                  {t('flows.result')}
                </button>
              </div>
              <div className="flex-1 overflow-auto">
                {activeTab === 'yaml' && (
                  <CodeMirror
                    value={generatedYaml}
                    height="100%"
                    extensions={[yaml()]}
                    theme={colorMode === 'dark' ? 'dark' : 'light'}
                    readOnly
                    className="h-full text-sm"
                  />
                )}
                {activeTab === 'result' && (
                  <div className="p-4">
                    {execution.isExecuting ? (
                      <div className="flex items-center justify-center h-full text-text-muted">
                        <Clock className="w-4 h-4 mr-2 animate-spin" /> {t('flows.executing')}
                      </div>
                    ) : execution.executionResult ? (
                      <div className="flex flex-col gap-2">
                        {execution.executionResult.steps.map((step, i) => (
                          <div key={i} className="flex items-center justify-between rounded border border-border bg-bg-card p-2 text-sm">
                            <div className="flex items-center gap-2">
                              {step.status === 'success' ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <X className="w-4 h-4 text-red-500" />}
                              <span className="font-medium text-text-main">{step.name}</span>
                            </div>
                            <div className="flex items-center gap-2 text-text-muted">
                              <Clock className="h-3 w-3" />
                              <span>{step.duration}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full text-text-muted text-sm">
                        {t('flows.no_result')}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full flex-col items-center justify-center text-center relative overflow-hidden rounded-[var(--radius)]">
            <div className="absolute inset-0 opacity-5">
              <img src="https://picsum.photos/seed/flow/800/600" alt="Flow Background" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
            </div>
            <div className="relative z-10 flex flex-col items-center">
              <Workflow className="mb-4 h-16 w-16 text-accent opacity-80" />
              <h3 className="text-xl font-bold text-text-main mb-2">{t('flows.title')}</h3>
              <p className="text-sm text-text-muted max-w-sm">
                {t('flows.subtitle')}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// H-7: ReactFlowProvider wraps the entire component
export function Flows() {
  return (
    <ReactFlowProvider>
      <FlowEditorInner />
    </ReactFlowProvider>
  );
}
