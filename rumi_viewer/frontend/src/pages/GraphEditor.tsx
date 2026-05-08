import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Save, TriangleAlert } from 'lucide-react';

import { Button } from '@/src/components/ui/Button';
import {
  compileCapabilityGraph,
  fetchCapabilityGraph,
  fetchCapabilityGraphs,
  fetchCapabilityProfiles,
  saveCapabilityGraph,
  validateCapabilityGraph,
} from '@/src/lib/api';
import type {
  ApiCapabilityGraph,
  ApiCapabilityProfile,
  CapabilityGraphCompileResponseData,
} from '@/src/lib/apiTypes';
import { useAppStore } from '@/src/store';

function formatGraph(graph: ApiCapabilityGraph | null): string {
  if (!graph) return '';
  return JSON.stringify({
    version: 'rumi.graph.v1',
    graph_id: graph.graph_id,
    display_name: graph.display_name ?? {en: graph.label},
    description: graph.description ?? {},
    nodes: graph.nodes,
    edges: graph.edges,
    metadata: graph.metadata ?? {},
  }, null, 2);
}

export function GraphEditor() {
  const addToast = useAppStore(state => state.addToast);
  const [profiles, setProfiles] = useState<ApiCapabilityProfile[]>([]);
  const [graphs, setGraphs] = useState<ApiCapabilityGraph[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [selectedGraphId, setSelectedGraphId] = useState('');
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<CapabilityGraphCompileResponseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const parsedGraph = useMemo(() => {
    try {
      const parsed = JSON.parse(source);
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null;
    } catch {
      return null;
    }
  }, [source]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const [profileData, graphData] = await Promise.all([
          fetchCapabilityProfiles(),
          fetchCapabilityGraphs(),
        ]);
        if (!mounted) return;
        setProfiles(profileData.profiles);
        setGraphs(graphData.graphs);
        setSelectedProfileId(profileData.profiles[0]?.profile_id ?? '');
        const graph = graphData.graphs[0] ?? null;
        setSelectedGraphId(graph?.graph_id ?? '');
        setSource(formatGraph(graph));
      } catch (error) {
        addToast(error instanceof Error ? error.message : 'Failed to load graphs', 'error');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, [addToast]);

  async function loadGraph(graphId: string) {
    setSelectedGraphId(graphId);
    setPreview(null);
    if (!graphId) {
      setSource('');
      return;
    }
    const result = await fetchCapabilityGraph(graphId);
    setSource(formatGraph(result.graph));
  }

  async function runPreview(kind: 'validate' | 'compile') {
    if (!parsedGraph || !selectedProfileId) {
      addToast('Graph JSON and profile are required', 'error');
      return;
    }
    setBusy(true);
    try {
      const graphId = String(parsedGraph.graph_id || selectedGraphId || 'draft');
      const result = kind === 'validate'
        ? await validateCapabilityGraph(graphId, selectedProfileId, parsedGraph)
        : await compileCapabilityGraph(graphId, selectedProfileId, parsedGraph);
      setPreview(result);
    } catch (error) {
      addToast(error instanceof Error ? error.message : 'Preview failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function saveGraph() {
    if (!parsedGraph) {
      addToast('Graph JSON is invalid', 'error');
      return;
    }
    setBusy(true);
    try {
      const created = !graphs.some(graph => graph.graph_id === parsedGraph.graph_id);
      const saved = await saveCapabilityGraph(parsedGraph, created);
      addToast(created ? 'Graph created' : 'Graph saved', 'success');
      setSelectedGraphId(saved.graph.graph_id);
      const graphData = await fetchCapabilityGraphs();
      setGraphs(graphData.graphs);
    } catch (error) {
      addToast(error instanceof Error ? error.message : 'Save failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center gap-2 text-text-muted">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading graphs</span>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-border px-6 py-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-main">Capability Graphs</h1>
        </div>
        <Button onClick={saveGraph} disabled={busy || !parsedGraph}>
          <Save className="w-4 h-4 mr-2" />
          Save
        </Button>
      </div>

      <div className="grid grid-cols-[280px_minmax(0,1fr)_360px] min-h-0 flex-1">
        <aside className="border-r border-border p-4 space-y-4 overflow-y-auto">
          <label className="block text-xs font-medium text-text-muted">Profile</label>
          <select
            className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm"
            value={selectedProfileId}
            onChange={event => setSelectedProfileId(event.target.value)}
          >
            {profiles.map(profile => (
              <option key={profile.profile_id} value={profile.profile_id}>{profile.label}</option>
            ))}
          </select>

          <label className="block text-xs font-medium text-text-muted">Graph</label>
          <select
            className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm"
            value={selectedGraphId}
            onChange={event => void loadGraph(event.target.value)}
          >
            {graphs.map(graph => (
              <option key={graph.graph_id} value={graph.graph_id}>{graph.label}</option>
            ))}
          </select>

          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => void runPreview('validate')} disabled={busy || !parsedGraph}>
              Validate
            </Button>
            <Button variant="secondary" onClick={() => void runPreview('compile')} disabled={busy || !parsedGraph}>
              Compile
            </Button>
          </div>
        </aside>

        <main className="min-h-0">
          <textarea
            className="h-full w-full resize-none bg-bg-main p-4 font-mono text-sm text-text-main outline-none"
            value={source}
            spellCheck={false}
            onChange={event => setSource(event.target.value)}
          />
        </main>

        <aside className="border-l border-border p-4 overflow-y-auto">
          <h2 className="text-sm font-semibold text-text-main">Preview</h2>
          {!preview ? (
            <div className="mt-4 text-sm text-text-muted">No preview yet</div>
          ) : (
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-2 text-sm">
                {preview.ok ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : <TriangleAlert className="w-4 h-4 text-amber-600" />}
                <span>{preview.ok ? 'Ready' : 'Needs attention'}</span>
              </div>
              {preview.diagnostics.map((item, index) => (
                <div key={`${item.code}-${index}`} className="rounded-md border border-border p-3 text-xs">
                  <div className="font-medium text-text-main">{item.code}</div>
                  <div className="mt-1 text-text-muted">{item.message}</div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
