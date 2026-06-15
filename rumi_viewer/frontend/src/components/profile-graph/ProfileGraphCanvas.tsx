import type {ApiProfileGraphEdge, ApiProfileGraphNode} from '@/src/lib/apiTypes';
import {graphNodeKindLabel} from '@/src/lib/profileGraph';
import {edgePath, layoutProfileGraph} from '@/src/lib/profileGraphLayout';
import {cn} from '@/src/lib/utils';

interface ProfileGraphCanvasProps {
  nodes: ApiProfileGraphNode[];
  edges: ApiProfileGraphEdge[];
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string) => void;
  emptyMessage?: string;
}

export function ProfileGraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  emptyMessage = 'No nodes selected yet. Use the + buttons to wire this profile.',
}: ProfileGraphCanvasProps) {
  if (!nodes.length) {
    return (
      <div className="flex min-h-[520px] items-center justify-center rounded-2xl border border-dashed border-border bg-bg-card/60 p-6 text-center text-sm text-text-muted">
        {emptyMessage}
      </div>
    );
  }

  const layout = layoutProfileGraph(nodes);
  const positions = new Map(layout.nodes.map((node) => [node.id, node]));

  return (
    <div className="relative min-h-[620px] overflow-auto rounded-xl border border-border bg-bg-main">
      <div className="relative" style={{width: layout.width, height: layout.height}}>
        <svg
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className="absolute left-0 top-0"
        >
          {edges.map((edge) => {
            const path = edgePath(edge, positions);
            if (!path) {
              return null;
            }
            return (
              <path
                key={edge.id}
                d={path}
                fill="none"
                stroke={edgeStroke(edge)}
                strokeWidth={edge.kind === 'fallback' ? 1.5 : 2}
                strokeDasharray={edge.kind === 'fallback' ? '4 4' : edge.kind.includes('api') ? '2 0' : '0'}
                opacity={edge.active ? 0.88 : 0.4}
              />
            );
          })}
        </svg>

        {layout.nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            className={cn(
              'absolute rounded-xl border px-3 py-2 text-left shadow-none transition-colors hover:bg-bg-hover',
              nodeChrome(node),
              selectedNodeId === node.id && 'ring-2 ring-accent/40',
            )}
            style={{
              left: node.x,
              top: node.y,
              width: node.width,
              height: node.height,
            }}
            onClick={() => onSelectNode?.(node.id)}
          >
            <div className="truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">
              {graphNodeKindLabel(node)}
            </div>
            <div className="mt-1 truncate text-sm font-semibold text-text-main">{node.label || node.ref || node.id}</div>
            <div className="truncate text-xs text-text-muted">{node.ref || node.id}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function edgeStroke(edge: ApiProfileGraphEdge): string {
  if (edge.kind === 'uses_prompt') return '#b794f4';
  if (edge.kind === 'selects' || edge.kind === 'executes') return '#34d399';
  if (edge.kind === 'receives_from' || edge.kind === 'delivers_to') return '#fb923c';
  if (edge.kind === 'allows_api' || edge.kind === 'handled_by') return '#fbbf24';
  if (edge.kind === 'uses_frontend') return '#60a5fa';
  if (edge.kind === 'launches_flow' || edge.kind === 'launches_graph') return '#2dd4bf';
  if (edge.kind === 'fallback') return '#f87171';
  return '#94a3b8';
}

function nodeChrome(node: ApiProfileGraphNode): string {
  const prefix = node.id.split(':', 1)[0];
  if (prefix === 'profile') return 'border-accent/50 bg-accent/8';
  if (prefix === 'tool') return 'border-emerald-500/40 bg-emerald-500/10';
  if (prefix === 'webhook') return 'border-orange-500/40 bg-orange-500/10';
  if (prefix === 'api') return 'border-amber-500/45 bg-amber-500/10';
  if (prefix === 'prompt') return 'border-fuchsia-500/40 bg-fuchsia-500/10';
  if (prefix === 'frontend') return 'border-sky-500/40 bg-sky-500/10';
  if (prefix === 'flow') return 'border-teal-500/40 bg-teal-500/10';
  if (prefix === 'storage' || node.kind === 'storage') return 'border-slate-500/35 bg-slate-500/10';
  return 'border-border bg-bg-card';
}
