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
    <div className="relative min-h-[540px] overflow-hidden rounded-2xl border border-border bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08),_transparent_45%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent)]">
      <svg viewBox={`0 0 ${layout.width} ${layout.height}`} className="absolute inset-0 h-full w-full">
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
            'absolute rounded-2xl border px-3 py-2 text-left shadow-[0_18px_40px_-28px_rgba(0,0,0,0.85)] transition-all',
            nodeChrome(node),
            selectedNodeId === node.id && 'ring-2 ring-white/70 shadow-[0_24px_50px_-30px_rgba(255,255,255,0.55)]',
          )}
          style={{
            left: node.x,
            top: node.y,
            width: node.width,
            height: node.height,
          }}
          onClick={() => onSelectNode?.(node.id)}
        >
          <div className="truncate text-[11px] uppercase tracking-[0.18em] text-white/55">
            {graphNodeKindLabel(node)}
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-white">{node.label || node.ref || node.id}</div>
          <div className="truncate text-xs text-white/65">{node.ref || node.id}</div>
        </button>
      ))}
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
  if (prefix === 'profile') return 'border-white/35 bg-white/10 backdrop-blur-sm';
  if (prefix === 'tool') return 'border-emerald-400/40 bg-emerald-500/14';
  if (prefix === 'webhook') return 'border-orange-400/40 bg-orange-500/14';
  if (prefix === 'api') return 'border-amber-400/45 bg-amber-500/14';
  if (prefix === 'prompt') return 'border-fuchsia-400/40 bg-fuchsia-500/14';
  if (prefix === 'frontend') return 'border-sky-400/40 bg-sky-500/14';
  if (prefix === 'flow') return 'border-teal-400/40 bg-teal-500/14';
  if (prefix === 'storage' || node.kind === 'storage') return 'border-slate-400/35 bg-slate-500/10';
  return 'border-slate-300/25 bg-slate-500/10';
}
